# Embedded file name: mud\world\immortalavatar.pyo
from mud.common.permission import User, Role
from mud.common.avatar import Avatar
from mud.world.player import Player
from immortalcommand import DoImmortalCommand

class ImmortalAvatar(Avatar):

    def setup(self, username, role, mind):
        self.username = username
        self.mind = mind
        self.player = Player.byPublicName(username)
        from mud.world.theworld import World
        self.world = World.byName('TheWorld')

    def perspective_command(self, cmd, args):
        DoImmortalCommand(self.player, cmd, args)