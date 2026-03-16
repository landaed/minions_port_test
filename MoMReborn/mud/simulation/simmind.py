# Embedded file name: mud\simulation\simmind.pyo
from tgenative import *
from mud.tgepython.console import TGEExport
from twisted.spread import pb
from twisted.internet import reactor
from twisted.cred.credentials import UsernamePassword
from md5 import md5
from mud.simulation.shared.simdata import SpawnpointInfo, SimMobInfo, DialogTriggerInfo
from mud.simulation.simobject import SimObject
from mud.world.defines import *
from mud.world.core import CoreSettings
from mud.gamesettings import *
from mud.world.shared.vocals import *
from mud.world.shared.models import GetModelInfo, HMOUNT
import mud.world.shared.worlddata
import os, sys
import traceback
from math import radians, sqrt
from random import randint
import re
from itertools import chain
SIMMIND = None
DBNAME_PARSER = re.compile('\\.|\\\\|/')
DATABLOCK_RAW = '\ndatablock PlayerData(%s)\n{\n   renderFirstPerson = false;\n   emap = true;\n\n   className = Armor;\n   shapeFile = "~/data/shapes/%s";\n   cameraMinDist = 0;\n   cameraMaxDist = 4;\n   computeCRC = true;\n\n   canObserve = true;\n   cmdCategory = "Clients";\n\n   cameraDefaultFov = 75.0;\n   cameraMinFov = 5.0;\n   cameraMaxFov = 75.0;\n\n    //debrisShapeName = "~/data/shapes/player/debris_player.dts";\n   //debris = playerDebris;\n\n   aiAvoidThis = %s;\n  \n   radius = 1;\n   scale = 1;\n\n   minLookAngle = -1.4;\n   maxLookAngle = 1.4;\n   maxFreelookAngle = 3.0;\n\n   mass = 90;\n   drag = 0.3;\n   maxdrag = 0.4;\n   density = 10;\n   maxDamage = 100;\n   maxEnergy =  60;\n   repairRate = 0.33;\n   energyPerDamagePoint = 75.0;\n\n   rechargeRate = 0.256;\n\n   runForce = 48 * 90;\n   runEnergyDrain = 0;\n   minRunEnergy = 0;\n   maxForwardSpeed = 8;\n   maxBackwardSpeed = 4;\n   maxSideSpeed = 6;\n\n   maxUnderwaterForwardSpeed = 1.5;\n   maxUnderwaterBackwardSpeed = 0.75;\n   maxUnderwaterSideSpeed = 1.125;\n\n   jumpForce = 8.3 * 90;\n   jumpEnergyDrain = 0;\n   minJumpEnergy = 0;\n   jumpDelay = 15;\n\n   recoverDelay = 9;\n   recoverRunForceScale = 1.2;\n\n   minImpactSpeed = 3 * %s + 7;\n   speedDamageScale = 0.4;\n\n   boundingBox = "1.2 1.2 2.3";\n   pickupRadius = 0.75;\n\n   // Damage location details\n   boxNormalHeadPercentage       = 0.83;\n   boxNormalTorsoPercentage      = 0.49;\n   boxHeadLeftPercentage         = 0;\n   boxHeadRightPercentage        = 1;\n   boxHeadBackPercentage         = 0;\n   boxHeadFrontPercentage        = 1;\n\n   // Foot Prints\n   decalData   = PlayerFootprint;\n   decalOffset = 0.25;\n\n   //footPuffEmitter = LightPuffEmitter;\n   footPuffNumParts = 10;\n   footPuffRadius = 0.25;\n\n   dustEmitter = LiftoffDustEmitter;\n\n   splash = PlayerSplash;\n   splashVelocity = 4.0;\n   splashAngle = 67.0;\n   splashFreqMod = 300.0;\n   splashVelEpsilon = 0.60;\n   bubbleEmitTime = 0.4;\n   splashEmitter[0] = PlayerFoamDropletsEmitter;\n   splashEmitter[1] = PlayerFoamEmitter;\n   splashEmitter[2] = PlayerBubbleEmitter;\n   mediumSplashSoundVelocity = 10.0;\n   hardSplashSoundVelocity = 20.0;\n   exitSplashSoundVelocity = 5.0;\n\n   // Controls over slope of runnable/jumpable surfaces\n   runSurfaceAngle  = 55;\n   jumpSurfaceAngle = 55;\n   maxStepHeight = 0.75;\n\n   minJumpSpeed = 20;\n   maxJumpSpeed = 30;\n\n   horizMaxSpeed = 68;\n   horizResistSpeed = 33;\n   horizResistFactor = 0.35;\n\n   upMaxSpeed = 80;\n   upResistSpeed = 25;\n   upResistFactor = 0.3;\n\n   footstepSplashHeight = 0.35;\n\n\n   groundImpactMinSpeed    = 10.0;\n   groundImpactShakeFreq   = "4.0 4.0 4.0";\n   groundImpactShakeAmp    = "1.0 1.0 1.0";\n   groundImpactShakeDuration = 0.8;\n   groundImpactShakeFalloff = 10.0;\n\n   //exitingWater         = ExitingWaterLightSound;\n\n   observeParameters = "0.5 4.5 4.5";\n   \n   scaleLimit = %s;\n};\n'

class ZoneInfo():

    def __init__(self):
        self.scaleLimit = 20


def CreateShapeImage(shapename):
    dbname = DBNAME_PARSER.sub('_', shapename)
    try:
        to = TGEObject(dbname)
        return to
    except:
        eval = '\ndatablock ShapeBaseImageData(%s)\n{\n   // Basic Item properties\n   shapeFile = "~/data/shapes/equipment/%s";\n};\n' % (dbname, shapename)

    TGEEval(eval)
    db = TGEObject(dbname)
    db.setDynamic()
    return dbname


def CreateTSShapePlayerDatablock(spawn, dbname, model):
    dbname += 'DTS'
    try:
        to = TGEObject(dbname)
    except:
        eval = ''
        if spawn.animation:
            f = file('%s/data/shapes/character/animations/%s/animation.cfg' % (GAMEROOT, spawn.animation))
            eval = f.read()
            f.close()
            eval = eval.replace('$datablock', dbname)
            eval = eval.replace('$dts', model)
            eval = eval.replace('#', '~/data/shapes/character/animations')
        else:
            eval = 'datablock TSShapeConstructor(%s)\n            {\n                baseShape = "~/data/shapes/%s";\n            };\n            ' % (dbname, model)
        TGEEval(eval)

    db = TGEObject(dbname)
    db.setDynamic()


def CreatePlayerDatablock(spawn, isPlayer = False):
    global SIMMIND
    modelname = spawn.modelname
    if any([not modelname, 'quarantine' in modelname, spawn.race in RPG_PC_RACES]):
        if spawn.race not in RPG_PC_RACES:
            modelname = 'undead/skeleton.dts'
            spawn.animation = 'humanoid'
            spawn.textureSingle = 'single/skeleton'
            spawn.look = 0
        else:
            if isPlayer:
                look = 0
                if '1' in spawn.modelname:
                    look = 1
                if '2' in spawn.modelname:
                    look = 2
            else:
                look = randint(0, 2)
            size, model, tex, animation = GetModelInfo(spawn.race, spawn.sex, look)
            spawn.look = look
            spawn.size = size
            modelname = model
            spawn.animation = animation
            if not spawn.textureHead:
                spawn.textureHead = tex[0]
            if not spawn.textureArms:
                spawn.textureArms = tex[1]
            if not spawn.textureLegs:
                spawn.textureLegs = tex[2]
            if not spawn.textureBody:
                spawn.textureBody = tex[3]
            if not spawn.textureFeet:
                spawn.textureFeet = tex[4]
            if not spawn.textureHands:
                spawn.textureHands = tex[5]
    modelname = 'character/models/%s' % modelname
    if not modelname.endswith('.dts'):
        modelname += '.dts'
    if isPlayer:
        aiAvoidThis = 'true'
    else:
        aiAvoidThis = 'false'
    ext = 'PlayerData'
    dbname = DBNAME_PARSER.sub('_', modelname[:-4]) + ext
    scaleLimit = str(SIMMIND.zoneInfo.scaleLimit)
    if scaleLimit[0] == '.':
        scaleLimit = '0' + scaleLimit
    try:
        return TGEObject(dbname)
    except:
        eval = DATABLOCK_RAW % (dbname,
         modelname,
         aiAvoidThis,
         spawn.scale,
         scaleLimit)
        TGEEval(eval)
        db = TGEObject(dbname)
        db.setDynamic()
        CreateTSShapePlayerDatablock(spawn, dbname, modelname)
        return db


class SimLookup(dict):

    def __setitem__(self, item, val):
        item = int(item)
        return dict.__setitem__(self, item, val)

    def __getitem__(self, item):
        item = int(item)
        return dict.__getitem__(self, item)


class SimMind(pb.Root):

    def errBack(self, reason):
        print 'errBack: %s' % reason

    def __init__(self, perspective = None, zoneInstanceName = None):
        global SIMMIND
        SIMMIND = self
        self.zoneInstanceName = zoneInstanceName
        self.perspective = perspective
        self.zombieUpdateTimer = 4
        self.simLookup = {}
        self.simObjects = []
        self.updateSimObjects()
        self.tickBrains()
        self.updateCanSee()
        self.passwords = {}
        self.psystemCount = 0
        self.spawnInfos = {}
        self.playerConnections = {}
        self.gameConnectionIds = []
        self.mobInfos = {}
        self.playerMobInfos = {}
        self.playerSpawnInfos = {}
        self.selectCredit = {}
        self.projectiles = {}
        self.zoneInfo = ZoneInfo()
        self.deathMarkers = {}

    def onZoneTrigger(self, trigger, obj):
        if obj.getClassName() != 'Player':
            return
        zonelink = trigger.ZoneLink
        id = int(obj.getId())
        so = self.simLookup[id]
        d = self.perspective.callRemote('SimAvatar', 'onZoneTrigger', so, zonelink)

    def remote_setZoneInfo(self, scaleLimit):
        self.zoneInfo.scaleLimit = scaleLimit

    def remote_setSpawnInfos(self, spawns):
        for spawn in spawns:
            self.spawnInfos[spawn.name] = spawn
            CreatePlayerDatablock(spawn, False)

    def remote_setPlayerPasswords(self, passwords):
        self.passwords = passwords

    def remote_addPlayerMobInfo(self, pid, mobInfo, spInfo):
        self.playerMobInfos[pid].append(mobInfo)
        self.playerSpawnInfos[pid].append(spInfo)

    def updateSpawnInfo(self, spinfo):
        for pid, spawninfos in self.playerSpawnInfos.iteritems():
            if spinfo in spawninfos:
                try:
                    simObject = self.simLookup[pid]
                    if simObject.spawnInfo == spinfo:
                        player = TGEObject(pid)
                        for x in xrange(0, 7):
                            player.setSkin(x, '')

                        datablock = CreatePlayerDatablock(spinfo, True)
                        player.SetDataBlock(datablock)
                        if spinfo.race in RPG_PC_RACES:
                            size, model, tex, animation = GetModelInfo(spinfo.race, spinfo.sex, 0)
                            player.setScaleModifier(1.0)
                            player.setScale('%f %f %f' % (size, size, size))
                        else:
                            player.setScaleModifier(1.0)
                            player.setScale('%f %f %f' % (spinfo.scale, spinfo.scale, spinfo.scale))
                        self.setPlayerSkins(player, simObject.mobInfo, spinfo)
                        simObject.brain.noanim = True
                except KeyError:
                    pass

    def remote_setPlayerSpawnInfo(self, pid, name):
        player = TGEObject(pid)
        for x in xrange(0, 7):
            player.setSkin(x, '')

        for spinfo in self.playerSpawnInfos[pid]:
            if spinfo.name == name:
                datablock = CreatePlayerDatablock(spinfo, True)
                player.SetDataBlock(datablock)
                self.simLookup[pid].spawnInfo = spinfo
                for m in self.playerMobInfos[pid]:
                    if m.NAME == spinfo.name:
                        self.simLookup[pid].mobInfo = m
                        break

                if spinfo.race in RPG_PC_RACES:
                    size, model, tex, animation = GetModelInfo(spinfo.race, spinfo.sex, 0)
                    player.setScale('%f %f %f' % (size, size, size))
                else:
                    player.setScale('%f %f %f' % (spinfo.scale, spinfo.scale, spinfo.scale))
                self.setPlayerSkins(player, self.simLookup[pid].mobInfo, spinfo)
                player.playThread(0, 'pain')
                player.playThread(0, 'idle')
                return

    def remote_removePlayerMobInfo(self, pid, mid):
        nlist = []
        name = None
        for minfo in self.playerMobInfos[pid]:
            if minfo.ID == mid:
                name = minfo.NAME
                continue
            nlist.append(minfo)

        slist = []
        if name:
            slist = list((sinfo for sinfo in self.playerSpawnInfos[pid] if sinfo.name != name))
        self.playerMobInfos[pid] = nlist
        self.playerSpawnInfos[pid] = slist
        return

    def setPlayerSkins(self, player, mobInfo, spawninfo):
        if spawninfo.textureSingle or spawninfo.textureBody.startswith('single/') or spawninfo.textureBody.startswith('multi/'):
            player.setSkin(6, '~/data/shapes/character/textures/%s' % spawninfo.textureSingle)
            if spawninfo.textureHead:
                player.setSkin(0, '~/data/shapes/character/textures/%s' % spawninfo.textureHead)
            if spawninfo.textureBody:
                player.setSkin(5, '~/data/shapes/character/textures/%s' % spawninfo.textureBody)
            if spawninfo.textureArms:
                player.setSkin(1, '~/data/shapes/character/textures/%s' % spawninfo.textureArms)
            if spawninfo.textureLegs:
                player.setSkin(2, '~/data/shapes/character/textures/%s' % spawninfo.textureLegs)
            if spawninfo.textureHands:
                player.setSkin(4, '~/data/shapes/character/textures/%s' % spawninfo.textureHands)
            if spawninfo.textureFeet:
                player.setSkin(3, '~/data/shapes/character/textures/%s' % spawninfo.textureFeet)
        else:
            if spawninfo.race == 'Titan' and spawninfo.sex == 'Male':
                player.setSkin(6, '~/data/shapes/character/textures/multi/titan_male_special')
            elif spawninfo.race == 'Titan' and spawninfo.sex == 'Female':
                player.setSkin(6, '~/data/shapes/character/textures/multi/titan_female_special')
            player.setSkin(0, '~/data/shapes/character/textures/%s' % spawninfo.textureHead)
            if mobInfo.MATARMS:
                player.setSkin(1, '~/data/shapes/character/textures/%s' % mobInfo.MATARMS)
            else:
                player.setSkin(1, '~/data/shapes/character/textures/%s' % spawninfo.textureArms)
            if mobInfo.MATLEGS:
                player.setSkin(2, '~/data/shapes/character/textures/%s' % mobInfo.MATLEGS)
            else:
                player.setSkin(2, '~/data/shapes/character/textures/%s' % spawninfo.textureLegs)
            if mobInfo.MATFEET:
                player.setSkin(3, '~/data/shapes/character/textures/%s' % mobInfo.MATFEET)
            else:
                player.setSkin(3, '~/data/shapes/character/textures/%s' % spawninfo.textureFeet)
            if mobInfo.MATHANDS:
                player.setSkin(4, '~/data/shapes/character/textures/%s' % mobInfo.MATHANDS)
            else:
                player.setSkin(4, '~/data/shapes/character/textures/%s' % spawninfo.textureHands)
            if mobInfo.MATBODY:
                player.setSkin(5, '~/data/shapes/character/textures/%s' % mobInfo.MATBODY)
            else:
                player.setSkin(5, '~/data/shapes/character/textures/%s' % spawninfo.textureBody)

    def onClientEnterGameResult(self, results, connection):
        if connection not in self.gameConnectionIds:
            print 'Player Dropped before Client Enter Game, possible kick'
            return
        transform, spawnInfos, mobInfos, avatarIndex, role = results
        transform[6] = radians(transform[6])
        t = ' '.join((str(val) for val in transform))
        conn = TGEObject(connection)
        dblocks = [ CreatePlayerDatablock(sp, True) for sp in spawnInfos ]
        playerid = int(conn.onClientEnterGameReal(t, dblocks[avatarIndex].getName()))
        player = TGEObject(playerid)
        player.realm = mobInfos[0].REALM
        if role == 'Monster':
            player.setShapeName('%s (%s)' % (spawnInfos[avatarIndex].name, role))
        elif role == 'Immortal' or role == 'Guardian':
            sn = player.getShapeName()
            player.setShapeName('%s (%s)' % (sn, role))
        self.setPlayerSkins(player, mobInfos[avatarIndex], spawnInfos[avatarIndex])
        self.playerConnections[playerid] = conn
        so = SimObject(playerid, spawnInfos[avatarIndex], mobInfos[avatarIndex], transform, -1, True)
        spinfo = spawnInfos[avatarIndex]
        if spinfo.race in RPG_PC_RACES:
            size, model, tex, animation = GetModelInfo(spinfo.race, spinfo.sex, 0)
            player.setScale('%f %f %f' % (size, size, size))
        else:
            player.setScale('%f %f %f' % (spinfo.scale, spinfo.scale, spinfo.scale))
        self.addSimObject(so)
        if int(TGEGetGlobal('$Py::ISSINGLEPLAYER')):
            name = 'ThePlayer'
        else:
            name = conn.getPublicName()
        self.playerMobInfos[playerid] = mobInfos
        self.playerSpawnInfos[playerid] = spawnInfos
        self.mobInfos[playerid] = mobInfos[avatarIndex]
        d = self.perspective.callRemote('SimAvatar', 'setPlayerSimObject', name, so)

    def onClientEnterGame(self, connection):
        if int(TGEGetGlobal('$Py::ISSINGLEPLAYER')):
            name = 'ThePlayer'
        else:
            name = TGEObject(connection).getPublicName()
        d = self.perspective.callRemote('SimAvatar', 'onClientEnterGame', name)
        d.addCallback(self.onClientEnterGameResult, connection)

    def addSimObject(self, so):
        self.simObjects.append(so)
        self.simLookup[so.id] = so

    def updateCanSee(self):
        try:
            cansee = TGEGenerateCanSee()
            if cansee:
                for id, cs in cansee.iteritems():
                    so = self.simLookup[id]
                    if int(so.tgeObject.isSimZombie()):
                        continue
                    so.updateCanSee(cs)

        except:
            pass

        self.canSeeTick = reactor.callLater(1, self.updateCanSee)

    def updateSimObjects(self):
        doZombie = False
        self.zombieUpdateTimer -= 1
        if not self.zombieUpdateTimer:
            self.zombieUpdateTimer = 4
            doZombie = True
        simUpdates = []
        numinzone = NumPlayersInZone()
        dedicated = int(TGEGetGlobal('$Server::Dedicated'))
        for so in self.simObjects:
            if not so.brain:
                continue
            tgeObject = so.tgeObject
            try:
                sz = int(tgeObject.isSimZombie()) != 0
                if sz != so.simZombie:
                    if sz and so.wanderGroup == -1:
                        tgeObject.setTransform(so.homePoint)
                    so.simZombie = sz
                    d = so.observer.callRemote('updateSimZombie', sz)
                    d.addErrback(self.errBack)
                if sz:
                    if dedicated and numinzone:
                        if so.wanderGroup <= 0:
                            continue
                        if doZombie:
                            simUpdates.append(so)
                        continue
                    continue
                conn = None
                if self.playerMobInfos.has_key(so.id):
                    if not so.spawnInfo.dirty:
                        for m in self.playerMobInfos[so.id]:
                            if m.dirty:
                                break
                        else:
                            simUpdates.append(so)
                            continue

                    conn = self.playerConnections[so.id]
                    zombie = False
                    worstmove = 999999
                    worstSpeedMod = 999999
                    walk = False
                    bestvis = 0
                    bestseeinvis = 0
                    bestscale = 0
                    alldead = True
                    bestlight = 0
                    flying = 1
                    attacking = False
                    overrideScale = False
                    minfo = so.mobInfo
                    sinfo = so.spawnInfo
                    sinfo.dirty = False
                    tgeObject.role = minfo.ROLE
                    target = so.brain.target
                    for m in self.playerMobInfos[so.id]:
                        m.dirty = False
                        if m.DETACHED:
                            continue
                        alldead = False
                        overrideScale = False
                        if m.MOVE < worstmove:
                            worstmove = m.MOVE
                        if m.SPEEDMOD < worstSpeedMod:
                            worstSpeedMod = m.SPEEDMOD
                        if m.WALK:
                            walk = True
                        if m.SIZE > bestscale:
                            bestscale = m.SIZE
                        if m.SEEINVISIBLE > bestseeinvis:
                            bestseeinvis = m.SEEINVISIBLE
                        if m.VISIBILITY > bestvis:
                            bestvis = m.VISIBILITY
                        if m.LIGHT > bestlight:
                            bestlight = m.LIGHT
                        if m.FLYING < flying:
                            flying = m.FLYING
                        if m.SLEEP:
                            worstmove = 0
                            worstSpeedMod = 0
                        if m.FEIGNDEATH:
                            worstmove = 0
                            worstSpeedMod = 0
                            flying = 0
                        if m.ATTACKING:
                            attacking = True
                        if not target and m.TGTID:
                            target = self.simLookup.get(m.TGTID)
                        if m.OVERRIDESCALE:
                            overrideScale = True

                    aggroRange = 100
                    if alldead:
                        move = 1
                        speedMod = 0
                        scale = 1
                        seeinvis = 0
                        vis = 1
                        flying = 0
                    else:
                        move = worstmove
                        speedMod = worstSpeedMod
                        scale = bestscale
                        seeinvis = bestseeinvis
                        vis = bestvis
                    if overrideScale:
                        tgeObject.setScaleModifier(1.0)
                        tgeObject.setScale('1.0 1.0 1.0')
                    else:
                        tgeObject.setScaleModifier(1.0)
                        tgeObject.setScale('%f %f %f' % (sinfo.scale, sinfo.scale, sinfo.scale))
                else:
                    if not so.mobInfo.dirty and not so.spawnInfo:
                        simUpdates.append(so)
                        continue
                    minfo = so.mobInfo
                    if minfo.PLAYERPET or tgeObject.playerPet:
                        tgeObject.setShapeName(minfo.VARNAME)
                    tgeObject.playerPet = minfo.PLAYERPET
                    tgeObject.realm = minfo.REALM
                    minfo.dirty = False
                    sinfo = so.spawnInfo
                    sinfo.dirty = False
                    move = minfo.MOVE
                    speedMod = minfo.SPEEDMOD
                    walk = minfo.WALK
                    if minfo.SLEEP:
                        move = 0
                        speedMod = 0
                    scale = minfo.SIZE
                    seeinvis = minfo.SEEINVISIBLE
                    vis = minfo.VISIBILITY
                    bestlight = minfo.LIGHT
                    flying = minfo.FLYING
                    attacking = minfo.ATTACKING
                    zombie = minfo.ZOMBIE
                    target = self.simLookup.get(minfo.TGTID)
                    aggroRange = minfo.AGGRORANGE
                mount0 = minfo.MOUNT0
                mount1 = minfo.MOUNT1
                mount2 = minfo.MOUNT2
                mount3 = minfo.MOUNT3
                twohanded = minfo.TWOHANDED
                if vis > 1:
                    vis = 1
                elif vis < 0:
                    vis = 0
                if seeinvis > 1:
                    seeinvis = 1
                elif seeinvis < 0:
                    seeinvis = 0
                if move > 4:
                    move = 4
                elif move < 0:
                    move = 0
                if speedMod < 0:
                    speedMod = 0
                elif speedMod * move > 32:
                    speedMod = 32 / move
                if scale < 0.2:
                    scale = 0.2
                elif scale > 5:
                    scale = 5
                if walk:
                    move *= 0.5
                so.brain.walk = walk
                tgeObject.setVisibility(vis)
                if conn:
                    conn.setSeeInvisible(seeinvis)
                tgeObject.aggroRange = aggroRange
                tgeObject.setFlyingMod(flying)
                tgeObject.setMoveModifier(move)
                tgeObject.setMaxForwardSpeed(speedMod)
                tgeObject.setScaleModifier(scale)
                tgeObject.setLightRadius(bestlight * 3.0)
                if not conn and not numinzone:
                    zombie = True
                tgeObject.setZombie(zombie)
                so.brain.twohanded = twohanded
                tgeObject.twoHanded = twohanded
                so.brain.attacking = attacking
                so.brain.setTarget(target)
                tgeObject.setEncounterSetting(minfo.ENCOUNTERSETTING)
                tgeObject.primaryLevel = minfo.PRIMARYLEVEL
                tgeObject.setAllianceLeader(minfo.ALLIANCELEADER)
                tgeObject.setGuildName(minfo.GUILDNAME)
                if not mount0:
                    tgeObject.unmountImage(0)
                elif minfo.MOUNT0_MAT:
                    tgeObject.mountImage(CreateShapeImage(mount0), 0, 1.0, '~/data/shapes/equipment/%s' % minfo.MOUNT0_MAT)
                else:
                    tgeObject.mountImage(CreateShapeImage(mount0), 0)
                if not mount1:
                    tgeObject.unmountImage(1)
                elif minfo.MOUNT1_MAT:
                    tgeObject.mountImage(CreateShapeImage(mount1), 1, 1.0, '~/data/shapes/equipment/%s' % minfo.MOUNT1_MAT)
                else:
                    tgeObject.mountImage(CreateShapeImage(mount1), 1)
                if not mount2:
                    tgeObject.unmountImage(2)
                elif minfo.MOUNT2_MAT:
                    tgeObject.mountImage(CreateShapeImage(mount2), 2, 1.0, '~/data/shapes/equipment/%s' % minfo.MOUNT2_MAT)
                else:
                    tgeObject.mountImage(CreateShapeImage(mount2), 2)
                if not mount3:
                    tgeObject.unmountImage(3)
                else:
                    scale = HMOUNT.get((sinfo.race, sinfo.sex, sinfo.look), 1.0)
                    tgeObject.mountImage(CreateShapeImage(mount3), 3, scale, '~/data/shapes/equipment/%s' % minfo.MOUNT3_MAT)
                self.setPlayerSkins(tgeObject, minfo, sinfo)
                simUpdates.append(so)
            except:
                traceback.print_exc()

        updates = []
        for so in simUpdates:
            r = so.updateTransform()
            if r:
                updates.append(r)

        if len(updates):
            self.perspective.callRemote('SimAvatar', 'updateSimObjects', updates)
        self.updateSimObjectsTick = reactor.callLater(2, self.updateSimObjects)
        return

    def tickBrains(self):
        for so in self.simObjects:
            if not so.brain or int(so.tgeObject.isSimZombie()):
                continue
            try:
                so.brain.tick()
            except:
                traceback.print_exc()

        self.brainsTick = reactor.callLater(0.1, self.tickBrains)

    def getBindPoints_r(self, simgroup, bindpoints):
        for x in xrange(0, int(simgroup.getCount())):
            tobj = TGEObject(simgroup.getObject(x))
            if tobj.getClassName() == 'SimGroup':
                self.getBindPoints_r(tobj, bindpoints)
            elif tobj.getClassName() == 'rpgBindPoint':
                bindpoints.append(tobj)

    def remote_getBindPoints(self):
        mg = TGEObject('MissionGroup')
        bindpoints = []
        self.getBindPoints_r(mg, bindpoints)
        abindpoints = [ tuple(wp.getTransform()[:3]) for wp in bindpoints ]
        return abindpoints

    def getWayPoints_r(self, simgroup, waypoints):
        for x in xrange(0, int(simgroup.getCount())):
            tobj = TGEObject(simgroup.getObject(x))
            if tobj.getClassName() == 'SimGroup':
                self.getWayPoints_r(tobj, waypoints)
            elif tobj.getClassName() == 'rpgWayPoint':
                waypoints.append(tobj)

    def getWayPoints(self):
        self.waypoints = {}
        mg = TGEObject('MissionGroup')
        waypoints = []
        self.getWayPoints_r(mg, waypoints)
        for wp in waypoints:
            transform = wp.getTransform()
            wandergroup = int(wp.wandergroup)
            if wandergroup == -1:
                print 'Warning:  Uninitialized waypoint'
                continue
            try:
                self.waypoints[wandergroup].append(transform)
            except KeyError:
                self.waypoints[wandergroup] = [transform]

        self.paths = {}
        for wgroup, waypoints in self.waypoints.iteritems():
            self.paths[wgroup] = dict(((x, []) for x in xrange(0, len(waypoints))))
            paths = self.paths[wgroup]
            for x, wp1 in enumerate(waypoints):
                for y, wp2 in enumerate(waypoints):
                    if x == y:
                        continue
                    result = TGECall('MyCastRay', '%f %f %f' % (wp1[0], wp1[1], wp1[2]), '%f %f %f' % (wp2[0], wp2[1], wp2[2]))
                    if int(result):
                        paths[x].append(y)

            print 'waygroup %s: %s' % (wgroup, paths)

    def getDialogTriggers_r(self, simgroup, dtriggers):
        for x in xrange(0, int(simgroup.getCount())):
            tobj = TGEObject(simgroup.getObject(x))
            if tobj.getClassName() == 'SimGroup':
                self.getDialogTriggers_r(tobj, dtriggers)
            elif tobj.getClassName() == 'TSStatic':
                if tobj.dialogTrigger and float(tobj.dialogRange):
                    dtriggers.append(tobj)

    def getDialogTriggers(self):
        mg = TGEObject('MissionGroup')
        dtriggers = []
        self.getDialogTriggers_r(mg, dtriggers)
        tinfos = []
        for dtrigger in dtriggers:
            transform = dtrigger.getTransform()
            triginfo = DialogTriggerInfo()
            triginfo.position = tuple(transform[:3])
            triginfo.dialogTrigger = dtrigger.dialogTrigger
            triginfo.dialogRange = float(dtrigger.dialogRange)
            tinfos.append(triginfo)

        if len(tinfos):
            self.perspective.callRemote('SimAvatar', 'setDialogTriggers', tinfos)

    def onReachDestination(self, id):
        so = self.simLookup[id]
        if so.wanderGroup != -1 and self.waypoints.has_key(so.wanderGroup) and len(self.waypoints[so.wanderGroup]) > 1:
            if so.waypoint == -1:
                p1 = so.tgeObject.getPosition()
                bestd = 999999
                best = 0
                for c, p2 in enumerate(self.waypoints[so.wanderGroup]):
                    x = p1[0] - p2[0]
                    y = p1[1] - p2[1]
                    z = p1[2] - p2[2]
                    d = x * x + y * y + z * z
                    if d < bestd:
                        best = c
                        bestd = d

                so.waypoint = best
                transform = self.waypoints[so.wanderGroup][so.waypoint]
                so.tgeObject.setTransform(' '.join((str(val) for val in transform)))
            paths = self.paths[so.wanderGroup]
            bah = False
            try:
                waypoints = paths[so.waypoint]
            except KeyError:
                bah = True

            if bah or not len(waypoints):
                transform = ' '.join(map(str, self.waypoints[so.wanderGroup][randint(0, len(self.waypoints[so.wanderGroup]) - 1)][:3]))
                so.tgeObject.setMoveDestination(transform, True)
                return
            if len(waypoints) == 1:
                so.waypoint = waypoints[0]
            else:
                so.waypoint = waypoints[randint(0, len(waypoints) - 1)]
            transform = ' '.join(map(str, self.waypoints[so.wanderGroup][so.waypoint][:3]))
            so.tgeObject.setMoveDestination(transform, True)
        else:
            if so.wanderGroup != -1:
                print 'Warning: Wandering mob with no waypoints.  Wandergroup = %i' % so.wanderGroup
            transform = map(str, so.tgeObject.getTransform()[:3])
            home = so.homePoint.split(' ', 3)[-1]
            point = '%s %s' % (' '.join(transform), home)
            so.tgeObject.setTransform(point)

    def remote_warp(self, id, tid):
        try:
            src = self.simLookup[id]
        except:
            print "WARNING: Warp: SimObject Src doesn't exist"

        try:
            tgt = self.simLookup[tid]
        except:
            print "WARNING: Warp: SimObject Tgt doesn't exist"

        strans = src.tgeObject.getTransform()
        ttrans = tgt.tgeObject.getTransform()
        src.tgeObject.setVelocity('0 0 0')
        src.tgeObject.setTransform('%s %s %s %s %s %s %s' % (ttrans[0],
         ttrans[1],
         ttrans[2],
         strans[3],
         strans[4],
         strans[5],
         strans[6]))

    def getSpawnPoints_r(self, simgroup, spawnpoints):
        for x in xrange(0, int(simgroup.getCount())):
            tobj = TGEObject(simgroup.getObject(x))
            if tobj.getClassName() == 'SimGroup':
                self.getSpawnPoints_r(tobj, spawnpoints)
            elif tobj.getClassName() == 'rpgSpawnPoint':
                spawnpoints.append(tobj)

    def remote_getSpawnPoints(self):
        self.getWayPoints()
        self.getDialogTriggers()
        spoints = []
        mg = TGEObject('MissionGroup')
        self.getSpawnPoints_r(mg, spoints)
        thepoints = []
        for sp in spoints:
            transform = sp.getGroundTransform()
            transform = tuple((float(x) for x in transform.split(' ')))
            spoint = SpawnpointInfo()
            spoint.transform = transform
            spoint.group = sp.spawngroup.upper()
            spoint.wanderGroup = sp.wandergroup
            thepoints.append(spoint)

        try:
            if int(TGEGetGlobal('$Server::Dedicated')) or int(TGEGetGlobal('$pref::gameplay::SPpopulators')):
                from populator import Populate
                ppoints, ppaths, pwaypoints = Populate(thepoints, self.paths)
                thepoints.extend(ppoints)
                for wgroup, ppoints in pwaypoints.iteritems():
                    self.waypoints[wgroup] = ppoints

                for wgroup, paths in ppaths.iteritems():
                    self.paths[wgroup] = paths

        except:
            traceback.print_exc()

        return thepoints

    def remote_spawnBot(self, name, transform, wanderGroup, sinfo, mobInfo):
        datablock = CreatePlayerDatablock(sinfo, False)
        if not self.spawnInfos.has_key(sinfo.name):
            self.spawnInfos[sinfo.name] = sinfo
        spawnInfo = self.spawnInfos[sinfo.name]
        dbname = datablock.getName()
        id = int(TGEEval('newNPCOrc("%s","1.0","%s","%s");' % (' '.join(map(str, transform)), mobInfo.VARNAME, dbname)))
        bot = TGEObject(id)
        if spawnInfo.race in RPG_PC_RACES:
            size, model, tex, animation = GetModelInfo(spawnInfo.race, spawnInfo.sex, 0)
            size *= spawnInfo.scale
            bot.setScale('%f %f %f' % (size, size, size))
        else:
            scale = spawnInfo.scale
            bot.setScale('%f %f %f' % (scale, scale, scale))
        self.setPlayerSkins(bot, mobInfo, spawnInfo)
        so = SimObject(id, spawnInfo, mobInfo, transform, wanderGroup, False)
        self.mobInfos[id] = mobInfo
        self.addSimObject(so)
        self.onReachDestination(id)
        bot.playThread(0, 'idle')
        return so

    def remote_setFollowTarget(self, spawnId, targetId):
        so = self.simLookup[spawnId]
        tgt = None
        if targetId:
            tgt = self.simLookup[targetId]
        so.brain.setFollowTarget(tgt)
        return

    def remote_setTarget(self, spawnId, targetId):
        so = self.simLookup[spawnId]
        tgt = None
        if targetId:
            tgt = self.simLookup[targetId]
        so.brain.setTarget(tgt)
        return

    def remote_setHomeTransform(self, spawnId, homePos, homeRot):
        so = self.simLookup[spawnId]
        so.homePoint = ' '.join(map(str, chain(homePos, homeRot)))

    def remote_resetHomeTransform(self, spawnID):
        so = self.simLookup[spawnID]
        so.homePoint = so.backupHomePoint

    def remote_inheritHomeTransform(self, spawnID, masterID):
        so = self.simLookup[spawnID]
        masterso = self.simLookup[masterID]
        so.homePoint = masterso.homePoint
        so.backupHomePoint = masterso.backupHomePoint
        so.wanderGroup = masterso.wanderGroup

    def remote_clearTarget(self, spawnId):
        so = self.simLookup[spawnId]
        so.brain.setTarget(None)
        so.tgeObject.setFollowObject(0)
        if so.wanderGroup > 0:
            if so.waypoint != -1:
                transform = self.waypoints[so.wanderGroup][so.waypoint]
                so.tgeObject.setMoveDestination('%f %f %f' % (transform[0], transform[1], transform[2]), True)
            else:
                self.onReachDestination(so.id)
        else:
            pos = so.homePoint.rsplit(' ', 4)[0]
            so.waypoint = -1
            so.tgeObject.setMoveDestination(pos, False)
        return

    def grantSelectCredit(self, result, srcId):
        self.selectCredit[srcId] = False

    def dialogTrigger(self, srcId, trigger):
        if self.selectCredit.get(srcId, None):
            return
        else:
            try:
                src = self.simLookup[srcId]
            except KeyError:
                return

            self.selectCredit[srcId] = True
            d = self.perspective.callRemote('SimAvatar', 'dialogTrigger', srcId, trigger)
            d.addCallback(self.grantSelectCredit, srcId)
            d.addErrback(self.grantSelectCredit, srcId)
            return

    def bindTrigger(self, srcId):
        if self.selectCredit.get(srcId, None):
            return
        else:
            try:
                src = self.simLookup[srcId]
            except KeyError:
                return

            self.selectCredit[srcId] = True
            d = self.perspective.callRemote('SimAvatar', 'bindTrigger', srcId)
            d.addCallback(self.grantSelectCredit, srcId)
            d.addErrback(self.grantSelectCredit, srcId)
            return

    def select(self, srcId, tgtId, charIndex, doubleClick, modifier_shift):
        if self.selectCredit.get(srcId, None):
            return
        else:
            try:
                src = self.simLookup[srcId]
            except KeyError:
                return

            try:
                tgt = self.simLookup[tgtId]
            except KeyError:
                return

            self.selectCredit[srcId] = True
            d = self.perspective.callRemote('SimAvatar', 'select', srcId, tgtId, charIndex, doubleClick, modifier_shift)
            d.addCallback(self.grantSelectCredit, srcId)
            d.addErrback(self.grantSelectCredit, srcId)
            return

    def remote_setSelection(self, srcId, tgtId, charIndex):
        try:
            so = self.simLookup[srcId]
        except KeyError:
            return

        tgt = self.simLookup.get(tgtId)
        so.brain.setTarget(tgt)
        conn = TGEObject(srcId)
        conn.setSelectedObjectId(tgtId, charIndex)

    def remote_setDisplayName(self, srcId, charName):
        try:
            self.simLookup[srcId].tgeObject.setShapeName(charName)
        except:
            traceback.print_exc()

    def remote_newSpellEffect(self, srcId, effect, interrupt = True):
        src = self.simLookup[srcId]
        if interrupt:
            TGEEval('interruptSpellcasting(%s);' % src.tgeObject.getId())
        src.tgeObject.castSpell(effect)

    def remote_newAudioEmitterLoop(self, srcId, sound, time):
        src = self.simLookup[srcId]
        pos = ' '.join(map(str, src.position))
        if src.spawnInfo.scale > 3.0:
            desc = 'AudioDefaultLooping3d'
        else:
            desc = 'AudioClosestLooping3d'
        eval = '\n         %%p = new AudioEmitter(AUDIOEMITTERLOOP_%i) {\n            position = "%s";\n            rotation = "1 0 0 0";\n            scale = "1 1 1";\n            description = "%s";\n            filename = "~/data/sound/%s";\n            parentId = %i;\n         };\n         MissionCleanup.add(%%p);\n         %%p.schedule(%i,"delete");        \n        ' % (self.psystemCount,
         pos,
         desc,
         sound,
         srcId,
         time)
        TGEEval(eval)
        self.psystemCount += 1

    def remote_newParticleSystem(self, srcId, emitterName, particleName, time):
        src = self.simLookup[srcId]
        pos = ' '.join(map(str, src.position))
        eval = '\n         %%p = new ParticleEmitterNode(PARTICLESYSTEM_%i) {\n            position = "%s";\n            rotation = "1 0 0 0";\n            scale = "1 1 1";\n            dataBlock = "ChimneySmokeEmitterNode";\n            emitter = "%s";\n            velocity = "1";\n            textureOverride = "~/data/shapes/particles/%s";\n            parentId = %i;\n         };\n         MissionCleanup.add(%%p);\n         %%p.schedule(%i,"delete");        \n        ' % (self.psystemCount,
         pos,
         emitterName,
         particleName,
         srcId,
         time)
        TGEEval(eval)
        self.psystemCount += 1

    def remote_deleteObject(self, id):
        try:
            del self.mobInfos[id]
        except KeyError:
            pass

        tge = TGEObject(id)
        so = self.simLookup[id]
        del self.simLookup[id]
        self.simObjects.remove(so)
        tge.delete()

    def remote_immobilize(self, id):
        tge = TGEObject(id)
        if tge.getClassName() == 'AIPlayer':
            tge.setMoveSpeed(0.0)

    def onPlayerDeleted(self, id):
        try:
            del self.mobInfos[id]
        except KeyError:
            pass

        try:
            del self.playerMobInfos[id]
        except KeyError:
            pass

        try:
            del self.playerSpawnInfos[id]
        except KeyError:
            pass

        try:
            del self.playerConnections[id]
            so = self.simLookup[id]
            del self.simLookup[id]
            self.simObjects.remove(so)
        except KeyError:
            pass

    def remote_die(self, id):
        so = self.simLookup[id]
        so.brain.die()
        so.tgeObject.setDamageState('Disabled')

    def remote_casting(self, id, casting, interrupt = True):
        so = self.simLookup[id]
        if interrupt:
            TGEEval('interruptSpellcasting(%s);' % so.tgeObject.getId())
        so.brain.casting(casting)

    def remote_cast(self, id, projectile = False):
        so = self.simLookup[id]
        so.brain.cast(projectile)

    def remote_playAnimation(self, id, anim):
        so = self.simLookup[id]
        so.brain.playAnimation(anim)

    def remote_pain(self, id):
        so = self.simLookup[id]
        so.brain.pain()

    def remote_triggerParticleNodes(self, id, pnodes):
        tge = self.simLookup[id].tgeObject
        for node, particle, texture, duration in pnodes:
            tge.triggerParticleNode(node, particle, texture, duration)

    def remote_respawnPlayer(self, soId, transform):
        so = self.simLookup[soId]
        t = map(float, transform.split(' '))
        t[6] = radians(t[6])
        so.tgeObject.setTransform(t)
        so.tgeObject.setVelocity('0 0 0')
        so.position = (t[0], t[1], t[2] + 2.0)
        so.tgeObject.setDamageState('Enabled')
        so.brain.death = 0

    def remote_vocalize(self, sexcode, set, vox, which, loc):
        if sexcode == 1:
            sex = 'Female'
        else:
            sex = 'Male'
        if which < 10:
            num = '0%i' % which
        else:
            num = str(which)
        filename = 'vocalsets/%s_LongSet_%s/%s_LS_%s_%s%s.ogg' % (sex,
         set,
         sex,
         set,
         VOCALFILENAMES[vox],
         num)
        self.remote_playSound(filename, loc)

    def remote_playSound(self, sound, loc, bigSound = False):
        if bigSound:
            desc = 'AudioDefault3d'
        else:
            desc = 'AudioClosest3d'
        eval = 'serverPlay3d(%s,"%s/data/sound/%s","%f %f %f");' % (desc,
         GAMEROOT,
         sound,
         loc[0],
         loc[1],
         loc[2])
        TGEEval(eval)

    def remote_spawnExplosion(self, srcId, explosion, onground = 0):
        src = self.simLookup[srcId]
        loc = src.position
        eval = 'ServerSpawnExplosion(%s,"%f %f %f",%i);' % (explosion,
         loc[0],
         loc[1],
         loc[2],
         onground)
        TGEEval(eval)

    def destroyServer(self):
        global SIMMIND
        try:
            self.canSeeTick.cancel()
        except:
            pass

        try:
            self.updateSimObjectsTick.cancel()
        except:
            pass

        try:
            self.brainsTick.cancel()
        except:
            pass

        self.simLookup = None
        self.simObjects = None
        self.spawnInfos = None
        self.playerSpawnInfos = None
        self.mobInfos = None
        self.playerMobInfos = None
        SIMMIND = None
        return

    def onGameConnectionConnect(self, connId):
        self.gameConnectionIds.append(connId)

    def onGameConnectionDrop(self, connId):
        try:
            self.gameConnectionIds.remove(connId)
        except:
            pass

        if int(TGEGetGlobal('$Py::ISSINGLEPLAYER')):
            self.destroyServer()

    def onProjectileCollision(self, projId, hitId, hitPos):
        rpgid = self.projectiles[projId]
        if self.simLookup.has_key(hitId):
            hitPos = map(float, hitPos.split(' '))
            self.perspective.callRemote('SimAvatar', 'projectileCollision', rpgid, hitId, hitPos)

    def onImpact(self, simId, velocity):
        try:
            src = self.simLookup[simId]
            psrc = src.tgeObject.getPosition()
            self.perspective.callRemote('SimAvatar', 'onImpact', simId, velocity, psrc)
        except KeyError:
            pass

    def onProjectileDeleted(self, projId):
        try:
            rpgid = self.projectiles[projId]
        except KeyError:
            return

        self.perspective.callRemote('SimAvatar', 'deleteProjectile', rpgid)
        del self.projectiles[projId]

    def remote_launchProjectile(self, pid, srcId, tgtId, pdata, speed):
        try:
            src = self.simLookup[srcId]
            dst = self.simLookup[tgtId]
        except KeyError:
            self.perspective.callRemote('SimAvatar', 'deleteProjectile', pid)
            return

        if not pdata.startswith('AFX_'):
            psrc = src.tgeObject.getPosition()
            pdst = dst.tgeObject.getPosition()
            sz = psrc[2] + src.spawnInfo.radius * 0.75
            dz = pdst[2] + dst.spawnInfo.radius * 0.75
            x = pdst[0] - psrc[0]
            y = pdst[1] - psrc[1]
            z = dz - sz
            d = sqrt(x * x + y * y + z * z)
            if not d:
                self.perspective.callRemote('SimAvatar', 'deleteProjectile', pid)
                return
            x /= d
            y /= d
            z /= d
            rad = src.spawnInfo.radius / 3
            px = psrc[0] + x * rad
            py = psrc[1] + y * rad
            pz = sz + z * rad
            x *= speed
            y *= speed
            z *= speed
            myid = int(TGECall('LaunchProjectile', srcId, tgtId, '%f %f %f' % (px, py, pz), pdata, '%f %f %f' % (x, y, z)))
        else:
            myid = int(TGECall('LaunchAfxProjectile', srcId, tgtId, pdata[4:]))
            if myid == -1:
                self.perspective.callRemote('SimAvatar', 'deleteProjectile', pid)
                return
        self.projectiles[myid] = pid
        return True

    def remote_setWeather(self, wc):
        from weather import SetWeather
        SetWeather(wc)

    def remote_stop(self):
        if int(TGEGetGlobal('$Server::Dedicated')):
            TGEEval('quit();')

    def remote_kickPlayer(self, id, publicName):
        conn = None
        if id != -1:
            conn = self.playerConnections.get(id, None)
        else:
            for i in reversed(self.gameConnectionIds):
                try:
                    c = TGEObject(i)
                except:
                    self.gameConnectionIds.remove(i)
                    continue

                if c.getPublicName() == publicName:
                    conn = c
                    break

        if conn:
            conn.delete('You were kicked from the server.')
        return

    def remote_setDeathMarker(self, publicName, realm, pos, rot, cname):
        self.remote_clearDeathMarker(publicName)
        realmdata = ('', 'GraveMarkerFoLData', 'GraveMarkerMoDData', 'GraveMarkerMoDData')
        eval = '\n         %%p = new Item(%s_DeathMarker) {\n            position = "%f %f %f";\n            rotation = "%f %f %f %f";\n            scale = ".5 .5 .5";\n            dataBlock = "%s";\n            static = true;\n         };\n         MissionCleanup.add(%%p);\n        ' % (publicName,
         pos[0],
         pos[1],
         pos[2] + 0.25,
         rot[0],
         rot[1],
         rot[2],
         rot[3],
         realmdata[realm])
        TGEEval(eval)
        self.deathMarkers[publicName] = TGEObject('%s_DeathMarker' % publicName)
        self.deathMarkers[publicName].setShapeName("%s's Grave" % cname)

    def remote_clearDeathMarker(self, publicName):
        dm = self.deathMarkers.get(publicName, None)
        if dm:
            del self.deathMarkers[publicName]
            dm.delete()
        return

    def remote_clearParticleNode(self, id, slot):
        tge = self.simLookup[id].tgeObject
        if slot == RPG_SLOT_PRIMARY:
            node = 'Mount0'
        else:
            node = 'Mount1'
        tge.clearParticleNode(node)

    def remote_itemParticleNode(self, id, slot, particle, texture):
        tge = self.simLookup[id].tgeObject
        if slot == RPG_SLOT_PRIMARY:
            node = 'Mount0'
        else:
            node = 'Mount1'
        tge.triggerParticleNode(node, particle, texture, -1)


def PyOnImpact(args):
    objectId = int(args[1])
    velocity = int(args[2])
    SIMMIND.onImpact(objectId, velocity)


def PyOnProjectileCollision(args):
    projId = int(args[1])
    hitId = int(args[2])
    hitPos = args[3]
    SIMMIND.onProjectileCollision(projId, hitId, hitPos)


def PyOnProjectileDeleted(args):
    projId = int(args[1])
    if SIMMIND:
        SIMMIND.onProjectileDeleted(projId)


def PyOnGameConnectionConnect(args):
    connId = int(args[1])
    SIMMIND.onGameConnectionConnect(connId)


def PyOnGameConnectionDrop(args):
    connId = int(args[1])
    SIMMIND.onGameConnectionDrop(connId)


def PyOnEndSequence(args):
    id = int(args[1])
    try:
        so = SIMMIND.simLookup[id]
        so.brain.onEndSequence()
    except KeyError:
        pass


def OnReachDestination(args):
    id = int(args[1])
    SIMMIND.onReachDestination(id)


def PyOnPlayerDeleted(args):
    id = int(args[1])
    player = TGEObject(id)
    if player.getClassName() == 'Player':
        SIMMIND.onPlayerDeleted(id)


def OnDialogTrigger(args):
    srcId = int(args[1])
    trigger = args[2]
    SIMMIND.dialogTrigger(srcId, trigger)


def OnBindTrigger(args):
    srcId = int(args[1])
    SIMMIND.bindTrigger(srcId)


def PySelect(args):
    srcId = int(args[1])
    tgtId = int(args[2])
    charIndex = int(args[3])
    doubleClick = int(args[4])
    modifier_shift = int(args[5])
    SIMMIND.select(srcId, tgtId, charIndex, doubleClick, modifier_shift)


def PyClientBegin(args):
    print args


def PyValidatePlayer(args):
    publicName = args[1]
    password = args[2]
    try:
        if SIMMIND.passwords[publicName] == password:
            return 'Validated'
        return 'Error'
    except:
        return 'Error'


def PyOnClientEnterGame(args):
    connection = int(args[1])
    SIMMIND.onClientEnterGame(connection)


def PyZoneTrigger(args):
    trigger = TGEObject(args[1])
    obj = TGEObject(args[2])
    SIMMIND.onZoneTrigger(trigger, obj)


def StartSimulation():
    if int(TGEGetGlobal('$Server::Dedicated')):
        SIMMIND.perspective.callRemote('SimAvatar', 'startSimulation', SIMMIND, SIMMIND.zoneInstanceName, os.getpid())
    else:
        from mud.client.playermind import PLAYERMIND
        SIMMIND.perspective.callRemote('SimAvatar', 'startSimulation', PLAYERMIND.simMind, PLAYERMIND.simMind.zoneInstanceName)


def NumPlayersInZone():
    try:
        return len(SIMMIND.gameConnectionIds)
    except:
        return 0


def GotZoneConnect(zconnect):
    print 'GotZoneConnect: %s' % zconnect.niceName
    SIMMIND.zoneInstanceName = zconnect.instanceName
    eval = 'createServer("Multiplayer", "%s/data/missions/%s");' % (GAMEROOT, zconnect.missionFile)
    TGEEval(eval)


def DedicatedDisconnected(args):
    TGEEval('quit();')


def WorldConnected(perspective):
    perspective.notifyOnDisconnect(DedicatedDisconnected)
    SIMMIND.perspective = perspective
    serverPort = int(TGEGetGlobal('$Pref::Server::Port'))
    zone = TGEGetGlobal('$zoneArg')
    print 'shooting for %s %d' % (zone, serverPort)
    perspective.callRemote('SimAvatar', 'spawnDedicatedZone', zone, serverPort).addCallbacks(GotZoneConnect, Failure)


def GotWorldInfos(winfos, perspective):
    perspective.broker.transport.loseConnection()
    wname = TGEGetGlobal('$Py::DedicatedWorld')
    wname = wname.replace('_', ' ')
    found = False
    for world in winfos:
        print world.worldName, wname
        if world.worldName == wname:
            found = True
            factory = pb.PBClientFactory()
            world.worldIP = '127.0.0.1'
            print 'Connecting to: %s:%d' % (world.worldIP, world.worldPort)
            reactor.connectTCP(world.worldIP, world.worldPort, factory, timeout=DEF_TIMEOUT)
            mind = SimMind()
            password = md5('ZoneServer').digest()
            factory.login(UsernamePassword('ZoneServer-ZoneServer', password), mind).addCallbacks(WorldConnected, Failure)

    if not found:
        print 'World is not currently up'


def Failure(reason):
    print 'Failure: %s' % reason


def MasterConnected(perspective):
    d = perspective.callRemote('EnumWorlds', 'enumLiveWorlds')
    d.addCallbacks(GotWorldInfos, Failure, (perspective,))


def WorldSimulationLogin():
    TGESetGlobal('$Py::ISSINGLEPLAYER', 0)
    val = TGEGetGlobal('$Py::WorldPort')
    if val:
        worldport = int(val)
        factory = pb.PBClientFactory()
        reactor.connectTCP('127.0.0.1', worldport, factory, timeout=DEF_TIMEOUT)
        mind = SimMind()
        password = md5('ZoneServer').digest()
        d = factory.login(UsernamePassword('ZoneServer-ZoneServer', password), mind)
        d.addCallbacks(WorldConnected, Failure)


TGEExport(PyOnPlayerDeleted, 'Py', 'OnPlayerDeleted', 'desc', 2, 2)
TGEExport(PyOnImpact, 'Py', 'OnImpact', 'desc', 3, 3)
TGEExport(PyOnGameConnectionConnect, 'Py', 'OnGameConnectionConnect', 'desc', 2, 2)
TGEExport(PyOnGameConnectionDrop, 'Py', 'OnGameConnectionDrop', 'desc', 2, 2)
TGEExport(OnDialogTrigger, 'Py', 'OnDialogTrigger', 'desc', 3, 3)
TGEExport(OnBindTrigger, 'Py', 'OnBindTrigger', 'desc', 2, 2)
TGEExport(PyZoneTrigger, 'Py', 'ZoneTrigger', 'desc', 3, 3)
TGEExport(PySelect, 'Py', 'Select', 'desc', 6, 6)
TGEExport(PySelect, 'Py', 'select', 'desc', 6, 6)
TGEExport(PyClientBegin, 'Py', 'ClientBegin', 'desc', 2, 2)
TGEExport(PyValidatePlayer, 'Py', 'ValidatePlayer', 'desc', 3, 3)
TGEExport(PyOnClientEnterGame, 'Py', 'PyClientEnterGame', 'desc', 2, 2)
TGEExport(OnReachDestination, 'Py', 'onReachDestination', 'desc', 2, 2)
TGEExport(PyOnEndSequence, 'Py', 'onEndSequence', 'desc', 2, 2)
TGEExport(StartSimulation, 'Py', 'StartSimulation', 'desc', 1, 1)
TGEExport(WorldSimulationLogin, 'Py', 'WorldSimulationLogin', 'desc', 1, 1)
TGEExport(PyOnProjectileCollision, 'Py', 'OnProjectileCollision', 'desc', 4, 4)
TGEExport(PyOnProjectileDeleted, 'Py', 'OnProjectileDeleted', 'desc', 2, 2)

def PyExec():
    pass