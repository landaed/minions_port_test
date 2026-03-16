# Embedded file name: mud\world\spell.pyo
from mud.common.persistent import Persistent
from mud.world.core import *
from mud.world.defines import *
from mud.world.effect import Effect
from mud.world.messages import GameMessage
from mud.world.process import Process
from mud.world.projectile import Projectile
from mud.worlddocs.utils import GetTWikiName
from collections import defaultdict
from math import ceil, floor
from random import randint
from sqlobject import *
from time import time as sysTime
import traceback

class SpellClass(Persistent):
    spellProto = ForeignKey('SpellProto')
    classname = StringCol()
    level = IntCol()


class SpellComponent(Persistent):
    spellProto = ForeignKey('SpellProto')
    itemProto = ForeignKey('ItemProto')
    count = IntCol()


class SpellParticleNode(Persistent):
    spellProto = ForeignKey('SpellProto')
    node = StringCol()
    particle = StringCol()
    texture = StringCol()
    duration = IntCol()


class SpellExclusion(Persistent):
    spellProto = ForeignKey('SpellProto')
    otherProtoName = StringCol()
    overwrites = BoolCol(default=False)


class SpellStore(Persistent):
    character = ForeignKey('Character')
    spellProto = ForeignKey('SpellProto')
    time = IntCol(default=0)
    mod = FloatCol(default=1.0)
    healMod = FloatCol(default=0.0)
    damageMod = FloatCol(default=0.0)
    level = IntCol(default=1)


class SpellProto(Persistent):
    name = StringCol(alternateID=True)
    spellType = IntCol(default=RPG_SPELL_HARMFUL | RPG_SPELL_AICAST | RPG_SPELL_PERSISTENT)
    filterClass = StringCol(default='')
    filterRealm = IntCol(default=-1)
    filterRace = StringCol(default='')
    filterLevelMin = IntCol(default=0)
    filterLevelMax = IntCol(default=1000)
    filterTimeStart = IntCol(default=-1)
    filterTimeEnd = IntCol(default=-1)
    target = IntCol(default=RPG_TARGET_SELF)
    castTime = IntCol(default=30)
    recastTime = IntCol(default=60)
    failureTime = IntCol(default=0)
    duration = IntCol(default=0)
    castRange = FloatCol(default=20)
    aoeRange = FloatCol(default=0)
    manaCost = IntCol(default=0)
    manaScalar = FloatCol(default=1.0)
    difficulty = FloatCol(default=1.0)
    skillname = StringCol(default='')
    classesInternal = MultipleJoin('SpellClass')
    componentsInternal = MultipleJoin('SpellComponent')
    effectProtosInternal = RelatedJoin('EffectProto')
    itemSpellsInternal = MultipleJoin('ItemSpell')
    spellbookPic = StringCol(default='')
    iconSrc = StringCol(default='')
    iconDst = StringCol(default='')
    castingMsg = StringCol(default='')
    beginMsg = StringCol(default='')
    tickMsg = StringCol(default='')
    endMsg = StringCol(default='')
    projectile = StringCol(default='')
    projectileSpeed = FloatCol(default=0)
    particleCasting = StringCol(default='')
    particleBegin = StringCol(default='')
    particleTick = StringCol(default='')
    particleEnd = StringCol(default='')
    particleTextureCasting = StringCol(default='')
    particleTextureBegin = StringCol(default='')
    afxSpellEffectCasting = StringCol(default='')
    afxSpellEffectBegin = StringCol(default='')
    afxSpellEffectEnd = StringCol(default='')
    explosionBegin = StringCol(default='')
    sndCasting = StringCol(default='')
    sndBegin = StringCol(default='')
    sndBeginDuration = IntCol(default=0)
    sndTick = StringCol(default='')
    sndEnd = StringCol(default='')
    leechTickMsg = StringCol(default='')
    drainTickMsg = StringCol(default='')
    regenTickMsg = StringCol(default='')
    damageMsg = StringCol(default='')
    desc = StringCol(default='')
    animOverride = StringCol(default='')
    particleNodesInternal = MultipleJoin('SpellParticleNode')
    exclusionsInternal = MultipleJoin('SpellExclusion')

    def _init(self, *args, **kw):
        Persistent._init(self, *args, **kw)
        self.particleNodes = [ (pn.node,
         pn.particle,
         pn.texture,
         pn.duration) for pn in self.particleNodesInternal ]
        self.components = self.componentsInternal[:]
        self.classes = self.classesInternal[:]
        self.effectProtos = self.effectProtosInternal[:]
        self.itemSpells = self.itemSpellsInternal[:]
        self.exclusions = dict(((e.otherProtoName, e.overwrites) for e in self.exclusionsInternal))
        self.level = 100
        if len(self.classes):
            self.level = min(self.classes, key=lambda obj: obj.level).level
        self.petCache = False

    def qualify(self, mob):
        if not len(self.classes):
            return True
        mclasses = (mob.pclass, mob.sclass, mob.tclass)
        mlevels = (mob.plevel, mob.slevel, mob.tlevel)
        for cl, level in zip(mclasses, mlevels):
            if not cl or not level:
                break
            for klass in self.classes:
                if klass.classname == cl.name and level >= klass.level:
                    return True

        return False

    def affectsStat(self, statname):
        for e in self.effectProtos:
            if e.affectsStat(statname):
                return True

        return False

    def _get_pet(self):
        if self.petCache == False:
            con = self._connection.getConnection()
            pet = con.execute('SELECT summon_pet_id FROM effect_proto WHERE id IN (SELECT effect_proto_id FROM effect_proto_spell_proto WHERE spell_proto_id=%i) AND summon_pet_id!=0 LIMIT 1;' % self.id).fetchone()
            if pet:
                from mud.world.spawn import Spawn
                self.petCache = Spawn.get(pet[0])
            else:
                self.petCache = None
        return self.petCache


RESISTTEXT = {RPG_RESIST_PHYSICAL: 'physical',
 RPG_RESIST_MAGICAL: 'magical',
 RPG_RESIST_FIRE: 'fire',
 RPG_RESIST_COLD: 'cold',
 RPG_RESIST_POISON: 'poison',
 RPG_RESIST_DISEASE: 'disease',
 RPG_RESIST_ACID: 'acid',
 RPG_RESIST_ELECTRICAL: 'electrical'}

class Spell(Process):

    def __init__(self, src, dst, spellProto, mod = 1.0, time = 0, skill = None, doParticles = True, fromStore = False, level = 1, proc = False):
        Process.__init__(self, src, dst)
        self.spellProto = spellProto
        self.time = time
        self.mod = mod
        self.spellEffectInfo = None
        self.effects = []
        self.skill = skill
        self.doParticles = doParticles
        self.fromStore = fromStore
        self.level = level
        self.healMod = 0.0
        self.damageMod = 0.0
        if src and not skill and not proc:
            self.healMod = src.castHealMod
            self.damageMod = src.castDmgMod
        return

    def globalPush(self):
        Process.globalPush(self)

    def begin(self):
        proto = self.spellProto
        src = self.src
        dst = self.dst
        time = self.time
        eprotos = proto.effectProtos[:]
        if src.player and proto.spellType & RPG_SPELL_HARMFUL:
            if dst.plevel - proto.level > 30:
                src.player.sendGameText(RPG_MSG_GAME_DENIED, "$src's <a:Spell%s>%s</a> spell is too low level and has been resisted!\\n" % (GetTWikiName(proto.name), proto.name), src)
                self.cancel()
                return
        if not self.skill and dst.player and not proto.spellType & RPG_SPELL_HARMFUL and dst != src:
            if not src.player or src.player.role.name != 'Immortal':
                if proto.level - dst.plevel > 20 and not self.hasTeleport():
                    dst.player.sendGameText(RPG_MSG_GAME_DENIED, "$src's <a:Spell%s>%s</a> spell is too high level and will not hold on %s!\\n" % (GetTWikiName(proto.name), proto.name, dst.name), src)
                    if src.player:
                        src.player.sendGameText(RPG_MSG_GAME_DENIED, "$src's <a:Spell%s>%s</a> spell is too high level and will not take hold on %s!\\n" % (GetTWikiName(proto.name), proto.name, dst.name), src)
                    self.cancel()
                    return
        passed = False
        if proto.filterLevelMax >= dst.plevel >= proto.filterLevelMin:
            passed = True
        if passed and proto.filterRealm != -1:
            passed = False
            if dst.spawn.realm == proto.filterRealm:
                passed = True
        if passed and proto.filterClass:
            passed = False
            if dst.pclassInternal == proto.filterClass:
                passed = True
            elif dst.sclassInternal == proto.filterClass and proto.filterLevelMax >= dst.slevel >= proto.filterLevelMin:
                passed = True
            elif dst.tclassInternal == proto.filterClass and proto.filterLevelMax >= dst.tlevel >= proto.filterLevelMin:
                passed = True
        if passed and proto.filterRace:
            passed = False
            if dst.spawn.race == proto.filterRace:
                passed = True
        if not passed:
            if src.player and not self.skill:
                src.player.sendGameText(RPG_MSG_GAME_DENIED, "$src's <a:Spell%s>%s</a> spell has no effect on %s!\\n" % (GetTWikiName(proto.name), proto.name, dst.name), src)
            self.cancel()
            return
        if proto.spellType & RPG_SPELL_HARMFUL:
            resisted = []
            for e in eprotos:
                resist = dst.resists.get(e.resist, 0)
                if resist > 0:
                    if randint(0, int(resist / 2)) > 10:
                        resisted.append(e)

            for e in resisted:
                eprotos.remove(e)

            if not len(eprotos):
                if not self.skill:
                    if src.player:
                        txt = RESISTTEXT[resisted[0].resist]
                        src.player.sendGameText(RPG_MSG_GAME_DENIED, "$src's <a:Spell%s>%s</a> spell has been resisted!\\n" % (GetTWikiName(proto.name), proto.name), src)
                    if dst.player:
                        dst.player.sendGameText(RPG_MSG_GAME_DENIED, "%s resisted $src's <a:Spell%s>%s</a> spell!\\n" % (dst.character.name, GetTWikiName(proto.name), proto.name), src)
                else:
                    if src.player:
                        txt = RESISTTEXT[resisted[0].resist]
                        src.player.sendGameText(RPG_MSG_GAME_DENIED, "$src's <a:Skill%s>%s</a> skill has been resisted!\\n" % (GetTWikiName(self.skill), self.skill), src)
                    if dst.player:
                        dst.player.sendGameText(RPG_MSG_GAME_DENIED, "%s resisted $src's <a:Skill%s>%s</a> skill!\\n" % (dst.character.name, GetTWikiName(self.skill), self.skill), src)
                self.cancel()
                return
            if len(resisted):
                if src.player and not self.skill:
                    txt = RESISTTEXT[resisted[0].resist]
                    src.player.sendGameText(RPG_MSG_GAME_DENIED, "$src's %s spell was partially resisted!\\n" % txt, src)
                if dst.player and not self.skill:
                    dst.player.sendGameText(RPG_MSG_GAME_DENIED, "%s partially resisted $src's <a:Spell%s>%s</a> spell!\\n" % (dst.character.name, GetTWikiName(proto.name), proto.name), src)
        cancel = []
        for process in dst.processesIn.copy():
            if not isinstance(process, Spell):
                continue
            sp = process.spellProto
            if sp == proto:
                process.cancel()
                continue
            if sp.name in proto.exclusions:
                if proto.exclusions[sp.name]:
                    cancel.append(process)
                    continue
                else:
                    if src.player:
                        src.player.sendGameText(RPG_MSG_GAME_DENIED, "%s\\'s <a:Spell%s>%s</a> spell is supressed by <a:Spell%s>%s</a>!\\n" % (src.name,
                         GetTWikiName(proto.name),
                         proto.name,
                         GetTWikiName(sp.name),
                         sp.name))
                    if dst.player and src.player and dst.player != src.player:
                        dst.player.sendGameText(RPG_MSG_GAME_DENIED, "%s\\'s <a:Spell%s>%s</a> spell is supressed by <a:Spell%s>%s</a>!\\n" % (src.name,
                         GetTWikiName(proto.name),
                         proto.name,
                         GetTWikiName(sp.name),
                         sp.name))
                    self.cancel()
                    return
            elif proto.name in sp.exclusions:
                if sp.exclusions[proto.name]:
                    if src.player:
                        src.player.sendGameText(RPG_MSG_GAME_DENIED, "%s\\'s <a:Spell%s>%s</a> spell is supressed by <a:Spell%s>%s</a>!\\n" % (src.name,
                         GetTWikiName(proto.name),
                         proto.name,
                         GetTWikiName(sp.name),
                         sp.name))
                    if dst.player and src.player and dst.player != src.player:
                        dst.player.sendGameText(RPG_MSG_GAME_DENIED, "%s\\'s <a:Spell%s>%s</a> spell is supressed by <a:Spell%s>%s</a>!\\n" % (src.name,
                         GetTWikiName(proto.name),
                         proto.name,
                         GetTWikiName(sp.name),
                         sp.name))
                    self.cancel()
                    return
                cancel.append(process)

        for p in cancel:
            p.cancel()

        if proto.beginMsg and not dst.battle and not self.fromStore:
            GameMessage(RPG_MSG_GAME_SPELLBEGIN, src.zone, src, dst, proto.beginMsg + '\\n', src.simObject.position, 20)
        for ep in eprotos:
            effect = Effect(self, src, dst, ep, time, self.mod, self.fromStore, self.healMod, self.damageMod)
            self.effects.append(effect)

        Process.begin(self)
        for e in self.effects:
            e.begin()

        if self.time == 0:
            doEffects = True
            if src.player:
                if sysTime() - src.player.spellEffectBeginTime < 5:
                    doEffects = False
                else:
                    src.player.spellEffectBeginTime = sysTime()
            hasTP = self.hasTeleport()
            zone = self.src.zone
            if proto.afxSpellEffectBegin and not hasTP and self.doParticles and doEffects:
                zone.simAvatar.mind.callRemote('newSpellEffect', self.dst.simObject.id, proto.afxSpellEffectBegin, False)
            if proto.explosionBegin and not hasTP and self.doParticles and doEffects:
                zone.simAvatar.mind.callRemote('spawnExplosion', self.dst.simObject.id, proto.explosionBegin, 0)
            if proto.particleBegin and not hasTP and self.doParticles and doEffects:
                t = 3000
                zone.simAvatar.mind.callRemote('newParticleSystem', self.dst.simObject.id, 'SpellBeginEmitter', proto.particleTextureBegin, t)
            if proto.sndBegin and not hasTP and self.doParticles:
                if not proto.sndBeginDuration:
                    self.dst.playSound(proto.sndBegin)
        return True

    def tick(self):
        proto = self.spellProto
        while True:
            if proto.duration == 0:
                yield True
            if self.time >= proto.duration:
                return
            self.time += 3
            for e in self.effects:
                e.iter.next()

            yield True

    def end(self):
        proto = self.spellProto
        src = self.src
        dst = self.dst
        for e in self.effects:
            e.end()

        if proto.endMsg and not dst.battle:
            GameMessage(RPG_MSG_GAME_SPELLEND, src.zone, src, dst, proto.endMsg + '\\n', dst.simObject.position, 0)
        self.globalPop()

    def takeOwnership(self, newOwner):
        self.src = newOwner
        for e in self.effects:
            e.takeOwnership(newOwner)

    def cancel(self):
        if self.canceled:
            return
        else:
            self.canceled = True
            self.iter = None
            for e in self.effects:
                e.cancel()

            self.globalPop()
            return

    def globalPop(self):
        for e in self.effects:
            e.globalPop()

        Process.globalPop(self)

    def grantsFlying(self):
        for e in self.effects:
            for st in e.effectProto.stats:
                if st.stage == RPG_EFFECT_STAGE_GLOBAL:
                    if st.statname == 'flying' and st.value > 0:
                        return True

        return False

    def grantsInvisibility(self):
        for e in self.effects:
            for st in e.effectProto.stats:
                if st.stage == RPG_EFFECT_STAGE_GLOBAL:
                    if st.statname == 'visibility' and st.value < 0:
                        return True

        return False

    def hasTeleport(self):
        for e in self.effects:
            if e.effectProto.teleport:
                return True

        return False

    def hasSleep(self):
        for e in self.effects:
            for st in e.effectProto.stats:
                if st.stage == RPG_EFFECT_STAGE_GLOBAL:
                    if st.statname == 'sleep':
                        return True

        return False


def CheckResist(src, dst, proto, skill = None):
    R = max(1, int(floor(GetLevelSpread(src, dst) * 100)))
    if randint(0, R) > 90:
        if src.player:
            if skill:
                src.player.sendGameText(RPG_MSG_GAME_DENIED, "$src's <a:Skill%s>%s</a> skill has been resisted!\\n" % (GetTWikiName(skill), skill), src)
            else:
                src.player.sendGameText(RPG_MSG_GAME_DENIED, "$src's <a:Spell%s>%s</a> spell has been resisted!\\n" % (GetTWikiName(proto.name), proto.name), src)
        if dst.player and not skill:
            dst.player.sendGameText(RPG_MSG_GAME_DENIED, "$src resisted %s's <a:Spell%s>%s</a> spell!\\n" % (src.name, GetTWikiName(proto.name), proto.name), dst)
        return True
    return False


def SpawnSpell(proto, src, dst, pos = (0, 0, 0), mod = 1.0, skill = None, spellLevel = 1, proc = False):
    if src.detached or dst.detached:
        return
    else:
        dstSimObject = dst.simObject
        simObjects = []
        if proto.aoeRange:
            simLookup = src.zone.simAvatar.simLookup
            for id in dstSimObject.canSee:
                try:
                    simObject = simLookup[id]
                    simObjects.append((simObject, simObject.position[:]))
                except KeyError:
                    continue

            simObjects.append((dstSimObject, pos))
        if proto.spellType & RPG_SPELL_HARMFUL:
            if src.character:
                src.cancelStatProcess('invulnerable', '$tgt is no longer protected from death!\\n')
            if not proto.aoeRange:
                if not src.player:
                    if not IsKOS(src, dst):
                        return
                elif not AllowHarmful(src, dst):
                    if skill:
                        src.player.sendGameText(RPG_MSG_GAME_DENIED, "$src's <a:Skill%s>%s</a> skill failed, no valid target.\\n" % (GetTWikiName(skill), skill), src)
                    else:
                        src.player.sendGameText(RPG_MSG_GAME_DENIED, "$src's <a:Spell%s>%s</a> spell failed, no valid target.\\n" % (GetTWikiName(proto.name), proto.name), src)
                    return
        srcPlayer = None
        if src.player:
            srcPlayer = src.player
        elif src.master and src.master.player:
            srcPlayer = src.master.player
        castRange = proto.castRange
        if proto.skillname:
            try:
                slevel = src.skillLevels[proto.skillname]
                diff = slevel - (proto.level - 2) * 10
                if diff > 0:
                    if diff > 20:
                        diff = 20
                    castRange += castRange * 0.2 * float(diff) / 20.0
            except KeyError:
                pass

        if proto.target == RPG_TARGET_OTHER:
            if src.player and dst.player != src.player and dstSimObject.id not in src.simObject.canSee:
                if skill:
                    srcPlayer.sendGameText(RPG_MSG_GAME_DENIED, "<a:Skill%s>%s</a> failed, $src can't see the skill target!\\n" % (GetTWikiName(skill), skill), src)
                else:
                    srcPlayer.sendGameText(RPG_MSG_GAME_DENIED, "<a:Spell%s>%s</a> failed, $src can't see the spell target!\\n" % (GetTWikiName(proto.name), proto.name), src)
                return
            if GetRangeMin(src, dst) > castRange:
                if src.player:
                    if skill:
                        srcPlayer.sendGameText(RPG_MSG_GAME_DENIED, "$src's target is out of range for the <a:Skill%s>%s</a> skill!\\n" % (GetTWikiName(skill), skill), src)
                    else:
                        srcPlayer.sendGameText(RPG_MSG_GAME_DENIED, "$src's target is out of range for the <a:Spell%s>%s</a> spell!\\n" % (GetTWikiName(proto.name), proto.name), src)
                return
        if proto.spellType & RPG_SPELL_HARMFUL and dst != src and not proto.aoeRange:
            if not proto.spellType & RPG_SPELL_NOAGGRO:
                dst.addAggro(src, 10)
            if CheckResist(src, dst, proto, skill):
                return
            if src.player and not skill and not proc:
                crit = src.skillLevels.get('Spell Critical')
                if crit:
                    if not randint(0, 5):
                        r = randint(0, 100)
                        if r >= 95:
                            icrit = 3
                        elif r >= 75:
                            icrit = 2
                        else:
                            icrit = 1
                        crit = ceil(crit / 250) - 1
                        if crit < 1:
                            crit = 1
                        if icrit > crit:
                            icrit = crit
                        if src.player:
                            srcPlayer.sendGameText(RPG_MSG_GAME_WHITE, '%s lands a spell critical! (%ix)\\n' % (src.name, icrit + 1))
                        mod += icrit
                        if src.character:
                            src.character.checkSkillRaise('Spell Critical', 1, 2)
        myclasses = ((src.spawn.pclassInternal, src.plevel), (src.spawn.sclassInternal, src.slevel), (src.spawn.tclassInternal, src.tlevel))
        best = 0
        chLevel = 0
        for pcl in proto.classes:
            for c, level in myclasses:
                if not c or not level:
                    continue
                if c == pcl.classname and level >= pcl.level:
                    r = level - pcl.level
                    if r > best:
                        best = r
                        chLevel = level

        if best:
            if best > 10:
                best = 10
            mod += float(best) * 0.1 * 0.5
        try:
            if src.character and proto.skillname:
                src.character.checkSkillRaise('Concentration', 2, 10)
                try:
                    slevel = src.skillLevels[proto.skillname]
                    diff = slevel - (chLevel - 2) * 10
                    if diff >= 0:
                        if diff > 20:
                            src.character.checkSkillRaise(proto.skillname, 39, 39)
                        else:
                            sel = float(diff) / 20.0
                            sel = int(round(36.0 * sel * (2 - sel))) + 3
                            src.character.checkSkillRaise(proto.skillname, sel, sel)
                    else:
                        src.character.checkSkillRaise(proto.skillname)
                except KeyError:
                    pass

        except:
            traceback.print_exc()

        if proto.aoeRange:
            squaredAoeRange = proto.aoeRange * proto.aoeRange
            mobLookup = src.zone.mobLookup
            validTarget = False
            isHarmful = proto.spellType & RPG_SPELL_HARMFUL
            isAggro = not proto.spellType & RPG_SPELL_NOAGGRO
            if srcPlayer:
                srcEncounterSetting = newEncounterSetting = srcPlayer.encounterSetting
            for simObject, cachedPosition in simObjects:
                try:
                    mobInSight = mobLookup[simObject]
                except KeyError:
                    continue

                dX = cachedPosition[0] - pos[0]
                dY = cachedPosition[1] - pos[1]
                dZ = cachedPosition[2] - pos[2]
                if squaredAoeRange >= dX * dX + dY * dY + dZ * dZ:
                    if not mobInSight.player:
                        mobsInRange = [mobInSight]
                    else:
                        mobsInRange = (character.mob for character in mobInSight.player.party.members if character.mob)
                    for mob in mobsInRange:
                        if not mob.detached:
                            if isHarmful:
                                if not src.player:
                                    if not IsKOS(src, mob):
                                        continue
                                else:
                                    if not AllowHarmful(src, mob):
                                        continue
                                    if dst != mob and (not mob.master or mob.master != dst):
                                        testMob = mob if not mob.master else mob.master
                                        if not testMob.player:
                                            if not IsKOS(mob, src):
                                                continue
                                        elif src.level - testMob.level > 10:
                                            continue
                            elif srcPlayer:
                                dstMob = mob if not mob.master else mob.master
                                if srcPlayer != dstMob.player:
                                    dstEncounterSetting = dstMob.player.encounterSetting
                                    if dstEncounterSetting > srcEncounterSetting:
                                        if dst != dstMob and src.level - dstMob.level > 10:
                                            continue
                                        if dstEncounterSetting > newEncounterSetting:
                                            dstEncounterSetting = newEncounterSetting
                            validTarget = True
                            if isHarmful:
                                if isAggro:
                                    mob.addAggro(src, 10)
                                if not CheckResist(src, mob, proto, skill):
                                    src.processesPending.add(Spell(src, mob, proto, mod, 0, skill, proc=proc))
                            else:
                                src.processesPending.add(Spell(src, mob, proto, mod, 0, skill, proc=proc))

            if srcPlayer:
                if not validTarget:
                    if skill:
                        srcPlayer.sendGameText(RPG_MSG_GAME_DENIED, "$src's <a:Skill%s>%s</a> failed, there was no valid target in range!\\n" % (GetTWikiName(skill), skill), src)
                    else:
                        srcPlayer.sendGameText(RPG_MSG_GAME_DENIED, "$src's <a:Spell%s>%s</a> failed, there was no valid target in range!\\n" % (GetTWikiName(proto.name), proto.name), src)
                elif newEncounterSetting > srcEncounterSetting:
                    srcPlayer.applyEncounterSetting(newEncounterSetting, True)
            return
        if proto.target == RPG_TARGET_PARTY or proto.target == RPG_TARGET_ALLIANCE:
            if src.player and srcPlayer.alliance:
                for p in srcPlayer.alliance.members:
                    doParticles = True
                    passed = False
                    if p.encounterSetting > srcPlayer.encounterSetting:
                        srcPlayer.applyEncounterSetting(p.encounterSetting, True)
                    for c in p.party.members:
                        if not c.mob or c.mob.detached:
                            continue
                        if not passed:
                            if c.mob.zone == src.zone and GetRangeMin(c.mob, src) <= castRange:
                                passed = True
                            else:
                                break
                        src.processesPending.add(Spell(src, c.mob, proto, mod, 0, skill, doParticles, False, spellLevel, proc=proc))
                        doParticles = False

            elif src.player:
                doParticles = True
                for c in srcPlayer.party.members:
                    if not c.mob or c.mob.detached:
                        continue
                    src.processesPending.add(Spell(src, c.mob, proto, mod, 0, skill, doParticles, False, spellLevel, proc=proc))
                    doParticles = False

            else:
                src.processesPending.add(Spell(src, src, proto, mod, 0, skill, True, False, spellLevel, proc=proc))
            return
        if srcPlayer and not proto.spellType & RPG_SPELL_HARMFUL:
            dstPlayer = None
            if dst.player:
                dstPlayer = dst.player
            elif dst.master and dst.master.player:
                dstPlayer = dst.master.player
            if dstPlayer and dstPlayer.encounterSetting > srcPlayer.encounterSetting:
                srcPlayer.applyEncounterSetting(dstPlayer.encounterSetting, True)
        src.processesPending.add(Spell(src, dst, proto, mod, 0, skill, True, False, spellLevel, proc=proc))
        return


class SpellCasting():

    def __init__(self, mob, spellProto, level = 1):
        self.mob = mob
        self.spellProto = spellProto
        haste = 1.0
        haste -= mob.castHaste
        if level != 1:
            haste -= level / 10.0 * 0.25
        if spellProto.skillname:
            try:
                slevel = mob.skillLevels[spellProto.skillname]
                diff = slevel - (spellProto.level - 2) * 10
                if diff > 0:
                    if diff > 20:
                        diff = 20
                    haste -= 0.1 * float(diff) / 20.0
            except KeyError:
                pass

        if haste > 2.0:
            haste = 2.0
        if haste < 0.25:
            haste = 0.25
        self.timer = spellProto.castTime * haste
        self.failed = False
        self.failedTime = 0
        self.level = level

    def begin(self):
        mob = self.mob
        if not mob.simObject:
            return False
        else:
            player = mob.player
            proto = self.spellProto
            if self.spellProto in mob.recastTimers:
                return False
            if 0 < mob.sleep or 0 < mob.stun or mob.isFeared or 0 < mob.suppressCasting:
                if player:
                    player.sendGameText(RPG_MSG_GAME_DENIED, "$src\\'s casting failed $srche is in no condition to cast a spell!\\n", mob)
                return False
            self.manaCost = proto.manaCost
            if self.level != 1:
                self.manaCost += self.level / 10.0 * 0.35
            if proto.skillname:
                try:
                    slevel = mob.skillLevels[proto.skillname]
                    diff = slevel - (proto.level - 2) * 10
                    if diff > 0:
                        if diff > 20:
                            diff = 20
                        self.manaCost -= int(round(self.manaCost * 0.1 * float(diff) / 20.0))
                except KeyError:
                    pass

            if proto.target == RPG_TARGET_PET and not mob.pet:
                if player:
                    player.sendGameText(RPG_MSG_GAME_DENIED, "$src's casting of <a:Spell%s>%s</a> failed, $src has no pet.\\n" % (GetTWikiName(proto.name), proto.name), mob)
                return False
            filterTimeBegin = proto.filterTimeStart
            filterTimeEnd = proto.filterTimeEnd
            if filterTimeBegin != -1 and filterTimeEnd != -1:
                time = mob.zone.time
                passed = False
                if filterTimeEnd < filterTimeBegin:
                    if 24 >= time.hour >= filterTimeBegin or filterTimeEnd > time.hour >= 0:
                        passed = True
                elif filterTimeEnd > time.hour >= filterTimeBegin:
                    passed = True
                if not passed:
                    if player:
                        player.sendGameText(RPG_MSG_GAME_DENIED, "$src's casting failed, the <a:Spell%s>%s</a> spell does not work at this time of day.\\n" % (GetTWikiName(proto.name), proto.name), mob)
                    return False
            if mob.mana < self.manaCost:
                if player:
                    player.sendGameText(RPG_MSG_GAME_DENIED, "$src's casting of <a:Spell%s>%s</a> failed, not enough mana.\\n" % (GetTWikiName(proto.name), proto.name), mob)
                else:
                    traceback.print_stack()
                    print 'AssertionError: ai mobs should check mana before cast!'
                return False
            if player:
                if len(proto.components):
                    components = defaultdict(int)
                    for c in proto.components:
                        if c.count > 0:
                            components[c.itemProto] += c.count

                    if not player.checkItems(components.copy(), True):
                        player.sendGameText(RPG_MSG_GAME_DENIED, '$src lacks the spell components to cast <a:Spell%s>%s</a>,\\n$srche needs: %s\\n' % (GetTWikiName(proto.name), proto.name, ', '.join(('<a:Item%s>%i %s</a>' % (GetTWikiName(ip.name), c, ip.name) for ip, c in components.iteritems()))), mob)
                        return False
            if proto.recastTime:
                mob.recastTimers[proto] = proto.recastTime
            doEffects = True
            if player:
                if sysTime() - player.spellEffectCastTime < 5:
                    doEffects = False
                else:
                    player.spellEffectCastTime = sysTime()
            mob.cancelInvisibility()
            mob.cancelFlying()
            mob.cancelStatProcess('feignDeath', '$tgt is obviously not dead!\\n')
            mob.cancelStatProcess('sneak', '$tgt is no longer sneaking!\\n')
            if player:
                player.mind.callRemote('disturbEncounterSetting')
            zone = self.mob.zone
            if doEffects:
                t = self.timer / 6
                t *= 1000
                if proto.particleCasting:
                    zone.simAvatar.mind.callRemote('newParticleSystem', mob.simObject.id, 'CastingEmitter', proto.particleTextureCasting, t)
                if proto.sndCasting:
                    zone.simAvatar.mind.callRemote('newAudioEmitterLoop', mob.simObject.id, proto.sndCasting, t)
                if proto.afxSpellEffectCasting:
                    zone.simAvatar.mind.callRemote('newSpellEffect', mob.simObject.id, proto.afxSpellEffectCasting)
            zone.simAvatar.mind.callRemote('casting', mob.simObject.id, True)
            if proto.castingMsg:
                msg = proto.castingMsg
                msg = msg.replace('$src', mob.name) + '\\n'
            else:
                msg = '%s begins casting a spell.\\n' % mob.name
            if not mob.battle:
                if player:
                    GameMessage(RPG_MSG_GAME_CASTING, mob.zone, mob, None, msg, mob.simObject.position, range=30)
                else:
                    GameMessage(RPG_MSG_GAME_CASTING_NPC, mob.zone, mob, None, msg, mob.simObject.position, range=30)
            return True

    def tick(self):
        mob = self.mob
        player = mob.player
        if self.timer <= 0:
            proto = self.spellProto
            componentsConsumed = None
            if player:
                if len(proto.components):
                    componentsConsumed = defaultdict(int)
                    for c in proto.components:
                        if c.count > 0:
                            componentsConsumed[c.itemProto] += c.count

                    if not player.checkItems(componentsConsumed.copy(), True):
                        player.sendGameText(RPG_MSG_GAME_DENIED, '$src lacks the spell components to cast <a:Spell%s>%s</a>,\\n$srche needs: %s\\n' % (GetTWikiName(proto.name), proto.name, ', '.join(('<a:Item%s>%i %s</a>' % (GetTWikiName(ip.name), c, ip.name) for ip, c in componentsConsumed.iteritems()))), mob)
                        if proto.recastTime and proto in mob.recastTimers:
                            player.cinfoDirty = True
                            del mob.recastTimers[proto]
                        mob.zone.simAvatar.mind.callRemote('casting', mob.simObject.id, False)
                        return True
            if proto.target == RPG_TARGET_PET and not mob.pet:
                mob.zone.simAvatar.mind.callRemote('casting', mob.simObject.id, False)
                if player:
                    player.sendGameText(RPG_MSG_GAME_DENIED, "$src's casting of <a:Spell%s>%s</a> failed, $src has no pet.\\n" % (GetTWikiName(proto.name), proto.name), mob)
                if proto.recastTime and proto in mob.recastTimers:
                    if player:
                        player.cinfoDirty = True
                    del mob.recastTimers[proto]
                return True
            if mob.spellTarget:
                tgt = mob.spellTarget
                mob.spellTarget = None
            else:
                tgt = mob.target
            if tgt and tgt == mob.pet and proto.target == RPG_TARGET_OTHER:
                tgt = mob
            if proto.target in (RPG_TARGET_SELF, RPG_TARGET_PARTY, RPG_TARGET_ALLIANCE):
                tgt = mob
            elif proto.target == RPG_TARGET_PET:
                tgt = mob.pet
            elif player and proto.target == RPG_TARGET_OTHER and proto.spellType & RPG_SPELL_HEALING:
                tgt = GetPlayerHealingTarget(mob, tgt, proto)
            if not proto.spellType & RPG_SPELL_HARMFUL and tgt != mob and tgt != mob.pet:
                if not tgt or all([player or mob.master and mob.master.player, tgt.player or tgt.master and tgt.master.player, AllowHarmful(mob, tgt)]):
                    kos = True
                else:
                    kos = IsKOS(tgt, mob)
                if kos:
                    tgt = mob
            if not tgt:
                if player:
                    if proto.spellType & RPG_SPELL_HARMFUL:
                        from mud.world.command import CmdTargetNearest
                        CmdTargetNearest(mob, None, False, True)
                        tgt = mob.target
                    else:
                        tgt = mob
                if not tgt:
                    mob.zone.simAvatar.mind.callRemote('casting', mob.simObject.id, False)
                    if player:
                        player.sendGameText(RPG_MSG_GAME_DENIED, "%s\\'s casting failed, no target.\\n" % mob.name)
                    if proto.recastTime and proto in mob.recastTimers:
                        if player:
                            player.cinfoDirty = True
                        del mob.recastTimers[proto]
                    return True
            if proto.spellType & RPG_SPELL_HARMFUL:
                if not proto.aoeRange and not AllowHarmful(mob, tgt):
                    if player:
                        player.sendGameText(RPG_MSG_GAME_DENIED, "%s\\'s casting failed, cannot cast a harmful spell on this target.\\n" % mob.name)
                    if proto.recastTime and proto in mob.recastTimers:
                        if player:
                            player.cinfoDirty = True
                        del mob.recastTimers[proto]
                    mob.zone.simAvatar.mind.callRemote('casting', mob.simObject.id, False)
                    return True
            if proto.target == RPG_TARGET_OTHER:
                dist = GetRangeMin(mob, tgt)
                castRange = proto.castRange
                if proto.skillname:
                    try:
                        slevel = mob.skillLevels[proto.skillname]
                        diff = slevel - (proto.level - 2) * 10
                        if diff > 0:
                            if diff > 20:
                                diff = 20
                            castRange += castRange * 0.2 * float(diff) / 20.0
                    except KeyError:
                        pass

                if dist > castRange:
                    if player:
                        player.sendGameText(RPG_MSG_GAME_DENIED, "%s\\'s target is out of range for this spell!\\n" % mob.name)
                    mob.zone.simAvatar.mind.callRemote('casting', mob.simObject.id, False)
                    return True
                if tgt.simObject.id not in mob.simObject.canSee:
                    if player and tgt.player != player:
                        player.sendGameText(RPG_MSG_GAME_DENIED, "%s can\\'t see the spell target!\\n" % mob.name)
                        mob.zone.simAvatar.mind.callRemote('casting', mob.simObject.id, False)
                        return True
            if componentsConsumed != None and player:
                player.takeItems(componentsConsumed)
            if proto.animOverride:
                mob.zone.simAvatar.mind.callRemote('playAnimation', mob.simObject.id, proto.animOverride)
            if len(proto.particleNodes):
                mob.zone.simAvatar.mind.callRemote('triggerParticleNodes', mob.simObject.id, proto.particleNodes)
            if proto.recastTime:
                mob.recastTimers[proto] = proto.recastTime
            mob.mana -= self.manaCost
            if proto.projectile:
                mob.zone.simAvatar.mind.callRemote('cast', mob.simObject.id, True)
                p = Projectile(mob, tgt, self.level)
                p.spellProto = proto
                p.launch()
                if proto.sndBegin:
                    mob.playSound(proto.sndBegin)
            else:
                mob.zone.simAvatar.mind.callRemote('cast', mob.simObject.id)
                if proto.sndBeginDuration:
                    t = proto.sndBeginDuration / 6
                    t *= 1000
                    mob.zone.simAvatar.mind.callRemote('newAudioEmitterLoop', mob.simObject.id, proto.sndBegin, t)
                mod = 1.0
                if self.level != 1.0:
                    mod += self.level / 10.0 * 0.5
                SpawnSpell(proto, mob, tgt, tgt.simObject.position, mod, None, self.level)
            return True
        else:
            return False

    def cancel(self):
        mob = self.mob
        mob.zone.simAvatar.mind.callRemote('casting', mob.simObject.id, False, True)
        mob.casting = None
        if self.spellProto.recastTime and self.spellProto in mob.recastTimers:
            if mob.player:
                mob.player.cinfoDirty = True
            del mob.recastTimers[self.spellProto]
        return