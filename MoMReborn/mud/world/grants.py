# Embedded file name: mud\world\grants.pyo


class GrantedLoot:
    items = []
    lootids = []
    confirmed = []

    def __init__(self, items, lootids):
        self.items = items
        self.lootids = lootids

    def giveMoney(self, player):
        pass


class GrantsProvider:
    detached = True
    looter = None
    loot = None
    zone = None
    pname = ''

    def __init__(self, pname, items, lootids):
        self.pname = pname
        self.loot = GrantedLoot(items, lootids)