# Embedded file name: mud\world\advancement.pyo
from mud.common.persistent import Persistent
from sqlobject import *

class AdvancementClass(Persistent):
    classname = StringCol()
    level = IntCol()
    advancementProto = ForeignKey('AdvancementProto')


class AdvancementRace(Persistent):
    racename = StringCol()
    level = IntCol()
    advancementProto = ForeignKey('AdvancementProto')


class AdvancementRequirement(Persistent):
    require = StringCol()
    rank = IntCol(default=1)
    advancementProto = ForeignKey('AdvancementProto')


class AdvancementExclusion(Persistent):
    exclude = StringCol()
    advancementProto = ForeignKey('AdvancementProto')


class AdvancementStat(Persistent):
    statname = StringCol()
    value = FloatCol()
    advancementProto = ForeignKey('AdvancementProto')


class AdvancementSkill(Persistent):
    skillname = StringCol()
    advancementProto = ForeignKey('AdvancementProto')


class AdvancementProto(Persistent):
    name = StringCol(alternateID=True)
    level = IntCol(default=1)
    desc = StringCol(default='')
    cost = IntCol(default=1)
    maxRank = IntCol(default=1)
    stats = MultipleJoin('AdvancementStat')
    skills = MultipleJoin('AdvancementSkill')
    classes = MultipleJoin('AdvancementClass')
    races = MultipleJoin('AdvancementRace')
    requirements = MultipleJoin('AdvancementRequirement')
    exclusionsInternal = MultipleJoin('AdvancementExclusion')

    def _init(self, *args, **kwargs):
        Persistent._init(self, *args, **kwargs)
        self.exclusions = self.exclusionsInternal