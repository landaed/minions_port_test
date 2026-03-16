# Embedded file name: mud\world\cserveravatar.pyo
import urllib
from twisted.spread import pb
from mud.utils import *
from sqlobject import *
from mud.common.permission import User, Role
from mud.world.defines import *
from mud.world.player import Player
from mud.world.grants import GrantsProvider
from mud.world.zone import Zone
from mud.worldserver.charutil import ExtractPlayer, InstallCharacterBuffer, InstallPlayerBuffer
from item import Item, ItemProto, ItemInstance
from random import choice
from string import letters
from time import time as sysTime
import traceback

def GenPasswd(length = 8, chars = letters):
    return ''.join([ choice(chars) for i in xrange(length) ])


AVATAR = None
EXTRACT_TIMES = {}
TICK_COUNTER = 90
TICK_COUNTER_SLOW = 46

class CharacterServerAvatar(pb.Root):

    def __init__(self):
        global AVATAR
        from mud.world.theworld import World
        self.world = World.byName('TheWorld')
        AVATAR = self
        self.mind = None
        return

    def extractLoggingPlayer(player, save = True):
        if not AVATAR:
            return
        else:
            if save:
                if not player.party or not len(player.party.members):
                    return
                from mud.worldserver.charutil import PLAYER_BUFFERS
                for pname, pbuffer, cbuffer, cvalues in PLAYER_BUFFERS[:]:
                    if pname == player.publicName:
                        PLAYER_BUFFERS.remove((pname,
                         pbuffer,
                         cbuffer,
                         cvalues))

                player.backupItems()
                publicName, pbuffer, cbuffer, cvalues = ExtractPlayer(player.publicName, player.id, player.party.members[0].id, False)
                pbuffer = safe_encode(pbuffer)
                cbuffer = safe_encode(cbuffer)
                publicName = player.publicName
                player.destroySelf()
                try:
                    user = User.byName(publicName)
                    for r in user.roles:
                        r.removeUser(user)

                    user.destroySelf()
                except:
                    pass

                AVATAR.mind.callRemote('savePlayerBuffer', publicName, pbuffer, cbuffer, cvalues, True)
            else:
                AVATAR.mind.callRemote('savePlayerBuffer', player.publicName, None, None, None, True, False)
            return

    extractLoggingPlayer = staticmethod(extractLoggingPlayer)

    def gotGlobalPlayers(self, results):
        players, muted = results
        AVATAR.world.globalPlayers = players
        AVATAR.world.mutedPlayers = muted

    def tick():
        global TICK_COUNTER
        global TICK_COUNTER_SLOW
        if not AVATAR:
            return
        elif not AVATAR.mind:
            return
        elif AVATAR.world.shuttingDown:
            return
        else:
            try:
                now = sysTime()
                try:
                    from mud.worldserver.charutil import PLAYER_BUFFERS
                    for pname, pbuffer, cbuffer, cvalues in PLAYER_BUFFERS[:]:
                        pbuf = safe_encode(pbuffer)
                        cbuf = safe_encode(cbuffer)
                        print 'sending buffers for %s (pb=%d cb=%d)' % (pname, len(pbuf), len(cbuf))
                        AVATAR.mind.callRemote('savePlayerBuffer', pname, pbuf, cbuf, cvalues)
                        EXTRACT_TIMES[pname] = now
                        PLAYER_BUFFERS.remove((pname,
                         pbuffer,
                         cbuffer,
                         cvalues))

                except:
                    traceback.print_exc()

                TICK_COUNTER_SLOW -= 3
                if TICK_COUNTER_SLOW <= 0:
                    TICK_COUNTER_SLOW = 45
                    try:
                        for p in AVATAR.world.activePlayers:
                            if not p.zone or p.enteringWorld:
                                continue
                            pname = p.publicName
                            if p.didCheckGrants < 1 and EXTRACT_TIMES.has_key(pname):
                                if p.didCheckGrants < 0 or EXTRACT_TIMES[pname] < now - 10:
                                    AVATAR.checkGrants(p)
                                    p.didCheckGrants = 1

                    except:
                        traceback.print_exc()

                TICK_COUNTER -= 3
                if TICK_COUNTER > 0:
                    return
                TICK_COUNTER = 90
                pnames = []
                extractTarget = None
                best = 0
                for p in AVATAR.world.activePlayers:
                    if not p.zone or p.enteringWorld:
                        continue
                    pname = p.publicName
                    pnames.append(pname)
                    extractionTimer = EXTRACT_TIMES.setdefault(pname, now)
                    t = now - extractionTimer
                    if t < 600:
                        continue
                    if t > best:
                        best = t
                        extractTarget = pname

                remove = []
                for k in EXTRACT_TIMES.iterkeys():
                    if k not in pnames:
                        remove.append(k)

                map(EXTRACT_TIMES.__delitem__, remove)
                if extractTarget:
                    p = Player.byPublicName(extractTarget)
                    if p and p.party:
                        p.backupItems()
                        ExtractPlayer(p.publicName, p.id, p.party.members[0].id)
            except:
                traceback.print_exc()

            try:
                pnames = []
                for p in AVATAR.world.activePlayers:
                    cname = ''
                    if p.curChar:
                        cname = p.curChar.name
                    zname = ''
                    if p.zone:
                        zname = p.zone.zone.niceName
                    pnames.append((p.publicName,
                     cname,
                     p.guildName,
                     zname))

                d = AVATAR.mind.callRemote('recordActivePlayers', AVATAR.world.multiName, pnames)
                d.addCallback(AVATAR.gotGlobalPlayers)
                d.addErrback(lambda e: None)
            except:
                traceback.print_exc()

            return

    tick = staticmethod(tick)

    def createPlayer(self, publicName, code):
        password = GenPasswd().upper()
        zone = Zone.byName('trinst')
        dzone = Zone.byName('kauldur')
        mzone = Zone.byName('trinst')
        p = Player(publicName=publicName, password=password, fantasyName=publicName, logZone=zone, bindZone=zone, darknessLogZone=dzone, darknessBindZone=dzone, monsterLogZone=mzone, monsterBindZone=mzone)
        p.logTransformInternal = '17.699 -288.385 121.573 0 0 1 35.9607'
        p.bindTransformInternal = '17.699 -288.385 121.573 0 0 1 35.9607'
        p.darknessLogTransformInternal = '-203.48 -395.96 150.1 0 0 1 38.92'
        p.darknessBindTransformInternal = '-203.48 -395.96 150.1 0 0 1 38.92'
        p.monsterLogTransformInternal = '-169.032 -315.986 150.9353 0 0 1 10.681'
        p.monsterBindTransformInternal = '-169.032 -315.986 150.9353 0 0 1 10.681'
        user = User(name=publicName, password=password)
        user.addRole(Role.byName('Player'))
        if code == 2:
            user.addRole(Role.byName('Immortal'))
            user.addRole(Role.byName('Guardian'))
        elif code == 1:
            user.addRole(Role.byName('Guardian'))
        return p

    def remote_transferPlayerInstalled(self, publicName, charname, cbuffer, remoteLeaderName):
        p = Player.byPublicName(publicName)
        Player.remoteLeaderNames[publicName] = remoteLeaderName
        cbuffer = safe_decode(cbuffer)
        InstallCharacterBuffer(p.id, charname, cbuffer)
        return (True, p.password)

    def remote_kickPlayer(self, publicName):
        try:
            player = Player.byPublicName(publicName)
        except:
            return

        try:
            world = player.world
            world.kickPlayer(player)
        except:
            traceback.print_exc()

    def gotContestLevelUp(self, result, player, levelType, level):
        if result:
            try:
                player.sendGameText(RPG_MSG_GAME_LEVELGAINED, '\\nYou have been awarded a Halloween Raffle ticket for %s level %i!!!  You can view your current contest level matrix at: http://minions.prairiegames.com\\n' % (levelType, level))
            except:
                pass

    def doContestLevelUp(self, player, levelType, level):
        d = self.mind.callRemote('contestLevelUpEvent', player.publicName, levelType, level)
        d.addCallback(self.gotContestLevelUp, player, levelType, level)

    def gotGrants(self, grants, player):
        if grants is None:
            return
        else:
            try:
                loot = []
                lootids = []
                confirmed = []
                gaintext = ''
                failtext = ''
                for id, type, number, units in grants:
                    if type == 'money':
                        confirmed.append(id)
                        player.platinum += number
                        gaintext += 'You got %s: %d of %s.\\n' % (type, number, units)
                    elif type == 'text':
                        confirmed.append(id)
                        text = urllib.unquote(units)
                        gaintext += '%s\\n' % text
                    elif type == 'item':
                        try:
                            itemname = urllib.unquote(units)
                            if itemname.startswith('Bane '):
                                bane = itemname.split()
                                itemname = urllib.unquote(bane[2])
                            else:
                                bane = None
                            from crafting import FocusGenSpecific
                            item = FocusGenSpecific(itemname)
                            if not item:
                                proto = ItemProto.byName(itemname)
                                item = proto.createInstance()
                            if bane:
                                from mud.world.itemvariants import AddStatVariant, V_STAT, V_WEAPON, V_BANEWEAPON, GenVBaneWeapon, VBANEWEAPON_RACES, ApplyVBaneWeapon, VBANEWEAPON_TEXT, VBANEWEAPON_MODS
                                level = int(bane[1])
                                race = str(bane[3])
                                power = int(bane[4])
                                item.variants[V_BANEWEAPON] = (race, power)
                                item.wpnRaceBane = race
                                item.wpnRaceBaneMod = power
                                item.levelOverride = level
                                item.hasVariants = True
                                item.refreshFromProto()
                            item.stackCount = number
                            loot.append(item)
                            lootids.append(id)
                        except:
                            traceback.print_exc()

                    elif type == 'monster':
                        try:
                            name = urllib.unquote(units)
                            lowerSpawn = name.lower()
                            skip = 0
                            for monsterSpawn in player.monsterSpawns:
                                if monsterSpawn.spawn.lower() == lowerSpawn:
                                    failtext += 'You already have the %s monster template.\\n' % monsterSpawn.spawn
                                    skip = 1

                            if skip == 0:
                                from spawn import Spawn
                                mspawn = name
                                try:
                                    con = Spawn._connection.getConnection()
                                    spawn = Spawn.get(con.execute('SELECT id FROM spawn WHERE lower(name)="%s" LIMIT 1;' % lowerSpawn).fetchone()[0])
                                    mspawn = spawn.name
                                    from player import PlayerMonsterSpawn
                                    PlayerMonsterSpawn(player=player, spawn=name)
                                    gaintext += 'You now have the %s monster template.\\n' % mspawn
                                    confirmed.append(id)
                                except:
                                    traceback.print_exc()
                                    gaintext += 'No such spawn %s.\\n' % mspawn

                        except:
                            traceback.print_exc()

                if len(confirmed) > 0:
                    self.mind.callRemote('confirmGrants', player.publicName, confirmed)
                if len(loot) > 0:
                    gaintext += '%s, %d items are waiting for you.\\n' % (player.publicName, len(loot))
                    mob = GrantsProvider(player.publicName, loot, lootids)
                    player.startLooting(mob)
                if len(gaintext) > 0:
                    player.sendGameText(RPG_MSG_GAME_GAINED, gaintext)
                if len(failtext) > 0:
                    player.sendGameText(RPG_MSG_GAME_DENIED, failtext)
            except:
                traceback.print_exc()

            return

    def checkGrants(self, player):
        d = self.mind.callRemote('checkGrants', player.publicName)
        d.addCallback(self.gotGrants, player)

    def remote_installPlayer(self, publicName, pbuffer, code, premium, guildInfo):
        print 'installPlayer %s (%d) %s, guild <%s>' % (publicName,
         code,
         'premium' if premium else 'free',
         guildInfo[0])
        from mud.server.app import THESERVER
        pbuffer = safe_decode(pbuffer)
        if not THESERVER.allowConnections:
            return (False, 'This world is currently unavailable. Please try again in a few minutes.')
        for p in self.world.activePlayers[:]:
            if p.publicName == publicName:
                self.world.activePlayers.remove(p)

        try:
            p = Player.byPublicName(publicName)
            if p:
                p.destroySelf()
        except SQLObjectNotFound:
            pass
        except:
            traceback.print_exc()
            return (False, 'This world is busy. Please try again in a minute.')

        try:
            user = User.byName(publicName)
            for r in user.roles:
                r.removeUser(user)

            user.destroySelf()
        except:
            pass

        if pbuffer and pbuffer != 'None':
            error = InstallPlayerBuffer(publicName, pbuffer)
            if error:
                return (False, 'Error installing player buffer')
            try:
                p = Player.byPublicName(publicName)
                password = GenPasswd().upper()
                p.password = password
                user = User(name=publicName, password=password)
                user.addRole(Role.byName('Player'))
                if code == 2:
                    user.addRole(Role.byName('Immortal'))
                    user.addRole(Role.byName('Guardian'))
                elif code == 1:
                    user.addRole(Role.byName('Guardian'))
            except:
                traceback.print_exc()
                return (False, 'Error setting up installed player')

        else:
            try:
                p = self.createPlayer(publicName, code)
            except:
                traceback.print_exc()
                return (False, 'Error creating new player')

        p.premium = premium
        p.fantasyName = p.publicName
        p.guildName, p.guildInfo, p.guildMOTD, p.guildRank = guildInfo
        self.world.activePlayers.append(p)
        return (True, p.password)