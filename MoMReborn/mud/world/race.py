# Embedded file name: mud\world\race.pyo
from defines import *

class Race:

    def __init__(self):
        self.name = ''
        self.xpMod = 1.0
        self.regenHealth = 1.0
        self.regenMana = 2
        self.regenStamina = 1
        self.consumeWater = 1
        self.consumeFood = 1
        self.move = 1
        self.swim = 1
        self.resists = {}
        self.realm = RPG_REALM_MONSTER
        self.seeInvisible = 0.0

    def getXPMod(self):
        return self.xpMod


class Troll(Race):

    def __init__(self):
        Race.__init__(self)
        self.name = 'Troll'
        self.xpMod = 1.05
        self.regenHealth = 1.05
        self.regenMana = 2
        self.regenStamina = 2
        self.realm = RPG_REALM_DARKNESS


class Ogre(Race):

    def __init__(self):
        Race.__init__(self)
        self.name = 'Ogre'
        self.regenHealth = 1.0
        self.regenMana = 2
        self.regenStamina = 1
        self.realm = RPG_REALM_DARKNESS
        self.resists = {RPG_RESIST_DISEASE: 10}


class Goblin(Race):

    def __init__(self):
        Race.__init__(self)
        self.name = 'Goblin'
        self.realm = RPG_REALM_DARKNESS


class Orc(Race):

    def __init__(self):
        Race.__init__(self)
        self.name = 'Orc'
        self.regenHealth = 1.0
        self.regenMana = 2.0
        self.regenStamina = 2
        self.realm = RPG_REALM_DARKNESS


class Dwarf(Race):

    def __init__(self):
        Race.__init__(self)
        self.name = 'Dwarf'
        self.regenHealth = 1.025
        self.regenMana = 2.0
        self.regenStamina = 2
        self.realm = RPG_REALM_LIGHT


class Gnome(Race):

    def __init__(self):
        Race.__init__(self)
        self.name = 'Gnome'
        self.realm = RPG_REALM_NEUTRAL


class Human(Race):

    def __init__(self):
        Race.__init__(self)
        self.name = 'Human'
        self.realm = RPG_REALM_NEUTRAL


class Elf(Race):

    def __init__(self):
        Race.__init__(self)
        self.name = 'Elf'
        self.regenMana = 2.5
        self.realm = RPG_REALM_LIGHT


class Halfling(Race):

    def __init__(self):
        Race.__init__(self)
        self.name = 'Halfling'
        self.regenHealth = 1.05
        self.regenStamina = 2
        self.realm = RPG_REALM_LIGHT


class Drakken(Race):

    def __init__(self):
        Race.__init__(self)
        self.name = 'Drakken'
        self.xpMod = 1.1
        self.regenHealth = 1.1
        self.regenMana = 2
        self.regenStamina = 1
        self.realm = RPG_REALM_DARKNESS
        self.resists = {RPG_RESIST_COLD: -25}


class Undead(Race):

    def __init__(self):
        Race.__init__(self)
        self.name = 'Undead'
        self.consumeWater = 0
        self.consumeFood = 0
        self.seeInvisible = 100.0


class Demon(Race):

    def __init__(self):
        Race.__init__(self)
        self.name = 'Demon'
        self.seeInvisible = 100.0
        self.resists = {RPG_RESIST_FIRE: 25}


class Giant(Race):

    def __init__(self):
        Race.__init__(self)
        self.name = 'Giant'
        self.consumeWater = 3
        self.consumeFood = 3
        self.move = 2
        self.realm = RPG_REALM_NEUTRAL


RACES = {}
RACES['Troll'] = Troll()
RACES['Ogre'] = Ogre()
RACES['Goblin'] = Goblin()
RACES['Orc'] = Orc()
RACES['Dwarf'] = Dwarf()
RACES['Gnome'] = Gnome()
RACES['Halfling'] = Halfling()
RACES['Drakken'] = Drakken()
RACES['Elf'] = Elf()
RACES['Human'] = Human()
RACES['Undead'] = Undead()
RACES['Demon'] = Demon()
RACES['Giant'] = Giant()

def GetRace(racename):
    if not RACES.has_key(racename):
        RACES[racename] = Human()
        RACES[racename].name = racename
    return RACES[racename]