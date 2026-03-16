# Embedded file name: mud\world\spawn.pyo
from twisted.spread import pb
from mud.common.persistent import Persistent
from mud.world.archetype import GetClass
from mud.world.defines import *
from mud.gamesettings import *
import mud.world.dialog
from mud.world.messages import ZoneMessage, ZoneSound
import mud.world.vendor
from mud.world.shared.vocals import *
from collections import defaultdict
from datetime import date
from math import ceil
from random import randint
from sqlobject import *
from time import strftime, strptime, time as sysTime

class SpawnSpell(Persistent):
    spawn = ForeignKey('Spawn')
    spellname = StringCol()


class SpawnEffect(Persistent):
    spawn = ForeignKey('Spawn')
    effectname = StringCol()


class SpawnSkill(Persistent):
    spawn = ForeignKey('Spawn')
    skillname = StringCol()
    level = IntCol()


class SpawnKillFaction(Persistent):
    spawn = ForeignKey('Spawn')
    faction = ForeignKey('Faction')
    percent = FloatCol(default=1.0)


class SpawnResistance(Persistent):
    spawn = ForeignKey('Spawn')
    resistType = IntCol()
    resistAmount = FloatCol()


class SpawnStat(Persistent):
    spawn = ForeignKey('Spawn')
    statname = StringCol()
    value = FloatCol()


class Spawn(Persistent):
    name = StringCol(alternateID=True)
    race = StringCol(default='Monster')
    sex = StringCol(default='Neuter')
    realm = IntCol(default=RPG_REALM_MONSTER)
    template = StringCol(default='')
    aggroRange = IntCol(default=20)
    followRange = IntCol(default=60)
    flags = IntCol(default=0)
    xpMod = FloatCol(default=1.0)
    difficultyMod = FloatCol(default=1.0)
    healthMod = FloatCol(default=1.0)
    damageMod = FloatCol(default=1.0)
    offenseMod = FloatCol(default=1.0)
    defenseMod = FloatCol(default=1.0)
    move = FloatCol(default=1)
    regenHealth = IntCol(default=0)
    regenMana = IntCol(default=0)
    regenStamina = IntCol(default=0)
    strBase = IntCol(default=0)
    dexBase = IntCol(default=0)
    refBase = IntCol(default=0)
    agiBase = IntCol(default=0)
    wisBase = IntCol(default=0)
    bdyBase = IntCol(default=0)
    mndBase = IntCol(default=0)
    mysBase = IntCol(default=0)
    seeInvisible = FloatCol(default=0)
    preBase = IntCol(default=0)
    resists = MultipleJoin('SpawnResistance')
    skills = MultipleJoin('SpawnSkill')
    effects = MultipleJoin('SpawnEffect')
    spawnSpellsInternal = MultipleJoin('SpawnSpell')
    spawnStatsInternal = MultipleJoin('SpawnStat')
    killFactions = MultipleJoin('SpawnKillFaction')
    lootProto = ForeignKey('LootProto', default=None)
    dialog = ForeignKey('Dialog', default=None)
    vendorProto = ForeignKey('VendorProto', default=None)
    pclassInternal = StringCol()
    plevel = IntCol(default=0)
    sclassInternal = StringCol(default='')
    slevel = IntCol(default=0)
    tclassInternal = StringCol(default='')
    tlevel = IntCol(default=0)
    model = StringCol(default='')
    animation = StringCol(default='')
    textureHead = StringCol(default='')
    textureArms = StringCol(default='')
    textureLegs = StringCol(default='')
    textureBody = StringCol(default='')
    textureHands = StringCol(default='')
    textureFeet = StringCol(default='')
    textureSingle = StringCol(default='')
    sndProfile = ForeignKey('SpawnSoundProfile', default=None)
    vocalSet = StringCol(default='')
    radius = FloatCol(default=2.0)
    scale = FloatCol(default=1)
    spawnInfos = MultipleJoin('SpawnInfo')
    factions = RelatedJoin('Faction')
    character = ForeignKey('Character', default=None)
    playerName = StringCol(default='')
    respawn = ForeignKey('Spawn', default=None)
    respawnTimer = IntCol(default=0)
    desc = StringCol(default='')

    def _init(self, *args, **kw):
        Persistent._init(self, *args, **kw)
        self.level = self.plevel
        self.modifiedScale = self.scale
        from spell import SpellProto
        self.spawnSpells = []
        for s in self.spawnSpellsInternal:
            try:
                spell = SpellProto.byName(s.spellname)
                self.spawnSpells.append(spell)
            except:
                print 'Warning: Unknown Spawn Spell -> %s' % s.spellname

        self.spawnStats = []
        for s in self.spawnStatsInternal:
            self.spawnStats.append(s)

        self.spawnInfoMale = None
        self.spawnInfoFemale = None
        self.sndProfileOverride = None
        return

    def destroySelf(self):
        for o in self.resists:
            o.destroySelf()

        for o in self.skills:
            o.destroySelf()

        for o in self.spawnSpellsInternal:
            o.destroySelf()

        for o in self.spawnStatsInternal:
            o.destroySelf()

        Persistent.destroySelf(self)

    def _get_spawnInfo(self):
        if self.sex == 'Female':
            return self.spawnInfoFemale
        else:
            return self.spawnInfoMale

    def _get_pclass(self):
        return GetClass(self.pclassInternal)

    def _set_pclass(self, pclass):
        self.pclassInternal = pclass.name

    def _get_sclass(self):
        if not self.sclassInternal:
            return None
        else:
            return GetClass(self.sclassInternal)

    def _set_sclass(self, sclass):
        if not sclass:
            self.sclassInternal = ''
            return
        self.sclassInternal = sclass.name

    def _get_tclass(self):
        if not self.tclassInternal:
            return None
        else:
            return GetClass(self.tclassInternal)

    def _set_tclass(self, tclass):
        if not tclass:
            self.tclassInternal = ''
            return
        self.tclassInternal = tclass.name

    def getSound(self, snd):
        sndProfile = self.sndProfile
        if self.sndProfileOverride:
            sndProfile = self.sndProfileOverride
        if not sndProfile:
            return None
        elif not sndProfile.sounds[snd]:
            return None
        else:
            return sndProfile.getSound(snd)

    def getSpawnInfo(self, sex = ''):
        from mud.world.shared.worlddata import SpawnInfo
        if sex == '':
            sex = self.sex
        if sex == 'Female':
            attr = 'spawnInfoFemale'
        else:
            attr = 'spawnInfoMale'
        if getattr(self, attr):
            si = getattr(self, attr)
        else:
            si = SpawnInfo()
            setattr(self, attr, si)
        si.spawn = self
        si.name = self.name
        si.modelname = self.model.lower() if self.model else ''
        si.radius = self.radius
        si.scale = self.scale
        si.animation = self.animation
        si.textureSingle = self.textureSingle
        si.textureBody = self.textureBody
        si.textureHead = self.textureHead
        si.textureLegs = self.textureLegs
        si.textureHands = self.textureHands
        si.textureFeet = self.textureFeet
        si.textureArms = self.textureArms
        si.realm = self.realm
        si.sex = sex
        si.race = self.race
        return si


class SpawnInfo(Persistent):
    spawn = ForeignKey('Spawn')
    frequency = IntCol(default=0)
    startTime = FloatCol(default=-1)
    endTime = FloatCol(default=-1)
    startDayRL = StringCol(default='')
    endDayRL = StringCol(default='')
    lifetime = FloatCol(default=0)
    wanderRange = FloatCol(default=0)
    wanderGroup = IntCol(default=0)
    spawnGroups = RelatedJoin('SpawnGroup')


class SpawnGroup(Persistent):
    groupName = StringCol()
    zone = ForeignKey('Zone')
    spawninfosInternal = RelatedJoin('SpawnInfo')
    targetName = StringCol(default='')
    popFreq = IntCol(default=-1)
    controllerInfo = ForeignKey('SpawnGroupControllerInfo', default=None)

    def _init(self, *args, **kw):
        Persistent._init(self, *args, **kw)
        self.spawninfosList = None
        return

    def _get_spawninfos(self):
        if self.spawninfosList == None:
            self.spawninfosList = self.spawninfosInternal
        return self.spawninfosList


class SpawnSoundProfile(Persistent):
    sndIdleLoop1 = StringCol(default='')
    sndIdleLoop2 = StringCol(default='')
    sndIdleLoop3 = StringCol(default='')
    sndIdleLoop4 = StringCol(default='')
    sndIdleRandom1 = StringCol(default='')
    sndIdleRandom2 = StringCol(default='')
    sndIdleRandom3 = StringCol(default='')
    sndIdleRandom4 = StringCol(default='')
    sndAlert1 = StringCol(default='')
    sndAlert2 = StringCol(default='')
    sndAlert3 = StringCol(default='')
    sndAlert4 = StringCol(default='')
    sndAttack1 = StringCol(default='')
    sndAttack2 = StringCol(default='')
    sndAttack3 = StringCol(default='')
    sndAttack4 = StringCol(default='')
    sndPain1 = StringCol(default='')
    sndPain2 = StringCol(default='')
    sndPain3 = StringCol(default='')
    sndPain4 = StringCol(default='')
    sndDeath1 = StringCol(default='')
    sndDeath2 = StringCol(default='')
    sndDeath3 = StringCol(default='')
    sndDeath4 = StringCol(default='')

    def _init(self, *args, **kw):
        Persistent._init(self, *args, **kw)
        sndattribs = ['sndIdleLoop',
         'sndIdleRandom',
         'sndAlert',
         'sndAttack',
         'sndPain',
         'sndDeath']
        for snd in sndattribs:
            num = 0
            for x in xrange(1, 5):
                if not getattr(self, snd + str(x)):
                    break
                num += 1

            setattr(self, 'numS' + snd[1:], num)

        sounds = self.sounds = {}
        sounds['sndPain'] = self.numSndPain
        sounds['sndIdleLoop'] = self.numSndIdleLoop
        sounds['sndIdleRandom'] = self.numSndIdleRandom
        sounds['sndAlert'] = self.numSndAlert
        sounds['sndAttack'] = self.numSndAttack
        sounds['sndDeath'] = self.numSndDeath

    def getSound(self, snd):
        w = self.sounds[snd]
        w = randint(1, w)
        return getattr(self, snd + str(w))


class Spawnpoint():

    def __init__(self, zone, transform, group, wandergroup):
        self.activeMobs = []
        self.activeInfo = None
        self.lifetime = 0
        self.delay = 0
        self.despawnTime = 0
        self.transform = transform
        self.zone = zone
        self.wanderGroup = wandergroup
        self.lastTick = sysTime()
        self.lastCheckTicker = 0
        self.blocked = False
        self.spawnGroupController = None
        populator = False
        if group.startswith('POPULATOR_'):
            populator = True
            p, num = group.split('_')
            num = int(num)
            if zone.populatorGroups.has_key(num):
                group = zone.populatorGroups[num]
            else:
                groups = []
                fgroups = []
                gengroups = []
                for sg in zone.zone.spawnGroups:
                    if sg.targetName or sg.popFreq < 0:
                        continue
                    unique = False
                    for sinfo in sg.spawninfos:
                        if sinfo.spawn.flags & RPG_SPAWN_UNIQUE:
                            unique = True
                            break

                    if unique:
                        print 'Warning: pop group contains a unique spawn', sg.groupName
                        continue
                    if 'CMT_RANK' in sg.groupName:
                        gengroups.append(sg)
                    elif 'PRT_RANK' in sg.groupName:
                        gengroups.append(sg)
                    elif 'MGE_RANK' in sg.groupName:
                        gengroups.append(sg)
                    elif 'RGE_RANK' in sg.groupName:
                        gengroups.append(sg)
                    elif sg.popFreq > 1:
                        fgroups.append(sg)
                    else:
                        groups.append(sg)

                if len(gengroups):
                    g = None
                    if len(gengroups) == 1:
                        g = gengroups[0]
                    else:
                        g = gengroups[randint(0, len(gengroups) - 1)]
                    if g.popFreq > 1:
                        fgroups.append(g)
                    else:
                        groups.append(g)
                for g in fgroups:
                    if not randint(0, g.popFreq):
                        groups.append(g)

                if not len(groups):
                    groups.extend(fgroups)
                if not len(groups):
                    if LOCALTEST:
                        print 'WARNING: No spawn for populator %i' % num
                elif len(groups) == 1:
                    group = groups[0].groupName.upper()
                else:
                    group = groups[randint(0, len(groups) - 1)].groupName.upper()
                zone.populatorGroups[num] = group
        self.groupName = group
        self.spawngroup = None
        for sg in zone.zone.spawnGroups:
            if sg.groupName.upper() == group.upper():
                if sg.controllerInfo:
                    self.spawnGroupController = sg.controllerInfo.spawnGroupController
                    self.spawngroup = self.spawnGroupController.registerSpawnpoint(self, sg.controllerInfo)
                    self.groupName = self.spawngroup.groupName
                else:
                    self.spawngroup = sg
                break
        else:
            if LOCALTEST:
                if not populator:
                    print 'WARNING: Cannot find %s SpawnGroup' % group

        return

    def removeMob(self, despawnTime = 0):
        if not len(self.activeMobs):
            return
        else:
            lastActiveMob = self.activeMobs[0]
            if not despawnTime:
                if lastActiveMob.spawn.respawnTimer:
                    despawnTime = lastActiveMob.spawn.respawnTimer
            self.activeMobs = []
            self.activeInfo = None
            self.despawnTime = despawnTime
            self.lastTick = sysTime()
            if self.spawnGroupController and not self.zone.stopped:
                self.blocked = self.spawnGroupController.spawnRemoved(self, lastActiveMob)
            return

    def getSpawnInfo(self, doTriggered = False, spawngroup = None):
        if self.blocked:
            return None
        if not spawngroup:
            spawngroup = self.spawngroup
            if not spawngroup:
                return None
        if spawngroup.targetName and not doTriggered:
            return None
        elif self.activeInfo or len(self.activeMobs):
            return None
        zone = self.zone
        time = zone.time
        sinfos = []
        for sinfo in spawngroup.spawninfos:
            if sinfo.spawn.flags & RPG_SPAWN_UNIQUE:
                alreadyup = False
                for m in zone.activeMobs:
                    if m.spawn == sinfo.spawn:
                        alreadyup = True
                        break
                else:
                    for m in zone.spawnedMobs:
                        if m.spawn == sinfo.spawn:
                            alreadyup = True
                            break

                if alreadyup:
                    continue
            if (sinfo.startTime == -1 or sinfo.endTime == -1) and (not sinfo.startDayRL or not sinfo.endDayRL):
                sinfos.append(sinfo)
                continue
            if sinfo.startTime != -1 and sinfo.endTime != -1 and not sinfo.startDayRL and not sinfo.endDayRL:
                if sinfo.endTime < sinfo.startTime:
                    if 24 >= time.hour >= sinfo.startTime or sinfo.endTime > time.hour >= 0:
                        sinfos.append(sinfo)
                elif sinfo.endTime > time.hour >= sinfo.startTime:
                    sinfos.append(sinfo)
                continue
            if sinfo.startDayRL and sinfo.endDayRL and sinfo.startTime == -1 and sinfo.endTime == -1:
                startDayRL = date(*strptime(sinfo.startDayRL + '-' + strftime('%Y'), '%m-%d-%Y')[0:3])
                endDayRL = date(*strptime(sinfo.endDayRL + '-' + strftime('%Y'), '%m-%d-%Y')[0:3])
                today = date.today()
                if endDayRL < startDayRL:
                    print endDayRL, today, startDayRL, endDayRL <= today <= startDayRL
                    if not endDayRL < today < startDayRL:
                        sinfos.append(sinfo)
                elif startDayRL <= today <= endDayRL:
                    sinfos.append(sinfo)
                continue

        if not len(sinfos):
            return None
        freqs = (RPG_FREQ_COMMON,
         RPG_FREQ_UNCOMMON,
         RPG_FREQ_RARE,
         RPG_FREQ_VERYRARE,
         RPG_FREQ_IMPOSSIBLE)
        for x in xrange(0, 5):
            for sinfo in sinfos:
                if sinfo.frequency == freqs[x]:
                    r = randint(0, freqs[x] - 1)
                    if not r:
                        return sinfo

        always = []
        for sinfo in sinfos:
            if sinfo.frequency <= 1:
                always.append(sinfo)

        if len(always):
            if len(always) == 1:
                return always[0]
            return always[randint(0, len(always) - 1)]
        else:
            return None

    def spawnMobByName(self, mname, caseInsensitive = False):
        hadMobs = len(self.activeMobs) > 0
        for aMob in self.activeMobs:
            aMob.zone.removeMob(aMob)

        self.activeMobs = []
        try:
            if caseInsensitive:
                con = Spawn._connection.getConnection()
                spawn = Spawn.get(con.execute('SELECT id FROM spawn WHERE lower(name)=lower("%s") LIMIT 1;' % mname).fetchone()[0])
            else:
                spawn = Spawn.byName(mname)
        except:
            return False

        zone = self.zone
        self.lifetime = -1
        self.activeMobs = [zone.spawnMob(spawn, self.transform, self.wanderGroup)]
        for aMob in self.activeMobs:
            aMob.spawnpoint = self

        self.activeInfo = None
        self.lastCheckTicker = 0
        if not hadMobs and self.spawnGroupController:
            self.spawnGroupController.spawnAdded(self)
        return True

    def triggeredSpawn(self, spawngroup = None):
        hadMobs = len(self.activeMobs) > 0
        for aMob in self.activeMobs:
            aMob.zone.removeMob(aMob)

        self.activeMobs = []
        mob = None
        sinfo = self.getSpawnInfo(True, spawngroup)
        if sinfo:
            zone = self.zone
            self.lifetime = sinfo.lifetime
            mob = zone.spawnMob(sinfo.spawn, self.transform, self.wanderGroup)
            mob.spawnpoint = self
            self.activeMobs = [mob]
            self.activeInfo = sinfo
        self.lastCheckTicker = 0
        if not hadMobs and self.spawnGroupController:
            self.spawnGroupController.spawnAdded(self)
        return mob

    def setDelay(self, delay):
        self.delay = delay
        self.lastTick = sysTime()

    def tick(self):
        if not self.spawngroup:
            return
        t = sysTime()
        delta = ceil((t - self.lastTick) * 6.0)
        self.lastTick = t
        if self.despawnTime > 0:
            self.despawnTime -= delta
        if self.delay > 0:
            self.delay -= delta
        if self.despawnTime > 0:
            return
        if self.delay > 0:
            return
        if self.lastCheckTicker > 0:
            self.lastCheckTicker -= delta
            return
        if self.blocked:
            return
        self.lastCheckTicker = 180
        zone = self.zone
        if len(self.activeMobs):
            if self.activeInfo:
                sinfo = self.activeInfo
                for aMob in reversed(self.activeMobs):
                    if not aMob.target and not aMob.corpseRemoval:
                        if sinfo.startTime != -1 and sinfo.endTime != -1:
                            if sinfo.endTime < sinfo.startTime:
                                if sinfo.startTime > zone.time.hour >= sinfo.endTime:
                                    zone.removeMob(aMob)
                            elif not sinfo.endTime > zone.time.hour >= sinfo.startTime:
                                zone.removeMob(aMob)
                        if sinfo.startDayRL and sinfo.endDayRL:
                            startDayRL = date(*strptime(sinfo.startDayRL + '-' + strftime('%Y'), '%m-%d-%Y')[0:3])
                            endDayRL = date(*strptime(sinfo.endDayRL + '-' + strftime('%Y'), '%m-%d-%Y')[0:3])
                            todayRL = date.today()
                            if endDayRL < startDayRL:
                                if endDayRL < todayRL < startDayRL:
                                    zone.removeMob(aMob)
                            elif not startDayRL <= todayRL <= endDayRL:
                                zone.removeMob(aMob)

            if not len(self.activeMobs):
                self.delay = 0
        if len(self.activeMobs):
            return
        sinfo = self.getSpawnInfo()
        if sinfo:
            self.lifetime = sinfo.lifetime
            if hasattr(sinfo, 'name'):
                print 'spawnMob %s' % sinfo.name
            mob = zone.spawnMob(sinfo.spawn, self.transform, self.wanderGroup)
            mob.spawnpoint = self
            self.activeMobs = [mob]
            self.activeInfo = sinfo
            if self.spawnGroupController:
                self.spawnGroupController.spawnAdded(self)


class SpawnGroupControllerInfo(Persistent):
    spawnGroup = ForeignKey('SpawnGroup')
    spawnGroupController = ForeignKey('SpawnGroupController')
    realm = IntCol(default=RPG_REALM_UNDEFINED)
    cycleMessage = StringCol(default='')
    cycleSound = StringCol(default='')
    spawnGroupSet = IntCol(default=0)
    groupIndex = IntCol(default=-1)


class SpawnGroupController(Persistent):
    name = StringCol(alternateID=True)
    spawnGroupInfosInternal = MultipleJoin('SpawnGroupControllerInfo')
    respawnCycle = IntCol(default=RPG_SPAWNCONTROLLER_CYCLE_RANDOM)
    respawnFlags = IntCol(default=RPG_SPAWNCONTROLLER_RESPAWN_NORMAL)

    def _init(self, *args, **kw):
        Persistent._init(self, *args, **kw)
        self.spawnGroupSets = None
        self.setRealms = {}
        self.spawnpoints = {}
        self.realm = RPG_REALM_UNDEFINED
        self.currentSpawnSet = None
        self.activeSpawns = 0
        self.killerRealms = defaultdict(int)
        self.lastKillerRealm = RPG_REALM_UNDEFINED
        return

    def registerSpawnpoint(self, spawnpoint, sgInfo):
        self.spawnpoints[spawnpoint] = sgInfo.groupIndex
        if not self.spawnGroupSets:
            sgSets = self.spawnGroupSets = {}
            for groupInfo in self.spawnGroupInfosInternal:
                sgSets.setdefault(groupInfo.spawnGroupSet, {})[groupInfo.groupIndex] = groupInfo
                self.setRealms[groupInfo.spawnGroupSet] = groupInfo.realm

            randIndex = randint(1, len(self.spawnGroupSets))
            self.currentSpawnSet = self.spawnGroupSets[randIndex]
            self.realm = self.setRealms[randIndex]
        try:
            return self.currentSpawnSet[sgInfo.groupIndex].spawnGroup
        except KeyError:
            return None

        return None

    def spawnAdded(self, spawnpoint):
        self.activeSpawns += 1

    def spawnRemoved(self, spawnpoint, lastMob):
        self.activeSpawns -= 1
        if lastMob and lastMob.kingKiller:
            killerRealm = lastMob.kingKiller.realm
            if killerRealm != self.realm:
                self.lastKillerRealm = killerRealm
                self.killerRealms[killerRealm] += 1
        if self.activeSpawns <= 0:
            self.cycleSpawnSet(lastMob)
            return True
        if self.respawnFlags & RPG_SPAWNCONTROLLER_RESPAWN_WIPE:
            return True
        return False

    def cycleSpawnSet(self, lastMob):
        respawnCycle = self.respawnCycle
        setPool = []
        if respawnCycle == RPG_SPAWNCONTROLLER_CYCLE_KILLERREALM:
            killerRealm = RPG_REALM_UNDEFINED
            maxNum = 0
            for realm, numKillers in self.killerRealms.iteritems():
                if numKillers > maxNum:
                    maxNum = numKillers
                    killerRealm = realm

            for setIndex, realm in self.setRealms.iteritems():
                if realm == killerRealm:
                    setPool.append(setIndex)

            if not len(setPool):
                respawnCycle = RPG_SPAWNCONTROLLER_CYCLE_REALM
        elif respawnCycle == RPG_SPAWNCONTROLLER_CYCLE_LASTKILLERREALM:
            for setIndex, realm in self.setRealms.iteritems():
                if realm == self.lastKillerRealm:
                    setPool.append(setIndex)

            if not len(setPool):
                respawnCycle = RPG_SPAWNCONTROLLER_CYCLE_REALM
        if respawnCycle == RPG_SPAWNCONTROLLER_CYCLE_REALM:
            for setIndex, realm in self.setRealms.iteritems():
                if realm != self.realm:
                    setPool.append(setIndex)

        elif respawnCycle == RPG_SPAWNCONTROLLER_CYCLE_OTHER:
            for setIndex, sgSet in self.spawnGroupSets.iteritems():
                if sgSet != self.currentSpawnSet:
                    setPool.append(setIndex)

        if not len(setPool):
            setPool = self.spawnGroupSets.keys()
        choice = setPool[randint(0, len(setPool) - 1)]
        self.currentSpawnSet = self.spawnGroupSets[choice]
        self.realm = self.setRealms[choice]
        self.killerRealms.clear()
        groupInfo = None
        for spawnpoint, groupIndex in self.spawnpoints.iteritems():
            if self.currentSpawnSet.has_key(groupIndex):
                groupInfo = self.currentSpawnSet[groupIndex]
                spawnpoint.groupName = groupInfo.spawnGroup.groupName
                spawnpoint.spawngroup = groupInfo.spawnGroup
                spawnpoint.blocked = False
                if self.respawnFlags & RPG_SPAWNCONTROLLER_RESPAWN_IMMEDIATE:
                    spawnpoint.despawnTime = 0
                    spawnpoint.delay = 0
                    spawnpoint.lastCheckTicker = 0
            else:
                spawnpoint.spawngroup = None

        if groupInfo:
            if groupInfo.cycleMessage:
                ZoneMessage(lastMob.zone, groupInfo.cycleMessage)
            if groupInfo.cycleSound:
                ZoneSound(lastMob.zone, groupInfo.cycleSound)
        return