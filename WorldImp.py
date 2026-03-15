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

from mud_ext.worlddaemon.worldimp import main
main()


