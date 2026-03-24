# tgenative stub for Linux headless operation
# Original tgenative is a compiled C extension providing Torque Game Engine bindings
# This stub provides no-op implementations for server-side usage

import sys
import builtins


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

    def setText(self, text):
        pass

    def setVisible(self, visible):
        pass

    def isSimZombie(self):
        return 0

    def isSwimming(self):
        return 0

    def isFlying(self):
        return 0

    def playThread(self, slot, anim):
        pass

    def getVelocity(self):
        return [0.0, 0.0, 0.0]

    def setVelocity(self, vel):
        pass

    def setFollowObject(self, obj_id):
        pass

    def setAvoidFollowObject(self, avoid):
        pass

    def setMoveSpeed(self, speed):
        pass

    def hasFlyingAnimation(self):
        return 0

    def getCount(self):
        return 0

    def getObject(self, index):
        return 0

    def getTransform(self):
        """Return the object's transform as a list of floats [x,y,z, rx,ry,rz,rw]."""
        return getattr(self, '_transform', [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0])

    def setTransform(self, transform_str):
        """Set the object's transform from a space-separated string."""
        if isinstance(transform_str, str):
            parts = transform_str.split()
            self._transform = [float(p) for p in parts]
        elif isinstance(transform_str, (list, tuple)):
            self._transform = list(transform_str)

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

    def isSimZombie(self):
        return 0


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


# --- Visibility / canSee ---

_sim_lookup_registry = None
_VISIBILITY_RANGE = 500.0
_VISIBILITY_RANGE_SQ = _VISIBILITY_RANGE * _VISIBILITY_RANGE


def TGERegisterSimLookup(sim_lookup):
    """Register the SimMind's simLookup so TGEGenerateCanSee can use it."""
    global _sim_lookup_registry
    _sim_lookup_registry = sim_lookup


def TGEGenerateCanSee():
    """Compute distance-based visibility for all sim objects.
    Returns {sim_id: [list of visible sim_ids]} for each object."""
    if not _sim_lookup_registry:
        return None
    objects = list(_sim_lookup_registry.values())
    result = {}
    for so in objects:
        pos = getattr(so, 'position', None)
        if pos is None:
            continue
        visible = []
        for other in objects:
            if other.id == so.id:
                continue
            opos = getattr(other, 'position', None)
            if opos is None:
                continue
            dx = pos[0] - opos[0]
            dy = pos[1] - opos[1]
            dz = pos[2] - opos[2]
            if dx * dx + dy * dy + dz * dz <= _VISIBILITY_RANGE_SQ:
                visible.append(other.id)
        result[so.id] = visible
    return result


def NumPlayersInZone():
    """Return the number of players in the zone. Stub returns 1 (always active)."""
    return 1


# --- Misc ---

def TGEGetSimTime():
    """Get the current simulation time in milliseconds."""
    import time
    return int(time.time() * 1000)

def TGEGetRealTime():
    """Get the current real time in milliseconds."""
    import time
    return int(time.time() * 1000)


# --- Register functions as builtins (mimicking original C extension behavior) ---
# The original tgenative C extension registered these as Python builtins.
# Code in simmind.py etc. uses them as bare names without importing.
builtins.TGEGetGlobal = TGEGetGlobal
builtins.TGESetGlobal = TGESetGlobal
builtins.TGECall = TGECall
builtins.TGEEval = TGEEval
builtins.TGENativeExport = TGENativeExport
builtins.TGEGetSimTime = TGEGetSimTime
builtins.TGEGetRealTime = TGEGetRealTime
builtins.TGEGenerateCanSee = TGEGenerateCanSee
builtins.TGERegisterSimLookup = TGERegisterSimLookup
builtins.NumPlayersInZone = NumPlayersInZone
