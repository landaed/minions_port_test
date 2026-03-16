# Embedded file name: mud\world\battle.pyo
import random
import traceback
from sqlobject import *
from mud.common.persistent import Persistent
from defines import *
from core import *
from messages import ZoneMessage, ZoneSound

class BattleGroup(Persistent):
    triggerSpawnGroup = StringCol(default='')
    spawnGroup = StringCol(default='')
    attackDelay = IntCol(default=0)
    passive = BoolCol(default=False)
    battleSequence = ForeignKey('BattleSequence', default=None)


class BattleSequence(Persistent):
    zoneSound = StringCol(default='')
    zoneMessage = StringCol(default='')
    delay = IntCol(default=0)
    battleGroups = MultipleJoin('BattleGroup')
    nextSequence = ForeignKey('BattleSequence', default=None)


class BattleResult(Persistent):
    triggerSpawnGroup = StringCol(default='')
    spawnGroup = StringCol(default='')
    zoneSound = StringCol(default='')
    zoneMessage = StringCol(default='')


class BattleMustSurvive(Persistent):
    name = StringCol()
    battleProto = ForeignKey('BattleProto')


class BattleProto(Persistent):
    name = StringCol(alternateID=True)
    zoneName = StringCol(default='')
    zoneMessage = StringCol(default='')
    zoneSound = StringCol(default='')
    side1StartSequence = ForeignKey('BattleSequence', default=None)
    side2StartSequence = ForeignKey('BattleSequence', default=None)
    side1VictoryResult = ForeignKey('BattleResult', default=None)
    side2VictoryResult = ForeignKey('BattleResult', default=None)
    side1DefeatResult = ForeignKey('BattleResult', default=None)
    side2DefeatResult = ForeignKey('BattleResult', default=None)
    battleMustSurvive = MultipleJoin('BattleMustSurvive')


class BattleSide():

    def __init__(self):
        self.battle = None
        self.zone = None
        self.delay = 0
        self.sequence = None
        self.battleGroups = {}
        self.battleGroupAttackTimers = {}
        self.thinkTimer = 0
        self.forfeit = False
        self.mobs = []
        return

    def triggerSequence(self):
        if not self.sequence:
            traceback.print_stack()
            print 'AssertionError: battle side has no sequence assigned!'
            return
        else:
            self.battleGroups = {}
            self.battleGroupAttackTimers = {}
            self.mobs = []
            sequence = self.sequence
            if sequence.zoneMessage:
                ZoneMessage(self.zone, sequence.zoneMessage)
            if sequence.zoneSound:
                ZoneSound(self.zone, sequence.zoneSound)
            for bg in sequence.battleGroups:
                self.battleGroups[bg] = []
                self.battleGroupAttackTimers[bg] = bg.attackDelay
                override = None
                if bg.spawnGroup:
                    for sg in self.zone.zone.spawnGroups:
                        if sg.groupName == bg.spawnGroup:
                            override = sg
                            break

                    for sp in self.zone.spawnpoints:
                        if sp.groupName == bg.triggerSpawnGroup:
                            mob = sp.triggeredSpawn(override)
                            if mob:
                                self.battleGroups[bg].append(mob)
                                self.mobs.append(mob)
                                mob.battle = self.battle

            self.sequence = sequence.nextSequence
            return

    def updateMobTarget(self, mob):
        if mob.target:
            return
        oside = self.battle.side1
        if oside == self:
            oside = self.battle.side2
        x = len(oside.mobs)
        if x:
            if x > 1:
                x = random.randint(0, x - 1)
            else:
                x = 0
            target = oside.mobs[x]
            if target and not target.detached:
                if target not in mob.aggro.keys():
                    mob.addAggro(target, 10)

    def tick(self):
        if self.delay:
            self.delay -= 3
            if self.delay <= 0:
                self.delay = 0
                self.triggerSequence()
        if not len(self.battleGroups):
            if not self.sequence:
                return True
            self.delay = self.sequence.delay + 3
        else:
            self.thinkTimer -= 3
            if self.thinkTimer <= 0:
                self.thinkTimer = 18
                for bg, mobs in self.battleGroups.iteritems():
                    if bg.passive:
                        continue
                    if self.battleGroupAttackTimers.get(bg) > 0:
                        self.battleGroupAttackTimers[bg] -= 18
                    if self.battleGroupAttackTimers.get(bg) <= 0:
                        for mob in mobs:
                            self.updateMobTarget(mob)

        return False

    def detachMob(self, mob):
        for bg, mobs in self.battleGroups.iteritems():
            if mob in mobs:
                mobs.remove(mob)
                self.mobs.remove(mob)
                if not len(mobs):
                    del self.battleGroups[bg]
                return True

        return False


class Battle():

    def __init__(self, zone, bproto):
        self.over = False
        self.forfeit = False
        self.name = bproto.name
        self.zone = zone
        zone.battles.append(self)
        self.battleProto = bproto
        side1 = self.side1 = BattleSide()
        side2 = self.side2 = BattleSide()
        side1.battle = self
        side2.battle = self
        s1seq = bproto.side1StartSequence
        s2seq = bproto.side2StartSequence
        if not s1seq or not s2seq:
            traceback.print_stack()
            print 'AssertionError: battle %s is missing a start sequence!' % self.name
            return
        side1.zone = zone
        side2.zone = zone
        side1.sequence = s1seq
        side2.sequence = s2seq
        side1.delay = s1seq.delay + 3
        side2.delay = s2seq.delay + 3
        self.battleMustSurvive = []
        for ms in bproto.battleMustSurvive:
            self.battleMustSurvive.append(ms.name)

        if bproto.zoneMessage:
            ZoneMessage(zone, bproto.zoneMessage)
        if bproto.zoneSound:
            ZoneSound(zone, bproto.zoneSound)

    def detachMob(self, mob):
        forfeit = False
        if mob.spawn.name in self.battleMustSurvive and not self.forfeit:
            ZoneMessage(self.zone, '%s has been slain!!!' % mob.spawn.name)
            forfeit = self.forfeit = True
        if self.side1.detachMob(mob):
            if forfeit:
                self.side1.forfeit = True
        if self.side2.detachMob(mob):
            if forfeit:
                self.side2.forfeit = True

    def end(self):
        self.over = True
        self.zone.battles.remove(self)
        for m in self.side1.mobs:
            m.despawnTimer = 3600

        for m in self.side2.mobs:
            m.despawnTimer = 3600

    def updateMobTarget(self, mob):
        if mob in self.side1.mobs:
            self.side1.updateMobTarget(mob)
        else:
            self.side2.updateMobTarget(mob)

    def doResult(self, result):
        if result.zoneMessage:
            ZoneMessage(self.zone, result.zoneMessage)
        if result.zoneSound:
            ZoneSound(self.zone, result.zoneSound)
        override = None
        if result.spawnGroup:
            for sg in self.zone.zone.spawnGroups:
                if sg.groupName == result.spawnGroup:
                    override = sg
                    break

            for sp in self.zone.spawnpoints:
                if sp.groupName == result.triggerSpawnGroup:
                    mob = sp.triggeredSpawn(override)
                    if mob:
                        mob.despawnTimer = 3600
                        mob.battle = self

        return

    def tick(self):
        end = False
        result = None
        if self.side1.tick() or self.side1.forfeit:
            end = True
            result = self.battleProto.side2VictoryResult
            for m in self.side1.mobs[:]:
                m.zone.removeMob(m)

        if self.side2.tick() or self.side2.forfeit:
            end = True
            result = self.battleProto.side1VictoryResult
            for m in self.side2.mobs[:]:
                m.zone.removeMob(m)

        if end:
            if result:
                self.doResult(result)
            self.end()
        return