# Embedded file name: mud\world\item.pyo
from mud.common.persistent import Persistent
from mud.world.defines import *
from mud.gamesettings import *
from mud.world.projectile import Projectile
from mud.world.spell import SpawnSpell, SpellProto
from mud.world.shared.playdata import ItemInfo
from mud.worlddocs.utils import GetTWikiName
from copy import copy
from math import ceil, floor
from random import randint
from sqlobject import *
import traceback

class ItemClassifier(Persistent):
    name = StringCol(alternateID=True)
    itemProtosInternal = RelatedJoin('ItemProto')
    itemContainerProtosInternal = RelatedJoin('ItemContainerProto')


class ItemContainerContent(Persistent):
    item = ForeignKey('Item')
    content = ForeignKey('Item')


class ItemContainerProto(Persistent):
    containerSize = IntCol(default=1)
    itemClassifiersInternal = RelatedJoin('ItemClassifier')
    contentFlagsRequired = IntCol(default=0)

    def _init(self, *args, **kw):
        Persistent._init(self, *args, **kw)


class ItemContainer():

    def __init__(self, item):
        self.item = item
        containerProto = item.itemProto.itemContainerProto
        if containerProto:
            self.containerSize = containerProto.containerSize
            self.contentTypes = [ it.name for it in containerProto.itemClassifiersInternal ]
            self.contentFlagsRequired = containerProto.contentFlagsRequired
        else:
            self.containerSize = 1
            self.contentTypes = []
            self.contentFlagsRequired = 0
        if item.item:
            self.content = [ ItemInstance(cc.content) for cc in item.item.containerContent ]
        else:
            self.content = []
        self.dirty = False

    def checkStack(self, item):
        if not item:
            return (False, None)
        else:
            stackMax = item.itemProto.stackMax
            if stackMax <= 1:
                return (False, None)
            useMax = item.itemProto.useMax
            if useMax > 1:
                if item.stackCount >= stackMax and item.useCharges >= useMax:
                    return (False, None)
                neededCharges = useMax * (item.stackCount - 1) + item.useCharges
                for citem in self.content:
                    if citem.name != item.name:
                        continue
                    freeCharges = useMax * (stackMax - item.stackCount + 1) - item.useCharges
                    if freeCharges <= 0:
                        continue
                    if freeCharges < neededCharges:
                        return (False, citem)
                    return (True, citem)
                else:
                    return (False, None)

            else:
                if item.stackCount >= stackMax:
                    return (False, None)
                for citem in self.content:
                    if citem.name != item.name:
                        continue
                    freeStack = stackMax - item.stackCount
                    if freeStack <= 0:
                        continue
                    if freeStack < item.stackCount:
                        return (False, citem)
                    return (True, citem)
                else:
                    return (False, None)

            return None

    def stackItem(self, item, candidate = None):
        if not item:
            return False
        else:
            if candidate and candidate.name != item.name:
                candidate = None
            if not candidate:
                fullyStack, candidate = self.checkStack(item)
                if not candidate:
                    return False
            switched, item1, item2 = candidate.doStack(item)
            success = not switched and not item2
            if success:
                self.dirty = True
            return success

    def checkItem(self, item, candidate = None, verbose = False):
        if not item:
            return False
        if verbose:
            if self.item.character:
                player = self.item.character.player
            elif self.item.player:
                player = self.item.player
            else:
                verbose = False
        if self.contentFlagsRequired != 0:
            if (item.flags ^ self.contentFlagsRequired) & self.contentFlagsRequired:
                if verbose:
                    player.sendGameText(RPG_MSG_GAME_DENIED, "<a:Item%s>%s</a> can't be stored in a <a:Item%s>%s</a>!\\n" % (GetTWikiName(item.name),
                     item.name,
                     GetTWikiName(self.item.name),
                     self.item.name))
                return False
        if len(self.contentTypes):
            for ctName in item.itemProto.itemTypes:
                if ctName in self.contentTypes:
                    break
            else:
                if verbose:
                    player.sendGameText(RPG_MSG_GAME_DENIED, "<a:Item%s>%s</a> can't be stored in a <a:Item%s>%s</a>!\\n" % (GetTWikiName(item.name),
                     item.name,
                     GetTWikiName(self.item.name),
                     self.item.name))
                return False

        fullyStack, citem = self.checkStack(item)
        if isinstance(candidate, list):
            candidate.append(citem)
        if not fullyStack and len(self.content) >= self.containerSize:
            if verbose:
                player.sendGameText(RPG_MSG_GAME_DENIED, "There's not enough space for the <a:Item%s>%s</a> in the <a:Item%s>%s</a>.\\n" % (GetTWikiName(item.name),
                 item.name,
                 GetTWikiName(self.item.name),
                 self.item.name))
            return False
        if verbose:
            player.sendGameText(RPG_MSG_GAME_GAINED, 'The <a:Item%s>%s</a> has been stowed away in the <a:Item%s>%s</a>.\\n' % (GetTWikiName(item.name),
             item.name,
             GetTWikiName(self.item.name),
             self.item.name))
        return True

    def insertItem(self, item, verbose = False):
        candidate = []
        if item.container:
            return False
        elif not self.checkItem(item, candidate, verbose):
            return False
        else:
            complete = False
            if len(candidate):
                complete = self.stackItem(item, candidate[0])
            if not complete:
                player = None
                if item.character:
                    player = item.character.player
                elif item.player:
                    player = item.player
                item.setCharacter(None)
                item.player = None
                item.slot = -1
                if player and player.cursorItem == item:
                    player.cursorItem = None
                    player.updateCursorItem(item)
                self.content.append(item)
            self.dirty = True
            return True

    def extractItem(self, item):
        try:
            self.content.remove(item)
        except ValueError:
            return None

        if item.item and self.item.item:
            con = ItemContainerContent._connection.getConnection()
            try:
                con.execute('DELETE FROM item_container_content WHERE item_id=? AND content_id=?;', (self.item.item.id, item.item.id))
            except:
                pass

        self.dirty = True
        return item

    def extractItemByIndex(self, itemIndex):
        try:
            return self.extractItem(self.content[itemIndex])
        except IndexError:
            return None

        return None

    def storeContents(self):
        backingStore = self.item.item
        if not backingStore:
            return
        currList = [ cc.content for cc in backingStore.containerContent ]
        for item in self.content:
            if item.flags & RPG_ITEM_ETHEREAL:
                continue
            if not item.item:
                item.storeToItem(True)
                ItemContainerContent(item=backingStore, content=item.item)
            elif item.item not in currList:
                ItemContainerContent(item=backingStore, content=item.item)


class ItemSoundProfile(Persistent):
    sndAttack1 = StringCol(default='')
    sndAttack2 = StringCol(default='')
    sndAttack3 = StringCol(default='')
    sndAttack4 = StringCol(default='')
    sndAttack5 = StringCol(default='')
    sndAttack6 = StringCol(default='')
    sndAttack7 = StringCol(default='')
    sndAttack8 = StringCol(default='')
    sndHit1 = StringCol(default='')
    sndHit2 = StringCol(default='')
    sndHit3 = StringCol(default='')
    sndHit4 = StringCol(default='')
    sndHit5 = StringCol(default='')
    sndHit6 = StringCol(default='')
    sndHit7 = StringCol(default='')
    sndHit8 = StringCol(default='')
    sndUse = StringCol(default='')
    sndEquip = StringCol(default='')

    def _init(self, *args, **kw):
        Persistent._init(self, *args, **kw)
        sndattribs = ['sndAttack', 'sndHit']
        for snd in sndattribs:
            num = 0
            for x in xrange(1, 5):
                if not getattr(self, snd + str(x)):
                    break
                num += 1

            setattr(self, 'numS' + snd[1:], num)

        sounds = self.sounds = {}
        sounds['sndAttack'] = self.numSndAttack
        sounds['sndHit'] = self.numSndHit

    def getSound(self, snd):
        w = self.sounds[snd]
        w = randint(1, w)
        return getattr(self, snd + str(w))


class ItemStat(Persistent):
    itemProto = ForeignKey('ItemProto')
    statname = StringCol()
    value = FloatCol()


class ItemSlot(Persistent):
    itemProto = ForeignKey('ItemProto')
    slot = IntCol()


class ItemRace(Persistent):
    itemProto = ForeignKey('ItemProto')
    racename = StringCol()


class ItemRealm(Persistent):
    itemProto = ForeignKey('ItemProto')
    realmname = IntCol()
    level = IntCol(default=0)


class ItemClass(Persistent):
    itemProto = ForeignKey('ItemProto')
    classname = StringCol()
    level = IntCol()


class ItemSpell(Persistent):
    itemProto = ForeignKey('ItemProto')
    spellProto = ForeignKey('SpellProto')
    trigger = IntCol(default=RPG_ITEM_TRIGGER_WORN)
    frequency = IntCol(default=RPG_FREQ_ALWAYS)
    duration = IntCol(default=0)


class ItemSpellTemp():

    def __init__(self, spellProto, trigger, frequency):
        self.spellProto = spellProto
        self.trigger = trigger
        self.frequency = frequency


class ItemSet(Persistent):
    itemProto = ForeignKey('ItemProto')
    itemSetProto = ForeignKey('ItemSetProto')
    contribution = StringCol()


class ItemProto(Persistent):
    name = StringCol(alternateID=True)
    flags = IntCol(default=0)
    itemClassifiersInternal = RelatedJoin('ItemClassifier')
    slotsInternal = MultipleJoin('ItemSlot')
    racesInternal = MultipleJoin('ItemRace')
    realmsInternal = MultipleJoin('ItemRealm')
    classesInternal = MultipleJoin('ItemClass')
    requiredClassNum = IntCol(default=1)
    requirementFlags = IntCol(default=RPG_ITEMREQUIREMENT_NORMAL)
    level = IntCol(default=1)
    statsInternal = MultipleJoin('ItemStat')
    spellsInternal = MultipleJoin('ItemSpell')
    food = IntCol(default=0)
    drink = IntCol(default=0)
    skill = StringCol(default='')
    desc = StringCol(default='')
    equipMessage = StringCol(default='')
    worthTin = IntCol(default=0L)
    startDayRL = StringCol(default='')
    endDayRL = StringCol(default='')
    useDestroy = BoolCol(default=True)
    useMax = IntCol(default=0)
    wpnRaceBane = StringCol(default='')
    wpnRaceBaneMod = FloatCol(default=0)
    wpnResistDebuff = IntCol(default=RPG_RESIST_PHYSICAL)
    wpnResistDebuffMod = IntCol(default=0)
    wpnDamage = FloatCol(default=0)
    wpnRate = FloatCol(default=0)
    wpnRange = FloatCol(default=0)
    projectile = StringCol(default='')
    speed = FloatCol(default=0)
    armor = IntCol(default=0)
    stackMax = IntCol(default=1)
    stackDefault = IntCol(default=1)
    repairMax = FloatCol(default=0)
    lifeTime = IntCol(default=0)
    expireMessage = StringCol(default='')
    items = MultipleJoin('Item')
    itemSetsInternal = MultipleJoin('ItemSet')
    bitmap = StringCol(default='')
    model = StringCol(default='')
    sndProfile = ForeignKey('ItemSoundProfile', default=None)
    material = StringCol(default='')
    spellProto = ForeignKey('SpellProto', default=None)
    light = FloatCol(default=0.0)
    craftConsumed = BoolCol(default=True)
    ingredientsInternal = MultipleJoin('RecipeIngredient')
    equippedParticle = StringCol(default='')
    equippedParticleTexture = StringCol(default='')
    itemContainerProto = ForeignKey('ItemContainerProto', default=None)
    effectDesc = StringCol(default='')
    rating = IntCol(default=0)
    noise = IntCol(default=0)
    wpnAmmunitionType = StringCol(default='')
    isAmmunitionType = StringCol(default='')
    weight = FloatCol(default=0)

    def _init(self, *args, **kw):
        Persistent._init(self, *args, **kw)
        self.raceList = None
        self.realmList = None
        self.slotList = None
        self.classList = None
        self.statList = None
        self.spellList = None
        self.itemSets = self.itemSetsInternal[:]
        self.ingredientList = None
        self.typeClassList = None
        return

    def _get_ingredients(self):
        if self.ingredientList != None:
            return self.ingredientList
        else:
            self.ingredientList = list(self.ingredientsInternal)
            return self.ingredientList

    def _get_races(self):
        if self.raceList != None:
            return self.raceList
        else:
            self.raceList = tuple((race.racename for race in self.racesInternal))
            return self.raceList

    def _get_realms(self):
        if self.realmList != None:
            return self.realmList
        else:
            self.realmList = list(self.realmsInternal)
            return self.realmList

    def _get_slots(self):
        if self.slotList != None:
            return self.slotList
        else:
            self.slotList = tuple((slot.slot for slot in self.slotsInternal))
            return self.slotList

    def _get_classes(self):
        if self.classList != None:
            return self.classList
        else:
            self.classList = list(self.classesInternal)
            return self.classList

    def _get_stats(self):
        if self.statList != None:
            return self.statList
        else:
            self.statList = list(self.statsInternal)
            return self.statList

    def _get_spells(self):
        if self.spellList != None:
            return self.spellList
        else:
            self.spellList = list(self.spellsInternal)
            return self.spellList

    def _get_itemTypes(self):
        if self.typeClassList != None:
            return self.typeClassList
        else:
            self.typeClassList = [ it.name for it in self.itemClassifiersInternal ]
            return self.typeClassList

    def createInstance(self, bitmapOverride = None, normalQuality = True):
        quality = RPG_QUALITY_EXCEPTIONAL
        repairMax = self.repairMax
        if not self.flags and not self.spellProto and len(self.slots):
            if normalQuality:
                quality = RPG_QUALITY_NORMAL
                repairMax = floor(repairMax * 0.8)
            elif self.stackMax <= 1:
                r = randint(0, 99)
                if r < 50:
                    quality = RPG_QUALITY_NORMAL
                    repairMax = floor(repairMax * 0.8)
                elif r < 65:
                    quality = RPG_QUALITY_CRUDDY
                    repairMax = floor(repairMax * 0.6)
                elif r < 85:
                    quality = RPG_QUALITY_SHODDY
                    repairMax = floor(repairMax * 0.7)
                elif r < 95:
                    quality = RPG_QUALITY_SUPERIOR
                    repairMax = floor(repairMax * 0.9)
        if self.flags & RPG_ITEM_INDESTRUCTIBLE:
            repairMax = 0
        elif self.repairMax > 0 and not repairMax:
            repairMax = 1
        else:
            repairMax = int(repairMax)
        repair = repairMax
        if self.stackMax > 1 and self.stackDefault > 1:
            stackCount = self.stackDefault
        else:
            stackCount = 1
        if bitmapOverride:
            bitmap = bitmapOverride
        else:
            bitmap = self.bitmap
        item = ItemInstance()
        item.name = self.name
        item.itemProto = self
        item.quality = quality
        item.repair = repair
        item.repairMax = repairMax
        item.lifeTime = self.lifeTime
        item.character = None
        item.stackCount = stackCount
        item.food = self.food
        item.drink = self.drink
        item.useCharges = self.useMax
        item.bitmap = bitmap
        if self.itemContainerProto:
            item.container = ItemContainer(item)
        item.refreshFromProto()
        return item


DAMAGELOOKUP = {'Fists': RPG_DMG_PUMMEL,
 '1H Pierce': RPG_DMG_PIERCING,
 '2H Pierce': RPG_DMG_PIERCING,
 '1H Impact': RPG_DMG_IMPACT,
 '2H Impact': RPG_DMG_IMPACT,
 '1H Cleave': RPG_DMG_CLEAVE,
 '2H Cleave': RPG_DMG_CLEAVE,
 '1H Slash': RPG_DMG_SLASHING,
 '2H Slash': RPG_DMG_SLASHING}

class Item(Persistent):
    name = StringCol()
    itemProto = ForeignKey('ItemProto')
    stackCount = IntCol(default=1)
    useCharges = IntCol(default=0)
    quality = IntCol(default=RPG_QUALITY_NORMAL)
    food = IntCol(default=0)
    drink = IntCol(default=0)
    repairMax = FloatCol(default=0)
    repair = FloatCol(default=0)
    lifeTime = IntCol(default=0)
    slot = IntCol(default=0)
    character = ForeignKey('Character', default=None)
    player = ForeignKey('Player', default=None)
    xpCoupon = IntCol(default=0)
    descOverride = StringCol(default='')
    levelOverride = IntCol(default=0)
    spellEnhanceLevel = IntCol(default=0)
    bitmap = StringCol(default='')
    hasVariants = BoolCol(default=False)
    variants = MultipleJoin('ItemVariant')
    crafted = BoolCol(default=False)
    containerContent = MultipleJoin('ItemContainerContent')

    def _init(self, *args, **kw):
        Persistent._init(self, *args, **kw)

    def expire(self):
        for v in self.variants:
            v.expire()

        for cc in self.containerContent:
            cc.content.expire()
            cc.expire()

        Persistent.expire(self)

    def destroySelf(self):
        for v in self.variants:
            v.destroySelf()

        for cc in self.containerContent:
            cc.content.destroySelf()
            cc.destroySelf()

        Persistent.destroySelf(self)


class ItemInstance():

    def __init__(self, item = None):
        self.worthIncreaseTin = 0
        self.procs = {}
        self.itemInfo = ItemInfo(self)
        if not item:
            self.item = None
            self.stackCount = 1
            self.useCharges = 0
            self.quality = RPG_QUALITY_NORMAL
            self.food = 0
            self.drink = 0
            self.repairMax = 0
            self.repair = 0
            self.lifeTime = 0
            self.slot = -1
            self.character = None
            self.player = None
            self.xpCoupon = 0
            self.descOverride = ''
            self.levelOverride = 0
            self.spellEnhanceLevel = 0
            self.bitmap = ''
            self.hasVariants = False
            self.variants = {}
            self.crafted = False
            self.container = None
        else:
            self.loadFromItem(item)
        return

    def loadFromItem(self, item):
        self.item = item
        self.name = item.name
        self.itemProto = item.itemProto
        self.stackCount = item.stackCount
        self.useCharges = item.useCharges
        self.quality = item.quality
        self.food = item.food
        self.drink = item.drink
        self.repairMax = item.repairMax
        self.repair = item.repair
        self.lifeTime = item.lifeTime
        self.slot = item.slot
        self.character = item.character
        self.player = item.player
        self.xpCoupon = item.xpCoupon
        self.descOverride = item.descOverride
        self.levelOverride = item.levelOverride
        self.spellEnhanceLevel = item.spellEnhanceLevel
        self.bitmap = item.bitmap
        self.hasVariants = item.hasVariants
        from itemvariants import ItemVariantsLoad
        ItemVariantsLoad(self)
        self.crafted = item.crafted
        if self.itemProto.itemContainerProto:
            self.container = ItemContainer(self)
        else:
            self.container = None
        self.refreshFromProto()
        return self

    def storeToItem(self, override = False):
        if not self.character and not self.player and not override:
            return
        if not self.item:
            self.item = Item(name=self.name, itemProto=self.itemProto)
        if 0 and RPG_SLOT_BANK_BEGIN <= self.slot < RPG_SLOT_BANK_END:
            print 'storeToItem %d: %s' % (self.slot, self.name)
        data = {'name': self.name,
         'stackCount': self.stackCount,
         'useCharges': self.useCharges,
         'quality': self.quality,
         'food': self.food,
         'drink': self.drink,
         'repairMax': self.repairMax,
         'repair': self.repair,
         'lifeTime': self.lifeTime,
         'slot': self.slot,
         'character': self.character,
         'player': self.player,
         'xpCoupon': self.xpCoupon,
         'descOverride': self.descOverride,
         'levelOverride': self.levelOverride,
         'spellEnhanceLevel': self.spellEnhanceLevel,
         'bitmap': self.bitmap,
         'hasVariants': self.hasVariants,
         'crafted': self.crafted}
        self.item.set(**data)
        from itemvariants import ItemVariantsSave
        ItemVariantsSave(self)
        if self.container:
            self.container.storeContents()

    def clone(self):
        proto = self.itemProto
        nitem = proto.createInstance()
        nitem.name = self.name
        nitem.quality = self.quality
        nitem.repair = self.repair
        nitem.repairMax = self.repairMax
        nitem.lifeTime = self.lifeTime
        nitem.stackCount = self.stackCount
        nitem.food = proto.food
        nitem.drink = proto.drink
        nitem.useCharges = proto.useMax
        nitem.bitmap = self.bitmap
        nitem.xpCoupon = self.xpCoupon
        nitem.descOverride = self.descOverride
        nitem.levelOverride = self.levelOverride
        nitem.spellEnhanceLevel = self.spellEnhanceLevel
        nitem.variants = copy(self.variants)
        return nitem

    def destroySelf(self):
        player = None
        if self.character:
            player = self.character.player
            mob = self.character.mob
            if mob:
                try:
                    del mob.itemRequireTick[self]
                except KeyError:
                    pass

                try:
                    del mob.itemFood[self]
                except KeyError:
                    pass

                try:
                    del mob.itemDrink[self]
                except KeyError:
                    pass

            try:
                if RPG_SLOT_WORN_END > self.slot >= RPG_SLOT_WORN_BEGIN:
                    mob.unequipItem(self.slot)
                elif mob.pet and RPG_SLOT_PET_END > self.slot >= RPG_SLOT_PET_BEGIN:
                    mob.pet.unequipItem(self.slot - RPG_SLOT_PET_BEGIN)
                self.character.items.remove(self)
            except ValueError:
                pass

        if self.player:
            player = self.player
            try:
                del self.player.bankItems[self.slot]
            except KeyError:
                pass

        if self.item:
            self.item.destroySelf()
            self.item = None
        if player:
            if self == player.cursorItem:
                player.cursorItem = None
                player.updateCursorItem(self)
            player.cinfoDirty = True
        return

    def clearVariants(self):
        self.variants = {}
        self.hasVariants = False

    def numVariants(self):
        num = 0
        for varList in self.variants.itervalues():
            if isinstance(varList, tuple):
                num += 1
            else:
                num += len(varList)

        return num

    def doStack(self, item):
        stackMax = self.itemProto.stackMax
        if not item or stackMax <= 1 or self.name != item.name:
            return (True, item, self)
        else:
            if not item.stackCount:
                item.stackCount = 1
            if not self.stackCount:
                self.stackCount = 1
            useMax = self.itemProto.useMax
            if useMax > 1:
                freeCharges = useMax * (stackMax - self.stackCount + 1) - self.useCharges
                if freeCharges <= 0:
                    return (True, item, self)
                neededCharges = useMax * (item.stackCount - 1) + item.useCharges
                if freeCharges > neededCharges:
                    freeCharges = neededCharges
                useCharges = freeCharges % useMax
                stackCount = freeCharges / useMax
                self.useCharges += useCharges
                item.useCharges -= useCharges
                if item.useCharges <= 0:
                    item.useCharges += useMax
                    item.stackCount -= 1
                if self.useCharges > useMax:
                    self.useCharges -= useMax
                    self.stackCount += 1
            else:
                stackCount = stackMax - self.stackCount
                if stackCount <= 0:
                    return (True, item, self)
                if stackCount > item.stackCount:
                    stackCount = item.stackCount
            self.stackCount += stackCount
            item.stackCount -= stackCount
            if item.stackCount <= 0:
                item.destroySelf()
                if useMax > 1:
                    self.itemInfo.refreshDict({'STACKCOUNT': self.stackCount,
                     'USECHARGES': self.useCharges})
                else:
                    self.itemInfo.refreshDict({'STACKCOUNT': self.stackCount})
                return (False, self, None)
            if useMax > 1:
                self.itemInfo.refreshDict({'STACKCOUNT': self.stackCount,
                 'USECHARGES': self.useCharges})
                item.itemInfo.refreshDict({'STACKCOUNT': item.stackCount,
                 'USECHARGES': item.useCharges})
            else:
                self.itemInfo.refreshDict({'STACKCOUNT': self.stackCount})
                item.itemInfo.refreshDict({'STACKCOUNT': item.stackCount})
            return (False, self, item)
            return None

    def doItemSpellUse(self, mob, proto):
        tgt = mob.target
        if proto.target == RPG_TARGET_SELF:
            tgt = mob
        if proto.target == RPG_TARGET_PARTY:
            tgt = mob
        if proto.target == RPG_TARGET_ALLIANCE:
            tgt = mob
        if proto.target == RPG_TARGET_PET:
            tgt = mob.pet
        if not tgt:
            return
        if proto.animOverride:
            mob.zone.simAvatar.mind.callRemote('playAnimation', mob.simObject.id, proto.animOverride)
        if len(proto.particleNodes):
            mob.zone.simAvatar.mind.callRemote('triggerParticleNodes', mob.simObject.id, proto.particleNodes)
        mod = 1.0
        if proto.projectile:
            p = Projectile(mob, mob.target)
            p.spellProto = proto
            p.launch()
        else:
            SpawnSpell(proto, mob, tgt, tgt.simObject.position, mod, proc=True)

    def use(self, mob):
        if self.wpnDamage and self.wpnRange and self.slot == RPG_SLOT_RANGED and mob.rangedReuse <= 0:
            mob.shootRanged()
            return
        else:
            player = mob.player
            if not self.isUseable(mob) or self.penalty:
                if player:
                    player.sendGameText(RPG_MSG_GAME_DENIED, '%s cannot currently use this %s.\\n' % (mob.name, self.name))
                return
            if mob.sleep > 0 or mob.stun > 0 or mob.isFeared:
                if player:
                    player.sendGameText(RPG_MSG_GAME_DENIED, '%s cannot use items while asleep, stunned, or feared.\\n' % mob.name)
                return
            if self.reuseTimer:
                if player:
                    player.sendGameText(RPG_MSG_GAME_DENIED, '%s cannot use this %s for another %i seconds.\\n' % (mob.name, self.name, self.reuseTimer))
                return
            if self.skill:
                if not mob.skillLevels.get(self.skill):
                    if player:
                        player.sendGameText(RPG_MSG_GAME_DENIED, '%s cannot use this %s as it requires the %s skill.\\n' % (mob.name, self.name, self.skill))
                    return
                try:
                    mskill = mob.mobSkillProfiles[self.skill]
                    self.reuseTimer = mskill.reuseTime
                except:
                    self.reuseTimer = 60

                mob.itemRequireTick[self] = self.reuseTimer
            else:
                self.reuseTimer = 0
            self.itemInfo.refresh()
            if player:
                char = mob.character
                spellProto = self.itemProto.spellProto
                if spellProto:
                    if self.spellEnhanceLevel:
                        for s in char.spells:
                            if s.spellProto == spellProto:
                                if s.level >= self.spellEnhanceLevel:
                                    player.sendGameText(RPG_MSG_GAME_DENIED, '%s already understands the knowledge contained in this tome.\\n' % char.name)
                                else:
                                    player.sendGameText(RPG_MSG_GAME_GAINED, '$src has increased $srchis knowledge of the <a:Spell%s>%s</a> spell!\\n' % (GetTWikiName(spellProto.name), spellProto.name), mob)
                                    self.stackCount -= 1
                                    if self.stackCount <= 0:
                                        player.takeItem(self)
                                    else:
                                        self.itemInfo.refreshDict({'STACKCOUNT': self.stackCount})
                                    s.level += 1
                                    if s.spellInfo:
                                        s.spellInfo.fullRefresh()
                                return

                        player.sendGameText(RPG_MSG_GAME_DENIED, "%s doesn't know the <a:Spell%s>%s</a> spell.\\n" % (char.name, GetTWikiName(spellProto.name), spellProto.name))
                        return
                    else:
                        sslots = [ s.slot for s in char.spells ]
                        for sslot in xrange(0, 256):
                            if sslot not in sslots:
                                char.onSpellSlot(sslot, self)
                                return

                        return
            if len(self.spells) and mob.character:
                gotone = False
                for ispell in self.spells:
                    if ispell.trigger == RPG_ITEM_TRIGGER_POISON:
                        pw = mob.worn.get(RPG_SLOT_PRIMARY, None)
                        if not pw:
                            if player:
                                player.sendGameText(RPG_MSG_GAME_DENIED, '%s must have a primary weapon equipped to apply a poison.\\n' % mob.name)
                            return
                        if pw.procs.has_key(ispell):
                            pw.procs[ispell] = [ispell.duration, RPG_ITEMPROC_POISON]
                            player.sendGameText(RPG_MSG_GAME_GAINED, '%s refreshes %s.\\n' % (mob.name, self.name))
                        elif len(pw.procs) < RPG_ITEMPROC_MAX:
                            pw.procs[ispell] = [ispell.duration, RPG_ITEMPROC_POISON]
                            player.sendGameText(RPG_MSG_GAME_GAINED, '%s applies %s.\\n' % (mob.name, self.name))
                        else:
                            overwriting = []
                            for proc in pw.procs.iterkeys():
                                if pw.procs[proc][1] != RPG_ITEMPROC_ENCHANTMENT:
                                    if not overwriting or overwriting[1] < pw.procs[proc][0]:
                                        overwriting = (proc, pw.procs[proc][0])

                            if not overwriting:
                                player.sendGameText(RPG_MSG_GAME_DENIED, '%s radiates so much power that %s evaporates.\\n' % (pw.name, self.name))
                            else:
                                del pw.procs[overwriting[0]]
                                pw.procs[ispell] = [ispell.duration, RPG_ITEMPROC_POISON]
                                player.sendGameText(RPG_MSG_GAME_DENIED, 'The applied %s nullifies %s.\\n' % (self.name, overwriting[0].spellProto.name))
                        if player or mob.master and mob.master.player:
                            pw.itemInfo.refreshProcs()
                        mob.playSound('sfx/Underwater_Bubbles2.ogg')
                        gotone = True
                    elif ispell.trigger == RPG_ITEM_TRIGGER_USE:
                        for e in ispell.spellProto.effectProtos:
                            if e.hasPermanentStats:
                                for stat in e.permanentStats:
                                    if 'Base' in stat.statname:
                                        stname = stat.statname.replace('Base', 'Raise')
                                        if not getattr(mob.character, stname):
                                            if player:
                                                player.sendGameText(RPG_MSG_GAME_DENIED, 'You cannot raise your stat higher in this manner.\\n')
                                            return

                            if e.giveSkill:
                                if mob.skillLevels.get(e.giveSkill, 0):
                                    if player:
                                        player.sendGameText(RPG_MSG_GAME_DENIED, '%s already knows the %s skill.\\n' % (mob.name, e.giveSkill))
                                    return

                        gotone = True
                        self.doItemSpellUse(mob, ispell.spellProto)

                if gotone and self.useCharges:
                    self.useCharges -= 1
                    if not self.useCharges and self.itemProto.useDestroy:
                        self.stackCount -= 1
                        if self.stackCount <= 0:
                            player.takeItem(self)
                        else:
                            self.useCharges = self.itemProto.useMax
                            self.itemInfo.refreshDict({'STACKCOUNT': self.stackCount,
                             'USECHARGES': self.useCharges})
                        return
                    if self.useCharges < 0:
                        self.useCharges = 0
                    else:
                        self.itemInfo.refreshDict({'USECHARGES': self.useCharges})
            if self.xpCoupon:
                mob.character.gainXP(self.xpCoupon, False)
                player.takeItem(self)
            return

    def tick(self):
        needsTick = True
        if self.reuseTimer:
            self.reuseTimer -= 1
            if self.reuseTimer <= 0:
                self.reuseTimer = 0
                self.itemInfo.refreshDict({'REUSETIMER': self.reuseTimer})
                needsTick = False
        if (self.character or self.player) and self.itemProto.lifeTime > 0:
            needsTick = True
            self.lifeTime -= 3
            if self.lifeTime <= 0:
                if self.character:
                    player = self.character.player
                    char = self.character
                else:
                    player = self.player
                    char = player.curChar
                if self.itemProto.expireMessage:
                    player.sendGameText(RPG_MSG_GAME_LOST, '%s\\n' % self.itemProto.expireMessage, char.mob)
                else:
                    player.sendGameText(RPG_MSG_GAME_LOST, 'The %s has magically been whisked away from %s!\\n' % (self.name, char.name))
                self.destroySelf()
                needsTick = False
        return needsTick

    def isUseable(self, mob):
        spawn = mob.spawn
        proto = self.itemProto
        if mob.player and not mob.player.premium:
            if self.level >= 50 or self.itemProto.flags & RPG_ITEM_PREMIUM:
                return False
        if proto.skill:
            if not mob.skillLevels.get(proto.skill):
                return False
        if len(proto.races):
            if proto.requirementFlags & RPG_ITEMREQUIREMENT_RACEREVERSED:
                if spawn.race in proto.races:
                    return False
            elif spawn.race not in proto.races:
                return False
        if len(proto.realms):
            for r in proto.realms:
                if spawn.realm == r.realmname:
                    break
            else:
                return False

        if proto.requirementFlags & RPG_ITEMREQUIREMENT_EXACTCLASSNUM:
            classNum = (3 if spawn.tclass else 2) if spawn.sclass else 1
            if classNum != proto.requiredClassNum:
                return False
        if len(proto.classes):
            if proto.requirementFlags & RPG_ITEMREQUIREMENT_CLASSREVERSED:
                for cl in proto.classes:
                    if cl.classname == spawn.pclass.name or spawn.sclass and spawn.sclass.name == cl.classname or spawn.tclass and spawn.tclass.name == cl.classname:
                        return False

            else:
                match = 0
                for cl in proto.classes:
                    if cl.classname == spawn.pclass.name or spawn.sclass and spawn.sclass.name == cl.classname or spawn.tclass and spawn.tclass.name == cl.classname:
                        match += 1
                        if match >= proto.requiredClassNum:
                            break
                else:
                    return False

        return True

    def setCharacter(self, char, refresh = True):
        if hasattr(char, 'mob') and char.mob:
            self.canUse = self.isUseable(char.mob)
            self.penalty = self.getPenalty(char.mob)
        if self.character == char:
            if refresh:
                self.refreshFromProto()
            return
        else:
            if self.character:
                if hasattr(self.character, 'mob') and self.character.mob:
                    if self in self.character.mob.worn.itervalues():
                        self.character.mob.unequipItem(self.slot)
                try:
                    mob = self.character.mob
                    if mob:
                        try:
                            del mob.itemRequireTick[self]
                        except KeyError:
                            pass

                        try:
                            del mob.itemFood[self]
                        except KeyError:
                            pass

                        try:
                            del mob.itemDrink[self]
                        except KeyError:
                            pass

                    self.character.items.remove(self)
                except ValueError:
                    pass

            if self.player:
                del self.player.bankItems[self.slot]
            self.character = char
            self.player = None
            if char:
                char.items.append(self)
                mob = char.mob
                if mob:
                    if self.lifeTime:
                        mob.itemRequireTick[self] = self.lifeTime
                    if self.food:
                        mob.itemFood[self] = self.food
                    if self.drink:
                        mob.itemDrink[self] = self.drink
            item = self.item
            if item:
                item.character = char
                item.player = None
            if refresh:
                self.refreshFromProto()
            return

    def setPlayerAsOwner(self, player):
        self.character = None
        self.player = player
        item = self.item
        if item:
            item.character = None
            item.player = player
        return

    def getPenalty(self, mob, forPet = False):
        if not forPet and not self.isUseable(mob):
            return 1.0
        proto = self.itemProto
        penalty = 1.0
        repairRatio = 1.0
        itemLevel = self.level
        levelCheck = mob.plevel
        delta = 9999
        for cl in list(proto.classes):
            if not cl.level:
                traceback.print_stack()
                print 'AssertionError: no level to class %s recommendation assigned, on item %s!' % (cl.classname, self.name)
                continue
            if forPet:
                if cl.level > itemLevel:
                    itemLevel = cl.level
                continue
            if cl.classname == mob.pclass.name:
                diff = cl.level - mob.plevel
                if diff < delta:
                    delta = diff
                    itemLevel = cl.level
                    levelCheck = mob.plevel
            elif mob.sclass and cl.classname == mob.sclass.name:
                diff = cl.level - mob.slevel
                if diff < delta:
                    delta = diff
                    itemLevel = cl.level
                    levelCheck = mob.slevel
            elif mob.tclass and cl.classname == mob.tclass.name:
                diff = cl.level - mob.tlevel
                if diff < delta:
                    delta = diff
                    itemLevel = cl.level
                    levelCheck = mob.tlevel

        for r in list(proto.realms):
            if r.level:
                if forPet:
                    if r.level > itemLevel:
                        itemLevel = r.level
                else:
                    diff = r.level - mob.plevel
                    if diff < delta:
                        itemLevel = r.level
                        levelCheck = mob.plevel

        if itemLevel > 1 and levelCheck < itemLevel:
            u = float(levelCheck) / float(itemLevel)
            f = float(levelCheck) * 0.01
            u = u * (1.0 - f + u * u * u * u * f)
            penalty = 1.0 - u
        else:
            penalty = 0.0
        if self.repairMax:
            repairRatio = float(self.repair) / float(self.repairMax)
            if repairRatio < 0.2:
                penalty += (0.2 - repairRatio) * 4.0
            if self.repair == 0:
                penalty = 1.0
        if penalty < 0.01:
            penalty = 0.0
        elif penalty > 1.0:
            penalty = 1.0
        return penalty

    def getWorth(self, valueMod = 1.0, playerSelling = False):
        proto = self.itemProto
        tin = proto.worthTin
        tin += self.worthIncreaseTin
        tin = floor(tin * RPG_QUALITY_MODS[self.quality])
        tin = ceil(tin * valueMod)
        mod = 1.0
        if self.stackCount:
            if not proto.stackDefault:
                mod = float(self.stackCount)
            else:
                mod = float(self.stackCount) / float(proto.stackDefault)
        if playerSelling and self.flags & RPG_ITEM_LITERATURE:
            mod /= 2.0
        if self.repairMax:
            diminish = 0.1 - 0.1 * float(self.repair) / float(self.repairMax)
            mod -= mod * diminish
        tin = ceil(tin * mod)
        return long(tin)

    def refreshFromProto(self, forPet = False):
        self.reuseTimer = 0
        proto = self.itemProto
        self.spellProto = proto.spellProto
        self.classes = [ (cl.classname, cl.level) for cl in proto.classes ]
        if self.spellProto:
            for cl in self.spellProto.classes:
                self.classes.append((cl.classname, cl.level))

        self.level = proto.level
        if self.levelOverride:
            self.level = self.levelOverride
        if not forPet:
            self.penalty = 0
            self.canUse = False
            if self.character:
                self.setCharacter(self.character, False)
        penalty = 1.0 - self.penalty
        self.light = floor(proto.light * penalty)
        self.flags = proto.flags
        self.material = proto.material
        if not self.stackCount:
            self.stackCount = 1
        self.wpnDamage = ceil(proto.wpnDamage * penalty)
        self.wpnRate = ceil(proto.wpnRate + self.penalty * proto.wpnRate)
        self.wpnRange = ceil(proto.wpnRange * penalty)
        self.model = proto.model
        self.sndProfile = proto.sndProfile
        self.dmgType = RPG_DMG_PUMMEL
        if DAMAGELOOKUP.has_key(proto.skill):
            self.dmgType = DAMAGELOOKUP[proto.skill]
        self.wpnAmmunitionType = proto.wpnAmmunitionType
        self.projectile = proto.projectile
        self.speed = proto.speed
        self.weight = proto.weight
        self.desc = proto.desc
        self.effectDesc = proto.effectDesc
        self.armor = floor(proto.armor * penalty)
        self.skill = proto.skill
        if not self.penalty:
            self.spells = list(proto.spells)
        else:
            self.spells = []
        self.stats = []
        for st in proto.stats:
            self.stats.append((st.statname, st.value))

        if self.hasVariants:
            self.flags |= RPG_ITEM_ARTIFACT
            numVariants = self.numVariants()
            if numVariants:
                self.quality = RPG_QUALITY_EXCEPTIONAL
                if self.spellEnhanceLevel == 9999:
                    self.flags |= RPG_ITEM_ENCHANTED
                level = self.level + 10
                self.worthIncreaseTin = level ** 5 + 500
                self.worthIncreaseTin *= numVariants * 2 + 5
            elif self.spellEnhanceLevel == 9999:
                self.quality = RPG_QUALITY_CRUDDY
        mod = RPG_QUALITY_MODS[self.quality]
        self.armor = floor(self.armor * mod)
        self.wpnDamage = floor(self.wpnDamage * mod)
        self.wpnRate = ceil(self.wpnRate + self.wpnRate * (1.0 - mod))
        self.wpnRange = floor(self.wpnRange * mod)
        self.light = ceil(self.light * mod)
        self.wpnRaceBane = proto.wpnRaceBane
        self.wpnRaceBaneMod = proto.wpnRaceBaneMod
        self.wpnResistDebuff = proto.wpnResistDebuff
        self.wpnResistDebuffMod = proto.wpnResistDebuffMod
        self.repairMax = proto.repairMax
        if self.hasVariants:
            if self.spellEnhanceLevel == 9999:
                from itemvariants import ApplyEnchantment
                ApplyEnchantment(self)
            elif numVariants:
                from itemvariants import ApplyVariants
                ApplyVariants(self)
        if self.quality == RPG_QUALITY_NORMAL:
            self.repairMax = floor(self.repairMax * 0.8)
        elif self.quality == RPG_QUALITY_CRUDDY:
            self.repairMax = floor(self.repairMax * 0.6)
        elif self.quality == RPG_QUALITY_SHODDY:
            self.repairMax = floor(self.repairMax * 0.7)
        elif self.quality == RPG_QUALITY_SUPERIOR:
            self.repairMax = floor(self.repairMax * 0.9)
        if self.flags & RPG_ITEM_INDESTRUCTIBLE:
            self.repairMax = 0
        elif proto.repairMax > 0 and not self.repairMax:
            self.repairMax = 1
        else:
            self.repairMax = int(self.repairMax)
        if self.repair > self.repairMax:
            self.repair = self.repairMax
        if penalty < 1.0:
            stats = []
            for st in self.stats:
                if st[1] < 0:
                    stats.append(st)
                else:
                    value = st[1]
                    if st[0] in RPG_STAT_PERCENTLOOKUP:
                        value = value * penalty
                    else:
                        value = floor(value * penalty)
                    if value:
                        stats.append((st[0], value))

            self.stats = stats
        self.itemInfo.reset()


class ItemSetStat(Persistent):
    itemSetPower = ForeignKey('ItemSetPower')
    statname = StringCol()
    value = FloatCol()


class ItemSetSpell(Persistent):
    itemSetPower = ForeignKey('ItemSetPower')
    spellProto = ForeignKey('SpellProto')
    trigger = IntCol(default=RPG_ITEM_TRIGGER_WORN)
    frequency = IntCol(default=RPG_FREQ_ALWAYS)
    duration = IntCol(default=0)


class ItemSetRequirement(Persistent):
    itemSetPower = ForeignKey('ItemSetPower')
    name = StringCol(default='')
    itemCount = IntCol(default=1)
    countTest = IntCol(default=RPG_ITEMSET_TEST_GREATEREQUAL)

    def makeTest(self, count):
        if self.countTest == RPG_ITEMSET_TEST_GREATEREQUAL:
            if count >= self.itemCount:
                return True
        elif self.countTest == RPG_ITEMSET_TEST_EQUAL:
            if count == self.itemCount:
                return True
        elif count <= self.itemCount:
            return True
        return False


class ItemSetPower(Persistent):
    name = StringCol(alternateID=True)
    harmful = BoolCol(default=False)
    requirementsInternal = MultipleJoin('ItemSetRequirement')
    statsInternal = MultipleJoin('ItemSetStat')
    spellsInternal = MultipleJoin('ItemSetSpell')
    message = StringCol(default='')
    sound = StringCol(default='')
    itemSetProtos = RelatedJoin('ItemSetProto')

    def _init(self, *args, **kw):
        Persistent._init(self, *args, **kw)
        self.requirements = self.requirementsInternal[:]
        self.stats = self.statsInternal[:]
        self.spells = self.spellsInternal[:]

    def removeMods(self, mob):
        for stat in self.stats:
            if stat.statname == 'haste':
                mob.itemSetHastes.remove(stat.value)
                mob.calcItemHaste()
            elif stat.statname in RPG_RESISTSTATS:
                mob.resists[RPG_RESISTLOOKUP[stat.statname]] -= stat.value
            elif hasattr(mob, stat.statname):
                setattr(mob, stat.statname, getattr(mob, stat.statname) - stat.value)

        for spell in self.spells:
            if mob.itemSetSpells.has_key(spell.trigger):
                mob.itemSetSpells[spell.trigger].remove(spell)

    def updateDerived(self, mob):
        for stat in self.stats:
            if stat.statname in RPG_DERIVEDSTATS and hasattr(mob, stat.statname):
                setattr(mob, stat.statname, getattr(mob, stat.statname) + stat.value)

    def checkAndApply(self, mob, contributions, exists, printMessage = True):
        for req in self.requirements:
            if not contributions.has_key(req.name):
                return False
            if self.harmful:
                if not req.makeTest(contributions[req.name][0]):
                    return False
            elif not req.makeTest(contributions[req.name][1]):
                return False

        if exists:
            return True
        if mob.simObject and mob.player and printMessage:
            if self.message:
                mob.player.sendGameText(RPG_MSG_GAME_YELLOW, '%s\\n' % self.message, mob)
            if self.sound:
                mob.playSound(self.sound)
        for stat in self.stats:
            if stat.statname == 'haste':
                mob.itemSetHastes.append(stat.value)
                mob.calcItemHaste()
            elif stat.statname in RPG_RESISTSTATS:
                mob.resists[RPG_RESISTLOOKUP[stat.statname]] += stat.value
            elif hasattr(mob, stat.statname):
                setattr(mob, stat.statname, getattr(mob, stat.statname) + stat.value)

        for spell in self.spells:
            if mob.itemSetSpells.has_key(spell.trigger):
                mob.itemSetSpells[spell.trigger].append(spell)
            else:
                mob.itemSetSpells[spell.trigger] = [spell]

        return True


class ItemSetProto(Persistent):
    name = StringCol(alternateID=True)
    powersInternal = RelatedJoin('ItemSetPower')

    def _init(self, *args, **kw):
        Persistent._init(self, *args, **kw)
        self.powers = self.powersInternal[:]

    def updateDerived(self, mob):
        for power in self.powers:
            if power in mob.equipMods['%s' % self.name]:
                power.updateDerived(mob)

    def checkAndApply(self, mob, printMessage = True):
        thisSet = mob.itemSets[self]
        if thisSet[1]:
            thisSet[1] = False
            if not len(thisSet[0]):
                for power in mob.equipMods['%s' % self.name].iterkeys():
                    power.removeMods(mob)

                del mob.equipMods['%s' % self.name]
                return
            if not mob.equipMods.has_key('%s' % self.name):
                mob.equipMods['%s' % self.name] = []
            for power in self.powers:
                exists = power in mob.equipMods['%s' % self.name]
                if power.checkAndApply(mob, thisSet[0], exists, printMessage):
                    if not exists:
                        mob.equipMods['%s' % self.name].append(power)
                elif exists:
                    power.removeMods(mob)
                    mob.equipMods['%s' % self.name].remove(power)

            return


def getTomeAtLevelForScroll(scroll, tomelevel):
    if not scroll or tomelevel < 2 or tomelevel > 10:
        traceback.print_stack()
        print 'AssertionError: invalid attributes!'
        return
    item = scroll.createInstance('STUFF/38')
    item.spellEnhanceLevel = tomelevel
    spellname = scroll.spellProto.name
    item.name = 'Tome of %s %s' % (spellname, RPG_ROMAN[tomelevel - 1])
    item.descOverride = "This tome contains secrets of the %s spell.  It can increase the reader's potency up to level %s in casting." % (spellname, RPG_ROMAN[tomelevel - 1])
    return item