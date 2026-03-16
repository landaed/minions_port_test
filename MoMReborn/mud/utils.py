# Embedded file name: mud\utils.pyo
import os, sys, shutil, stat
import traceback
from twisted.python import log
from datetime import datetime
import base64, cPickle
OLDSTDOUT = sys.stdout
PLATFORM = None
if sys.platform[:3] == 'win':
    PLATFORM = 'win'
elif sys.platform[:6] == 'darwin':
    PLATFORM = 'mac'

def is_frozen():
    return hasattr(sys, 'frozen')


def safe_encode(x):
    if x:
        return base64.encodestring(cPickle.dumps(x, 2))


def safe_decode(x):
    if x:
        return cPickle.loads(base64.decodestring(x))


def getSQLiteURL(path):
    off = os.getcwd()
    return '%s/%s' % (off, path)


def main_args():
    try:
        f = open('./args.txt', 'r')
        text = f.read()
        f.close()
        args = text.strip().split()
        for a in args:
            print 'adding arg %s' % a
            sys.argv.append(a)

        if '-rmargs' in args:
            os.remove('./args.txt')
    except:
        pass


def is_patching():
    if '-patch' in sys.argv:
        return True
    cwd = os.getcwd()
    if PLATFORM == 'mac':
        ok = cwd.endswith('cache/MinionsOfMirth.app/Contents')
    else:
        ok = cwd.endswith('cache')
    return ok


def chdir_main():
    if is_frozen():
        maindir = os.path.dirname(sys.executable)
        os.chdir(maindir)
        if PLATFORM == 'mac':
            os.chdir('..')
        maindir = os.getcwd()
        print 'running from %s' % maindir


def get_lock():
    lock = None
    try:
        if PLATFORM == 'win':
            import win32event, win32api, winerror
            lockname = 'Global\\mom_client_%s' % base64.encodestring(sys.executable).strip()
            lock = win32event.CreateMutex(None, True, lockname)
            if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
                return
        else:
            if is_patching():
                lockname = '../../../logs/mac_lock.txt'
            else:
                lockname = './logs/mac_lock.txt'
            if os.path.exists(lockname):
                os.remove(lockname)
            lock = os.open(lockname, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            if lock:
                os.chmod(lockname, stat.S_IRWXO | stat.S_IRWXG | stat.S_IRWXU)
    except:
        pass

    return lock


def free_lock(lock):
    if not lock:
        return
    try:
        if PLATFORM == 'win':
            import win32event
            win32event.ReleaseMutex(lock)
        else:
            if is_patching():
                lockname = '../../../logs/mac_lock.txt'
            else:
                lockname = './logs/mac_lock.txt'
            os.close(lock)
            os.unlink(lockname)
    except:
        pass


def if_rmtree(x):
    if os.path.exists(x):
        shutil.rmtree(x)


def if_makedirs(x):
    if not os.path.exists(x):
        os.makedirs(x)


def ptimediff(x):
    import time
    t = time.gmtime(x)
    s = ''
    if t.tm_yday > 1:
        s += '%d days, ' % (t.tm_yday - 1)
    if t.tm_hour:
        s += '%d hours, ' % t.tm_hour
    if t.tm_min:
        s += '%d mins, ' % t.tm_min
    return '%s%d secs' % (s, t.tm_sec)


if PLATFORM == 'win':

    def setup_cpu(i):
        import win32process
        h = win32process.GetCurrentProcess()
        processMask, systemMask = win32process.GetProcessAffinityMask(h)
        if not systemMask:
            return
        i += 1
        if i < 0:
            i = -i
        while True:
            i = i % 4
            mask = 3 << i * 2
            if systemMask & mask:
                mask &= systemMask
                break
            else:
                i += 1

        print 'setup_cpu %d %08x %08x/%08x' % (i,
         mask,
         processMask,
         systemMask)
        win32process.SetProcessAffinityMask(h, mask)


    def set_priority(ap):
        import win32process
        p = win32process.NORMAL_PRIORITY_CLASS
        if ap == 1:
            p = win32process.ABOVE_NORMAL_PRIORITY_CLASS
        elif ap == -1:
            p = win32process.BELOW_NORMAL_PRIORITY_CLASS
        elif ap > 1:
            p = win32process.HIGH_PRIORITY_CLASS
        elif ap < -1:
            p = win32process.IDLE_PRIORITY_CLASS
        h = win32process.GetCurrentProcess()
        win32process.SetPriorityClass(h, p)


    def set_console_title(title):
        import win32console
        h = win32console.GetConsoleWindow()
        if h:
            win32console.SetConsoleTitle(title)


def kill_process(pid):
    try:
        if PLATFORM == 'win':
            import win32api, win32process, win32con
            try:
                h = win32api.OpenProcess(win32con.PROCESS_TERMINATE, False, pid)
                if h:
                    win32process.TerminateProcess(h, -1)
                    win32api.CloseHandle(h)
            except win32api.error as e:
                if e.funcname == 'OpenProcess' and e.winerror == 87:
                    pass
                else:
                    raise

        else:
            import signal
            os.kill(pid, signal.SIGKILL)
    except:
        traceback.print_exc()


def make_writable(name):
    name = name.replace(os.sep, '/')
    a = name.split('/')
    fn = None
    for n in a:
        if fn is None:
            fn = n
        else:
            fn = fn + '/' + n
        try:
            if PLATFORM == 'win':
                os.chmod(fn, stat.S_IREAD | stat.S_IWRITE)
            else:
                os.chmod(fn, stat.S_IRWXO | stat.S_IRWXG | stat.S_IRWXU)
        except:
            traceback.print_exc()

    return


def give_perm(name):
    if PLATFORM == 'mac':
        try:
            os.chmod(name, stat.S_IRWXO | stat.S_IRWXG | stat.S_IRWXU)
        except:
            pass


class TwistedLogFile:

    def __init__(self, fname, withStdout):
        self.name = fname
        self.f = open(fname, 'w')
        self.withStdout = withStdout
        if withStdout:
            sys.stdout = self
            sys.stderr = self
        if log.defaultObserver:
            log.defaultObserver.stop()
            log.defaultObserver = None
        log.addObserver(self.emit)
        return

    def emit(self, eventDict):
        text = log.textFromEventDict(eventDict)
        if text is None:
            return
        else:
            timestr = datetime.fromtimestamp(eventDict['time']).strftime('%Y-%m-%d %H:%M:%S')
            msg = '%s [%s] %s\n' % (timestr, eventDict['system'], text)
            self.write(msg)
            self.flush()
            return

    def write(self, bytes):
        self.f.write(bytes)
        if self.withStdout:
            OLDSTDOUT.write(bytes)

    def flush(self):
        if self.f:
            self.f.flush()
            if self.withStdout:
                OLDSTDOUT.flush()

    def close(self):
        if self.f:
            self.flush()
            log.removeObserver(self.emit)
            if self.withStdout:
                sys.stdout = OLDSTDOUT
                sys.stderr = OLDSTDOUT
            self.f.close()
            self.f = None
        return


LOGFILE = None

def get_backup_name(fname):
    n = datetime.now()
    s = n.strftime('%Y%m%d%H%M%S')
    d, f = os.path.split(fname)
    f, ext = os.path.splitext(f)
    i = 0
    while True:
        backupfile = '%s/%s_%s_%i%s' % (d,
         f,
         s,
         i,
         ext)
        if not os.path.exists(backupfile):
            return backupfile
        i += 1


def start_log(fname, keepOld = False, withStdout = True):
    global LOGFILE
    if keepOld:
        if os.path.exists(fname):
            backupfile = get_backup_name(fname)
            os.rename(fname, backupfile)
    LOGFILE = TwistedLogFile(fname, withStdout)
    give_perm(fname)


def stop_log():
    global LOGFILE
    if LOGFILE:
        LOGFILE.close()
        LOGFILE = None
    return


def tick_log():
    if LOGFILE and LOGFILE.withStdout:
        LOGFILE.flush()
        pos = LOGFILE.f.tell()
        if pos >= 524288:
            LOGFILE.close()
            fname = LOGFILE.name
            backupfile = get_backup_name(fname)
            os.rename(fname, backupfile)
            start_log(fname, withStdout=LOGFILE.withStdout)


def real_spawn(path, cmd, args, needRoot = False):
    needconsole = False
    if not cmd:
        cmd = sys.executable
        needconsole = True
    if PLATFORM == 'win':
        if needconsole:
            print 'start "%s" %s\nargs: %s' % (path, cmd, args)
            os.system('start "%s" %s %s' % (path, cmd, args))
        else:
            print 'CreateProcess "%s" %s\nargs: %s' % (path, cmd, args)
            cmd = '%s/%s' % (path, cmd)
            import win32process
            flags = win32process.CREATE_BREAKAWAY_FROM_JOB | win32process.CREATE_NEW_PROCESS_GROUP | win32process.DETACHED_PROCESS
            win32process.CreateProcess(cmd, args, None, None, False, flags, None, path, win32process.STARTUPINFO())
    else:
        cmd = '%s/%s' % (path, cmd)
        if needRoot:
            print 'pytge.Spawn "%s"\nargs: %s' % (cmd, args)
            import pytge
            pytge.Spawn(1, cmd, args.split(' '))
        else:
            print 'open -a "%s"\nargs: %s' % (cmd, args)
            argsname = '%s/args.txt' % path
            args = '-rmargs ' + args
            f = file(argsname, 'w')
            f.write(args)
            f.close()
            os.chmod(argsname, stat.S_IRWXO | stat.S_IRWXG | stat.S_IRWXU)
            os.system('open -a "%s"' % cmd)
    return