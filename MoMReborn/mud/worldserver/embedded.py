# Embedded file name: mud\worldserver\embedded.pyo
from time import time as sysTime
import traceback, sys, os
from tgenative import *
from mud.world.core import CoreSettings
from mud.gamesettings import *
from mud.utils import *
from mud.tgepython.console import TGEExport
import mud.world.newplayeravatar
import mud.world.playeravatar
import mud.world.simavatar
from mud.world.theworld import World
from mud.world.zone import Zone
from mud.world.player import Player, PlayerXPCredit
from mud.common.avatar import RoleAvatar
from mud.common.permission import User, Role
from mud.common.dbconfig import SetDBConnection
WORLDSERVER = None
MANHOLE = None
STARTZONE = 'trinst'
STARTTRANSFORM = '17.699 -288.385 121.573 0 0 1 35.9607'
DSTARTZONE = 'kauldur'
DSTARTTRANSFORM = '-203.48 -395.96 150.1 0 0 1 38.92'
MSTARTZONE = 'trinst'
MSTARTTRANSFORM = '-169.032 -315.986 150.9353 0 0 1 10.681'

def CreatePlayer():
    try:
        p = Player.byPublicName('ThePlayer')
    except:
        zone = Zone.byName(STARTZONE)
        dzone = Zone.byName(DSTARTZONE)
        mzone = Zone.byName(MSTARTZONE)
        p = Player(publicName='ThePlayer', password='ThePlayer', fantasyName='ThePlayer', logZone=zone, bindZone=zone, darknessLogZone=dzone, darknessBindZone=dzone, monsterLogZone=mzone, monsterBindZone=mzone)
        p.logTransformInternal = STARTTRANSFORM
        p.bindTransformInternal = STARTTRANSFORM
        p.darknessLogTransformInternal = DSTARTTRANSFORM
        p.darknessBindTransformInternal = DSTARTTRANSFORM
        p.monsterLogTransformInternal = MSTARTTRANSFORM
        p.monsterBindTransformInternal = MSTARTTRANSFORM
        user = User(name='ThePlayer', password='ThePlayer')
        user.addRole(Role.byName('Player'))
        user.addRole(Role.byName('Immortal'))

    p.premium = True


def ShutdownEmbeddedWorld():
    global MANHOLE
    global WORLDSERVER
    if not WORLDSERVER:
        return
    else:
        world = World.byName('TheWorld')
        world.shutdown()
        WORLDSERVER.shutdown()
        WORLDSERVER = None
        if MANHOLE:
            MANHOLE.stopListening()
        MANHOLE = None
        SetDBConnection(None)
        return


def SetupEmbeddedWorld(worldname):
    global WORLDSERVER
    DATABASE = '%s/data/worlds/singleplayer/%s/world.db' % (GAMEROOT, worldname)
    SetDBConnection(getSQLiteURL(DATABASE), True)
    try:
        user = User.byName('NewPlayer')
        user.destroySelf()
    except:
        pass

    CreatePlayer()
    from twisted.spread import pb
    from twisted.internet import reactor
    from twisted.cred.credentials import UsernamePassword
    from mud.server.app import Server
    WORLDSERVER = server = Server(3013)
    server.startServices()
    world = World.byName('TheWorld')
    try:
        v = int(TGEGetGlobal('$pref::gameplay::difficulty'))
    except:
        v = 0
        TGESetGlobal('$pref::gameplay::difficulty', 0)

    try:
        respawn = float(TGEGetGlobal('$pref::gameplay::monsterrespawn'))
    except:
        TGESetGlobal('$pref::gameplay::monsterrespawn', 0.0)
        respawn = 0.0

    try:
        SPpopulators = int(TGEGetGlobal('$pref::gameplay::SPpopulators'))
    except:
        SPpopulators = 0
        TGESetGlobal('$pref::gameplay::SPpopulators', 0)

    if v == 1:
        CoreSettings.DIFFICULTY = 0
    elif v == 2:
        CoreSettings.DIFFICULTY = 2
    else:
        CoreSettings.DIFFICULTY = 1
    CoreSettings.RESPAWNTIME = respawn
    CoreSettings.SPPOPULATORS = SPpopulators
    CoreSettings.SINGLEPLAYER = True
    world.launchTime = sysTime()
    world.singlePlayer = True
    world.startup()
    world.transactionTick()
    world.tick()