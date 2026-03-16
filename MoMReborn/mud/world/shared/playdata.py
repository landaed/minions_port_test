# Embedded file name: mud\world\shared\playdata.pyo
from twisted.spread import pb
from math import floor, ceil
from mud.world.defines import *
from mud.world.core import *
import traceback
from operator import attrgetter
from itertools import imap
DIRTY = False

def IsDirty():
    global DIRTY
    if DIRTY:
        DIRTY = False
        return True
    return False


ADVANCEMENTS_DIRTY = False

def AdvancementsDirty():
    global ADVANCEMENTS_DIRTY
    if ADVANCEMENTS_DIRTY:
        ADVANCEMENTS_DIRTY = False
        return True
    return False


TACTICAL_DIRTY = False

def IsTacticalDirty():
    global TACTICAL_DIRTY
    if TACTICAL_DIRTY:
        TACTICAL_DIRTY = False
        return True
    return False


SKILLS_DIRTY = []

def AreSkillsDirty(cinfo):
    global SKILLS_DIRTY
    d = cinfo in SKILLS_DIRTY
    SKILLS_DIRTY = []
    return d


class RootInfo(pb.Cacheable):

    def __init__(self, player, charInfos):
        self.observers = []
        self.state = None
        self.player = player
        self.charInfos = charInfos
        self.forceBankUpdate = False
        return

    def stoppedObserving(self, perspective, observer):
        self.observers.remove(observer)

    def getStateToCacheAndObserveFor(self, perspective, observer):
        self.observers.append(observer)
        state = self.state = {}
        player = self.player
        state['PLAYERNAME'] = player.name
        state['CHARINFOS'] = self.charInfos
        tin = long(player.tin)
        tin += player.copper * 100L
        tin += player.silver * 10000L
        tin += player.gold * 1000000L
        tin += player.platinum * 100000000L
        state['TIN'] = tin
        state['PAUSED'] = False
        state['GUILDNAME'] = player.guildName
        state['BANK'] = dict(((slot, item.itemInfo) for slot, item in player.bankItems.iteritems()))
        try:
            state['POSITION'] = player.simObject.position
        except:
            state['POSITION'] = (0, 0, 0)

        return state

    def tick(self):
        if not self.state:
            return
        else:
            for v in self.charInfos.itervalues():
                rmi = getattr(v, 'rapidMobInfo', None)
                if rmi:
                    rmi.tick()

            changed = {}
            state = self.state
            player = self.player
            if player.world.paused != state['PAUSED']:
                changed['PAUSED'] = state['PAUSED'] = player.world.paused
            if state['GUILDNAME'] != player.guildName:
                changed['GUILDNAME'] = state['GUILDNAME'] = player.guildName
            tin = long(player.tin)
            tin += player.copper * 100L
            tin += player.silver * 10000L
            tin += player.gold * 1000000L
            tin += player.platinum * 100000000L
            if state['TIN'] != tin:
                changed['TIN'] = state['TIN'] = tin
            bank = dict(((slot, item.itemInfo) for slot, item in player.bankItems.iteritems()))
            if self.forceBankUpdate or state['BANK'] != bank:
                changed['BANK'] = state['BANK'] = bank
                self.forceBankUpdate = False
            position = player.simObject.position
            if state['POSITION'] != position:
                changed['POSITION'] = state['POSITION'] = position
            if len(changed):
                for o in self.observers:
                    d = o.callRemote('updateChanged', changed)
                    d.addErrback(lambda e: None)

            return


class RootInfoGhost(pb.RemoteCache):

    def __init__(self):
        from tgenative import TGEObject
        self.tomeGui = TGEObject('TomeGui_Window')

    def setCopyableState(self, state):
        self.__dict__.update(state)
        self.bankDirty = True
        guildname = state.get('GUILDNAME')
        if guildname:
            self.tomeGui.setText('< %s >' % guildname)
        else:
            self.tomeGui.setText('Tome')

    def observe_updateChanged(self, changed):
        self.__dict__.update(changed)
        if 'BANK' in changed:
            self.bankDirty = True
        guildname = changed.get('GUILDNAME', -1)
        if guildname != -1:
            if guildname:
                self.tomeGui.setText('< %s >' % guildname)
            else:
                self.tomeGui.setText('Tome')

    def checkMoney(self, worth):
        if self.TIN >= worth:
            return True
        return False


pb.setUnjellyableForClass(RootInfo, RootInfoGhost)

class RapidMobInfo(pb.Cacheable):

    def __init__(self, mob):
        self.observers = []
        self.state = None
        self.mob = mob
        return

    def stoppedObserving(self, perspective, observer):
        self.observers.remove(observer)

    def getStateToCacheAndObserveFor(self, perspective, observer):
        self.observers.append(observer)
        if self.state:
            return self.state
        else:
            state = self.state = {}
            mob = self.mob
            state['HEALTH'] = float(mob.health)
            state['MAXHEALTH'] = float(mob.maxHealth)
            state['MANA'] = float(mob.mana)
            state['MAXMANA'] = float(mob.maxMana)
            state['STAMINA'] = float(mob.stamina)
            state['MAXSTAMINA'] = float(mob.maxStamina)
            targetdMob = mob.target
            if targetdMob:
                state['TGT'] = targetdMob.name
                state['TGTID'] = targetdMob.id
                state['TGTHEALTH'] = float(targetdMob.health) / float(targetdMob.maxHealth)
                state['TGTRACE'] = targetdMob.spawn.race
                state['TGTSEX'] = targetdMob.sex
            else:
                state['TGT'] = None
                state['TGTID'] = 0
                state['TGTHEALTH'] = -1
                state['TGTRACE'] = None
                state['TGTSEX'] = None
            if mob.pet:
                state['PETNAME'] = mob.pet.name
                state['PETHEALTH'] = float(mob.pet.health) / float(mob.pet.maxHealth)
                state['PETAGGRESSIVE'] = mob.pet.attacking
            else:
                state['PETNAME'] = None
                state['PETHEALTH'] = -1
                state['PETAGGRESSIVE'] = False
            state['AUTOATTACK'] = mob.autoAttack
            state['RANGEDREUSE'] = mob.rangedReuse
            state['CASTING'] = bool(mob.casting)
            return state

    def tick(self):
        changed = {}
        state = self.state
        mob = self.mob
        health = float(mob.health)
        if state['HEALTH'] != health:
            changed['HEALTH'] = state['HEALTH'] = health
        maxHealth = float(mob.maxHealth)
        if state['MAXHEALTH'] != maxHealth:
            changed['MAXHEALTH'] = state['MAXHEALTH'] = maxHealth
        mana = mob.mana
        if state['MANA'] != mana:
            changed['MANA'] = state['MANA'] = mana
        maxMana = mob.maxMana
        if state['MAXMANA'] != maxMana:
            changed['MAXMANA'] = state['MAXMANA'] = maxMana
        stamina = float(mob.stamina)
        if state['STAMINA'] != stamina:
            changed['STAMINA'] = state['STAMINA'] = stamina
        maxStamina = float(mob.maxStamina)
        if state['MAXSTAMINA'] != maxStamina:
            changed['MAXSTAMINA'] = state['MAXSTAMINA'] = maxStamina
        targetdMob = mob.target
        if targetdMob:
            tgt = targetdMob.name
            tgtid = targetdMob.id
            tgthealth = float(targetdMob.health) / float(targetdMob.maxHealth)
            tgtrace = targetdMob.spawn.race
            tgtsex = targetdMob.sex
        else:
            tgt = None
            tgtid = 0
            tgthealth = -1
            tgtrace = None
            tgtsex = None
        if mob.pet:
            petname = mob.pet.name
            pethealth = float(mob.pet.health) / float(mob.pet.maxHealth)
            petAggressive = mob.pet.attacking
        else:
            petname = None
            pethealth = -1
            petAggressive = False
        if state['TGT'] != tgt:
            changed['TGT'] = state['TGT'] = tgt
        if state['TGTID'] != tgtid:
            changed['TGTID'] = state['TGTID'] = tgtid
        if state['TGTHEALTH'] != tgthealth:
            changed['TGTHEALTH'] = state['TGTHEALTH'] = tgthealth
        if state['TGTRACE'] != tgtrace:
            changed['TGTRACE'] = state['TGTRACE'] = tgtrace
        if state['TGTSEX'] != tgtsex:
            changed['TGTSEX'] = state['TGTSEX'] = tgtsex
        if state['PETNAME'] != petname:
            changed['PETNAME'] = state['PETNAME'] = petname
        if state['PETHEALTH'] != pethealth:
            changed['PETHEALTH'] = state['PETHEALTH'] = pethealth
        if state['PETAGGRESSIVE'] != petAggressive:
            changed['PETAGGRESSIVE'] = state['PETAGGRESSIVE'] = petAggressive
        if state['AUTOATTACK'] != mob.autoAttack:
            changed['AUTOATTACK'] = state['AUTOATTACK'] = mob.autoAttack
        if state['RANGEDREUSE'] != mob.rangedReuse:
            changed['RANGEDREUSE'] = state['RANGEDREUSE'] = mob.rangedReuse
        casting = bool(mob.casting)
        if state['CASTING'] != casting:
            changed['CASTING'] = state['CASTING'] = casting
        if len(changed):
            for o in self.observers:
                o.callRemote('updateChanged', changed).addErrback(lambda e: None)

        return


class RapidMobInfoGhost(pb.RemoteCache):

    def setCopyableState(self, state):
        self.__dict__.update(state)

    def observe_updateChanged(self, changed):
        self.__dict__.update(changed)
        from mud.client.gui.partyWnd import PARTYWND
        from mud.client.gui.macro import MACROMASTER
        for charIndex, cinfo in PARTYWND.charInfos.iteritems():
            if cinfo.RAPIDMOBINFO == self:
                break

        encounterChanged = False
        if 'CASTING' in changed:
            PARTYWND.spellPane.setFromCharacterInfo(PARTYWND.charInfos[PARTYWND.curIndex])
            if changed['CASTING']:
                PARTYWND.encounterBlock += 1
            else:
                PARTYWND.encounterBlock -= 1
            encounterChanged = True
        if 'AUTOATTACK' in changed:
            if changed['AUTOATTACK']:
                PARTYWND.encounterBlock += 1
            else:
                PARTYWND.encounterBlock -= 1
            encounterChanged = True
            MACROMASTER.updateAttackMacros(charIndex, changed['AUTOATTACK'])
        if 'PETAGGRESSIVE' in changed:
            if changed['PETAGGRESSIVE']:
                PARTYWND.encounterBlock += 1
            else:
                PARTYWND.encounterBlock -= 1
            encounterChanged = True
        if encounterChanged:
            if PARTYWND.encounterBlock < 0:
                PARTYWND.encounterBlock = 0
            PARTYWND.encounterSettingDisturbed()
        if 'RANGEDREUSE' in changed:
            MACROMASTER.updateRangedAttackMacros(charIndex)


pb.setUnjellyableForClass(RapidMobInfo, RapidMobInfoGhost)

class ItemInfo(pb.Cacheable):
    keysDynamicHigh = {'PENALTY': 'penalty',
     'SLOT': 'slot',
     'REPAIR': 'repair',
     'REUSETIMER': 'reuseTimer',
     'USECHARGES': 'useCharges',
     'STACKCOUNT': 'stackCount'}
    keysDynamicLow = {'NAME': 'name',
     'ARMOR': 'armor',
     'STATS': 'stats',
     'FLAGS': 'flags',
     'LEVEL': 'level',
     'spellEnhanceLevel': 'spellEnhanceLevel',
     'WPNDAMAGE': 'wpnDamage',
     'WPNRATE': 'wpnRate',
     'RACEBANE': 'wpnRaceBane',
     'RACEMOD': 'wpnRaceBaneMod',
     'RESISTDEBUFF': 'wpnResistDebuff',
     'RESISTDEBUFFMOD': 'wpnResistDebuffMod',
     'DESC': 'descOverride'}

    def __init__(self, item):
        self.observers = []
        self.state = {}
        self.initialized = False
        self.item = item

    def getFullState(self):
        state = self.state
        self.initialized = True
        item = self.item
        state.update(((k, getattr(item, attr)) for k, attr in ItemInfo.keysDynamicHigh.iteritems()))
        state.update(((k, getattr(item, attr)) for k, attr in ItemInfo.keysDynamicLow.iteritems()))
        if item.character:
            state['OWNERCHARID'] = item.character.id
        else:
            state['OWNERCHARID'] = 0
        state['PROTOID'] = item.itemProto.id
        state['REPAIRMAX'] = item.repairMax
        state['BITMAP'] = item.bitmap
        state['WPNRANGE'] = item.wpnRange
        state['LIGHT'] = item.light
        state['QUALITY'] = item.quality
        state['WORTHINCREASETIN'] = item.worthIncreaseTin
        state['POISONS'] = []
        state['ENCHANTMENTS'] = []
        for proc, details in item.procs.iteritems():
            if details[1] == RPG_ITEMPROC_POISON:
                state['POISONS'].append(proc.spellProto.name)
            else:
                state['ENCHANTMENTS'].append(proc.spellProto.name)

        if item.container:
            state['CONTENT'] = [ ci.itemInfo for ci in item.container.content ]
            item.container.dirty = False

    def getStateToCacheAndObserveFor(self, perspective, observer):
        self.observers.append(observer)
        self.getFullState()
        return self.state

    def stoppedObserving(self, perspective, observer):
        self.observers.remove(observer)

    def reset(self):
        self.getFullState()
        for o in self.observers:
            o.callRemote('updateChanged', self.state).addErrback(lambda e: None)

    def refresh(self):
        if not self.initialized:
            self.getFullState()
            changed = self.state
        else:
            state = self.state
            changed = {}
            item = self.item
            for k, attr in ItemInfo.keysDynamicHigh.iteritems():
                v = getattr(item, attr)
                if state[k] != v:
                    state[k] = changed[k] = v

            if item.character:
                ownerid = item.character.id
            else:
                ownerid = 0
            if ownerid != state['OWNERCHARID']:
                state['OWNERCHARID'] = changed['OWNERCHARID'] = ownerid
            poisons = []
            enchantments = []
            for proc, details in item.procs.iteritems():
                if details[1] == RPG_ITEMPROC_POISON:
                    poisons.append(proc.spellProto.name)
                else:
                    enchantments.append(proc.spellProto.name)

            if poisons != state['POISONS']:
                state['POISONS'] = changed['POISONS'] = poisons
            if enchantments != state['ENCHANTMENTS']:
                state['ENCHANTMENTS'] = changed['ENCHANTMENTS'] = enchantments
            if item.container and item.container.dirty:
                state['CONTENT'] = changed['CONTENT'] = [ ci.itemInfo for ci in item.container.content ]
                item.container.dirty = False
        if len(changed):
            for o in self.observers:
                o.callRemote('updateChanged', changed).addErrback(lambda e: None)

    def refreshDict(self, selection):
        rm = []
        for k, v in selection.iteritems():
            try:
                if self.state[k] != v:
                    self.state[k] = v
                else:
                    rm.append(k)
            except KeyError:
                rm.append(k)
                traceback.print_exc()

        map(selection.__delitem__, rm)
        if len(selection):
            for o in self.observers:
                o.callRemote('updateChanged', selection).addErrback(lambda e: None)

    def refreshProcs(self):
        poisons = []
        enchantments = []
        for proc, details in self.item.procs.iteritems():
            if details[1] == RPG_ITEMPROC_POISON:
                poisons.append(proc.spellProto.name)
            else:
                enchantments.append(proc.spellProto.name)

        changed = {}
        if poisons != self.state['POISONS']:
            self.state['POISONS'] = changed['POISONS'] = poisons
        if enchantments != self.state['ENCHANTMENTS']:
            self.state['ENCHANTMENTS'] = changed['ENCHANTMENTS'] = enchantments
        if len(changed):
            for o in self.observers:
                o.callRemote('updateChanged', changed).addErrback(lambda e: None)

    def refreshContents(self):
        if self.item.container and self.item.container.dirty:
            changed = {}
            self.state['CONTENT'] = changed['CONTENT'] = [ ci.itemInfo for ci in self.item.container.content ]
            self.item.container.dirty = False
            for o in self.observers:
                o.callRemote('updateChanged', changed).addErrback(lambda e: None)


STAT_PRETTY = dict(([stat.upper(), (stat, False)] for stat in RPG_STATS))
STAT_PRETTY['MAXHEALTH'] = ('Health', False)
STAT_PRETTY['HEALTH'] = ('Health', False)
STAT_PRETTY['MAXSTAMINA'] = ('Stamina', False)
STAT_PRETTY['STAMINA'] = ('Stamina', False)
STAT_PRETTY['MAXMANA'] = ('Mana', False)
STAT_PRETTY['PRE'] = ('Presence', False)
STAT_PRETTY['REGENHEALTH'] = ('Regeneration', False)
STAT_PRETTY['REGENSTAMINA'] = ('Revitalization', False)
STAT_PRETTY['REGENMANA'] = ('Mana Regen', False)
STAT_PRETTY['REGENCOMBAT'] = ('Combat Regen', False)
STAT_PRETTY['DEFENSE'] = ('Defense', False)
STAT_PRETTY['OFFENSE'] = ('Offense', False)
STAT_PRETTY['ARMOR'] = ('Armor', False)
STAT_PRETTY['AGGRORANGE'] = ('Aggro Range', False)
STAT_PRETTY['HASTE'] = ('Melee Haste', True)
STAT_PRETTY['CASTHASTE'] = ('Casting Haste', True)
STAT_PRETTY['MOVE'] = ('Movement', True)
STAT_PRETTY['CASTHEALMOD'] = ('Heal Mod', True)
STAT_PRETTY['CASTDMGMOD'] = ('Cast Dmg Mod', True)
STAT_PRETTY['CRITICAL'] = ('Critical', True)
STAT_PRETTY['VISIBILITY'] = ('Visibility', True)
STAT_PRETTY['SIZE'] = ('Size', True)
STAT_PRETTY['INNATEHASTE'] = ('Innate Haste', True)
STAT_PRETTY['MELEEDMGMOD'] = ('Melee Dmg Mod', True)

class ItemInfoGhost(pb.RemoteCache):

    def __init__(self):
        self.text = ''
        self.infoDirty = True

    def generateItemText(self):
        wpntext = []
        stattext = []
        if True:
            rtext = ['\\c3Resists:']
            for stat, value in self.STATS:
                if not value:
                    continue
                statupper = stat.upper()
                try:
                    prettyPrint, isPercent = STAT_PRETTY[statupper]
                    colorCode = 2 if value > 0 else 1
                    if isPercent:
                        stattext.append('\\c3%s \\c%i%i%%' % (prettyPrint, colorCode, value * 100))
                    else:
                        stattext.append('\\c3%s \\c%i%i' % (prettyPrint, colorCode, value))
                    continue
                except:
                    pass

                try:
                    prettyPrint = RPG_RESIST_TEXT[RPG_RESISTLOOKUP[stat]]
                    colorCode = 2 if value > 0 else 1
                    rtext.append('\\c3%s \\c%i%i' % (prettyPrint, colorCode, value))
                    continue
                except:
                    pass

                if stat == 'dmgBonusOffhand':
                    wpntext.append('\\c3%s \\c2%i' % ('Dmg Bonus(Offhand)', value))
                elif stat == 'dmgBonusPrimary':
                    wpntext.append('\\c3%s \\c2%i' % ('Dmg Bonus', value))
                else:
                    print 'Warning!  Item stat print style not defined: %s' % stat
                    stattext.append('\\c3%s \\c2%i' % (stat, value))

            if len(rtext) > 1:
                stattext.extend(rtext)
        text = []
        if self.LEVEL > 1:
            text.append('\\c3Recommended Level: \\c0%i' % self.LEVEL)
        if len(self.RACES):
            colorCode = 1 if self.REQFLAGS & RPG_ITEMREQUIREMENT_RACEREVERSED else 2
            text.append('\\c3Races: \\c%i%s' % (colorCode, ' '.join(self.RACES)))
        if len(self.REALMS):
            rtext = ['\\c3Realms:']
            for r, level in self.REALMS:
                if r == RPG_REALM_LIGHT and level <= 1:
                    rtext.append('\\c0FoL\\c3')
                elif r == RPG_REALM_DARKNESS and level <= 1:
                    rtext.append('\\c0MoD\\c3')
                elif r == RPG_REALM_MONSTER and level <= 1:
                    rtext.append('\\c0Monsters\\c3')
                elif r == RPG_REALM_LIGHT and level > 1:
                    rtext.append('\\c0FoL\\c3(\\c0%i\\c3)' % level)
                elif r == RPG_REALM_DARKNESS and level > 1:
                    rtext.append('\\c0MoD\\c3(\\c0%i\\c3)' % level)
                elif r == RPG_REALM_MONSTER and level > 1:
                    rtext.append('\\c0Monsters\\c3(\\c0%i\\c3)' % level)

            text.append(' '.join(rtext))
        if self.REQFLAGS & RPG_ITEMREQUIREMENT_EXACTCLASSNUM:
            if self.REQCLASSNUM == 1:
                text.append('\\c3Single Classed')
            elif self.REQCLASSNUM == 2:
                text.append('\\c3Double Classed')
            else:
                text.append('\\c3Triple Classed')
        if len(self.CLASSES):
            rtext = ['\\c3Classes:']
            if self.REQFLAGS & RPG_ITEMREQUIREMENT_CLASSREVERSED:
                colorCode = 1
            else:
                if self.REQCLASSNUM > 1:
                    rtext.append('\\c0Match %i Classes' % self.REQCLASSNUM)
                colorCode = 0
            for clName, level in self.CLASSES:
                rtext.append('\\c%i%s\\c3(\\c0%i\\c3)' % (colorCode, clName, level))

            text.append(' '.join(rtext))
        if self.PENALTY:
            text.append('\\c3Penalty: \\c1%i%%' % int(self.PENALTY * 100.0))
        if self.SKILL:
            text.append('\\c3Skill: \\c2%s' % self.SKILL)
        if len(self.SLOTS):
            text.append('\\c3Slots: \\c2%s' % ' \\c2'.join((RPG_SLOT_TEXT[slot] for slot in self.SLOTS)))
        if self.USEMAX and self.USECHARGES:
            text.append('\\c3Charges: \\c2%i' % self.USECHARGES)
        if self.RACEBANE:
            text.append('\\c3Bane: Offense \\c2+%i%% \\c3Damage \\c2+%i%% \\c3vs \\c0%s' % (int(RPG_BANEWEAPON_OFFENSE[self.RACEMOD] * 100.0), int(RPG_BANEWEAPON_DAMAGE[self.RACEMOD] * 100.0), self.RACEBANE))
        if self.RESISTDEBUFFMOD:
            text.append('\\c3Enemy Resists: \\c0%s \\c1-%i' % (RPG_RESIST_TEXT[self.RESISTDEBUFF], self.RESISTDEBUFFMOD))
        if self.WPNDAMAGE:
            text.append('\\c3Wpn Dmg/Delay: \\c3(\\c0%i\\c3/\\c0%i\\c3)' % (self.WPNDAMAGE, self.WPNRATE))
        if len(wpntext):
            text.append(' '.join(wpntext))
        if self.WPNRANGE:
            text.append('\\c3Range: \\c0%i' % self.WPNRANGE)
        if len(stattext):
            text.append(' '.join(stattext))
        if self.ARMOR:
            text.append('\\c3Armor: \\c0%i' % self.ARMOR)
        if self.LIGHT:
            text.append('\\c3Radiance: \\c0%i' % ceil(self.LIGHT))
        if self.REPAIRMAX:
            colorCode = 1 if self.REPAIR < self.REPAIRMAX else 0
            text.append('\\c3Repair: \\c%i%i\\c3/\\c0%i' % (colorCode, self.REPAIR, self.REPAIRMAX))
        if self.EFFECTDESC:
            text.append('\\c3Effect: \\c0%s' % self.EFFECTDESC)
        if self.DESC:
            text.append('\\n\\c0%s' % self.DESC)
        if len(self.POISONS):
            text.append('\\c3Active Poisons: \\c0%s' % ', '.join(self.POISONS))
        if len(self.ENCHANTMENTS):
            text.append('\\c3Active Enchantments: \\c0%s' % ', '.join(self.ENCHANTMENTS))
        self.text = '\\cp%s' % '\\n'.join(text)

    def setCopyableState(self, state):
        global DIRTY
        DIRTY = True
        self.infoDirty = True
        from mud.client.playermind import GetMoMClientDBConnection
        con = GetMoMClientDBConnection()
        self.__dict__.update(state)
        self.PROTONAME, self.SKILL, self.WEIGHT, self.STACKMAX, self.USEMAX, self.EFFECTDESC, basedesc, spID, self.STACKDEFAULT, self.WORTHTIN, self.REQFLAGS, self.REQCLASSNUM, containerProtoID = con.execute('SELECT name,skill,weight,stack_max,use_max,effect_desc,desc,spell_proto_id,stack_default,worth_tin,requirement_flags,required_class_num,item_container_proto_id FROM item_proto WHERE id = %i LIMIT 1;' % self.PROTOID).fetchone()
        self.SLOTS = tuple((s[0] for s in con.execute('SELECT slot FROM item_slot WHERE item_proto_id = %i;' % self.PROTOID)))
        self.ISPOISON = bool(con.execute('SELECT id FROM item_spell WHERE item_proto_id = %i AND trigger = %i LIMIT 1;' % (self.PROTOID, RPG_ITEM_TRIGGER_POISON)).fetchone())
        if not self.FLAGS and self.QUALITY != RPG_QUALITY_NORMAL and not spID and len(self.SLOTS) and not self.STACKMAX > 1:
            self.NAME = ' '.join((RPG_QUALITY_TEXT[self.QUALITY], self.NAME))
        self.SPELLINFO = None
        if spID:
            self.SPELLINFO = SpellInfoGhost(spID)
            if not self.DESC:
                self.DESC = self.SPELLINFO.DESC
        elif not self.DESC:
            self.DESC = basedesc
        self.CLASSES = [ (classname, level) for classname, level in con.execute('SELECT classname,level FROM item_class WHERE item_proto_id = %i;' % self.PROTOID) ]
        if spID:
            self.CLASSES.extend(self.SPELLINFO.CLASSES)
        self.CLASSES = tuple(self.CLASSES)
        self.RACES = tuple((item[0] for item in con.execute('SELECT racename FROM item_race WHERE item_proto_id = %i;' % self.PROTOID)))
        self.REALMS = tuple(((realmname, level) for realmname, level in con.execute('SELECT realmname,level FROM item_realm WHERE item_proto_id = %i;' % self.PROTOID)))
        if containerProtoID:
            self.CONTAINERSIZE = con.execute('SELECT container_size FROM item_container_proto WHERE id=%i LIMIT 1;' % containerProtoID).fetchone()[0]
        else:
            self.CONTAINERSIZE = 0
        self.generateItemText()
        return

    def getWorth(self, valueMod = 1.0, playerSelling = False):
        tin = self.WORTHTIN
        tin += self.WORTHINCREASETIN
        tin = floor(tin * RPG_QUALITY_MODS[self.QUALITY])
        tin = ceil(tin * valueMod)
        mod = 1.0
        if self.STACKCOUNT:
            if not self.STACKDEFAULT:
                mod = float(self.STACKCOUNT)
            else:
                mod = float(self.STACKCOUNT) / float(self.STACKDEFAULT)
        if playerSelling and self.FLAGS & RPG_ITEM_LITERATURE:
            mod /= 2.0
        if self.REPAIRMAX:
            diminish = 0.1 - 0.1 * float(self.REPAIR) / float(self.REPAIRMAX)
            mod -= mod * diminish
        tin = ceil(tin * mod)
        return long(tin)

    def isUseable(self, cinfo):
        if self.SKILL:
            if not cinfo.SKILLS.get(self.SKILL):
                return False
        if len(self.RACES):
            if self.REQFLAGS & RPG_ITEMREQUIREMENT_RACEREVERSED:
                if cinfo.RACE in self.RACES:
                    return False
            elif cinfo.RACE not in self.RACES:
                return False
        if len(self.REALMS):
            for r in self.REALMS:
                if cinfo.REALM == r[0]:
                    break
            else:
                return False

        if self.REQFLAGS & RPG_ITEMREQUIREMENT_EXACTCLASSNUM:
            classNum = (3 if cinfo.TCLASS else 2) if cinfo.SCLASS else 1
            if classNum != self.REQCLASSNUM:
                return False
        if len(self.CLASSES):
            if self.REQFLAGS & RPG_ITEMREQUIREMENT_CLASSREVERSED:
                for clName, level in self.CLASSES:
                    if cinfo.PCLASS == clName or cinfo.SCLASS == clName or cinfo.TCLASS == clName:
                        return False

            else:
                match = 0
                for clName, level in self.CLASSES:
                    if cinfo.PCLASS == clName:
                        if self.SPELLINFO:
                            if cinfo.PLEVEL < level:
                                continue
                        match += 1
                    elif cinfo.SCLASS == clName:
                        if self.SPELLINFO:
                            if cinfo.SLEVEL < level:
                                continue
                        match += 1
                    elif cinfo.TCLASS == clName:
                        if self.SPELLINFO:
                            if cinfo.TLEVEL < level:
                                continue
                        match += 1
                    if match >= self.REQCLASSNUM:
                        break
                else:
                    return False

        return True

    def observe_setState(self, state):
        self.infoDirty = True
        self.setCopyableState(state)

    def observe_updateChanged(self, changed):
        global DIRTY
        DIRTY = True
        self.infoDirty = True
        desc = changed.get('DESC', -1)
        if not desc:
            del changed['DESC']
        self.__dict__.update(changed)
        if changed.has_key('CONTENT'):
            from mud.client.gui.itemContainerWnd import ItemContainerWnd
            ItemContainerWnd = ItemContainerWnd.instance
            if ItemContainerWnd.container == self:
                ItemContainerWnd.openContainer(self)
        if changed.has_key('REUSETIMER'):
            from mud.client.gui.macro import MACROMASTER
            MACROMASTER.updateItemUsingMacros(self.NAME)
        self.generateItemText()


pb.setUnjellyableForClass(ItemInfo, ItemInfoGhost)

class SpellEffectInfo(pb.Copyable, pb.RemoteCopy):

    def __init__(self, spell = None):
        if spell:
            proto = spell.spellProto
            if not spell.skill:
                try:
                    self.NAME = ' '.join([proto.name, RPG_ROMAN[spell.level - 1]])
                except KeyError:
                    self.NAME = proto.name

            else:
                self.NAME = proto.name
            self.HARMFUL = proto.spellType & RPG_SPELL_HARMFUL
            self.ICONSRC = proto.iconSrc
            self.ICONDST = proto.iconDst
            self.SRCMOBID = spell.src.id
            self.DSTMOBID = spell.dst.id
            self.PID = spell.pid
            self.TIME = float(proto.duration) / 6.0 - float(spell.time) / 6.0


pb.setUnjellyableForClass(SpellEffectInfo, SpellEffectInfo)

class CharacterInfo(pb.Cacheable):
    spawnkeys = {'NAME': 'name',
     'RACE': 'race',
     'SEX': 'sex',
     'REALM': 'realm'}
    mobkeys = {'STRBASE': 'strBase',
     'DEXBASE': 'dexBase',
     'BDYBASE': 'bdyBase',
     'MNDBASE': 'mndBase',
     'WISBASE': 'wisBase',
     'AGIBASE': 'agiBase',
     'REFBASE': 'refBase',
     'MYSBASE': 'mysBase',
     'STR': 'str',
     'DEX': 'dex',
     'BDY': 'bdy',
     'MND': 'mnd',
     'WIS': 'wis',
     'AGI': 'agi',
     'REF': 'ref',
     'MYS': 'mys',
     'PRE': 'pre',
     'OFFENSE': 'offense',
     'DEFENSE': 'defense',
     'HEALTH': 'health',
     'ARMOR': 'armor'}

    def __init__(self, character):
        self.character = character
        self.state = {}
        self.observers = []

    def stoppedObserving(self, perspective, observer):
        self.observers.remove(observer)

    def getStateToCacheAndObserveFor(self, perspective, observer):
        self.observers.append(observer)
        state = self.state
        mob = self.character.mob
        spawn = mob.spawn
        for k, attr in CharacterInfo.spawnkeys.iteritems():
            state[k] = getattr(spawn, attr)

        for k, attr in CharacterInfo.mobkeys.iteritems():
            state[k] = getattr(mob, attr)

        self.rapidMobInfo = state['RAPIDMOBINFO'] = RapidMobInfo(mob)
        state['ADVANCEMENTS'] = [ (a.advancementProto.name, a.rank) for a in self.character.advancements ]
        state['PCLASS'] = spawn.pclassInternal
        state['SCLASS'] = spawn.sclassInternal
        state['TCLASS'] = spawn.tclassInternal
        state['PLEVEL'] = spawn.plevel
        state['SLEVEL'] = spawn.slevel
        state['TLEVEL'] = spawn.tlevel
        state['UNDERWATERRATIO'] = mob.underWaterRatio
        character = self.character
        state['SPAWNID'] = mob.spawn.id
        state['CHARID'] = character.id
        state['ADVANCE'] = character.advancementPoints
        state['MOBID'] = mob.id
        state['ITEMS'] = dict(((item.slot, item.itemInfo) for item in character.items))
        spells = {}
        for cspell in character.spells:
            if not cspell.spellInfo:
                cspell.spellInfo = CharSpellInfo(character, cspell)
            spells[cspell.slot] = cspell.spellInfo

        state['SPELLS'] = spells
        state['SKILLS'] = mob.skillLevels.copy()
        state['SKILLREUSE'] = dict(((key.upper(), 1) for key in mob.skillReuse.iterkeys()))
        state['PXPPERCENT'] = character.pxpPercent
        state['SXPPERCENT'] = character.sxpPercent
        state['TXPPERCENT'] = character.txpPercent
        state['PORTRAITPIC'] = character.portraitPic
        state['DEAD'] = character.dead
        if state.has_key('SPELLEFFECTS'):
            traceback.print_stack()
            print "AssertionError: CharacterInfo state got spell effects in dictionary and shouldn't!"
            return
        spelleffects = []
        from mud.world.spell import Spell
        processes = []
        processes.extend(mob.processesIn)
        processes.extend(mob.processesOut)
        for p in processes:
            if isinstance(p, Spell):
                if not p.spellProto.duration:
                    continue
                if not p.spellEffectInfo:
                    p.spellEffectInfo = SpellEffectInfo(p)
                if p.spellEffectInfo not in spelleffects:
                    spelleffects.append(p.spellEffectInfo)

        state['SPELLEFFECTS'] = spelleffects
        state['RESISTS'] = resists = []
        for resist in RPG_RESISTVALUES:
            r = mob.resists.get(resist, 0)
            if r:
                resists.append((resist, r))

        state['VAULTITEMS'] = [ (v.id, v.name, v.stackCount) for v in self.character.vaultItems ]
        return state

    def refreshLite(self, send = False):
        state = self.state
        mob = self.character.mob
        spawn = mob.spawn
        character = self.character
        changed = {}
        for k, attr in CharacterInfo.spawnkeys.iteritems():
            v = getattr(spawn, attr)
            if state[k] != v:
                changed[k] = v
                state[k] = v

        for k, attr in CharacterInfo.mobkeys.iteritems():
            v = getattr(mob, attr)
            if state[k] != v:
                changed[k] = v
                state[k] = v

        if state['UNDERWATERRATIO'] != mob.underWaterRatio:
            state['UNDERWATERRATIO'] = changed['UNDERWATERRATIO'] = mob.underWaterRatio
        if state['PXPPERCENT'] != character.pxpPercent:
            changed['PXPPERCENT'] = state['PXPPERCENT'] = character.pxpPercent
        if state['SXPPERCENT'] != character.sxpPercent:
            changed['SXPPERCENT'] = state['SXPPERCENT'] = character.sxpPercent
        if state['TXPPERCENT'] != character.txpPercent:
            changed['TXPPERCENT'] = state['TXPPERCENT'] = character.txpPercent
        resists = []
        for resist in RPG_RESISTVALUES:
            r = mob.resists.get(resist, 0)
            if r:
                resists.append((resist, r))

        if state['RESISTS'] != resists:
            changed['RESISTS'] = state['RESISTS'] = resists
        if send:
            if len(changed):
                for o in self.observers:
                    o.callRemote('updateChanged', changed).addErrback(lambda e: None)

        return changed

    def refresh(self):
        state = self.state
        character = self.character
        mob = character.mob
        spawn = mob.spawn
        changed = self.refreshLite()
        if mob.skillLevels != state['SKILLS']:
            changed['SKILLS'] = state['SKILLS'] = mob.skillLevels.copy()
        skillReuse = dict(((key.upper(), 1) for key in mob.skillReuse.iterkeys()))
        if skillReuse != state['SKILLREUSE']:
            changed['SKILLREUSE'] = state['SKILLREUSE'] = skillReuse
        items = dict(((item.slot, item.itemInfo) for item in character.items))
        if state['ITEMS'] != items:
            state['ITEMS'] = changed['ITEMS'] = items
        if state['PCLASS'] != spawn.pclassInternal:
            state['PCLASS'] = changed['PCLASS'] = spawn.pclassInternal
        if state['SCLASS'] != spawn.sclassInternal:
            state['SCLASS'] = changed['SCLASS'] = spawn.sclassInternal
        if state['TCLASS'] != spawn.tclassInternal:
            state['TCLASS'] = changed['TCLASS'] = spawn.tclassInternal
        if state['PLEVEL'] != spawn.plevel:
            state['PLEVEL'] = changed['PLEVEL'] = spawn.plevel
        if state['SLEVEL'] != spawn.slevel:
            state['SLEVEL'] = changed['SLEVEL'] = spawn.slevel
        if state['TLEVEL'] != spawn.tlevel:
            state['TLEVEL'] = changed['TLEVEL'] = spawn.tlevel
        if state['DEAD'] != character.dead:
            state['DEAD'] = changed['DEAD'] = character.dead
        if state['ADVANCE'] != character.advancementPoints:
            state['ADVANCE'] = changed['ADVANCE'] = character.advancementPoints
        cadvance = [ (a.advancementProto.name, a.rank) for a in self.character.advancementsCache ]
        if state['ADVANCEMENTS'] != cadvance:
            state['ADVANCEMENTS'] = changed['ADVANCEMENTS'] = cadvance
        spells = {}
        for cspell in character.spells:
            if not cspell.spellInfo:
                cspell.spellInfo = CharSpellInfo(character, cspell)
            else:
                cspell.spellInfo.refresh()
            spells[cspell.slot] = cspell.spellInfo

        if state['SPELLS'] != spells:
            changed['SPELLS'] = state['SPELLS'] = spells
        if len(mob.processesIn):
            spelleffects = []
            from mud.world.spell import Spell
            processes = []
            processes.extend(mob.processesIn)
            for p in processes:
                if isinstance(p, Spell):
                    if not p.spellProto.duration:
                        continue
                    if not p.spellEffectInfo:
                        p.spellEffectInfo = SpellEffectInfo(p)
                    else:
                        p.spellEffectInfo.TIME = float(p.spellProto.duration) / 6.0 - float(p.time) / 6.0
                    if p.spellEffectInfo not in spelleffects:
                        spelleffects.append(p.spellEffectInfo)

            if spelleffects != state['SPELLEFFECTS']:
                changed['SPELLEFFECTS'] = state['SPELLEFFECTS'] = spelleffects
        elif len(state['SPELLEFFECTS']):
            changed['SPELLEFFECTS'] = state['SPELLEFFECTS'] = []
        if state['PORTRAITPIC'] != character.portraitPic:
            changed['PORTRAITPIC'] = state['PORTRAITPIC'] = character.portraitPic
        vitems = [ (v.id, v.name, v.stackCount) for v in self.character.vaultItems ]
        if state['VAULTITEMS'] != vitems:
            changed['VAULTITEMS'] = state['VAULTITEMS'] = vitems
        if len(changed):
            for o in self.observers:
                o.callRemote('updateChanged', changed).addErrback(lambda e: None)

        character.player.cinfoDirty = False

    def refreshVault(self):
        state = self.state
        changed = {}
        vitems = [ (v.id, v.name, v.stackCount) for v in self.character.vaultItems ]
        if state['VAULTITEMS'] != vitems:
            changed['VAULTITEMS'] = state['VAULTITEMS'] = vitems
            for o in self.observers:
                o.callRemote('updateChanged', changed).addErrback(lambda e: None)


class CharacterInfoGhost(pb.RemoteCache):

    def __init__(self):
        self.clientSettings = {}
        self.clientSettings['LINKMOUSETARGET'] = 1
        self.clientSettings['LINKTARGET'] = None
        self.clientSettings['DEFAULTTARGET'] = None
        self.clientSettings['PXPGAIN'] = 1
        self.clientSettings['SXPGAIN'] = 0
        self.clientSettings['TXPGAIN'] = 0
        self.clientSettings['ENCOUNTERPVEZONE'] = 1
        self.clientSettings['ENCOUNTERPVEDIE'] = 1
        return

    def setCopyableState(self, state):
        global DIRTY
        self.__dict__.update(state)
        DIRTY = True
        SKILLS_DIRTY.append(self)

    def observe_updateChanged(self, changed):
        global DIRTY
        global ADVANCEMENTS_DIRTY
        self.__dict__.update(changed)
        DIRTY = True
        if changed.has_key('SKILLS') or changed.has_key('SKILLREUSE'):
            SKILLS_DIRTY.append(self)
            try:
                from mud.client.gui.macro import MACROMASTER
                MACROMASTER.updateSkillUsingMacros(iterableSkills=changed['SKILLREUSE'])
            except KeyError:
                pass

        if changed.has_key('DEAD'):
            if changed['DEAD']:
                from mud.client.gui.partyWnd import PARTYWND
                from mud.client.gui.macro import MACROMASTER
                for charIndex, cinfo in PARTYWND.charInfos.iteritems():
                    if cinfo == self:
                        break

                MACROMASTER.stopMacrosForChar(charIndex)
        if changed.has_key('ADVANCE') or changed.has_key('ADVANCEMENTS') or changed.has_key('PLEVEL') or changed.has_key('SLEVEL') or changed.has_key('TLEVEL') or changed.has_key('TCLASS') or changed.has_key('SCLASS') or changed.has_key('PCLASS'):
            ADVANCEMENTS_DIRTY = True


pb.setUnjellyableForClass(CharacterInfo, CharacterInfoGhost)

class EffectProtoInfo(pb.Copyable, pb.RemoteCopy):

    def __init__(self, eproto = None):
        if eproto:
            pass


pb.setUnjellyableForClass(EffectProtoInfo, EffectProtoInfo)

class CharSpellInfo(pb.Cacheable):

    def __init__(self, character, charSpell):
        self.observers = []
        self.char = character
        self.charSpell = charSpell
        self.state = None
        return

    def stoppedObserving(self, perspective, observer):
        self.observers.remove(observer)

    def getFullState(self):
        state = self.state = {}
        proto = self.charSpell.spellProto
        state['ID'] = proto.id
        state['SLOT'] = self.charSpell.slot
        state['RECASTTIMER'] = 0
        state['SPELLINFO'] = SpellInfo(proto, self.charSpell.level)
        if self.char.mob.recastTimers.has_key(proto):
            state['RECASTTIMER'] = self.char.mob.recastTimers[proto]
        return state

    def getStateToCacheAndObserveFor(self, perspective, observer):
        self.observers.append(observer)
        return self.getFullState()

    def fullRefresh(self):
        r = self.getFullState()
        for o in self.observers:
            o.callRemote('updateChanged', r).addErrback(lambda e: None)

    def refresh(self):
        state = self.state
        if state == None:
            return
        else:
            changed = {}
            proto = self.charSpell.spellProto
            slot = self.charSpell.slot
            if slot != state['SLOT']:
                state['SLOT'] = changed['SLOT'] = slot
            recast = 0
            if self.char.mob.recastTimers.has_key(proto):
                recast = self.char.mob.recastTimers[proto]
            if recast != state['RECASTTIMER']:
                state['RECASTTIMER'] = changed['RECASTTIMER'] = recast
            if not len(changed):
                return
            for o in self.observers:
                o.callRemote('updateChanged', changed).addErrback(lambda e: None)

            return


class CharSpellInfoGhost(pb.RemoteCache):

    def setCopyableState(self, state):
        self.__dict__.update(state)

    def observe_updateChanged(self, changed):
        self.__dict__.update(changed)
        if changed.has_key('RECASTTIMER'):
            from mud.client.gui.macro import MACROMASTER
            MACROMASTER.updateSpellUsingMacros(self.SPELLINFO.BASENAME)


pb.setUnjellyableForClass(CharSpellInfo, CharSpellInfoGhost)

class SpellInfo(pb.Cacheable):

    def __init__(self, proto, level = 0):
        self.observers = []
        self.proto = proto
        self.level = level

    def stoppedObserving(self, perspective, observer):
        self.observers.remove(observer)

    def getFullState(self):
        state = self.state = {}
        state['ID'] = self.proto.id
        state['LEVEL'] = self.level
        return state

    def getStateToCacheAndObserveFor(self, perspective, observer):
        self.observers.append(observer)
        return self.getFullState()

    def fullRefresh(self):
        for o in self.observers:
            o.callRemote('updateChanged', self.getFullState()).addErrback(lambda e: None)


class SpellInfoGhost(pb.RemoteCache):

    def __init__(self, spID = None):
        self.text = ''
        self.ID = spID
        if spID:
            self.LEVEL = 0
            self.generateItemText()

    def generateItemText(self):
        from mud.client.playermind import GetMoMClientDBConnection
        con = GetMoMClientDBConnection()
        self.BASENAME, self.SPELLBOOKPIC, self.DESC, self.TARGET, self.CASTTIME, self.RECASTTIME, self.DURATION, self.CASTRANGE, self.AOERANGE, self.MANACOST, self.SKILLNAME, self.SPELLTYPE = con.execute('SELECT name,spellbook_pic,desc,target,cast_time,recast_time,duration,cast_range,aoe_range,mana_cost,skillname,spell_type FROM spell_proto WHERE id = %i LIMIT 1;' % self.ID).fetchone()
        self.CLASSES = tuple(((classname, level) for classname, level in con.execute('SELECT classname,level FROM spell_class WHERE spell_proto_id = %i;' % self.ID)))
        self.COMPONENTS = []
        for protoID, count in con.execute('SELECT item_proto_id,count FROM spell_component WHERE spell_proto_id = %i;' % self.ID):
            self.COMPONENTS.append((con.execute('SELECT name FROM item_proto WHERE id = %i LIMIT 1;' % protoID).fetchone()[0], count))

        negate = negatemax = 0
        for neg, negMax in con.execute('SELECT negate,negate_max_level FROM effect_proto WHERE id in (SELECT effect_proto_id FROM effect_proto_spell_proto WHERE spell_proto_id = %i);' % self.ID):
            if neg > negate:
                negate = neg
            if negMax > negatemax:
                negatemax = negMax

        self.NEGATE = negate
        self.NEGATEMAXLEVEL = negatemax
        text = []
        if self.LEVEL:
            self.NAME = ' '.join([self.BASENAME, RPG_ROMAN[self.LEVEL - 1]])
            text.append('\\cp\\c3Casting Level: \\c0%s\\n' % RPG_ROMAN[self.LEVEL - 1])
        if self.SKILLNAME:
            text.append('\\c3Skill: \\c0%s ' % self.SKILLNAME)
        if self.SPELLTYPE & RPG_SPELL_HARMFUL:
            text.append('\\c3Target: \\c1%s ' % RPG_TARGET_TEXT[self.TARGET])
        else:
            text.append('\\c3Target: \\c2%s ' % RPG_TARGET_TEXT[self.TARGET])
        if self.TARGET != RPG_TARGET_SELF:
            text.append('\\c3Range: \\c0%im ' % self.CASTRANGE)
        if self.AOERANGE:
            text.append('\\c3AoE Range: \\c0%im ' % self.AOERANGE)
        if not self.DURATION:
            text.append('\\c3Duration: \\c0Instant ')
        else:
            d = self.DURATION / 6
            if d > 60:
                m, s = divmod(d, 60)
                text.append('\\c3Duration: \\c0%im %is ' % (m, s))
            else:
                text.append('\\c3Duration: \\c0%is ' % d)
        if not self.CASTTIME:
            text.append('\\c3Cast Time: \\c0Instant ')
        else:
            d = self.CASTTIME / 6
            if d > 60:
                m, s = divmod(d, 60)
                text.append('\\c3Cast Time: \\c0%im %is ' % (m, s))
            else:
                text.append('\\c3Cast Time: \\c0%is ' % d)
        text.append('\\c3Mana: \\c0%i ' % self.MANACOST)
        if self.NEGATE and self.NEGATEMAXLEVEL:
            text.append('\\n\\c3Negate: \\c0%i \\c3of max level \\c0%i \\n' % (self.NEGATE, self.NEGATEMAXLEVEL))
        classtext = ' '.join(('\\c0%s\\c3(\\c0%i\\c3)' % (cl, level) for cl, level in self.CLASSES))
        if classtext:
            text.append('\\c3Classes: %s ' % classtext)
        comptext = ' '.join(('\\c0%s\\c3(\\c0%i\\c3)' % (c, count) for c, count in self.COMPONENTS))
        if comptext:
            text.append('\\c3Components: %s ' % comptext)
        desctext = self.DESC
        if desctext:
            if len(text):
                text.append('\\n\\n%s' % desctext)
            else:
                text.append(desctext)
        self.text = ''.join(text)

    def setCopyableState(self, state):
        self.__dict__.update(state)
        self.generateItemText()

    def observe_updateChanged(self, changed):
        self.__dict__.update(changed)
        if self.LEVEL:
            self.NAME = ' '.join([self.BASENAME, RPG_ROMAN[self.LEVEL - 1]])


pb.setUnjellyableForClass(SpellInfo, SpellInfoGhost)

class AllianceInfo(pb.Cacheable):

    def __init__(self, alliance):
        self.alliance = alliance
        self.cnames = {}
        self.chealth = {}
        self.observers = []
        self.state = None
        return

    def getStateDict(self, state):
        from mud.world.alliance import Alliance
        state['PNAMES'] = []
        state['NAMES'] = {}
        state['HEALTHS'] = {}
        state['MOBIDS'] = {}
        alliance = self.alliance
        a = Alliance.masterAllianceInfo.get(alliance.remoteLeaderName)
        if a:
            local = {}
            for m in alliance.members:
                if not m.party:
                    continue
                c = m.party.members[0]
                if c.mob:
                    h = round(float(c.mob.health) / float(c.mob.maxHealth), 1)
                    local[m.name] = (c.name, h, c.mob.id)
                else:
                    local[m.name] = (c.name, 1.0, -1)

            for x, (pname, cname) in enumerate(a):
                state['PNAMES'].append(pname)
                state['NAMES'][x] = []
                state['HEALTHS'][x] = []
                state['MOBIDS'][x] = []
                if pname in local:
                    cname, health, id = local[pname]
                    state['NAMES'][x].append(cname)
                    state['HEALTHS'][x].append(health)
                    state['MOBIDS'][x].append(id)
                else:
                    state['NAMES'][x].append(cname)
                    state['HEALTHS'][x].append(1.0)
                    state['MOBIDS'][x].append(-1)

        elif alliance and alliance.members:
            allianceIndex = 0
            for m in alliance.members:
                state['PNAMES'].append(m.name)
                state['NAMES'][allianceIndex] = []
                state['HEALTHS'][allianceIndex] = []
                state['MOBIDS'][allianceIndex] = []
                if m.party:
                    for c in m.party.members:
                        if c.mob:
                            state['NAMES'][allianceIndex].append(c.name)
                            h = round(float(c.mob.health) / float(c.mob.maxHealth), 1)
                            state['HEALTHS'][allianceIndex].append(h)
                            state['MOBIDS'][allianceIndex].append(c.mob.id)
                        else:
                            state['NAMES'][allianceIndex].append(c.name)
                            state['HEALTHS'][allianceIndex].append(1.0)
                            state['MOBIDS'][allianceIndex].append(-1)
                            break

                    allianceIndex += 1

    def getStateToCacheAndObserveFor(self, perspective, observer):
        self.observers.append(observer)
        state = {}
        if not self.state:
            self.state = state
        alliance = self.alliance
        state['LEADER'] = alliance.remoteLeaderName
        self.getStateDict(state)
        return state

    def stoppedObserving(self, perspective, observer):
        self.observers.remove(observer)

    def refresh(self):
        changed = {}
        state = {}
        self.getStateDict(state)
        if self.state['PNAMES'] != state['PNAMES']:
            changed['PNAMES'] = self.state['PNAMES'] = state['PNAMES']
        if self.state['NAMES'] != state['NAMES']:
            changed['NAMES'] = self.state['NAMES'] = state['NAMES']
        if self.state['HEALTHS'] != state['HEALTHS']:
            changed['HEALTHS'] = self.state['HEALTHS'] = state['HEALTHS']
        if self.state['MOBIDS'] != state['MOBIDS']:
            changed['MOBIDS'] = self.state['MOBIDS'] = state['MOBIDS']
        if len(changed):
            for o in self.observers:
                o.callRemote('updateChanged', changed).addErrback(lambda e: None)


class AllianceInfoGhost(pb.RemoteCache):

    def setCopyableState(self, state):
        self.__dict__.update(state)

    def observe_updateChanged(self, changed):
        self.__dict__.update(changed)
        from mud.client.gui.allianceWnd import ALLIANCEWND
        from mud.client.gui.leaderWnd import LEADERWND
        ALLIANCEWND.setAllianceInfo(self)
        LEADERWND.setAllianceInfo(self)


pb.setUnjellyableForClass(AllianceInfo, AllianceInfoGhost)

class TradeInfo(pb.Cacheable):

    def __init__(self, trade):
        self.trade = trade
        self.observers = []
        self.state = None
        return

    def stoppedObserving(self, perspective, observer):
        self.observers.remove(observer)

    def getStateToCacheAndObserveFor(self, perspective, observer):
        self.observers.append(observer)
        state = {}
        trade = self.trade
        if not self.state:
            self.state = state
        state['P0NAME'] = trade.p0.name
        state['P1NAME'] = trade.p1.name
        state['C0NAME'] = trade.p0.charName
        state['C1NAME'] = trade.p1.charName
        state['P0ACCEPTED'] = trade.p0Accepted
        state['P1ACCEPTED'] = trade.p1Accepted
        state['P0TIN'] = trade.p0Tin
        state['P1TIN'] = trade.p1Tin
        state['P0ITEMS'] = dict(((slot, item.itemInfo) for slot, item in trade.p0Items.iteritems()))
        state['P1ITEMS'] = dict(((slot, item.itemInfo) for slot, item in trade.p1Items.iteritems()))
        return state

    def refresh(self):
        changed = {}
        trade = self.trade
        p0Items = dict(((slot, item.itemInfo) for slot, item in trade.p0Items.items()))
        p1Items = dict(((slot, item.itemInfo) for slot, item in trade.p1Items.items()))
        if self.state['P0ACCEPTED'] != trade.p0Accepted:
            self.state['P0ACCEPTED'] = changed['P0ACCEPTED'] = trade.p0Accepted
        if self.state['P1ACCEPTED'] != trade.p1Accepted:
            self.state['P1ACCEPTED'] = changed['P1ACCEPTED'] = trade.p1Accepted
        if self.state['P0TIN'] != trade.p0Tin:
            self.state['P0TIN'] = changed['P0TIN'] = trade.p0Tin
        if self.state['P1TIN'] != trade.p1Tin:
            self.state['P1TIN'] = changed['P1TIN'] = trade.p1Tin
        if self.state['P0ITEMS'] != p0Items:
            self.state['P0ITEMS'] = changed['P0ITEMS'] = p0Items
        if self.state['P1ITEMS'] != p1Items:
            self.state['P1ITEMS'] = changed['P1ITEMS'] = p1Items
        if len(changed):
            for o in self.observers:
                o.callRemote('updateChanged', changed).addErrback(lambda e: None)

    def refreshDict(self, dict):
        for k, v in dict.items():
            try:
                if self.state[k] != v:
                    self.state[k] = v
                else:
                    del dict[k]
            except:
                del dict[k]
                traceback.print_exc()

        if len(dict):
            for o in self.observers:
                o.callRemote('updateChanged', dict).addErrback(lambda e: None)


class TradeInfoGhost(pb.RemoteCache):

    def setCopyableState(self, state):
        self.__dict__.update(state)

    def observe_updateChanged(self, changed):
        self.__dict__.update(changed)
        from mud.client.gui.tradeWnd import TRADEWND
        TRADEWND.setFromTradeInfo(self)


pb.setUnjellyableForClass(TradeInfo, TradeInfoGhost)