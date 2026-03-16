# Embedded file name: mud\world\career.pyo
from mud.common.persistent import Persistent
from sqlobject import *

class ClassProto(Persistent):
    name = StringCol(alternateID=True)
    archetype = StringCol(default='')
    xpMod = FloatCol(default=1.0)
    skills = RelatedJoin('ClassSkill')