# Copyright (C) 2004-2007 Prairie Games, Inc
# Please see LICENSE.TXT for details


def getSQLiteURL(path):
    """Convert a file path to a SQLObject SQLite connection URI.

    Works on Windows and POSIX. Some callers prepend a '/' to an already
    absolute path (e.g. "/C:\\Users\\...\\master.db"); on Windows that both
    confuses os.path.abspath and, left as "sqlite://C:\\...", makes SQLObject's
    URI parser treat the drive letter's ':' as a port. So:
      * strip a leading slash that sits in front of a Windows drive letter,
      * use forward slashes,
      * and encode the drive ':' as '|' in the single-slash URI form
        ("sqlite:/C|/Users/...") which SQLObject converts back to "C:/Users/...".
    """
    import os
    import re
    # "/C:\..." or "\C:/..." -> "C:\..."  (drop the spurious leading separator)
    if re.match(r"^[\\/][A-Za-z]:", path):
        path = path[1:]
    abs_path = os.path.abspath(path).replace("\\", "/")
    if os.name == "nt" and len(abs_path) > 1 and abs_path[1] == ":":
        # C:/Users/... -> sqlite:/C|/Users/...
        return "sqlite:/%s|%s" % (abs_path[0], abs_path[2:])
    return "sqlite://%s" % abs_path


def open_debug_log(name="enterworld_debug.log"):
    """Append-open a throwaway debug log in a portable temp dir, never raising.

    The enter-world path logged to a hardcoded "/tmp/..." which doesn't exist on
    Windows, so the open() threw and aborted entering the world. Use the OS temp
    dir instead, and fall back to a black-hole buffer if even that fails (these
    are debug logs; they must never break gameplay)."""
    try:
        import os
        import tempfile
        return open(os.path.join(tempfile.gettempdir(), name), "a")
    except Exception:
        import io
        return io.StringIO()

