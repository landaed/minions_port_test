# Embedded file name: mud\client\gui\masterLoginDlg.pyo
from tgenative import *
from mud.tgepython.console import TGEExport
from mud.gamesettings import MASTERIP, MASTERPORT, DEF_TIMEOUT
from twisted.spread import pb
from twisted.internet import reactor
from twisted.cred.credentials import UsernamePassword
from md5 import md5

def Connected(perspective):
    TGECall('CloseMessagePopup')
    from masterGui import Setup
    Setup(perspective)


def Failure(reason):
    TGECall('CloseMessagePopup')
    TGEEval('Canvas.setContent(MainMenuGui);')
    TGECall('MessageBoxOK', 'Error!', reason.getErrorMessage())


def DoMasterLogin():
    from masterGui import MasterPerspective
    if MasterPerspective and not MasterPerspective.broker.disconnected:
        from masterGui import Setup
        Setup(MasterPerspective)
        return
    pname = TGEObject('MASTERLOGIN_PUBLICNAME').getValue()
    password = TGEObject('MASTERLOGIN_PASSWORD').getValue()
    TGESetGlobal('$pref::PublicName', pname)
    TGESetGlobal('$pref::MasterPassword', password)
    if not pname or not password:
        TGEEval('Canvas.setContent(MainMenuGui);')
        TGECall('MessageBoxOK', 'Error', 'Invalid username or password.')
        return
    TGEObject('MASTERLOGIN_PUBLICNAME').setText(pname)
    TGEObject('MASTERLOGIN_PASSWORD').setText(password)
    TGECall('MessagePopup', 'Logging into Master Server...', 'Please wait...')
    factory = pb.PBClientFactory()
    reactor.connectTCP(MASTERIP, MASTERPORT, factory, timeout=DEF_TIMEOUT)
    password = md5(password).digest()
    d = factory.login(UsernamePassword('%s-Player' % pname, password), pb.Root())
    d.addCallbacks(Connected, Failure)


def PyExec():
    pass