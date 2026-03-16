# Embedded file name: mud\world\guardianavatar.pyo
from mud.common.avatar import Avatar
from mud.common.permission import User, Role
from mud.world.defines import RPG_MSG_SPEECH_SYSTEM
from mud.world.guardiancommand import DoGuardianCommand
from mud.world.player import Player

class GuardianAvatar(Avatar):

    def setup(self, username, role, mind):
        self.username = username
        self.mind = mind
        self.player = Player.byPublicName(username)
        from mud.world.theworld import World
        self.world = World.byName('TheWorld')

    def perspective_command(self, cmd, args):
        DoGuardianCommand(self.player, cmd, args)

    def perspective_chat(self, args):
        if not len(args):
            return
        name = self.player.charName
        sname = name.replace(' ', '_')
        msg = ' '.join(args)
        msg = 'GM: <<a:gamelinkcharlink%s>%s</a>> %s\\n' % (sname, name, msg)
        world = self.player.world
        if world.daemonPerspective:
            world.daemonPerspective.callRemote('propagateCmd', 'receiveGMChat', name, msg)
        for p in world.activePlayers:
            if p.role.name == 'Immortal' or p.role.name == 'Guardian':
                p.sendSpeechText(RPG_MSG_SPEECH_SYSTEM, msg, name)