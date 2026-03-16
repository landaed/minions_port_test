# Embedded file name: mud\client\gui\registerDlg.pyo
from tgenative import *
from mud.tgepython.console import TGEExport
from mud.world.defines import *
from mud.gamesettings import *
from twisted.spread import pb
from twisted.internet import reactor
from twisted.cred.credentials import UsernamePassword
from md5 import md5
RegPerspective = None

def Result(results):
    global RegPerspective
    TGECall('CloseMessagePopup')
    RegPerspective = None
    msg = results[1]
    pw = results[2]
    regkey = results[3]
    if results[0]:
        title = 'Error!'
    else:
        title = 'Success!'
        publicName = TGEObject('REGISTERDLG_PUBLICNAME').getValue()
        TGEObject('MASTERLOGIN_PUBLICNAME').setValue(publicName)
        TGEObject('MASTERLOGIN_PASSWORD').setValue(pw)
        TGESetGlobal('$pref::PublicName', publicName)
        TGESetGlobal('$pref::MasterPassword', pw)
        TGESetGlobal('$pref::RegKey', regkey)
    TGECall('MessageBoxOK', title, msg)
    TGEEval('canvas.popDialog(registerDlg);')
    return


def Connected(perspective):
    global RegPerspective
    TGECall('CloseMessagePopup')
    RegPerspective = perspective
    regkey = TGEObject('REGISTERDLG_REGKEY').getValue()
    publicName = TGEObject('REGISTERDLG_PUBLICNAME').getValue()
    email = TGEObject('REGISTERDLG_EMAILADDRESS').getValue()
    TGECall('MessagePopup', 'Communicating with Master Server...', 'Submitting Registation Information...')
    d = RegPerspective.callRemote('RegistrationAvatar', 'submitKey', regkey, email, publicName)
    d.addCallbacks(Result, Failure)


def Failure(reason):
    global RegPerspective
    TGECall('CloseMessagePopup')
    TGECall('MessageBoxOK', 'Error!', reason.getErrorMessage())
    RegPerspective = None
    return


def OnRegister():
    regkey = TGEObject('REGISTERDLG_REGKEY').getValue()
    publicName = TGEObject('REGISTERDLG_PUBLICNAME').getValue()
    email = TGEObject('REGISTERDLG_EMAILADDRESS').getValue()
    verify = TGEObject('REGISTERDLG_VERIFYEMAILADDRESS').getValue()
    try:
        if not len(email) or not len(verify) or not len(publicName):
            return
    except:
        return

    if len(publicName) < 4:
        TGECall('MessageBoxOK', 'Invalid Entry', 'Your public name must be at least 4 characters.')
        return
    if not publicName.isalpha():
        TGECall('MessageBoxOK', 'Invalid Entry', 'Your public name must not have numbers or other punctuation.')
        return
    if email != verify:
        TGECall('MessageBoxOK', 'Error!', "Emails don't match.  Please carefully enter your email...")
        return
    TGECall('MessagePopup', 'Communicating with Master Server...', 'Please wait...')
    factory = pb.PBClientFactory()
    reactor.connectTCP(MASTERIP, MASTERPORT, factory, timeout=DEF_TIMEOUT)
    password = md5('Registration').digest()
    d = factory.login(UsernamePassword('Registration-Registration', password), pb.Root())
    d.addCallbacks(Connected, Failure)


def PyExec():
    TGEExport(OnRegister, 'Py', 'OnRegister', 'desc', 1, 1)