# Embedded file name: mud\world\projectile.pyo
from mud.world.core import AllowHarmful, GetRange
from mud.world.damage import Damage
from mud.world.defines import *
from math import ceil
from random import randint

class Projectile:
    id = 1L

    def __init__(self, src, dst, level = 1):
        self.src = src
        self.dst = dst
        self.weapon = None
        self.ammoDamage = 0
        self.ammoSpells = []
        self.spellProto = None
        self.speed = 1
        self.level = level
        self.projectile = None
        self.id = Projectile.id
        Projectile.id += 1
        return

    def onCollision(self, hitPos):
        src = self.src
        dst = self.dst
        if dst.detached or src.detached:
            return
        else:
            if self.spellProto:
                if self.spellProto.spellType & RPG_SPELL_HARMFUL and not src.character and dst != src.target:
                    return
                mod = 1.0
                if self.level != 1.0:
                    mod += self.level / 10.0
                from mud.world.spell import SpawnSpell
                SpawnSpell(self.spellProto, src, dst, hitPos, mod)
            else:
                if not AllowHarmful(src, dst):
                    return
                if src.character:
                    src.cancelStatProcess('invulnerable', '$tgt is no longer protected from death!\\n')
                if not dst.aggro.get(src, 0):
                    dst.addAggro(src, 10)
                askill = src.skillLevels.get('Archery')
                if not askill:
                    return
                missed = False
                if dst.plevel - src.plevel > 30:
                    missed = True
                else:
                    base = 4 - int((float(dst.plevel) - float(src.plevel)) / 10.0)
                    if base > 4:
                        base = 4
                    mod = int(float(askill) * 2.0 / float(dst.plevel))
                    resistance = dst.resists.get(RPG_RESIST_PHYSICAL, 0)
                    mod -= int(float(resistance) / float(askill))
                    if mod > 20:
                        mod = 20
                    base += mod
                    if base < 1:
                        base = 1
                    if not randint(0, base):
                        missed = True
                if missed:
                    if src.character:
                        if GetRange(src, dst) > 20:
                            src.player.sendGameText(RPG_MSG_GAME_DENIED, '%s completely misses the target.\\n' % src.name)
                        else:
                            src.player.sendGameText(RPG_MSG_GAME_DENIED, "%s easily deflects %s\\'s ranged attack.\\n" % (dst.name, src.name))
                    return
                if src.target != dst:
                    if src.character:
                        src.player.sendGameText(RPG_MSG_GAME_YELLOW, '%s misses the target and hits %s instead.\\n' % (src.name, dst.name))
                    else:
                        return
                dmg = askill
                wdmg = (self.weapon.wpnDamage + self.ammoDamage) * 10
                wdmg *= askill / 1000.0
                dmg += wdmg
                if dmg < 20:
                    dmg = 20
                dmg = randint(int(dmg / 2), int(dmg))
                critical = False
                try:
                    icrit = src.skillLevels['Precise Shot']
                except:
                    icrit = 0

                if icrit:
                    ps = src.advancements.get('preciseShot', 0.0)
                    chance = float(ceil(15 / src.critical))
                    chance *= 1.0 - ps
                    chance = int(chance)
                    if not randint(0, chance):
                        if src.character:
                            src.character.checkSkillRaise('Precise Shot', 5)
                        icrit /= 200.0
                        if icrit < 2:
                            icrit = 2.0
                        if icrit > 5:
                            icrit = 5.0
                        dmg *= icrit * (1.0 + ps)
                        dmg *= src.critical
                        dmg = int(dmg)
                        critical = True
                if dmg:
                    if not critical:
                        Damage(dst, src, dmg, RPG_DMG_PIERCING, None, False)
                    else:
                        Damage(dst, src, dmg, RPG_DMG_PIERCING, 'precisely wounds', False)
                    from mud.world.combat import doAttackProcs
                    doAttackProcs(src, dst, self.weapon, self.ammoSpells)
                    if src.character:
                        src.character.checkSkillRaise('Archery')
            return

    def launch(self):
        if self.spellProto:
            self.projectile = self.spellProto.projectile
            self.speed = self.spellProto.projectileSpeed
        self.src.zone.launchProjectile(self)