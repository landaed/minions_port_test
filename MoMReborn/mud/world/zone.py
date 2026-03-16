# Embedded file name: mud\world\zone.pyo
from twisted.internet import reactor
from mud.common.persistent import Persistent
from mud.world.core import *
from mud.world.defines import *
from mud.world.mob import Mob
from mud.world.spawn import Spawnpoint
from mud.world.spell import Spell
from mud.world.weather import Weather
from mud.world.grants import GrantsProvider
from copy import copy
from itertools import repeat
from random import choice
from sqlobject import *
import string
from time import time as sysTime
import traceback

def GenPasswd(length = 8, chars = string.letters + string.digits):
    return ''.join([ choice(chars) for i in xrange(length) ])


class ZoneInstance():
    instanceCounter = 0

    def __init__(self, zone, ip, port, zonepassword, owningPlayer):
        self.zone = zone
        self.name = '%s_INSTANCE_%i' % (zone.name, ZoneInstance.instanceCounter)
        self.xpMod = zone.xpMod
        ZoneInstance.instanceCounter += 1
        self.status = 'Launching'
        self.dedicated = not owningPlayer
        self.owningPlayer = owningPlayer
        self.ip = ip
        self.port = port
        self.password = zonepassword
        self.time = None
        self.simAvatar = None
        self.players = []
        self.mobLookup = {}
        self.spawnpoints = None
        self.live = False
        self.activeMobs = []
        self.spawnedMobs = []
        self.playerQueue = {}
        self.playerPasswords = {}
        self.tickRootInfo = None
        self.rootInfoTick()
        self.weather = Weather(self.zone)
        self.bindpoints = []
        self.projectiles = {}
        self.dialogTriggers = []
        self.dynamic = False
        self.timeOut = -1
        self.stopped = False
        self.spawnpoints = []
        self.battles = []
        self.paused = False
        self.charTickCounter = 4
        self.pid = None
        self.populatorGroups = {}
        self.spawnIndex = 0
        self.allSpawnsTicked = False
        return

    def failure(self, error):
        print error

    def playerEnterZone(self, player):
        if not player.world:
            print 'WARNING: Player Entering Zone not attached to world... probably lost connection to world while zoning in'
            return
        player.zone.simAvatar.setDisplayName(player)
        if player.role.name not in ('Guardian', 'Immortal'):
            if player.enteringWorld:
                for p in self.players:
                    p.sendGameText(RPG_MSG_GAME_BLUE, '%s has entered the zone.\\n' % player.charName)

                for p in player.world.activePlayers:
                    if p == player:
                        continue
                    if p.enteringWorld:
                        continue
                    if p in self.players:
                        continue
                    p.sendGameText(RPG_MSG_GAME_BLUE, '%s has entered the world.\\n' % player.charName)

            else:
                pmob = player.curChar.mob
                for p in self.players:
                    if AllowHarmful(pmob, p.curChar.mob):
                        continue
                    p.sendGameText(RPG_MSG_GAME_BLUE, '%s has entered the zone.\\n' % player.charName)

        player.enteringWorld = False
        try:
            del self.playerQueue[player]
        except KeyError:
            pass

        if sysTime() - player.encounterPreserveTimer < 300:
            player.mind.callRemote('checkEncounterSetting', True)
        player.encounterPreserveTimer = 0
        player.encounterSetting = RPG_ENCOUNTER_PVE
        self.players.append(player)
        for c in player.party.members:
            mob = c.mob
            self.mobLookup[player.simObject] = mob
            mob.simObject = player.simObject
            self.activeMobs.append(mob)
            if c.dead:
                self.detachMob(mob)

        if CoreSettings.MAXPARTY == 1:
            player.world.setDeathMarker(player, player.party.members[0])
        player.world.sendCharacterInfo(player)

    def connectPlayer(self, result, player, zconnect):
        if player and player.mind:
            player.mind.callRemote('connect', zconnect, player.fantasyName)

    def connectQueuedPlayers(self, result):
        for p, z in self.playerQueue.iteritems():
            self.connectPlayer(None, p, z)

        self.playerQueue.clear()
        return

    def submitPlayer(self, player, zconnect):
        player.zone = self
        pw = GenPasswd()
        self.playerPasswords[player.publicName] = pw
        zconnect.playerZoneConnectPassword = pw
        self.playerQueue[player] = zconnect
        if not self.live:
            if CoreSettings.SINGLEPLAYER:
                player.mind.callRemote('createServer', zconnect)
        else:
            d = self.simAvatar.setPlayerPasswords(self.playerPasswords)
            d.addCallback(self.connectPlayer, player, zconnect)

    def start(self):
        if not self.simAvatar:
            traceback.print_stack()
            print "AssertionError: simAvatar doesn't exist!"
            return
        self.live = True
        d = self.simAvatar.setPlayerPasswords(self.playerPasswords)
        d.addCallback(self.connectQueuedPlayers)

    def stop(self):
        if self.stopped:
            return
        self.stopped = True
        print 'stopping zone %s' % self.name
        self.weather.cancel()
        try:
            self.tickRootInfo.cancel()
        except:
            pass

        map(self.removeMob, list((mob for mob in self.activeMobs if not mob.master)))
        self.simAvatar.stop()

    def createSpawnpoints(self, spinfos):
        self.spawnpoints = [ Spawnpoint(self, si.transform, si.group, si.wanderGroup) for si in spinfos ]

    def mobBotSpawned(self, simObject, mob):
        self.mobLookup[simObject] = mob
        mob.simObject = simObject
        self.activeMobs.append(mob)
        self.spawnedMobs.remove(mob)
        mob.spawned()

    def spawnMob(self, spawn, transform, wanderGroup, master = None, sizemod = 1.0):
        mob = Mob(spawn, self, None, None, master, sizemod)
        self.spawnedMobs.append(mob)
        d = self.simAvatar.spawnBot(spawn, transform, wanderGroup, mob.mobInfo)
        d.addCallback(self.mobBotSpawned, mob)
        self.world.cpuSpawn -= 1
        return mob

    def tick(self, spawnZone = None):
        self.charTickCounter -= 1
        try:
            if self.world.paused:
                if not self.paused:
                    self.paused = True
                    self.simAvatar.pause(True)
                if not self.charTickCounter:
                    self.charTickCounter = 5
                return
            if self.paused:
                self.simAvatar.pause(False)
                self.paused = False
            if not self.allSpawnsTicked and self.spawnpoints and len(self.spawnpoints):
                self.world.cpuSpawn = 1000000
                self.world.cpuDespawn = 1000000
                self.allSpawnsTicked = True
                for s in self.spawnpoints:
                    try:
                        s.tick()
                    except:
                        traceback.print_exc()

                self.world.cpuSpawn = 0
                self.world.cpuDespawn = 0
            if spawnZone == self and self.allSpawnsTicked:
                if self.spawnpoints and len(self.spawnpoints) > 0:
                    start = self.spawnIndex
                    while self.world.cpuSpawn > 0 and self.world.cpuDespawn > 0:
                        s = self.spawnpoints[self.spawnIndex]
                        go = True
                        if len(s.activeMobs) and s.activeInfo and (s.activeInfo.startTime == -1 or s.activeInfo.endTime == -1):
                            if not s.activeInfo.startDayRL or not s.activeInfo.endDayRL:
                                go = False
                        if go:
                            try:
                                s.tick()
                            except:
                                traceback.print_exc()

                        self.spawnIndex += 1
                        if self.spawnIndex == len(self.spawnpoints):
                            self.spawnIndex = 0
                        if start == self.spawnIndex:
                            break

            for mob in self.mobLookup.itervalues():
                if mob.detached and mob.kingTimer > 0:
                    mob.kingTimer -= 3

            for b in reversed(self.battles):
                b.tick()

            if len(self.players):
                for mob in reversed(self.activeMobs):
                    mob.tick()

            if self.weather.dirty and self.simAvatar:
                self.simAvatar.sendWeather(self.weather)
                self.weather.dirty = False
            for p in self.players:
                try:
                    p.tick()
                    dirty = p.cinfoDirty
                    if not self.charTickCounter:
                        if not p.party or not p.party.members or not len(p.party.members):
                            continue
                        for c in p.party.members:
                            if dirty:
                                c.charInfo.refresh()
                            else:
                                c.charInfo.refreshLite(True)

                except:
                    traceback.print_exc()

        except:
            traceback.print_exc()

        if not self.charTickCounter:
            self.charTickCounter = 5

    def rootInfoTick(self):
        for p in self.players:
            try:
                if p.rootInfo:
                    p.rootInfo.tick()
            except:
                traceback.print_exc()

        self.tickRootInfo = reactor.callLater(0.5, self.rootInfoTick)

    def setTarget(self, mob, target, checkVisibility = False):
        if target and target.detached:
            target = None
        if target == mob.target:
            return
        else:
            if target:
                if mob.detached:
                    return
                if checkVisibility and (mob.player or mob.master and mob.master.player) and not IsVisible(mob, target):
                    return
            mob.setTarget(target)
            if not mob.player:
                if target:
                    self.simAvatar.setTarget(mob.simObject, target.simObject)
                elif mob.detached:
                    self.simAvatar.immobilize(mob.simObject)
                else:
                    self.simAvatar.clearTarget(mob.simObject)
            else:
                for index, c in enumerate(mob.player.party.members):
                    if c.mob == mob:
                        break

                if target:
                    d = self.simAvatar.mind.callRemote('setSelection', mob.simObject.id, target.simObject.id, index)
                else:
                    d = self.simAvatar.mind.callRemote('setSelection', mob.simObject.id, 0, index)
                d.addErrback(lambda e: None)
            return

    def setFollowTarget(self, mob, target):
        if mob.player:
            return
        else:
            if target:
                if mob.detached:
                    return
                if target.detached:
                    target = None
            mob.setFollowTarget(target)
            if target:
                self.simAvatar.setFollowTarget(mob.simObject, target.simObject)
            else:
                self.simAvatar.setFollowTarget(mob.simObject, None)
            return

    def setTargetById(self, mob, mobId):
        if mob.detached:
            return
        else:
            if mobId == 0:
                self.setTarget(mob, None)
            for m in self.activeMobs:
                if mobId == m.id:
                    self.setTarget(mob, m)
                    break

            return

    def select(self, srcSimObject, tgtSimObject, charIndex, doubleClick, modifier_shift):
        mob = self.mobLookup[srcSimObject]
        player = mob.player
        if not player:
            traceback.print_stack()
            print 'AssertionError: mob is no player mob!'
            return
        else:
            mob = player.party.members[charIndex].mob
            if mob.detached:
                player.sendGameText(RPG_MSG_GAME_DENIED, '%s is no longer of this world and cannot interact with it.\\n' % mob.name)
            target = self.mobLookup[tgtSimObject]
            if modifier_shift:
                player.avatar.sendTgtDesc(mob, target)
                return
            if target.detached and not target.player:
                try:
                    kk = target.kingKiller
                    if kk and kk.player and target.kingTimer > 0:
                        cmobs = [ m.mob for m in kk.player.party.members ]
                        for a in kk.player.alliance.members:
                            for m in a.party.members:
                                cmobs.append(m.mob)

                        if mob not in cmobs:
                            player.sendGameText(RPG_MSG_GAME_LOOT, 'You cannot loot this corpse at this time.\\n')
                            return
                except:
                    traceback.print_exc()

                if target.genLoot and target.loot:
                    target.genLoot = False
                    if not target.loot.generateCorpseLoot():
                        target.loot = None
                if player.realm == RPG_REALM_MONSTER and target.spawn.race not in ('Undead', 'Golem'):
                    if target.loot and not target.loot.fleshDone and len(target.loot.items) < 16:
                        from item import ItemProto
                        fproto = ItemProto.byName('Flesh and Blood')
                        flesh = fproto.createInstance()
                        flesh.slot = -1
                        target.loot.items.append(flesh)
                        target.loot.fleshDone = True
                if not target.loot or not len(target.loot.items):
                    if target.loot:
                        target.loot.giveMoney(player)
                    player.sendGameText(RPG_MSG_GAME_LOOT, 'The corpse crumbles to dust!\\n')
                    self.removeMob(target)
                    return
                if target.master and target.master.player:
                    player.sendGameText(RPG_MSG_GAME_LOOT, 'You cannot loot player pets.\\n')
                    return
                if target.looter and target.looter != mob.player:
                    player.sendGameText(RPG_MSG_GAME_LOOT, '%s is already looting the corpse.\\n' % target.looter.curChar.name)
                    return
                if target.looter == player:
                    return
                if player.looting:
                    player.looting.looter = None
                    player.looting = None
                player.startLooting(target)
                return False
            if target.player:
                for c in target.player.party.members:
                    if not c.dead:
                        target = c.mob
                        break

            self.setTarget(mob, target, checkVisibility=True)
            if doubleClick:
                player.avatar.perspective_doCommand('INTERACT', [mob.player.curChar.mob.charIndex])
            player.mind.callRemote('mouseSelect', charIndex, target.id)
            return True

    def reattachMob(self, mob):
        if not mob.detached:
            traceback.print_stack()
            print 'AssertionError: mob is not detached!'
            return
        else:
            mob.detached = False
            if mob.character:
                for store in mob.character.spellStore:
                    if not mob.character.dead:
                        restoreSpell = Spell(mob, mob, store.spellProto, store.mod, store.time, None, False, True, store.level)
                        restoreSpell.healMod = store.healMod
                        restoreSpell.damageMod = store.damageMod
                        mob.processesPending.add(restoreSpell)
                    store.destroySelf()

            self.activeMobs.append(mob)
            return

    def detachMob(self, mob):
        if mob.detached:
            return
        else:
            mob.detachSelf()
            try:
                self.activeMobs.remove(mob)
            except ValueError:
                pass

            map(Mob.detachMob, self.activeMobs, repeat(mob, len(self.activeMobs)))
            if mob.interacting:
                mob.interacting.endInteraction()
            self.setTarget(mob, None)
            if not mob.player:
                mob.setFollowTarget(None)
                if not self.stopped:
                    self.simAvatar.setFollowTarget(mob.simObject, None)
            return

    def removeMob(self, mob, despawnTime = 0):
        if isinstance(mob, GrantsProvider):
            if mob.looter:
                mob.looter.looting = None
                try:
                    mob.looter.mind.callRemote('setLoot', {}, 'grants')
                except:
                    pass

            if mob.loot:
                for item in mob.loot.items:
                    item.destroySelf()

            return
        else:
            if mob.master and mob.master.player:
                mob.master.character.petHealthBackup = mob.health
                mob.master.character.petHealthTimer = int(sysTime())
            if mob.corpseRemoval:
                mob.corpseRemoval.cancel()
                mob.corpseRemoval = None
            if mob.spawnpoint:
                mob.spawnpoint.removeMob(despawnTime)
            mob.kingKiller = None
            if not mob.detached:
                self.detachMob(mob)
            if mob.looter:
                mob.looter.looting = None
                try:
                    mob.looter.mind.callRemote('setLoot', {})
                except:
                    pass

            if mob.loot:
                mob.loot.mob = None
                for item in mob.loot.items:
                    item.destroySelf()

            if not mob.player:
                try:
                    self.simAvatar.deleteObject(mob.simObject)
                except:
                    pass

                try:
                    del self.mobLookup[mob.simObject]
                except KeyError:
                    pass

            mob.simObject = None
            self.world.cpuDespawn -= 1
            return

    def removePlayer(self, player):
        if player in self.players:
            self.players.remove(player)
        for c in player.party.members:
            try:
                del self.mobLookup[c.mob.simObject]
            except KeyError:
                pass

            self.detachMob(c.mob)
            self.removeMob(c.mob)
            c.mob.character = None
            c.mob.player = None
            c.mob = None

        if self.simAvatar:
            self.simAvatar.removePlayer(player.simObject)
        player.simObject = None
        return

    def playerRespawned(self, result, args):
        player = args[0]
        for c in player.party.members:
            if not c.dead and c.mob.detached:
                self.reattachMob(c.mob)

    def respawnPlayer(self, player, transform = None):
        for char in player.party.members:
            mob = char.mob
            if not mob.detached:
                if mob.interacting:
                    mob.interacting.endInteraction()
                for otherMob in self.activeMobs:
                    if otherMob.followTarget == mob and otherMob.master != mob:
                        self.setFollowTarget(otherMob, None)

        self.simAvatar.respawnPlayer(player, transform).addCallback(self.playerRespawned, (player,))
        return

    def projectileCollision(self, pid, hitObj, hitPos):
        if self.mobLookup.has_key(hitObj):
            proj = self.projectiles[pid]
            proj.dst = self.mobLookup[hitObj]
            proj.onCollision(hitPos)

    def onImpact(self, simObject, velocity):
        mob = self.mobLookup.get(simObject, None)
        if mob:
            if not mob.player:
                return
            if mob.player:
                for c in mob.player.party.members:
                    c.mob.onImpact(velocity)

        return

    def deleteProjectile(self, pid):
        del self.projectiles[pid]

    def launchProjectile(self, p):
        self.projectiles[p.id] = p
        self.simAvatar.launchProjectile(p)

    def setDialogTriggers(self, tinfos):
        from dialog import DialogTrigger
        self.dialogTriggers = [ DialogTrigger(t) for t in tinfos ]

    def kickPlayer(self, player):
        self.simAvatar.kickPlayer(player)

    def setDeathMarker(self, publicName, charName, realm, pos, rot):
        self.simAvatar.setDeathMarker(publicName, charName, realm, pos, rot)

    def clearDeathMarker(self, publicName):
        self.simAvatar.clearDeathMarker(publicName)


class ZoneLink(Persistent):
    name = StringCol(alternateID=True)
    dstZoneName = StringCol()
    dstZoneTransform = StringCol()


class TempZoneLink():

    def __init__(self, dstZoneName, dstZoneTransform):
        self.dstZoneName = dstZoneName
        self.dstZoneTransform = dstZoneTransform


class Zone(Persistent):
    name = StringCol(alternateID=True)
    niceName = StringCol()
    missionFile = StringCol()
    climate = IntCol(default=RPG_CLIMATE_TEMPERATE)
    xpMod = FloatCol(default=1.0)
    aggroMod = FloatCol(default=1.0)
    scaleLimit = FloatCol(default=20.0)
    immTransform = StringCol(default='0 0 0 1 0 0 0')
    allowGuest = BoolCol(default=False)
    spawnGroups = MultipleJoin('SpawnGroup')
    world = ForeignKey('World')