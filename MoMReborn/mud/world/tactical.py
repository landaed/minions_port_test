# Embedded file name: mud\world\tactical.pyo
import mud.world.faction
from mud.world.core import *
from mud.world.defines import *
from mud.world.shared.vocals import *
from collections import defaultdict

class Tactical:

    def __init__(self, mob):
        self.mob = mob

    def doMob(self, otherMob):
        mob = self.mob
        if otherMob.aggroOff:
            return
        if not mob.aggro.has_key(otherMob):
            tgtRange = GetRange(mob, otherMob)
            aggroRange = mob.aggroRange * mob.zone.zone.aggroMod
            vis = mob.seeInvisible + otherMob.visibility
            if vis > 0:
                if vis > 1:
                    vis = 1
                if tgtRange <= aggroRange * vis:
                    if otherMob.sneak:
                        sn = otherMob.skillLevels.get('Sneak', 0)
                        if mob.plevel >= 90 or sn + 100 < mob.plevel * 10:
                            otherMob.cancelStatProcess('sneak', '$tgt has been noticed!\\n')
                        else:
                            return
                    mob.addAggro(otherMob, 10)
        elif otherMob.sneak:
            otherMob.cancelStatProcess('sneak', '$tgt has been noticed!\\n')

    def tick(self):
        mob = self.mob
        if not mob.zone.world.aggroOn:
            return
        elif mob.player or mob.detached:
            return
        else:
            zone = mob.zone
            simAvatar = zone.simAvatar
            doNewAggro = not mob.target
            if mob.aggroRange and not mob.battle:
                for id in mob.simObject.canSee:
                    try:
                        otherMob = zone.mobLookup[simAvatar.simLookup[id]]
                    except KeyError:
                        continue

                    if mob == otherMob:
                        continue
                    if not otherMob.player and otherMob.detached:
                        continue
                    if otherMob.invulnerable > 0:
                        continue
                    if mob.plevel < 50:
                        if mob.plevel < otherMob.plevel - 20:
                            continue
                    if not otherMob.aggroRange:
                        continue
                    if mob.master and mob.master.player:
                        if not mob.aggro.get(otherMob, 0):
                            continue
                    if otherMob.battle:
                        continue
                    if not IsKOS(mob, otherMob):
                        if mob.master or otherMob.master:
                            continue
                        if not otherMob.player:
                            if otherMob.assists and mob.realm == otherMob.realm:
                                if GetRange(mob, otherMob) <= otherMob.spawn.aggroRange * mob.zone.zone.aggroMod * 0.65:
                                    for m in mob.aggro.iterkeys():
                                        if not otherMob.aggro.get(m, 0):
                                            otherMob.addAggro(m, 5)

                        elif mob.assists and mob.realm == otherMob.realm:
                            if GetRange(mob, otherMob) <= mob.spawn.aggroRange * mob.zone.zone.aggroMod * 0.65:
                                for m in otherMob.aggro.iterkeys():
                                    if not m.player or m.detached:
                                        continue
                                    if not mob.aggro.get(m, 0):
                                        if m.realm != mob.realm and AllowHarmful(m, otherMob) and m.simObject.id in mob.simObject.canSee:
                                            mob.addAggro(m, 5)

                        continue
                    if doNewAggro:
                        if otherMob.player:
                            initial = not mob.aggro.get(otherMob, 0)
                            for c in otherMob.player.party.members:
                                if c.mob.detached:
                                    continue
                                self.doMob(c.mob)

                            if initial and mob.aggro.get(otherMob, 0):
                                a = 10
                                for member in otherMob.player.party.members:
                                    if not member.mob.detached and not member.mob.sneak:
                                        if member.mob.pet:
                                            mob.addAggro(member.mob.pet, a)
                                        else:
                                            mob.addAggro(member.mob, a)
                                        a -= 1

                        else:
                            self.doMob(otherMob)

            if len(mob.aggro):
                mostHated = None
                bestAggro = -999999
                bestRange = 999999
                bestRangeAggro = -999999
                bestRangeMob = None
                if mob.target:
                    bestRange = GetRange(mob, mob.target)
                    if bestRange <= mob.followRange or mob.battle:
                        bestRangeAggro = bestAggro = mob.aggro.get(mob.target, 0)
                        if bestAggro:
                            mostHated = mob.target
                            bestRangeMob = mob.target
                for m, hate in mob.aggro.iteritems():
                    if m.feignDeath:
                        continue
                    if hate:
                        testRange = GetRange(mob, m)
                        if testRange <= mob.followRange or mob.battle:
                            if hate > bestAggro:
                                bestAggro = hate
                                mostHated = m
                            if testRange < bestRange:
                                bestRange = testRange
                                bestRangeAggro = hate
                                bestRangeMob = m

                if mob.move <= 0 and bestRangeMob:
                    crange = GetRangeMin(mob, mostHated)
                    wpnRange = 0
                    pweapon = mob.worn.get(RPG_SLOT_PRIMARY)
                    sweapon = mob.worn.get(RPG_SLOT_SECONDARY)
                    if pweapon and pweapon.wpnRange > wpnRange:
                        wpnRange = pweapon.wpnRange / 5.0
                    if sweapon:
                        secondaryRangeAdjusted = sweapon.wpnRange / 5.0
                        if secondaryRangeAdjusted > wpnRange:
                            wpnRange = secondaryRangeAdjusted
                    if crange > wpnRange:
                        mostHated = bestRangeMob
                        bestAggro = bestRangeAggro
                if mostHated:
                    if mob.master and mob.master.player:
                        if bestAggro < RPG_PLAYERPET_AGGROTHRESHOLD * mob.level:
                            zone.setTarget(mob, None)
                            return
                    if mostHated.isFeared and mostHated.master:
                        master = mostHated.master
                        if mob.aggro.has_key(master):
                            testRange = GetRange(mob, master)
                            if testRange <= mob.followRange or mob.battle:
                                mostHated = master
                    if mostHated != mob.target:
                        snd = mob.spawn.getSound('sndAlert')
                        if snd:
                            mob.playSound(snd)
                        else:
                            mob.vocalize(VOX_MADSCREAM)
                        zone.setTarget(mob, mostHated)
                    if mostHated.combatTimer < 72:
                        mostHated.combatTimer = 72
                else:
                    mob.aggro = defaultdict(int)
                    if mob.target:
                        zone.setTarget(mob, None)
            else:
                zone.setTarget(mob, None)
            return