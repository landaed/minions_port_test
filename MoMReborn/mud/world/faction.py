# Embedded file name: mud\world\faction.pyo
from sqlobject import *
from defines import *
from mud.common.persistent import Persistent

class FactionRelation(Persistent):
    relation = IntCol(default=RPG_FACTION_UNDECIDED)
    faction = ForeignKey('Faction')
    otherFaction = ForeignKey('Faction')


class Faction(Persistent):
    name = StringCol(alternateID=True)
    level = IntCol(default=1)
    realm = IntCol(default=RPG_REALM_UNDEFINED)
    relations = MultipleJoin('FactionRelation')
    attackMsg = StringCol(default='')
    enemyMsg = StringCol(default='')
    spawns = RelatedJoin('Spawn')


KOS = {}

def InitKOS():
    from spawn import Spawn
    con = Spawn._connection.getConnection()
    for sname, sid in con.execute('SELECT name,id FROM spawn;'):
        kos = KOS[str(sname)] = []
        for otherName in con.execute('SELECT name FROM spawn WHERE id IN (SELECT DISTINCT spawn_id FROM faction_spawn WHERE faction_id IN (SELECT DISTINCT other_faction_id FROM faction_relation WHERE relation<%i AND (faction_id IN (SELECT faction_id FROM faction_spawn WHERE spawn_id=%i))));' % (RPG_FACTION_DISLIKED, sid)):
            kos.append(str(otherName[0]))