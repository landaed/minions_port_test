# Embedded file name: mud\world\loot.pyo
from mud.common.persistent import Persistent
from mud.world.core import *
from mud.world.defines import *
from mud.world.item import getTomeAtLevelForScroll, ItemProto
from mud.world.itemvariants import GenVariantItem
from mud.world.shared.sounddefs import *
from datetime import date
from random import randint
from sqlobject import *
from time import strftime, strptime, time as sysTime
import traceback
ZONE_POTIONS = {'anidaenforest': 'Potion of Anidaen Gate',
 'arctic': 'Potion of Frostbite Gate',
 'jakrethjungle': 'Potion of Jakreth Gate',
 'talrimhills': 'Potion of Talrim Gate',
 'desertmohrum': 'Potion of Mohrum Gate',
 'trinst': 'Potion of Trinst Gate',
 'kauldur': 'Potion of Kauldur Gate',
 'swamp': 'Potion of Swamp Gate',
 'templesoflinaar': 'Potion of Temples of Linaar Gate',
 'hollow': 'Potion of Haunted Hollow Gate'}
ZONE_ENCHANTINGITEMS = {'desertmohrum': ['Sandstone of Clarity',
                  'Sandstone of Strength',
                  'Sandstone of Health',
                  'Sandstone of Ether',
                  'Sandstone of Endurance',
                  'Sandstone of the Sphinx'],
 'mountain': ['Coal of Insight',
              'Coal of Fiery Protection',
              'Coal of Health',
              'Coal of Ether',
              'Coal of Endurance',
              'Coal of the Dwarven King'],
 'arctic': ['Icy Shard of Instinct',
            'Icy Shard of the Arcane',
            'Icy Shard of Cold Protection',
            'Icy Shard of Health',
            'Icy Shard of Ether',
            'Icy Shard of Endurance',
            'Icy Shard of Volsh'],
 'anidaenforest': ['Bark of Magic Protection',
                   'Bark of Health',
                   'Bark of Ether',
                   'Bark of Endurance',
                   'Bark of Speed'],
 'talrimhills': ['Limestone of Constitution',
                 'Limestone of Electrical Resistance',
                 'Limestone of Health',
                 'Limestone of Ether',
                 'Limestone of Endurance',
                 'Limestone of Lightning'],
 'hazerothkeep': ['Quartz of Nimbleness',
                  'Quartz of Physical Protection',
                  'Quartz of Health',
                  'Quartz of Ether',
                  'Quartz of Endurance',
                  'Quartz of the Warling Cleric'],
 'wasteland': ['Blighted Shard of Quickness',
               'Blighted Shard of Defense',
               'Blighted Shard of Health',
               'Blighted Shard of Ether',
               'Blighted Shard of Endurance',
               'Blighted Shard of Aelieas'],
 'jakrethjungle': ['Vine of Poison Resist',
                   'Vine of Disease Resist',
                   'Vine of Health',
                   'Vine of Ether',
                   'Vine of Endurance',
                   'Vine of the Cavebear'],
 'swamp': ['Muck-Covered Stone of Acidity',
           'Muck-Covered Stone of Health',
           'Muck-Covered Stone of Ether',
           'Muck-Covered Stone of Endurance',
           'Muck-Covered Stone of the Ghoul Slayer']}
ENCHANT_QualityDropDistribution = [0,
 50,
 75,
 88,
 94,
 97,
 99,
 100]
STAT_POTIONS = ('Strength',
 'Mind',
 'Reflex',
 'Agility',
 'Body',
 'Wisdom',
 'Mysticism',
 'Dexterity')
WILDTOMES = ('Paladin',
 'Cleric',
 'Necromancer',
 'Tempest',
 'Wizard',
 'Shaman',
 'Revealer',
 'Druid',
 'Ranger',
 'Bard',
 'Doom Knight')
ZONE_SEASONALITEMS = {'arctic': [],
 'anidaenforest': ['Spring Leaf'],
 'desertmohrum': ['Parched Bone'],
 'hazerothkeep': [],
 'jakrethjungle': [],
 'mountain': ['Wheat Panicle'],
 'swamp': [],
 'talrimhills': [],
 'trinst': ['Wheat Panicle'],
 'wasteland': ['Parched Bone'],
 'kauldur': ['Parched Bone']}

class LootItem(Persistent):
    lootProto = ForeignKey('LootProto')
    itemProto = ForeignKey('ItemProto')
    freq = IntCol(default=RPG_FREQ_ALWAYS)
    flags = IntCol(default=0)


class LootProto(Persistent):
    spawns = MultipleJoin('Spawn')
    lootItems = MultipleJoin('LootItem')
    tin = IntCol(default=0L)

    def _init(self, *args, **kw):
        Persistent._init(self, *args, **kw)
        self.itemDetails = dict(((item.itemProto.name, item.flags) for item in self.lootItems))


class Loot():

    def initRandomLoot():
        randomProtos = Loot.randomItemProtos = []
        spellScrolls = Loot.spellScrolls = {}
        protos = {}
        con = ItemProto._connection.getConnection()
        for id, spell_proto_id in con.execute('SELECT id,spell_proto_id FROM item_proto WHERE spell_proto_id OR (rating = 1 AND NOT flags & %d)' % RPG_ITEM_SOULBOUND):
            ip = protos.setdefault(id, ItemProto.get(id))
            if spell_proto_id:
                for classname, level in con.execute('SELECT classname,level FROM spell_class WHERE spell_proto_id = %d' % spell_proto_id):
                    spellScrolls.setdefault(classname, {}).setdefault(level, []).append(ip)

            else:
                randomProtos.append(ip)

        uloot = {}
        for itemid, freq in con.execute('SELECT DISTINCT item_proto_id,freq FROM loot_item WHERE freq >= %d AND loot_proto_id IN (SELECT DISTINCT loot_proto_id FROM spawn WHERE NOT flags & %d)' % (RPG_FREQ_COMMON, RPG_SPAWN_UNIQUE)):
            if con.execute('SELECT id FROM item_slot WHERE item_proto_id = %d LIMIT 1' % itemid).fetchone():
                if freq > uloot.get(itemid, 0):
                    uloot[itemid] = freq

        uniqueProtos = Loot.uniqueItemProtos = {}
        for itemid, freq in uloot.iteritems():
            ip = protos.setdefault(itemid, ItemProto.get(itemid))
            level = ip.level
            for cl in ip.classes:
                if cl.level > level:
                    level = cl.level

            if level == 1:
                continue
            uniqueProtos.setdefault(level, []).append((freq, ip))

    initRandomLoot = staticmethod(initRandomLoot)

    def __init__(self, mob, lootProto):
        self.mob = mob
        self.lootProto = lootProto
        self.items = []
        self.tin = 0L
        self.fleshDone = False
        self.corpseLootGenerated = False
        self.pickPocketTimer = 0

    def giveMoney(self, player):
        gotsome = False
        if self.tin:
            gotsome = True
            player.alliance.giveMoney(player, self.tin)
        self.tin = 0L
        return gotsome

    def generateCorpseLoot(self):
        loot = self.items
        if self.corpseLootGenerated:
            return self.tin or len(loot)
        spawn = self.mob.spawn
        proto = self.lootProto
        self.corpseLootGenerated = True
        if proto:
            if proto.tin:
                self.tin = randint(0, proto.tin)
            for lootitem in proto.lootItems:
                if not len(lootitem.itemProto.slots):
                    freq = lootitem.freq
                    r = 0
                    if freq > 1:
                        r = randint(0, freq - 1)
                    if not r:
                        iproto = lootitem.itemProto
                        if iproto.startDayRL or iproto.endDayRL:
                            startDayRL = date(*strptime('%s-%s' % (iproto.startDayRL if iproto.startDayRL else '1-1', strftime('%Y')), '%m-%d-%Y')[0:3])
                            endDayRL = date(*strptime('%s-%s' % (iproto.endDayRL if iproto.endDayRL else '1-1', strftime('%Y')), '%m-%d-%Y')[0:3])
                            todayRL = date.today()
                            if endDayRL < startDayRL:
                                if endDayRL < todayRL < startDayRL:
                                    continue
                            elif not startDayRL <= todayRL <= endDayRL:
                                continue
                        item = iproto.createInstance()
                        GenVariantItem(item, self.mob.plevel)
                        item.slot = -1
                        loot.append(item)
                    if len(loot) == 16:
                        break

        if len(loot) < 16 and ZONE_SEASONALITEMS.has_key(self.mob.zone.zone.name):
            if not randint(0, 3):
                tempSeasonalItemlist = []
                zoneSeasonalItemList = ZONE_SEASONALITEMS[self.mob.zone.zone.name]
                if len(zoneSeasonalItemList) > 0:
                    for eachSeasonalItem in zoneSeasonalItemList:
                        try:
                            testItem = ItemProto.byName(eachSeasonalItem)
                        except SQLObjectNotFound:
                            continue

                        if testItem.startDayRL or testItem.endDayRL:
                            startDayRL = date(*strptime('%s-%s' % (testItem.startDayRL if testItem.startDayRL else '1-1', strftime('%Y')), '%m-%d-%Y')[0:3])
                            endDayRL = date(*strptime('%s-%s' % (testItem.endDayRL if testItem.endDayRL else '1-1', strftime('%Y')), '%m-%d-%Y')[0:3])
                            todayRL = date.today()
                            if endDayRL < startDayRL:
                                if endDay < todayRL < startDayRL:
                                    continue
                            elif not startDayRL <= todayRL <= endDayRL:
                                continue
                        tempSeasonalItemlist.append(testItem)

                    if len(tempSeasonalItemlist) > 0:
                        seasonalItem = tempSeasonalItemlist[randint(0, len(tempSeasonalItemlist) - 1)]
                        itemInstance = seasonalItem.createInstance()
                        itemInstance.slot = -1
                        loot.append(itemInstance)
        if len(loot) < 16:
            num = randint(0, int(spawn.plevel / 10) + 1)
            for x in xrange(0, num):
                if randint(0, 3):
                    continue
                iproto = Loot.randomItemProtos[randint(0, len(Loot.randomItemProtos) - 1)]
                item = iproto.createInstance()
                GenVariantItem(item, self.mob.plevel)
                item.slot = -1
                loot.append(item)
                if len(loot) == 16:
                    break

        if len(loot) < 16:
            chance = 35 - spawn.plevel / 3
            if not randint(0, chance):
                try:
                    zpotion = ZONE_POTIONS[self.mob.zone.zone.name]
                    zpotion = ItemProto.byName(zpotion)
                    item = zpotion.createInstance()
                    item.slot = -1
                    loot.append(item)
                except:
                    pass

        if len(loot) < 16:
            chance = 35 - spawn.plevel / 4
            if not randint(0, chance):
                try:
                    p = ItemProto.byName('Moon Powder')
                    item = p.createInstance()
                    item.slot = -1
                    loot.append(item)
                except:
                    traceback.print_exc()

        num = 1
        if self.mob.uniqueVariant:
            num = 2
        for x in xrange(0, num):
            if len(loot) < 16:
                chance = (110 - spawn.plevel) / 2
                if not randint(0, chance):
                    try:
                        index = randint(0, len(STAT_POTIONS) - 1)
                        stat = STAT_POTIONS[index]
                        potion = 'Potion of %s' % stat
                        if spawn.plevel >= 25:
                            chance = (110 - spawn.plevel) / 3
                            if not randint(0, chance):
                                potion = 'Elixir of %s' % stat
                        potion = ItemProto.byName(potion)
                        item = potion.createInstance()
                        item.slot = -1
                        loot.append(item)
                    except:
                        traceback.print_exc()

        num = 2 if self.mob.uniqueVariant else 1
        for x in xrange(0, num):
            if len(loot) < 16:
                if not randint(0, 4):
                    scrolls = set()
                    if not randint(0, 2):
                        wclass = WILDTOMES[randint(0, len(WILDTOMES) - 1)]
                        wlevel = spawn.plevel
                        classes = ((spawn.pclassInternal, spawn.plevel),
                         (spawn.sclassInternal, spawn.slevel),
                         (spawn.tclassInternal, spawn.tlevel),
                         (wclass, wlevel))
                    else:
                        classes = ((spawn.pclassInternal, spawn.plevel), (spawn.sclassInternal, spawn.slevel), (spawn.tclassInternal, spawn.tlevel))
                    for cl, level in classes:
                        spellScrolls = Loot.spellScrolls.get(cl)
                        if spellScrolls:
                            for x in xrange(max(1, level - 5), level + 11):
                                try:
                                    scrolls.update(spellScrolls[x])
                                except KeyError:
                                    continue

                    scroll = None
                    if len(scrolls) == 1:
                        scroll = scrolls.pop()
                    elif len(scrolls) > 1:
                        scroll = list(scrolls)[randint(0, len(scrolls) - 1)]
                    if scroll:
                        v = (0, 30, 55, 75, 85, 90, 94, 97, 101)
                        x = randint(0, 100)
                        for z in xrange(0, 9):
                            if x < v[z]:
                                break

                        x = z + 1
                        if self.mob.uniqueVariant:
                            x += 5
                            if x > 10:
                                x = 10
                        item = getTomeAtLevelForScroll(scroll, x)
                        item.slot = -1
                        item.itemInfo.reset()
                        loot.append(item)

        num = 2 if self.mob.uniqueVariant else 1
        for x in xrange(0, num):
            if len(loot) < 16:
                chance = (110 - spawn.plevel) / 2
                if not randint(0, chance):
                    try:
                        iname = 'Scroll of Learning'
                        if spawn.plevel >= 60:
                            chance = (110 - spawn.plevel) / 3
                            if not randint(0, chance):
                                iname = 'Book of Learning'
                        book = ItemProto.byName(iname)
                        item = book.createInstance()
                        item.slot = -1
                        loot.append(item)
                    except:
                        traceback.print_exc()

        if len(loot) < 16 and self.mob.uniqueVariant:
            x = max(1, spawn.plevel - 20)
            items = {}
            uniqueProtos = Loot.uniqueItemProtos
            for level in xrange(x, spawn.plevel + 1):
                try:
                    for freq, ip in uniqueProtos[level]:
                        items.setdefault(freq, []).append(ip)

                except KeyError:
                    continue

            if len(items):
                for x in xrange(3):
                    ip = None
                    if not randint(0, 2):
                        for freq in sorted(items.iterkeys(), reverse=True):
                            if not randint(0, freq):
                                if len(items[freq]) == 1:
                                    ip = items[freq][0]
                                    break
                                else:
                                    ip = items[freq][randint(0, len(items[freq]) - 1)]
                                    break

                        if ip:
                            item = ip.createInstance()
                            item.slot = -1
                            loot.append(item)

        if len(loot) < 16:
            if not randint(0, RPG_FREQ_RARE):
                try:
                    zoneEnchItemList = ZONE_ENCHANTINGITEMS[self.mob.zone.zone.name]
                    enchQuality = 0
                    if not randint(0, RPG_FREQ_IMPOSSIBLE):
                        enchName = zoneEnchItemList[-1]
                        enchQuality = ENCHANT_QualityCount - 1
                    else:
                        enchName = zoneEnchItemList[randint(0, len(zoneEnchItemList) - 2)]
                        qualityCursor = randint(1, 100)
                        for qualityTester in xrange(ENCHANT_QualityCount):
                            if qualityCursor <= ENCHANT_QualityDropDistribution[qualityTester]:
                                break
                            enchQuality += 1

                    enchItem = ItemProto.byName(enchName)
                    item = enchItem.createInstance()
                    item.spellEnhanceLevel = enchQuality + 10
                    item.name = '%s %s' % (ENCHANT_QualityPrefix[enchQuality], item.name)
                    item.slot = -1
                    loot.append(item)
                except:
                    pass

        if len(loot) < 16:
            if not randint(0, RPG_FREQ_IMPOSSIBLE * 3):
                try:
                    p = ItemProto.byName('Essence of the Void')
                    item = p.createInstance()
                    item.slot = -1
                    loot.append(item)
                except:
                    traceback.print_exc()

        for item in loot:
            if not item.flags & RPG_ITEM_INDESTRUCTIBLE and item.repairMax > 0:
                if item.repairMax == 1:
                    item.repair = 1
                else:
                    item.repair = randint(1, item.repairMax)

        if len(loot):
            self.items = loot
            return True
        elif self.tin:
            return True
        else:
            return False

    def generateLoot(self):
        spawn = self.mob.spawn
        proto = self.lootProto
        self.items = loot = []
        if proto:
            for lootitem in proto.lootItems:
                if len(lootitem.itemProto.slots):
                    freq = lootitem.freq
                    r = 0
                    if freq > 1:
                        r = randint(0, freq - 1)
                    if not r:
                        iproto = lootitem.itemProto
                        item = iproto.createInstance()
                        GenVariantItem(item, self.mob.plevel)
                        item.slot = -1
                        loot.append(item)
                        if len(loot) == 16:
                            break


def GenerateLoot(mob):
    if mob.player or mob.master and not mob.spawn.lootProto:
        return
    mob.loot = Loot(mob, mob.spawn.lootProto)
    mob.loot.generateLoot()