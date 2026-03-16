# Embedded file name: mud\world\worldupdate.pyo
import sys, os, traceback
from datetime import datetime
import re
import shutil
from sqlobject import *
from pysqlite2 import dbapi2 as sqlite
from mud.utils import *
from mud.common.dbconfig import SetDBConnection
from mud.common.permission import User, Role
from mud.common.persistent import Persistent
from mud.world.defines import *
from mud.world.player import Player, PlayerXPCredit, PlayerMonsterSpawn
from mud.world.zone import Zone
from mud.world.character import Character, CharacterSpell, CharacterSkill, CharacterAdvancement, CharacterDialogChoice, CharacterVaultItem, CharacterFaction
from mud.world.spawn import Spawn, SpawnResistance, SpawnStat
from mud.world.spell import SpellProto, SpellStore
from mud.world.advancement import AdvancementProto
from mud.world.faction import Faction
from mud.world.item import Item, ItemProto, ItemSpell, ItemContainerContent
from mud.world.itemvariants import ItemVariant
try:
    from tgenative import *
    from mud.tgepython.console import TGEExport
except:
    pass

WSCHEMA = {}
TABLES = ['Player',
 'PlayerXPCredit',
 'PlayerMonsterSpawn',
 'PlayerIgnore',
 'Character',
 'CharacterSpell',
 'CharacterSkill',
 'CharacterAdvancement',
 'CharacterDialogChoice',
 'CharacterVaultItem',
 'CharacterFaction',
 'Item',
 'ItemVariant',
 'ItemContainerContent',
 'Spawn',
 'SpawnResistance',
 'SpawnStat',
 'User',
 'Role',
 'SpellStore']
FROMGAME = False
FORCE = False

def GetGenesisTime(text):
    if not text:
        return datetime(1, 1, 1)
    gdate, gtime = text.split(' ')
    gyear, gmonth, gday = gdate.split('-')
    ghour, gminute, gsecond = gtime.split(':')
    gyear = int(gyear)
    gmonth = int(gmonth)
    gday = int(gday)
    ghour = int(ghour)
    gminute = int(gminute)
    gsecond = int(gsecond)
    return datetime(gyear, gmonth, gday, ghour, gminute, gsecond)


def CheckWorld(worldPath, baselinePath):
    global WCONN
    global BCONN
    global FORCE
    global FROMGAME
    WCONN = sqlite.connect(worldPath)
    wcur = WCONN.cursor()
    try:
        wcur.execute('select genesis_time from World where name = "TheWorld" LIMIT 1;')
        wdatetime = GetGenesisTime(wcur.fetchone()[0])
    except:
        wdatetime = GetGenesisTime(None)

    wcur.close()
    WCONN.close()
    WCONN = None
    BCONN = sqlite.connect(baselinePath)
    bcur = BCONN.cursor()
    bcur.execute('select genesis_time from World where name = "TheWorld" LIMIT 1;')
    bdatetime = GetGenesisTime(bcur.fetchone()[0])
    bcur.close()
    BCONN.close()
    BCONN = None
    if 0 and is_frozen():
        from genesistime import GENESISTIME
        gdatetime = GetGenesisTime(GENESISTIME)
        if gdatetime != bdatetime:
            if FROMGAME:
                TGEEval('canvas.setContent("MainMenuGui");')
                TGECall('MessageBoxOK', 'Error updating world!', 'Genesis Time does not match Baseline Time!')
                return -1
    if wdatetime < bdatetime or FORCE:
        return 1
    else:
        return 0


def FilterColumns(klass, dbAttr):
    del dbAttr['id']
    for col, value in dbAttr.items():
        ncol = klass.sqlmeta.columns.get(col)
        if ncol:
            if ncol._sqliteType() == 'TIMESTAMP':
                date, time = value.split(' ')
                year, month, day = date.split('-')
                hour, minute, second = time.split(':')
                year = int(year)
                month = int(month)
                day = int(day)
                hour = int(hour)
                minute = int(minute)
                second = int(second)
                dbAttr[col] = datetime(year, month, day, hour, minute, second)
        else:
            del dbAttr[col]


class ItemContainerContentCopier:

    def __init__(self, cur, id):
        self.dbAttr = {}
        cur.execute('SELECT * from item_container_content WHERE id = %i LIMIT 1;' % id)
        for name, value in zip(WSCHEMA['ItemContainerContent'], cur.fetchone()):
            self.dbAttr[str(name)] = value

        contentID = self.dbAttr.get('contentID', -1)
        if contentID == -1:
            self.content = None
        else:
            self.content = ItemCopier(cur, contentID)
        return

    def install(self, item):
        if not self.content:
            return
        else:
            FilterColumns(ItemContainerContent, self.dbAttr)
            container = self.content.install(None)
            if container:
                self.dbAttr['contentID'] = container.id
                self.dbAttr['itemID'] = item.id
                ItemContainerContent(**self.dbAttr)
            return


class ItemVariantCopier:

    def __init__(self, cur, id):
        self.dbAttr = {}
        cur.execute('SELECT * from item_variant WHERE id = %i LIMIT 1;' % id)
        for name, value in zip(WSCHEMA['ItemVariant'], cur.fetchone()):
            self.dbAttr[str(name)] = value

    def install(self, item):
        FilterColumns(ItemVariant, self.dbAttr)
        self.dbAttr['itemID'] = item.id
        ItemVariant(**self.dbAttr)


class ItemCopier:

    def __init__(self, cur, itemID, bank = False):
        self.dbAttr = {}
        cur.execute('SELECT * from item WHERE id=? LIMIT 1;', (itemID,))
        for name, value in zip(WSCHEMA['Item'], cur.fetchone()):
            self.dbAttr[str(name)] = value

        protoID = self.dbAttr.get('itemProtoID', -1)
        cur.execute('select name from item_proto where id=? LIMIT 1;', (protoID,))
        self.protoName = cur.fetchone()[0]
        variants = self.variants = []
        cur.execute('select id from item_variant where item_id=?;', (itemID,))
        for r in cur.fetchall():
            f = ItemVariantCopier(cur, r[0])
            variants.append(f)

        content = self.content = []
        try:
            cur.execute('SELECT id FROM item_container_content WHERE item_id=?;', (itemID,))
            for cc in cur.fetchall():
                c = ItemContainerContentCopier(cur, cc[0])
                content.append(c)

        except:
            pass

    def install(self, owner, bank = False):
        try:
            ip = ItemProto.byName(self.protoName)
        except:
            print 'Item: %s no longer exists' % self.protoName
            return

        FilterColumns(Item, self.dbAttr)
        self.dbAttr['itemProtoID'] = ip.id
        if owner:
            if bank:
                self.dbAttr['characterID'] = None
                self.dbAttr['playerID'] = owner.id
            else:
                self.dbAttr['characterID'] = owner.id
                self.dbAttr['playerID'] = None
        else:
            self.dbAttr['characterID'] = None
            self.dbAttr['playerID'] = None
        if not self.dbAttr['stackCount']:
            if ip.stackMax > 1:
                self.dbAttr['stackCount'] = ip.stackDefault
            else:
                self.dbAttr['stackCount'] = 1
        item = Item(**self.dbAttr)
        for iv in self.variants:
            iv.install(item)

        for cc in self.content:
            cc.install(item)

        return item


class CharacterFactionCopier:

    def __init__(self, cur, id):
        self.dbAttr = {}
        cur.execute('SELECT * from character_faction WHERE id = %i LIMIT 1;' % id)
        for name, value in zip(WSCHEMA['CharacterFaction'], cur.fetchone()):
            self.dbAttr[str(name)] = value

        cur.execute('select name from faction where id = %i LIMIT 1;' % self.dbAttr['factionID'])
        self.factionName = cur.fetchone()[0]

    def install(self, char):
        try:
            f = Faction.byName(self.factionName)
        except:
            print 'Faction: %s no longer exists' % self.factionName
            return

        FilterColumns(CharacterFaction, self.dbAttr)
        self.dbAttr['characterID'] = char.id
        self.dbAttr['factionID'] = f.id
        CharacterFaction(**self.dbAttr)


class PlayerMonsterSpawnCopier:

    def __init__(self, cur, id):
        self.dbAttr = {}
        cur.execute('SELECT * from player_monster_spawn WHERE id = %i LIMIT 1;' % id)
        for name, value in zip(WSCHEMA['PlayerMonsterSpawn'], cur.fetchone()):
            self.dbAttr[str(name)] = value

    def install(self, player):
        FilterColumns(PlayerMonsterSpawn, self.dbAttr)
        self.dbAttr['playerID'] = player.id
        PlayerMonsterSpawn(**self.dbAttr)


class CharacterAdvancementCopier:

    def __init__(self, cur, id):
        self.dbAttr = {}
        cur.execute('SELECT * from character_advancement WHERE id = %i LIMIT 1;' % id)
        for name, value in zip(WSCHEMA['CharacterAdvancement'], cur.fetchone()):
            self.dbAttr[str(name)] = value

        protoID = self.dbAttr.get('advancementProtoID', -1)
        cur.execute('select name from advancement_proto where id = %i LIMIT 1;' % protoID)
        self.protoName = cur.fetchone()[0]

    def install(self, char):
        try:
            adv = AdvancementProto.byName(self.protoName)
        except:
            print 'Advancement: %s no longer exists' % self.protoName
            return

        FilterColumns(CharacterAdvancement, self.dbAttr)
        self.dbAttr['advancementProtoID'] = adv.id
        self.dbAttr['characterID'] = char.id
        CharacterAdvancement(**self.dbAttr)


class CharacterVaultItemCopier:

    def __init__(self, cur, id):
        self.dbAttr = {}
        cur.execute('SELECT * from character_vault_item WHERE id = %i LIMIT 1;' % id)
        for name, value in zip(WSCHEMA['CharacterVaultItem'], cur.fetchone()):
            self.dbAttr[str(name)] = value

        self.item = ItemCopier(cur, self.dbAttr['itemID'])

    def install(self, char):
        FilterColumns(CharacterVaultItem, self.dbAttr)
        self.dbAttr['characterID'] = char.id
        item = self.item.install(None)
        if not item:
            return
        else:
            self.dbAttr['itemID'] = item.id
            CharacterVaultItem(**self.dbAttr)
            return


class CharacterSkillCopier:

    def __init__(self, cur, id):
        self.dbAttr = {}
        cur.execute('SELECT * from character_skill WHERE id = %i LIMIT 1;' % id)
        for name, value in zip(WSCHEMA['CharacterSkill'], cur.fetchone()):
            self.dbAttr[str(name)] = value

    def install(self, char):
        FilterColumns(CharacterSkill, self.dbAttr)
        self.dbAttr['characterID'] = char.id
        CharacterSkill(**self.dbAttr)


class CharacterDialogChoiceCopier:

    def __init__(self, cur, id):
        self.dbAttr = {}
        cur.execute('SELECT * from character_dialog_choice WHERE id = %i LIMIT 1;' % id)
        for name, value in zip(WSCHEMA['CharacterDialogChoice'], cur.fetchone()):
            self.dbAttr[str(name)] = value

    def install(self, char):
        FilterColumns(CharacterDialogChoice, self.dbAttr)
        self.dbAttr['characterID'] = char.id
        CharacterDialogChoice(**self.dbAttr)


class CharacterSpellCopier:

    def __init__(self, cur, id):
        self.dbAttr = {}
        cur.execute('SELECT * from character_spell WHERE id = %i LIMIT 1;' % id)
        for name, value in zip(WSCHEMA['CharacterSpell'], cur.fetchone()):
            self.dbAttr[str(name)] = value

        protoID = self.dbAttr.get('spellProtoID', -1)
        cur.execute('select name from spell_proto where id = %i LIMIT 1;' % protoID)
        self.protoName = cur.fetchone()[0]

    def install(self, char):
        try:
            sp = SpellProto.byName(self.protoName)
        except:
            print 'Spell: %s no longer exists' % self.protoName
            return

        FilterColumns(CharacterSpell, self.dbAttr)
        self.dbAttr['spellProtoID'] = sp.id
        self.dbAttr['characterID'] = char.id
        CharacterSpell(**self.dbAttr)


class SpellStoreCopier:

    def __init__(self, cur, id):
        self.dbAttr = {}
        cur.execute('SELECT * from spell_store WHERE id = %i LIMIT 1;' % id)
        for name, value in zip(WSCHEMA['SpellStore'], cur.fetchone()):
            self.dbAttr[str(name)] = value

        protoID = self.dbAttr.get('spellProtoID', -1)
        cur.execute('select name from spell_proto where id = %i LIMIT 1;' % protoID)
        self.protoName = cur.fetchone()[0]

    def install(self, char):
        try:
            sp = SpellProto.byName(self.protoName)
        except:
            print 'Spell: %s no longer exists' % self.protoName
            return

        FilterColumns(SpellStore, self.dbAttr)
        self.dbAttr['spellProtoID'] = sp.id
        self.dbAttr['characterID'] = char.id
        SpellStore(**self.dbAttr)


class SpawnStatCopier:

    def __init__(self, cur, id):
        self.dbAttr = {}
        cur.execute('SELECT * from spawn_stat WHERE id = %i LIMIT 1;' % id)
        for name, value in zip(WSCHEMA['SpawnStat'], cur.fetchone()):
            self.dbAttr[str(name)] = value

    def install(self, spawn):
        FilterColumns(SpawnStat, self.dbAttr)
        self.dbAttr['spawnID'] = spawn.id
        s = SpawnStat(**self.dbAttr)
        return s


class SpawnResistanceCopier:

    def __init__(self, cur, id):
        self.dbAttr = {}
        cur.execute('SELECT * from spawn_resistance WHERE id = %i LIMIT 1;' % id)
        for name, value in zip(WSCHEMA['SpawnResistance'], cur.fetchone()):
            self.dbAttr[str(name)] = value

    def install(self, spawn):
        FilterColumns(SpawnResistance, self.dbAttr)
        self.dbAttr['spawnID'] = spawn.id
        s = SpawnResistance(**self.dbAttr)
        return s


class SpawnCopier:

    def __init__(self, cur, id):
        self.dbAttr = {}
        cur.execute('SELECT * from spawn WHERE id = %i LIMIT 1;' % id)
        for name, value in zip(WSCHEMA['Spawn'], cur.fetchone()):
            self.dbAttr[str(name)] = value

    def install(self):
        FilterColumns(Spawn, self.dbAttr)
        try:
            s = Spawn(**self.dbAttr)
        except:
            print 'Problem installing %s trying with an appended X to name' % self.dbAttr['name']
            self.dbAttr['name'] = self.dbAttr['name'] + 'X'
            try:
                s = Spawn(**self.dbAttr)
            except:
                raise Exception, 'Error'

        return s


class CharacterCopier:

    def __init__(self, cur, id):
        self.dbAttr = {}
        cur.execute('SELECT * from character WHERE id = %i LIMIT 1;' % id)
        for name, value in zip(WSCHEMA['Character'], cur.fetchone()):
            self.dbAttr[str(name)] = value

        spawnID = self.dbAttr.get('spawnID', -1)
        self.spawn = SpawnCopier(cur, spawnID)
        sresists = self.sresists = []
        cur.execute('select id from spawn_resistance where spawn_id = %i;' % spawnID)
        for r in cur.fetchall():
            f = SpawnResistanceCopier(cur, r[0])
            sresists.append(f)

        sstats = self.sstats = []
        cur.execute('select id from spawn_stat where spawn_id = %i;' % spawnID)
        for r in cur.fetchall():
            f = SpawnStatCopier(cur, r[0])
            sstats.append(f)

        advancements = self.advancements = []
        cur.execute('select id from character_advancement where character_id = %i;' % id)
        for r in cur.fetchall():
            f = CharacterAdvancementCopier(cur, r[0])
            advancements.append(f)

        skills = self.skills = []
        cur.execute('select id from character_skill where character_id = %i;' % id)
        for r in cur.fetchall():
            f = CharacterSkillCopier(cur, r[0])
            skills.append(f)

        spells = self.spells = []
        cur.execute('select id from character_spell where character_id = %i;' % id)
        for r in cur.fetchall():
            f = CharacterSpellCopier(cur, r[0])
            spells.append(f)

        vaultItems = self.vaultItems = []
        try:
            cur.execute('select id from character_vault_item where character_id = %i;' % id)
            for r in cur.fetchall():
                f = CharacterVaultItemCopier(cur, r[0])
                vaultItems.append(f)

        except:
            traceback.print_exc()

        factions = self.factions = []
        try:
            cur.execute('select id from character_faction where character_id = %i;' % id)
            for r in cur.fetchall():
                f = CharacterFactionCopier(cur, r[0])
                factions.append(f)

        except:
            traceback.print_exc()

        items = self.items = []
        cur.execute('select id from item where character_id = %i and (slot >= %i or slot < %i) and slot != -1;' % (id, RPG_SLOT_BANK_END, RPG_SLOT_BANK_BEGIN))
        for r in cur.fetchall():
            f = ItemCopier(cur, r[0])
            items.append(f)

        dc = self.dc = []
        try:
            cur.execute('select id from character_dialog_choice where character_id = %i;' % id)
            for r in cur.fetchall():
                f = CharacterDialogChoiceCopier(cur, r[0])
                dc.append(f)

        except:
            traceback.print_exc()

        spellStore = self.spellStore = []
        try:
            cur.execute('select id from spell_store where character_id = %i;' % id)
            for r in cur.fetchall():
                sps = SpellStoreCopier(cur, r[0])
                spellStore.append(sps)

        except:
            traceback.print_exc()

    def install(self, player):
        spawn = self.spawn.install()
        FilterColumns(Character, self.dbAttr)
        self.dbAttr['name'] = spawn.name
        self.dbAttr['spawnID'] = spawn.id
        self.dbAttr['playerID'] = player.id
        char = Character(**self.dbAttr)
        spawn.character = char
        spawn.playerName = player.publicName
        for a in self.sresists:
            a.install(spawn)

        for a in self.sstats:
            a.install(spawn)

        for a in self.advancements:
            a.install(char)

        for s in self.spells:
            s.install(char)

        for s in self.skills:
            s.install(char)

        for i in self.items:
            i.install(char)

        for i in self.vaultItems:
            i.install(char)

        for f in self.factions:
            f.install(char)

        for dc in self.dc:
            dc.install(char)

        for sps in self.spellStore:
            sps.install(char)


class PlayerCopier:

    def __init__(self, conn, id):
        self.dbAttr = {}
        cur = conn.cursor()
        bindZoneID = -1
        logZoneID = -1
        darknessBindZoneID = -1
        darknessLogZoneID = -1
        monsterBindZoneID = -1
        monsterLogZoneID = -1
        cur.execute('SELECT * from player WHERE id = %i LIMIT 1;' % id)
        for name, value in zip(WSCHEMA['Player'], cur.fetchone()):
            if name == 'bindZoneID':
                bindZoneID = value
            elif name == 'logZoneID':
                logZoneID = value
            elif name == 'darknessBindZoneID':
                darknessBindZoneID = value
            elif name == 'darknessLogZoneID':
                darknessLogZoneID = value
            elif name == 'monsterBindZoneID':
                monsterBindZoneID = value
            elif name == 'monsterLogZoneID':
                monsterLogZoneID = value
            self.dbAttr[str(name)] = value

        cur.execute('select name from Zone where id = %i LIMIT 1;' % bindZoneID)
        self.bindZone = cur.fetchone()[0]
        cur.execute('select name from Zone where id = %i LIMIT 1;' % logZoneID)
        self.logZone = cur.fetchone()[0]
        cur.execute('select name from Zone where id = %i LIMIT 1;' % darknessBindZoneID)
        self.darknessBindZone = cur.fetchone()[0]
        cur.execute('select name from Zone where id = %i LIMIT 1;' % darknessLogZoneID)
        self.darknessLogZone = cur.fetchone()[0]
        try:
            cur.execute('select name from Zone where id = %i LIMIT 1;' % monsterBindZoneID)
            self.monsterBindZone = cur.fetchone()[0]
            cur.execute('select name from Zone where id = %i LIMIT 1;' % monsterLogZoneID)
            self.monsterLogZone = cur.fetchone()[0]
        except:
            self.monsterLogZone = self.monsterBindZone = 'trinst'

        chars = self.characters = []
        cur.execute('select id from Character where player_id = %i;' % id)
        for r in cur.fetchall():
            c = CharacterCopier(cur, r[0])
            chars.append(c)

        mspawns = self.mspawns = []
        try:
            cur.execute('select id from player_monster_spawn where player_id = %i;' % id)
            for r in cur.fetchall():
                f = PlayerMonsterSpawnCopier(cur, r[0])
                mspawns.append(f)

        except:
            traceback.print_exc()

        items = self.items = []
        cur.execute('select id from item where player_id = %i and slot >= %i and slot < %i;' % (id, RPG_SLOT_BANK_BEGIN, RPG_SLOT_BANK_END))
        for r in cur.fetchall():
            f = ItemCopier(cur, r[0])
            items.append(f)

        cur.close()

    def install(self):
        if not FROMGAME:
            print 'Installing Player: %s' % self.dbAttr['publicName']
        try:
            bindZone = Zone.byName(self.bindZone)
        except:
            bindZone = Zone.byName('trinst')
            self.dbAttr['bindTransformInternal'] = '17.699 -288.385 121.573 0 0 1 35.9607'

        try:
            logZone = Zone.byName(self.logZone)
        except:
            logZone = Zone.byName('trinst')
            self.dbAttr['logTransformInternal'] = '17.699 -288.385 121.573 0 0 1 35.9607'

        try:
            darknessBindZone = Zone.byName(self.darknessBindZone)
        except:
            darknessBindZone = Zone.byName('kauldur')
            self.dbAttr['darknessBindTransformInternal'] = '-203.48 -395.96 150.1 0 0 1 38.92'

        try:
            darknessLogZone = Zone.byName(self.darknessLogZone)
        except:
            darknessLogZone = Zone.byName('kauldur')
            self.dbAttr['darknessLogTransformInternal'] = '-203.48 -395.96 150.1 0 0 1 38.92'

        try:
            monsterBindZone = Zone.byName(self.monsterBindZone)
        except:
            monsterBindZone = Zone.byName('trinst')
            self.dbAttr['monsterBindTransformInternal'] = '-169.032 -315.986 150.9353 0 0 1 10.681'

        try:
            monsterLogZone = Zone.byName(self.monsterLogZone)
        except:
            monsterLogZone = Zone.byName('trinst')
            self.dbAttr['monsterLogTransformInternal'] = '-169.032 -315.986 150.9353 0 0 1 10.681'

        self.dbAttr['bindZoneID'] = bindZone.id
        self.dbAttr['logZoneID'] = logZone.id
        self.dbAttr['darknessBindZoneID'] = darknessBindZone.id
        self.dbAttr['darknessLogZoneID'] = darknessLogZone.id
        self.dbAttr['monsterBindZoneID'] = monsterBindZone.id
        self.dbAttr['monsterLogZoneID'] = monsterLogZone.id
        FilterColumns(Player, self.dbAttr)
        player = Player(**self.dbAttr)
        for c in self.characters:
            c.install(player)

        for f in self.mspawns:
            f.install(player)

        for i in self.items:
            i.install(player, bank=True)


class UserCopier:

    def __init__(self, conn, id):
        self.dbAttr = {}
        cur = conn.cursor()
        cur.execute('SELECT * from user WHERE id = %i LIMIT 1;' % id)
        for name, value in zip(WSCHEMA['User'], cur.fetchone()):
            self.dbAttr[str(name)] = value

        self.roles = []
        cur.execute('select distinct name from role where id in (select role_id from role_user where user_id = %i);' % id)
        for name in cur.fetchall():
            self.roles.append(name[0])

        cur.close()

    def install(self):
        if self.dbAttr['name'] == 'ZoneServer':
            return
        FilterColumns(User, self.dbAttr)
        user = User(**self.dbAttr)
        for r in self.roles:
            try:
                role = Role.byName(r)
            except:
                print 'Role: %s no longer exists!' % r
                continue

            user.addRole(role)


def QuerySchema(wconn):
    for t in TABLES:
        cols = WSCHEMA[t] = []
        for col in wconn.execute('PRAGMA table_info(%s);' % mixedToUnder(t)).fetchall():
            cols.append(str(underToMixed(col[1])))


def WorldUpdate(worldPath, baselinePath, fromgame = False, force = False):
    global FORCE
    global FROMGAME
    FROMGAME = fromgame
    FORCE = force
    try:
        result = CheckWorld(worldPath, baselinePath)
    except:
        traceback.print_exc()
        return -1

    if result != 1:
        return result
    else:
        try:
            if FROMGAME:
                TGECall('MessagePopup', 'Updating World...', 'Please wait...')
                TGEEval('Canvas.repaint();')
            WCONN = sqlite.connect(worldPath)
            QuerySchema(WCONN)
            players = []
            for r in WCONN.execute('select id from Player;').fetchall():
                pc = PlayerCopier(WCONN, r[0])
                players.append(pc)

            users = []
            for r in WCONN.execute('select id from user;').fetchall():
                u = UserCopier(WCONN, r[0])
                users.append(u)

            WCONN.close()
            shutil.copyfile(worldPath, '%s.bak' % worldPath)
            shutil.copyfile(baselinePath, '%s.new' % worldPath)
            from mud.utils import getSQLiteURL
            DATABASE = '%s.new' % worldPath
            SetDBConnection(getSQLiteURL(DATABASE))
            tran = Player._connection.transaction()
            cursor = Player._connection.getConnection().cursor()
            for u in users:
                u.install()

            for p in players:
                p.install()

            cursor.close()
            tran.commit()
            SetDBConnection(None)
            shutil.copyfile('%s.new' % worldPath, worldPath)
        except:
            traceback.print_exc()
            return -1

        if FROMGAME:
            TGECall('MessagePopup', 'Loading World...', 'Please wait...')
            TGEEval('Canvas.repaint();')
        return 0


_underToMixedRE = re.compile('_(.)')

def underToMixed(name):
    if name.endswith('_id'):
        return underToMixed(name[:-3] + 'ID')
    return _underToMixedRE.sub(lambda m: m.group(1).upper(), name)


_mixedToUnderRE = re.compile('[A-Z]+')

def mixedToUnder(s):
    if s.endswith('ID'):
        return mixedToUnder(s[:-2] + '_id')
    trans = _mixedToUnderRE.sub(mixedToUnderSub, s)
    if trans.startswith('_'):
        trans = trans[1:]
    return trans


def mixedToUnderSub(match):
    m = match.group(0).lower()
    if len(m) > 1:
        return '_%s_%s' % (m[:-1], m[-1])
    else:
        return '_%s' % m