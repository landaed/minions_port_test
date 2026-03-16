# Copyright (C) 2004-2007 Prairie Games, Inc
# Please see LICENSE.TXT for details


def getSQLiteURL(path):
    """Convert a file path to a SQLObject SQLite connection URI."""
    import os
    # Always resolve to absolute path to avoid issues with cwd changes
    # between connection creation and actual use (SQLObject connects lazily)
    abs_path = os.path.abspath(path)
    return "sqlite://%s" % abs_path
