# Embedded file name: mud\world\newplayeravatar.pyo
from mud.common.avatar import Avatar
from mud.common.permission import User, Role
from mud.world.core import *
from mud.world.player import Player
from mud.world.theworld import World
from random import choice
import string

def GenPasswd(length = 8, chars = string.letters):
    return ''.join([ choice(chars) for i in xrange(length) ])


class NewPlayerAvatar(Avatar):
    ownerPublicName = None

    def setup(self, username, role, mind):
        self.username = username
        self.world = World.byName('TheWorld')

    def perspective_newPlayer(self, publicName, fantasyName, playerPassword = None):
        if self.world.pwNewPlayer and playerPassword != self.world.pwNewPlayer:
            return (-1, 'Incorrect player password.', None)
        try:
            player = Player.byPublicName(publicName)
        except:
            pass
        else:
            return (-1, 'You already have an account on this world.', None)

        try:
            player = Player.byFantasyName(fantasyName)
        except:
            pass
        else:
            return (-1, 'That avatar name is taken, please choose another.', None)

        password = GenPasswd().upper()
        from mud.world.zone import Zone
        zone = Zone.byName('trinst')
        dzone = Zone.byName('kauldur')
        mzone = Zone.byName('trinst')
        p = Player(publicName=publicName, password=password, fantasyName=fantasyName, logZone=zone, bindZone=zone, darknessLogZone=dzone, darknessBindZone=dzone, monsterLogZone=mzone, monsterBindZone=mzone)
        p.logTransformInternal = '17.699 -288.385 121.573 0 0 1 35.9607'
        p.bindTransformInternal = '17.699 -288.385 121.573 0 0 1 35.9607'
        p.darknessLogTransformInternal = '-203.48 -395.96 150.1 0 0 1 38.92'
        p.darknessBindTransformInternal = '-203.48 -395.96 150.1 0 0 1 38.92'
        p.monsterLogTransformInternal = '-169.032 -315.986 150.9353 0 0 1 10.681'
        p.monsterBindTransformInternal = '-169.032 -315.986 150.9353 0 0 1 10.681'
        user = User(name=publicName, password=password)
        user.addRole(Role.byName('Player'))
        if publicName == NewPlayerAvatar.ownerPublicName:
            user.addRole(Role.byName('Immortal'))
            user.addRole(Role.byName('Guardian'))
            return (0, 'Immortal Account Created.\nYour password is %s' % password, password)
        else:
            return (0, 'Account Created.\nYour password is %s' % password, password)

    def perspective_queryPlayer(self, publicName):
        try:
            player = Player.byPublicName(publicName)
            return True
        except:
            pass


class QueryAvatar(Avatar):

    def perspective_retrieveWorldInfo(self):
        return (CoreSettings.WORLDTEXT, CoreSettings.WORLDPIC)