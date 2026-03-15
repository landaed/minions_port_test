# Copyright (C) 2004-2007 Prairie Games, Inc
# Please see LICENSE.TXT for details


def getSQLiteURL(path):
    """Convert a file path to a SQLObject SQLite connection URI."""
    import os
    # Ensure absolute path uses sqlite:///path format
    if os.path.isabs(path):
        return "sqlite://%s" % path
    return "sqlite:%s" % path
