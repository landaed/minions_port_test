# tgenative stub for Linux headless operation
# Original tgenative is a compiled C extension providing Torque Game Engine bindings
# This stub provides no-op implementations for server-side usage

import sys


# --- Core TGE Functions ---

def TGEGetGlobal(name):
    """Get a TGE global variable."""
    return ""

def TGESetGlobal(name, value):
    """Set a TGE global variable."""
    pass

def TGECall(*args):
    """Call a TGE console function."""
    return ""

def TGEEval(script):
    """Evaluate a TGE script string."""
    return ""

def TGEExport(pattern, filename, append=False):
    """Export TGE variables matching pattern to a file."""
    pass

def TGENativeExport(*args):
    """Register a native-exported console function (stub - no-op)."""
    pass


# --- TGE Object System ---

class TGEObject:
    """Stub for TGE game objects."""
    def __init__(self, obj_id=None):
        self.id = obj_id or 0

    def getFieldValue(self, field):
        return ""

    def setFieldValue(self, field, value):
        pass

    def call(self, method, *args):
        return ""

    def getName(self):
        return ""

    def getClassName(self):
        return ""

    def getId(self):
        return self.id

    def __repr__(self):
        return "TGEObject(%s)" % self.id


class TGEConnection(TGEObject):
    """Stub for TGE network connections."""
    pass


class SimObject(TGEObject):
    """Stub for TGE SimObject."""
    pass


class SimDataBlock(TGEObject):
    """Stub for TGE SimDataBlock."""
    pass


# --- Console/Callback Registration ---

def TGERegisterFunction(namespace, name, func):
    """Register a Python function as a TGE console function."""
    pass

def TGERegisterPackage(name, activate=True):
    """Register a TGE script package."""
    pass

def TGERegisterCallbacks(obj):
    """Register callback methods on an object."""
    pass


# --- Misc ---

def TGEGetSimTime():
    """Get the current simulation time in milliseconds."""
    import time
    return int(time.time() * 1000)

def TGEGetRealTime():
    """Get the current real time in milliseconds."""
    import time
    return int(time.time() * 1000)
