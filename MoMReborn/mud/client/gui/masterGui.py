# Embedded file name: mud\client\gui\masterGui.pyo
from tgenative import *
from mud.tgepython.console import TGEExport
from mud.world.shared.worlddata import WorldInfo
from twisted.spread import pb
from twisted.internet import reactor
from twisted.cred.credentials import UsernamePassword
from mud.world.defines import *
from mud.gamesettings import *
import os
import time
from md5 import md5

def CheckPublicName():
    pname = TGEGetGlobal('$pref::PublicName')
    if pname == 'ThePlayer':
        TGESetGlobal('$pref::PublicName', '')


MasterPerspective = None
WORLDS = []
FILTERED_WORLDS = []
WORLDINFO = None
CWORLDNAME = None
WORLDINFOCACHE = {}
RETRIEVETIMES = {}
WORLDTEXT = '<shadowcolor:000000><shadow:1:1><just:center><lmargin%:2><rmargin%:98><font:Arial Bold:20>Minions of Mirth\n<font:Arial:18><color:BBBBFF>World Server\n\n<font:Arial:16><color:FFFFFF>No Information Available'
WORLDTEXT = WORLDTEXT.replace('\r', '\\r')
WORLDTEXT = WORLDTEXT.replace('\n', '\\n')
WORLDTEXT = WORLDTEXT.replace('\x07', '\\a')
WORLDTEXT = WORLDTEXT.replace('"', '\\"')
RETRIEVETEXT = '<shadowcolor:000000><shadow:1:1><just:center><lmargin%:2><rmargin%:98><font:Arial Bold:20>Minions of Mirth\n<font:Arial:18><color:BBBBFF>World Server\n\n<font:Arial:20><color:FFFFFF>Retrieving World Server Information'
RETRIEVETEXT = RETRIEVETEXT.replace('\r', '\\r')
RETRIEVETEXT = RETRIEVETEXT.replace('\n', '\\n')
RETRIEVETEXT = RETRIEVETEXT.replace('\x07', '\\a')
RETRIEVETEXT = RETRIEVETEXT.replace('"', '\\"')
SERVER_PREMIUM = 0
SERVER_FREE = 1
SERVER_PG = 2
SERVERTYPE = SERVER_PG
MASTER_LOGIN_PLAYER = None
MASTER_LOGIN_GUARDIAN = None
MASTER_LOGIN_IMMORTAL = None

def GotWorldInfo(results, perspective, worldName):
    global CWORLDNAME
    perspective.broker.transport.loseConnection()
    text, banner = results
    text = text.replace('\r', '\\r')
    text = text.replace('\n', '\\n')
    text = text.replace('\x07', '\\a')
    text = text.replace('"', '\\"')
    hasBanner = False
    if banner and len(banner):
        hasBanner = True
        filename = './%s/cache/worldbanners/%s.jpg' % (GAMEROOT, worldName)
        try:
            path = os.path.dirname(filename)
            os.makedirs(path)
        except:
            pass

        f = file(filename, 'wb')
        f.write(banner)
        f.close()
    WORLDINFOCACHE[worldName] = (text, hasBanner)
    if CWORLDNAME == worldName:
        SetWorldInfo(worldName)


def QueryWorldInfoConnected(perspective, worldName):
    d = perspective.callRemote('QueryAvatar', 'retrieveWorldInfo')
    d.addCallbacks(GotWorldInfo, QueryWorldInfoFailure, (perspective, worldName), {}, (worldName,))


def QueryWorldInfoFailure(reason, worldName):
    print 'failed to query world %s: %s' % (worldName, reason)
    if CWORLDNAME == worldName:
        bitmap = TGEObject('WORLD_BANNER')
        bitmap.setBitmap('~/data/ui/elements/mmws')
        TGEEval('WORLD_DESC.setText("%s");' % WORLDTEXT)


def QueryWorldInfo(worldname):
    global WORLDS
    for winfo in WORLDS:
        if winfo.worldName == worldname:
            factory = pb.PBClientFactory()
            reactor.connectTCP(winfo.worldIP, winfo.worldPort, factory, timeout=DEF_TIMEOUT)
            password = md5('-').digest()
            d = factory.login(UsernamePassword('Query-Query', password), pb.Root())
            d.addCallback(QueryWorldInfoConnected, (worldname,))
            d.addErrback(QueryWorldInfoFailure, (worldname,))
            return True


def NewPlayerConnected(npperspective):
    global WORLDINFO
    from worldLoginDlg import Setup
    Setup(npperspective, WORLDINFO)


def PlayerSubmittedToWorld(result):
    global MASTER_LOGIN_IMMORTAL
    global MASTER_LOGIN_GUARDIAN
    if not result[0]:
        TGECall('CloseMessagePopup')
        TGECall('MessageBoxOK', 'Error', result[1])
        return
    from mud.client.playermind import PlayerMind
    from mud.client.gui.worldLoginDlg import PlayerConnected, SetWorldInfo
    from mud.client.gui.worldLoginDlg import Failure as MyFailure
    SetWorldInfo(WORLDINFO)
    mind = PlayerMind()
    factory = pb.PBClientFactory()
    factory.unsafeTracebacks = LOCALTEST or GAMEBUILD_TEST
    mind.worldIP = WORLDINFO.worldIP
    reactor.connectTCP(WORLDINFO.worldIP, WORLDINFO.worldPort, factory, timeout=DEF_TIMEOUT)
    role = 'Player'
    if TGEGetGlobal('$pref::GM_LOGIN') == '1':
        TGESetGlobal('$pref::GM_LOGIN_ROLE', 'Player')
        if int(MASTER_LOGIN_IMMORTAL.getValue()):
            TGESetGlobal('$pref::GM_LOGIN_ROLE', 'Immortal')
            role = 'Immortal'
        elif int(MASTER_LOGIN_GUARDIAN.getValue()):
            TGESetGlobal('$pref::GM_LOGIN_ROLE', 'Guardian')
            role = 'Guardian'
    password = md5(result[1]).digest()
    d = factory.login(UsernamePassword('%s-%s' % (TGEGetGlobal('$pref::PublicName'), role), password), mind)
    d.addCallbacks(PlayerConnected, MyFailure, (mind,))


def OnMasterSelectWorld():
    global WORLDINFO
    global FILTERED_WORLDS
    global MasterPerspective
    CheckPublicName()
    try:
        tc = TGEObject('MasterWorldList')
        sr = int(tc.getSelectedId())
        winfo = FILTERED_WORLDS[sr]
        WORLDINFO = winfo
        TGESetGlobal('$Py::WORLDNAME', 'PrairieWorld')
        TGECall('MessagePopup', 'Contacting World...', 'Please wait...')
        try:
            wn = WORLDINFO.worldName.replace(' ', '_')
            x = TGEGetGlobal('$pref::WorldPassword_%s' % wn)
            if len(x) == 8:
                TGESetGlobal('$pref::WorldPassword', x)
        except:
            pass

        d = MasterPerspective.callRemote('PlayerAvatar', 'submitPlayerToWorld', winfo.worldName)
        d.addCallbacks(PlayerSubmittedToWorld, Failure)
    except:
        pass


def EnumLiveWorldsResults(worlds):
    global WORLDS
    global SERVERTYPE
    global FILTERED_WORLDS
    TGECall('CloseMessagePopup')
    WORLDS = worlds
    FILTERED_WORLDS = []
    TGEObject('MASTERGUI_WORLDPANEL').visible = True
    wscroll = TGEObject('MASTERGUI_WORLDSCROLL')
    wlist = TGEObject('MasterWorldList')
    passtext = TGEObject('MASTER_GUI_PASSWORDTEXT')
    statustext = TGEObject('MASTER_GUI_STATUSTEXT')
    wnametext = TGEObject('MASTERGUI_WORLDNAME')
    ss = []
    for x in xrange(0, 10):
        s = TGEObject('MASTERGUI_SS%i' % x)
        s.visible = False
        ss.append(s)

    if SERVERTYPE == SERVER_PG:
        wscroll.extent = '141 215'
        wlist.extent = '146 8'
        passtext.visible = False
        statustext.visible = False
        wnametext.visible = False
    else:
        wscroll.extent = '260 215'
        wlist.extent = '256 51'
        passtext.visible = True
        statustext.visible = True
        wnametext.visible = True
    tc = TGEObject('MasterWorldList')
    tc.setVisible(False)
    tc.clear()
    i = 0
    for wi in worlds:
        pg = 'FREE ' in wi.worldName.upper() or 'PREMIUM ' in wi.worldName.upper()
        if pg and SERVERTYPE != SERVER_PG:
            continue
        if not pg and SERVERTYPE == SERVER_PG:
            continue
        FILTERED_WORLDS.append(wi)
        pw = 'N'
        if wi.hasPlayerPassword:
            pw = 'Y'
        p = '-1/-1'
        if SERVERTYPE == SERVER_PG:
            p = 'Open'
            if hasattr(wi, 'maxPlayers'):
                if wi.numLivePlayers < wi.maxPlayers:
                    p = 'Open'
                else:
                    p = 'Full'
        elif hasattr(wi, 'maxPlayers'):
            p = '%i/%i' % (wi.numLivePlayers, wi.maxPlayers)
        if SERVERTYPE == SERVER_PG:
            tc.addRow(i, '%s' % wi.worldName)
            ss[i].visible = True
            f = float(wi.numLivePlayers) / 80.0
            if f > 1.0:
                f = 1.0
            ss[i].setValue(f)
        else:
            tc.addRow(i, '%s \t %s \t %s' % (wi.worldName, p, pw))
        i += 1

    tc.setSelectedRow(0)
    tc.scrollVisible(0)
    tc.setActive(True)
    tc.setVisible(True)
    PyOnWorldChoose()


def Failure(reason):
    TGECall('CloseMessagePopup')
    TGECall('MessageBoxOK', 'Error!', reason.getErrorMessage())


def OnRefreshWorlds():
    if MasterPerspective:
        TGECall('MessagePopup', 'Refreshing Worlds...', 'Please wait...')
        try:
            d = MasterPerspective.callRemote('EnumWorldsAvatar', 'enumLiveWorlds')
            d.addCallbacks(EnumLiveWorldsResults, Failure)
        except:
            TGECall('CloseMessagePopup')
            TGECall('MessageBoxOK', 'Error!', 'Connection to the Master Server has been lost...')


def MasterLogout():
    global MasterPerspective
    if MasterPerspective:
        MasterPerspective.broker.transport.loseConnection()
        MasterPerspective = None
    return


def OnMasterGuiLogout():
    MasterLogout()
    TGEEval('Canvas.setContent(MainMenuGui);')
    TGESetGlobal('$Py::WORLDNAME', '')


def Setup(perspective):
    global MASTER_LOGIN_PLAYER
    global MasterPerspective
    from mud.client.playermind import SimMind
    SimMind.directConnect = ''
    TGEObject('MASTERGUI_WORLDPANEL').visible = False
    MASTER_LOGIN_PLAYER.visible = False
    MASTER_LOGIN_GUARDIAN.visible = False
    MASTER_LOGIN_IMMORTAL.visible = False
    if TGEGetGlobal('$pref::GM_LOGIN') == '1':
        MASTER_LOGIN_PLAYER.visible = True
        MASTER_LOGIN_GUARDIAN.visible = True
        MASTER_LOGIN_IMMORTAL.visible = True
        v = TGEGetGlobal('$pref::GM_LOGIN_ROLE')
        if v != None and v.lower() == 'guardian':
            MASTER_LOGIN_PLAYER.setValue(0)
            MASTER_LOGIN_GUARDIAN.setValue(1)
            MASTER_LOGIN_IMMORTAL.setValue(0)
        elif v != None and v.lower() == 'immortal':
            MASTER_LOGIN_PLAYER.setValue(0)
            MASTER_LOGIN_GUARDIAN.setValue(0)
            MASTER_LOGIN_IMMORTAL.setValue(1)
        else:
            MASTER_LOGIN_PLAYER.setValue(1)
            MASTER_LOGIN_GUARDIAN.setValue(0)
            MASTER_LOGIN_IMMORTAL.setValue(0)
    TGESetGlobal('$Py::ISSINGLEPLAYER', 0)
    TGESetGlobal('$Py::LastTell', '')
    MasterPerspective = perspective
    TGEEval('Canvas.setContent(MasterGui);')
    from patcherGui import DisplayPatchInfo
    DisplayPatchInfo()
    OnRefreshWorlds()
    return


def SetWorldInfo(worldname):
    text, hasBanner = WORLDINFOCACHE[worldname]
    if not text:
        text = WORLDTEXT
    TGEEval('WORLD_DESC.setText("%s");' % text)
    bitmap = TGEObject('WORLD_BANNER')
    if not hasBanner:
        bitmap.setBitmap('~/data/ui/elements/mmws')
    else:
        bitmap.setBitmap('~/cache/worldbanners/%s.jpg' % worldname)


def PyOnWorldChoose():
    global CWORLDNAME
    tc = TGEObject('MasterWorldList')
    sr = int(tc.getSelectedId())
    try:
        winfo = FILTERED_WORLDS[sr]
    except:
        return

    CWORLDNAME = winfo.worldName
    i = WORLDINFOCACHE.get(winfo.worldName, None)
    if i:
        SetWorldInfo(winfo.worldName)
    else:
        if RETRIEVETIMES.has_key(winfo.worldName):
            t = RETRIEVETIMES[winfo.worldName]
            t = time.time() - t
            if t < 30:
                bitmap = TGEObject('WORLD_BANNER')
                bitmap.setBitmap('~/data/ui/elements/mmws')
                TGEEval('WORLD_DESC.setText("%s");' % WORLDTEXT)
                return
        bitmap = TGEObject('WORLD_BANNER')
        bitmap.setBitmap('~/data/ui/elements/mmws')
        TGEEval('WORLD_DESC.setText("%s");' % RETRIEVETEXT)
        RETRIEVETIMES[winfo.worldName] = time.time()
        QueryWorldInfo(winfo.worldName)
    return


def PyOnDirectSelectWorld():
    global WORLDINFO
    TGEEval('Canvas.popDialog(DirectConnectWnd);')
    CheckPublicName()
    ip = TGEObject('DIRECTIP_IP').getValue()
    TGECall('MessagePopup', 'Contacting World...', 'Please wait...')
    port = TGEObject('DIRECTIP_PORT').getValue()
    TGESetGlobal('$pref::DirectConnectIP', ip)
    TGESetGlobal('$pref::DirectConnectPort', port)
    try:
        port = int(port)
    except:
        port = 2006

    from mud.client.playermind import SimMind
    SimMind.directConnect = ip
    WORLDINFO = WorldInfo()
    WORLDINFO.worldName = 'DirectConnection'
    WORLDINFO.worldIP = ip
    WORLDINFO.worldPort = port
    WORLDINFO.hasPlayerPassword = True
    TGESetGlobal('$Py::WORLDNAME', 'DirectConnection')
    password = md5('').digest()
    factory = pb.PBClientFactory()
    reactor.connectTCP(ip, port, factory, timeout=DEF_TIMEOUT)
    d = factory.login(UsernamePassword('NewPlayer-NewPlayer', password), pb.Root())
    d.addCallbacks(NewPlayerConnected, Failure)


def PyOnFreeServers():
    global SERVERTYPE
    if SERVERTYPE != SERVER_FREE:
        SERVERTYPE = SERVER_FREE
        EnumLiveWorldsResults(WORLDS)


def PyOnPremiumServers():
    global SERVERTYPE
    if SERVERTYPE != SERVER_PREMIUM:
        SERVERTYPE = SERVER_PREMIUM
        EnumLiveWorldsResults(WORLDS)


def PyOnPGServers():
    global SERVERTYPE
    if SERVERTYPE != SERVER_PG:
        SERVERTYPE = SERVER_PG
        EnumLiveWorldsResults(WORLDS)


def PyExec():
    global MASTER_LOGIN_IMMORTAL
    global MASTER_LOGIN_PLAYER
    global MASTER_LOGIN_GUARDIAN
    MASTER_LOGIN_PLAYER = TGEObject('MASTER_LOGIN_PLAYER')
    MASTER_LOGIN_GUARDIAN = TGEObject('MASTER_LOGIN_GUARDIAN')
    MASTER_LOGIN_IMMORTAL = TGEObject('MASTER_LOGIN_IMMORTAL')
    CheckPublicName()
    TGEExport(OnMasterSelectWorld, 'Py', 'OnMasterSelectWorld', 'desc', 1, 1)
    TGEExport(OnMasterGuiLogout, 'Py', 'OnMasterGuiLogout', 'desc', 1, 1)
    TGEExport(OnRefreshWorlds, 'Py', 'OnRefreshWorlds', 'desc', 1, 1)
    TGEExport(PyOnWorldChoose, 'Py', 'OnWorldChoose', 'desc', 1, 1)
    TGEExport(PyOnDirectSelectWorld, 'Py', 'OnDirectSelectWorld', 'desc', 1, 1)
    PyOnPGServers()
    PyOnPremiumServers()