# Embedded file name: mud\world\archetype.pyo
from career import ClassProto
CLASSES = {}

class Archetype:

    def __init__(self):
        self.xpMod = 1.0
        try:
            self.classProto = ClassProto.byName(self.name)
            self.classSkills = list(self.classProto.skills)
        except:
            self.classProto = None
            self.classSkills = []

        return

    def getMaxHealth(self, mob, level):
        return level * level + 10

    def getMaxMana(self, mob, level):
        return 100

    def getMaxStamina(self, mob, level):
        return level * level

    def getOffense(self, mob, level):
        return level * level

    def getDefense(self, mob, level):
        return level * level

    def getXPMod(self):
        return 1

    def getPrimaryAttackRate(self, mob, level):
        return 16

    def getSecondaryAttackRate(self, mob, level):
        return 24

    def getCritical(self, mob, level):
        return 1.0

    def getClassStats(self, mob, level):
        stats = {}
        health = self.getMaxHealth(mob, level)
        if not mob.player and level > 20:
            health *= level / 20
        stats['maxHealth'] = health
        stats['maxMana'] = self.getMaxMana(mob, level) + 6
        stats['maxStamina'] = self.getMaxStamina(mob, level)
        stats['offense'] = self.getOffense(mob, level)
        stats['defense'] = self.getDefense(mob, level)
        stats['primaryAttackRate'] = self.getPrimaryAttackRate(mob, level)
        stats['secondaryAttackRate'] = self.getSecondaryAttackRate(mob, level)
        stats['critical'] = self.getCritical(mob, level)
        return stats


class Combatant(Archetype):

    def __init__(self):
        Archetype.__init__(self)

    def getMaxMana(self, mob, level):
        return 0

    def getCritical(self, mob, level):
        return 1.0

    def getMaxHealth(self, mob, level):
        s1 = level / 10.0
        s2 = level / 25.0
        return int(level * level + 50 + mob.bdy * s1 + mob.str * s2) + mob.pre * 5

    def getMaxStamina(self, mob, level):
        s1 = level / 10.0
        s2 = level / 25.0
        return int(level * level + 50 + mob.bdy * s1 + mob.str * s2) + mob.pre * 5

    def getOffense(self, mob, level):
        s1 = level / 10.0
        s2 = level / 25.0
        s3 = level / 50.0
        return int(level * level + 10 + mob.str * s1 + mob.dex * s2 + mob.ref * s3) + mob.pre * 10

    def getDefense(self, mob, level):
        s1 = level / 10.0
        s2 = level / 25.0
        s3 = level / 50.0
        s4 = level / 100.0
        base = int(level * level + 10 + mob.bdy * s1 + mob.dex * s2 + mob.ref * s3 + mob.agi * s4)
        base += mob.armor * 4 + +mob.pre * 4
        return base


class Magi(Archetype):

    def __init__(self):
        Archetype.__init__(self)

    def getMaxStamina(self, mob, level):
        s1 = level / 10.0
        s2 = level / 25.0
        return int(level * level + 50 + mob.bdy * s1 + mob.str * s2) / 2 + 16 + mob.pre * 5

    def getMaxMana(self, mob, level):
        x = int(mob.mnd / 10 * level) + int(mob.pre * level * 0.5)
        x += int(mob.mnd * 5 * float(level) / 100.0)
        return x

    def getMaxHealth(self, mob, level):
        global CLASSES
        if not mob.player:
            return int(CLASSES['Warrior'].getMaxHealth(mob, level) * 0.75)
        s1 = level / 10.0
        s2 = level / 25.0
        return int(level * level + 50 + mob.bdy * s1 + mob.str * s2) / 4 + 16 + mob.pre * 2

    def getOffense(self, mob, level):
        s1 = level / 10.0
        s2 = level / 25.0
        s3 = level / 50.0
        offence = int(level * level + 10 + mob.str * s1 + mob.dex * s2 + mob.ref * s3)
        return offence / 4 + mob.pre

    def getDefense(self, mob, level):
        s1 = level / 10.0
        s2 = level / 25.0
        s3 = level / 50.0
        s4 = level / 100.0
        base = int(level * level + 10 + mob.bdy * s1 + mob.dex * s2 + mob.ref * s3 + mob.agi * s4)
        base += mob.armor * 4 + mob.pre
        return base / 5

    def getCritical(self, mob, level):
        return 0.5


class Priest(Archetype):

    def __init__(self):
        Archetype.__init__(self)

    def getMaxStamina(self, mob, level):
        s1 = level / 10.0
        s2 = level / 25.0
        return int(level * level + 50 + mob.bdy * s1 + mob.str * s2) + 16 + mob.pre * 5

    def getMaxMana(self, mob, level):
        x = int(mob.mys / 10 * level) + int(mob.pre * level * 0.5)
        x += int(mob.mys * 5 * float(level) / 100.0)
        return x

    def getMaxHealth(self, mob, level):
        if not mob.player:
            return int(CLASSES['Warrior'].getMaxHealth(mob, level) * 0.75)
        s1 = level / 10.0
        s2 = level / 25.0
        return int(level * level + 50 + mob.bdy * s1 + mob.str * s2) / 2

    def getOffense(self, mob, level):
        s1 = level / 10.0
        s2 = level / 25.0
        s3 = level / 50.0
        return int(level * level + 10 + mob.str * s1 + mob.dex * s2 + mob.ref * s3) / 2

    def getDefense(self, mob, level):
        s1 = level / 10.0
        s2 = level / 25.0
        s3 = level / 50.0
        s4 = level / 100.0
        base = int(level * level + 10 + mob.bdy * s1 + mob.dex * s2 + mob.ref * s3 + mob.agi * s4)
        base += mob.armor * 4
        return base / 2

    def getCritical(self, mob, level):
        return 0.8


class Rogue(Archetype):

    def __init__(self):
        Archetype.__init__(self)

    def getMaxStamina(self, mob, level):
        s1 = level / 10.0
        s2 = level / 25.0
        return int(level * level + 50 + mob.bdy * s1 + mob.str * s2) + mob.pre * 5

    def getMaxMana(self, mob, level):
        return 0

    def getMaxHealth(self, mob, level):
        if not mob.player:
            return int(CLASSES['Warrior'].getMaxHealth(mob, level) * 0.85)
        s1 = level / 10.0
        s2 = level / 25.0
        return int((level * level + 50 + mob.bdy * s1 + mob.str * s2) * 0.75) + mob.pre * 5

    def getOffense(self, mob, level):
        s1 = level / 10.0
        s2 = level / 25.0
        s3 = level / 50.0
        base = int((level * level + 10 + mob.str * s2 + mob.dex * s1 + mob.ref * s2) * 1.3)
        return base + mob.pre * 6

    def getDefense(self, mob, level):
        s1 = level / 10.0
        s2 = level / 25.0
        s3 = level / 50.0
        s4 = level / 100.0
        base = int((level * level + 10 + mob.bdy * s2 + mob.dex * s1 + mob.ref * s2 + mob.agi * s2) * 0.75)
        base += mob.armor * 3 + mob.pre * 3
        return base

    def getCritical(self, mob, level):
        return 1.2


class Warrior(Combatant):

    def __init__(self):
        self.name = 'Warrior'
        Combatant.__init__(self)

    def getXPMod(self):
        return 0.9

    def getCritical(self, mob, level):
        return 1.1

    def getDefense(self, mob, level):
        return int(Combatant.getDefense(self, mob, level) * 1.2)

    def getMaxHealth(self, mob, level):
        return int(Combatant.getMaxHealth(self, mob, level) * 1.3)


class Ranger(Combatant):

    def __init__(self):
        self.name = 'Ranger'
        Combatant.__init__(self)

    def getXPMod(self):
        return 1

    def getMaxMana(self, mob, level):
        x = int(mob.mnd / 10 * level) + int(mob.pre * level * 0.5)
        x += int(mob.mnd * 5 * float(level) / 100.0)
        return x

    def getMaxHealth(self, mob, level):
        return int(Combatant.getMaxHealth(self, mob, level) * 1)


class Paladin(Combatant):

    def __init__(self):
        self.name = 'Paladin'
        Combatant.__init__(self)

    def getXPMod(self):
        return 1.05

    def getMaxMana(self, mob, level):
        x = int(mob.wis / 10 * level) + int(mob.pre * level * 0.5)
        x += int(mob.wis * 5 * float(level) / 100.0)
        return x

    def getDefense(self, mob, level):
        return int(Combatant.getDefense(self, mob, level) * 1.1)

    def getMaxHealth(self, mob, level):
        return int(Combatant.getMaxHealth(self, mob, level) * 1.2)


class DoomKnight(Combatant):

    def __init__(self):
        self.name = 'Doom Knight'
        Combatant.__init__(self)

    def getMaxMana(self, mob, level):
        x = int(mob.mnd / 10 * level) + int(mob.pre * level * 0.5)
        x += int(mob.mnd * 5.0 * float(level) / 100.0)
        return x

    def getXPMod(self):
        return 0.9


class Barbarian(Combatant):

    def __init__(self):
        self.name = 'Barbarian'
        Combatant.__init__(self)

    def getXPMod(self):
        return 1.05

    def getOffense(self, mob, level):
        return int(Combatant.getOffense(self, mob, level) * 1.2)

    def getDefense(self, mob, level):
        return int(Combatant.getDefense(self, mob, level) * 0.9)

    def getMaxHealth(self, mob, level):
        return int(Combatant.getMaxHealth(self, mob, level) * 1.1)


class Monk(Combatant):

    def __init__(self):
        self.name = 'Monk'
        Combatant.__init__(self)

    def getXPMod(self):
        return 1.1

    def getMaxHealth(self, mob, level):
        s1 = level / 10.0
        s2 = level / 25.0
        return int(level * level + 50 + mob.bdy * s1 + mob.str * s2) + mob.pre * 7

    def getOffense(self, mob, level):
        s1 = level / 10.0
        s2 = level / 25.0
        s3 = level / 50.0
        base = int((level * level + 10 + mob.str * s1 + mob.dex * s2 + mob.ref * s3) * 1.25)
        return base + mob.pre * 6

    def getDefense(self, mob, level):
        s0 = level / 5.0
        s1 = level / 10.0
        s2 = level / 25.0
        s3 = level / 50.0
        s4 = level / 100.0
        base = int(level * level + 10 + mob.bdy * s1 + mob.dex * s2 + mob.ref * s1 + mob.agi * s0)
        base += mob.armor * 2 + mob.pre * 4
        return base


class Assassin(Rogue):

    def __init__(self):
        self.name = 'Assassin'
        Rogue.__init__(self)

    def getXPMod(self):
        return 1.1

    def getCritical(self, mob, level):
        return 1.4


class Thief(Rogue):

    def __init__(self):
        self.name = 'Thief'
        Rogue.__init__(self)

    def getXPMod(self):
        return 1


class Bard(Rogue):

    def __init__(self):
        self.name = 'Bard'
        Rogue.__init__(self)

    def getXPMod(self):
        return 1

    def getMaxStamina(self, mob, level):
        s1 = level / 10.0
        s2 = level / 25.0
        return int(level * level + 50 + mob.bdy * s1 + mob.str * s2) + mob.pre * 5

    def getCritical(self, mob, level):
        return 1.0

    def getMaxMana(self, mob, level):
        x = int(mob.mnd / 10 * level) + int(mob.pre * level * 0.5)
        x += int(mob.mnd * 5 * float(level) / 100.0)
        return x

    def getMaxHealth(self, mob, level):
        s1 = level / 10.0
        s2 = level / 25.0
        return int(level * level + 50 + mob.bdy * s1 + mob.str * s2) + mob.pre * 6

    def getOffense(self, mob, level):
        s1 = level / 10.0
        s2 = level / 25.0
        s3 = level / 50.0
        base = int(level * level + 10 + mob.str * s1 + mob.dex * s2 + mob.ref * s3)
        return base + mob.pre * 4

    def getDefense(self, mob, level):
        s1 = level / 10.0
        s2 = level / 25.0
        s3 = level / 50.0
        s4 = level / 100.0
        base = int(level * level + 10 + mob.bdy * s1 + mob.dex * s2 + mob.ref * s3 + mob.agi * s4)
        base += mob.armor * 4 + mob.pre * 4
        return base


class Wizard(Magi):

    def __init__(self):
        self.name = 'Wizard'
        Magi.__init__(self)

    def getXPMod(self):
        return 1.05


class Revealer(Magi):

    def __init__(self):
        self.name = 'Revealer'
        Magi.__init__(self)

    def getXPMod(self):
        return 1.05


class Necromancer(Magi):

    def __init__(self):
        self.name = 'Necromancer'
        Magi.__init__(self)

    def getXPMod(self):
        return 1.1


class Cleric(Priest):

    def __init__(self):
        self.name = 'Cleric'
        Priest.__init__(self)

    def getXPMod(self):
        return 1

    def getMaxMana(self, mob, level):
        x = int(mob.wis / 10 * level) + int(mob.pre * level * 0.5)
        x += int(mob.wis * 5 * float(level) / 100.0)
        return x


class Tempest(Priest):

    def __init__(self):
        self.name = 'Tempest'
        Priest.__init__(self)

    def getXPMod(self):
        return 1.05


class Shaman(Priest):

    def __init__(self):
        self.name = 'Shaman'
        Priest.__init__(self)

    def getXPMod(self):
        return 1.05


class Druid(Priest):

    def __init__(self):
        self.name = 'Druid'
        Priest.__init__(self)

    def getMaxMana(self, mob, level):
        x = int(mob.wis / 10 * level) + int(mob.pre * level * 0.5)
        x += int(mob.wis * 5 * float(level) / 100.0)
        return x

    def getXPMod(self):
        return 1


def InitClassSkills():
    global CLASSES
    CLASSES = {}
    CLASSES['Warrior'] = Warrior()
    CLASSES['Ranger'] = Ranger()
    CLASSES['Paladin'] = Paladin()
    CLASSES['Doom Knight'] = DoomKnight()
    CLASSES['Barbarian'] = Barbarian()
    CLASSES['Monk'] = Monk()
    CLASSES['Thief'] = Thief()
    CLASSES['Assassin'] = Assassin()
    CLASSES['Bard'] = Bard()
    CLASSES['Wizard'] = Wizard()
    CLASSES['Revealer'] = Revealer()
    CLASSES['Necromancer'] = Necromancer()
    CLASSES['Cleric'] = Cleric()
    CLASSES['Tempest'] = Tempest()
    CLASSES['Shaman'] = Shaman()
    CLASSES['Druid'] = Druid()
    for cl in CLASSES.itervalues():
        if cl.classProto:
            cl.classSkills = cl.classProto.skills


def GetClass(classname):
    if not len(CLASSES):
        InitClassSkills()
    try:
        return CLASSES[classname]
    except KeyError:
        print 'WARNING: Unknown class: %s' % classname
        return CLASSES['Warrior']