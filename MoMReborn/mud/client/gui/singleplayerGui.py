# Embedded file name: mud\client\gui\singleplayerGui.pyo
from tgenative import *
from mud.tgepython.console import TGEExport
from twisted.spread import pb
from twisted.internet import reactor
from twisted.cred.credentials import UsernamePassword
from mud.gamesettings import *
from mud.client.irc import IRCConnect
from mud.client.playermind import PlayerMind, SimMind
from mud.client.gui.worldGui import Setup as worldSetup
from mud.world.worldupdate import WorldUpdate
from mud.worldserver.embedded import SetupEmbeddedWorld, ShutdownEmbeddedWorld
from mud.world.defines import *
from md5 import md5
import os
import shutil
import traceback
WORLDS = []

def Error(value):
    print value


def EnumSinglePlayerWorlds():
    global WORLDS
    worlds = []
    if not os.path.exists('./%s/data/worlds/singleplayer' % GAMEROOT):
        os.makedirs('./%s/data/worlds/singleplayer' % GAMEROOT)
    dir = os.listdir('./%s/data/worlds/singleplayer' % GAMEROOT)
    for fn in dir:
        if os.path.isdir('./%s/data/worlds/singleplayer/%s' % (GAMEROOT, fn)):
            worlds.append(fn)

    WORLDS = worlds
    tc = TGEObject('SINGLEPLAYER_WORLDLIST')
    tc.setVisible(False)
    tc.clear()
    for i, wi in enumerate(worlds):
        TGEEval('SINGLEPLAYER_WORLDLIST.addRow(%i,"%s" TAB "%s");' % (i, wi, ''))

    tc.setSelectedRow(0)
    tc.scrollVisible(0)
    tc.setActive(True)
    tc.setVisible(True)


WORLDDB = None

def PlayerConnected(perspective, mind):
    global WORLDDB
    mind.setPerspective(perspective)
    worldSetup(perspective)
    shutil.copyfile(WORLDDB, WORLDDB + '.good')


def OnLoadSingleWorld(worldname = None):
    global WORLDDB
    TGESetGlobal('$Py::ISSINGLEPLAYER', 1)
    TGESetGlobal('$Py::LastTell', '')
    if not worldname:
        tc = TGEObject('SINGLEPLAYER_WORLDLIST')
        sr = int(tc.getSelectedId())
        if sr >= 0 and len(WORLDS):
            worldname = WORLDS[sr]
    if worldname:
        TGECall('MessagePopup', 'Loading World...', 'Please wait...')
        TGEEval('Canvas.repaint();')
        try:
            try:
                WORLDDB = '%s/data/worlds/singleplayer/%s/world.db' % (GAMEROOT, worldname)
                r = WorldUpdate(WORLDDB, '%s/data/worlds/multiplayer.baseline/world.db' % GAMEROOT, True)
            except:
                TGECall('CloseMessagePopup')
                TGECall('MessageBoxOK', 'Problem Updating World!', 'There was an error updating this world!')
                return

            if not r:
                SetupEmbeddedWorld(worldname)
            else:
                TGECall('CloseMessagePopup')
                return
        except:
            TGECall('CloseMessagePopup')
            TGECall('MessageBoxOK', 'Problem Loading World!', 'There was an error loading this world!')
            traceback.print_exc()
            ShutdownEmbeddedWorld()
            return

        TGECall('CloseMessagePopup')
        TGESetGlobal('$Py::WORLDNAME', worldname)
        factory = pb.PBClientFactory()
        reactor.connectTCP('127.0.0.1', 3013, factory, timeout=DEF_TIMEOUT)
        mind = PlayerMind()
        password = md5('ThePlayer').digest()
        d = factory.login(UsernamePassword('ThePlayer-Immortal', password), mind)
        d.addCallback(PlayerConnected, mind)
        d.addErrback(Error)


DWORLD = ''

def OnReallyDeleteSingleWorld():
    global DWORLD
    if os.path.isdir('./%s/data/worlds/singleplayer/%s' % (GAMEROOT, DWORLD)):
        try:
            shutil.rmtree('./%s/data/worlds/singleplayer/%s' % (GAMEROOT, DWORLD))
        except:
            traceback.print_exc()

    EnumSinglePlayerWorlds()


def OnDeleteSingleWorld():
    global DWORLD
    tc = TGEObject('SINGLEPLAYER_WORLDLIST')
    sr = int(tc.getSelectedId())
    if sr >= 0 and len(WORLDS):
        DWORLD = WORLDS[sr]
        TGEEval('MessageBoxYesNo("Delete World?", "Do you really want to delete %s?","Py::OnReallyDeleteSingleWorld();");' % WORLDS[sr])


def OnNewSingleWorld():
    name = TGEObject('SINGLEPLAYER_WORLDNAME').getValue()
    if not len(name):
        TGECall('MessageBoxOK', 'Invalid World Name!', 'Please enter SOME world name')
        return
    if name in WORLDS:
        TGECall('MessageBoxOK', 'World Exists', 'That world already exists')
        return
    if not name.replace(' ', '').isalnum():
        TGECall('MessageBoxOK', 'Invalid World Name!', 'Please only use letters and numbers in your world name.')
        return
    TGEEval('canvas.popDialog(NewSinglePlayerWorldDlg);')
    os.makedirs('./%s/data/worlds/singleplayer/%s' % (GAMEROOT, name))
    shutil.copyfile('./%s/data/worlds/multiplayer.baseline/world.db' % GAMEROOT, './%s/data/worlds/singleplayer/%s/world.db' % (GAMEROOT, name))
    EnumSinglePlayerWorlds()


def OnSPGlobalChatLogin():
    username = TGEGetGlobal('$pref::SPGlobalChatUserName')
    try:
        if len(username) < 4 or len(username) > 12:
            TGECall('MessageBoxOK', 'Invalid Username', 'Your username must be more than 4 characters and less than 13')
            return
    except:
        TGECall('MessageBoxOK', 'Invalid Username', 'Your username must be more than 4 characters and less than 13', 'SPGCUSERTEXT.makeFirstResponder(true);')
        return

    if not username.isalpha():
        TGECall('MessageBoxOK', 'Invalid Username', 'Your username must not include numbers or other punctuation.', 'SPGCUSERTEXT.makeFirstResponder(true);')
        return
    IRCConnect(username)
    TGEEval('Canvas.popDialog(SPGlobalChatGui);')


def Setup():
    SimMind.directConnect = ''
    EnumSinglePlayerWorlds()


def PyExec():
    Setup()
    TGEExport(OnNewSingleWorld, 'Py', 'OnNewSingleWorld', 'desc', 1, 1)
    TGEExport(OnLoadSingleWorld, 'Py', 'OnLoadSingleWorld', 'desc', 1, 1)
    TGEExport(OnReallyDeleteSingleWorld, 'Py', 'OnReallyDeleteSingleWorld', 'desc', 1, 1)
    TGEExport(OnDeleteSingleWorld, 'Py', 'OnDeleteSingleWorld', 'desc', 1, 1)
    TGEExport(OnSPGlobalChatLogin, 'Py', 'OnSPGlobalChatLogin', 'desc', 1, 1)