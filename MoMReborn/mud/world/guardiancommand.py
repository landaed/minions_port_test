# Embedded file name: mud\world\guardiancommand.pyo
import math
from defines import *
from zone import Zone
from core import *
import sys

def CmdMute(mob, args):
    if len(args) < 1:
        return
    else:
        publicName = args[0]
        from player import Player
        try:
            player = Player.byPublicName(publicName)
        except:
            try:
                from character import Character
                char = Character.byName(publicName)
                publicName = char.mob.player.publicName
            except:
                publicName = None

            try:
                player = Player.byPublicName(publicName)
            except:
                mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'Unknown player or character %s.\\n' % publicName)
                return

        if not IsUserSuperior(mob.player.publicName, publicName):
            mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'You do not have the required permission for this action.\\n')
            return
        mob.player.world.mutedPlayers[publicName] = 28800
        mob.player.sendGameText(RPG_MSG_GAME_GAINED, 'User %s has been muted.\\n' % publicName)
        return


def CmdUnmute(mob, args):
    if len(args) < 1:
        return
    else:
        publicName = args[0]
        from player import Player
        try:
            player = Player.byPublicName(publicName)
        except:
            try:
                from character import Character
                char = Character.byName(publicName)
                publicName = char.mob.player.publicName
            except:
                publicName = None

            try:
                player = Player.byPublicName(publicName)
            except:
                mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'Unknown player or character %s.\\n' % publicName)
                return

        try:
            del mob.player.world.mutedPlayers[publicName]
        except:
            pass

        mob.player.sendGameText(RPG_MSG_GAME_GAINED, 'User %s has been unmuted.\\n' % publicName)
        return


def CmdKick(mob, args):
    publicName = args[0]
    from player import Player
    try:
        player = Player.byPublicName(publicName)
    except:
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'Unknown player %s.\\n' % publicName)
        return

    if not IsUserSuperior(mob.player.publicName, publicName):
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'You do not have the required permission for this action.\\n')
        return
    mob.player.sendGameText(RPG_MSG_GAME_GAINED, 'Player %s has been kicked.\\n' % publicName)
    mob.player.world.kickPlayer(player)


def CmdUnban(mob, args):
    if not len(args):
        return
    from mud.common.permission import BannedUser
    try:
        banned = BannedUser.byName(args[0])
        banned.destroySelf()
        mob.player.sendGameText(RPG_MSG_GAME_GAINED, 'User %s has been unbanned.\\n' % args[0])
        return
    except:
        pass

    mob.player.sendGameText(RPG_MSG_GAME_DENIED, "User %s hasn't been banned.\\n" % args[0])


def CmdBan(mob, args):
    from mud.common.permission import User, Role, BannedUser
    from player import Player
    if not len(args):
        return
    try:
        player = Player.byPublicName(args[0])
    except:
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'Unknown player %s.\\n' % args[0])
        return

    if not IsUserSuperior(mob.player.publicName, player.publicName):
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'You do not have the required permission for this action.\\n')
        return
    try:
        banned = BannedUser.byName(args[0])
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'User %s already banned.\\n' % args[0])
        return
    except:
        pass

    try:
        user = User.byName(args[0])
    except:
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'Unknown user %s.\\n' % args[0])
        return

    BannedUser(name=args[0])
    mob.player.sendGameText(RPG_MSG_GAME_GAINED, 'User %s has been banned.\\n' % args[0])
    world = mob.player.world
    world.kickPlayer(player)


def CmdPlayerInfo(mob, args):
    from player import Player
    if not len(args):
        return
    try:
        player = Player.byPublicName(args[0])
    except:
        try:
            player = Player.byFantasyName(args[0])
        except:
            mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'Unknown player %s.\\n' % args[0])
            return

    ip = '???'
    try:
        if player.avatar and player.avatar.mind:
            ip = player.avatar.mind.broker.transport.getPeer().host
    except:
        pass

    mob.player.sendGameText(RPG_MSG_GAME_GAINED, 'Player Info for %s:\\n Public Name: %s\\nAvatar Name: %s\\nIP: %s\\n' % (args[0],
     player.publicName,
     player.fantasyName,
     ip))


def CmdClearFaction(mob, args):
    if not len(args):
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'Please specify the faction to reset.\\n')
        return
    target = mob.target
    if not target or not target.player:
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'Please select the player whose faction to reset.\\n')
        return
    factionName = ' '.join(args).upper()
    char = target.player.curChar
    charSpawn = char.spawn
    from faction import KOS
    KOS[charSpawn.name] = []
    for charFaction in char.characterFactions:
        if charFaction.faction.name.upper() != factionName:
            continue
        factionName = charFaction.faction.name
        charFaction.points = 0
        for factionspawn in charFaction.faction.spawns:
            try:
                if charSpawn.name in KOS[factionspawn.name]:
                    KOS[factionspawn.name].remove(charSpawn.name)
            except KeyError:
                pass

        break

    msg = "%s's faction standing with %s has been reset.\\n" % (char.name, factionName)
    mob.player.sendGameText(RPG_MSG_GAME_GAINED, msg)
    char.player.sendGameText(RPG_MSG_GAME_GAINED, msg)


def CmdInvis(mob, args):
    setInvis = mob.visibility > -100
    if len(args):
        argUpper = args[0].lower()
        if argUpper == 'on':
            setInvis = True
        elif argUpper == 'off':
            setInvis = False
        else:
            mob.player.sendGameText(RPG_MSG_GAME_DENIED, "Valid arguments are 'on' or 'off'. The argument can also be omitted to toggle.\\n")
            return
    if setInvis:
        for c in mob.player.party.members:
            if c.mob.visibility > -100:
                c.mob.visibility -= 200

        mob.player.sendGameText(RPG_MSG_GAME_GAINED, 'GM invisibility enabled.\\n')
    else:
        for c in mob.player.party.members:
            if c.mob.visibility <= -100:
                c.mob.visibility += 200

        mob.player.sendGameText(RPG_MSG_GAME_GAINED, 'GM invisibility disabled.\\n')


COMMANDS = {}
COMMANDS['ban'] = CmdBan
COMMANDS['unban'] = CmdUnban
COMMANDS['kick'] = CmdKick
COMMANDS['mute'] = CmdMute
COMMANDS['unmute'] = CmdUnmute
COMMANDS['playerinfo'] = CmdPlayerInfo
COMMANDS['clearfaction'] = CmdClearFaction
COMMANDS['resetfaction'] = CmdClearFaction
COMMANDS['invis'] = CmdInvis

def DoGuardianCommand(player, cmd, args):
    mob = player.curChar.mob
    if type(args) != list:
        args = [args]
    cmd = cmd.lower()
    if COMMANDS.has_key(cmd):
        COMMANDS[cmd](mob, args)
    else:
        print 'Unknown Command: %s' % cmd