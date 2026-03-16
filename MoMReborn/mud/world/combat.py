# Embedded file name: mud\world\combat.pyo
from mud.world.core import AllowHarmful, CoreSettings, GetLevelSpread, GetRangeMin
from mud.world.damage import Damage
from mud.world.defines import *
from mud.world.process import Process
from mud.world.spell import SpawnSpell
from mud.worlddocs.utils import GetTWikiName
from math import ceil, floor
from random import randint

class UnarmedSoundProfile:

    def __init__(self):
        self.sndAttack1 = 'character/Boxing_FemalePunchBreath06.ogg'
        self.sndAttack2 = 'character/Boxing_FemalePunchBreath07.ogg'
        self.sndAttack3 = 'character/Boxing_FemalePunchBreath09.ogg'
        self.sndAttack4 = 'character/Boxing_MalePunchGrunt01.ogg'
        self.sndAttack5 = 'character/Boxing_MalePunchGrunt02.ogg'
        self.sndAttack6 = 'character/Boxing_MalePunchGrunt05.ogg'
        self.sndAttack7 = 'character/Boxing_MalePunchGrunt03.ogg'
        self.sndAttack8 = 'character/Boxing_MalePunchBreath02.ogg'
        self.numSndAttack = 8
        self.sndHit1 = 'character/Punch_Boxing_BodyHit01.ogg'
        self.sndHit2 = 'character/Punch_Boxing_BodyHit02.ogg'
        self.sndHit3 = 'character/Punch_Boxing_BodyHit03.ogg'
        self.sndHit4 = 'character/Punch_Boxing_BodyHit04.ogg'
        self.sndHit5 = 'character/Punch_Boxing_FaceHit1.ogg'
        self.sndHit6 = 'character/Punch_Boxing_FaceHit2.ogg'
        self.sndHit7 = 'character/Punch_Boxing_FaceHit3.ogg'
        self.sndHit8 = 'character/Punch_Boxing_FaceHit4.ogg'
        self.numSndHit = 8

    def getSound(self, snd):
        if snd == 'sndAttack':
            return getattr(self, 'sndAttack%i' % randint(1, 8))
        return getattr(self, 'sndHit%i' % randint(1, 8))


UNARMEDSOUNDPROFILE = UnarmedSoundProfile()

def SuccessfulAttack(mob, offhand = False):
    char = mob.character
    skill = 'Fists'
    if offhand:
        wpn = mob.worn.get(RPG_SLOT_SECONDARY, None)
    else:
        wpn = mob.worn.get(RPG_SLOT_PRIMARY, None)
    if wpn and wpn.skill:
        skill = wpn.skill
    char.checkSkillRaise(skill, 1, 8)
    char.checkSkillRaise('Tactics Offense', 1, 8)
    if offhand:
        pweapon = mob.worn.get(RPG_SLOT_PRIMARY, None)
        if pweapon and wpn:
            if '2H' in pweapon.skill or '2H' in skill and mob.skillLevels.get('Power Wield'):
                char.checkSkillRaise('Power Wield', 1, 8)
            else:
                char.checkSkillRaise('Dual Wield', 1, 8)
        else:
            char.checkSkillRaise('Dual Wield', 1, 8)
    return


def SuccessfulDefense(mob):
    mob.character.checkSkillRaise('Tactics Defense', 1, 5)


def doAttackProcs(attacker, defender, weapon = None, additionalProcs = None):
    if not attacker:
        return
    spellProcs = []
    if weapon:
        if not weapon.penalty:
            spellProcs.extend(weapon.spells)
        spellProcs.extend(weapon.procs.keys())
    if additionalProcs:
        spellProcs.extend(additionalProcs)
    spellProcs.extend(attacker.itemSetSpells.get(RPG_ITEM_TRIGGER_MELEE, []))
    refreshProcs = False
    dexMod = float(min(attacker.dex, 7500)) / 750.0 - 10.0
    dexMod = 0.75 + dexMod * dexMod / 400.0
    for proc in spellProcs:
        if proc.trigger == RPG_ITEM_TRIGGER_MELEE or proc.trigger == RPG_ITEM_TRIGGER_POISON:
            modFreq = int(round(dexMod * proc.frequency))
            if modFreq <= 1 or not randint(0, modFreq):
                proto = proc.spellProto
                tgt = defender
                if proto.target == RPG_TARGET_SELF:
                    tgt = attacker
                elif proto.target == RPG_TARGET_PARTY:
                    tgt = attacker
                elif proto.target == RPG_TARGET_ALLIANCE:
                    tgt = attacker
                elif proto.target == RPG_TARGET_PET:
                    tgt = attacker.pet
                if tgt:
                    if proc.trigger == RPG_ITEM_TRIGGER_POISON and weapon:
                        weapon.procs[proc][0] -= 1
                        if weapon.procs[proc][0] <= 0:
                            del weapon.procs[proc]
                            if attacker.player or attacker.master and attacker.master.player:
                                if attacker.player:
                                    player = attacker.player
                                else:
                                    player = attacker.master.player
                                player.sendGameText(RPG_MSG_GAME_SPELLEND, "The <a:Spell%s>%s</a> on %s's <a:Item%s>%s</a> has worn off.\\n" % (GetTWikiName(proto.name),
                                 proto.name,
                                 attacker.name,
                                 GetTWikiName(weapon.itemProto.name),
                                 weapon.name))
                                refreshProcs = True
                    SpawnSpell(proto, attacker, tgt, tgt.simObject.position, 1.0, proc=True)

    if refreshProcs:
        if weapon:
            weapon.itemInfo.refreshProcs()


class CombatProcess(Process):

    def __init__(self, src, dst):
        Process.__init__(self, src, dst)
        self.type = 'Combat'
        self.dmgType = 0
        self.attacker = src
        self.defender = dst
        src.primaryAttackTimer = 0
        src.secondaryAttackTimer = 0

    def getPrimaryDamage(self):
        dmg = self.attacker.level * 3 + 10
        ratio = float(self.damage) / 100.0
        if '2H' in self.skill:
            ratio += 0.66
        dmg += self.attacker.pre / 3
        return dmg * ratio + dmg * ratio

    def getSecondaryDamage(self):
        dmg = self.attacker.level * 2 + 10
        ratio = float(self.damage) / 100.0
        if '2H' in self.skill:
            ratio += 0.66
        dmg += self.attacker.pre / 5
        return dmg * ratio + dmg * ratio

    def getPrimaryAttackRate(self):
        mob = self.attacker
        base = float(mob.primaryAttackRate)
        wpnRate = 16.0
        pweapon = mob.worn.get(RPG_SLOT_PRIMARY)
        sweapon = mob.worn.get(RPG_SLOT_SECONDARY)
        if mob.player and (not pweapon or not pweapon.skill or 'Fists' == pweapon.skill):
            monkfists = mob.advancements.get('monkFists', 0)
            if monkfists:
                if monkfists == 1:
                    wpnRate = 14
                elif monkfists == 2:
                    wpnRate = 13
                elif monkfists == 3:
                    wpnRate = 12
                else:
                    wpnRate = 10
        else:
            monkfists = 0
        slow = 0
        if pweapon and sweapon:
            improve = mob.advancements.get('powerWield', 0.0)
            if improve < 1.0:
                if pweapon.skill and '2H' in pweapon.skill:
                    slow += 0.15
                if sweapon.skill and '2H' in sweapon.skill:
                    slow += 0.15
                if slow == 0.3:
                    if improve:
                        slow *= 1.0 - improve
        if pweapon and not monkfists:
            wpnRate = float(pweapon.wpnRate)
        base += wpnRate
        haste = mob.itemHaste + mob.innateHaste + float(mob.effectHaste[1])
        haste -= mob.slow
        haste -= slow
        if not mob.stamina:
            haste -= 0.2
        if haste < 0:
            base += floor(base * -haste)
        else:
            base -= floor(base * haste)
        base += 4
        if base < 8:
            base = 8
        return ceil(base)

    def getSecondaryAttackRate(self):
        mob = self.attacker
        base = float(mob.secondaryAttackRate)
        wpnRate = 20.0
        pweapon = mob.worn.get(RPG_SLOT_PRIMARY)
        sweapon = mob.worn.get(RPG_SLOT_SECONDARY)
        if (not sweapon or not sweapon.skill or 'Fists' == sweapon.skill) and mob.player:
            monkfists = mob.advancements.get('monkFists', 0.0)
            if monkfists:
                if monkfists == 1:
                    wpnRate = 14
                elif monkfists == 2:
                    wpnRate = 13
                elif monkfists == 3:
                    wpnRate = 12
                else:
                    wpnRate = 10
        else:
            monkfists = 0
        slow = 0
        if pweapon and sweapon:
            improve = mob.advancements.get('powerWield', 0.0)
            if improve < 1.0:
                if '2H' in pweapon.skill:
                    slow += 0.15
                if '2H' in sweapon.skill:
                    slow += 0.15
                if slow == 0.3:
                    if improve:
                        slow *= 1.0 - improve
        if sweapon and not monkfists:
            wpnRate = float(sweapon.wpnRate)
        base += wpnRate
        haste = mob.itemHaste + mob.innateHaste + float(mob.effectHaste[1])
        haste -= mob.slow
        haste -= slow
        if not mob.stamina:
            haste -= 0.2
        if haste < 0:
            base += floor(base * -haste)
        else:
            base -= floor(base * haste)
        base += 6
        if base < 11:
            base = 11
        return ceil(base)

    def clearSrc(self):
        self.cancel()
        self.src = None
        return

    def clearDst(self):
        self.cancel()
        self.dst = None
        return

    def begin(self):
        Process.begin(self)

    def end(self):
        Process.end(self)

    def tick(self):
        src = self.src
        dst = self.dst
        attackerSkillup = src.character and not dst.player and not (dst.master and dst.master.player)
        while src.target == dst and dst.health:
            if not src.player and dst.feignDeath:
                src.zone.setTarget(src, None)
                break
            inhibit = False
            attacker = self.attacker
            defender = self.defender
            player = attacker.player
            if player:
                if not AllowHarmful(attacker, defender):
                    attacker.attackOff()
                    yield True
                    continue
                if attacker.casting:
                    if attacker.casting.spellProto.skillname != 'Singing' and not attacker.combatCasting:
                        yield True
                        continue
            inhibitPrimary = False
            inhibitSecondary = False
            if src.primaryAttackTimer <= 3 or src.secondaryAttackTimer <= 3:
                if defender.simObject.id not in attacker.simObject.canSee:
                    attacker.combatInhibited += 3
                    if player and not player.msgCombatCantSee:
                        player.msgCombatCantSee = 20
                        player.sendGameText(RPG_MSG_GAME_DENIED, "%s's adversary is obstructed!\\n" % attacker.character.name)
                    inhibit = True
                crange = GetRangeMin(attacker, defender)
                wpnRange = 0
                primaryRangeAdjusted = 0
                secondaryRangeAdjusted = 0
                pweapon = attacker.worn.get(RPG_SLOT_PRIMARY)
                sweapon = attacker.worn.get(RPG_SLOT_SECONDARY)
                if pweapon and pweapon.wpnRange > wpnRange:
                    primaryRangeAdjusted = pweapon.wpnRange / 5.0
                    wpnRange = primaryRangeAdjusted
                if sweapon:
                    secondaryRangeAdjusted = sweapon.wpnRange / 5.0
                    if secondaryRangeAdjusted > wpnRange:
                        wpnRange = secondaryRangeAdjusted
                        if pweapon and crange > primaryRangeAdjusted:
                            inhibitPrimary = True
                    elif crange > secondaryRangeAdjusted:
                        inhibitSecondary = True
                if crange > wpnRange:
                    attacker.combatInhibited += 3
                    if player and not player.msgCombatNotCloseEnough:
                        player.msgCombatNotCloseEnough = 20
                        player.sendGameText(RPG_MSG_GAME_DENIED, "%s's adversary is out of melee range!\\n" % attacker.character.name)
                    inhibit = True
            if src.sleep <= 0 and src.stun <= 0 and not src.isFeared and not inhibit:
                if not inhibitPrimary:
                    src.primaryAttackTimer -= 3
                    if src.primaryAttackTimer <= 0:
                        src.primaryAttackTimer += self.getPrimaryAttackRate()
                        attacks = 1
                        da = src.skillLevels.get('Double Attack', 0)
                        if da:
                            da = 1000 - da
                            da /= 40
                            da += dst.plevel / 10
                            if da < 10:
                                da = 10
                            if not randint(0, int(da)):
                                attacks = 2
                                if attackerSkillup:
                                    src.character.checkSkillRaise('Double Attack', 2, 2)
                        ta = src.skillLevels.get('Triple Attack', 0)
                        if ta:
                            ta = 1000 - ta
                            ta /= 15
                            ta += dst.plevel / 10
                            if ta < 10:
                                ta = 10
                            if not randint(0, int(ta)):
                                attacks = 3
                                if attackerSkillup:
                                    src.character.checkSkillRaise('Triple Attack', 2, 2)
                        if src.player:
                            if attacks == 2:
                                src.player.sendGameText(RPG_MSG_GAME_YELLOW, '%s double attacks!\\n' % src.name)
                            elif attacks == 3:
                                src.player.sendGameText(RPG_MSG_GAME_YELLOW, '%s triple attacks!\\n' % src.name)
                        self.skill = 'Fists'
                        self.dmgType = RPG_DMG_PUMMEL
                        if not src.player:
                            self.damage = src.plevel / 2
                        else:
                            self.damage = 4
                        self.weapon = src.worn.get(RPG_SLOT_PRIMARY, None)
                        if self.weapon:
                            self.dmgType = self.weapon.dmgType
                            self.damage = int(self.weapon.wpnDamage * 15)
                            if self.weapon.skill:
                                self.skill = self.weapon.skill
                        if self.skill == 'Fists' and src.player:
                            monkfists = attacker.advancements.get('monkFists', 0.0)
                            if monkfists:
                                if monkfists == 1:
                                    self.damage = 225
                                elif monkfists == 2:
                                    self.damage = 300
                                elif monkfists == 3:
                                    self.damage = 450
                                else:
                                    self.damage = 600
                        self.damage += int(src.skillLevels[self.skill] * 1.5)
                        for a in xrange(0, attacks):
                            dmg = self.doAttack(self.getPrimaryDamage(), False)
                            if dmg and attackerSkillup:
                                SuccessfulAttack(src)

                if not inhibitSecondary:
                    powerWield = src.skillLevels.get('Power Wield', 0)
                    if src.skillLevels.has_key('Dual Wield') or powerWield:
                        skip = False
                        w = src.worn.get(RPG_SLOT_PRIMARY)
                        s = src.worn.get(RPG_SLOT_SECONDARY)
                        twohanded = 0
                        if w and w.skill and '2H' in w.skill:
                            twohanded += 1
                        if s and s.skill and '2H' in s.skill:
                            twohanded += 1
                        if twohanded and (not w or not s or not powerWield):
                            skip = True
                        if src.secondaryAttackRate > 0 and not skip:
                            src.secondaryAttackTimer -= 3
                            if src.secondaryAttackTimer <= 0:
                                src.secondaryAttackTimer += self.getSecondaryAttackRate()
                                self.skill = 'Fists'
                                self.dmgType = RPG_DMG_PUMMEL
                                if not src.player:
                                    self.damage = src.plevel / 2
                                else:
                                    self.damage = 4
                                self.weapon = src.worn.get(RPG_SLOT_SECONDARY, None)
                                if self.weapon:
                                    self.dmgType = self.weapon.dmgType
                                    self.damage = int(self.weapon.wpnDamage * 15)
                                    if self.weapon.skill:
                                        self.skill = self.weapon.skill
                                if self.skill == 'Fists' and src.player:
                                    monkfists = attacker.advancements.get('monkFists', 0.0)
                                    if monkfists:
                                        if monkfists == 1:
                                            self.damage = 150
                                        elif monkfists == 2:
                                            self.damage = 200
                                        elif monkfists == 3:
                                            self.damage = 300
                                        else:
                                            self.damage = 400
                                self.damage += int(src.skillLevels[self.skill])
                                dmg = self.doAttack(self.getSecondaryDamage(), True)
                                if dmg and attackerSkillup:
                                    SuccessfulAttack(src, True)
            yield True

        return

    def calcDamageActual(self, MAXDMG):
        attacker = self.attacker
        defender = self.defender
        spread = GetLevelSpread(attacker, defender)
        R = randint(0, 99)
        if self.wpnAdvanceMod:
            MAXDMG += MAXDMG * self.wpnAdvanceMod
        d = MAXDMG / 3.0
        additive = MAXDMG / 3.0
        if R <= 10:
            additive = 0
        if d < 1.0:
            d = 1.0
        R = ceil(d / spread)
        if not R:
            R = 1
        damage = randint(1, R)
        damage = damage + additive
        if damage > MAXDMG:
            damage = MAXDMG
        if not attacker.player:
            if attacker.plevel < 30:
                damage = int(ceil(damage * 0.65))
                if damage < attacker.plevel:
                    damage = attacker.plevel
            elif attacker.plevel < 60:
                if damage < attacker.plevel * 5:
                    damage = attacker.plevel * 5
            elif attacker.plevel < 80:
                if damage < attacker.plevel * 10:
                    damage = attacker.plevel * 10
            elif attacker.plevel < 90:
                if damage < attacker.plevel * 20:
                    damage = attacker.plevel * 20
            elif damage < attacker.plevel * 30:
                damage = attacker.plevel * 30
            if attacker.zone.zone.name == 'field':
                damage = int(ceil(damage * attacker.damageMod))
            if attacker.master:
                damage *= 0.5
                if damage < 10:
                    damage = 10
        return int(damage)

    def calcDamageAdjustedMax(self, damage):
        attacker = self.attacker
        defender = self.defender
        if attacker.player:
            plevel = attacker.skillLevels[self.skill] / 10
            if plevel < 1:
                plevel = 1
        else:
            plevel = attacker.plevel
        DFDLEVEL = defender.level
        ATTLEVEL = attacker.level
        DFDDEFENSE = defender.defense
        if DFDLEVEL > 100:
            DFDLEVEL = 100
        spread = defender.plevel - plevel
        if plevel < defender.plevel:
            spread = spread + (defender.plevel - plevel) ** 2
        LS = (spread + 100.0) * 10.0 / 1000.0
        R = LS * 0.5
        ADJUSTEDMAX = damage / R
        ADJUSTEDMAX = ADJUSTEDMAX - DFDDEFENSE / 100 * (DFDLEVEL * 4 / 100)
        a = defender.armor / LS
        if a > defender.armor:
            a = defender.armor
        a *= defender.plevel / 100.0
        a *= 0.5
        a = int(a)
        rand = randint(0, 9)
        if rand < 4:
            a = a / 3
        elif rand <= 7:
            a = a / 2
        if a > ADJUSTEDMAX:
            a = ADJUSTEDMAX
        a = ADJUSTEDMAX - a
        if not a:
            a = 1
        if ADJUSTEDMAX / a < ADJUSTEDMAX / 3:
            ADJUSTEDMAX /= 3
        else:
            ADJUSTEDMAX /= a
        ADJUSTEDMAX *= 1.3333
        s = 0
        d = 5.0 - plevel / 20.0
        if d < 2:
            d = 2
        s = attacker.str / d
        ADJUSTEDMAX += s
        if ADJUSTEDMAX < plevel * 3.5:
            ADJUSTEDMAX = plevel * 3.5
        ADJUSTEDMAX += plevel * 2
        if ADJUSTEDMAX > damage / 2:
            ADJUSTEDMAX = damage / 2
        if ADJUSTEDMAX < 6:
            ADJUSTEDMAX = 6
        elif ADJUSTEDMAX > 6500:
            ADJUSTEDMAX = 6500
        return int(ADJUSTEDMAX)

    def calcBaseHitPercentage(self, attoffense, defdefense):
        attacker = self.attacker
        defender = self.defender
        R = GetLevelSpread(attacker, defender)
        R *= 0.5
        d = defdefense * (R * R)
        if not d:
            d = 1
        base = attoffense * 60 / d
        if base > 99:
            base = 99
        elif base < 1:
            base = 1
        lc = attacker.plevel / 4
        if base < lc:
            base = lc
        return base

    def doAttack(self, dmg, offhand = False):
        attacker = self.attacker
        defender = self.defender
        attackerSkillup = attacker.character and not defender.player and not (defender.master and defender.master.player)
        defenderSkillup = defender.character and not attacker.player and not (attacker.master and attacker.master.player)
        if attacker.player:
            stm = attacker.plevel * 3
            if offhand:
                stm = int(stm * 0.6)
            if stm < 1:
                stm = 1
            attacker.stamina -= stm
            if attacker.stamina < 0:
                attacker.stamina = 0
            attacker.cancelStatProcess('invulnerable', '$tgt is no longer protected from death!\\n')
        if not defender.aggro.get(attacker, 0):
            defender.addAggro(attacker, 10)
        if not defender.combatTimer:
            defender.combatTimer = 72
        block = defender.skillLevels.get('Block', 0)
        if block and defender.plevel + 5 >= attacker.plevel:
            if attacker.plevel > defender.plevel:
                block -= (attacker.plevel - defender.plevel) * 2
            block /= 2
            if block < 1:
                block = 1
            x = defender.plevel * 15
            if x < block * 10:
                x = block * 10
            if randint(0, x) < block:
                if attacker.player:
                    attacker.player.sendGameText(RPG_MSG_GAME_YELLOW, "%s blocks %s's attack!\\n" % (defender.name, attacker.name))
                if defender.player:
                    defender.player.sendGameText(RPG_MSG_GAME_YELLOW, "%s blocks %s's attack!\\n" % (defender.name, attacker.name))
                if defenderSkillup and attacker.plevel >= defender.plevel - 10:
                    defender.character.checkSkillRaise('Block', 1, 1)
                return 0
        block = defender.skillLevels.get('Dodge', 0)
        if block and defender.plevel + 5 >= attacker.plevel:
            if attacker.plevel > defender.plevel:
                block -= (attacker.plevel - defender.plevel) * 2
            block /= 2
            if block < 1:
                block = 1
            x = defender.plevel * 15
            if x < block * 10:
                x = block * 10
            if randint(0, x) < block:
                if attacker.player:
                    attacker.player.sendGameText(RPG_MSG_GAME_YELLOW, "%s dodges %s's attack!\\n" % (defender.name, attacker.name))
                if defender.player:
                    defender.player.sendGameText(RPG_MSG_GAME_YELLOW, "%s dodges %s's attack!\\n" % (defender.name, attacker.name))
                if defenderSkillup and attacker.plevel >= defender.plevel - 10:
                    defender.character.checkSkillRaise('Dodge', 1, 1)
                return 0
        block = defender.skillLevels.get('Shields', 0)
        if block and defender.worn.has_key(RPG_SLOT_SHIELD):
            skip = False
            wpn = defender.worn.get(RPG_SLOT_PRIMARY, None)
            wpn2 = defender.worn.get(RPG_SLOT_SECONDARY, None)
            if wpn and wpn.skill and '2H' in wpn.skill:
                skip = True
            elif wpn2 and wpn2.skill and '2H' in wpn2.skill:
                skip = True
            if not skip:
                if block and defender.plevel + 5 >= attacker.plevel:
                    if attacker.plevel > defender.plevel:
                        block -= (attacker.plevel - defender.plevel) * 2
                    block /= 2
                    if block < 1:
                        block = 1
                    x = defender.plevel * 15
                    if x < block * 10:
                        x = block * 10
                    if randint(0, x) < block:
                        sex = 'itself'
                        if defender.spawn.sex == 'Male':
                            sex = 'himself'
                        elif defender.spawn.sex == 'Female':
                            sex = 'herself'
                        if attacker.player:
                            attacker.player.sendGameText(RPG_MSG_GAME_YELLOW, "%s shields %s from %s's attack!\\n" % (defender.name, sex, attacker.name))
                        if defender.player:
                            defender.player.sendGameText(RPG_MSG_GAME_YELLOW, "%s shields %s from %s's attack!\\n" % (defender.name, sex, attacker.name))
                        if defenderSkillup and attacker.plevel >= defender.plevel - 10:
                            defender.character.checkSkillRaise('Shields', 1, 1)
                        defender.zone.simAvatar.mind.callRemote('playAnimation', defender.simObject.id, 'shieldblock')
                        return 0
        slot = RPG_SLOT_PRIMARY
        if offhand:
            slot = RPG_SLOT_SECONDARY
        wpn = attacker.worn.get(slot, None)
        if attacker.visibility <= 0:
            attacker.cancelInvisibility()
        if attacker.flying > 0:
            attacker.cancelFlying()
        if attacker.feignDeath > 0:
            attacker.cancelStatProcess('feignDeath', '$tgt is obviously not dead!\\n')
        player = attacker.player
        attacker.combatInhibited = 0
        actualdmg = 0
        offense = attacker.offense
        defense = defender.defense
        offense += attacker.skillLevels.get('Tactics Offense', 0) * 2
        defense += defender.skillLevels.get('Tactics Defense', 0)
        offense += attacker.skillLevels[self.skill]
        defense += defender.armor * (defender.plevel / 15)
        offense += offense * (attacker.offenseMod / 5.0)
        defense += defense * (defender.defenseMod / 5.0)
        self.wpnAdvanceMod = attacker.advancements.get(self.skill, 0.0)
        if self.wpnAdvanceMod:
            offense += offense * self.wpnAdvanceMod
        bane = -1
        twohanded = False
        if wpn:
            if wpn.wpnRaceBane == defender.spawn.race:
                bane = wpn.wpnRaceBaneMod
            if wpn.wpnResistDebuffMod:
                defender.extraDamageInfo.resistDebuff = wpn.wpnResistDebuff
                defender.extraDamageInfo.resistDebuffMod = wpn.wpnResistDebuffMod
            if wpn.skill and '2H' in wpn.skill:
                twohanded = True
        if bane != -1:
            offense += offense * RPG_BANEWEAPON_OFFENSE[bane]
        if attacker.player and CoreSettings.DIFFICULTY != RPG_DIFFICULTY_HARDCORE:
            offense = int(offense * 1.2)
        if attacker.player and CoreSettings.DIFFICULTY == RPG_DIFFICULTY_EASY:
            offense += int(offense * 1.1)
        offense = int(offense)
        defense = int(defense)
        hitp = self.calcBaseHitPercentage(offense, defense)
        if attacker.player and CoreSettings.DIFFICULTY == RPG_DIFFICULTY_EASY:
            hitp += int(hitp * 0.3)
        if attacker.player and CoreSettings.DIFFICULTY != RPG_DIFFICULTY_HARDCORE and defender.plevel < 5:
            hitp += int(hitp)
        if not attacker.player and attacker.plevel < 5 and hitp > 4:
            hitp /= 2
        actualdmg = 0
        if randint(0, 100) < hitp:
            maxdmg = self.calcDamageAdjustedMax(dmg)
            actualdmg = self.calcDamageActual(maxdmg)
            actualdmg *= attacker.meleeDmgMod
            if bane != -1:
                actualdmg += actualdmg * RPG_BANEWEAPON_DAMAGE[bane]
            if actualdmg:
                if defender.player and CoreSettings.DIFFICULTY == RPG_DIFFICULTY_EASY:
                    actualdmg /= 3
                    if actualdmg < 1:
                        actualdmg = 1
                elif defender.player and CoreSettings.DIFFICULTY != RPG_DIFFICULTY_HARDCORE and attacker.plevel < 5:
                    actualdmg = int(actualdmg * 0.5)
                    if actualdmg < 1:
                        actualdmg = 1
                if not attacker.stamina:
                    actualdmg = int(actualdmg * 0.75)
                    if actualdmg < 1:
                        actualdmg = 1
                critical = False
                if not offhand and attacker.stamina:
                    try:
                        icrit = attacker.skillLevels['Inflict Critical']
                    except:
                        icrit = 0

                    if icrit:
                        c = 20.0 / attacker.critical
                        c -= icrit / 200
                        if c < 10:
                            c = 10
                        chance = int(ceil(c))
                        if not randint(0, chance):
                            if attackerSkillup:
                                attacker.character.checkSkillRaise('Inflict Critical', 8)
                            c = randint(0, 8)
                            if c == 8:
                                icrit = 4
                            elif c >= 5:
                                icrit = 3
                            else:
                                icrit = 2
                            if not attacker.player:
                                actualdmg *= 2.0
                            else:
                                actualdmg *= attacker.critical
                                actualdmg *= icrit
                            critical = True
                            try:
                                gwnd = attacker.skillLevels['Grievous Wound']
                            except:
                                gwnd = 0

                            if attacker.plevel + int(floor(gwnd / 45.0)) < defender.plevel:
                                gwnd = 0
                            if not attacker.player:
                                gwnd /= 3
                            if gwnd and not randint(0, int(20.0 - float(gwnd) / 15.0)):
                                if attackerSkillup:
                                    attacker.character.checkSkillRaise('Grievous Wound', 2, 2)
                                actualdmg *= 1.1967 + 0.0033 * gwnd
                                if attacker.dmgBonusPrimary:
                                    actualdmg += attacker.dmgBonusPrimary
                                Damage(defender, attacker, actualdmg, RPG_DMG_CRITICAL, 'grievously wounds')
                            else:
                                if attacker.dmgBonusPrimary:
                                    actualdmg += attacker.dmgBonusPrimary
                                Damage(defender, attacker, actualdmg, RPG_DMG_CRITICAL)
                if not critical:
                    r = defender.skillLevels.get('Riposte', 0)
                    if r:
                        r = 1000 - r
                        r /= 50
                        r += attacker.plevel / 10
                        if r < 10:
                            r = 10
                        if not randint(0, int(r)):
                            if defenderSkillup:
                                defender.character.checkSkillRaise('Riposte', 10)
                            Damage(attacker, defender, actualdmg / 2, RPG_DMG_PHYSICAL, 'ripostes', False)
                    if attacker.dmgBonusPrimary and not offhand:
                        actualdmg += attacker.dmgBonusPrimary
                    elif attacker.dmgBonusOffhand and offhand:
                        actualdmg += attacker.dmgBonusOffhand
                    Damage(defender, attacker, actualdmg, self.dmgType)
        elif defenderSkillup and defender.plevel - attacker.plevel < 5:
            SuccessfulDefense(defender)
        sndProfile = UNARMEDSOUNDPROFILE
        if wpn and wpn.sndProfile:
            sndProfile = wpn.sndProfile
        snd = attacker.spawn.getSound('sndAttack')
        if snd:
            attacker.playSound(snd)
        if not actualdmg:
            snd = sndProfile.getSound('sndAttack')
            if snd:
                attacker.playSound(snd)
        else:
            snd = sndProfile.getSound('sndHit')
            if snd:
                attacker.playSound(snd)
            damagedProcs = defender.damagedProcs[:]
            damagedProcs.extend(defender.itemSetSpells.get(RPG_ITEM_TRIGGER_DAMAGED, []))
            if len(damagedProcs):
                for item in damagedProcs:
                    for ispell in item.spells:
                        if ispell.trigger == RPG_ITEM_TRIGGER_DAMAGED:
                            if ispell.frequency <= 1 or not randint(0, ispell.frequency):
                                proto = ispell.spellProto
                                if proto.target == RPG_TARGET_SELF:
                                    tgt = defender
                                elif proto.target == RPG_TARGET_PARTY:
                                    tgt = defender
                                elif proto.target == RPG_TARGET_ALLIANCE:
                                    tgt = defender
                                elif proto.target == RPG_TARGET_PET:
                                    tgt = defender.pet
                                else:
                                    tgt = attacker
                                if tgt:
                                    SpawnSpell(proto, defender, tgt, tgt.simObject.position, 1.0, proc=True)

            additionalProcs = None
            if self.skill == 'Fists':
                item = None
                if offhand:
                    item = attacker.worn.get(RPG_SLOT_LFINGER, None)
                else:
                    item = attacker.worn.get(RPG_SLOT_RFINGER, None)
                if item and item.skill == 'Fists':
                    additionalProcs = item.spells
            doAttackProcs(attacker, defender, wpn, additionalProcs)
            if wpn:
                if attacker.player and wpn.repairMax and wpn.repair and not randint(0, 20):
                    wpn.repair -= 1
                    repairRatio = float(wpn.repair) / float(wpn.repairMax)
                    if not repairRatio:
                        attacker.player.sendGameText(RPG_MSG_GAME_RED, "%s's <a:Item%s>%s</a> has broken! (%i/%i)\\n" % (attacker.name,
                         GetTWikiName(wpn.itemProto.name),
                         wpn.name,
                         wpn.repair,
                         wpn.repairMax))
                        attacker.playSound('sfx/Shatter_IceBlock1.ogg')
                    elif repairRatio < 0.2:
                        attacker.player.sendGameText(RPG_MSG_GAME_YELLOW, "%s's <a:Item%s>%s</a> is severely damaged! (%i/%i)\\n" % (attacker.name,
                         GetTWikiName(wpn.itemProto.name),
                         wpn.name,
                         wpn.repair,
                         wpn.repairMax))
                        attacker.playSound('sfx/Menu_Horror24.ogg')
                    wpn.setCharacter(attacker.character, True)
        defender.extraDamageInfo.clear()
        return actualdmg