# Embedded file name: mud\client\gui\worldLoginDlg.pyo
from tgenative import *
from mud.tgepython.console import TGEExport
from mud.client.playermind import PlayerMind
from twisted.spread import pb
from twisted.internet import reactor
from twisted.cred.credentials import UsernamePassword
from md5 import md5
NewPlayerPerspective = None
WORLDINFO = None

def SetWorldInfo(wi):
    global WORLDINFO
    WORLDINFO = wi


def PlayerConnected(perspective, mind):
    TGECall('CloseMessagePopup')
    mind.setPerspective(perspective)
    from worldGui import Setup
    Setup(perspective)
    pw = TGEObject('WORLDLOGIN_PASSWORD').getValue()
    TGESetGlobal('$pref::WorldPassword', pw)


def OnWorldLoginCancel():
    global NewPlayerPerspective
    if NewPlayerPerspective:
        NewPlayerPerspective.broker.transport.loseConnection()
    NewPlayerPerspective = None
    from masterLoginDlg import DoMasterLogin
    DoMasterLogin()
    return


def OnWorldLogin(args):
    guardian = int(args[1]) == 1
    immortal = int(args[1]) == 2
    avatar = 'Player'
    if immortal:
        avatar = 'Immortal'
    elif guardian:
        avatar = 'Guardian'
    worldpassword = TGEObject('WORLDLOGIN_PASSWORD').getValue()
    if len(worldpassword) < 6:
        TGECall('MessageBoxOK', 'Error!', 'World passwords are at least 6 characters long.')
    else:
        TGECall('MessagePopup', 'Logging into world...', 'Please wait...')
        factory = pb.PBClientFactory()
        reactor.connectTCP(WORLDINFO.worldIP, WORLDINFO.worldPort, factory, timeout=DEF_TIMEOUT)
        mind = PlayerMind()
        password = md5(worldpassword).digest()
        factory.login(UsernamePassword('%s-%s' % (TGEGetGlobal('$pref::PublicName'), avatar), password), mind).addCallbacks(PlayerConnected, Failure, (mind,))


def GotNewPlayerResult(result):
    global NewPlayerPerspective
    NewPlayerPerspective = None
    TGECall('CloseMessagePopup')
    code = result[0]
    msg = result[1]
    pw = result[2]
    if code:
        title = 'Error!'
    else:
        title = 'Success!'
        TGESetGlobal('$pref::WorldPassword', pw)
        TGEObject('WORLDLOGIN_PASSWORD').setValue(pw)
        TGEEval('Canvas.pushDialog(WorldLoginDlg);')
    TGECall('MessageBoxOK', title, msg)
    return


def OnWorldRegister():
    fname = TGEObject('WORLDREGISTER_FANTASYNAME').getValue()
    pw = TGEObject('WORLDREGISTER_PLAYERPASSWORD').getValue()
    if len(fname) < 4:
        TGECall('MessageBoxOK', 'Invalid Entry', 'Your avatar name must be at least 4 characters.')
        return
    if not fname.isalpha():
        TGECall('MessageBoxOK', 'Invalid Entry', 'Your avatar name must not have numbers or other punctuation.')
        return
    TGESetGlobal('$pref::FantasyName', fname)
    pname = TGEGetGlobal('$pref::PublicName')
    TGECall('MessagePopup', 'Creating Account...', 'Please wait...')
    NewPlayerPerspective.callRemote('NewPlayerAvatar', 'newPlayer', pname, fname, pw).addCallbacks(GotNewPlayerResult, Failure)


def GotQueryPlayerResult(result):
    global NewPlayerPerspective
    TGECall('CloseMessagePopup')
    if not result:
        TGEEval('Canvas.pushDialog(WorldRegisterDlg);')
    else:
        NewPlayerPerspective = None
        TGEEval('Canvas.pushDialog(WorldLoginDlg);')
    return


def Failure(reason):
    global NewPlayerPerspective
    TGECall('CloseMessagePopup')
    TGECall('MessageBoxOK', 'Error!', reason.getErrorMessage())
    if NewPlayerPerspective:
        NewPlayerPerspective.broker.transport.loseConnection()
    NewPlayerPerspective = None
    from masterLoginDlg import DoMasterLogin
    DoMasterLogin()
    return


def Setup(npperspective, winfo):
    global WORLDINFO
    global NewPlayerPerspective
    if winfo.hasPlayerPassword:
        TGEObject('WORLDREGISTER_PASSWORDTEXT').visible = True
        TGEObject('WORLDREGISTER_PLAYERPASSWORD').visible = True
    else:
        TGEObject('WORLDREGISTER_PASSWORDTEXT').visible = False
        TGEObject('WORLDREGISTER_PLAYERPASSWORD').visible = False
    WORLDINFO = winfo
    NewPlayerPerspective = npperspective
    NewPlayerPerspective.callRemote('NewPlayerAvatar', 'queryPlayer', TGEGetGlobal('$pref::PublicName')).addCallbacks(GotQueryPlayerResult, Failure)


def PyExec():
    TGEExport(OnWorldRegister, 'Py', 'OnWorldRegister', 'desc', 1, 1)
    TGEExport(OnWorldLogin, 'Py', 'OnWorldLogin', 'desc', 2, 2)
    TGEExport(OnWorldLoginCancel, 'Py', 'OnWorldLoginCancel', 'desc', 1, 1)