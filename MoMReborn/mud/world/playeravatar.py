# Embedded file name: mud\world\playeravatar.pyo
from mud.common.avatar import Avatar
from mud.world.item import ItemInstance, Item
from mud.world.player import Player
from mud.world.character import Character, CharacterSpell, CharacterVaultItem
from mud.world.theworld import World
from mud.world.spawn import Spawn, SpawnResistance, SpawnStat
from mud.world.party import Party
from mud.world.spell import SpellClass, Spell
from mud.world.command import DoCommand
from mud.world.repair import RepairItem, RepairAll, RepairParty
from mud.world.zone import Zone
from mud.world.messages import GameMessage
from defines import *
from core import *
from sqlobject import *
from twisted.internet import reactor
from alliance import Alliance
import traceback
from time import time
from mud.worldserver.charutil import ExtractPlayer, InstallCharacterBuffer
from mud.gamesettings import *
from mud.utils import *
from mud.world.shared.worlddata import CharacterInfo, ZoneConnectionInfo
from mud.world.shared.playdata import RootInfo
from mud.world.shared.models import GetModelInfo

class PlayerAvatar(Avatar):

    def setup(self, username, role, mind):
        self.mind = mind
        self.username = username
        self.player = Player.byPublicName(username)
        self.player.role = role
        self.player.reset()
        self.player.mind = mind
        self.world = World.byName('TheWorld')
        self.player.world = self.world
        self.syncTime()
        self.player.avatar = self
        self.world.playerJoinWorld(self.player)
        self.charInfos = []

    def perspective_logout(self):
        self.logout()

    def logout(self):
        if not self.player:
            return
        else:
            player = self.player
            player.avatar = None
            if player.loggingOut:
                return
            if self.tickSyncTime:
                try:
                    self.tickSyncTime.cancel()
                except:
                    pass

                self.tickSyncTime = None
            player.loggingOut = True
            player.logout()
            player.loggingOut = False
            self.player = None
            return

    def failedSyncTime(self):
        print 'failedSyncTime %s - logout' % self.username
        self.logout()

    def syncTime(self):
        d = self.mind.callRemote('syncTime', self.world.time.hour, self.world.time.minute)
        d.addErrback(self.failedSyncTime)
        self.tickSyncTime = reactor.callLater(60, self.syncTime)

    def gotCheckCharacterName(self, result, newchar):
        if not result:
            return self.newCharacter(newchar)
        return (-1, 'That name is taken, please choose another')

    def gotCheckCharacterNameError(self, result):
        return (-1, 'There was an error creating this character')

    def perspective_newCharacter(self, newchar):
        if not self.player.premium:
            nc = 0
            names = []
            if self.player.cserverInfos:
                for cinfo in self.player.cserverInfos:
                    if cinfo.realm != RPG_REALM_MONSTER:
                        nc += 1
                        names.append(cinfo.name)

            for c in self.player.characters:
                if c.spawn.realm != RPG_REALM_MONSTER and c.spawn.name not in names:
                    nc += 1

            if nc >= 3:
                return (-1, 'You may have 3 characters in the Minions of Mirth Free Account.\nPremium Account allows up to 24 characters.\nPlease see www.prairiegames.com for more information.', None)
        from cserveravatar import AVATAR
        if AVATAR:
            d = AVATAR.mind.callRemote('checkCharacterName', newchar.name)
            d.addCallback(self.gotCheckCharacterName, newchar)
            d.addErrback(self.gotCheckCharacterNameError)
            return d
        else:
            return self.newCharacter(newchar)

    def newCharacter(self, newchar):
        print 'newCharacter %s' % newchar.name
        if not self.player.premium:
            if newchar.realm == RPG_REALM_DARKNESS or newchar.race not in RPG_DEMO_RACES:
                return (-1, 'Premium Account is required to use this character.\nPlease see www.prairiegames.com for more information.', None)
        if not self.player.world.singlePlayer:
            nc = 0
            if self.player.cserverInfos:
                nc = len(self.player.cserverInfos)
            for c in self.player.characters:
                if c.spawn.realm != RPG_REALM_MONSTER:
                    nc += 1

            if nc >= 24:
                return (-1, 'The maximum characters on this server is 24.', None)
        try:
            char = Character.byName(newchar.name)
        except:
            pass
        else:
            return (-1, 'That character name is taken.', None)

        try:
            s = Spawn.byName(newchar.name)
        except:
            pass
        else:
            return (-1, 'That character name is invalid.', None)

        print 'spawn %s' % newchar.name
        size, model, tex, animation = GetModelInfo(newchar.race, newchar.sex, newchar.look)
        spawn = Spawn(name=newchar.name, race=newchar.race, pclassInternal=newchar.klass, plevel=1, model=model, scale=size, radius=2, vocalSet='C')
        spawn.realm = newchar.realm
        spawn.sex = newchar.sex
        spawn.strBase = newchar.scores['STR'] + newchar.adjs['STR']
        spawn.dexBase = newchar.scores['DEX'] + newchar.adjs['DEX']
        spawn.refBase = newchar.scores['REF'] + newchar.adjs['REF']
        spawn.agiBase = newchar.scores['AGI'] + newchar.adjs['AGI']
        spawn.wisBase = newchar.scores['WIS'] + newchar.adjs['WIS']
        spawn.bdyBase = newchar.scores['BDY'] + newchar.adjs['BDY']
        spawn.mndBase = newchar.scores['MND'] + newchar.adjs['MND']
        spawn.mysBase = newchar.scores['MYS'] + newchar.adjs['MYS']
        char = Character(player=self.player, name=newchar.name, spawn=spawn, portraitPic=newchar.portraitPic)
        spawn.character = char
        spawn.playerName = self.player.publicName
        char.addStartingGear()
        char.backupItems()
        print 'done spawning %s' % newchar.name
        from cserveravatar import AVATAR
        if AVATAR:
            publicName, pbuffer, cbuffer, cvalues = ExtractPlayer(self.player.publicName, self.player.id, char.id, False)
            pbuffer = safe_encode(pbuffer)
            cbuffer = safe_encode(cbuffer)
            AVATAR.mind.callRemote('savePlayerBuffer', publicName, pbuffer, cbuffer, cvalues)
            char.destroySelf()
        return (0, '%s has been created.\n%s awaits your command!' % (newchar.name, 'He' if newchar.sex == 'Male' else 'She'), None)

    def gotCheckMonsterName(self, result, mname, mspawn):
        if not result:
            return self.newMonster(mname, mspawn)
        return (-1, 'That name is taken, please chose another')

    def gotCheckMonsterNameError(self, result):
        return (-1, 'There was an error creating this monster')

    def perspective_newMonster(self, mname, mspawn):
        if not self.player.premium:
            nc = 0
            names = []
            if self.player.cserverInfos:
                for cinfo in self.player.cserverInfos:
                    if cinfo.realm == RPG_REALM_MONSTER:
                        nc += 1
                        names.append(cinfo.name)

            for c in self.player.characters:
                if c.spawn.realm == RPG_REALM_MONSTER and c.spawn.name not in names:
                    nc += 1

            if nc >= 1:
                return (-1, 'You may have 1 monster in the Minions of Mirth Free Account.\nPremium Account allows up to 10 monsters.\nPlease see www.prairiegames.com for more information.', None)
        if not self.player.premium:
            try:
                src = Spawn.byName(mspawn)
            except:
                return (-1, "That's odd no spawn.", None)

            if src.plevel > 20:
                return (-1, 'You may create monsters greater than level 20 with Premium Account.\nPlease see www.prairiegames.com for more information.', None)
        from cserveravatar import AVATAR
        if AVATAR:
            level = 0
            if self.player.cserverInfos:
                for cinfo in self.player.cserverInfos:
                    if cinfo.levels[0] > level:
                        level = cinfo.levels[0]

            for c in self.player.characters:
                if c.spawn.plevel > level:
                    level = c.spawn.level

            try:
                src = Spawn.byName(mspawn)
            except:
                return (-1, "That's odd no spawn.", None)

            if src.plevel > level:
                return (-1, 'You must have a MoD or FoL character of level %i or higher to create this monster.' % src.plevel, None)
            d = AVATAR.mind.callRemote('checkCharacterName', mname)
            d.addCallback(self.gotCheckMonsterName, mname, mspawn)
            d.addErrback(self.gotCheckMonsterNameError)
            return d
        else:
            return self.newMonster(mname, mspawn)

    def confirmGrants(self, pname, confirmed):
        from cserveravatar import AVATAR
        if AVATAR:
            d = AVATAR.mind.callRemote('confirmGrants', pname, confirmed)
        else:
            print 'ERROR: confirmGrants for %s %d items' % (pname, len(confirmed))

    def newMonster(self, mname, mspawn):
        if not self.player.world.singlePlayer:
            nc = 0
            for c in self.player.characters:
                if c.spawn.realm == RPG_REALM_MONSTER:
                    nc += 1

            if nc >= 10:
                return (-1, 'The maximum monsters on this server is 10.', None)
        try:
            p = Player.byPublicName(mname)
        except:
            pass
        else:
            return (-1, 'That character name is taken.', None)

        try:
            p = Player.byFantasyName(mname)
        except:
            pass
        else:
            return (-1, 'That character name is taken.', None)

        try:
            char = Character.byName(mname)
        except:
            pass
        else:
            return (-1, 'That character name is taken.', None)

        try:
            s = Spawn.byName(mname)
        except:
            pass
        else:
            return (-1, 'That character name is invalid.', None)

        try:
            src = Spawn.byName(mspawn)
        except:
            return (-1, "That's odd no spawn.", None)

        spawn = Spawn(name=mname, pclassInternal=src.pclassInternal, plevel=1, model='')
        for n in Spawn.sqlmeta.columns.keys():
            if n != 'id' and n != 'name':
                setattr(spawn, n, getattr(src, n))

        spawn.difficultyMod = 1.0
        spawn.healthMod = 1.0
        spawn.damageMod = 1.0
        spawn.offenseMod = 1.0
        spawn.defenseMod = 1.0
        char = Character(player=self.player, name=mname, spawn=spawn, portraitPic='p033')
        spawn.character = char
        spawn.playerName = self.player.publicName
        if spawn.sex == 'Male':
            ret = (0, '%s has been created.  He awaits your command!' % mname)
        elif spawn.sex == 'Female':
            ret = (0, '%s has been created.  She awaits your command!' % mname)
        else:
            ret = (0, '%s has been created.  It awaits your command!' % mname)
        qspells = list(SpellClass.select(OR(AND(SpellClass.q.classname == spawn.pclassInternal, SpellClass.q.level <= spawn.plevel), AND(SpellClass.q.classname == spawn.sclassInternal, SpellClass.q.level <= spawn.slevel), AND(SpellClass.q.classname == spawn.tclassInternal, SpellClass.q.level <= spawn.tlevel))))
        sprotos = frozenset([ sc.spellProto for sc in sorted(qspells, key=lambda obj: obj.level) ])
        for slot, sproto in enumerate(sprotos):
            CharacterSpell(character=char, spellProto=sproto, slot=slot, recast=0)

        spawn.realm = RPG_REALM_MONSTER
        spawn.template = mspawn
        pneeded = 0
        sneeded = 0
        tneeded = 0
        if spawn.plevel > 1:
            pneeded = (spawn.plevel - 1) * (spawn.plevel - 1) * 100L * char.pxpMod
        if spawn.slevel > 1:
            sneeded = (spawn.slevel - 1) * (spawn.slevel - 1) * 100L * char.sxpMod
        if spawn.tlevel > 1:
            tneeded = (spawn.tlevel - 1) * (spawn.tlevel - 1) * 100L * char.txpMod
        char.xpPrimary = int(pneeded + 1)
        char.xpSecondary = int(sneeded + 1)
        char.xpTertiary = int(tneeded + 1)
        base = spawn.plevel * 10 + 100
        spawn.strBase = base
        spawn.dexBase = base
        spawn.refBase = base
        spawn.agiBase = base
        spawn.wisBase = base
        spawn.bdyBase = base
        spawn.mndBase = base
        spawn.mysBase = base
        char.advancementLevelPrimary = spawn.plevel
        for i in xrange(2, char.advancementLevelPrimary):
            points = int(float(i) / 2.0)
            if points < 5:
                points = 5
            char.advancementPoints += points

        char.advancementLevelSecondary = spawn.slevel
        for i in xrange(2, char.advancementLevelSecondary):
            points = int(float(i) / 2.0)
            if points < 3:
                points = 3
            char.advancementPoints += points

        char.advancementLevelTertiary = spawn.tlevel
        for i in xrange(2, char.advancementLevelTertiary):
            points = int(float(i) / 2.0)
            if points < 1:
                points = 1
            char.advancementPoints += points

        spawn.flags |= RPG_SPAWN_MONSTERADVANCED
        for resist in src.resists:
            SpawnResistance(spawn=spawn, resistType=resist.resistType, resistAmount=resist.resistAmount)

        for stat in src.spawnStats:
            s = SpawnStat(spawn=spawn, statname=stat.statname, value=stat.value)
            spawn.spawnStats.append(s)

        from cserveravatar import AVATAR
        if AVATAR:
            publicName, pbuffer, cbuffer, cvalues = ExtractPlayer(self.player.publicName, self.player.id, char.id, False)
            pbuffer = safe_encode(pbuffer)
            cbuffer = safe_encode(cbuffer)
            AVATAR.mind.callRemote('savePlayerBuffer', publicName, pbuffer, cbuffer, cvalues)
            char.destroySelf()
        return ret

    def gotDeleteCharacter(self, result):
        if result == False:
            return (-1, 'There was an error deleting this character')
        return (0, '%s has been deleted.' % result)

    def gotDeleteCharacterError(self, result):
        return (-1, 'There was an error deleting this character')

    def perspective_deleteCharacter(self, cname):
        from cserveravatar import AVATAR
        if not AVATAR:
            try:
                char = Character.byName(cname)
            except:
                return (-1, 'No character named %s.' % cname)

            if char.player != self.player:
                return (-1, 'Hack attempt!')
            char.destroySelf()
            return (0, '%s has been deleted.' % cname)
        try:
            char = Character.byName(cname)
            if char.player != self.player:
                return (-1, 'There was an error deleting %s' % cname)
            char.destroySelf()
        except:
            pass

        self.player.cserverInfos = [ n for n in self.player.cserverInfos if n.name != cname ]
        try:
            d = AVATAR.mind.callRemote('deleteCharacter', self.player.publicName, cname)
            d.addCallback(self.gotDeleteCharacter)
            d.addErrback(self.gotDeleteCharacterError)
            return d
        except:
            return (-1, 'There was an error deleting %s' % cname)

    def gotCharacterInfos(self, result):
        cinfos = []
        mspawns = []
        for ms in self.player.monsterSpawns:
            mspawns.append(ms.spawn)

        names = []
        for cname, cvalues in result.iteritems():
            names.append(cname)
            name, race, pclass, sclass, tclass, plevel, slevel, tlevel, realm, rename = cvalues
            cinfo = CharacterInfo()
            cinfo.status = 'Alive'
            cinfo.name = str(cname)
            cinfo.race = str(race)
            cinfo.realm = realm
            cinfo.klasses.append(str(pclass))
            cinfo.levels.append(plevel)
            cinfo.newCharacter = False
            cinfo.rename = rename
            cinfos.append(cinfo)

        self.player.cserverInfos = cinfos[:]
        for c in self.player.characters:
            if c.name not in names:
                cinfo = CharacterInfo(c)
                cinfo.newCharacter = True
                cinfos.append(cinfo)

        self.charInfos = cinfos
        return (cinfos, mspawns, 1)

    def gotRenameCheckCharacterName(self, result, c, newname):
        if result == 0:
            c.rename = 0
            c.name = newname
            return (0, 'Character renamed')
        return (-1, "There was a problem renaming this character.\nIt's possible that the name is taken.\nPlease try another name or try again later.")

    def gotRenameCheckCharacterNameError(self, result):
        return (-1, 'There was an error renaming this character.')

    def perspective_renameCharacter(self, oldname, newname):
        for c in self.charInfos:
            if not c.rename:
                continue
            if c.name == oldname:
                from cserveravatar import AVATAR
                d = AVATAR.mind.callRemote('renameCharacter', oldname, newname)
                d.addCallback(self.gotRenameCheckCharacterName, c, newname)
                d.addErrback(self.gotRenameCheckCharacterNameError)
                return d

        return (-1, 'There was an error renaming this character.')

    def gotCharacterInfosError(self, result):
        return ([], [], 1)

    def perspective_queryCharacters(self):
        from cserveravatar import AVATAR
        if not AVATAR:
            cinfos = []
            mspawns = []
            for ms in self.player.monsterSpawns:
                mspawns.append(ms.spawn)

            for c in self.player.characters:
                cinfo = CharacterInfo(c)
                cinfos.append(cinfo)

            return (cinfos, mspawns, CoreSettings.MAXPARTY)
        try:
            d = AVATAR.mind.callRemote('getCharacterInfos', self.player.publicName)
            d.addCallback(self.gotCharacterInfos)
            d.addErrback(self.gotCharacterInfosError)
            return d
        except:
            print 'ERROR!'
            return ([], [], 1)

    def gotCharacterBuffer(self, cbuffer, party, simPort, simPassword):
        if not self.player:
            return
        if cbuffer:
            cbuffer = safe_decode(cbuffer)
            InstallCharacterBuffer(self.player.id, party[0], cbuffer)
        self.enterWorld(party, simPort, simPassword)

    def playerJumped(self, result):
        try:
            self.mind.broker.transport.loseConnection()
        except:
            pass

        self.logout()

    def playerTransfered(self, result, party):
        wip, wport, wpassword, zport, zpassword = result
        d = self.mind.callRemote('jumpServer', wip, wport, wpassword, zport, zpassword, party)
        d.addCallback(self.playerJumped)
        d.addErrback(self.playerJumped)

    def gotTransferCharacterBuffer(self, cbuffer, party, zoneName):
        from cserveravatar import AVATAR
        self.player.transfering = True
        p = self.player
        guildInfo = (p.guildName,
         p.guildInfo,
         p.guildMOTD,
         p.guildRank)
        d = AVATAR.mind.callRemote('zoneTransferPlayer', self.player.publicName, None, party[0], cbuffer, zoneName, None, self.player.publicName, guildInfo)
        d.addCallback(self.playerTransfered, party)
        return d

    def perspective_jumpIntoWorld(self, cname):
        self.enterWorld([cname], None, None)
        self.perspective_queryCharacters()
        return

    def perspective_enterWorld(self, party, simPort, simPassword):
        from cserveravatar import AVATAR
        if not AVATAR:
            self.enterWorld(party, simPort, simPassword)
            return
        cname = party[0]
        newc = False
        player = self.player
        for c in self.charInfos:
            if cname == c.name:
                newc = c.newCharacter
                if c.realm == RPG_REALM_DARKNESS:
                    zoneName = self.player.darknessLogZone.name
                elif c.realm == RPG_REALM_MONSTER:
                    zoneName = self.player.monsterLogZone.name
                elif c.realm == RPG_REALM_LIGHT:
                    zoneName = self.player.logZone.name
                else:
                    raise Exception, 'Unknown Realm!'

        if zoneName in self.world.staticZoneNames:
            d = AVATAR.mind.callRemote('getCharacterBuffer', self.player.publicName, party[0])
            d.addCallback(self.gotCharacterBuffer, party, simPort, simPassword)
            return d
        if newc:
            char = Character.byName(cname)
            publicName, pbuffer, cbuffer, cvalues = ExtractPlayer(player.publicName, player.id, char.id, False)
            self.player.transfering = True
            pbuffer = safe_encode(pbuffer)
            cbuffer = safe_encode(cbuffer)
            p = self.player
            guildInfo = (p.guildName,
             p.guildInfo,
             p.guildMOTD,
             p.guildRank)
            d = AVATAR.mind.callRemote('zoneTransferPlayer', player.publicName, pbuffer, cname, cbuffer, zoneName, cvalues, self.player.publicName, guildInfo)
            d.addCallback(self.playerTransfered, party)
        else:
            d = AVATAR.mind.callRemote('getCharacterBuffer', self.player.publicName, party[0])
            d.addCallback(self.gotTransferCharacterBuffer, party, zoneName)
            return d

    def enterWorld(self, party, simPort, simPassword):
        from cserveravatar import AVATAR
        alldead = True
        chars = []
        for p in party:
            c = Character.byName(p)
            chars.append(c)
            if not c.dead:
                alldead = False
                break

        c = chars[0]
        self.player.darkness = False
        self.player.monster = False
        if c.spawn.realm == RPG_REALM_DARKNESS:
            self.player.darkness = True
        elif c.spawn.realm == RPG_REALM_MONSTER:
            self.player.monster = True
        self.player.charName = c.name
        self.player.realm = c.spawn.realm
        if alldead:
            for c in chars:
                c.dead = False
                c.health = -999999
                c.stamina = -999999
                c.mana = -999999

            if self.player.darkness:
                self.player.darknessLogTransformInternal = self.player.darknessBindTransformInternal
                self.player.darknessLogZone = self.player.darknessBindZone
            elif self.player.monster:
                self.player.monsterLogTransformInternal = self.player.monsterBindTransformInternal
                self.player.monsterLogZone = self.player.monsterBindZone
            else:
                self.player.logTransformInternal = self.player.bindTransformInternal
                self.player.logZone = self.player.bindZone
        zone = self.world.playerSelectZone(self, simPort, simPassword)
        if not zone:
            return
        else:
            ip = zone.ip
            if zone.owningPlayer == self.player:
                ip = '127.0.0.1'
            self.player.loggingOut = False
            self.player.cursorItem = None
            self.player.simPort = simPort
            self.player.simPassword = simPassword
            zconnect = ZoneConnectionInfo()
            zconnect.ip = ip
            zconnect.password = zone.password
            zconnect.port = zone.port
            zconnect.niceName = zone.zone.niceName
            zconnect.missionFile = zone.zone.missionFile
            zconnect.instanceName = zone.name
            zone.submitPlayer(self.player, zconnect)
            self.player.party = Party()
            self.player.party.assemble(self.player, party)
            self.player.updateKOS()
            if AVATAR:
                if self.masterPerspective.avatars.has_key('ImmortalAvatar'):
                    for c in self.player.party.members:
                        c.mob.aggroOff = True

            self.player.rootInfo = RootInfo(self.player, self.player.party.charInfos)
            self.mind.callRemote('setRootInfo', self.player.rootInfo, time() - self.player.world.pauseTime)
            if self.player.cursorItem:
                self.mind.callRemote('setCursorItem', self.player.cursorItem.itemInfo)
            if Player.remoteLeaderNames.has_key(self.player.publicName):
                rln = Player.remoteLeaderNames[self.player.publicName]
                del Player.remoteLeaderNames[self.player.publicName]
                found = False
                a = Alliance.masterAllianceInfo.get(rln)
                if a:
                    for pname, cname in a:
                        if pname == self.player.publicName:
                            found = True
                            break

                if not found:
                    self.player.alliance = Alliance(self.player)
                else:
                    found = False
                    for p in self.world.activePlayers:
                        if p == self.player:
                            continue
                        if not p.alliance:
                            continue
                        if p.alliance.remoteLeaderName == rln:
                            found = True
                            self.player.alliance = p.alliance
                            if p.alliance.remoteLeaderName == self.player.publicName:
                                p.alliance.leader = self.player
                                p.alliance.members.insert(0, self.player)
                            else:
                                p.alliance.members.append(self.player)
                            self.player.alliance.setupForPlayer(self.player)
                            break

                    if not found:
                        self.player.alliance = Alliance(self.player, rln)
            else:
                self.player.alliance = Alliance(self.player)
            if self.player.publicName == 'ThePlayer':
                text = ''
            else:
                text = ', %s%s%s' % (self.player.publicName, ', premium player' if self.player.premium else '', ', of guild <%s>' % self.player.guildName if self.player.guildName else '')
            self.player.sendGameText(RPG_MSG_GAME_GLOBAL, '\nWelcome to "%s"%s!\n' % (GAMENAME, text))
            if CoreSettings.MOTD:
                self.player.sendGameText(RPG_MSG_GAME_GLOBAL, 'Server MOTD: ' + CoreSettings.MOTD + '\\n')
            if self.player.guildMOTD:
                self.player.sendGameText(RPG_MSG_GAME_LEVELGAINED, 'Guild MOTD: ' + self.player.guildMOTD + '\\n')
            return

    def perspective_doCommand(self, cmd, args):
        index = 0
        if len(args):
            index = int(args[0])
        try:
            char = self.player.party.members[index]
            if not char or char.dead or not char.mob:
                return
            DoCommand(char.mob, cmd, args[1:])
        except:
            traceback.print_exc()

    def perspective_onSpellSlot(self, cid, slot):
        party = self.player.party
        char = Character.get(cid)
        if char not in party.members:
            print 'onSpellSlot: PLAYER ATTEMPTING TO MANIPULATE NONPARTY CHARACTER'
            return
        if char.dead or not char.mob:
            return
        cursorItem = self.player.cursorItem
        char.onSpellSlot(slot)
        self.player.updateCursorItem(cursorItem)

    def perspective_onSpellSlotSwap(self, cid, src, dest):
        party = self.player.party
        char = Character.get(cid)
        if char not in party.members:
            print 'onSpellSlot: PLAYER ATTEMPTING TO MANIPULATE NONPARTY CHARACTER'
            return
        if char.dead or not char.mob:
            return
        char.onSpellSlotSwap(src, dest)

    def perspective_onInvSlot(self, cid, slot):
        party = self.player.party
        char = Character.get(cid)
        if char not in party.members:
            print 'onInvSlot: PLAYER ATTEMPTING TO MANIPULATE NONPARTY CHARACTER'
            return
        if char.dead or not char.mob:
            return
        cursorItem = self.player.cursorItem
        char.onInvSlot(slot)
        self.player.updateCursorItem(cursorItem)

    def perspective_onInvSlotAlt(self, cid, slot):
        party = self.player.party
        char = Character.get(cid)
        if char not in party.members:
            print 'onInvSlot: PLAYER ATTEMPTING TO MANIPULATE NONPARTY CHARACTER'
            return
        if char.dead or not char.mob:
            return
        char.onInvSlotAlt(slot)

    def perspective_onInvSlotCtrl(self, charID, invSlot):
        char = Character.get(charID)
        if char not in self.player.party.members:
            print 'onInvSlotCtrl: PLAYER ATTEMPTING TO MANIPULATE NONPARTY CHARACTER'
            return
        if char.dead or not char.mob:
            return
        if RPG_SLOT_WORN_END > invSlot >= RPG_SLOT_WORN_BEGIN or RPG_SLOT_CARRY_END > invSlot >= RPG_SLOT_CARRY_BEGIN or RPG_SLOT_CRAFTING_END > invSlot >= RPG_SLOT_CRAFTING_BEGIN:
            for item in char.items:
                if item.slot == invSlot:
                    item.use(char.mob)
                    return

        else:
            print 'onInvSlotCtrl: PLAYER ATTEMPTING TO USE INVALID SLOT'
            return

    def perspective_onApplyPoison(self, charID, poisonSlot, applicationSlot):
        player = self.player
        char = Character.get(charID)
        if char not in player.party.members:
            print 'onApplyPoison: PLAYER ATTEMPTING TO MANIPULATE NONPARTY CHARACTER'
            return
        else:
            mob = char.mob
            if char.dead or not mob:
                return
            if mob.sleep > 0 or mob.stun > 0 or mob.isFeared:
                player.sendGameText(RPG_MSG_GAME_DENIED, '%s cannot use items while asleep, stunned, or feared.\\n' % char.name)
                return
            poisonTarget = None
            if applicationSlot in (RPG_SLOT_PRIMARY, RPG_SLOT_SECONDARY, RPG_SLOT_RANGED):
                poisonTarget = mob.worn.get(applicationSlot)
                if not poisonTarget:
                    player.sendGameText(RPG_MSG_GAME_DENIED, "Can't apply poison, %s has nothing equipped in this slot.\\n" % char.name)
                    return
            elif applicationSlot in (RPG_SLOT_PET_PRIMARY, RPG_SLOT_PET_SECONDARY, RPG_SLOT_PET_RANGED):
                if mob.pet:
                    poisonTarget = mob.pet.worn.get(applicationSlot - RPG_SLOT_PET_PRIMARY + RPG_SLOT_PRIMARY)
                    if not poisonTarget:
                        player.sendGameText(RPG_MSG_GAME_DENIED, "Can't apply poison, %s's pet has nothing equipped in this slot.\\n" % char.name)
                        return
                else:
                    player.sendGameText(RPG_MSG_GAME_DENIED, "Can't apply poison, %s has no pet.\\n" % char.name)
                    return
            if not poisonTarget:
                print 'onApplyPoison: PLAYER ATTEMPTING TO APPLY POISON TO WRONG SLOT'
                return
            for item in char.items:
                if item.slot == poisonSlot:
                    poison = item
                    break
            else:
                print 'onApplyPoison: PLAYER ATTEMPTING TO USE INVALID SLOT'
                return

            if not poison.isUseable(mob) or poison.penalty:
                player.sendGameText(RPG_MSG_GAME_DENIED, '%s cannot currently use this %s.\\n' % (char.name, poison.name))
                return
            if poison.reuseTimer:
                player.sendGameText(RPG_MSG_GAME_DENIED, '%s cannot use this %s for another %i seconds.\\n' % (char.name, poison.name, poison.reuseTimer))
                return
            skipRefresh = True
            if poison.skill:
                if not mob.skillLevels.get(poison.skill):
                    player.sendGameText(RPG_MSG_GAME_DENIED, '%s cannot use this %s as it requires the %s skill.\\n' % (char.name, poison.name, poison.skill))
                    return
                try:
                    mskill = mob.mobSkillProfiles[poison.skill]
                    poison.reuseTimer = mskill.reuseTime
                except:
                    poison.reuseTimer = 60

                mob.itemRequireTick[poison] = poison.reuseTimer
                skipRefresh = False
            if len(poison.spells):
                for ispell in poison.spells:
                    if ispell.trigger == RPG_ITEM_TRIGGER_POISON:
                        targetProcs = poisonTarget.procs
                        if targetProcs.has_key(ispell):
                            targetProcs[ispell] = [ispell.duration, RPG_ITEMPROC_POISON]
                            player.sendGameText(RPG_MSG_GAME_GAINED, '%s refreshes %s.\\n' % (char.name, poison.name))
                        elif len(targetProcs) < RPG_ITEMPROC_MAX:
                            targetProcs[ispell] = [ispell.duration, RPG_ITEMPROC_POISON]
                            player.sendGameText(RPG_MSG_GAME_GAINED, '%s applies %s.\\n' % (char.name, poison.name))
                        else:
                            overwriting = []
                            for proc, procData in targetProcs.iteritems():
                                if procData[1] != RPG_ITEMPROC_ENCHANTMENT:
                                    if not overwriting or overwriting[1] < procData[0]:
                                        overwriting = (proc, procData[0])

                            if overwriting:
                                del targetProcs[overwriting[0]]
                                targetProcs[ispell] = [ispell.duration, RPG_ITEMPROC_POISON]
                                player.sendGameText(RPG_MSG_GAME_DENIED, 'The applied %s nullifies %s.\\n' % (poison.name, overwriting[0].spellProto.name))
                            else:
                                player.sendGameText(RPG_MSG_GAME_DENIED, '%s radiates so much power that %s evaporates.\\n' % (poisonTarget.name, poison.name))
                        player.mind.callRemote('playSound', 'sfx/Underwater_Bubbles2.ogg')
                        poisonTarget.itemInfo.refreshProcs()
                        if poison.useCharges:
                            poison.useCharges -= 1
                            if not poison.useCharges and poison.itemProto.useDestroy:
                                poison.stackCount -= 1
                                if poison.stackCount <= 0:
                                    player.takeItem(poison)
                                else:
                                    poison.useCharges = poison.itemProto.useMax
                                    skipRefresh = False
                            elif poison.useCharges < 0:
                                poison.useCharges = 0
                            else:
                                skipRefresh = False

            if not skipRefresh:
                poison.itemInfo.refresh()
            return

    def perspective_endLooting(self):
        if not self.player.looting:
            return
        else:
            self.player.stopLooting(self.player.looting)
            self.player.looting.looter = None
            self.player.looting = None
            return True

    def perspective_loot(self, cindex, slot, alt = False):
        if not self.player.looting:
            return
        char = self.player.party.members[cindex]
        if char.dead or not char.mob:
            return
        char.onLoot(self.player.looting, slot, alt)

    def perspective_destroyCorpse(self):
        if not self.player.looting:
            return
        self.player.stopLooting(self.player.looting, True)

    def perspective_expungeItem(self):
        item = self.player.cursorItem
        self.player.cursorItem = None
        if item.character.player != self.player:
            raise ValueError, 'Attempting to expunge an item not belonging to player!'
            return
        else:
            item.slot = -1
            self.player.updateCursorItem(item)
            item.destroySelf()
            self.player.cinfoDirty = True
            return

    def perspective_splitItem(self, newStackSize):
        item = self.player.cursorItem
        if item.character not in self.player.party.members:
            raise Exception, "Attempting to split an item not belonging to player's present party!"
            self.player.cursorItem = None
            return
        else:
            item.character.splitItem(item, newStackSize)
            return

    def perspective_chooseZone(self, choice):
        found = False
        zoneInstanceName = ''
        player = self.player
        if player.darkness:
            player.darknessLogTransformInternal = player.triggeredZoneLink.dstZoneTransform
            player.darknessLogZone = Zone.byName(player.triggeredZoneLink.dstZoneName)
        elif player.monster:
            player.monsterLogTransformInternal = player.triggeredZoneLink.dstZoneTransform
            player.monsterLogZone = Zone.byName(player.triggeredZoneLink.dstZoneName)
        else:
            player.logTransformInternal = player.triggeredZoneLink.dstZoneTransform
            player.logZone = Zone.byName(player.triggeredZoneLink.dstZoneName)
        self.world.closePlayerZone(player)
        if choice == 'new' and player.world.singlePlayer:
            zi = self.world.playerSelectZone(self, self.player.simPort, self.player.simPassword)
            if zi:
                zoneInstanceName = zi.name
                found = True
            else:
                found = False
        else:
            for zo in player.triggeredZoneOptions:
                if zo.zoneInstanceName == choice:
                    zoneInstanceName = zo.zoneInstanceName
                    found = True
                    break

        if found:
            zi = self.world.getZoneByInstanceName(zoneInstanceName)
            if not zi:
                traceback.print_stack()
                print 'AssertionError: zone not found!'
                return
            player.zone = zi
            player.party.reassemble()
            ip = zi.ip
            if zi.owningPlayer == player:
                ip = '127.0.0.1'
            zconnect = ZoneConnectionInfo()
            zconnect.ip = ip
            zconnect.password = zi.password
            zconnect.port = zi.port
            zconnect.niceName = zi.zone.niceName
            zconnect.missionFile = zi.zone.missionFile
            zconnect.instanceName = zi.name
            zi.submitPlayer(self.player, zconnect)
            self.player.rootInfo = RootInfo(self.player, self.player.party.charInfos)
            self.mind.callRemote('setRootInfo', self.player.rootInfo)
            if self.player.cursorItem:
                self.mind.callRemote('setCursorItem', self.player.cursorItem.itemInfo)

    def perspective_onInteractionChoice(self, index, pane):
        if not self.player.interacting or not self.player.curDialogLine:
            pane.callRemote('close')
            return
        self.player.dialog.handleChoice(self.player, index, pane)

    def perspective_endInteraction(self):
        self.player.endInteraction()

    def perspective_sellItem(self, charIndex, slot):
        if not self.player.interacting or not self.player.interacting.vendor:
            return
        else:
            char = self.player.party.members[charIndex]
            if char.dead or not char.mob:
                return
            item = None
            found = False
            for item in char.items:
                if item.slot == slot:
                    found = True
                    break

            if item and found:
                self.player.interacting.vendor.buyItem(self.player, item)
            else:
                print 'Warning: Player item selling wackiness!!! Item to be sold not found!'
            return

    def perspective_buyItem(self, charIndex, itemIndex):
        if not self.player.interacting or not self.player.interacting.vendor:
            return
        char = self.player.party.members[charIndex]
        if char.dead or not char.mob:
            return
        self.player.interacting.vendor.sellItem(self.player, char, itemIndex)

    def perspective_setCurrentCharacter(self, cindex):
        if cindex >= len(self.player.party.members):
            return -1
        cchar = self.player.party.members[cindex]
        if self.player.curChar != cchar:
            self.player.curChar = cchar
            if hasattr(self.player, 'dialog'):
                if self.player.dialog and self.player.interacting:
                    if hasattr(self.player.interacting, 'spawn'):
                        name = self.player.interacting.spawn.name
                    else:
                        name = self.player.dialog.title
                    self.player.dialog.setLine(self.player, self.player.dialog.greeting, name)
        return cindex

    def perspective_setXPGain(self, charindex, pvalue, svalue, tvalue):
        char = self.player.party.members[charindex]
        char.setXPGain(pvalue, svalue, tvalue)

    def perspective_invite(self):
        player = self.player
        alliance = player.alliance
        if player.invite:
            player.sendGameText(RPG_MSG_GAME_DENIED, 'You must accept or decline an outstanding invitation first.\\n')
            return
        target = player.curChar.mob.target
        if not target:
            player.sendGameText(RPG_MSG_GAME_DENIED, 'You must have a valid target to invite.\\n')
            return
        if not target.player:
            player.sendGameText(RPG_MSG_GAME_DENIED, 'You cannot invite %s to the alliance.\\n' % target.name)
            return
        if alliance.leader != player or alliance.remoteLeaderName != player.publicName:
            player.sendGameText(RPG_MSG_GAME_DENIED, 'You are not the leader of the alliance.\\n')
            return
        if alliance.countMembers() >= 6:
            player.sendGameText(RPG_MSG_GAME_DENIED, 'The alliance is full.\\n')
            return
        otherplayer = target.player
        if otherplayer == player:
            return
        if otherplayer.invite:
            player.sendGameText(RPG_MSG_GAME_DENIED, '%s is already considering an alliance.\\n' % otherplayer.charName)
            return
        if otherplayer.alliance.countMembers() > 1:
            player.sendGameText(RPG_MSG_GAME_DENIED, '%s is already in an alliance.\\n' % otherplayer.charName)
            return
        d = otherplayer.mind.callRemote('checkIgnore', player.charName)
        d.addCallback(self.gotCheckIgnoreAlliance, player, otherplayer)
        d.addErrback(self.gotCheckIgnoreAllianceError)

    def gotCheckIgnoreAlliance(self, ignored, player, otherplayer):
        if ignored:
            player.sendGameText(RPG_MSG_GAME_DENIED, '%s is ignoring you.\\n' % otherplayer.charName)
            return
        player.sendGameText(RPG_MSG_GAME_GOOD, 'You have invited %s to the alliance.\\n' % otherplayer.charName)
        otherplayer.sendGameText(RPG_MSG_GAME_GOOD, '%s has invited you to form an alliance.\\n' % player.charName)
        player.alliance.invite(otherplayer)

    def gotCheckIgnoreAllianceError(self, error):
        print 'Error in checkIgnore: %s' % str(error)

    def perspective_joinAlliance(self):
        player = self.player
        if not player.invite:
            return False
        else:
            leader = player.invite.leader
            if player.invite.alliance != leader.alliance:
                player.invite = None
                player.sendGameText(RPG_MSG_GAME_DENIED, 'This alliance has disbanded.\\n')
                return False
            alliance = leader.alliance
            if not alliance.join(player):
                player.sendGameText(RPG_MSG_GAME_DENIED, 'You cannot join the alliance at this time.\\n')
                return False
            player.sendGameText(RPG_MSG_GAME_GOOD, "You have joined %s's alliance.\\n" % leader.charName)
            for p in alliance.members:
                for c in p.party.members:
                    mob = c.mob
                    target = mob.target
                    if target:
                        if target.master:
                            target = target.master
                        if target.player and target.player in alliance.members:
                            mob.attackOff()
                    mob = mob.pet
                    if mob:
                        target = mob.target
                        if target:
                            if target.master:
                                target = target.master
                            if target.player and target.player in alliance.members:
                                mob.attackOff()
                                try:
                                    del mob.aggro[mob.target]
                                except KeyError:
                                    pass

                if p == player:
                    continue
                p.sendGameText(RPG_MSG_GAME_GOOD, '%s has joined your alliance.\\n' % player.charName)

            return True

    def perspective_leaveDecline(self):
        player = self.player
        if player.invite:
            try:
                player.invite.decline()
            except:
                traceback.print_exc()

            player.invite = None
            return
        else:
            if player.alliance.countMembers() > 1:
                player.alliance.leave(player)
            return

    def perspective_disband(self):
        player = self.player
        if player.publicName != player.alliance.remoteLeaderName:
            return
        if player.alliance.countMembers() > 1:
            player.alliance.disband()

    def perspective_kick(self, name):
        player = self.player
        if player.publicName != player.alliance.remoteLeaderName:
            return
        if player.alliance.leader == player and player.alliance.countMembers() > 1:
            player.alliance.kick(name)

    def perspective_onPlayerTradeMoney(self, money):
        player = self.player
        if not player.trade:
            return 0L
        return player.trade.submitMoney(player, money)

    def perspective_onPlayerTradeSlot(self, slot):
        player = self.player
        if not player.trade:
            return
        party = player.party
        char = player.curChar
        cursorItem = player.cursorItem
        char.onInvSlot(slot + RPG_SLOT_TRADE0)
        player.updateCursorItem(cursorItem)

    def perspective_onPlayerTradeCancel(self):
        player = self.player
        if not player.trade:
            return
        player.trade.cancel()

    def perspective_onPlayerTradeAccept(self):
        player = self.player
        if not player.trade:
            return
        player.trade.accept(player)

    def sendTgtDesc(self, src, tgt):
        if not tgt:
            return
        else:
            char = tgt.character
            player = tgt.player
            infoDict = {}
            infoDict['NAME'] = tgt.name
            infoDict['TGTID'] = tgt.id
            infoDict['PCLASS'] = tgt.pclass.name
            infoDict['PLEVEL'] = tgt.plevel
            if tgt.sclass and tgt.slevel:
                infoDict['SCLASS'] = tgt.sclass.name
                infoDict['SLEVEL'] = tgt.slevel
                if tgt.tclass and tgt.tlevel:
                    infoDict['TCLASS'] = tgt.tclass.name
                    infoDict['TLEVEL'] = tgt.tlevel
            infoDict['RACE'] = tgt.race.name
            infoDict['REALM'] = tgt.realm
            infoDict['DESC'] = tgt.spawn.desc
            if self.player == player:
                infoDict['MYSELF'] = True
            else:
                if player:
                    player.sendGameText(RPG_MSG_GAME_EVENT, '%s is getting inspected by <a:gamelinkcharlink%s>%s</a>.\\n' % (char.name, src.name.replace(' ', '_'), src.name))
                infoDict['MYSELF'] = False
                infoDict['STANDING'] = GetFactionRelationDesc(src, tgt)
            infoDict['CHARTGT'] = char != None
            if char:
                infoDict['VARIANTNAME'] = char.lastName
                infoDict['DEADTGT'] = char.dead == True
                infoDict['GUILDNAME'] = player.guildName
                infoDict['BIRTHDATE'] = char.creationTime.strftime('%a, %b %d %Y')
                infoDict['PORTRAIT'] = char.portraitPic
                infoDict['ENCOUNTERSETTING'] = player.encounterSetting
            else:
                infoDict['DEADTGT'] = tgt.detached == True
                infoDict['PET'] = tgt.master != None
                infoDict['VARIANTNAME'] = tgt.variantName
            self.mind.callRemote('setTgtDesc', infoDict)
            return

    def perspective_setSpawnDesc(self, myDesc, mobID):
        mob = None
        for c in self.player.party.members:
            if c.mob.id == mobID:
                mob = c.mob
                break

        if mob:
            mob.spawn.desc = myDesc
        else:
            self.player.sendGameText(RPG_MSG_GAME_DENIED, "Spawn description couldn't be set, spawn not found.\\n")
        return

    def perspective_setPortraitPic(self, pic):
        self.player.curChar.portraitPic = pic

    def perspective_cancelProcess(self, cid, pid):
        for c in self.player.party.members:
            if c.id == cid:
                for p in c.mob.processesIn:
                    if isinstance(p, Spell):
                        if pid == p.pid and not p.spellProto.spellType & RPG_SPELL_HARMFUL:
                            p.cancel()
                            return

    def perspective_chooseAdvancement(self, cname, advancement):
        for c in self.player.party.members:
            if c.name == cname:
                c.chooseAdvancement(advancement)
                return

        raise RuntimeWarning, 'Player %s attempting to choose advancement %s for %s' % (self.player.name, advancement, cname)

    def perspective_onCraft(self, cindex, recipeID, useCraftWindow = False):
        if cindex > len(self.player.party.members) - 1:
            return
        self.player.party.members[cindex].onCraft(recipeID, useCraftWindow)

    def perspective_repairItem(self, cindex):
        if cindex > len(self.player.party.members) - 1:
            return
        RepairItem(self.player, self.player.party.members[cindex])

    def perspective_repairAll(self, cindex):
        if cindex > len(self.player.party.members) - 1:
            return
        RepairAll(self.player, self.player.party.members[cindex])

    def perspective_repairParty(self, cindex):
        if cindex > len(self.player.party.members) - 1:
            return
        RepairParty(self.player, self.player.party.members[cindex])

    def perspective_onBankSlot(self, slot):
        player = self.player
        cursorItem = player.cursorItem
        bankItem = player.bankItems.get(slot, None)
        if bankItem:
            switched, newBankItem, newCursorItem = bankItem.doStack(cursorItem)
            if switched:
                newCursorItem.setCharacter(player.curChar, False)
                newCursorItem.slot = RPG_SLOT_CURSOR
                newCursorItem.refreshFromProto()
                if newBankItem:
                    newBankItem.setCharacter(None, False)
                    newBankItem.slot = slot
                    newBankItem.setPlayerAsOwner(player)
                    player.bankItems[slot] = newBankItem
                    newBankItem.refreshFromProto()
            elif not newCursorItem:
                cursorItem = None
            player.cursorItem = newCursorItem
            player.updateCursorItem(cursorItem)
            player.rootInfo.forceBankUpdate = True
            return
        else:
            if cursorItem:
                cursorItem.setCharacter(None, False)
                cursorItem.slot = slot
                cursorItem.setPlayerAsOwner(player)
                player.bankItems[slot] = cursorItem
                cursorItem.refreshFromProto()
                player.cursorItem = None
                player.rootInfo.forceBankUpdate = True
            player.updateCursorItem(cursorItem)
            return

    def perspective_onAcceptResurrect(self):
        if not self.player.resurrectionRequest:
            return
        else:
            t, xpRecover, healthRecover, manaRecover, staminaRecover, cname = self.player.resurrectionRequest
            if time() - t > 30:
                self.player.sendGameText(RPG_MSG_GAME_DENIED, 'This resurrection has expired.\\n')
                return
            self.player.resurrectionRequest = None
            c = self.player.party.members[0]
            if c.name != cname:
                return
            if not c.deathZone:
                return
            c.playerResurrect(xpRecover, healthRecover, manaRecover, staminaRecover)
            return

    def perspective_onResurrect(self, cname):
        if not self.player.resurrection:
            return
        else:
            t, xpRecover, healthRecover, manaRecover, staminaRecover, cnames = self.player.resurrection
            self.player.resurrection = None
            if self.player.curChar:
                pCharName = self.player.curChar.name
            else:
                pCharName = self.player.fantasyName
            if cname not in cnames:
                self.player.sendGameText(RPG_MSG_GAME_DENIED, 'Resurrection error, resurrect target %s not in list of possible resurrection targets.\\n' % cname)
                return
            if time() - t > 30:
                self.player.sendGameText(RPG_MSG_GAME_DENIED, 'Resurrection expired.\\n')
                return
            for p in self.player.world.activePlayers:
                if p.zone and p in p.zone.players:
                    c = p.party.members[0]
                    if c.deathZone and c.name == cname:
                        if p.resurrectionRequest:
                            timer = p.resurrectionRequest[0]
                            if time() - timer < 30:
                                self.player.sendGameText(RPG_MSG_GAME_DENIED, '%s is already being resurrected.\\n' % cname)
                                return
                        p.resurrectionRequest = (time(),
                         xpRecover,
                         healthRecover,
                         manaRecover,
                         staminaRecover,
                         cname)
                        p.mind.callRemote('resurrectionRequest', pCharName, xpRecover)
                        return

            self.player.world.daemonPerspective.callRemote('resurrectionRequest', pCharName, xpRecover, healthRecover, manaRecover, staminaRecover, time(), cname)
            return

    def perspective_onRemoveVault(self, id):
        player = self.player
        if player.cursorItem:
            return
        else:
            char = player.curChar
            try:
                vitem = CharacterVaultItem.get(id)
            except:
                print 'WARNING: Invalid vault item id %i' % id
                return

            if char != vitem.character:
                print 'WARNING: Player %s attempting to remove vault item to incorrect character %s' % (player.name, char.name)
                return
            item = ItemInstance(vitem.item)
            vitem.destroySelf()
            char.vaultItemsDirty = True
            item.setCharacter(char)
            item.slot = RPG_SLOT_CURSOR
            player.cursorItem = item
            player.updateCursorItem(None)
            return

    def perspective_onPlaceVault(self):
        player = self.player
        if not player.cursorItem:
            return
        else:
            item = player.cursorItem
            if item.flags & (RPG_ITEM_ETHEREAL | RPG_ITEM_WORLDUNIQUE):
                return
            stackMax = item.itemProto.stackMax
            char = player.curChar
            stacked = False
            if stackMax > 1:
                useMax = item.itemProto.useMax
                if useMax > 1:
                    neededCharges = useMax * (item.stackCount - 1) + item.useCharges
                    for vitem in char.vaultItems:
                        if vitem.name != item.name:
                            continue
                        candidate = vitem.item
                        freeCharges = useMax * (stackMax - candidate.stackCount + 1) - candidate.useCharges
                        if freeCharges <= 0:
                            continue
                        stacked = True
                        if freeCharges > neededCharges:
                            freeCharges = neededCharges
                        stackCount = freeCharges / useMax
                        useCharges = freeCharges % useMax
                        candidate.useCharges += useCharges
                        item.useCharges -= useCharges
                        if item.useCharges <= 0:
                            item.useCharges += useMax
                            item.stackCount -= 1
                        if candidate.useCharges > useMax:
                            candidate.useCharges -= useMax
                            candidate.stackCount += 1
                        break

                else:
                    for vitem in char.vaultItems:
                        if vitem.name != item.name or vitem.stackCount >= stackMax:
                            continue
                        stacked = True
                        candidate = vitem.item
                        stackCount = stackMax - candidate.stackCount
                        if stackCount > item.stackCount:
                            stackCount = item.stackCount
                        break

                if stacked:
                    candidate.stackCount += stackCount
                    vitem.stackCount += stackCount
                    item.stackCount -= stackCount
                    if item.stackCount <= 0:
                        player.takeItem(item)
                        char.vaultItemsDirty = True
                        char.charInfo.refreshVault()
                        return
            if RPG_PRIVATE_VAULT_LIMIT <= len(char.vaultItems):
                self.player.sendGameText(RPG_MSG_GAME_DENIED, "%s's private vault is full.\\n" % char.name)
                if stacked:
                    item.itemInfo.refreshDict({'STACKCOUNT': item.stackCount,
                     'USECHARGES': item.useCharges})
                    char.vaultItemsDirty = True
                    char.charInfo.refreshVault()
                return
            item.setCharacter(None)
            item.player = None
            item.slot = -1
            player.cursorItem = None
            player.updateCursorItem(item)
            item.storeToItem(True)
            CharacterVaultItem(character=char, item=item.item, name=item.name, stackCount=item.stackCount)
            char.vaultItemsDirty = True
            char.charInfo.refresh()
            return

    def perspective_submitFriends(self, friends):
        self.player.friends = set((f.upper() for f in friends))

    def perspective_setEncounterSetting(self, index, now = False):
        if now:
            self.player.encounterSetting = index
        elif self.player.encounterSetting != index:
            char = self.player.curChar
            mob = char.mob
            if index == RPG_ENCOUNTER_PVE:
                msg = '%s will cease fighting other players.\\n' % char.name
            elif index == RPG_ENCOUNTER_RVR:
                msg = 'Attention: %s may now engage in realm versus realm battles!\\n' % char.name
            elif index == RPG_ENCOUNTER_GVG:
                msg = 'Attention: %s may now engage in guild versus guild battles!\\n' % char.name
            else:
                msg = 'WARNING: %s may now engage in player versus player battles!\\n' % char.name
            GameMessage(RPG_MSG_GAME_COMBAT, mob.zone, mob, None, msg, mob.simObject.position, range=30)
            reactor.callLater(10, self.player.applyEncounterSetting, index)
        return

    def perspective_insertItem(self, containerSlot, charID):
        player = self.player
        cursorItem = player.cursorItem
        if not cursorItem:
            return
        else:
            srcChar = None
            if charID:
                srcChar = Character.get(charID)
                if srcChar not in player.party.members:
                    print 'insertItem: PLAYER %s IS ATTEMPTING TO MANIPULATE NONPARTY CHARACTER %s!' % (player.name, srcChar.name)
                    return
            container = None
            if RPG_SLOT_BANK_BEGIN <= containerSlot < RPG_SLOT_BANK_END:
                container = player.bankItems.get(containerSlot)
            else:
                if not srcChar:
                    print 'insertItem: ERROR, container owner unspecified!'
                    return
                if srcChar.mob and RPG_SLOT_WORN_BEGIN <= containerSlot < RPG_SLOT_WORN_END:
                    container = srcChar.mob.worn.get(containerSlot)
                else:
                    for citem in srcChar.items:
                        if citem.slot == containerSlot:
                            container = citem
                            break

            if not container or not container.container:
                print 'insertItem: WARNING, could not find desired container for player %s!' % player.name
                return
            if container.container.insertItem(cursorItem, True):
                container.itemInfo.refreshContents()
            return

    def perspective_extractItem(self, containerSlot, charID, itemIndex):
        player = self.player
        if player.cursorItem:
            return
        else:
            srcChar = None
            if charID:
                srcChar = Character.get(charID)
                if srcChar not in player.party.members:
                    print 'extractItem: PLAYER %s IS ATTEMPTING TO MANIPULATE NONPARTY CHARACTER %s!' % (player.name, srcChar.name)
                    return
            tgtChar = player.curChar
            container = None
            if RPG_SLOT_BANK_BEGIN <= containerSlot < RPG_SLOT_BANK_END:
                container = player.bankItems.get(containerSlot)
            else:
                if not srcChar:
                    print 'extractItem: ERROR, container owner unspecified!'
                    return
                if srcChar.mob and RPG_SLOT_WORN_BEGIN <= containerSlot < RPG_SLOT_WORN_END:
                    container = srcChar.mob.worn.get(containerSlot)
                else:
                    for citem in srcChar.items:
                        if citem.slot == containerSlot:
                            container = citem
                            break

            if not container or not container.container:
                print 'extractItem: WARNING, could not find desired container for player %s!' % player.name
                return
            extraction = container.container.extractItemByIndex(itemIndex)
            if not extraction:
                return
            extraction.setCharacter(tgtChar)
            extraction.slot = RPG_SLOT_CURSOR
            player.cursorItem = extraction
            player.updateCursorItem(None)
            container.itemInfo.refreshContents()
            return