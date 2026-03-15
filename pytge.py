# pytge stub for Linux headless operation
# Original pytge is a compiled C extension (.pyd) wrapping the Torque Game Engine
# This stub allows the Python server processes to import pytorque without crashing

import sys
import time

def Init(argv):
    """Initialize the Torque Game Engine (stub - no-op on Linux)."""
    print("[pytge stub] Init called with %d args" % len(argv))

def Tick():
    """Run one frame of the Torque engine loop (stub - sleeps briefly)."""
    time.sleep(0.05)  # 20 ticks per second
    return True

def Shutdown():
    """Shutdown the Torque Game Engine (stub - no-op on Linux)."""
    print("[pytge stub] Shutdown called")

def TGEGetGlobal(name):
    """Get a TGE global variable (stub - returns empty string)."""
    return ""

def TGESetGlobal(name, value):
    """Set a TGE global variable (stub - no-op)."""
    pass
