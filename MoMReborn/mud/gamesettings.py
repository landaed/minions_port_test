# Embedded file name: mud\gamesettings.pyo
GAMEROOT = 'minions.of.mirth'
GAMENAME = 'Minions of Mirth: Undead Wars'
LOCALTEST = False
GAMEBUILD_TEST = False
HAVE_PATCHED = False
GAMEVERSION = '2.6.2'
MASTERIP = 'momreborn.duckdns.org'
MASTERPORT = 2002
GMSERVERIP = MASTERIP
GMSERVERPORT = 2003
DB_BACKUP_PERIOD = 5400
LOGIN_DELAY = 30
DEF_TIMEOUT = 240
MASTER_PASSWORD = '^$!^@&uUUUuqjlkja--++'
GMSERVER_PASSWORD = '&^!(*&@(*@jjjkkwiwiwu--++'
PATCH_URL = 'http://momreborn.duckdns.org'
GAMEBUILD_PREFIX = ''
IRC_IP = 'irc.prairiegames.com'
IRC_PORT = 6667
from mud.utils import *
import os, sys

def BetaSettings():
    global GAMEBUILD_PREFIX
    global GMSERVERIP
    global MASTERIP
    global HAVE_PATCHED
    global GAMEBUILD_TEST
    global LOCALTEST
    global PATCH_URL
    if PLATFORM == 'mac' and is_frozen():
        conf = '../../config'
    else:
        conf = './config'
    if os.path.exists('%s/local.txt' % conf):
        LOCALTEST = True
        MASTERIP = '127.0.0.1'
        GAMEBUILD_PREFIX = 'LOCALTEST '
        print 'LOCALTEST'
        HAVE_PATCHED = True
        print 'NOPATCH'
    if not LOCALTEST and os.path.exists('%s/beta.txt' % conf):
        GAMEBUILD_TEST = True
        PATCH_URL = 'http://beta.minionsofmirth.net'
        GAMEBUILD_PREFIX = 'BETA '
        MASTERIP = 'beta.minionsofmirth.net'
        print 'BETA'
    if not HAVE_PATCHED and os.path.exists('%s/nopatch.txt' % conf):
        HAVE_PATCHED = True
        print 'NOPATCH'
    GMSERVERIP = MASTERIP


def ServerSettings():
    global DEF_TIMEOUT
    if PLATFORM != 'win':
        raise Exception, 'not supported'
    BetaSettings()
    DEF_TIMEOUT = 480


IN_PATCHING = False

def ClientSettings():
    global IN_PATCHING
    BetaSettings()
    IN_PATCHING = is_patching()
    if HAVE_PATCHED and IN_PATCHING:
        raise Exception, 'cannot be patching'