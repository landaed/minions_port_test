# Embedded file name: mud\tgepython\console.pyo
import traceback
from tgenative import *
import inspect
import sys
from mud.utils import *

class TGEManager:

    def __init__(self):
        self.simDataBlocks = {}
        self.simObjects = {}
        self.objectLookup = {}
        self.functionBindings = {}

    def registerObject(self, id, object):
        self.objectLookup[id] = object
        if isinstance(object, SimDataBlock):
            self.simDataBlocks[id] = object
        else:
            self.simObjects[id] = object

    def unregisterObject(self, objectid):
        o = self.objectLookup[objectid]
        if isinstance(o, SimDataBlock):
            del self.simDataBlocks[objectid]
        else:
            del self.simObjects[objectid]
        o._tgedeleted = True
        del self.objectLookup[objectid]

    def cleanup(self):
        for x in self.simObjects.itervalues():
            x._tge.delete()

        for x in self.simDataBlocks.itervalues():
            x._tge.delete()

        self.objectLookup.clear()
        self.simObjects.clear()
        self.simDataBlocks.clear()

    def export(self, function, namespace, fname, usage, minarg, maxarg):
        if namespace == None:
            namespace = 'Global'
            TGENativeExport(fname, usage, minarg, maxarg)
        else:
            TGENativeExport(namespace, fname, usage, minarg, maxarg)
        if not self.functionBindings.has_key(namespace):
            self.functionBindings[namespace] = {}
        self.functionBindings[namespace][fname] = function
        return

    def callback(self, selfid, namespace, functionname, args):
        simo = None
        if selfid != None:
            try:
                simo = self.objectLookup[selfid]
            except:
                simo = None

        if not self.functionBindings[namespace].has_key(functionname):
            raise TypeError, ("TGECall: Function doesn't exist", namespace, functionname)
            return
        else:
            try:
                if simo != None:
                    r = self.functionBindings[namespace][functionname](simo, args)
                elif args[0] != None:
                    r = self.functionBindings[namespace][functionname](args)
                else:
                    r = self.functionBindings[namespace][functionname]()
            except:
                traceback.print_exc()
                return

            return r


def TGECleanup():
    gTGEManager.cleanup()


def TGEExport(function, namespace, fname, usage, minarg, maxarg):
    gTGEManager.export(function, namespace, fname, usage, minarg, maxarg)


def TGEDelete(selfid):
    gTGEManager.unregisterObject(selfid)


def TGEPyExec(filename, function = None):
    m = __import__(filename)
    if not function:
        m.PyExec()


def TGEGetObject(objname):
    try:
        x = TGEObject('objname')
    except:
        return None

    return x


def TGECallback(selfid, namespace, functionname, args):
    return gTGEManager.callback(selfid, namespace, functionname, args)


def TGEGameRunning():
    b = TGEGetGlobal('$Game::Running')
    if b == None or int(b) == 0:
        return False
    else:
        return True


gTGEManager = TGEManager()

class TGEWriter:

    def __init__(self):
        sys.stdout = self
        sys.stderr = self

    def write(self, text):
        TGEPrint(text)
        OLDSTDOUT.write(text)

    def flush(self):
        pass


gTGEWriter = TGEWriter()
print 'python %s' % sys.version
TGEInit(TGECallback, TGEDelete)