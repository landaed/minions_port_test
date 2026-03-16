# Embedded file name: mud\world\damage.pyo
from mud.world.core import *
from mud.world.defines import *
from mud.world.messages import GameMessage
from mud.world.shared.vocals import *
from math import ceil, floor
from random import randint
import time

class ExtraDamageInfo:

    def __init__(self):
        self.clear()

    def clear(self):
        self.resistDebuff = None
        self.resistDebuffMod = 0
        return


class XPDamage:

    def __init__(self):
        self.lastTime = time.time()
        self.amount = 0

    def addDamage(self, amount):
        self.amount += amount
        self.lastTime = time.time()


DAMAGETEXT = {}
DAMAGETEXT[RPG_DMG_FIRE] = 'burns'
DAMAGETEXT[RPG_DMG_COLD] = 'freezes'
DAMAGETEXT[RPG_DMG_POISON] = 'poisons'
DAMAGETEXT[RPG_DMG_DISEASE] = 'diseases'
DAMAGETEXT[RPG_DMG_ACID] = 'corrodes'
DAMAGETEXT[RPG_DMG_ELECTRICAL] = 'zaps'
DAMAGETEXT[RPG_DMG_MAGICAL] = 'oppresses'
DAMAGETEXT[RPG_DMG_SLASHING] = 'slashes'
DAMAGETEXT[RPG_DMG_IMPACT] = 'crushes'
DAMAGETEXT[RPG_DMG_CLEAVE] = 'cleaves'
DAMAGETEXT[RPG_DMG_PIERCING] = 'pierces'
DAMAGETEXT[RPG_DMG_PHYSICAL] = 'damages'
DAMAGETEXT[RPG_DMG_PUMMEL] = 'pummels'
DAMAGETEXT[RPG_DMG_CLAWS] = 'claws'
DAMAGETEXT[RPG_DMG_CRITICAL] = 'critically wounds'
DAMAGETEXT[RPG_DMG_DRAIN] = 'drains'
DAMAGETEXTNOINFLICTOR = {}
DAMAGETEXTNOINFLICTOR[RPG_DMG_FIRE] = 'burned'
DAMAGETEXTNOINFLICTOR[RPG_DMG_COLD] = 'frozen'
DAMAGETEXTNOINFLICTOR[RPG_DMG_POISON] = 'poisoned'
DAMAGETEXTNOINFLICTOR[RPG_DMG_DISEASE] = 'diseased'
DAMAGETEXTNOINFLICTOR[RPG_DMG_ACID] = 'corroded'
DAMAGETEXTNOINFLICTOR[RPG_DMG_ELECTRICAL] = 'zapped'
DAMAGETEXTNOINFLICTOR[RPG_DMG_MAGICAL] = 'oppressed'
DAMAGETEXTNOINFLICTOR[RPG_DMG_SLASHING] = 'slashed'
DAMAGETEXTNOINFLICTOR[RPG_DMG_IMPACT] = 'crushed'
DAMAGETEXTNOINFLICTOR[RPG_DMG_CLEAVE] = 'cleaved'
DAMAGETEXTNOINFLICTOR[RPG_DMG_PUMMEL] = 'pummeled'
DAMAGETEXTNOINFLICTOR[RPG_DMG_PIERCING] = 'pierced'
DAMAGETEXTNOINFLICTOR[RPG_DMG_CLAWS] = 'clawed'
DAMAGETEXTNOINFLICTOR[RPG_DMG_CRITICAL] = 'critically wounded'
DAMAGETEXTNOINFLICTOR[RPG_DMG_DRAIN] = 'drains'
DAMAGETEXTNOINFLICTOR[RPG_DMG_PHYSICAL] = 'damaged'

def Heal(mob, healer, amount, isRegen = False):
    if mob.health >= mob.maxHealth:
        return
    gap = mob.maxHealth - mob.health
    if amount > gap:
        amount = gap
    mob.health += amount
    if mob != healer and not isRegen:
        if healer.player and amount > 1:
            for m in mob.zone.activeMobs:
                if m.player:
                    continue
                if m.aggro.get(mob, 0) > 0:
                    m.addAggro(healer, amount / 2)

    if mob.player and not isRegen:
        mob.player.sendGameText(RPG_MSG_GAME_GOOD, '%s has been healed for %i points!\\n' % (mob.name, amount))


def Damage(mob, inflictor, amount, dmgType, textDesc = None, doThorns = True, outputText = True, isDrain = False):
    if mob.invulnerable > 0:
        return 0
    elif dmgType != RPG_DMG_UNSTOPPABLE and not AllowHarmful(inflictor, mob):
        return 0
    else:
        if mob.combatTimer < 72:
            mob.combatTimer = 72
        if not mob.player:
            if not mob.mobInitialized:
                mob.initMob()
        if 0 >= amount:
            amount = 1
        if inflictor:
            if inflictor.character:
                inflictor.cancelStatProcess('invulnerable', '$tgt is no longer protected from death!\\n')
            if (inflictor.difficultyMod > 1.0 or inflictor.damageMod > 1.0) and doThorns:
                if inflictor.damageMod > inflictor.difficultyMod:
                    amount += amount * (inflictor.damageMod / 4.0)
                    amount = ceil(amount)
                else:
                    amount += amount * (inflictor.difficultyMod / 4.0)
                    amount = ceil(amount)
        if not isDrain:
            rtype = RESISTFORDAMAGE[dmgType]
            resist = mob.resists.get(rtype, 0)
        else:
            resist = 0
        extraDamageInfo = mob.extraDamageInfo
        if 0 < resist and extraDamageInfo.resistDebuffMod and rtype == extraDamageInfo.resistDebuff:
            resist -= mob.extraDamageInfo.resistDebuffMod
            if 0 > resist:
                resist = 0
        if resist:
            if 0 > resist:
                adjustedAMount = amount + -resist * 3
                if adjustedAMount > amount * 2:
                    adjustedAMount = amount * 2
                amount = adjustedAMount
            else:
                adjustedAMount = amount - resist * 2
                if adjustedAMount / amount < 0.5:
                    amount *= 0.5
                else:
                    amount = adjustedAMount
        amount = floor(amount)
        if 1 > amount:
            amount = 1
        if inflictor:
            if inflictor.player:
                for char in inflictor.player.party.members:
                    charMob = char.mob
                    if charMob.detached:
                        continue
                    hate = amount
                    if charMob == inflictor:
                        hate *= 2
                    mob.addAggro(charMob, hate)

            else:
                mob.addAggro(inflictor, amount * 2)
            mob.xpDamage.setdefault(inflictor, XPDamage()).addDamage(amount)
            if mob.player and not isDrain:
                for item in mob.wornBreakable.itervalues():
                    if item.repair and not randint(0, 20):
                        item.repair -= 1
                        repairRatio = float(item.repair) / float(item.repairMax)
                        if not repairRatio:
                            mob.player.sendGameText(RPG_MSG_GAME_RED, "%s's %s has broken! (0/%i)\\n" % (mob.name, item.name, item.repairMax))
                            mob.playSound('sfx/Shatter_IceBlock1.ogg')
                        elif 0.2 > repairRatio:
                            mob.player.sendGameText(RPG_MSG_GAME_YELLOW, "%s's %s is severely damaged! (%i/%i)\\n" % (mob.name,
                             item.name,
                             item.repair,
                             item.repairMax))
                            mob.playSound('sfx/Menu_Horror24.ogg')
                        item.setCharacter(mob.character, True)

        mob.cancelStatProcess('feignDeath', '$tgt is obviously not dead!\\n')
        mob.cancelSleep()
        if mob.player and mob.casting and not mob.combatCasting:
            cancel = True
            conc = mob.skillLevels.get('Concentration', 0)
            if conc:
                r = randint(0, amount)
                if r <= conc * 2:
                    cancel = False
                    mob.character.checkSkillRaise('Concentration', 2, 10)
            if cancel:
                t = mob.casting.spellProto.recastTime / 5
                if t:
                    mob.recastTimers[mob.casting.spellProto] = t
                mob.casting.cancel()
                mob.player.sendGameText(RPG_MSG_GAME_DENIED, "%s's casting has been interrupted!\\n" % mob.name)
        if (not mob.battle or not (inflictor and inflictor.battle)) and not isDrain:
            if outputText:
                if not textDesc:
                    if inflictor:
                        dmgText = DAMAGETEXT[dmgType]
                    else:
                        dmgText = DAMAGETEXTNOINFLICTOR[dmgType]
                else:
                    dmgText = textDesc
                if inflictor:
                    text = '%s %s %s for %i damage!\\n' % (inflictor.name,
                     dmgText,
                     mob.name,
                     amount)
                else:
                    text = '%s is %s for %i damage!\\n' % (mob.name, dmgText, amount)
                GameMessage(RPG_MSG_GAME_COMBAT, mob.zone, inflictor, mob, text, mob.simObject.position, 20)
            mob.zone.simAvatar.mind.callRemote('pain', mob.simObject.id)
            snd = mob.spawn.getSound('sndPain')
            if snd:
                if not randint(0, 1):
                    mob.playSound(snd)
            elif not randint(0, 2):
                mob.vocalize(VOX_HURTGRUNT)
            else:
                mob.vocalize(VOX_HURTPUNCH)
        mob.health -= amount
        DAMAGEAMOUNT = amount
        mob.tookDamage = True
        if doThorns and inflictor and len(mob.processesIn) and not isDrain:
            thornDmgType = DAMAGEFORRESIST[RESISTFORDAMAGE[dmgType]]
            dmgReflection = mob.dmgReflectionEffects.get(thornDmgType, None)
            if dmgReflection:
                bestThornDamage = 0
                thornDamage = 0
                for effect in dmgReflection:
                    thornDamage = ceil(amount * effect.dmgReflectionPercent)
                    if thornDamage > effect.dmgReflectionMax:
                        thornDamage = effect.dmgReflectionMax
                    if thornDamage > bestThornDamage:
                        bestThornDamage = thornDamage

                thornDamageTaken = Damage(mob=inflictor, inflictor=None, amount=bestThornDamage, dmgType=thornDmgType, textDesc=None, doThorns=False, outputText=False)
                thornText = '%s is %s for %i damage!\\n' % (inflictor.name, DAMAGETEXTNOINFLICTOR[thornDmgType], thornDamageTaken)
                GameMessage(RPG_MSG_GAME_COMBAT, mob.zone, mob, inflictor, thornText, mob.simObject.position, 20)
        extraDamageInfo.clear()
        return DAMAGEAMOUNT