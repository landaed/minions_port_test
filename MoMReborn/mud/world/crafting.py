# Embedded file name: mud\world\crafting.pyo
from mud.common.persistent import Persistent
from mud.world.core import GenMoneyText
from mud.world.defines import *
from mud.world.item import getTomeAtLevelForScroll, ItemProto, ItemSpellTemp
from mud.world.itemvariants import AddStatVariant, V_BANEWEAPON, V_STAT, V_WEAPON
from mud.world.spell import Spell, SpellProto
from mud.world.shared.sounddefs import *
from mud.worlddocs.utils import GetTWikiName
from collections import defaultdict
from math import ceil
from random import randint
from sqlobject import *
WEAPON_SKILLS = ('1H Pierce',
 '2H Pierce',
 '1H Impact',
 '2H Impact',
 '1H Cleave',
 '2H Cleave',
 '1H Slash',
 '2H Slash',
 'Archery')
ARMOR_SKILLS = ('Light Armor',
 'Medium Armor',
 'Heavy Armor',
 'Shield')

class RecipeIngredient(Persistent):
    recipe = ForeignKey('Recipe')
    itemProto = ForeignKey('ItemProto')
    count = IntCol(default=1)


class Recipe(Persistent):
    name = StringCol(alternateID=True)
    craftedItemProto = ForeignKey('ItemProto')
    craftSound = StringCol(default='')
    skillname = StringCol()
    skillLevel = IntCol()
    filterClass = StringCol(default='')
    filterRealm = IntCol(default=-1)
    filterRace = StringCol(default='')
    filterLevelMin = IntCol(default=0)
    filterLevelMax = IntCol(default=1000)
    costTP = IntCol(default=0L)
    ingredients = MultipleJoin('RecipeIngredient')


FORGE_LOOKUP = {'anidaenforest': (654.112,
                   -175.686,
                   146.782,
                   100),
 'hazerothkeep': (716,
                  472,
                  210,
                  100),
 'kauldur': (-245,
             -493,
             150,
             100),
 'mountain': (650.116,
              -607.307,
              160.346,
              100),
 'trinst': (128,
            186,
            127,
            100)}

def getBlacksmithingMods(mob, craftProto, skillLevel):
    noForge = False
    notify = False
    if 100 >= skillLevel or not mob.simObject:
        noForge = True
    elif mob.zone.zone.name not in FORGE_LOOKUP:
        noForge = True
        notify = True
    else:
        mobPos = mob.simObject.position
        forgePos = FORGE_LOOKUP[mob.zone.zone.name]
        x = mobPos[0] - forgePos[0]
        y = mobPos[1] - forgePos[1]
        z = mobPos[2] - forgePos[2]
        if x * x + y * y + z * z > forgePos[3]:
            noForge = True
            notify = True
    player = mob.player
    char = mob.character
    if notify:
        player.sendGameText(RPG_MSG_GAME_DENIED, "%s can't use a forge here and may only craft items of lesser quality.\\n" % char.name)
    protoUseMax = craftProto.useMax
    protoStackDefault = craftProto.stackDefault
    protoStackMax = craftProto.stackMax
    if noForge:
        charges = int(ceil(0.5 * float(protoUseMax)))
        stackCount = protoStackDefault
        moneyMod = 5.0
    else:
        mod = float(skillLevel - 10) / 900.0
        if 1 < protoUseMax:
            charges = int(ceil(0.5 * float(protoUseMax) * (1.0 + mod)))
            if charges > protoUseMax:
                charges = protoUseMax
            stackCount = protoStackDefault
            moneyMod = 0.2 * (float(charges) - float(protoUseMax) / 2.0) + 1.0
        elif 1 < protoStackMax:
            charges = protoUseMax
            stackCount = int(float(protoStackDefault) * (1.0 + mod))
            moneyMod = 0.2 * float(stackCount - protoStackDefault) + 1.0
        else:
            charges = protoUseMax
            stackCount = 1
            moneyMod = 1.5 - mod
    return (moneyMod, stackCount, charges)


ENCHANT_skillname = 'Enchanting'
ENCHANT_MergeCount = 2
ENCHANT_MaxEnchantTypes = 5
ENCHANT_MinSpellLevelReq = 3
ENCHANT_SpellComponentMod = 3
ENCHANT_RawItems = ['Sandstone',
 'Coal',
 'Icy Shard',
 'Bark',
 'Limestone',
 'Quartz',
 'Blighted Shard',
 'Vine',
 'Muck-Covered Stone']
ENCHANT_QualitySkillReq = [1,
 1,
 1,
 60,
 120,
 180,
 240,
 300]
ENCHANT_RawAttribsLUT = {'HEALTH': ['Health', 50],
 'MANA': ['Ether', 50],
 'ETHER': ['Ether', 50],
 'STAMINA': ['Endurance', 50],
 'ENDURANCE': ['Endurance', 50],
 'STRENGTH': ['Strength', 200],
 'BODY': ['Constitution', 200],
 'CONSTITUTION': ['Constitution', 200],
 'REFLEX': ['Instinct', 200],
 'INSTINCT': ['Instinct', 200],
 'AGILITY': ['Nimbleness', 200],
 'NIMBLENESS': ['Nimbleness', 200],
 'DEXTERITY': ['Quickness', 200],
 'QUICKNESS': ['Quickness', 200],
 'MIND': ['Insight', 200],
 'INSIGHT': ['Insight', 200],
 'WISDOM': ['Clarity', 200],
 'CLARITY': ['Clarity', 200],
 'MYSTICISM': ['the Arcane', 200],
 'THE ARCANE': ['the Arcane', 200]}
ENCHANT_SlotLUT = {'all': {'Strength': ['str', 400, 300],
         'Constitution': ['bdy', 400, 300],
         'Instinct': ['ref', 400, 300],
         'Nimbleness': ['agi', 400, 300],
         'Quickness': ['dex', 400, 300],
         'Insight': ['mnd', 400, 300],
         'Clarity': ['wis', 400, 300],
         'the Arcane': ['mys', 400, 300]},
 RPG_SLOT_HEAD: {'Health': ['maxHealth', 800, 1],
                 'Ether': ['maxMana', 4000, 1],
                 'Defense': ['armor', 300, 100],
                 'Physical Protection': ['resistPhysical', 60, 500],
                 'Magic Protection': ['resistMagical', 60, 500],
                 'Aelieas': ['regenMana', 50, 800]},
 RPG_SLOT_BACK: {'Ether': ['maxMana', 2400, 1],
                 'Defense': ['armor', 200, 100],
                 'Magic Protection': ['resistMagical', 80, 500],
                 'the Sphinx': ['castHaste', 0.15, 800]},
 RPG_SLOT_CHEST: {'Health': ['maxHealth', 4000, 1],
                  'Endurance': ['maxStamina', 1500, 1],
                  'Defense': ['armor', 600, 100],
                  'Physical Protection': ['resistPhysical', 80, 500],
                  'Fiery Protection': ['resistFire', 80, 500],
                  'Cold Protection': ['resistCold', 80, 500],
                  'Acidity': ['resistAcid', 80, 500],
                  'Electrical Resistance': ['resistElectrical', 80, 500],
                  'the Dwarven King': ['regenHealth', 30, 800]},
 RPG_SLOT_ARMS: {'Health': ['maxHealth', 600, 1],
                 'Defense': ['armor', 300, 100],
                 'Fiery Protection': ['resistFire', 30, 500],
                 'Cold Protection': ['resistCold', 30, 500],
                 'Lightning': ['castDmgMod', 0.5, 900]},
 RPG_SLOT_HANDS: {'Health': ['maxHealth', 600, 1],
                  'Ether': ['maxMana', 900, 1],
                  'Defense': ['armor', 200, 100],
                  'Fiery Protection': ['resistFire', 30, 500],
                  'Cold Protection': ['resistCold', 30, 500],
                  'Acidity': ['resistAcid', 30, 500],
                  'Electrical Resistance': ['resistElectrical', 30, 500],
                  'the Warling Cleric': ['castHealMod', 0.5, 700],
                  'the Sphinx': ['castHaste', 0.4, 800]},
 RPG_SLOT_PRIMARY: {'the Ghoul Slayer': ['Undead Bane', 10, 400]},
 RPG_SLOT_SECONDARY: {'the Ghoul Slayer': ['Undead Bane', 10, 400]},
 RPG_SLOT_RANGED: {'the Ghoul Slayer': ['Undead Bane', 10, 400]},
 RPG_SLOT_WAIST: {'Health': ['maxHealth', 600, 1],
                  'Defense': ['armor', 100, 100],
                  'Poison Resist': ['resistPoison', 80, 500],
                  'Disease Resist': ['resistDisease', 80, 500],
                  'Volsh': ['haste', 1.25, 800]},
 RPG_SLOT_LEGS: {'Health': ['maxHealth', 800, 1],
                 'Endurance': ['maxStamina', 1200, 1],
                 'Defense': ['armor', 400, 100],
                 'Physical Protection': ['resistPhysical', 60, 500],
                 'the Dwarven King': ['regenHealth', 20, 800],
                 'the Cavebear': ['regenStamina', 20, 800]},
 RPG_SLOT_FEET: {'Health': ['maxHealth', 600, 1],
                 'Endurance': ['maxStamina', 3000, 1],
                 'Defense': ['armor', 300, 100],
                 'Poison Resist': ['resistPoison', 75, 500],
                 'Disease Resist': ['resistDisease', 75, 500],
                 'Acidity': ['resistAcid', 50, 500],
                 'Electrical Resistance': ['resistElectrical', 50, 500],
                 'the Cavebear': ['regenStamina', 35, 800],
                 'Speed': ['move', 2.0, 800]},
 RPG_SLOT_SHIELD: {'Defense': ['armor', 800, 100],
                   'Physical Protection': ['resistPhysical', 120, 500],
                   'Magic Protection': ['resistMagical', 120, 500],
                   'Fiery Protection': ['resistFire', 120, 500],
                   'Cold Protection': ['resistCold', 120, 500],
                   'Poison Resist': ['resistPoison', 120, 500],
                   'Disease Resist': ['resistDisease', 120, 500],
                   'Acidity': ['resistAcid', 120, 500],
                   'Electrical Resistance': ['resistElectrical', 120, 500]},
 RPG_SLOT_SHOULDERS: {'Defense': ['armor', 500, 100],
                      'Physical Protection': ['resistPhysical', 80, 500]},
 RPG_SLOT_LEAR: {},
 RPG_SLOT_REAR: {},
 RPG_SLOT_NECK: {'Magic Protection': ['resistMagical', 110, 500],
                 'Fiery Protection': ['resistFire', 90, 500],
                 'Cold Protection': ['resistCold', 90, 500],
                 'Poison Resist': ['resistPoison', 80, 500],
                 'Disease Resist': ['resistDisease', 80, 500],
                 'Acidity': ['resistAcid', 80, 500],
                 'Electrical Resistance': ['resistElectrical', 110, 500]},
 RPG_SLOT_LFINGER: {},
 RPG_SLOT_RFINGER: {},
 RPG_SLOT_LWRIST: {},
 RPG_SLOT_RWRIST: {}}

def FocusGenSpecific(focusname):
    try:
        focusQuality, focusType = focusname.split(' ', 1)
        focusQuality = focusQuality.capitalize()
        if focusQuality not in ENCHANT_QualityPrefix:
            return None
        if focusQuality == 'Raw':
            return None
        con = ItemProto._connection.getConnection()
        protoID, name = con.execute('SELECT id,name FROM item_proto WHERE lower(name)=lower("%s") LIMIT 1;' % focusType).fetchone()
        enchFocus = ItemProto.get(protoID)
        focus = enchFocus.createInstance()
        for i, v in enumerate(ENCHANT_QualityPrefix):
            if focusQuality == v:
                focus.spellEnhanceLevel = i + 10
                break

        focus.name = str('%s %s' % (focusQuality, name))
        focus.slot = -1
        return focus
    except:
        return None

    return None


def EnchantCmd(mob, enchName):
    player = mob.player
    char = mob.character
    enchFoci = [ [] for i in xrange(ENCHANT_QualityCount) ]
    enchTarget = []
    emptySlots = range(RPG_SLOT_CRAFTING_BEGIN, RPG_SLOT_CRAFTING_END)
    enchanted = False
    healthCost = 0
    manaCost = 0
    staminaCost = 0
    statCost = []
    slevel = mob.skillLevels.get(ENCHANT_skillname, 0)
    if not slevel:
        player.sendGameText(RPG_MSG_GAME_DENIED, "%s doesn't know how to enchant anything.\\n" % char.name)
        return
    elif ENCHANT_skillname in mob.skillReuse:
        player.sendGameText(RPG_MSG_GAME_DENIED, '%s is still recovering from a previous enchant, and can enchant again in about %i seconds.\\n' % (char.name, mob.skillReuse[ENCHANT_skillname]))
        return
    else:
        mskill = mob.mobSkillProfiles[ENCHANT_skillname]
        mob.skillReuse[ENCHANT_skillname] = mskill.reuseTime
        skillReq = 0
        costMod = 1 - 0.0005 * slevel
        costModSQ = costMod * costMod
        if mob.attacking or mob.charmEffect or mob.isFeared or mob.sleep > 0 or mob.stun > 0 or mob.casting:
            player.sendGameText(RPG_MSG_GAME_DENIED, "$src\\'s enchanting failed, $srche is in no condition to enchant anything!\\n", mob)
            return
        mob.cancelInvisibility()
        mob.cancelFlying()
        mob.cancelStatProcess('feignDeath', '$tgt is obviously not dead!\\n')
        mob.cancelStatProcess('sneak', '$tgt is no longer sneaking!\\n')
        foundFocus = False
        for item in char.items:
            if RPG_SLOT_CRAFTING_END > item.slot >= RPG_SLOT_CRAFTING_BEGIN:
                emptySlots.remove(item.slot)
                if item.crafted:
                    for islot in item.itemProto.slots:
                        if islot in ENCHANT_SlotLUT:
                            enchTarget.append(item)
                            break

                elif item.skill == ENCHANT_skillname:
                    spellEnhanceLevel = item.spellEnhanceLevel
                    if spellEnhanceLevel:
                        spellEnhanceLevel -= 10
                    enchFoci[spellEnhanceLevel].append(item)
                    foundFocus = True

        if not foundFocus:
            player.sendGameText(RPG_MSG_GAME_DENIED, "%s can't focus on anything to enchant.\\n" % char.name)
            return
        if len(enchName):
            firstWord = enchName.split(' ', 1)[0]
            if firstWord == 'FOCUS':
                if not len(enchFoci[0]):
                    player.sendGameText(RPG_MSG_GAME_DENIED, "%s doesn't have a raw focus to enchant.\\n" % char.name)
                    return
                skillReq = 1000
                enchNameAttrib = enchName.split(' OF ', 1)[-1]
                try:
                    skillReq = ENCHANT_RawAttribsLUT[enchNameAttrib][1]
                    enchNameAttrib = ENCHANT_RawAttribsLUT[enchNameAttrib][0]
                except:
                    player.sendGameText(RPG_MSG_GAME_DENIED, "%s can't enchant a focus with this attribute.\\n" % char.name)
                    return

                enchTarget = None
                if not len(emptySlots):
                    for foc in enchFoci[0]:
                        if foc.stackCount <= 1:
                            enchTarget = foc
                            break

                    if not enchTarget:
                        player.sendGameText(RPG_MSG_GAME_DENIED, '%s has no more room in the crafting inventory.\\n' % char.name)
                        return
                else:
                    enchTarget = enchFoci[0][0]
                basicCost = skillReq * costModSQ
                if enchNameAttrib == 'Health':
                    healthCost = int(basicCost * 4)
                    manaCost = int(basicCost) << 1
                elif enchNameAttrib == 'Ether':
                    manaCost = int(basicCost * 6)
                elif enchNameAttrib == 'Endurance':
                    staminaCost = int(basicCost * 4)
                    manaCost = int(basicCost) << 1
                else:
                    manaCost = int(basicCost * 8)
                    statCost.append(ENCHANT_SlotLUT['all'][enchNameAttrib][0])
                    statCost.append(statCost[0] + 'Base')
                    statCost.append(statCost[0] + 'Raise')
                    statCost.append(-1)
                    statCost.append(getattr(char, statCost[2]))
                    if statCost[-1] >= 300:
                        player.sendGameText(RPG_MSG_GAME_DENIED, "%s isn't powerful enough for this enchantment.\\n" % char.name)
                        return
                if mob.health < healthCost + 1:
                    player.sendGameText(RPG_MSG_GAME_DENIED, "%s doesn't have enough health to power the focus.\\n" % char.name)
                    return
                if mob.mana < manaCost:
                    player.sendGameText(RPG_MSG_GAME_DENIED, "%s doesn't have enough mana to power the focus.\\n" % char.name)
                    return
                if mob.mana < staminaCost:
                    player.sendGameText(RPG_MSG_GAME_DENIED, "%s doesn't have enough stamina to power the focus.\\n" % char.name)
                    return
                if slevel < skillReq and randint(0, int((1.0 - float(slevel) / float(skillReq)) * 10.0)):
                    player.sendGameText(RPG_MSG_GAME_DENIED, '%s failed the focus enchantment.\\n' % char.name)
                    buffMod = 2.0 - float(slevel) / 1000.0
                    mob.processesPending.add(Spell(mob, mob, SpellProto.byName('Enchanting - Mana drain'), buffMod, 0, 'Mana Drain'))
                    mob.mana -= manaCost
                    mob.stamina -= staminaCost
                    mob.health -= healthCost
                    if mob.health < 1:
                        mob.health = 1
                    return
                newFocus = enchTarget.itemProto.createInstance()
                newFocus.spellEnhanceLevel = int(1 + slevel / 166)
                newFocus.name = '%s %s of %s' % (ENCHANT_QualityPrefix[newFocus.spellEnhanceLevel], enchTarget.name, enchNameAttrib)
                newFocus.spellEnhanceLevel += 10
                newFocus.descOverride = 'This %s gleams with a magical hue. It may be used to enchant items.' % enchTarget.name
                if enchTarget.stackCount <= 1:
                    newFocus.slot = enchTarget.slot
                    player.takeItem(enchTarget)
                else:
                    newFocus.slot = emptySlots.pop()
                    enchTarget.stackCount -= 1
                    enchTarget.itemInfo.refreshDict({'STACKCOUNT': enchTarget.stackCount})
                newFocus.setCharacter(char)
                player.sendGameText(RPG_MSG_GAME_GAINED, '%s successfully enchanted a raw focus with mystic power.\\n' % char.name)
                enchanted = True
            else:
                if not len(enchTarget) == 1:
                    player.sendGameText(RPG_MSG_GAME_DENIED, 'You need to put one single crafted item into the crafting window.\\n')
                    return
                enchTarget = enchTarget[0]
                enchProto = enchTarget.itemProto
                if not enchProto.wpnDamage or enchProto.projectile:
                    player.sendGameText(RPG_MSG_GAME_DENIED, 'Only melee weapons or bows can be enchanted with a proc.\\n')
                    return
                if len(enchTarget.procs) >= RPG_ITEMPROC_MAX:
                    player.sendGameText(RPG_MSG_GAME_DENIED, "This weapon can't hold any more power enchantments.\\n")
                    return
                enchSpell = None
                cspell = None
                for knownSpell in char.spells:
                    knownSpellProto = knownSpell.spellProto
                    if knownSpellProto.name.upper() == enchName:
                        if knownSpellProto.qualify(mob):
                            enchSpell = knownSpell
                            cspell = knownSpellProto
                        break

                if not enchSpell:
                    player.sendGameText(RPG_MSG_GAME_DENIED, '%s cannot cast this spell.\\n' % char.name)
                    return
                if not cspell.spellType & RPG_SPELL_HARMFUL:
                    player.sendGameText(RPG_MSG_GAME_DENIED, 'Weapons can only be enchanted with harmful spells.\\n')
                    return
                if not enchSpell.level >= ENCHANT_MinSpellLevelReq:
                    player.sendGameText(RPG_MSG_GAME_DENIED, "%s doesn't know this spell enough to enchant a weapon with it.\\n" % char.name)
                    return
                charms = False
                for eff in cspell.effectProtos:
                    if eff.flags & RPG_EFFECT_CHARM:
                        charms = True
                        break

                if charms or cspell.affectsStat('stun') or cspell.affectsStat('sleep') or cspell.affectsStat('fear'):
                    player.sendGameText(RPG_MSG_GAME_DENIED, "Stun, sleep, fear and charm spells aren't allowed for weapon enchantments.\\n")
                    return
                if mob.recastTimers.has_key(cspell):
                    player.sendGameText(RPG_MSG_GAME_DENIED, '%s has to wait another %i seconds before attempting to cast this spell again.\\n' % (char.name, int(mob.recastTimers[cspell] / 6)))
                    return
                manaCost = int((cspell.manaCost + enchTarget.level * 5) * 10 * costMod)
                staminaCost = int(0.2 * mob.maxStamina * costModSQ)
                if mob.mana < manaCost:
                    player.sendGameText(RPG_MSG_GAME_DENIED, "%s doesn't have enough mana to enchant this item.\\n" % char.name)
                    return
                if mob.stamina < staminaCost:
                    player.sendGameText(RPG_MSG_GAME_DENIED, "%s doesn't have enough stamina to enchant this item.\\n" % char.name)
                    return
                components = defaultdict(int)
                if len(cspell.components):
                    for c in cspell.components:
                        if c.count > 0:
                            components[c.itemProto] += int(c.count * ENCHANT_SpellComponentMod)

                    if not player.checkItems(components.copy(), True):
                        player.sendGameText(RPG_MSG_GAME_DENIED, '$src lacks the spell components for this enchantment,\\n$srche needs: %s\\n' % ', '.join(('<a:Item%s>%i %s</a>' % (GetTWikiName(ip.name), c, ip.name) for ip, c in components.iteritems())), mob)
                        return
                if cspell.recastTime:
                    mob.recastTimers[cspell] = cspell.recastTime
                if enchTarget.itemProto.level * 0.9 < cspell.level:
                    player.sendGameText(RPG_MSG_GAME_DENIED, "The %s can't hold this amount of power and it just seeps out again.\\n" % enchTarget.name)
                    mob.mana -= manaCost >> 1
                    mob.stamina -= staminaCost >> 1
                    return
                if len(components):
                    player.takeItems(components)
                skillReq = float(cspell.level) / float(enchTarget.level) * 54.0 + 1.0
                reqMod = float(cspell.level) / 90.0 * 4.4
                skillReq *= reqMod * reqMod + 1.0
                if enchTarget.repairMax > 0:
                    if enchTarget.repair > 0:
                        skillReq *= float(enchTarget.repairMax) / float(enchTarget.repair)
                    else:
                        skillReq = 9999999
                skillReq = int(skillReq)
                success = randint(0, skillReq * 7 / 5)
                if success > slevel:
                    mob.processesPending.add(Spell(mob, mob, SpellProto.byName('Enchanting failure')))
                    player.sendGameText(RPG_MSG_GAME_LOST, 'The enchantment was too unstable and vanishes in an explosion!\\n')
                    mob.mana -= manaCost
                    mob.stamina -= staminaCost
                    mob.health -= int(mob.maxHealth * 0.1)
                    if mob.health < 1:
                        mob.health = 1
                    if enchTarget.repairMax and enchTarget.repair:
                        enchTarget.repair -= randint(1, 25)
                        if enchTarget.repair < 0:
                            enchTarget.repair = 0
                        repairRatio = float(enchTarget.repair) / float(enchTarget.repairMax)
                        if not repairRatio:
                            player.sendGameText(RPG_MSG_GAME_RED, "%s's %s has shattered in the explosion! (%i/%i)\\n" % (char.name,
                             enchTarget.name,
                             enchTarget.repair,
                             enchTarget.repairMax))
                            mob.playSound('sfx/Shatter_IceBlock1.ogg')
                        elif repairRatio < 0.2:
                            player.sendGameText(RPG_MSG_GAME_YELLOW, "%s's %s got severely damaged by the explosion! (%i/%i)\\n" % (char.name,
                             enchTarget.name,
                             enchTarget.repair,
                             enchTarget.repairMax))
                            mob.playSound('sfx/Menu_Horror24.ogg')
                    enchTarget.itemInfo.refresh()
                    return
                skillReq = min(skillReq, 1000)
                duration = int(round(0.008 * slevel + 2)) - randint(-3, 2)
                if duration < 1:
                    duration = 1
                frequency = int(round(10 - 0.008 * slevel)) + randint(-1, 5)
                if frequency < 2:
                    frequency = 2
                newProc = ItemSpellTemp(cspell, RPG_ITEM_TRIGGER_POISON, frequency)
                enchTarget.procs[newProc] = [duration, RPG_ITEMPROC_ENCHANTMENT]
                enchTarget.itemInfo.refresh()
                player.sendGameText(RPG_MSG_GAME_GAINED, '%s successfully enchanted the %s with %s.\\n' % (char.name, enchTarget.name, cspell.name))
                enchanted = True
        elif len(enchTarget):
            if len(enchTarget) > 1:
                player.sendGameText(RPG_MSG_GAME_DENIED, "It's too stressful to enchant multiple items at once.\\n")
                return
            enchTarget = enchTarget[0]
            basicProto = enchTarget.itemProto
            primarySuccessMod = 1.0
            desiredEnchantments = {}
            desiredEnchantments[0] = [0, []]
            skillReq = basicProto.level * 5
            modif = float(slevel) / float(skillReq)
            if modif < 1:
                primarySuccessMod *= modif
            rel = basicProto.level / 100.0
            enchStatMod = 0.005 + 0.995 * rel * rel
            enchFoci = reduce(list.__add__, enchFoci[1:])
            try:
                for var in enchTarget.variants[V_STAT]:
                    try:
                        desiredEnchantments[var[0]][0] += var[1]
                    except KeyError:
                        desiredEnchantments[var[0]] = [var[1], []]

            except KeyError:
                pass

            try:
                baneRace, baneMod = enchTarget.variants[V_BANEWEAPON]
                desiredEnchantments[baneRace + ' Bane'] = [baneMod, []]
            except KeyError:
                pass

            foundFocus = False
            clampedStats = []
            for foc in enchFoci:
                enchAttrName = foc.name.split(' of ', 1)[-1]
                focusType = None
                try:
                    focusType = ENCHANT_SlotLUT['all'][enchAttrName]
                except:
                    try:
                        focusType = ENCHANT_SlotLUT[basicProto.slots[0]][enchAttrName]
                    except:
                        continue

                foundFocus = True
                focusSuccessMod = primarySuccessMod
                if not foc.stackCount:
                    foc.stackCount = 1
                skillReq += int(focusType[2] / 10.0 * float(foc.stackCount))
                modif = float(slevel) / focusType[2]
                if modif < 1:
                    focusSuccessMod *= modif
                spellEnhanceLevel = foc.spellEnhanceLevel - 10
                modif = 0.5 * slevel / float(ENCHANT_QualitySkillReq[spellEnhanceLevel])
                skillReq += int(float(ENCHANT_QualitySkillReq[spellEnhanceLevel]) / 10.0 * float(foc.stackCount))
                if modif < 1:
                    focusSuccessMod *= modif
                focusEnchantValue = 0.2 * focusType[1] / float(9 - spellEnhanceLevel)
                if focusSuccessMod < 0.01:
                    focusSuccessMod = 0.01
                focusEnchantValue *= (randint(40 * foc.stackCount, 60 * foc.stackCount) - randint(0, foc.stackCount * int(round(1 / focusSuccessMod - 1)))) / 50.0
                if desiredEnchantments.has_key(focusType[0]):
                    manaCost += 2 * focusType[2] * foc.stackCount
                    desiredEnchantments[focusType[0]][0] += focusEnchantValue
                    desiredEnchantments[focusType[0]][1].append(foc)
                    focMaxValue = enchStatMod * focusType[1]
                    if desiredEnchantments[focusType[0]][0] > focMaxValue:
                        manaCost += int(200 * (desiredEnchantments[focusType[0]][0] / focMaxValue - 1.0))
                        desiredEnchantments[focusType[0]][0] = focMaxValue
                        clampedStats.append(foc.name)
                    if focusType[1] >= 10:
                        desiredEnchantments[focusType[0]][0] = int(ceil(desiredEnchantments[focusType[0]][0]))
                elif len(desiredEnchantments) <= ENCHANT_MaxEnchantTypes:
                    manaCost += focusType[2] * foc.stackCount
                    desiredEnchantments[focusType[0]] = [focusEnchantValue, [foc]]
                    focMaxValue = enchStatMod * focusType[1]
                    if desiredEnchantments[focusType[0]][0] > focMaxValue:
                        manaCost += int(100 * (desiredEnchantments[focusType[0]][0] / focMaxValue - 1.0))
                        desiredEnchantments[focusType[0]][0] = focMaxValue
                        clampedStats.append(foc.name)
                    if focusType[1] >= 10:
                        desiredEnchantments[focusType[0]][0] = int(ceil(desiredEnchantments[focusType[0]][0]))
                else:
                    manaCost += 3 * focusType[2] * foc.stackCount
                    desiredEnchantments[0][1].append(foc)
                    desiredEnchantments[0][0] += foc.stackCount

            manaCost = int(manaCost * costMod)
            if not foundFocus:
                player.sendGameText(RPG_MSG_GAME_DENIED, "%s doesn't know how to use these foci in conjuction with the %s.\\n" % (char.name, enchTarget.name))
                return
            if mob.mana < manaCost:
                player.sendGameText(RPG_MSG_GAME_DENIED, "%s doesn't have enough mana for this enchantment.\\n" % char.name)
                return
            if desiredEnchantments[0][0]:
                modif = 2.0 / desiredEnchantments[0][0]
                if modif < 1.0:
                    primarySuccessMod *= modif
            if primarySuccessMod < 1:
                if not randint(0, int(primarySuccessMod * 10)):
                    mob.processesPending.add(Spell(mob, mob, SpellProto.byName('Enchanting failure')))
                    player.takeItem(enchTarget)
                    for foc in enchFoci:
                        player.takeItem(foc)

                    mob.mana -= manaCost
                    mob.health -= int(mob.maxHealth * 0.4)
                    if mob.health < 1:
                        mob.health = 1
                    player.sendGameText(RPG_MSG_GAME_LOST, '%s accidentally turned this enchantment into a puff of smoke.\\n' % char.name)
                    return
            if skillReq > 1000:
                skillReq = 1000
            enchTarget.levelOverride = basicProto.level
            enchTarget.clearVariants()
            if desiredEnchantments[0][0]:
                player.sendGameText(RPG_MSG_GAME_LOST, "The %s can't hold all of that power and some of it just seeps out again.\\n" % enchTarget.name)
            expungeList = desiredEnchantments.pop(0)
            expungeList = expungeList[1]
            map(player.takeItem, expungeList)
            for attr in desiredEnchantments:
                enchValue = desiredEnchantments[attr][0]
                map(player.takeItem, desiredEnchantments[attr][1])
                if not enchValue:
                    continue
                enchanted = True
                AddStatVariant(enchTarget, attr, enchValue)
                enchTarget.levelOverride += 2

            if enchanted:
                enchTarget.name = 'Enchanted ' + basicProto.name
                if enchTarget.levelOverride > 100:
                    enchTarget.levelOverride = 100
                enchTarget.descOverride = enchTarget.descOverride.split('\\nEnchanted by')[0] + '\\nEnchanted by %s' % char.name
                enchTarget.hasVariants = True
                enchTarget.spellEnhanceLevel = 9999
            else:
                enchTarget.descOverride = enchTarget.descOverride.split('\\nEnchanted by')[0]
                enchTarget.hasVariants = False
                enchTarget.spellEnhanceLevel = 0
                enchTarget.flags = enchTarget.flags & ~RPG_ITEM_ENCHANTED
                enchTarget.quality = RPG_QUALITY_NORMAL
                enchTarget.worthIncreaseTin = 0
            enchTarget.crafted = True
            enchTarget.refreshFromProto()
            enchanted = True
            numClampedStats = len(clampedStats)
            if numClampedStats:
                if 1 == numClampedStats:
                    player.sendGameText(RPG_MSG_GAME_LOST, "The %s become stable as some of %s's energy escapes.\\n" % (enchTarget.name, clampedStats[0]))
                elif 2 == numClampedStats:
                    player.sendGameText(RPG_MSG_GAME_LOST, "The %s become stable as some of %s and %s's energy escapes.\\n" % (enchTarget.name, clampedStats[0], clampedStats[1]))
                else:
                    player.sendGameText(RPG_MSG_GAME_LOST, "The %s become stable as some of %s, and %s's energy escapes.\\n" % (enchTarget.name, ', '.join(clampedStats[:-1]), clampedStats[-1]))
        else:
            for qualityIndex, partialFociList in zip(range(2, ENCHANT_QualityCount), enchFoci[1:-1]):
                if not len(partialFociList):
                    continue
                skillReq = ENCHANT_QualitySkillReq[qualityIndex]
                if slevel < skillReq:
                    player.sendGameText(RPG_MSG_GAME_DENIED, "%s doesn't know how to merge these items yet.\\n" % char.name)
                    return
                manaCost = int(skillReq * 10 * costModSQ)
                if mob.mana < manaCost:
                    player.sendGameText(RPG_MSG_GAME_DENIED, "%s doesn't have enough mana to merge these items.\\n" % char.name)
                    return
                focusName = partialFociList[0].name
                focusCount = partialFociList[0].stackCount
                if not focusCount:
                    focusCount = 1
                for counter in xrange(1, len(partialFociList)):
                    foc = partialFociList[counter]
                    if foc.name == focusName:
                        if not foc.stackCount:
                            focusCount += 1
                        else:
                            focusCount += foc.stackCount
                    else:
                        player.sendGameText(RPG_MSG_GAME_DENIED, 'Only foci of the same kind can be merged.\\n')
                        return

                if focusCount < ENCHANT_MergeCount:
                    player.sendGameText(RPG_MSG_GAME_DENIED, "%s hasn't enough %s to merge.\\n" % (char.name, focusName))
                    return
                if not len(emptySlots):
                    player.sendGameText(RPG_MSG_GAME_DENIED, '%s has no more room in the crafting inventory.\\n' % char.name)
                    return
                focusNameStripped = focusName.split(' ', 1)[-1]
                focusShort = focusNameStripped.split(' of ', 1)[0]
                newFocusKind = ItemProto.byName(focusShort)
                newFocus = newFocusKind.createInstance()
                newFocus.name = '%s %s' % (ENCHANT_QualityPrefix[qualityIndex], focusNameStripped)
                newFocus.descOverride = 'This %s gleams with a magical hue. It may be used to enchant items.' % focusShort
                newFocus.spellEnhanceLevel = qualityIndex + 10
                newFocus.slot = emptySlots.pop()
                newFocus.setCharacter(char)
                remainingKills = ENCHANT_MergeCount
                for eraseFoc in partialFociList:
                    eraseCount = eraseFoc.stackCount
                    if not eraseCount:
                        eraseCount = 1
                    if eraseCount <= remainingKills:
                        player.takeItem(eraseFoc)
                        remainingKills -= eraseCount
                    else:
                        eraseFoc.stackCount -= remainingKills
                        eraseFoc.itemInfo.refreshDict({'STACKCOUNT': eraseFoc.stackCount})
                        break
                    if not remainingKills:
                        break

                enchanted = True
                player.sendGameText(RPG_MSG_GAME_GAINED, '%s successfully merged %i foci.\\n' % (char.name, ENCHANT_MergeCount))
                break

        if not enchanted:
            player.sendGameText(RPG_MSG_GAME_DENIED, "%s wasn't able to do anything with these items.\\n" % char.name)
            return
        mob.processesPending.add(Spell(mob, mob, SpellProto.byName('Dis - Enchanting')))
        mob.health -= healthCost
        mob.mana -= manaCost
        mob.stamina -= staminaCost
        if len(statCost):
            setattr(char, statCost[2], int(statCost[4] - statCost[3]))
            setattr(mob.spawn, statCost[1], int(getattr(mob.spawn, statCost[1]) + statCost[3]))
            setattr(mob, statCost[0], int(getattr(mob, statCost[0]) + statCost[3]))
            player.cinfoDirty = True
        mlevel = mskill.maxValue
        cap = mskill.absoluteMax
        if not cap or slevel < cap:
            if slevel >= mlevel:
                player.sendGameText(RPG_MSG_GAME_YELLOW, '%s currently cannot gain any more skill in %s.\\n' % (char.name, ENCHANT_skillname))
            elif slevel - skillReq < 10:
                char.checkSkillRaise(ENCHANT_skillname, 1, 1)
            else:
                player.sendGameText(RPG_MSG_GAME_YELLOW, "%s can't learn anything new from this enchantment.\\n" % char.name)
        player.sendGameText(RPG_MSG_GAME_YELLOW, '%s feels drained.\\n' % char.name)
        return


def DisenchantCmd(mob, attribs):
    player = mob.player
    char = mob.character
    slevel = mob.skillLevels.get('Disenchanting', 0)
    if not slevel:
        player.sendGameText(RPG_MSG_GAME_DENIED, "%s doesn't know how to disenchant anything.\\n" % char.name)
        return
    if 'Disenchanting' in mob.skillReuse:
        player.sendGameText(RPG_MSG_GAME_DENIED, '$src is still recovering from a previous disenchant,\\n$srche can disenchant again in about %i seconds.\\n' % mob.skillReuse['Disenchanting'], mob)
        return
    mskill = mob.mobSkillProfiles['Disenchanting']
    mob.skillReuse['Disenchanting'] = mskill.reuseTime
    disenchanted = False
    skillReq = 0
    diffMod = 1000
    manaCost = 0
    if mob.attacking or mob.charmEffect or mob.isFeared or mob.sleep > 0 or mob.stun > 0 or mob.casting:
        player.sendGameText(RPG_MSG_GAME_DENIED, "$src\\'s disenchanting failed, $srche is in no condition to disenchant anything!\\n", mob)
        return
    mob.cancelInvisibility()
    mob.cancelFlying()
    mob.cancelStatProcess('feignDeath', '$tgt is obviously not dead!\\n')
    mob.cancelStatProcess('sneak', '$tgt is no longer sneaking!\\n')
    disenchTarget = [ item for item in char.items if RPG_SLOT_CRAFTING_END > item.slot >= RPG_SLOT_CRAFTING_BEGIN ]
    if not len(disenchTarget) == 1:
        player.sendGameText(RPG_MSG_GAME_DENIED, 'You need to put one single item or stack into the crafting window.\\n')
        return
    disenchTarget = disenchTarget[0]
    if disenchTarget.skill == ENCHANT_skillname:
        spellEnhanceLevel = disenchTarget.spellEnhanceLevel
        if not spellEnhanceLevel:
            player.sendGameText(RPG_MSG_GAME_DENIED, "A raw focus can't be disenchanted.\\n")
            return
        spellEnhanceLevel -= 10
        diffMod = ENCHANT_QualitySkillReq[spellEnhanceLevel] - slevel + spellEnhanceLevel * 10
        if diffMod <= 0:
            diffMod = 1
        manaCost = int(float(diffMod) / 37.0 * 450.0) + 500
        if mob.mana < manaCost:
            player.sendGameText(RPG_MSG_GAME_DENIED, "%s doesn't have enough mana to disenchant this item.\\n" % char.name)
            return
        if diffMod >= 10 and randint(0, int(diffMod / 10.0)):
            mob.processesPending.add(Spell(mob, mob, SpellProto.byName('Enchanting failure')))
            player.sendGameText(RPG_MSG_GAME_LOST, "Whoops! Disenchanting this focus didn't go as intended.\\n")
            player.takeItem(disenchTarget)
            mob.mana -= manaCost * 2
            if mob.mana < 0:
                mob.mana = 0
            return
        proto = ItemProto.byName(disenchTarget.itemProto.name.split(' of ')[0])
        newFocus = proto.createInstance()
        newFocus.slot = disenchTarget.slot
        newFocus.setCharacter(char)
        disenchTarget.destroySelf()
        mob.processesPending.add(Spell(mob, mob, SpellProto.byName('Dis - Enchanting')))
        player.sendGameText(RPG_MSG_GAME_GAINED, '%s successfully disenchanted the focus.\\n' % char.name)
        mob.mana -= manaCost
        mlevel = mskill.maxValue
        cap = mskill.absoluteMax
        if not cap or slevel < cap:
            if slevel >= mlevel:
                player.sendGameText(RPG_MSG_GAME_YELLOW, '%s currently cannot gain any more skill in Disenchanting.\\n' % char.name)
            elif slevel - skillReq < 10:
                char.checkSkillRaise('Disenchanting', 1, 1)
            else:
                player.sendGameText(RPG_MSG_GAME_YELLOW, "%s can't learn anything new from this disenchantment.\\n" % char.name)
        return
    disenchTargetStats = []
    if not disenchTarget.spellEnhanceLevel == 9999:
        disenchTargetStats = [ (st.statname, st.value) for st in disenchTarget.itemProto.stats ]
    try:
        disenchTargetStats.extend(disenchTarget.variants[V_STAT])
    except KeyError:
        pass

    try:
        baneRace, baneMod = disenchTarget.variants[V_BANEWEAPON]
        disenchTargetStats.append((baneRace + ' Bane', baneMod))
    except KeyError:
        pass

    try:
        dmg, rate, resist, debuff = item.variants[V_WEAPON]
        if dmg != -1:
            disenchTargetStats.append(('Damage Mod', dmg))
        if rate != -1:
            disenchTargetStats.append(('Weapon Speed', rate))
        if debuff != -1:
            disenchTargetStats.append(('Debuff', (resist, debuff)))
    except KeyError:
        pass

    numEnchantments = len(disenchTargetStats)
    if not numEnchantments:
        player.sendGameText(RPG_MSG_GAME_DENIED, "This item doesn't bear any enchantments and therefore can't be disenchanted.\\n")
        return
    disenchItemLevel = disenchTarget.level
    classes = list(disenchTarget.itemProto.classes)
    if len(classes):
        for cl in classes:
            if cl.level > disenchItemLevel:
                disenchItemLevel = cl.level

    freeslots = range(RPG_SLOT_CRAFTING_BEGIN, RPG_SLOT_CRAFTING_END)
    freeslots.remove(disenchTarget.slot)
    if disenchTarget.flags & RPG_ITEM_ENCHANTED and disenchTarget.crafted:
        skillReq = disenchItemLevel * 10
        diffMod = skillReq - slevel
        if diffMod < -500:
            diffMod = -500
        iScale = float(disenchItemLevel) * 0.15 + 1.0
        sScale = (1000.0 - float(slevel)) / 333.0 + 1.0
        isScale = iScale * sScale
        manaCost = int(round(isScale * isScale * iScale * numEnchantments))
        numEnchantments = 1
        if mob.mana < manaCost:
            player.sendGameText(RPG_MSG_GAME_DENIED, "%s doesn't have enough mana to disenchant this item.\\n" % char.name)
            return
        if diffMod > 0 and randint(0, int(diffMod / 10.0)):
            mob.processesPending.add(Spell(mob, mob, SpellProto.byName('Enchanting failure')))
            player.sendGameText(RPG_MSG_GAME_LOST, '%s drained too much energy, accidentally destroying the %s.\\n' % (char.name, disenchTarget.name))
            player.takeItem(disenchTarget)
            mob.mana -= manaCost
            return
        disenchTypeNames = [ dts[0].upper() for dts in disenchTargetStats ]
        disenchIndex = 0
        if len(attribs):
            try:
                if attribs == 'HEALTH':
                    attribs = 'maxHealth'
                elif attribs == 'MANA':
                    attribs = 'maxMana'
                elif attribs == 'STAMINA':
                    attribs = 'maxStamina'
                elif attribs == 'MELEE HASTE':
                    attribs = 'haste'
                elif attribs == 'CASTING HASTE':
                    attribs = 'castHaste'
                elif attribs == 'REGENERATION':
                    attribs = 'regenHealth'
                elif attribs == 'REVITALIZATION':
                    attribs = 'regenStamina'
                elif attribs == 'MANA REGEN':
                    attribs = 'regenMana'
                disenchIndex = disenchTypeNames.index(attribs)
            except:
                player.sendGameText(RPG_MSG_GAME_DENIED, "Couldn't find %s in %s's stats. Possible stats are: %s\\n" % (attribs, disenchTarget.name, ', '.join(disenchTypeNames)))
                return

        disenchTargetStats.pop(disenchIndex)
        disenchTarget.clearVariants()
        disenchTarget.name = disenchTarget.itemProto.name
        if len(disenchTargetStats):
            disenchTarget.name = 'Enchanted ' + disenchTarget.name
            for oldStat in disenchTargetStats:
                AddStatVariant(disenchTarget, oldStat[0], oldStat[1])

            disenchTarget.levelOverride = disenchTarget.itemProto.level + 2 * len(disenchTargetStats)
            if disenchTarget.levelOverride > 100:
                disenchTarget.levelOverride = 100
            disenchTarget.hasVariants = True
            disenchTarget.spellEnhanceLevel = 9999
        else:
            disenchTarget.descOverride = disenchTarget.descOverride.split('\\nEnchanted by')[0]
            disenchTarget.levelOverride = disenchTarget.itemProto.level
            disenchTarget.hasVariants = False
            disenchTarget.spellEnhanceLevel = 0
            disenchTarget.flags = disenchTarget.flags & ~RPG_ITEM_ENCHANTED
            disenchTarget.quality = RPG_QUALITY_NORMAL
            disenchTarget.worthIncreaseTin = 0
        disenchTarget.crafted = True
        disenchTarget.refreshFromProto()
        disenchanted = True
    elif disenchTarget.flags & RPG_ITEM_ARTIFACT and not disenchTarget.flags & RPG_ITEM_SOULBOUND:
        disenchProto = disenchTarget.itemProto
        if disenchProto.stackDefault > 1:
            if disenchTarget.stackCount < disenchProto.stackDefault:
                player.sendGameText(RPG_MSG_GAME_DENIED, 'At least %i %s are required to attempt disenchanting.\\n' % (disenchProto.stackDefault, disenchTarget.name))
                return
        skillReq = int(disenchItemLevel * 7.4)
        diffMod = skillReq - slevel
        if diffMod < -500:
            diffMod = -500
        iScale = float(disenchItemLevel) * 0.15 + 1.0
        sScale = (1000.0 - float(slevel)) / 333.0 + 1.0
        isScale = iScale * sScale
        manaCost = int(round(0.5 * isScale * isScale * iScale * numEnchantments))
        if mob.mana < manaCost:
            player.sendGameText(RPG_MSG_GAME_DENIED, "%s doesn't have enough mana to disenchant this item.\\n" % char.name)
            return
        if diffMod > 0 and randint(0, int(diffMod / 5.0)):
            mob.processesPending.add(Spell(mob, mob, SpellProto.byName('Enchanting failure')))
            player.sendGameText(RPG_MSG_GAME_LOST, '%s drained too much energy, accidentally turning the %s to dust.\\n' % (char.name, disenchTarget.name))
            player.takeItem(disenchTarget)
            mob.mana -= manaCost
            return
        disenchTarget.name = 'Powerless ' + disenchTarget.name
        disenchTarget.clearVariants()
        if disenchTarget.itemProto.desc:
            disenchTarget.descOverride = '%s\\n\\nStripped from its power by %s' % (disenchTarget.itemProto.desc, char.name)
        else:
            disenchTarget.descOverride = 'Stripped from its power by %s' % char.name
        disenchTarget.levelOverride = disenchTarget.itemProto.level - 10
        if disenchTarget.levelOverride < 1:
            disenchTarget.levelOverride = 1
        disenchTarget.hasVariants = True
        disenchTarget.spellEnhanceLevel = 9999
        disenchTarget.refreshFromProto()
        disenchanted = True
    else:
        player.sendGameText(RPG_MSG_GAME_DENIED, "%s can't disenchant this kind of item.\\n" % char.name)
        return
    if disenchanted:
        mob.processesPending.add(Spell(mob, mob, SpellProto.byName('Dis - Enchanting')))
        player.sendGameText(RPG_MSG_GAME_GAINED, '%s successfully disenchanted the artifact.\\n' % char.name)
        mob.mana -= manaCost
        if not randint(0, int(ceil((diffMod + 500) / 75.0))):
            numEnchItems = randint(1, int(slevel / 225) + 1)
            if numEnchItems > numEnchantments:
                numEnchItems = numEnchantments
            for i in xrange(numEnchItems):
                enchItem = ItemProto.byName(ENCHANT_RawItems[randint(0, len(ENCHANT_RawItems) - 1)])
                item = enchItem.createInstance()
                if len(freeslots):
                    item.slot = freeslots.pop()
                    item.setCharacter(char)
                else:
                    break

            player.sendGameText(RPG_MSG_GAME_GAINED, 'Some of the mystic energy drained from the item forms into solid matter.\\n')
        if not randint(0, int(100 - slevel * 0.09)):
            buffMod = slevel / 100.0 + 1.0
            mob.processesPending.add(Spell(mob, mob, SpellProto.byName('Disenchanting Focus'), buffMod))
            player.sendGameText(RPG_MSG_GAME_GAINED, '%s managed to harness some mystic energy drained from the item.\\n' % char.name)
        mlevel = mskill.maxValue
        cap = mskill.absoluteMax
        if not cap or slevel < cap:
            if slevel >= mlevel:
                player.sendGameText(RPG_MSG_GAME_YELLOW, '%s currently cannot gain any more skill in Disenchanting.\\n' % char.name)
            elif slevel - skillReq < 10:
                char.checkSkillRaise('Disenchanting', 1, 1)
            else:
                player.sendGameText(RPG_MSG_GAME_YELLOW, "%s can't learn anything new from this disenchantment.\\n" % char.name)


def Craft(mob, recipeID, useCraftWindow):
    player = mob.player
    char = mob.character
    if useCraftWindow:
        useItems = [ item for item in char.items if RPG_SLOT_CRAFTING_END > item.slot >= RPG_SLOT_CRAFTING_BEGIN ]
        if not len(useItems):
            return
    else:
        useItems = char.items
    if recipeID == -1:
        if mob.skillLevels.get('Scribing', 0):
            if 'Scribing' in mob.skillReuse:
                player.sendGameText(RPG_MSG_GAME_DENIED, '$src is still cleaning $srchis tools,\\n$srche can use the <a:SkillScribing>Scribing</a> skill again in about %i seconds.\\n' % mob.skillReuse['Scribing'], mob)
                return
            spellEnhanceLevel = useItems[0].spellEnhanceLevel
            name = useItems[0].name
            passed = True
            if spellEnhanceLevel > 0 and spellEnhanceLevel < 10:
                count = 0
                for item in useItems:
                    if spellEnhanceLevel != item.spellEnhanceLevel or name != item.name:
                        passed = False
                        break
                    count += item.stackCount

                if count == 2 and passed:
                    mobSkill = mob.mobSkillProfiles['Scribing']
                    mob.skillReuse['Scribing'] = mobSkill.reuseTime
                    char.checkSkillRaise('Scribing', 1, 2)
                    player.mind.callRemote('playSound', 'sfx/Pencil_WriteOnPaper2.ogg')
                    player.sendGameText(RPG_MSG_GAME_GOOD, '%s has successfully combined the knowledge of the %s tomes.\\n' % (char.name, name))
                    spellname = useItems[0].itemProto.spellProto.name
                    scroll = ItemProto.byName('Scroll of %s' % spellname)
                    nitem = getTomeAtLevelForScroll(scroll, spellEnhanceLevel + 1)
                    nitem.slot = RPG_SLOT_CRAFTING0
                    nitem.setCharacter(char)
                    for item in useItems:
                        player.takeItem(item)

                    return
        player.sendGameText(RPG_MSG_GAME_DENIED, '%s is unable to craft anything with these items.\\n' % char.name)
        return
    try:
        recipe = Recipe.get(recipeID)
    except:
        player.sendGameText(RPG_MSG_GAME_DENIED, 'Server received invalid recipe id. Crafting had to be aborted.\\n')
        print 'WARNING: %s used invalid recipe id %i.' % (mob.name, recipeID)
        return

    skillname = recipe.skillname
    charSkillLevel = mob.skillLevels.get(skillname, 0)
    if charSkillLevel < recipe.skillLevel:
        player.sendGameText(RPG_MSG_GAME_DENIED, '%s requires a %i skill in <a:Skill%s>%s</a>.\\n' % (char.name,
         recipe.skillLevel,
         GetTWikiName(skillname),
         skillname))
        return
    craftProto = recipe.craftedItemProto
    craftStackMax = craftProto.stackMax
    craftStackDefault = craftProto.stackDefault
    craftUseMax = craftProto.useMax
    if skillname == 'Blacksmithing':
        moneyMod, craftStackCount, craftCharges = getBlacksmithingMods(mob, craftProto, charSkillLevel)
    else:
        moneyMod, craftStackCount, craftCharges = 1.0, craftStackDefault, craftUseMax
    cost = long(moneyMod * recipe.costTP)
    if not player.checkMoney(cost):
        player.sendGameText(RPG_MSG_GAME_DENIED, 'This <a:Skill%s>%s</a> requires %s.\\n' % (GetTWikiName(skillname), skillname, GenMoneyText(cost)))
        return
    if skillname in mob.skillReuse:
        player.sendGameText(RPG_MSG_GAME_DENIED, '$src is still cleaning $srchis tools,\\n$srche can use the <a:Skill%s>%s</a> skill again in about %i seconds.\\n' % (GetTWikiName(skillname), skillname, mob.skillReuse[skillname]), mob)
        return
    mobSkill = mob.mobSkillProfiles[skillname]
    if skillname == 'Archery':
        mob.skillReuse[skillname] = 12
    else:
        mob.skillReuse[skillname] = mobSkill.reuseTime
    ingredients = defaultdict(int)
    for i in list(recipe.ingredients):
        ingredients[i.itemProto] += i.count

    emptySlots = range(RPG_SLOT_CRAFTING_BEGIN, RPG_SLOT_CRAFTING_END)
    consumed = {}
    stackItems = []
    if not useCraftWindow and craftStackMax > 1:
        if craftUseMax > 1:
            neededSpace = craftStackCount * craftCharges
        else:
            neededSpace = craftStackCount
        for item in useItems:
            proto = item.itemProto
            if proto in ingredients:
                if proto.useMax > 1:
                    ingredients[proto] -= 1
                    if proto.craftConsumed:
                        consumed[item] = 1
                else:
                    ingredients[proto] -= item.stackCount
                    if proto.craftConsumed:
                        if ingredients[proto] < 0:
                            consumed[item] = item.stackCount + ingredients[proto]
                        else:
                            consumed[item] = item.stackCount
                if ingredients[proto] <= 0:
                    del ingredients[proto]
            if RPG_SLOT_CRAFTING_END > item.slot >= RPG_SLOT_CRAFTING_BEGIN:
                emptySlots.remove(item.slot)
                if craftProto.name == item.name:
                    if craftUseMax > 1:
                        diff = (craftStackMax - item.stackCount + 1) * craftUseMax - item.useCharges
                    else:
                        diff = craftStackMax - item.stackCount
                    if diff > 0:
                        stackItems.append((item, diff))
                        neededSpace -= diff

        if neededSpace > 0 and not len(emptySlots):
            player.sendGameText(RPG_MSG_GAME_DENIED, '%s has no more room in the crafting inventory.\\n' % char.name)
            return
    else:
        for item in useItems:
            proto = item.itemProto
            if proto in ingredients:
                if proto.useMax > 1:
                    ingredients[proto] -= 1
                    if proto.craftConsumed:
                        consumed[item] = 1
                else:
                    ingredients[proto] -= item.stackCount
                    if proto.craftConsumed:
                        if ingredients[proto] < 0:
                            consumed[item] = item.stackCount + ingredients[proto]
                        else:
                            consumed[item] = item.stackCount
                if ingredients[proto] <= 0:
                    del ingredients[proto]
            if useCraftWindow:
                if not proto.craftConsumed:
                    emptySlots.remove(item.slot)
            elif RPG_SLOT_CRAFTING_END > item.slot >= RPG_SLOT_CRAFTING_BEGIN:
                emptySlots.remove(item.slot)

        if not len(emptySlots):
            player.sendGameText(RPG_MSG_GAME_DENIED, '%s has no more room in the crafting inventory.\\n' % char.name)
            return
    if len(ingredients):
        player.sendGameText(RPG_MSG_GAME_DENIED, '%s lacks %s for this craft.\\n' % (char.name, ', '.join(('%i <a:Item%s>%s</a>' % (count, GetTWikiName(item.name), item.name) for item, count in ingredients.iteritems()))))
        return
    for item, count in consumed.items():
        proto = item.itemProto
        if proto.useMax > 1:
            item.useCharges -= 1
            if item.useCharges <= 0:
                item.stackCount -= 1
                if item.stackCount <= 0:
                    player.takeItem(item)
                else:
                    item.useCharges = proto.useMax
                    item.itemInfo.refreshDict({'STACKCOUNT': item.stackCount,
                     'USECHARGES': item.useCharges})
            else:
                item.itemInfo.refreshDict({'USECHARGES': item.useCharges})
        else:
            item.stackCount -= count
            if item.stackCount <= 0:
                player.takeItem(item)
            else:
                item.itemInfo.refreshDict({'STACKCOUNT': item.stackCount})

    player.takeMoney(cost)
    if craftStackMax > 1 and craftUseMax > 1:
        totalCharges = craftCharges * craftStackCount
        for item, diff in stackItems:
            if diff > totalCharges:
                diff = totalCharges
            item.stackCount += diff / craftUseMax
            item.useCharges += diff % craftUseMax
            if item.useCharges > craftUseMax:
                item.useCharges -= craftUseMax
                item.stackCount += 1
            totalCharges -= diff
            item.itemInfo.refreshDict({'STACKCOUNT': item.stackCount,
             'USECHARGES': item.useCharges})
            if totalCharges <= 0:
                craftCharges = 0
                craftStackCount = 0
                break
        else:
            craftStackCount = totalCharges / craftUseMax
            craftCharges = totalCharges % craftUseMax
            if not craftCharges:
                craftCharges = craftUseMax
            else:
                craftStackCount += 1
    elif craftStackMax > 1:
        for item, diff in stackItems:
            if diff > craftStackCount:
                diff = craftStackCount
            item.stackCount += diff
            craftStackCount -= diff
            item.itemInfo.refreshDict({'STACKCOUNT': item.stackCount})
            if craftStackCount <= 0:
                break

    if craftStackCount:
        item = craftProto.createInstance()
        item.slot = emptySlots.pop()
        item.stackCount = craftStackCount
        item.useCharges = craftCharges
        item.setCharacter(char)
        if craftProto.desc:
            item.descOverride = '%s\\n\\nCrafted by %s' % (craftProto.desc, char.name)
        else:
            item.descOverride = 'Crafted by %s' % char.name
        item.crafted = True
    player.sendGameText(RPG_MSG_GAME_GAINED, '%s has crafted a <a:Item%s>%s</a>!\\n' % (char.name, GetTWikiName(craftProto.name), craftProto.name))
    costTotalText = GenMoneyText(cost)
    if costTotalText:
        player.sendGameText(RPG_MSG_GAME_YELLOW, 'This <a:Skill%s>%s</a> consumes %s.\\n' % (GetTWikiName(skillname), skillname, costTotalText))
    maxLevel = mobSkill.maxValue
    cap = mobSkill.absoluteMax
    if not cap or charSkillLevel < cap:
        if charSkillLevel >= maxLevel:
            player.sendGameText(RPG_MSG_GAME_YELLOW, '%s currently cannot gain any more skill in <a:Skill%s>%s</a>.\\n' % (char.name, GetTWikiName(skillname), skillname))
        elif skillname == 'Blacksmithing':
            char.checkSkillRaise('Blacksmithing', 3, 4)
        elif charSkillLevel - recipe.skillLevel < 15:
            char.checkSkillRaise(skillname, 1, 2)
    if recipe.craftSound:
        player.mind.callRemote('playSound', recipe.craftSound)