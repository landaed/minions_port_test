# Embedded file name: mud\client\gui\patcherGui.pyo
from tgenative import *
from mud.tgepython.console import TGEExport
from mud.world.defines import *
from mud.gamesettings import *
from mud.utils import *
import mud.manifests as mg
from twisted.internet import reactor
from twisted.web.client import HTTPDownloader, _parse
from twisted.spread import pb
from twisted.cred.credentials import UsernamePassword
import cPickle, zlib
import os, sys, shutil, traceback
import time
PATCHCODE_UPDATE = 0
PATCHCODE_MULTIPLAYER = 1
PATCHSTATUS_IDLE = 0
PATCHSTATUS_GETMANIFEST_FH = 1
PATCHSTATUS_GETMANIFEST = 2
PATCHSTATUS_DOWNLOADING = 3
PATCHSTATUS_APPLYING = 4
PATCHSTATUS_ROLLBACK = 5
from masterLoginDlg import DoMasterLogin
if PLATFORM == 'mac':
    CACHE_PATH = './cache/MinionsOfMirth.app/Contents'
    OLD_PATH = '../../..'
else:
    CACHE_PATH = './cache'
    OLD_PATH = '..'
if PLATFORM == 'mac':
    CACHE_SKIPLIST = ['patch.cpz',
     'patchfh.txt',
     'common/prefs.cs',
     'common/prefs.cs.dso',
     'minions.of.mirth/client/prefs.cs',
     'minions.of.mirth/client/prefs.cs.dso',
     'minions.of.mirth/client/config.cs',
     'minions.of.mirth/client/config.cs.dso',
     'minions.of.mirth/server/prefs.cs',
     'minions.of.mirth/server/prefs.cs.dso',
     'minions.of.mirth/server/banlist.cs',
     'minions.of.mirth/server/banlist.cs.dso']
else:
    CACHE_SKIPLIST = ['patch.cpz', 'patchfh.txt']
MAX_DOWNLOADS = 2
ABORT = False
doDisplayPatchInfo = False

def safe_filehash(fname):
    try:
        return mg.getFileHash(fname)
    except:
        pass


class FileHTTP(HTTPDownloader):

    def __init__(self, url, file, size, slot):
        self.keyName = file
        self.slot = slot
        self.progress = 0
        self.size = size
        filename = '%s/%s' % (CACHE_PATH, file)
        HTTPDownloader.__init__(self, url, filename, agent='MOMGameClient/%s' % GAMEVERSION)

    def stop(self):
        if self.protocol and self.protocol.transport:
            self.protocol.transport.loseConnection()

    def gotHeaders(self, headers):
        global ABORT
        if ABORT:
            self.stop()
        else:
            if not self.size:
                if headers.has_key('content-length'):
                    self.size = int(headers['content-length'][0])
                    print '%s size=%d' % (self.keyName, self.size)
            Patcher.instance.statusCallback(self)
        return HTTPDownloader.gotHeaders(self, headers)

    def pagePart(self, data):
        if ABORT:
            self.stop()
        else:
            self.progress += len(data)
            Patcher.instance.progressCallback(self)
        return HTTPDownloader.pagePart(self, data)


def downloadPage(url, file, size = 0, slot = 0):
    scheme, host, port, path = _parse(url)
    d = FileHTTP(url, file, size, slot)
    reactor.connectTCP(host, port, d, timeout=60)
    return d


class Patcher(object):
    instance = None

    def __new__(cl, *p, **k):
        if not Patcher.instance:
            Patcher.instance = object.__new__(cl, *p, **k)
        return Patcher.instance

    def __init__(self):
        self.tgeInitialized = False
        self.username = ''
        self.password = ''
        self.patchCode = PATCHCODE_UPDATE
        self.patchServerAddress = ''
        self.reset()

    def reset(self):
        global ABORT
        ABORT = False
        self.status = PATCHSTATUS_IDLE
        self.changes = 0
        self.targetfh = ''
        self.targetManifest = {}
        self.listFiles = []
        self.listFilesSize = 0
        self.restFiles = []
        self.patchDownloads = [ None for i in range(MAX_DOWNLOADS) ]
        self.fileProgress = [ 0.0 for i in range(MAX_DOWNLOADS) ]
        if self.tgeInitialized:
            self.tgeFirstText.setText('')
            self.tgeFirstText.visible = False
            self.tgeFirstProgress.setValue(0.0)
            self.tgeFirstProgress.visible = False
            self.tgeSecondText.setText('')
            self.tgeSecondText.visible = False
            self.tgeSecondProgress.setValue(0.0)
            self.tgeSecondProgress.visible = False
            self.tgeStatusText.setText('')
            self.tgeStatusText.visible = False
            self.tgeTotalText.setText('')
            self.tgeTotalText.visible = False
            self.tgeTotalProgress.setValue(0.0)
            self.tgeTotalProgress.visible = False
        return

    def initTGEObjects(self):
        self.tgeStatusText = TGEObject('PATCHER_STATUS_TEXT')
        self.tgeFirstText = TGEObject('PATCHER_FIRST_TEXT')
        self.tgeFirstProgress = TGEObject('PATCHER_FIRST_PROGRESS')
        self.tgeSecondText = TGEObject('PATCHER_SECOND_TEXT')
        self.tgeSecondProgress = TGEObject('PATCHER_SECOND_PROGRESS')
        self.tgeTotalText = TGEObject('PATCHER_TOTAL_TEXT')
        self.tgeTotalProgress = TGEObject('PATCHER_TOTAL_PROGRESS')
        self.tgeInitialized = True

    def setupPatchInfo(self, patchCode):
        self.patchCode = patchCode
        self.username = ''
        self.password = ''
        self.patchServerAddress = '%s/%s' % (PATCH_URL, PLATFORM)
        if PLATFORM == 'mac':
            self.patchServerAddress += '/MinionsOfMirth.app/Contents'

    def statusCallback(self, d):
        if self.status == PATCHSTATUS_GETMANIFEST or self.status == PATCHSTATUS_GETMANIFEST_FH:
            self.tgeFirstProgress.setValue(0.0)
        elif self.status == PATCHSTATUS_DOWNLOADING:
            text = 'downloading %s' % os.path.basename(d.keyName)
            if d.slot:
                self.tgeSecondProgress.setValue(0.0)
                self.tgeSecondText.setText(text)
            else:
                self.tgeFirstProgress.setValue(0.0)
                self.tgeFirstText.setText(text)
            totrel = 1.0 - len(self.listFiles) / float(self.listFilesSize)
            self.tgeTotalProgress.setValue(0.05 + 0.95 * totrel)

    def progressCallback(self, d):
        if d.size:
            rel = d.progress / float(d.size)
        else:
            rel = d.progress / 1024.0
            if rel > 1.0:
                rel = 0.0
        if self.status == PATCHSTATUS_GETMANIFEST or self.status == PATCHSTATUS_GETMANIFEST_FH:
            self.tgeFirstProgress.setValue(rel)
            self.tgeTotalProgress.setValue(0.05 * rel)
        elif self.status == PATCHSTATUS_DOWNLOADING:
            if d.slot:
                self.tgeSecondProgress.setValue(rel)
            else:
                self.tgeFirstProgress.setValue(rel)

    def finalize(self):
        global HAVE_PATCHED
        self.tgeFirstText.visible = False
        self.tgeFirstProgress.visible = False
        self.tgeSecondText.visible = False
        self.tgeSecondProgress.visible = False
        self.tgeStatusText.setText('patch downloading')
        self.tgeTotalText.setText('completed downloading')
        self.tgeTotalProgress.setValue(1.0)
        print 'total patching changes: %d' % self.changes
        if not self.changes:
            return self.donePatching()
        HAVE_PATCHED = True
        self.status = PATCHSTATUS_IDLE
        if int(TGEGetGlobal('$pref::Video::fullScreen')):
            TGECall('toggleFullScreen')
        self.tgeStatusText.setText('restart is needed!')
        TGECall('MessageBoxOK', 'Success!', 'Patch for "%s" has been downloaded, hit ok to apply.\nIt will start automatically, do not relaunch the game.' % GAMENAME, 'Py::OnPatchRestart();')

    def errDownload(self, reason, d):
        global ABORT
        ABORT = True
        e = 'An error occurred while downloading file "%s":\n%s' % (d.keyName, reason.getErrorMessage())
        print e
        print traceback.print_stack()
        TGECall('MessageBoxOK', 'Patcher Error', e, 'Py::OnPatchError();')

    def doneDownload(self, result, d):
        global ABORT
        if ABORT:
            return
        else:
            file = d.keyName
            self.tgeFirstText.setText('verifying "%s"' % os.path.basename(file))
            cachefname = '%s/%s' % (CACHE_PATH, file)
            hash = safe_filehash(cachefname)
            fv, fh = self.targetManifest[file]
            if hash == fh:
                self.patchDownloads[d.slot] = None
            else:
                try:
                    os.remove(cachefname)
                except:
                    ABORT = True
                    e = 'Error removing faulty patch download "%s":\n%s' % (cachefname, traceback.format_exc())
                    print e
                    TGECall('MessageBoxOK', 'Patcher Error', e, 'Py::OnPatchError();')
                    return

                ABORT = True
                e = 'An error occurred while downloading file "%s".\nTry again later.' % file
                print e
                TGECall('MessageBoxOK', 'Patcher Error', e, 'Py::OnPatchError();')
            return

    def downloadFile(self, file, size, slot):
        global ABORT
        if ABORT:
            return
        text = 'loading %s' % os.path.basename(file)
        if slot:
            self.tgeSecondText.setText(text)
            self.tgeSecondProgress.setValue(0.0)
        else:
            self.tgeFirstText.setText(text)
            self.tgeFirstProgress.setValue(0.0)
        fv, fh = self.targetManifest[file]
        oldfname = './%s' % file
        cachefname = '%s/%s' % (CACHE_PATH, file)
        if os.path.exists(cachefname):
            hash = safe_filehash(cachefname)
            if fv[1] != 2 and hash == fh:
                if os.path.exists(oldfname):
                    hash = safe_filehash(oldfname)
                    if hash == fh:
                        if fv[1] != 0 and os.path.exists(cachefname):
                            try:
                                make_writable(cachefname)
                                os.remove(cachefname)
                            except:
                                pass

                        return
                self.changes += 1
                return
            try:
                make_writable(cachefname)
                os.remove(cachefname)
            except:
                ABORT = True
                e = 'Error removing faulty patch download "%s":\n%s' % (cachefname, traceback.format_exc())
                print e
                TGECall('MessageBoxOK', 'Patcher Error', e, 'Py::OnPatchError();')
                return

        if os.path.exists(oldfname):
            hash = safe_filehash(oldfname)
            if hash == fh:
                if fv[1] == 0:
                    try:
                        head, tail = os.path.split(cachefname)
                        if_makedirs(head)
                        shutil.copy2(oldfname, cachefname)
                    except:
                        ABORT = True
                        e = 'Failed to move file to cache:\n%s' % traceback.format_exc()
                        print e
                        TGECall('MessageBoxOK', 'Patcher Error', e, 'Py::OnPatchError();')

                return
            print 'diff %s' % file
            if fv[1] == 2:
                self.changes += 1
                return
        try:
            head, tail = os.path.split(cachefname)
            if_makedirs(head)
        except:
            ABORT = True
            e = 'Could not create required directories for "%s":\n%s' % (cachefname, traceback.format_exc())
            print e
            TGECall('MessageBoxOK', 'Patcher Error', e, 'Py::OnPatchError();')
            return

        self.changes += 1
        username = self.username
        password = self.password
        url = '%s/%s' % (self.patchServerAddress, file.replace(' ', '%20'))
        d = downloadPage(url, file, size, slot)
        d.deferred.addCallback(self.doneDownload, d)
        d.deferred.addErrback(self.errDownload, d)
        return d

    def tickWalking(self):
        if ABORT:
            return
        else:
            if not len(self.listFiles):
                if self.patchDownloads.count(None) == MAX_DOWNLOADS:
                    self.finalize()
                    return
            for k in range(0, 16):
                have = None
                for i in range(MAX_DOWNLOADS):
                    if not self.patchDownloads[i]:
                        if not len(self.listFiles):
                            break
                        name = self.listFiles[0]
                        d = self.downloadFile(name, 0, i)
                        if d:
                            self.patchDownloads[i] = d
                            have = True
                        del self.listFiles[0]

                if ABORT:
                    return
                if have or not len(self.listFiles):
                    break

            totrel = 1.0 - len(self.listFiles) / float(self.listFilesSize)
            self.tgeTotalProgress.setValue(0.05 + 0.95 * totrel)
            reactor.callLater(0.02, self.tickWalking)
            return

    def startWalking(self):
        if ABORT:
            return
        self.status = PATCHSTATUS_DOWNLOADING
        self.tgeFirstText.setText('')
        self.tgeFirstText.visible = True
        self.tgeFirstProgress.setValue(0.0)
        self.tgeFirstProgress.visible = True
        self.tgeSecondText.setText('')
        self.tgeSecondText.visible = True
        self.tgeSecondProgress.setValue(0.0)
        self.tgeSecondProgress.visible = True
        self.tgeStatusText.setText('processing patch files...')
        self.tgeTotalText.setText('walking patch files')
        self.tgeTotalProgress.setValue(0.05)
        self.listFiles = self.targetManifest.keys()
        self.listFilesSize = len(self.listFiles)
        CleanCache(self.listFiles)
        reactor.callLater(0.02, self.tickWalking)

    def errRemoteManifest(self, reason):
        global ABORT
        ABORT = True
        e = 'Unable to get remote manifest:\n%s' % reason.getErrorMessage()
        print e
        TGECall('MessageBoxOK', 'Patcher Error', e, 'Py::OnPatchError();')

    def loadTargetManifest(self, fname):
        f = open(fname, 'rb')
        zd = f.read()
        f.close()
        sd = zlib.decompress(zd)
        self.targetManifest = cPickle.loads(sd)

    def donePatching(self):
        global HAVE_PATCHED
        HAVE_PATCHED = True
        self.status = PATCHSTATUS_IDLE
        CleanCache()
        if self.patchCode == PATCHCODE_MULTIPLAYER:
            DoMasterLogin()
        else:
            TGEEval('canvas.setContent(MainMenuGui);')
            DisplayPatchInfo()
            TGECall('MessageBoxOK', 'Live Update', 'Your game is up to date.')

    def doneRemoteManifest(self, result):
        global ABORT
        if ABORT:
            return
        else:
            oldhash = safe_filehash('./patch.cpz')
            if self.status == PATCHSTATUS_GETMANIFEST_FH:
                try:
                    f = open('%s/patchfh.txt' % CACHE_PATH, 'rb')
                    hash = str(f.read())
                    f.close()
                    if oldhash is not None and hash == oldhash:
                        return self.donePatching()
                    self.status = PATCHSTATUS_GETMANIFEST
                    url = '%s/patch.cpz' % self.patchServerAddress
                    d = downloadPage(url, 'patch.cpz')
                    d.deferred.addCallbacks(self.doneRemoteManifest, self.errRemoteManifest)
                except:
                    ABORT = True
                    e = 'Error while analysing remote manifest:\n%s' % traceback.format_exc()
                    print e
                    TGECall('MessageBoxOK', 'Patcher Error', e, 'Py::OnPatchError();')
                    return

                return
            hash = safe_filehash('%s/patch.cpz' % CACHE_PATH)
            if hash is not None and hash == oldhash:
                return self.donePatching()
            try:
                self.loadTargetManifest('%s/patch.cpz' % CACHE_PATH)
            except:
                ABORT = True
                e = 'Error while analysing remote manifest:\n%s' % traceback.format_exc()
                print e
                TGECall('MessageBoxOK', 'Patcher Error', e, 'Py::OnPatchError();')
                return

            self.startWalking()
            return

    def getRemoteManifest(self):
        if ABORT:
            return
        self.status = PATCHSTATUS_GETMANIFEST_FH
        self.tgeFirstText.setText('downloading...')
        self.tgeFirstText.visible = True
        self.tgeFirstProgress.setValue(0.0)
        self.tgeFirstProgress.visible = True
        self.tgeStatusText.setText('please wait...')
        self.tgeStatusText.visible = True
        self.tgeTotalText.setText('downloading patch info')
        self.tgeTotalText.visible = True
        self.tgeTotalProgress.setValue(0.0)
        self.tgeTotalProgress.visible = True
        url = '%s/patchfh.txt' % self.patchServerAddress
        d = downloadPage(url, 'patchfh.txt')
        d.deferred.addCallbacks(self.doneRemoteManifest, self.errRemoteManifest)

    def onApplyRestart(self):
        try:
            path = os.path.normpath('%s/%s' % (os.getcwd(), OLD_PATH))
            if PLATFORM == 'win':
                name = 'MinionsOfMirth.exe'
            else:
                name = 'MinionsOfMirth.app/Contents/MacOS/MinionsOfMirth'
            real_spawn(path, name, '-pid=%d' % os.getpid())
        except:
            traceback.print_exc()

        self.onPatchQuit()

    def cleanupRestore(self):
        if_rmtree('%s/restore' % OLD_PATH)

    def applyingFile(self, file):
        oldfname = os.path.normpath('%s/%s' % (OLD_PATH, file))
        if os.path.exists(oldfname):
            make_writable(oldfname)
            rfn = os.path.normpath('%s/restore/%s' % (OLD_PATH, file)).replace(os.sep, '/')
            if os.path.exists(rfn):
                make_writable(rfn)
                os.remove(rfn)
            head, tail = os.path.split(rfn)
            if_makedirs(head)
            os.rename(oldfname, rfn)
            self.restFiles.append(file)
        if os.path.exists(file):
            shutil.copy2(file, oldfname)
            make_writable(oldfname)

    def tickApplying(self):
        if self.status == PATCHSTATUS_APPLYING:
            if not len(self.listFiles):
                try:
                    self.applyingFile('patch.cpz')
                    self.applyingFile('patchfh.txt')
                except:
                    traceback.print_exc()

                self.cleanupRestore()
                TGECall('MessageBoxOK', 'Success!', '"%s" is completely patched!\nIt will start automatically, do not relaunch the game.' % GAMENAME, 'Py::OnApplyRestart();')
                return
            for k in xrange(0, 16):
                if not len(self.listFiles):
                    break
                try:
                    file = self.listFiles[0]
                    oldfname = os.path.normpath('%s/%s' % (OLD_PATH, file))
                    fv, fh = self.targetManifest[file]
                    if PLATFORM == 'mac':
                        if file.startswith('MinionsOfMirth.app/Contents/'):
                            file = file[len('MinionsOfMirth.app/Contents/'):]
                    docopy = 1
                    if os.path.exists(oldfname):
                        make_writable(oldfname)
                        hash = safe_filehash(oldfname)
                        if hash == fh:
                            docopy = 0
                        else:
                            rfn = os.path.normpath('%s/restore/%s' % (OLD_PATH, file)).replace(os.sep, '/')
                            if os.path.exists(rfn):
                                make_writable(rfn)
                                os.remove(rfn)
                            head, tail = os.path.split(rfn)
                            if_makedirs(head)
                            os.rename(oldfname, rfn)
                            self.restFiles.append(file)
                    if docopy and fv[1] != 2:
                        head, tail = os.path.split(oldfname)
                        if_makedirs(head)
                        shutil.copy2(file, oldfname)
                        make_writable(oldfname)
                    del self.listFiles[0]
                except:
                    e = 'Failed to apply patch:\n%s' % traceback.format_exc()
                    print e
                    self.status = PATCHSTATUS_ROLLBACK
                    self.tgeTotalText.setText('rollback patch')
                    break

        else:
            if not len(self.restFiles):
                self.cleanupRestore()
                self.onPatchQuit()
                return
            for k in range(0, 16):
                if not len(self.restFiles):
                    break
                try:
                    file = self.restFiles[0]
                    oldfname = os.path.normpath('%s/%s' % (OLD_PATH, file))
                    if os.path.exists(oldfname):
                        make_writable(oldfname)
                        os.remove(oldfname)
                    rfn = os.path.normpath('%s/restore/%s' % (OLD_PATH, file))
                    os.rename(rfn, oldfname)
                    del self.restFiles[0]
                    self.listFiles.append('')
                except:
                    e = 'Failed to rollback patch:\n%s' % traceback.format_exc()
                    print e
                    TGECall('MessageBoxOK', 'Patcher Error', e, 'Py::OnPatchQuit();')
                    return

        totrel = 1.0 - len(self.listFiles) / float(self.listFilesSize)
        self.tgeTotalProgress.setValue(totrel)
        reactor.callLater(0.02, self.tickApplying)

    def applyPatch(self):
        self.reset()
        self.status = PATCHSTATUS_APPLYING
        TGEEval('canvas.setContent(PatcherGui);')
        self.tgeStatusText.setText('please wait...')
        self.tgeStatusText.visible = True
        self.tgeTotalText.setText('applying patch')
        self.tgeTotalText.visible = True
        self.tgeTotalProgress.setValue(0.0)
        self.tgeTotalProgress.visible = True
        if_makedirs('%s/restore' % OLD_PATH)
        make_writable('%s/restore' % OLD_PATH)
        try:
            fname = './patch.cpz'
            if PLATFORM == 'mac' and not os.path.exists(fname):
                fname = '%s/cache/patch.cpz' % OLD_PATH
            self.loadTargetManifest(fname)
        except:
            ABORT = True
            e = 'Error while analysing remote manifest:\n%s' % traceback.format_exc()
            print e
            TGECall('MessageBoxOK', 'Patcher Error', e, 'Py::OnPatchQuit();')
            return

        self.listFiles = self.targetManifest.keys()
        self.listFilesSize = len(self.listFiles)
        reactor.callLater(0.02, self.tickApplying)

    def patch(self):
        global ABORT
        self.reset()
        TGEEval('canvas.setContent(PatcherGui);')
        try:
            try:
                if_makedirs(CACHE_PATH)
            except:
                traceback.print_exc()
                s = 'Could not create cache directory. Missing permissions?'
                TGECall('MessageBoxOK', 'Patcher Error', e, 'Py::OnPatchError();')
                return

            self.getRemoteManifest()
        except:
            ABORT = True
            e = 'There was an error during the patching process:\n%s' % traceback.format_exc()
            print e
            TGECall('MessageBoxOK', 'Patcher Error', e, 'Py::OnPatchError();')

    def patchInfoErrback(self, reason):
        TGECall('CloseMessagePopup')
        e = 'An error occurred while retrieving patch server information:\n%s' % reason.getErrorMessage()
        print e
        TGECall('MessageBoxOK', 'Patcher Error', e)

    def patchServerResults(self, args, perspective):
        perspective.broker.transport.loseConnection()
        TGECall('CloseMessagePopup')
        if args[0]:
            e = 'An error occurred while retrieving patch server information:\n%s' % args[1]
            print e
            TGECall('MessageBoxOK', 'Patcher Error', e)
            return
        self.patchServerAddress, self.username, self.password = args[1]
        if len(args) > 2 and args[2]:
            self.patchServerAddress, self.cUsername, self.cPassword = args[2]
        else:
            self.patchServerAddress, self.cUsername, self.cPassword = args[1]
        self.patch()

    def onPatchRestart(self):
        try:
            if not is_frozen():
                raise Exception, 'we do not patch source'
            else:
                path = os.path.normpath('%s/%s' % (os.getcwd(), CACHE_PATH))
                if PLATFORM == 'win':
                    name = 'MinionsOfMirth.exe'
                else:
                    name = 'MacOS/MinionsOfMirth'
                real_spawn(path, name, '-patch -pid=%d' % os.getpid(), True)
            self.onPatchQuit()
        except:
            e = 'An error occurred while trying to patch'
            print e
            traceback.print_exc()
            TGECall('MessageBoxOK', 'Patcher Error', e, 'Py::OnPatchQuit();')

    def onPatchError(self):
        global ABORT
        ABORT = True
        TGEEval('canvas.setContent(MainMenuGui);')

    def onPatchCancel(self):
        global ABORT
        if self.status == PATCHSTATUS_APPLYING:
            self.status = PATCHSTATUS_ROLLBACK
            self.tgeTotalText.setText('rollback patch')
            return
        if self.status == PATCHSTATUS_ROLLBACK:
            return
        ABORT = True
        TGEEval('canvas.setContent(MainMenuGui);')

    def onPatchQuit(self):
        global ABORT
        ABORT = True
        TGEEval('quit();')


Patcher()

def CleanCache(listFiles = None):
    try:
        cppos = len(CACHE_PATH) - 1
        for dirpath, dirnames, filenames in os.walk(CACHE_PATH):
            for file in filenames:
                name = os.path.normpath(os.path.join(dirpath, file)).replace(os.sep, '/')
                relname = name[cppos:]
                if relname in CACHE_SKIPLIST or relname[:5] == 'logs/':
                    continue
                if listFiles and relname in listFiles:
                    continue
                print 'remove %s' % name
                os.remove(name)

    except:
        pass


def DisplayPatchInfo():
    global doDisplayPatchInfo
    if IN_PATCHING:
        time.sleep(10)
        Patcher.instance.applyPatch()
        return
    if HAVE_PATCHED:
        CleanCache()
    if doDisplayPatchInfo:
        doDisplayPatchInfo = False
        TGEEval('canvas.pushDialog(EULAWnd);')
        try:
            lines = []
            f = file('./patchlist.txt', 'r')
            i = 0
            for l in f:
                text = l.rstrip()
                text = text.replace('\x07', '\\a')
                text = text.replace('"', '\\"')
                lines.append(text)
                if i > 30:
                    lines.append('\n... for more see patchlist.txt')
                    break
                i += 1

            f.close()
            text = '<shadowcolor:000000><shadow:1:1><font:Arial Bold:14>' + '\\n'.join(lines)
            TGEEval('patchinfownd_text.setText("%s");' % text)
            TGEEval('canvas.pushDialog(PatchInfoWnd);')
        except:
            pass


def OnPatch():
    Patcher.instance.setupPatchInfo(PATCHCODE_UPDATE)
    Patcher.instance.patch()


def OnMasterLogin():
    if is_frozen() and not HAVE_PATCHED:
        pname = TGEObject('MASTERLOGIN_PUBLICNAME').getValue()
        password = TGEObject('MASTERLOGIN_PASSWORD').getValue()
        if not len(pname) or not len(password):
            TGEEval('Canvas.setContent(MainMenuGui);')
            TGECall('MessageBoxOK', 'Error', 'Invalid username or password.')
            return
        TGESetGlobal('$pref::PublicName', pname)
        TGESetGlobal('$pref::MasterPassword', password)
        Patcher.instance.setupPatchInfo(PATCHCODE_MULTIPLAYER)
        Patcher.instance.patch()
    else:
        DoMasterLogin()


def OnMultiplayer():
    TGEEval('canvas.pushDialog("MasterLoginDlg");')


def PyExec():
    PATCHER = Patcher.instance
    PATCHER.initTGEObjects()
    TGEExport(PATCHER.onPatchRestart, 'Py', 'OnPatchRestart', 'desc', 1, 1)
    TGEExport(PATCHER.onPatchError, 'Py', 'OnPatchError', 'desc', 1, 1)
    TGEExport(PATCHER.onPatchQuit, 'Py', 'OnPatchQuit', 'desc', 1, 1)
    TGEExport(PATCHER.onPatchCancel, 'Py', 'OnPatchCancel', 'desc', 1, 1)
    TGEExport(PATCHER.onApplyRestart, 'Py', 'OnApplyRestart', 'desc', 1, 1)
    TGEExport(DisplayPatchInfo, 'Py', 'DisplayPatchInfo', 'desc', 1, 1)
    TGEExport(OnPatch, 'Py', 'OnPatch', 'desc', 1, 1)
    TGEExport(OnMasterLogin, 'Py', 'OnMasterLogin', 'desc', 1, 1)
    TGEExport(OnMultiplayer, 'Py', 'OnMultiplayer', 'desc', 1, 1)
    pname = TGEGetGlobal('$pref::PublicName')
    password = TGEGetGlobal('$pref::MasterPassword')
    if not pname or not password:
        pname = ''
        password = ''
    TGEObject('MASTERLOGIN_PUBLICNAME').setText(pname)
    TGEObject('MASTERLOGIN_PASSWORD').setText(password)