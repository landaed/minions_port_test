# Embedded file name: mud\world\theworld.pyo
from twisted.internet import reactor
from mud.utils import *
from mud.common.persistent import Persistent
from mud.world.core import *
from mud.world.cserveravatar import CharacterServerAvatar
from mud.world.defines import *
from mud.gamesettings import *
from mud.world.zone import TempZoneLink, Zone, ZoneInstance
from mud.world.shared.worlddata import ZoneOption
from mud.worldserver.charutil import ExtractPlayer
import mud.world.guardianavatar
import mud.world.immortalavatar
import mud.world.statsavatar
from copy import copy
from datetime import datetime
import os, sys, shutil
from sqlobject import *
from time import time as sysTime
import traceback

class Time():

    def __init__(self):
        self.second = 0
        self.minute = 15
        self.hour = 12
        self.day = 0
        self.ticks = 0
        self.lasttime = -1

    def tick(self):
        if self.lasttime == -1:
            self.lasttime = sysTime()
        delta = sysTime() - self.lasttime
        self.lasttime = sysTime()
        self.ticks += 3
        self.second += delta * 24.0
        if self.second > 59:
            self.second -= 59
            self.minute += 1
            if self.minute > 59:
                self.minute = 0
                self.hour += 1
                if self.hour > 23:
                    self.hour = 0
                    self.day += 1


class World(Persistent):
    name = StringCol(alternateID=True, default='TheWorld')
    allowGuests = BoolCol(default=True)
    pwNewPlayer = StringCol(default='')
    pwCreateZone = StringCol(default='')
    maxLiveZones = IntCol(default=1024)
    maxLivePlayers = IntCol(default=4096)
    second = IntCol(default=0)
    minute = IntCol(default=15)
    hour = IntCol(default=12)
    day = IntCol(default=0)
    ticks = IntCol(default=0)
    zones = MultipleJoin('Zone')
    singlePlayer = BoolCol(default=False)
    aggroOn = BoolCol(default=True)
    genesisTime = DateTimeCol(default=datetime.now)

    def _init(self, *args, **kw):
        Persistent._init(self, *args, **kw)
        self.shuttingDown = False
        self.liveZoneInstances = []
        self.waitingZoneInstances = []
        self.activePlayers = []
        self.globalPlayers = {}
        self.mutedPlayers = {}
        self.time = Time()
        self.time.second = 0
        self.time.minute = self.minute
        self.time.hour = self.hour
        self.time.day = self.day
        self.time.ticks = 0
        self.lasttime = -1
        self.transaction = None
        self.tickTransaction = None
        self.singlePlayer = False
        self.liveZoneCallback = None
        self.usedZonePorts = []
        self.running = False
        self.dbFile = None
        self.backupTick = 30
        self.paused = False
        self.pauseTime = sysTime()
        self.daemonPerspective = None
        self.daemonMind = None
        self.clusterNum = -1
        self.worldPort = -1
        self.staticZoneNames = []
        self.priority = 1
        self.deathMarkers = {}
        self.characterInfos = {}
        self.allowConnections = True
        self.cpuSpawn = 0
        self.cpuDespawn = 0
        self.spawnZoneIndex = 0
        self.isShuttingDown = False
        return

    def tick(self):
        if not self.running:
            return
        else:
            reactor.callLater(0.5, self.tick)
            self.time.tick()
            if self.time.hour != self.hour:
                self.minute = self.time.minute
                self.hour = self.time.hour
                self.day = self.time.day
            CharacterServerAvatar.tick()
            if self.isShuttingDown:
                self.cpuSpawn = 0
                self.cpuDespawn = 0
            else:
                self.cpuSpawn = 4
                self.cpuDespawn = 8
            spawnZone = None
            if len(self.liveZoneInstances) > 0:
                if self.spawnZoneIndex > len(self.liveZoneInstances) - 1:
                    self.spawnZoneIndex = 0
                spawnZone = self.liveZoneInstances[self.spawnZoneIndex]
                self.spawnZoneIndex += 1
            for z in self.liveZoneInstances:
                z.tick(spawnZone)

            if not self.singlePlayer:
                timedOut = []
                for z in self.liveZoneInstances:
                    if not z.dynamic:
                        continue
                    if not len(z.players) and not len(z.playerQueue):
                        if z.timeOut == -1:
                            z.timeOut = sysTime()
                        elif (sysTime() - z.timeOut) / 60 > 20:
                            timedOut.append(z)
                    else:
                        z.timeOut = -1

                for z in timedOut:
                    self.closeZone(z)

            return

    def commit(self, commitOnly = False):
        if self.tickTransaction:
            self.tickTransaction.cancel()
        self.transactionTick(commitOnly)

    def transactionTick(self, commitOnly = False):
        if self.transaction:
            self.transaction.commit()
            self.transaction = None
        if not commitOnly and self.dbFile:
            self.backupTick -= 1
            if self.backupTick < 0:
                self.backupTick = 30
                BackupWorld(self.dbFile)
                if not self.singlePlayer:
                    tick_log()
        self.transaction = Persistent._connection.transaction()
        delay = 600 if self.singlePlayer else 60
        self.tickTransaction = reactor.callLater(delay, self.transactionTick)
        return

    def startup(self):
        from mud.world.archetype import InitClassSkills
        from mud.world.faction import InitKOS
        from mud.world.loot import Loot
        from mud.world.mobspells import InitMobSpells
        InitClassSkills()
        InitKOS()
        Loot.initRandomLoot()
        InitMobSpells()
        self.running = True

    def shutdown(self):
        if self.running:
            self.running = False
            for p in self.activePlayers[:]:
                p.logout()

            self.activePlayers = []
            self.shuttingDown = True
            if self.tickTransaction:
                self.tickTransaction.cancel()
                self.tickTransaction = None
            if self.transaction:
                self.transaction.commit()
                self.transaction = None
        return

    def playerJoinWorld(self, player):
        if player not in self.activePlayers:
            print 'playerJoinWorld: added %s to active players' % player.publicName
            for p in self.activePlayers:
                pass

            self.activePlayers.append(player)
        player.world = self
        player.zone = None
        player.enteringWorld = True
        if self.daemonPerspective:
            self.daemonPerspective.callRemote('playerJoinedWorld', player.publicName)
        return

    def playerLeaveWorld(self, player):
        zones = copy(self.liveZoneInstances)
        zones.extend(self.waitingZoneInstances)
        if self.daemonPerspective:
            self.daemonPerspective.callRemote('playerLeftWorld', player.publicName, player.transfering)
        if CoreSettings.MAXPARTY == 1 and not player.transfering:
            self.clearDeathMarker(player)
        for zinst in zones:
            if player == zinst.owningPlayer:
                self.closeZone(zinst)

        player.zone = None
        if player in self.activePlayers:
            self.activePlayers.remove(player)
        if player.extract:
            CharacterServerAvatar.extractLoggingPlayer(player, not player.enteringWorld)
        if self.singlePlayer:
            self.shutdown()
        return

    def playerJumped(self, result, player):
        player.extract = False
        try:
            player.mind.broker.transport.loseConnection()
        except:
            pass

        if player.avatar:
            player.avatar.logout()

    def playerTransfered(self, result, party, player):
        wip, wport, wpassword, zport, zpassword = result
        d = player.mind.callRemote('jumpServer', wip, wport, wpassword, zport, zpassword, party)
        d.addCallback(self.playerJumped, player)
        d.addErrback(self.playerJumped, player)

    def onZoneTrigger(self, player, zoneLink):
        zoneName = zoneLink.dstZoneName
        if player.trade:
            player.trade.cancel()
        if self.singlePlayer:
            pass
        else:
            if not self.allowConnections:
                if player.darkness:
                    player.darknessLogTransformInternal = zoneLink.dstZoneTransform
                    player.darknessLogZone = Zone.byName(zoneLink.dstZoneName)
                elif player.monster:
                    player.monsterLogTransformInternal = zoneLink.dstZoneTransform
                    player.monsterLogZone = Zone.byName(zoneLink.dstZoneName)
                else:
                    player.logTransformInternal = zoneLink.dstZoneTransform
                    player.logZone = Zone.byName(zoneLink.dstZoneName)
                player.backupItems()
                publicName, pbuffer, cbuffer, cvalues = ExtractPlayer(player.publicName, player.id, player.party.members[0].id, False)
                pbuffer = safe_encode(pbuffer)
                cbuffer = safe_encode(cbuffer)
                player.transfering = True
                from mud.world.cserveravatar import AVATAR
                AVATAR.mind.callRemote('savePlayerBuffer', publicName, pbuffer, cbuffer, cvalues)
                player.extract = False
                self.kickPlayer(player)
                return
            if zoneName not in self.staticZoneNames:
                player.prepForZoneOut()
                player.zone.removePlayer(player)
                player.zone = None
                if player.darkness:
                    player.darknessLogTransformInternal = zoneLink.dstZoneTransform
                    player.darknessLogZone = Zone.byName(zoneLink.dstZoneName)
                elif player.monster:
                    player.monsterLogTransformInternal = zoneLink.dstZoneTransform
                    player.monsterLogZone = Zone.byName(zoneLink.dstZoneName)
                else:
                    player.logTransformInternal = zoneLink.dstZoneTransform
                    player.logZone = Zone.byName(zoneLink.dstZoneName)
                publicName, pbuffer, cbuffer, cvalues = ExtractPlayer(player.publicName, player.id, player.party.members[0].id, False)
                pbuffer = safe_encode(pbuffer)
                cbuffer = safe_encode(cbuffer)
                player.transfering = True
                aname = player.publicName
                if player.alliance:
                    aname = player.alliance.remoteLeaderName
                else:
                    print 'Warning: Player %s has no alliance on zone trigger, could mess up alliances!!!!!' % player.publicName
                from mud.world.cserveravatar import AVATAR
                guildInfo = (player.guildName,
                 player.guildInfo,
                 player.guildMOTD,
                 player.guildRank)
                d = AVATAR.mind.callRemote('zoneTransferPlayer', player.publicName, pbuffer, player.party.members[0].name, cbuffer, zoneName, cvalues, aname, guildInfo)
                d.addCallback(self.playerTransfered, [player.party.members[0].name], player)
                return
        zone = Zone.byName(zoneName)
        if self.singlePlayer:
            self.closeZone(player.zone)
        allzi = []
        allzi.extend(self.liveZoneInstances)
        allzi.extend(self.waitingZoneInstances)
        zoptions = []
        if not self.singlePlayer:
            found = False
            for zi in allzi:
                if zi.zone == zone:
                    found = True
                    break

            if not found:
                print 'onZoneTrigger needs %s' % zoneName
                allzi.append(self.startZoneProcess(zoneName))
        for zi in allzi:
            if zi.zone == zone:
                zo = ZoneOption()
                zo.zoneName = zoneName
                zo.zoneInstanceName = zi.name
                if zi.owningPlayer:
                    zo.owner = zi.owningPlayer.fantasyName
                else:
                    zo.owner = None
                zo.status = zi.status
                zoptions.append(zo)

        player.prepForZoneOut()
        player.zone.removePlayer(player)
        player.zone = None
        player.triggeredZoneLink = zoneLink
        player.triggeredZoneOptions = zoptions
        player.mind.callRemote('setZoneOptions', zoptions)
        return

    def getPlayerZone(self, pavatar, simPort, simPassword):
        if self.shuttingDown:
            return
        else:
            player = pavatar.player
            allzi = []
            allzi.extend(self.liveZoneInstances)
            allzi.extend(self.waitingZoneInstances)
            if player.darkness:
                logZone = player.darknessLogZone
            elif player.monster:
                logZone = player.monsterLogZone
            else:
                logZone = player.logZone
            for z in allzi:
                if z.zone.name == logZone.name:
                    return z

            if self.singlePlayer:
                ip = '127.0.0.1'
                z = ZoneInstance(logZone, ip, simPort, simPassword, None)
                z.world = self
                z.time = self.time
                self.waitingZoneInstances.append(z)
                return z
            raise AssertionError, "error, zone %s isn't up!" % logZone.name
            return

    def playerSelectZone(self, pavatar, simPort, simPassword):
        if self.shuttingDown:
            return None
        else:
            return self.getPlayerZone(pavatar, simPort, simPassword)

    def closeZone(self, zinst):
        try:
            if zinst in self.liveZoneInstances:
                self.liveZoneInstances.remove(zinst)
            if zinst in self.waitingZoneInstances:
                self.waitingZoneInstances.remove(zinst)
            zinst.stop()
            if zinst.port in self.usedZonePorts:
                self.usedZonePorts.remove(zinst.port)
        except:
            traceback.print_exc()

    def closePlayerZone(self, player):
        for zinst in self.liveZoneInstances:
            if zinst.owningPlayer == player:
                self.closeZone(zinst)
                break

        for zinst in self.waitingZoneInstances:
            if zinst.owningPlayer == player:
                self.closeZone(zinst)
                break

    def startSimulation(self, zoneInstanceName, pid):
        zinst = None
        for z in self.waitingZoneInstances:
            if z.name == zoneInstanceName:
                zinst = z
                break

        if not zinst:
            traceback.print_stack()
            print 'AssertionError: zinst is empty!'
            return
        else:
            zinst.pid = pid
            self.waitingZoneInstances.remove(zinst)
            self.liveZoneInstances.append(zinst)
            zinst.status = 'Live'
            if self.liveZoneCallback:
                self.liveZoneCallback(zinst)
            if self.daemonPerspective:
                zpid = []
                zport = []
                zpassword = []
                for zname in self.staticZoneNames:
                    for z in self.liveZoneInstances:
                        if zname == z.zone.name:
                            if z.pid == None:
                                traceback.print_stack()
                                print 'AssertionError: z.pid is empty!'
                                return
                            zpid.append(z.pid)
                            zpassword.append(z.password)
                            zport.append(z.port)

                self.daemonPerspective.callRemote('setZonePID', zpid, zport, zpassword)
            return zinst

    def spawnDedicatedZone(self, simAvatar, zoneName, simPort):
        if zoneName == 'any':
            znames = [ zone.name for zone in self.zones ]
            zinstances = []
            for zi in self.liveZoneInstances:
                zinstances.append(zi)

            for zi in self.waitingZoneInstances:
                zinstances.append(zi)

            for zi in zinstances:
                if zi.zone.name in znames:
                    znames.remove(zi.zone.name)

            if not len(znames):
                raise Warning, 'all zones served... eventually we serve another zone instance, based on waiting etc'
            zoneName = znames[0]
        else:
            for zi in self.waitingZoneInstances:
                if zi.port == simPort:
                    return zi

        traceback.print_stack()
        print "AssertionError: dedicated server launched remotely, shouldn't happen for now!"
        return
        zone = Zone.byName(zoneName)
        ip = self.zoneIP
        simPassword = ''
        z = ZoneInstance(zone, ip, simPort, simPassword, None)
        z.time = self.time
        self.waitingZoneInstances.append(z)
        return z

    def startZoneProcess(self, zoneName, dynamic = True):
        port = None
        for x in xrange(self.zoneStartPort, self.zoneStartPort + 100):
            if x in self.usedZonePorts:
                continue
            port = x
            self.usedZonePorts.append(x)
            break

        if port == None:
            traceback.print_stack()
            print 'AssertionError: no port assigned!'
            return
        else:
            zone = Zone.byName(zoneName)
            ip = self.zoneIP
            simPassword = ''
            z = ZoneInstance(zone, ip, port, simPassword, None)
            z.world = self
            z.time = self.time
            z.dynamic = dynamic
            self.waitingZoneInstances.append(z)
            args = './zoneserver.py -dedicated -serverport %i -zone %s -world %s -worldport %i' % (port,
             zoneName,
             self.multiName,
             self.worldPort)
            if dynamic:
                args += ' -dynamic'
            args += ' -cluster=%i' % self.clusterNum
            real_spawn(os.getcwd(), '', args)
            return z

    def getZoneByInstanceName(self, iname):
        for zi in self.liveZoneInstances:
            if zi.name == iname:
                return zi

        for zi in self.waitingZoneInstances:
            if zi.name == iname:
                return zi

        return None

    def reallySetDeathMarker(self, publicName, info):
        charName, realm, zoneName, pos, rot = info
        self.deathMarkers[publicName] = info
        for zi in self.liveZoneInstances:
            if zi.zone.name == zoneName:
                zi.setDeathMarker(publicName, charName, realm, pos, rot)
                return

    def reallyClearDeathMarker(self, publicName):
        if not self.deathMarkers.has_key(publicName):
            return
        del self.deathMarkers[publicName]
        for zi in self.liveZoneInstances:
            zi.clearDeathMarker(publicName)

    def setDeathMarkerInfo(self, info):
        for p in self.deathMarkers.keys():
            if p not in info:
                self.reallyClearDeathMarker(p)

        for pname, dm in info.items():
            charName, realm, zoneName, pos, rot = dm
            if pname in self.deathMarkers:
                if dm == self.deathMarkers[pname]:
                    continue
                self.reallyClearDeathMarker(pname)
                if zoneName in self.staticZoneNames:
                    self.reallySetDeathMarker(pname, dm)
            elif zoneName in self.staticZoneNames:
                self.reallySetDeathMarker(pname, dm)

    def clearDeathMarker(self, player):
        if not self.daemonPerspective:
            return
        try:
            self.daemonPerspective.callRemote('clearDeathMarker', player.publicName)
        except:
            traceback.print_exc()

    def setDeathMarker(self, player, character):
        if self.daemonPerspective:
            try:
                self.clearDeathMarker(player)
                if character.deathZone:
                    zoneName = character.deathZone.name
                    dt = character.deathTransform
                    realm = player.realm
                    charname = player.party.members[0].name
                    pos = (dt[0], dt[1], dt[2])
                    rot = (dt[3],
                     dt[4],
                     dt[5],
                     dt[6])
                    self.daemonPerspective.callRemote('setDeathMarker', player.publicName, charname, realm, zoneName, pos, rot)
            except:
                traceback.print_exc()

    def sendCharacterInfo(self, player):
        if self.daemonPerspective:
            try:
                c = player.party.members[0]
                s = c.spawn
                prefix = ''
                if player.avatar and player.avatar.masterPerspective:
                    if player.avatar.masterPerspective.avatars.has_key('GuardianAvatar'):
                        prefix = '(Guardian) '
                    if player.avatar.masterPerspective.avatars.has_key('ImmortalAvatar'):
                        prefix = '(Immortal) '
                cinfo = (prefix,
                 c.name,
                 s.realm,
                 s.pclassInternal,
                 s.sclassInternal,
                 s.tclassInternal,
                 s.plevel,
                 s.slevel,
                 s.tlevel,
                 player.zone.zone.niceName,
                 player.guildName)
                self.daemonPerspective.callRemote('setCharacterInfo', player.publicName, cinfo)
            except:
                traceback.print_exc()

    def onPlayerDeath(self, player):
        xpLoss = -1
        if len(player.party.members) > 1:
            xpLoss = 0
            for c in player.party.members:
                if c.xpDeathPrimary or c.xpDeathSecondary or c.xpDeathTertiary:
                    xpLoss = 1
                    break

        player.mind.callRemote('partyWipe', xpLoss)
        czone = player.zone.zone
        for c in player.party.members:
            c.dead = False
            c.mob.health = 1
            c.mob.mana = 1
            c.mob.stamina = 1

        if player.darkness:
            bzone = player.darknessBindZone
            btransform = player.darknessBindTransformInternal
        elif player.monster:
            bzone = player.monsterBindZone
            btransform = player.monsterBindTransformInternal
        else:
            bzone = player.bindZone
            btransform = player.bindTransformInternal
        if czone == bzone:
            player.zone.respawnPlayer(player)
        else:
            player.flushMessages()
            zlink = TempZoneLink(bzone.name, btransform)
            self.onZoneTrigger(player, zlink)

    def kickPlayer(self, player):
        player.loggingOut = True
        if player.zone:
            player.zone.kickPlayer(player)
        avatar = player.avatar
        player.logout()
        if avatar:
            if avatar.mind:
                avatar.mind.broker.transport.loseConnection()


def BackupWorld(worldfile):
    try:
        print '... backing up world database'
        n = datetime.now()
        s = n.strftime('%Y%m%d')
        d, f = os.path.split(worldfile)
        f, ext = os.path.splitext(f)
        backfolder = '%s/%s' % (d, s)
        if not os.path.exists(backfolder):
            os.makedirs(backfolder)
        i = 0
        while True:
            backupfile = '%s/%s_%i%s' % (backfolder,
             f,
             i,
             ext)
            if not os.path.exists(backupfile):
                shutil.copyfile(worldfile, backupfile)
                break
            i += 1

    except:
        traceback.print_exc()