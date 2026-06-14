# Copyright (C) 2004-2007 Prairie Games, Inc
# Please see LICENSE.TXT for details

from mud_ext.gamesettings import override_ip_addresses
override_ip_addresses()

import os, sys

def main_is_frozen():
   return (hasattr(sys, "frozen") or # new py2exe
           hasattr(sys, "importers") # old py2exe
           or getattr(sys, 'frozen', False)) # tools/freeze
           
if main_is_frozen():
    os.chdir("../common")
    maindir = os.getcwd()
    sys.path.append(maindir)    
    
elif sys.platform == "win32":
    # sys.argv[0] may be just "WorldDaemon.py" (no directory) when launched from
    # the repo root; os.chdir("") raises WinError 123. Only chdir when there's
    # an actual directory component.
    _scriptdir = os.path.dirname(os.path.abspath(sys.argv[0]))
    if _scriptdir:
        os.chdir(_scriptdir)


from mud_ext.worlddaemon.main import main
main()


