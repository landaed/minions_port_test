# Embedded file name: mud\client\gui\lostPasswordDlg.pyo
from tgenative import *
from mud.tgepython.console import TGEExport
from mud.gamesettings import MASTERIP, MASTERPORT, DEF_TIMEOUT
from twisted.spread import pb
from twisted.internet import reactor
from twisted.cred.credentials import UsernamePassword
from md5 import md5
PUBLICNAME = ''
EMAILADDRESS = ''
RegPerspective = None

def Result(results):
    global RegPerspective
    RegPerspective = None
    TGECall('CloseMessagePopup')
    msg = results[1]
    if results[0]:
        title = 'Error!'
    else:
        title = 'Success!'
        TGEEval('canvas.popDialog(LostPasswordDlg);')
    TGECall('MessageBoxOK', title, msg)
    return


def Connected(perspective):
    global EMAILADDRESS
    global PUBLICNAME
    global RegPerspective
    RegPerspective = perspective
    TGECall('CloseMessagePopup')
    TGECall('MessagePopup', 'Communicating with Master Server...', 'Requesting password...')
    d = perspective.callRemote('RegistrationAvatar', 'requestPassword', PUBLICNAME, EMAILADDRESS)
    d.addCallbacks(Result, Failure)


def Failure(reason):
    TGECall('CloseMessagePopup')
    TGECall('MessageBoxOK', 'Error!', reason.value)


def OnRequestLostPassword():
    global PUBLICNAME
    global EMAILADDRESS
    pname = TGEObject('LOSTPASSWORD_PUBLICNAME').getValue()
    email = TGEObject('LOSTPASSWORD_EMAIL').getValue()
    if not pname:
        TGECall('MessageBoxOK', 'Lost Password', 'Invalid Public Name')
        return
    if '@' not in email or '.' not in email:
        TGECall('MessageBoxOK', 'Lost Password', 'Invalid email address')
        return
    PUBLICNAME, EMAILADDRESS = pname, email
    TGECall('MessagePopup', 'Contacting Master Server...', 'Please wait...')
    factory = pb.PBClientFactory()
    reactor.connectTCP(MASTERIP, MASTERPORT, factory, timeout=DEF_TIMEOUT)
    password = md5('Registration').digest()
    d = factory.login(UsernamePassword('Registration-Registration', password), pb.Root())
    d.addCallbacks(Connected, Failure)


def PyExec():
    TGEExport(OnRequestLostPassword, 'Py', 'OnRequestLostPassword', 'desc', 1, 1)