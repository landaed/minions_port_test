# Embedded file name: mud\world\character.pyo
from mud.common.persistent import Persistent
from mud.world.advancement import AdvancementProto
from mud.world.archetype import GetClass
from mud.world.defines import *
from mud.gamesettings import *
from mud.world.item import ItemInstance, ItemProto
from mud.world.race import GetRace
from mud.world.shared.sounddefs import *
from mud.world.grants import GrantsProvider
from mud.worlddocs.utils import GetTWikiName
from collections import defaultdict
from datetime import datetime
from math import floor
from random import randint
from sqlobject import *
import traceback

class StartingGear(Persistent):
    racename = StringCol(default='')
    classname = StringCol(default='')
    sex = StringCol(default='')
    realm = IntCol()
    items = StringCol(default='')

    def qualify(self, spawn):
        if self.racename and self.racename != spawn.race:
            return False
        if self.classname:
            if spawn.pclass.name != self.classname:
                return False
        if self.sex and self.sex != spawn.sex:
            return False
        if self.realm and self.realm != spawn.realm:
            return False
        return True


class CharacterSpell(Persistent):
    slot = IntCol(default=0)
    recast = IntCol(default=0)
    level = IntCol(default=1)
    character = ForeignKey('Character')
    spellProto = ForeignKey('SpellProto')

    def _init(self, *args, **kw):
        Persistent._init(self, *args, **kw)
        self.spellInfo = None
        return


class CharacterSkill(Persistent):
    skillname = StringCol()
    level = IntCol(default=1)
    character = ForeignKey('Character')


class CharacterDialogChoice(Persistent):
    identifier = StringCol()
    count = IntCol(default=1)
    character = ForeignKey('Character')


class CharacterAdvancement(Persistent):
    rank = IntCol(default=1)
    advancementProto = ForeignKey('AdvancementProto')
    character = ForeignKey('Character')

    def apply(self):
        pass

    def remove(self):
        pass


class CharacterVaultItem(Persistent):
    name = StringCol()
    stackCount = IntCol()
    character = ForeignKey('Character')
    item = ForeignKey('Item')


class CharacterFaction(Persistent):
    points = IntCol(default=0)
    character = ForeignKey('Character')
    faction = ForeignKey('Faction')


class Character(Persistent):
    name = StringCol(alternateID=True, default='')
    lastName = StringCol(default='')
    creationTime = DateTimeCol(default=datetime.now)
    xpPrimary = IntCol(default=0)
    xpSecondary = IntCol(default=0)
    xpTertiary = IntCol(default=0)
    xpDeathPrimary = IntCol(default=0)
    xpDeathSecondary = IntCol(default=0)
    xpDeathTertiary = IntCol(default=0)
    advancementPoints = IntCol(default=0)
    advancementLevelPrimary = IntCol(default=1)
    advancementLevelSecondary = IntCol(default=1)
    advancementLevelTertiary = IntCol(default=1)
    portraitPic = StringCol()
    dead = BoolCol(default=False)
    strRaise = IntCol(default=300)
    bdyRaise = IntCol(default=300)
    dexRaise = IntCol(default=300)
    mndRaise = IntCol(default=300)
    wisRaise = IntCol(default=300)
    agiRaise = IntCol(default=300)
    refRaise = IntCol(default=300)
    mysRaise = IntCol(default=300)
    health = IntCol(default=-999999)
    mana = IntCol(default=-999999)
    stamina = IntCol(default=-999999)
    pchange = BoolCol(default=False)
    schange = BoolCol(default=False)
    tchange = BoolCol(default=False)
    deathTransformInternal = StringCol(default='0 0 0 1 0 0 0')
    player = ForeignKey('Player')
    spawn = ForeignKey('Spawn')
    spellsInternal = MultipleJoin('CharacterSpell')
    itemsInternal = MultipleJoin('Item')
    vaultItemsInternal = MultipleJoin('CharacterVaultItem')
    advancements = MultipleJoin('CharacterAdvancement')
    skills = MultipleJoin('CharacterSkill')
    characterDialogChoices = MultipleJoin('CharacterDialogChoice')
    characterFactions = MultipleJoin('CharacterFaction')
    spellStore = MultipleJoin('SpellStore')
    deathZone = ForeignKey('Zone', default=None)

    def _init(self, *args, **kw):
        Persistent._init(self, *args, **kw)
        self.mob = None
        self.xpGainPrimary = 1.0
        self.xpGainSecondary = 0
        self.xpGainTertiary = 0
        self.itemList = None
        self.vaultItemsDirty = True
        self.vaultItemList = None
        self.spellsDirty = True
        self.spellList = None
        self.petHealthBackup = 0
        self.petHealthTimer = -9999
        self.setXPMods()
        self.calcXPPercents()
        self.checkAdvancements()
        return

    def _get_deathTransform(self):
        return map(float, self.deathTransformInternal.split(' '))

    def _set_deathTransform(self, transform):
        self.deathTransformInternal = ' '.join(map(str, transform))

    def _get_items(self):
        if not self.itemList:
            self.itemList = []
            for item in self.itemsInternal:
                if item.itemProto.flags & RPG_ITEM_ETHEREAL:
                    item.destroySelf()
                    continue
                self.itemList.append(ItemInstance(item))

        return self.itemList

    def _get_vaultItems(self):
        if self.vaultItemsDirty:
            self.vaultItemList = self.vaultItemsInternal
        self.vaultItemsDirty = False
        return self.vaultItemList

    def _get_spells(self):
        if self.spellsDirty:
            self.spellList = self.spellsInternal
        self.spellsDirty = False
        return self.spellList

    def refreshItems(self):
        petItems = []
        for item in self.items:
            if not RPG_SLOT_PET_END > item.slot >= RPG_SLOT_PET_BEGIN:
                item.refreshFromProto()
            else:
                petItems.append(item)

        self.refreshPetItems(petItems)
        self.player.cinfoDirty = True

    def backupItems(self):
        map(ItemInstance.storeToItem, self.items)

    def trainClass(self, klass):
        spawn = self.spawn
        if not spawn.slevel:
            spawn.slevel = 1
            spawn.sclassInternal = klass
        else:
            spawn.tlevel = 1
            spawn.tclassInternal = klass
        self.setXPMods()
        self.calcXPPercents()
        self.mob.levelChanged()

    def setXPGain(self, pgain, sgain, tgain):
        self.xpGainPrimary = pgain
        self.xpGainSecondary = sgain
        self.xpGainTertiary = tgain
        if not self.spawn.sclassInternal:
            self.xpGainSecondary = 0.0
        if not self.spawn.tclassInternal:
            self.xpGainTertiary = 0.0

    def setXPMods(self):
        self.pxpMod = 1.0
        self.sxpMod = 1.0
        self.txpMod = 1.0
        spawn = self.spawn
        race = GetRace(self.spawn.race)
        pclass = GetClass(spawn.pclassInternal)
        if spawn.sclassInternal:
            sclass = GetClass(spawn.sclassInternal)
            if spawn.tclassInternal:
                tclass = GetClass(spawn.tclassInternal)
            else:
                tclass = None
        else:
            sclass = None
            tclass = None
        xpmod = race.getXPMod() - 1.0
        self.pxpMod = 1.0 + xpmod + (pclass.getXPMod() - 1.0)
        if sclass:
            self.sxpMod = 1.0 + xpmod + (sclass.getXPMod() - 1.0)
            if tclass:
                self.txpMod = 1.0 + xpmod + (tclass.getXPMod() - 1.0)
        return

    def calcXPPercents(self):
        spawn = self.spawn
        self.pxpPercent = 0
        self.sxpPercent = 0
        self.txpPercent = 0
        if not spawn.plevel:
            spawn.plevel = 1
        pneeded = spawn.plevel * spawn.plevel * 100L * self.pxpMod
        pprevneeded = (spawn.plevel - 1) * (spawn.plevel - 1) * 100L * self.pxpMod
        self.pxpPercent = (self.xpPrimary - pprevneeded) / (pneeded - pprevneeded)
        if spawn.slevel:
            sneeded = spawn.slevel * spawn.slevel * 100L * self.sxpMod
            sprevneeded = (spawn.slevel - 1) * (spawn.slevel - 1) * 100L * self.sxpMod
            self.sxpPercent = (self.xpSecondary - sprevneeded) / (sneeded - sprevneeded)
            if spawn.tlevel:
                tneeded = spawn.tlevel * spawn.tlevel * 100L * self.txpMod
                tprevneeded = (spawn.tlevel - 1) * (spawn.tlevel - 1) * 100L * self.txpMod
                self.txpPercent = (self.xpTertiary - tprevneeded) / (tneeded - tprevneeded)

    def gainLevel(self, which):
        spawn = self.spawn
        if not self.player.premium:
            if which == 0 and spawn.plevel >= RPG_DEMO_PLEVEL_LIMIT:
                return
            if which == 1 and spawn.slevel >= RPG_DEMO_SLEVEL_LIMIT:
                return
            if which == 2:
                return
        if which == 0:
            self.xpPrimary = int(spawn.plevel * spawn.plevel * 100L * self.pxpMod + 1)
        elif which == 1:
            self.xpSecondary = int(spawn.slevel * spawn.slevel * 100L * self.sxpMod + 1)
        elif which == 2:
            self.xpTertiary = int(spawn.tlevel * spawn.tlevel * 100L * self.txpMod + 1)
        self.gainXP(10)

    def gainXP(self, amount, clamp = True, rez = None, clampAdjust = 0):
        spawn = self.spawn
        mob = self.mob
        total = 1.0
        pgain = self.xpGainPrimary
        total -= pgain
        if total < 0.0:
            total = 0.0
        sgain = self.xpGainSecondary
        if sgain > total:
            sgain = total
        total -= sgain
        if total < 0.0:
            total = 0.0
        tgain = self.xpGainTertiary
        if tgain > total:
            tgain = total
        total -= tgain
        if total < 0.0:
            total = 0.0
        if total:
            if self.xpGainPrimary >= self.xpGainSecondary and self.xpGainPrimary >= self.xpGainTertiary:
                pgain += total
            elif self.xpGainSecondary >= self.xpGainPrimary and self.xpGainSecondary >= self.xpGainTertiary:
                sgain += total
            elif self.xpGainTertiary >= self.xpGainPrimary and self.xpGainTertiary >= self.xpGainSecondary:
                tgain += total
            else:
                pgain += total
        if not spawn.slevel:
            sgain = 0.0
        if not spawn.tlevel:
            tgain = 0.0
        msg = False
        if not self.player.premium:
            if spawn.plevel >= RPG_DEMO_PLEVEL_LIMIT and pgain:
                if spawn.slevel > 0 and spawn.slevel < RPG_DEMO_SLEVEL_LIMIT:
                    sgain += pgain
                    if sgain > 1.0:
                        sgain = 1.0
                pgain = 0
                msg = True
                self.player.sendGameText(RPG_MSG_GAME_DENIED, '\\n%s has reached primary level %i and can gain more experience by training in a secondary class or purchasing Premium Account.\\nThe Premium Account will also allow %s to use premium gear and multiclass in a third class to level 100!\\nPlease see www.prairiegames.com for more information.\\n\\n' % (self.spawn.name, RPG_DEMO_PLEVEL_LIMIT, self.spawn.name))
            if spawn.slevel >= RPG_DEMO_SLEVEL_LIMIT and sgain:
                if spawn.plevel < RPG_DEMO_PLEVEL_LIMIT:
                    pgain += sgain
                    if pgain > 1.0:
                        pgain = 1.0
                sgain = 0
                if not msg:
                    self.player.sendGameText(RPG_MSG_GAME_DENIED, '\\n%s has reached secondary level %i and can gain more experience by purchasing the Premium Account.\\nThe Premium Account will also allow %s to use premium gear and multiclass in a third class to level 100!\\nPlease see www.prairiegames.com for more information.\\n\\n' % (self.spawn.name, RPG_DEMO_SLEVEL_LIMIT, self.spawn.name))
            if not sgain and not pgain:
                return
        if spawn.sclass and spawn.slevel >= spawn.plevel and spawn.plevel != 100:
            pgain += sgain
            sgain = 0
        if spawn.tclass and spawn.tlevel >= spawn.slevel and spawn.slevel != 100:
            pgain += tgain
            tgain = 0
        if rez:
            xpp, xps, xpt = rez
        else:
            xpp = amount * pgain
            xps = amount * sgain / 2
            xpt = amount * tgain / 3
            xpp *= mob.xpScalar
            xps *= mob.xpScalar
            xpt *= mob.xpScalar
        pneeded = spawn.plevel * spawn.plevel * 100L * self.pxpMod
        sneeded = spawn.slevel * spawn.slevel * 100L * self.sxpMod
        tneeded = spawn.tlevel * spawn.tlevel * 100L * self.txpMod
        pgap = pneeded - (spawn.plevel - 1) * (spawn.plevel - 1) * 100L * self.pxpMod
        sgap = sneeded - (spawn.slevel - 1) * (spawn.slevel - 1) * 100L * self.sxpMod
        tgap = tneeded - (spawn.tlevel - 1) * (spawn.tlevel - 1) * 100L * self.txpMod
        if clamp:
            clampAdjust = 1.0 - clampAdjust
            pdiv = 10 / clampAdjust
            sdiv = 10 / clampAdjust
            tdiv = 10 / clampAdjust
            if xpp > pgap / pdiv:
                xpp = pgap / pdiv
            if xps:
                if xps > sgap / sdiv:
                    xps = sgap / sdiv
            if xpt:
                if xpt > tgap / tdiv:
                    xpt = tgap / tdiv
        xpp = int(floor(xpp))
        xps = int(floor(xps))
        xpt = int(floor(xpt))
        calc = False
        if spawn.plevel == 100 and self.xpPrimary + xpp >= pneeded:
            self.xpPrimary = int(pneeded) - 1
            xpp = 0
            calc = True
        if spawn.slevel == 100 and self.xpSecondary + xps >= sneeded:
            self.xpSecondary = int(sneeded) - 1
            xps = 0
            calc = True
        if spawn.tlevel == 100 and self.xpTertiary + xpt >= tneeded:
            self.xpTertiary = int(tneeded) - 1
            xpt = 0
            calc = True
        if not xpp and not xps and not xpt:
            if calc:
                self.calcXPPercents()
            return
        self.xpPrimary += xpp
        self.xpSecondary += xps
        self.xpTertiary += xpt
        text = []
        if xpp:
            text.append('%i primary' % xpp)
        if xps:
            text.append('%i secondary' % xps)
        if xpt:
            text.append('%i tertiary' % xpt)
        text = '%s gained %s xp!\\n' % (self.name, ', '.join(text))
        self.player.sendGameText(RPG_MSG_GAME_GAINED, text)
        gained = False
        if spawn.plevel < 100:
            if self.xpPrimary >= pneeded:
                spawn.plevel += 1
                mob.plevel += 1
                gained = True
                advance = False
                points = 0
                totalPoints = 0
                advDiff = spawn.plevel - self.advancementLevelPrimary
                if advDiff > 0:
                    advance = True
                    for i in xrange(advDiff):
                        self.advancementLevelPrimary += 1
                        points = int(float(spawn.plevel - i) / 2.0)
                        if points < 5:
                            points = 5
                        self.advancementPoints += points
                        totalPoints += points

                self.player.mind.callRemote('playSound', 'sfx/Pickup_Magic02.ogg')
                pclassName = spawn.pclassInternal
                if advance:
                    self.player.sendGameText(RPG_MSG_GAME_LEVELGAINED, '%s is now a level %i <a:Class%s>%s</a>!!!\\n' % (self.name,
                     spawn.plevel,
                     GetTWikiName(pclassName),
                     pclassName.lower()))
                    self.player.sendGameText(RPG_MSG_GAME_LEVELGAINED, '%s has gained %i advancement points!!!\\n' % (self.name, totalPoints))
                    if RPG_MULTICLASS_SECONDARY_LEVEL_REQUIREMENT == spawn.plevel and not spawn.slevel:
                        self.player.sendGameText(RPG_MSG_GAME_GAINED, '%s can now train in a secondary class.\\n' % self.name)
                    elif RPG_MULTICLASS_TERTIARY_LEVEL_REQUIREMENT == spawn.plevel and not spawn.tlevel:
                        self.player.sendGameText(RPG_MSG_GAME_GAINED, '%s can now train in a tertiary class.\\n' % self.name)
                else:
                    self.player.sendGameText(RPG_MSG_GAME_LEVELGAINED, '%s has regained a primary level!!! (<a:Class%s>%s</a>, %i)\\n' % (self.name,
                     GetTWikiName(pclassName),
                     pclassName.lower(),
                     spawn.plevel))
        if spawn.sclass and spawn.slevel < spawn.plevel:
            if self.xpSecondary >= sneeded:
                spawn.slevel += 1
                mob.slevel += 1
                gained = True
                advance = False
                points = 0
                totalPoints = 0
                advDiff = spawn.slevel - self.advancementLevelSecondary
                if advDiff > 0:
                    advance = True
                    for i in xrange(advDiff):
                        self.advancementLevelSecondary += 1
                        points = int(float(spawn.slevel - i) / 2.0)
                        if points < 3:
                            points = 3
                        self.advancementPoints += points
                        totalPoints += points

                self.player.mind.callRemote('playSound', 'sfx/Pickup_Magic02.ogg')
                sclassName = spawn.sclassInternal
                if advance:
                    self.player.sendGameText(RPG_MSG_GAME_LEVELGAINED, "%s's secondary class of <a:Class%s>%s</a> is now level %i!!\\n" % (self.name,
                     GetTWikiName(sclassName),
                     sclassName.lower(),
                     spawn.slevel))
                    self.player.sendGameText(RPG_MSG_GAME_LEVELGAINED, '%s has gained %i advancement points!!!\\n' % (self.name, totalPoints))
                else:
                    self.player.sendGameText(RPG_MSG_GAME_LEVELGAINED, '%s has regained a secondary class level! (<a:Class%s>%s</a>, %i)!!\\n' % (self.name,
                     GetTWikiName(sclassName),
                     sclassName.lower(),
                     spawn.slevel))
        if spawn.tclass and spawn.tlevel < spawn.slevel:
            if self.xpTertiary >= tneeded:
                spawn.tlevel += 1
                mob.tlevel += 1
                gained = True
                advance = False
                points = 0
                totalPoints = 0
                advDiff = spawn.tlevel - self.advancementLevelTertiary
                if advDiff > 0:
                    advance = True
                    for i in xrange(advDiff):
                        self.advancementLevelTertiary += 1
                        points = int(float(spawn.tlevel - i) / 2.0)
                        if points < 1:
                            points = 1
                        self.advancementPoints += points
                        totalPoints += points

                self.player.mind.callRemote('playSound', 'sfx/Pickup_Magic02.ogg')
                tclassName = spawn.tclassInternal
                if advance:
                    self.player.sendGameText(RPG_MSG_GAME_LEVELGAINED, "%s's tertiary class of <a:Class%s>%s</a> is now level %i!!\\n" % (self.name,
                     GetTWikiName(tclassName),
                     tclassName.lower(),
                     spawn.tlevel))
                    self.player.sendGameText(RPG_MSG_GAME_LEVELGAINED, '%s has gained %i advancement points!!!\\n' % (self.name, totalPoints))
                else:
                    self.player.sendGameText(RPG_MSG_GAME_LEVELGAINED, '%s has regained a tertiary level!!! (<a:Class%s>%s</a>, %i)\\n' % (self.name,
                     GetTWikiName(tclassName),
                     tclassName.lower(),
                     spawn.tlevel))
        self.calcXPPercents()
        if gained:
            mob.levelChanged()

    def onSpellSlotSwap(self, srcslot, dstslot):
        if srcslot == dstslot:
            return
        else:
            srcspell = None
            for spell in self.spells:
                if spell.slot == srcslot:
                    srcspell = spell
                    break

            dstspell = None
            for spell in self.spells:
                if spell.slot == dstslot:
                    dstspell = spell
                    break

            if srcspell:
                srcspell.slot = dstslot
            if dstspell:
                dstspell.slot = srcslot
            return

    def onSpellSlot(self, slot, item = None):
        for spell in self.spells:
            if spell.slot == slot:
                sProto = spell.spellProto
                if sProto.qualify(self.mob):
                    self.mob.cast(sProto, spell.level)
                else:
                    self.player.sendGameText(RPG_MSG_GAME_DENIED, '%s does not know how to cast <a:Spell%s>%s</a>.\\n' % (self.name, GetTWikiName(sProto.name), sProto.name))
                return

        if not item:
            item = self.player.cursorItem
            if not item:
                return
        if item.spellEnhanceLevel:
            return
        spellToLearnProto = item.itemProto.spellProto
        if not spellToLearnProto:
            return
        for characterSpell in self.spells:
            if spellToLearnProto == characterSpell.spellProto:
                self.player.sendGameText(RPG_MSG_GAME_DENIED, '%s already knows this spell!\\n' % self.name)
                return

        if not spellToLearnProto.qualify(self.mob):
            self.player.sendGameText(RPG_MSG_GAME_DENIED, '%s cannot learn <a:Spell%s>%s</a> at this time.\\n' % (self.name, GetTWikiName(spellToLearnProto.name), spellToLearnProto.name))
            return
        CharacterSpell(character=self, spellProto=spellToLearnProto, slot=slot, recast=0)
        self.spellsDirty = True
        item.stackCount -= 1
        if 0 >= item.stackCount:
            item.destroySelf()
        else:
            item.itemInfo.refreshDict({'STACKCOUNT': item.stackCount})
        self.player.mind.callRemote('playSound', 'sfx/Pencil_WriteOnPaper2.ogg')
        self.player.sendGameText(RPG_MSG_GAME_GOOD, '%s learns <a:Spell%s>%s</a>.\\n' % (self.name, GetTWikiName(spellToLearnProto.name), spellToLearnProto.name))

    def equipItems(self, printSets = True):
        for item in self.items:
            if RPG_SLOT_WORN_END > item.slot >= RPG_SLOT_WORN_BEGIN:
                self.mob.equipItem(item.slot, item, printSets)

    def unequipItems(self):
        for item in self.items:
            if RPG_SLOT_WORN_END > item.slot >= RPG_SLOT_WORN_BEGIN:
                self.mob.unequipItem(item.slot)

    def onTradeSlot(self, slot):
        player = self.player
        trade = player.trade
        if not trade:
            return
        elif trade.p0Accepted or trade.p1Accepted:
            return
        else:
            if trade.p0 == player:
                titems = trade.p0Items
            else:
                titems = trade.p1Items
            cursorItem = player.cursorItem
            tradeSlot = slot - RPG_SLOT_TRADE_BEGIN
            previtem = titems.get(tradeSlot, None)
            if not cursorItem and not previtem:
                return
            if cursorItem:
                if cursorItem.flags & RPG_ITEM_SOULBOUND and player.role.name != 'Immortal':
                    self.player.sendGameText(RPG_MSG_GAME_DENIED, 'This item cannot be traded.\\n')
                    return
                for tslot in xrange(RPG_SLOT_TRADE_BEGIN, RPG_SLOT_TRADE_END):
                    for item in self.items:
                        if item.slot == tslot:
                            break
                    else:
                        cursorItem.slot = tslot
                        break

                else:
                    return

                titems[tradeSlot] = cursorItem
            else:
                del titems[tradeSlot]
            if previtem:
                previtem.slot = RPG_SLOT_CURSOR
                previtem.setCharacter(self)
            player.cursorItem = previtem
            player.updateCursorItem(cursorItem)
            trade.refresh()
            return

    def equipItem(self, item):
        mob = self.mob
        itemProto = item.itemProto
        slots = set(itemProto.slots)
        if RPG_SLOT_PRIMARY in slots or RPG_SLOT_SECONDARY in slots:
            itemTwoHanded = item.skill and '2H' in item.skill
            powerwield = mob.skillLevels.get('Power Wield')
            dualwield = powerwield or mob.skillLevels.get('Dual Wield')
            if not dualwield:
                slots.discard(RPG_SLOT_SECONDARY)
            elif powerwield and itemTwoHanded and RPG_SLOT_PRIMARY in slots:
                slots.add(RPG_SLOT_SECONDARY)
        if not len(slots):
            return False
        else:
            useslot = None
            unequip = False
            for slot in slots:
                if not self.mob.worn.get(slot):
                    useslot = slot
                    break
            else:
                if item.slot == -1 or RPG_SLOT_LOOT_BEGIN <= item.slot < RPG_SLOT_LOOT_END:
                    return False
                unequip = True
                useslot = slots.pop()

            if useslot == RPG_SLOT_PRIMARY:
                sitem = mob.worn.get(RPG_SLOT_SECONDARY, None)
                if sitem:
                    if not dualwield:
                        if not self.unequipItem(RPG_SLOT_SECONDARY):
                            return False
                    elif not powerwield and (itemTwoHanded or '2H' in sitem.skill):
                        if not self.unequipItem(RPG_SLOT_SECONDARY):
                            return False
            elif useslot == RPG_SLOT_SECONDARY:
                pitem = mob.worn.get(RPG_SLOT_PRIMARY, None)
                if pitem:
                    if not dualwield:
                        if RPG_SLOT_PRIMARY in slots:
                            useslot = RPG_SLOT_PRIMARY
                            if unequip:
                                if not self.unequipItem(RPG_SLOT_SECONDARY):
                                    return False
                            unequip = True
                        elif not self.unequipItem(RPG_SLOT_SECONDARY):
                            return False
                    elif not powerwield and (itemTwoHanded or '2H' in pitem.skill):
                        if RPG_SLOT_PRIMARY in slots:
                            useslot = RPG_SLOT_PRIMARY
                            if unequip and (itemTwoHanded or '2H' in mob.worn.get(RPG_SLOT_SECONDARY).skill):
                                if not self.unequipItem(RPG_SLOT_SECONDARY):
                                    return False
                            unequip = True
                        elif not self.unequipItem(RPG_SLOT_PRIMARY):
                            return False
            if item.flags & RPG_ITEM_UNIQUE:
                for iitem in self.mob.worn.itervalues():
                    if itemProto == iitem.itemProto and iitem.slot != useslot:
                        self.player.sendGameText(RPG_MSG_GAME_DENIED, '%s can only use one of these at a time!\\n' % self.name)
                        return False

            if unequip and not self.unequipItem(useslot, item.slot):
                return False
            item.slot = useslot
            self.mob.equipItem(useslot, item)
            if item.sndProfile and item.sndProfile.sndEquip:
                snd = item.sndProfile.sndEquip
            else:
                snd = SND_ITEMEQUIP
            self.player.mind.callRemote('playSound', snd)
            return True

    def unequipItem(self, slot, putslot = None):
        for item in self.items:
            if item.slot == slot:
                if putslot != None and putslot != -1:
                    item.slot = putslot
                else:
                    free = self.getFreeCarrySlots()
                    if not len(free):
                        return False
                    item.slot = free[0]
                self.mob.unequipItem(slot)
                return True

        return False

    def onInvSlotAlt(self, slot):
        if RPG_SLOT_WORN_END > slot >= RPG_SLOT_WORN_BEGIN:
            self.unequipItem(slot)
            if self.player.cursorItem:
                self.onInvSlot(slot)
            return
        else:
            if RPG_SLOT_CARRY_END > slot >= RPG_SLOT_CARRY_BEGIN or RPG_SLOT_CRAFTING_END > slot >= RPG_SLOT_CRAFTING_BEGIN:
                for item in self.items:
                    if item.slot == slot:
                        proto = item.itemProto
                        cursorItem = self.player.cursorItem
                        stackMax = proto.stackMax
                        if stackMax > 1:
                            if not cursorItem or cursorItem.name == item.name:
                                if not item.stackCount:
                                    item.stackCount = 1
                                if not cursorItem:
                                    if item.stackCount == 1:
                                        self.onInvSlot(slot)
                                        self.player.cursorItem = item
                                        self.player.updateCursorItem(None)
                                        return
                                    nitem = item.clone()
                                    nitem.setCharacter(self, False)
                                    nitem.stackCount = 1
                                    item.stackCount -= 1
                                    item.itemInfo.refreshDict({'STACKCOUNT': item.stackCount})
                                    self.player.cursorItem = nitem
                                    nitem.slot = RPG_SLOT_CURSOR
                                    self.player.updateCursorItem(None)
                                    return
                                if cursorItem.stackCount < stackMax:
                                    useMax = proto.useMax
                                    useStack = False
                                    refreshUse = False
                                    if useMax > 1 and item.useCharges < useMax:
                                        amt = useMax - cursorItem.useCharges
                                        refreshUse = True
                                        if amt >= item.useCharges:
                                            cursorItem.useCharges += item.useCharges
                                            useStack = True
                                        else:
                                            cursorItem.useCharges = item.useCharges - amt
                                        item.useCharges = useMax
                                    if not useStack:
                                        cursorItem.stackCount += 1
                                    if refreshUse and useStack:
                                        cursorItem.itemInfo.refreshDict({'USECHARGES': cursorItem.useCharges})
                                    elif refreshUse:
                                        cursorItem.itemInfo.refreshDict({'STACKCOUNT': cursorItem.stackCount,
                                         'USECHARGES': cursorItem.useCharges})
                                    else:
                                        cursorItem.itemInfo.refreshDict({'STACKCOUNT': cursorItem.stackCount})
                                    if item.stackCount > 1:
                                        item.stackCount -= 1
                                        if refreshUse:
                                            item.itemInfo.refreshDict({'STACKCOUNT': item.stackCount,
                                             'USECHARGES': item.useCharges})
                                        else:
                                            item.itemInfo.refreshDict({'STACKCOUNT': item.stackCount})
                                        return
                                    self.player.takeItem(item)
                            return
                        if len(proto.slots):
                            if not item.isUseable(self.mob):
                                if not self.player.premium:
                                    if item.level >= 50 or item.itemProto.flags & RPG_ITEM_PREMIUM:
                                        self.player.sendGameText(RPG_MSG_GAME_DENIED, '\\nThis item requires Premium Account.\nPlease see www.prairiegames.com for more information.\\n\\n')
                                self.player.sendGameText(RPG_MSG_GAME_DENIED, '%s cannot use this item!\\n' % self.name)
                                return
                            self.equipItem(item)
                            return
                        break

            return

    def setPetEquipment(self):
        if not self.mob:
            return
        pet = self.mob.pet
        if not pet or pet.detached or pet.charmEffect:
            return
        self.refreshPetItems()
        pet.mobInfo.refresh()

    def refreshPetItems(self, itemList = None):
        pet = self.mob.pet
        if not itemList:
            itemList = self.items
        if not pet:
            for item in itemList:
                if RPG_SLOT_PET_BEGIN <= item.slot < RPG_SLOT_PET_END:
                    item.setCharacter(self, True)

            return
        map(pet.unequipItem, xrange(RPG_SLOT_WORN_BEGIN, RPG_SLOT_WORN_END))
        myrealm = self.mob.spawn.realm
        for item in itemList:
            if not RPG_SLOT_PET_BEGIN <= item.slot < RPG_SLOT_PET_END:
                continue
            proto = item.itemProto
            petSlot = item.slot - RPG_SLOT_PET_BEGIN
            if not self.player.premium:
                if item.level >= 50 or proto.flags & RPG_ITEM_PREMIUM:
                    pet.equipItem(petSlot, item)
                    continue
            if len(proto.realms):
                for r in proto.realms:
                    if myrealm == r.realmname:
                        break
                else:
                    pet.equipItem(petSlot, item)
                    continue

            item.penalty = item.getPenalty(pet, True)
            item.refreshFromProto(True)
            pet.equipItem(petSlot, item)

    def onPetSlot(self, slot):
        cursorItem = self.player.cursorItem
        previtem = None
        for item in self.items:
            if item.slot == slot:
                previtem = item
                break

        if cursorItem:
            if slot - RPG_SLOT_PET_BEGIN not in cursorItem.itemProto.slots:
                self.player.sendGameText(RPG_MSG_GAME_DENIED, 'This item cannot be equipped here.\\n')
                return
            cursorItem.setCharacter(self)
            cursorItem.slot = slot
            self.player.cursorItem = None
            self.player.mind.callRemote('setItemSlot', self.id, cursorItem.itemInfo, slot)
        elif previtem:
            self.player.mind.callRemote('setItemSlot', self.id, None, slot)
        if previtem:
            previtem.slot = RPG_SLOT_CURSOR
            self.player.cursorItem = previtem
            previtem.setCharacter(self, True)
        if previtem or cursorItem:
            self.player.mind.callRemote('playSound', SND_INVENTORY)
            self.setPetEquipment()
        return

    def eat(self, tick = True):
        if not self.player:
            return
        items = []
        for m in self.player.party.members:
            items.extend(m.mob.itemFood.keys())

        for item in items:
            if item.food:
                item.food -= 1
                self.mob.hungry = False
                if item.food <= 0:
                    item.stackCount -= 1
                    if item.stackCount <= 0:
                        self.player.takeItem(item)
                    else:
                        item.food = item.itemProto.food
                        item.itemInfo.refreshDict({'STACKCOUNT': item.stackCount})
                return

        if tick:
            self.mob.hungry = True
            self.player.sendGameText(RPG_MSG_GAME_DENIED, '%s is starving.\\n' % self.name)

    def drink(self, tick = True):
        if not self.player:
            return
        items = []
        for m in self.player.party.members:
            items.extend(m.mob.itemDrink.keys())

        for item in items:
            if item.drink:
                item.drink -= 1
                self.mob.thirsty = False
                if item.drink <= 0:
                    item.stackCount -= 1
                    if item.stackCount <= 0:
                        self.player.takeItem(item)
                    else:
                        item.drink = item.itemProto.drink
                        item.itemInfo.refreshDict({'STACKCOUNT': item.stackCount})
                return

        if tick:
            self.mob.thirsty = True
            self.player.sendGameText(RPG_MSG_GAME_DENIED, '%s is thirsty.\\n' % self.name)

    def onInvSlot(self, slot):
        if RPG_SLOT_TRADE_END > slot >= RPG_SLOT_TRADE_BEGIN:
            self.onTradeSlot(slot)
            return
        elif RPG_SLOT_PET_END > slot >= RPG_SLOT_PET_BEGIN:
            self.onPetSlot(slot)
            return
        else:
            cursorItem = self.player.cursorItem
            previtem = None
            for item in self.items:
                if item.slot == slot:
                    previtem = item
                    break

            if previtem:
                if cursorItem and previtem.container:
                    if previtem.container.insertItem(cursorItem, True):
                        previtem.itemInfo.refreshContents()
                        return
                    switched, cursorItem, previtem = True, previtem, cursorItem
                else:
                    switched, cursorItem, previtem = previtem.doStack(cursorItem)
                    if not switched:
                        return
            shouldEquip = False
            if cursorItem:
                if RPG_SLOT_WORN_END > slot >= RPG_SLOT_WORN_BEGIN:
                    if not cursorItem.isUseable(self.mob):
                        if not self.player.premium:
                            if cursorItem.level >= 50 or cursorItem.itemProto.flags & RPG_ITEM_PREMIUM:
                                self.player.sendGameText(RPG_MSG_GAME_DENIED, '\\nThis item requires Premium Account.\\nPlease see www.prairiegames.com for more information.\\n\\n')
                        self.player.sendGameText(RPG_MSG_GAME_DENIED, '%s cannot use this item!\\n' % self.name)
                        return
                    if cursorItem.flags & RPG_ITEM_UNIQUE:
                        for iitem in self.mob.worn.itervalues():
                            if cursorItem.itemProto == iitem.itemProto and slot != iitem.slot:
                                self.player.sendGameText(RPG_MSG_GAME_DENIED, '%s can only use one of these at a time!\\n' % self.name)
                                return

                    if slot == RPG_SLOT_SECONDARY and not self.mob.skillLevels.get('Dual Wield'):
                        self.player.sendGameText(RPG_MSG_GAME_DENIED, '%s does not know how to <a:SkillDualWield>dual wield</a>.\\n' % self.name)
                        return
                    if slot == RPG_SLOT_SECONDARY and cursorItem.skill and '2H' in cursorItem.skill and not self.mob.skillLevels.get('Power Wield'):
                        self.player.sendGameText(RPG_MSG_GAME_DENIED, '%s does not know how to <a:SkillPowerWield>power wield</a>.\\n' % self.name)
                        return
                    if slot not in cursorItem.itemProto.slots and not (slot == RPG_SLOT_SECONDARY and cursorItem.skill and '2H' in cursorItem.skill):
                        self.player.sendGameText(RPG_MSG_GAME_DENIED, 'This item cannot be equipped here.\\n')
                        return
                    shouldEquip = True
                cursorItem.setCharacter(self)
                cursorItem.slot = slot
                self.player.cursorItem = None
                self.player.updateCursorItem(cursorItem)
                self.player.mind.callRemote('setItemSlot', self.id, cursorItem.itemInfo, slot)
            elif previtem:
                self.player.mind.callRemote('setItemSlot', self.id, None, slot)
            if previtem:
                if RPG_SLOT_WORN_END > slot >= RPG_SLOT_WORN_BEGIN:
                    self.mob.unequipItem(slot)
                previtem.slot = RPG_SLOT_CURSOR
                self.player.cursorItem = previtem
                self.player.updateCursorItem(cursorItem)
            if shouldEquip:
                self.mob.equipItem(slot, cursorItem)
                snd = SND_ITEMEQUIP
                if cursorItem.sndProfile and cursorItem.sndProfile.sndEquip:
                    snd = cursorItem.sndProfile.sndEquip
                self.player.mind.callRemote('playSound', snd)
            else:
                self.player.mind.callRemote('playSound', SND_INVENTORY)
            return

    def stackItem(self, sitem):
        if not sitem:
            return False
        else:
            stackMax = sitem.itemProto.stackMax
            if stackMax <= 1:
                return False
            useMax = sitem.itemProto.useMax
            stacking = {}
            if useMax > 1:
                neededCharges = useMax * (sitem.stackCount - 1) + sitem.useCharges
                for item in self.items:
                    if sitem == item or sitem.name != item.name:
                        continue
                    freeCharges = useMax * (stackMax - item.stackCount + 1) - item.useCharges
                    if freeCharges <= 0:
                        continue
                    if freeCharges > neededCharges:
                        freeCharges = neededCharges
                    stacking[item] = freeCharges
                    neededCharges -= freeCharges
                    if neededCharges <= 0:
                        break
                else:
                    return False

                for item, charges in stacking.iteritems():
                    stackCount = charges / useMax
                    charges = charges % useMax
                    item.stackCount += stackCount
                    item.useCharges += charges
                    if item.useCharges > useMax:
                        item.useCharges -= useMax
                        item.stackCount += 1
                    item.itemInfo.refreshDict({'STACKCOUNT': item.stackCount,
                     'USECHARGES': item.useCharges})

                return True
            neededStack = sitem.stackCount
            for item in self.items:
                if sitem == item or sitem.name != item.name:
                    continue
                freeStack = stackMax - item.stackCount
                if freeStack <= 0:
                    continue
                if freeStack > neededStack:
                    freeStack = neededStack
                stacking[item] = freeStack
                neededStack -= freeStack
                if neededStack <= 0:
                    break
            else:
                return False

            for item, count in stacking.iteritems():
                item.stackCount += count
                item.itemInfo.refreshDict({'STACKCOUNT': item.stackCount})

            return True

    def onLoot(self, mob, slot, alt = False):
        if not mob.loot or len(mob.loot.items) <= slot:
            return
        else:
            item = mob.loot.items[slot]
            mslot = item.slot
            if alt:
                if self.stackItem(item):
                    item.destroySelf()
                else:
                    if not self.player.giveItemInstance(item):
                        self.player.sendGameText(RPG_MSG_GAME_DENIED, '%s has no free inventory slots!\\n' % self.name)
                        return
                    if item.slot == -1:
                        traceback.print_stack()
                        print 'AssertionError: item owner whackiness!'
            else:
                if self.player.cursorItem:
                    self.player.sendGameText(RPG_MSG_GAME_DENIED, "Put down the item in %s\\'s cursor first!\\n" % self.name)
                    return
                item.setCharacter(self)
                item.slot = RPG_SLOT_CURSOR
                self.player.cursorItem = item
                self.player.updateCursorItem(None)
            if mslot != -1:
                mob.unequipItem(mslot)
                if len(mob.loot.items) > 1:
                    mob.mobInfo.refresh()
            mob.loot.items.remove(item)
            grants = isinstance(mob, GrantsProvider)
            if grants:
                id = mob.loot.lootids[slot]
                mob.loot.confirmed.append(id)
                mob.loot.lootids.remove(id)
            if item.itemProto.flags & RPG_ITEM_WORLDUNIQUE:
                for p in self.player.world.activePlayers:
                    p.sendGameText(RPG_MSG_GAME_BLUE, '%s has looted the sought-after <a:Item%s>%s</a>.\\n' % (item.character.name, GetTWikiName(item.itemProto.name), item.name))

            else:
                self.player.alliance.lootMessage(self.player, item)
            if not len(mob.loot.items):
                if not grants:
                    self.player.sendGameText(RPG_MSG_GAME_LOOT, 'As %s takes the last item, the corpse crumbles to dust!\\n' % self.name)
                self.player.stopLooting(mob, True)
            else:
                self.player.startLooting(mob, True)
            return

    def recoverDeathXP(self, xpRecover):
        pxp = int(self.xpDeathPrimary * xpRecover)
        sxp = int(self.xpDeathSecondary * xpRecover)
        txp = int(self.xpDeathTertiary * xpRecover)
        if pxp or sxp or txp:
            rez = (pxp, sxp, txp)
            self.gainXP(1, False, rez)
        self.xpDeathPrimary = 0
        self.xpDeathSecondary = 0
        self.xpDeathTertiary = 0
        if not pxp and not sxp and not txp:
            self.player.sendGameText(RPG_MSG_GAME_GOOD, '%s has been resurrected!\\n' % self.name)
            return
        self.player.sendGameText(RPG_MSG_GAME_GOOD, '%s has been resurrected and regained some lost experience!\\n' % self.name)

    def playerResurrect(self, xpRecover, healthRecover, manaRecover, staminaRecover):
        self.player.world.clearDeathMarker(self.player)
        self.recoverDeathXP(xpRecover)
        dz = self.deathZone
        self.deathZone = None
        mob = self.mob
        self.dead = False
        if healthRecover:
            mob.health = healthRecover
            if mob.health > mob.maxHealth:
                mob.health = mob.maxHealth
        else:
            mob.health = 1
        self.health = int(mob.health)
        if manaRecover:
            mob.mana = manaRecover
            if mob.mana > mob.maxMana:
                mob.mana = mob.maxMana
        else:
            mob.mana = 1
        self.mana = int(mob.mana)
        if staminaRecover:
            mob.stamina = staminaRecover
            if mob.stamina > mob.maxStamina:
                mob.stamina = mob.maxStamina
        else:
            mob.stamina = 1
        self.stamina = int(mob.stamina)
        if dz == self.player.zone.zone:
            self.player.zone.respawnPlayer(self.player, self.deathTransformInternal)
        else:
            from zone import TempZoneLink
            zlink = TempZoneLink(dz.name, self.deathTransformInternal)
            self.player.world.onZoneTrigger(self.player, zlink)
        return

    def resurrect(self, xpRecover):
        if not self.dead:
            return
        self.mob.autoAttack = False
        self.dead = False
        self.mob.health = 1
        self.mob.mana = 1
        self.mob.stamina = 1
        self.mob.zone.reattachMob(self.mob)
        self.recoverDeathXP(xpRecover)

    def loseXP(self, factor = 1.0, death = True):
        player = self.player
        spawn = self.spawn
        pneeded = spawn.plevel * spawn.plevel * 100L * self.pxpMod
        sneeded = spawn.slevel * spawn.slevel * 100L * self.sxpMod
        tneeded = spawn.tlevel * spawn.tlevel * 100L * self.txpMod
        pprevneeded = (spawn.plevel - 1) * (spawn.plevel - 1) * 100L * self.pxpMod
        sprevneeded = (spawn.slevel - 1) * (spawn.slevel - 1) * 100L * self.sxpMod
        tprevneeded = (spawn.tlevel - 1) * (spawn.tlevel - 1) * 100L * self.txpMod
        pgap = pneeded - pprevneeded
        sgap = sneeded - sprevneeded
        tgap = tneeded - tprevneeded
        pxploss = pgap / (spawn.plevel * 2)
        sxploss = 0
        txploss = 0
        if spawn.slevel:
            sxploss = sgap / (spawn.slevel * 2)
        if spawn.tlevel:
            txploss = tgap / (spawn.tlevel * 2)
        pxploss = int(pxploss * 0.8 * factor)
        sxploss = int(sxploss * 0.8 * factor)
        txploss = int(txploss * 0.8 * factor)
        if self.spawn.plevel < 5:
            pxploss = sxploss = txploss = 0
        losses = []
        if pxploss and self.xpPrimary:
            losses.append(str(pxploss))
        if sxploss and self.xpSecondary:
            losses.append(str(sxploss))
        if txploss and self.xpTertiary:
            losses.append(str(txploss))
        pxp = int(self.xpPrimary - pxploss)
        sxp = int(self.xpSecondary - sxploss)
        txp = int(self.xpTertiary - txploss)
        if death:
            if len(losses):
                player.sendGameText(RPG_MSG_GAME_CHARDEATH, '%s has died and lost %s experience!!\\n' % (self.name, '/'.join(losses)))
            else:
                player.sendGameText(RPG_MSG_GAME_CHARDEATH, '%s has died!!\\n' % self.name)
        else:
            player.sendGameText(RPG_MSG_GAME_CHARDEATH, '%s has lost %s experience!!\\n' % (self.name, '/'.join(losses)))
        if pxp < 0:
            pxploss = self.xpPrimary
            pxp = 0
        if sxp < 0:
            sxploss = self.xpSecondary
            sxp = 0
        if txp < 0:
            txploss = self.xpTertiary
            txp = 0
        self.xpDeathPrimary = pxploss
        self.xpDeathSecondary = sxploss
        self.xpDeathTertiary = txploss
        self.xpPrimary = int(pxp)
        self.xpSecondary = int(sxp)
        self.xpTertiary = int(txp)
        lost = False
        selector = {True: 's',
         False: ''}
        lostLevels = 0
        prevLevel = spawn.plevel - 1
        while pxp < pprevneeded and prevLevel > 0:
            lostLevels += 1
            prevLevel -= 1
            pprevneeded = prevLevel * prevLevel * 100L * self.pxpMod

        if lostLevels:
            lost = True
            spawn.level -= lostLevels
            spawn.plevel -= lostLevels
            self.player.sendGameText(RPG_MSG_GAME_LEVELLOST, '%s has lost %i primary level%s in the <a:Class%s>%s</a> class.\\n' % (self.name,
             lostLevels,
             selector[lostLevels > 1],
             GetTWikiName(spawn.pclassInternal),
             spawn.pclassInternal))
        lostLevels = 0
        prevLevel = spawn.slevel - 1
        while sxp < sprevneeded and prevLevel > 0:
            lostLevels += 1
            prevLevel -= 1
            sprevneeded = prevLevel * prevLevel * 100L * self.sxpMod

        if lostLevels:
            lost = True
            spawn.slevel -= lostLevels
            self.player.sendGameText(RPG_MSG_GAME_LEVELLOST, '%s has lost %i secondary level%s in the <a:Class%s>%s</a> class.\\n' % (self.name,
             lostLevels,
             selector[lostLevels > 1],
             GetTWikiName(spawn.sclassInternal),
             spawn.sclassInternal))
        lostLevels = 0
        prevLevel = spawn.tlevel - 1
        while txp < tprevneeded and prevLevel > 0:
            lostLevels += 1
            prevLevel -= 1
            tprevneeded = prevLevel * prevLevel * 100L * self.txpMod

        if lostLevels:
            lost = True
            spawn.tlevel -= lostLevels
            self.player.sendGameText(RPG_MSG_GAME_LEVELLOST, '%s has lost %i tertiary level%s in the <a:Class%s>%s</a> class.\\n' % (self.name,
             lostLevels,
             selector[lostLevels > 1],
             GetTWikiName(spawn.tclassInternal),
             spawn.tclassInternal))
        self.calcXPPercents()
        if lost:
            self.mob.levelChanged()

    def addStartingGear(self):
        slot = RPG_SLOT_CARRY0
        usedslots = []
        sgear = list(StartingGear.select())
        for sg in sgear:
            if sg.items != '' and sg.qualify(self.spawn):
                inames = sg.items.split(',')
                for iname in inames:
                    iproto = ItemProto.byName(iname)
                    item = iproto.createInstance()
                    item.slot = -1
                    for islot in iproto.slots:
                        if islot not in usedslots:
                            item.slot = islot
                            usedslots.append(islot)
                            break

                    if item.slot == -1:
                        item.slot = slot
                        slot += 1
                    item.setCharacter(self)

        credits = list(self.player.xpCredits)
        if len(credits):
            iproto = ItemProto.byName('Certificate of Experience')
            for cr in credits:
                credit = iproto.createInstance()
                credit.descOverride = "This certificate grants it's user %i experience points." % cr.xp
                credit.xpCoupon = cr.xp
                credit.setCharacter(self)
                credit.slot = slot
                slot += 1
                cr.destroySelf()
                if slot == RPG_SLOT_CARRY_END:
                    break

    def checkGiveItems(self, numItems):
        if numItems:
            usedslots = 0
            for item in self.items:
                if RPG_SLOT_CARRY_END > item.slot >= RPG_SLOT_CARRY_BEGIN:
                    usedslots += 1

            freeslots = RPG_SLOT_CARRY_END - RPG_SLOT_CARRY_BEGIN - usedslots
            if freeslots < numItems:
                self.player.sendGameText(RPG_MSG_GAME_DENIED, '%s needs %i free inventory spaces.\\n' % (self.name, numItems))
                return False
        return True

    def giveItemProtos(self, itemProtos, counts):
        player = self.player
        for proto, count in zip(itemProtos, counts):
            for c in xrange(0, count):
                item = proto.createInstance()
                slot = None
                for x in xrange(RPG_SLOT_CARRY_BEGIN, RPG_SLOT_CARRY_END):
                    for sitem in self.items:
                        if x == sitem.slot:
                            break
                    else:
                        slot = x
                        break

                if not slot:
                    traceback.print_stack()
                    print 'AssertionError: no slot found!'
                    return
                item.slot = slot
                item.setCharacter(self)
                player.sendGameText(RPG_MSG_GAME_GAINED, '%s has gained <a:Item%s>%s</a>!\\n' % (self.name, GetTWikiName(proto.name), item.name))

        return

    def takeItems(self, itemDict, silent = False):
        for proto, count in itemDict.items():
            if count <= 0:
                del itemDict[proto]

        if not len(itemDict):
            return
        else:
            if not silent:
                lostItems = defaultdict(int)
            for item in self.items[:]:
                if RPG_SLOT_TRADE_END > item.slot >= RPG_SLOT_TRADE_BEGIN:
                    continue
                if RPG_SLOT_LOOT_END > item.slot >= RPG_SLOT_LOOT_BEGIN:
                    continue
                if item.container:
                    for citem in item.container.content[:]:
                        citemProto = citem.itemProto
                        countNeeded = itemDict.get(citemProto, None)
                        if not countNeeded:
                            continue
                        sc = citem.stackCount
                        if not sc:
                            sc = 1
                        if sc > countNeeded:
                            sc = countNeeded
                        citem.stackCount -= sc
                        if citem.stackCount <= 0:
                            item.container.extractItem(citem)
                            citem.destroySelf()
                        else:
                            citem.itemInfo.refreshDict({'STACKCOUNT': citem.stackCount})
                        if not silent:
                            lostItems[citemProto] += sc
                        if sc < countNeeded:
                            itemDict[citemProto] -= sc
                            continue
                        del itemDict[citemProto]
                        if not len(itemDict):
                            break

                    if not len(itemDict):
                        break
                itemProto = item.itemProto
                countNeeded = itemDict.get(itemProto, None)
                if not countNeeded:
                    continue
                sc = item.stackCount
                if not sc:
                    sc = 1
                if sc > countNeeded:
                    sc = countNeeded
                item.stackCount -= sc
                if item.stackCount <= 0:
                    item.destroySelf()
                else:
                    item.itemInfo.refreshDict({'STACKCOUNT': item.stackCount})
                if not silent:
                    lostItems[itemProto] += sc
                if sc < countNeeded:
                    itemDict[itemProto] -= sc
                    continue
                del itemDict[itemProto]
                if not len(itemDict):
                    break

            if not silent:
                self.player.sendGameText(RPG_MSG_GAME_LOST, '%s lost %s.\\n' % (self.name, ', '.join(('<a:Item%s>%i %s</a>' % (GetTWikiName(ip.name), c, ip.name) for ip, c in lostItems.iteritems()))))
            self.player.cinfoDirty = True
            return

    def giveItemInstance(self, item):
        freeSlots = self.getFreeCarrySlots()
        if len(freeSlots):
            item.slot = freeSlots[0]
            item.setCharacter(self)
            return True
        else:
            if item.isUseable(self.mob):
                backupSlot = item.slot
                item.slot = -1
                self.equipItem(item)
                if item.slot != -1:
                    item.setCharacter(self)
                    return True
                item.slot = backupSlot
            for ownedItems in self.items:
                if ownedItems.slot == RPG_SLOT_CURSOR:
                    break
            else:
                item.slot = RPG_SLOT_CURSOR
                item.setCharacter(self)
                self.player.cursorItem = item
                self.player.updateCursorItem(None)
                return True

            return False

    def getFreeCarrySlots(self):
        freeSlots = range(RPG_SLOT_CARRY_BEGIN, RPG_SLOT_CARRY_END)
        for item in self.items:
            try:
                freeSlots.remove(item.slot)
            except:
                continue

        return freeSlots

    def checkSkillRaise(self, skillname, min = 3, max = 8, playSound = True, silent = False):
        mob = self.mob
        reuseTime = 0
        try:
            slevel = mob.skillLevels[skillname]
            mlevel = mob.mobSkillProfiles[skillname].maxValue
            reuseTime = mob.mobSkillProfiles[skillname].reuseTime
            questReq = mob.mobSkillProfiles[skillname].questRequirements
        except KeyError:
            return

        if slevel >= mlevel:
            return
        for qreq in questReq:
            if slevel >= qreq[1]:
                dcs = list(CharacterDialogChoice.select(AND(CharacterDialogChoice.q.identifier == qreq[0], CharacterDialogChoice.q.characterID == self.id)))
                if not dcs or not len(dcs) or not dcs[0].count:
                    return

        i = int(slevel / 10)
        if i < min:
            i = min
        if i > max:
            i = max
        if reuseTime:
            i /= 2
            if i < min:
                i = min
        if randint(0, i):
            return
        for skill in self.skills:
            if skill.skillname == skillname:
                skill.level += 1
                mob.skillLevels[skillname] = skill.level
                mob.updateClassStats()
                if not silent:
                    self.player.sendGameText(RPG_MSG_GAME_GAINED, '%s has become better at <a:Skill%s>%s</a>! (%i)\\n' % (self.name,
                     GetTWikiName(skillname),
                     skillname,
                     skill.level))
                return

    def removeAdvancementStats(self):
        mob = self.mob
        try:
            if not mob:
                return
            mob.derivedDirty = True
            mob.advancementStats = []
            mob.advancements.clear()
            for adv in self.advancements:
                for stat in adv.advancementProto.stats:
                    if stat.statname.startswith('advance_'):
                        continue
                    v = float(adv.rank) * stat.value
                    if stat.statname in RPG_RESISTSTATS:
                        mob.resists[RPG_RESISTLOOKUP[stat.statname]] -= v
                    else:
                        mob.__dict__[stat.statname] -= v

        except:
            traceback.print_exc()

    def applyAdvancementStats(self):
        mob = self.mob
        try:
            if not mob:
                return
            mob.derivedDirty = True
            mob.advancementStats = []
            advancements = mob.advancements
            advancements.clear()
            for adv in self.advancements:
                for stat in adv.advancementProto.stats:
                    v = float(adv.rank) * stat.value
                    if stat.statname.startswith('advance_'):
                        st = stat.statname[8:]
                        advancements[st] += v
                    elif stat.statname in RPG_RESISTSTATS:
                        mob.resists[RPG_RESISTLOOKUP[stat.statname]] += v
                    else:
                        mob.__dict__[stat.statname] += v
                        mob.advancementStats.append((stat.statname, v))

        except:
            traceback.print_exc()

    def checkAdvancements(self):
        advancements = list(self.advancements)
        for a in advancements:
            if hasattr(a, 'hasBeenDestroyed'):
                continue
            adv = list(self.advancements)
            for b in adv:
                if a == b:
                    continue
                for ex in a.advancementProto.exclusions:
                    if ex.exclude == b.advancementProto.name:
                        b.hasBeenDestroyed = True
                        b.destroySelf()

        self.advancementsCache = self.advancements
        if self.spawn.template and not self.spawn.flags & RPG_SPAWN_MONSTERADVANCED:
            from spawn import Spawn
            template = Spawn.byName(self.spawn.template)
            for i in xrange(2, template.plevel):
                points = int(float(i) / 2.0)
                if points < 5:
                    points = 5
                self.advancementPoints += points

            for i in xrange(2, template.slevel):
                points = int(float(i) / 2.0)
                if points < 3:
                    points = 3
                self.advancementPoints += points

            for i in xrange(2, template.tlevel):
                points = int(float(i) / 2.0)
                if points < 1:
                    points = 1
                self.advancementPoints += points

            self.spawn.flags |= RPG_SPAWN_MONSTERADVANCED

    def chooseAdvancement(self, advance):
        spawn = self.spawn
        try:
            a = AdvancementProto.byName(advance)
        except:
            print 'WARNING: Unknown Advancement %s' % advance
            return

        thisAdv = None
        existingAdv = {}
        for adv in self.advancements:
            proto = adv.advancementProto
            existingAdv[proto.name] = adv.rank
            if proto == a:
                thisAdv = adv

        passed = True
        if spawn.plevel < a.level or self.advancementPoints < a.cost or thisAdv and thisAdv.rank >= a.maxRank:
            passed = False
        elif len(a.classes):
            passed = False
            for cl in a.classes:
                if cl.classname == spawn.pclassInternal and cl.level <= spawn.plevel or cl.classname == spawn.sclassInternal and cl.level <= spawn.slevel or cl.classname == spawn.tclassInternal and cl.level <= spawn.tlevel:
                    passed = True
                    break

        if passed and len(a.races):
            passed = False
            for rc in a.races:
                if rc.racename == spawn.race and rc.level <= spawn.plevel:
                    passed = True
                    break

        if passed:
            for req in a.requirements:
                if req.require not in existingAdv or req.rank > existingAdv[req.require]:
                    passed = False
                    break

        if not passed:
            print 'WARNING: %s attempted unqualified advancement %s' % (self.name, advance)
            return
        else:
            self.removeAdvancementStats()
            if thisAdv:
                thisAdv.rank += 1
                self.advancementPoints -= a.cost
                self.applyAdvancementStats()
                self.player.sendGameText(RPG_MSG_GAME_GAINED, '%s has gained a rank in %s! (%i)\\n' % (self.name, advance, thisAdv.rank))
                return
            CharacterAdvancement(advancementProto=a, character=self)
            self.advancementPoints -= a.cost
            self.checkAdvancements()
            self.applyAdvancementStats()
            self.player.sendGameText(RPG_MSG_GAME_GAINED, '%s has advanced in %s!\\n' % (self.name, advance))
            self.advancementsCache = self.advancements
            return

    def onCraft(self, recipeID, useCraftWindow):
        if self.dead:
            self.player.sendGameText(RPG_MSG_GAME_DENIED, '%s is dead and cannot craft!\\n' % self.name)
            return
        from crafting import Craft
        Craft(self.mob, recipeID, useCraftWindow)

    def splitItem(self, item, newStackSize):
        if newStackSize >= item.stackCount or newStackSize < 1:
            return
        if len(self.getFreeCarrySlots()) < 1:
            self.player.sendGameText(RPG_MSG_GAME_DENIED, "%s doesn't have enough free carry slots for item split!\\n" % self.name)
            return
        nitem = item.clone()
        nitem.stackCount = item.stackCount - newStackSize
        if not self.giveItemInstance(nitem):
            nitem.destroySelf()
            raise Exception, 'Unable to give item instance on split!'
            return
        item.stackCount = newStackSize
        item.itemInfo.refreshDict({'STACKCOUNT': item.stackCount})

    def destroySelf(self):
        for o in self.spellsInternal:
            o.destroySelf()

        for o in self.itemsInternal:
            if RPG_SLOT_BANK_BEGIN <= o.slot < RPG_SLOT_BANK_END:
                o.character = None
            else:
                o.destroySelf()

        for o in self.advancements:
            o.destroySelf()

        for o in self.skills:
            o.destroySelf()

        for o in self.characterDialogChoices:
            o.destroySelf()

        for o in self.spellStore:
            o.destroySelf()

        for o in self.vaultItems:
            o.destroySelf()

        for o in self.characterFactions:
            o.destroySelf()

        self.spawn.destroySelf()
        Persistent.destroySelf(self)
        return