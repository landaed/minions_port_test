# Embedded file name: mud\world\skill.pyo
from core import *
from random import randint
from math import floor, ceil, sqrt
from damage import Damage
from defines import *
import traceback
from mud.worlddocs.utils import GetTWikiName
from mud.common.persistent import Persistent
from sqlobject import *

class ClassSkillQuestRequirement(Persistent):
    classSkill = ForeignKey('ClassSkill')
    choiceIdentifier = StringCol()
    levelBarrier = IntCol()


class ClassSkillRaceRequirement(Persistent):
    classSkill = ForeignKey('ClassSkill')
    race = StringCol()


class ClassSkill(Persistent):
    skillname = StringCol(default='')
    levelGained = IntCol(default=0)
    levelCapped = IntCol(default=0)
    minReuseTime = IntCol(default=0)
    maxReuseTime = IntCol(default=0)
    maxValue = IntCol(default=0)
    trained = BoolCol(default=False)
    spellProto = ForeignKey('SpellProto', default=None)
    classProtos = RelatedJoin('ClassProto')
    raceRequirementsInternal = MultipleJoin('ClassSkillRaceRequirement')
    questRequirementsInternal = MultipleJoin('ClassSkillQuestRequirement')

    def _init(self, *args, **kw):
        Persistent._init(self, *args, **kw)
        self.raceRequirements = []
        for r in list(self.raceRequirementsInternal):
            self.raceRequirements.append(r.race)

        self.questRequirements = []
        for qreq in list(self.questRequirementsInternal):
            self.questRequirements.append((qreq.choiceIdentifier, qreq.levelBarrier))

    def getMaxValueForLevel(self, level):
        if level < self.levelGained:
            return 0
        if not self.maxValue:
            return 0
        if not self.levelGained:
            return 0
        if level >= self.levelCapped:
            return self.maxValue
        if self.levelGained == self.levelCapped:
            return self.maxValue
        step = floor(self.maxValue / (self.levelCapped - self.levelGained))
        value = floor((level - self.levelGained) * step + step)
        if value > self.maxValue:
            value = self.maxValue
        return int(value)

    def getReuseTimeForLevel(self, level):
        if not self.maxReuseTime or not self.minReuseTime:
            return 0
        if not self.maxValue:
            return 0
        if level < self.levelGained:
            return 0
        if level > self.levelCapped:
            level = self.levelCapped
        if self.levelGained == self.levelCapped:
            return self.minReuseTime
        spread = float(self.maxReuseTime) - float(self.minReuseTime)
        gap = float(self.levelCapped) - float(self.levelGained)
        if not gap:
            return self.maxReuseTime
        phase = float(level - self.levelGained) / gap
        spread *= phase
        t = floor(self.maxReuseTime - spread)
        if t < self.minReuseTime:
            t = self.minReuseTime
        return int(t)


def DoAssess(mob):
    if not mob.player:
        print 'WARNING: Non-player mob attempting to assess.'
        return (False, False)
    else:
        player = mob.player
        tgt = mob.target
        if not tgt or tgt == mob:
            player.sendGameText(RPG_MSG_GAME_DENIED, "$src's <a:SkillAssess>assess</a> failed, no target.\\n", mob)
            return (False, False)
        if GetRangeMin(mob, tgt) > 5.0:
            player.sendGameText(RPG_MSG_GAME_DENIED, "$src's <a:SkillAssess>assess</a> failed, out of range.\\n", mob)
            return (False, False)
        if player.looting:
            player.looting.looter = None
            player.looting = None
        alevel = mob.skillLevels.get('Assess', 0)
        assessDict = {}
        if tgt.player:
            if tgt.stun > 0:
                assessDict = dict(((x, item.itemInfo) for x, item in enumerate(tgt.worn.itervalues())))
            else:
                x = 0
                for item in tgt.worn.itervalues():
                    if item.slot in (RPG_SLOT_LEAR,
                     RPG_SLOT_REAR,
                     RPG_SLOT_NECK,
                     RPG_SLOT_LFINGER,
                     RPG_SLOT_RFINGER):
                        if item.level <= alevel:
                            assessDict[x] = item.itemInfo
                            x += 1
                    elif item.slot in (RPG_SLOT_WAIST,
                     RPG_SLOT_LWRIST,
                     RPG_SLOT_RWRIST,
                     RPG_SLOT_LIGHT):
                        if item.level <= alevel * 2:
                            assessDict[x] = item.itemInfo
                            x += 1
                    else:
                        assessDict[x] = item.itemInfo
                        x += 1

        else:
            loot = tgt.loot
            if loot and loot.generateCorpseLoot():
                if tgt.stun > 0 or alevel == 250:
                    assessDict = dict(((x, item.itemInfo) for x, item in enumerate(loot.items)))
                else:
                    x = 0
                    for item in loot.items:
                        try:
                            if loot.lootProto.itemDetails[item.itemProto.name] & RPG_LOOT_PICKPOCKET:
                                assessDict[x] = item.itemInfo
                                x += 1
                                continue
                        except:
                            pass

                        if item.flags & RPG_ITEM_QUEST:
                            assessDict[x] = item.itemInfo
                            x += 1
                            continue
                        if item.slot != -1:
                            if item.slot in (RPG_SLOT_LEAR,
                             RPG_SLOT_REAR,
                             RPG_SLOT_NECK,
                             RPG_SLOT_LFINGER,
                             RPG_SLOT_RFINGER):
                                if item.level <= alevel:
                                    assessDict[x] = item.itemInfo
                                    x += 1
                            elif item.slot in (RPG_SLOT_WAIST,
                             RPG_SLOT_LWRIST,
                             RPG_SLOT_RWRIST,
                             RPG_SLOT_LIGHT):
                                if item.level <= alevel * 2:
                                    assessDict[x] = item.itemInfo
                                    x += 1
                            else:
                                assessDict[x] = item.itemInfo
                                x += 1
                            continue
                        if item.level == 1 and len(item.itemProto.slots) == 0:
                            if tgt.level * 2.5 <= alevel:
                                assessDict[x] = item.itemInfo
                                x += 1
                            continue
                        if item.level * 2 <= alevel:
                            assessDict[x] = item.itemInfo
                            x += 1

        if not len(assessDict):
            player.sendGameText(RPG_MSG_GAME_DENIED, "$tgt doesn't seem to have anything of particular worth.\\n", mob)
            return (False, True)
        player.mind.callRemote('setLoot', assessDict, 'assess')
        mob.character.checkSkillRaise('Assess')
        player.sendGameText(RPG_MSG_GAME_GAINED, "$src tries to assess $tgt's possessions.\\n", mob)
        return (True, True)


def DoDisarm(mob):
    if not mob.player:
        print 'WARNING: Non-player mob attempting to disarm.'
        return (False, False)
    else:
        tgt = mob.target
        player = mob.player
        if not tgt:
            player.sendGameText(RPG_MSG_GAME_DENIED, "$src's <a:SkillDisarm>disarm</a> failed, no target.\\n", mob)
            return (False, False)
        if tgt.player or tgt.master and tgt.master.player:
            player.sendGameText(RPG_MSG_GAME_DENIED, "$src's <a:SkillDisarm>disarm</a> failed, can't disarm other players.\\n", mob)
            return (False, False)
        weapon = tgt.worn.get(RPG_SLOT_SECONDARY)
        if not weapon:
            weapon = tgt.worn.get(RPG_SLOT_PRIMARY)
        if not weapon:
            player.sendGameText(RPG_MSG_GAME_DENIED, "$src's <a:SkillDisarm>disarm</a> failed, $tgt carries no weapon.\\n", mob)
            return (False, False)
        if GetRangeMin(mob, tgt) > 2.0:
            player.sendGameText(RPG_MSG_GAME_DENIED, "$src's <a:SkillDisarm>disarm</a> failed, $tgt is out of range.\\n", mob)
            return (False, False)
        pplevel = mob.plevel
        spread = pplevel - mob.target.plevel
        failed = False
        if spread < -5:
            failed = True
        else:
            chance = 6 + spread
            r = randint(0, chance)
            if not r:
                failed = True
        if not tgt.aggro.get(mob, 0):
            tgt.addAggro(mob, 10)
        if failed:
            player.sendGameText(RPG_MSG_GAME_DENIED, '$src has failed to <a:SkillDisarm>disarm</a> $tgt!\\n', mob)
            return (False, True)
        tgt.unequipItem(weapon.slot)
        weapon.slot = -1
        tgt.mobInfo.refresh()
        stolen = False
        if not weapon.flags & RPG_ITEM_SOULBOUND and not weapon.flags & RPG_ITEM_UNIQUE:
            pplevel = mob.skillLevels.get('Pick Pocket', 0) / 10
            mod = mob.target.difficultyMod
            if pplevel:
                difficulty = int(round(5.0 * (mod * mod * float(mob.target.plevel)) / float(pplevel)))
                if not randint(0, difficulty):
                    if player.giveItemInstance(weapon):
                        player.sendGameText(RPG_MSG_GAME_GAINED, "%s successfully yanks away $tgt's <a:Item%s>%s</a>!\\n" % (weapon.character.name, GetTWikiName(weapon.itemProto.name), weapon.name), mob)
                        loot = tgt.loot
                        loot.items.remove(weapon)
                        if not len(loot.items):
                            tgt.loot = None
                        stolen = True
        if not stolen:
            player.sendGameText(RPG_MSG_GAME_GAINED, "$src has <a:SkillDisarm>disarmed</a> $tgt's <a:Item%s>%s</a>.\\n" % (GetTWikiName(weapon.itemProto.name), weapon.name), mob)
        mob.character.checkSkillRaise('Disarm')
        player.mind.callRemote('playSound', 'sfx/Hit_HugeMetalPlatformDrop.ogg')
        return (True, True)


def DoPickPocket(mob):
    if not mob.player:
        print 'WARNING: Non-player mob attempting to pick pocket'
        return (False, False)
    else:
        tgt = mob.target
        if not tgt or tgt == mob:
            mob.player.sendGameText(RPG_MSG_GAME_DENIED, "$src's <a:SkillPickPocket>pick pocket</a> failed, no target.\\n", mob)
            return (False, False)
        if tgt.player or tgt.master and tgt.master.player:
            mob.player.sendGameText(RPG_MSG_GAME_DENIED, "$src's <a:SkillPickPocket>pick pocket</a> failed, can't pick pocket other players.\\n", mob)
            return (False, False)
        tgtDisabled = tgt.sleep > 0 or tgt.stun > 0
        if tgt.target:
            if tgt.target.player != mob.player:
                mob.player.sendGameText(RPG_MSG_GAME_DENIED, "<a:SkillPickPocket>Pick pocket</a> failed, can't pick pocket targets in combat with other players.\\n", mob)
                return (False, False)
            if tgt.target == mob and not tgtDisabled:
                mob.player.sendGameText(RPG_MSG_GAME_DENIED, '<a:SkillPickPocket>Pick pocket</a> failed, $tgt has a keen eye on $src.\\n', mob)
                return (False, False)
        if mob.attacking:
            mob.player.sendGameText(RPG_MSG_GAME_DENIED, '$src is too occupied with combat to <a:SkillPickPocket>pick pocket</a>.\\n', mob)
            return (False, False)
        if GetRangeMin(mob, tgt) > 2.0:
            mob.player.sendGameText(RPG_MSG_GAME_DENIED, "$src's <a:SkillPickPocket>pick pocket</a> failed, out of range.\\n", mob)
            return (False, False)
        loot = tgt.loot
        nothing = True
        if loot and loot.generateCorpseLoot():
            nothing = False
        if nothing:
            mob.player.sendGameText(RPG_MSG_GAME_DENIED, '<a:SkillPickPocket>Pick pocket</a> failed, $tgt has nothing to steal.\\n', mob)
            return (False, True)
        pickPocketNormal = []
        pickPocketSpecial = []
        for item in loot.items:
            if loot.lootProto.itemDetails.has_key(item.itemProto.name):
                if loot.lootProto.itemDetails[item.itemProto.name] & RPG_LOOT_PICKPOCKET:
                    pickPocketSpecial.append(item)
                elif not item.flags & RPG_ITEM_SOULBOUND and item.slot != -1:
                    if item.slot in (RPG_SLOT_SHOULDERS, RPG_SLOT_HANDS, RPG_SLOT_FEET) and not tgtDisabled:
                        continue
                    elif item.slot in (RPG_SLOT_CHEST, RPG_SLOT_ARMS, RPG_SLOT_LEGS) and tgt.stun <= 0:
                        continue
                    pickPocketNormal.append(item)
                continue
            pickPocketNormal.append(item)

        if not loot.tin and not len(pickPocketNormal) and not len(pickPocketSpecial):
            mob.player.sendGameText(RPG_MSG_GAME_DENIED, '<a:SkillPickPocket>Pick pocket</a> failed, $tgt has nothing to steal.\\n', mob)
            return (False, True)
        pplevel = mob.skillLevels.get('Pick Pocket', 0)
        succ = 500.0
        if not tgtDisabled:
            succ *= sqrt(1.0 - loot.pickPocketTimer / 270.0)
        succ *= 2.0 - float(tgt.plevel * 10 - pplevel) / 500.0
        mod = tgt.difficultyMod / 100.0
        if mod > 1.0:
            mod = 1.0
        succ *= sqrt(1.0 - mod)
        if tgtDisabled:
            succ *= 1.5
        succ = int(succ)
        if succ > 975:
            succ = 975
        if succ < 5:
            succ = 5
        loot.pickPocketTimer = 270
        noticed = False
        if randint(1, 1000) > succ:
            mob.player.sendGameText(RPG_MSG_GAME_DENIED, "$tgt has noticed $src's <a:SkillPickPocket>pick pocketing</a>!\\n", mob)
            if tgt.sleep > 0:
                tgt.cancelSleep()
            if not tgt.aggro.get(mob, 0):
                tgt.addAggro(mob, 10)
            if succ >= 600:
                mob.character.checkSkillRaise('Pick Pocket', 4, 4)
            return (False, True)
        if tgt.sleep > 0 and randint(0, 1500) > succ:
            tgt.cancelSleep()
            if not tgt.aggro.get(mob, 0):
                tgt.addAggro(mob, 10)
            noticed = True
        if succ <= 750:
            mob.character.checkSkillRaise('Pick Pocket', 2, 2)
        if len(pickPocketSpecial):
            x = len(pickPocketSpecial) - 1
            if x >= 1:
                x = randint(0, x)
            item = pickPocketSpecial[x]
            slot = item.slot
            if mob.player.giveItemInstance(item):
                mob.player.sendGameText(RPG_MSG_GAME_GAINED, '%s successfully <a:SkillPickPocket>pick pockets</a> a <a:Item%s>%s</a>!\\n' % (item.character.name, GetTWikiName(item.itemProto.name), item.name))
                loot.items.remove(item)
                if not loot.tin and not len(loot.items):
                    tgt.loot = None
                if slot != -1:
                    tgt.unequipItem(slot)
                    tgt.mobInfo.refresh()
                return (True, True)
        takeItem = False
        if len(pickPocketNormal):
            if loot.tin:
                if randint(0, 2):
                    takeItem = True
            else:
                takeItem = True
        if takeItem:
            x = len(pickPocketNormal) - 1
            if x >= 1:
                x = randint(0, x)
            item = pickPocketNormal[x]
            slot = item.slot
            if slot != -1:
                skip = doNotice = False
                if slot in (RPG_SLOT_HEAD,
                 RPG_SLOT_WAIST,
                 RPG_SLOT_BACK,
                 RPG_SLOT_PRIMARY,
                 RPG_SLOT_SECONDARY,
                 RPG_SLOT_RANGED,
                 RPG_SLOT_AMMO,
                 RPG_SLOT_SHIELD,
                 RPG_SLOT_LIGHT):
                    doNotice = not noticed
                elif slot in (RPG_SLOT_SHOULDERS, RPG_SLOT_HANDS, RPG_SLOT_FEET):
                    doNotice = not noticed
                elif slot in (RPG_SLOT_CHEST, RPG_SLOT_ARMS, RPG_SLOT_LEGS):
                    skip = not randint(0, 3)
                    doNotice = not noticed
                if doNotice:
                    span = pplevel - 10 * tgt.plevel
                    if span < 200:
                        if span < -100:
                            noticed = True
                        else:
                            noticed = randint(1, 100) > (span + 100) / 6
                    else:
                        noticed = randint(0, 1)
                    if noticed:
                        mob.player.sendGameText(RPG_MSG_GAME_DENIED, "$tgt has noticed $src's <a:SkillPickPocket>pick pocketing</a>!\\n", mob)
                        if tgt.sleep > 0:
                            tgt.cancelSleep()
                        tgt.addAggro(mob, 10)
                if skip:
                    mob.player.sendGameText(RPG_MSG_GAME_DENIED, "$src fails to remove the <a:Item%s>%s</a> from its victim. It's not as easy as it looks after all.\\n" % (GetTWikiName(item.itemProto.name), item.name), mob)
                    return (False, True)
            if mob.player.giveItemInstance(item):
                mob.player.sendGameText(RPG_MSG_GAME_GAINED, '%s successfully <a:SkillPickPocket>pick pockets</a> a <a:Item%s>%s</a>!\\n' % (item.character.name, GetTWikiName(item.itemProto.name), item.name))
                loot.items.remove(item)
                if not loot.tin and not len(loot.items):
                    tgt.loot = None
                if slot != -1:
                    tgt.unequipItem(slot)
                    tgt.mobInfo.refresh()
                return (True, True)
        if loot.tin:
            half = loot.tin / 2
            tin = loot.tin - half
            loot.tin = half
            worth = GenMoneyText(tin)
            mob.player.giveMoney(tin)
            mob.player.sendGameText(RPG_MSG_GAME_GAINED, '$src successfully <a:SkillPickPocket>pick pockets</a> %s.\\n' % worth, mob)
            if not loot.tin and not len(loot.items):
                tgt.loot = None
            return (True, True)
        if tgt.sleep > 0:
            tgt.cancelSleep()
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, '$src quickly retracts $srchis hand before $tgt notices $srchim.\\n', mob)
        return (True, True)
        return


def DoBackstab(mob):
    if not mob.player:
        print 'WARNING: Non-player mob attempting to backstab'
        return (False, False)
    else:
        tgt = mob.target
        if not tgt or not AllowHarmful(mob, tgt):
            mob.player.sendGameText(RPG_MSG_GAME_DENIED, "$src's <a:SkillBackstab>backstab</a> failed, no valid target.\\n", mob)
            return (False, False)
        if tgt.sleep <= 0 and tgt.stun <= 0 and mob in tgt.aggro.keys():
            mob.player.sendGameText(RPG_MSG_GAME_DENIED, '$src cannot <a:SkillBackstab>backstab</a> a current enemy.\\n', mob)
            return (False, False)
        if tgt.plevel - 10 > mob.plevel:
            mob.player.sendGameText(RPG_MSG_GAME_DENIED, '$src lacks the skill to <a:SkillBackstab>backstab</a> $tgt, $tgt is too strong.\\n', mob)
            return (False, False)
        wpnRange = 0
        pweapon = mob.worn.get(RPG_SLOT_PRIMARY, None)
        if not pweapon or not pweapon.skill or pweapon.skill == 'Fists':
            mob.player.sendGameText(RPG_MSG_GAME_DENIED, '$src cannot <a:SkillBackstab>backstab</a> with $srchis fists.\\n', mob)
            return (False, False)
        noBackstab = ('1H Impact', '2H Impact')
        if pweapon.skill in noBackstab:
            mob.player.sendGameText(RPG_MSG_GAME_DENIED, '$src cannot backstab with a %s weapon.\\n' % pweapon.skill, mob)
            return (False, False)
        if pweapon and pweapon.wpnRange > wpnRange:
            wpnRange = pweapon.wpnRange / 5.0
        if GetRangeMin(mob, tgt) > wpnRange:
            mob.player.sendGameText(RPG_MSG_GAME_DENIED, '$src cannot <a:SkillBackstab>backstab</a> $tgt, out of range.\\n', mob)
            return (False, False)
        tgt.addAggro(mob, 200)
        bs = mob.skillLevels.get('Backstab', 0) / 8
        spread = mob.level - tgt.level + 10
        if spread > 40:
            spread = 40
        dmgMod = 0.25 + spread * 0.09375
        backstabDamage = (randint(bs, bs * bs) + 300) * dmgMod
        Damage(tgt, mob, backstabDamage, RPG_DMG_PHYSICAL, 'backstabs', False)
        mob.character.checkSkillRaise('Backstab', 3, 3)
        mob.cancelStatProcess('sneak', '$tgt is no longer sneaking!\\n')
        mob.player.mind.callRemote('playSound', 'sfx/DarkMagic_ProjectileLaunch.ogg')
        return (True, True)


def DoRescue(mob):
    if not mob.player:
        print 'WARNING: Non-player mob attempting to rescue'
        return (False, False)
    allianceMembers = []
    for player in mob.player.alliance.members:
        for character in player.party.members:
            cmob = character.mob
            if cmob:
                if cmob.pet:
                    allianceMembers.append(cmob.pet)
                allianceMembers.append(cmob)

    if len(allianceMembers) <= 1:
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'There is no one to <a:SkillRescue>rescue</a>.\\n')
        return (False, False)
    aggro = {}
    for m in mob.zone.activeMobs:
        if m.player:
            continue
        for amob, amt in m.aggro.iteritems():
            if amob in allianceMembers:
                if amt > aggro.get(m, 0):
                    aggro[m] = amt

    if not len(aggro):
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'There is no one in need of <a:SkillRescue>rescue</a>.\\n')
        return (False, False)
    for m, amt in aggro.iteritems():
        m.aggro[mob] = amt * 1.25

    mob.character.checkSkillRaise('Rescue')
    mob.player.sendGameText(RPG_MSG_GAME_BLUE, '$src <a:SkillRescue>rescues</a> the alliance!\\n', mob)
    mob.player.mind.callRemote('playSound', 'sfx/Fireball_Launch5.ogg')
    return (True, True)


def DoEvade(mob):
    if not mob.player:
        print 'WARNING: Non-player mob attempting to evade'
        return (False, False)
    allianceMembers = []
    for player in mob.player.alliance.members:
        for character in player.party.members:
            cmob = character.mob
            if cmob.pet:
                allianceMembers.append(cmob.pet)
            allianceMembers.append(cmob)

    if len(allianceMembers) <= 1:
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, '$src needs a member of $srchis alliance to shift the focus of the aggressor onto.\\n', mob)
        return (False, False)
    mobAggro = {}
    memberAggro = {}
    for m in mob.zone.activeMobs:
        if m.player:
            continue
        for amob, amt in m.aggro.iteritems():
            if amob == mob:
                if amt > mobAggro.get(m, 0):
                    mobAggro[m] = amt
            elif amob in allianceMembers:
                if amt > memberAggro.get(m, 0):
                    memberAggro[m] = amt

    if not len(mobAggro):
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, '$src has no one to <a:SkillEvade>evade</a>.\\n', mob)
        return (False, False)
    slevel = mob.skillLevels.get('Evade', 0)
    aggroMod = 0.05 * slevel / 1000.0
    for m, amt in mobAggro.iteritems():
        try:
            memberAmt = memberAggro[m]
        except:
            continue

        if amt < memberAmt:
            m.aggro[mob] -= int(ceil(aggroMod * m.aggro[mob]))
        else:
            m.aggro[mob] = memberAmt - int(ceil(aggroMod * m.aggro[mob]))

    mob.character.checkSkillRaise('Evade')
    mob.player.sendGameText(RPG_MSG_GAME_BLUE, '$src <a:SkillEvade>evades</a> the focus of the aggressor!\\n', mob)
    mob.player.mind.callRemote('playSound', 'sfx/Fireball_Launch5.ogg')
    return (True, True)


def DoShieldBash(mob):
    tgt = mob.target
    if not tgt:
        if mob.player:
            mob.player.sendGameText(RPG_MSG_GAME_DENIED, "$src's <a:SkillShieldBash>shield bash</a> failed, no target.\\n", mob)
        return (False, False)
    else:
        wshield = mob.worn.get(RPG_SLOT_SHIELD, None)
        if not wshield or not wshield.skill or wshield.skill != 'Shields':
            if mob.player:
                mob.player.sendGameText(RPG_MSG_GAME_DENIED, '$src cannot <a:SkillShieldBash>shield bash</a> without a shield.\\n', mob)
            return (False, False)
        if GetRangeMin(mob, tgt) > 1:
            if mob.player:
                mob.player.sendGameText(RPG_MSG_GAME_DENIED, '$src cannot <a:SkillShieldBash>shield bash</a> $tgt, out of range.\\n', mob)
            return (False, False)
        tgt.addAggro(mob, 15)
        mob.cancelStatProcess('sneak', '$tgt is no longer sneaking!\\n')
        return (True, True)


SKILLS = {}
SKILLS['Assess'] = DoAssess
SKILLS['Backstab'] = DoBackstab
SKILLS['Disarm'] = DoDisarm
SKILLS['Evade'] = DoEvade
SKILLS['Pick Pocket'] = DoPickPocket
SKILLS['Rescue'] = DoRescue
SKILLS['Shield Bash'] = DoShieldBash

def DoSkillSpell(mob, skillname):
    from projectile import Projectile
    from spell import SpawnSpell
    player = mob.player
    mobSkill = mob.mobSkillProfiles[skillname]
    classSkill = mobSkill.classSkill
    skillLevel = mob.skillLevels.get(skillname, 0)
    if not skillLevel:
        return False
    else:
        mod = float(skillLevel) / float(classSkill.maxValue)
        if mod < 0.1:
            mod = 0.1
        proto = classSkill.spellProto
        tgt = mob.target
        if proto.target == RPG_TARGET_SELF:
            tgt = mob
        elif proto.target == RPG_TARGET_PARTY:
            tgt = mob
        elif proto.target == RPG_TARGET_ALLIANCE:
            tgt = mob
        elif proto.target == RPG_TARGET_PET:
            tgt = mob.pet
        elif player and proto.spellType & RPG_SPELL_HEALING and proto.target == RPG_TARGET_OTHER:
            tgt = GetPlayerHealingTarget(mob, tgt, proto)
        if not tgt:
            if player:
                if proto.spellType & RPG_SPELL_HARMFUL:
                    from command import CmdTargetNearest
                    CmdTargetNearest(mob, None, False, True)
                    tgt = mob.target
                    if not tgt:
                        player.sendGameText(RPG_MSG_GAME_DENIED, "$src's <a:Skill%s>%s</a> skill failed, no target.\\n" % (GetTWikiName(skillname), skillname), mob)
                else:
                    tgt = mob
        if not tgt:
            return False
        if proto.spellType & RPG_SPELL_HARMFUL:
            if not AllowHarmful(mob, tgt) and not proto.aoeRange:
                if player:
                    player.sendGameText(RPG_MSG_GAME_DENIED, "$src's <a:Skill%s>%s</a> skill failed, no valid target.\\n" % (GetTWikiName(skillname), skillname), mob)
                return False
            if not player and not (mob.master and mob.master.player) and not IsKOS(mob, tgt):
                return False
        if not proto.spellType & RPG_SPELL_HARMFUL and mob.target == tgt:
            if tgt and IsKOS(tgt, mob):
                tgt = mob
        if mob.character:
            c = 10
            if mobSkill.reuseTime > 180:
                c = 5
            if mobSkill.reuseTime > 360:
                c = 3
            mob.character.checkSkillRaise(skillname, c)
        if proto.animOverride:
            mob.zone.simAvatar.mind.callRemote('playAnimation', mob.simObject.id, proto.animOverride)
        if len(proto.particleNodes):
            mob.zone.simAvatar.mind.callRemote('triggerParticleNodes', mob.simObject.id, proto.particleNodes)
        if proto.projectile:
            p = Projectile(mob, mob.target)
            p.spellProto = proto
            p.launch()
        else:
            SpawnSpell(proto, mob, tgt, tgt.simObject.position, mod, skillname)
        return True


def UseSkill(mob, tgt, skillname):
    if not mob or mob.detached or not mob.simObject:
        return
    else:
        player = mob.player
        if 0 < mob.sleep or 0 < mob.stun or mob.isFeared:
            if player:
                player.sendGameText(RPG_MSG_GAME_DENIED, '$src is in no condition to use a skill!\\n', mob)
            return
        mobSkill = mob.mobSkillProfiles.get(skillname, None)
        if not mobSkill:
            if player:
                player.sendGameText(RPG_MSG_GAME_DENIED, '$src has lost $srchis ability in <a:Skill%s>%s</a>!\\n' % (GetTWikiName(skillname), skillname), mob)
            return
        classSkill = mobSkill.classSkill
        if not mobSkill.reuseTime:
            return
        if mob.skillReuse.has_key(classSkill.skillname):
            return
        success = used = False
        if skillname in SKILLS:
            if skillname not in mob.skillLevels:
                traceback.print_stack()
                print "AssertionError: mob %s doesn't know the skill %s!" % (mob.name, skillname)
                return
            success, used = SKILLS[skillname](mob)
        else:
            success = True
        if success and classSkill.spellProto:
            used = DoSkillSpell(mob, skillname)
        if used:
            mob.skillReuse[classSkill.skillname] = mobSkill.reuseTime
            if skillname != 'Feign Death':
                mob.cancelStatProcess('feignDeath', '$tgt is obviously not dead!\\n')
        if player:
            player.mind.callRemote('disturbEncounterSetting')
        return