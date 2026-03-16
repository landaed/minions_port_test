# Embedded file name: mud\world\command.pyo
from datetime import datetime
from mud.gamesettings import *
from mud.common.permission import User
from mud.world.core import *
from mud.world.defines import *
from mud.world.guild import GuildCharacters, GuildClearMOTD, GuildCreate, GuildDecline, GuildDemote, GuildDisband, GuildInvite, GuildJoin, GuildLeave, GuildPromote, GuildPublicName, GuildRemove, GuildRoster, GuildSetLeader, GuildSetMOTD
from mud.world.inn import Inn
from mud.world.messages import GameMessage
from mud.world.pet import PetCmdAttack, PetCmdDismiss, PetCmdFollowMe, PetCmdStandDown, PetCmdStay
from mud.world.shared.vocals import *
from datetime import timedelta
from math import degrees
from random import randint
from time import time as sysTime
import traceback

def CheckMuted(mob):
    player = mob.player
    if player.world.mutedPlayers.has_key(player.publicName):
        mt = player.world.mutedPlayers[player.publicName]
        m = mt / 60 + 1
        if m > 59:
            player.sendSpeechText(RPG_MSG_SPEECH_ERROR, 'You have been muted.\\n')
        else:
            player.sendSpeechText(RPG_MSG_SPEECH_ERROR, 'You have been muted and will be able to speak in %i minutes.\\n' % m)
        return True
    return False


def CmdLadder(mob, args):
    from mud.world.newplayeravatar import NewPlayerAvatar
    mob.player.sendGameText(RPG_MSG_GAME_EVENT, 'The ladder command is currently inactive.\\n')
    return
    text = '\\n------------------------------------\\n'
    text += 'Most Experienced Characters\\n'
    text += '------------------------------------\\n'
    chars = {}
    players = {}
    cursor = mob.spawn.__class__._connection.getConnection().cursor()
    try:
        cursor.execute('select name,xp_primary,xp_secondary,xp_tertiary,player_id from character;')
        for r in cursor.fetchall():
            name, xpPrimary, xpSecondary, xpTertiary, playerID = r
            c2 = mob.spawn.__class__._connection.getConnection().cursor()
            c2.execute('select public_name from player where id = %i;' % playerID)
            if c2.fetchone()[0] == NewPlayerAvatar.ownerPublicName:
                c2.close()
                continue
            c2.close()
            c2 = mob.spawn.__class__._connection.getConnection().cursor()
            c2.execute("select realm from spawn where name = '%s';" % name)
            if c2.fetchone()[0] == RPG_REALM_MONSTER:
                c2.close()
                continue
            c2.close()
            xp = xpPrimary + xpSecondary + xpTertiary
            chars[name] = xp
            players[name] = playerID

        v = chars.values()
        v.sort()
        v.reverse()
        v = v[:9]
        x = 1
        for xp in v:
            if x > 20:
                break
            for c, cxp in chars.iteritems():
                if cxp == xp:
                    cursor.execute("select pclass_internal,plevel,sclass_internal,slevel,tclass_internal,tlevel from spawn where name = '%s';" % c)
                    pclassInternal, plevel, sclassInternal, slevel, tclassInternal, tlevel = cursor.fetchone()
                    text += '%i.  <%s> %s (%i) ' % (x,
                     c,
                     pclassInternal,
                     plevel)
                    if slevel:
                        text += '%s (%i) ' % (sclassInternal, slevel)
                    if tlevel:
                        text += '%s (%i) ' % (tclassInternal, tlevel)
                    cursor.execute('select fantasy_name from player where id = %i;' % players[c])
                    pname = cursor.fetchone()[0]
                    text += '- %s\\n' % pname
                    x += 1

        text = str(text)
        mob.player.sendGameText(RPG_MSG_GAME_EVENT, text)
    except:
        traceback.print_exc()

    cursor.close()


def CmdSuicide(mob, args):
    for c in mob.player.party.members:
        if not c.dead:
            c.mob.die()


def CmdUnstick(mob, args):
    for c in mob.player.party.members:
        if c.mob.unstickReuse:
            mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'You must wait a short time before trying to unstick again.\\n')
            return

    mob.player.sendGameText(RPG_MSG_GAME_GAINED, 'Please try and unstick yourself.\\n')
    for c in mob.player.party.members:
        if not c.mob.unstick:
            c.mob.unstickReuse = 270
            c.mob.unstick = 18
            c.mob.flying += 1.0


def CmdAvatar(mob, args):
    if not len(args):
        return
    name = args[0].upper()
    index = 0
    for m in mob.player.party.members:
        if m.name.upper() == name:
            if mob.player.modelChar == m:
                return
            mob.player.modelChar = m
            mob.player.modelIndex = index
            mob.player.avatarCharName = m.name
            mob.player.zone.simAvatar.mind.callRemote('setPlayerSpawnInfo', mob.player.simObject.id, m.spawn.name)
            mob.player.sendGameText(RPG_MSG_GAME_GAINED, 'Your avatar has been set to %s.\\n' % m.name)
            return
        index += 1


def CmdWho(mob, args):
    if len(args):
        original = ' '.join(args)
        filter = original.upper()
        for pname, info in mob.player.world.characterInfos.iteritems():
            prefix, cname, realm, pclass, sclass, tclass, plevel, slevel, tlevel, zone, guild = info
            if cname.upper() == filter:
                classes = (pclass, sclass, tclass)
                levels = (plevel, slevel, tlevel)
                text = '%s (%s %s)\\n' % (' '.join([prefix, cname]), '/'.join((RPG_CLASS_ABBR[klass] for klass in classes if klass)), '/'.join(('%i' % level for level in levels if level)))
                mob.player.sendGameText(RPG_MSG_GAME_EVENT, text)
                return

        try:
            charname, guildname, wname, zname = mob.player.world.globalPlayers[filter]
            mob.player.sendGameText(RPG_MSG_GAME_EVENT, '%s is on %s\\n' % (charname, wname))
        except KeyError:
            mob.player.sendGameText(RPG_MSG_GAME_DENIED, '%s is not currently logged in.\\n' % original)

        return
    text = ''
    for pname, info in mob.player.world.characterInfos.iteritems():
        prefix, cname, realm, pclass, sclass, tclass, plevel, slevel, tlevel, zone, guild = info
        classes = (pclass, sclass, tclass)
        levels = (plevel, slevel, tlevel)
        text += '%s (%s %s)\\n' % (' '.join([prefix, cname]), '/'.join((RPG_CLASS_ABBR[klass] for klass in classes if klass)), '/'.join(('%i' % level for level in levels if level)))

    text += '\\n'
    mob.player.sendGameText(RPG_MSG_GAME_EVENT, text)


def CmdWhoOld(mob, args):
    filter = None
    if len(args):
        filter = ' '.join(args).upper()
    text = ''
    for p in mob.player.world.activePlayers:
        if filter and p.publicName.upper() != filter:
            continue
        prefix = ''
        if p.avatar and p.avatar.masterPerspective:
            if p.avatar.masterPerspective.avatars.has_key('GuardianAvatar'):
                prefix = '(Guardian) '
            if p.avatar.masterPerspective.avatars.has_key('ImmortalAvatar'):
                prefix = '(Immortal) '
        if p.enteringWorld:
            text += '%s%s <Entering World> ' % (prefix, p.name)
        elif p.zone:
            text += '%s%s <%s> ' % (prefix, p.name, p.zone.zone.niceName)
        else:
            text += '%s%s ' % (prefix, p.name)
        if p.party and len(p.party.members):
            c = p.party.members[0]
            classes = (c.spawn.pclassInternal, c.spawn.sclassInternal, c.spawn.tclassInternal)
            levels = (c.spawn.plevel, c.spawn.slevel, c.spawn.tlevel)
            text += '(%s %s)\\n' % ('/'.join((RPG_CLASS_ABBR[klass] for klass in classes if klass)), '/'.join(('%i' % level for level in levels if level)))
        else:
            text += '\\n'

    text += '\\n'
    mob.player.sendGameText(RPG_MSG_GAME_EVENT, text)
    return


def CmdEval(mob, args):
    target = mob.target
    if not target:
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, '%s has no target.\\n' % mob.name)
        return
    if target.level - mob.level <= -5:
        color, text = RPG_MSG_GAME_GREEN, '%s is no match for %s.\\n' % (target.name, mob.name)
    elif target.level - mob.level <= -1:
        color, text = RPG_MSG_GAME_BLUE, '%s might challenge %s.\\n' % (target.name, mob.name)
    elif target.level - mob.level == 0:
        color, text = RPG_MSG_GAME_WHITE, '%s is an even match for %s.\\n' % (target.name, mob.name)
    elif target.level - mob.level <= 2:
        color, text = RPG_MSG_GAME_YELLOW, '%s has a significant advantage over %s.\\n' % (target.name, mob.name)
    else:
        color, text = RPG_MSG_GAME_RED, '%s would cream %s.\\n' % (target.name, mob.name)
    if target.spawn.desc:
        if target.player:
            mob.player.sendGameText(RPG_MSG_GAME_YELLOW, target.spawn.desc.replace('\n', '\\n') + '  ', stripML=True)
        else:
            mob.player.sendGameText(RPG_MSG_GAME_YELLOW, target.spawn.desc + '  ')
    factionRelColoring = {RPG_FACTION_HATED: RPG_MSG_GAME_RED,
     RPG_FACTION_DISLIKED: RPG_MSG_GAME_BLUE,
     RPG_FACTION_UNDECIDED: RPG_MSG_GAME_WHITE,
     RPG_FACTION_LIKED: RPG_MSG_GAME_YELLOW,
     RPG_FACTION_ADORED: RPG_MSG_GAME_GREEN}
    standing, desc = GetFactionRelationDesc(mob, target)
    mob.player.sendGameText(factionRelColoring[standing], desc)
    mob.player.sendGameText(color, text)


def CmdDesc(mob, args):
    target = mob.target
    player = mob.player
    if not target:
        player.sendGameText(RPG_MSG_GAME_DENIED, '%s has no target.\\n' % mob.name)
        return
    player.avatar.sendTgtDesc(mob, target)


def CmdMyDesc(mob, args):
    player = mob.player
    player.avatar.sendTgtDesc(mob, mob)


def CmdPet(mob, args):
    if not len(args):
        return
    if not mob.pet:
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, '%s has no pet.\\n' % mob.name)
        return
    cmd = args[0].upper()
    if cmd == 'ATTACK':
        if mob.target:
            PetCmdAttack(mob.pet, mob.target)
    elif cmd == 'STAY':
        PetCmdStay(mob.pet)
    elif cmd == 'FOLLOWME':
        PetCmdFollowMe(mob.pet)
    elif cmd == 'STANDDOWN':
        PetCmdStandDown(mob.pet)
    elif cmd == 'DISMISS':
        PetCmdDismiss(mob.pet)


def CmdBind(mob, args):
    pos = mob.simObject.position
    for bp in mob.zone.bindpoints:
        x = pos[0] - bp[0]
        y = pos[1] - bp[1]
        z = pos[2] - bp[2]
        distSQ = x * x + y * y + z * z
        if distSQ <= 144:
            mob.player.mind.callRemote('playSound', 'sfx/Magic_Appear01.ogg')
            mob.player.sendGameText(RPG_MSG_GAME_GAINED, 'You feel a connection to this place.\\n')
            darkness = mob.player.darkness
            if darkness:
                mob.player.darknessBindZone = mob.zone.zone
            elif mob.player.monster:
                mob.player.monsterBindZone = mob.zone.zone
            else:
                mob.player.bindZone = mob.zone.zone
            transform = list(mob.simObject.position)
            transform.extend(list(mob.simObject.rotation))
            transform[-1] = degrees(transform[-1])
            if darkness:
                mob.player.darknessBindTransform = transform
            elif mob.player.monster:
                mob.player.monsterBindTransform = transform
            else:
                mob.player.bindTransform = transform
            return

    bindzone = ''
    if mob.player.darkness:
        bindzone = mob.player.darknessBindZone.niceName
    elif mob.player.monster:
        bindzone = mob.player.monsterBindZone.niceName
    else:
        bindzone = mob.player.bindZone.niceName
    mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'You cannot bind here and remain bound at %s\\n' % bindzone)


def CmdZoneInteract(mob, args, trigger = None):
    player = mob.player
    player.endInteraction()
    zone = mob.zone
    myPos = mob.simObject.position
    bestdt = None
    bestdistSQ = 999999
    for dt in zone.dialogTriggers:
        if not trigger:
            destPos = dt.position
            x = myPos[0] - destPos[0]
            y = myPos[1] - destPos[1]
            z = myPos[2] - destPos[2]
            distSQ = x * x + y * y + z * z
            if distSQ <= dt.range * dt.range and distSQ < bestdistSQ:
                bestdistSQ = distSQ
                bestdt = dt
        elif dt.dialog.name == trigger:
            bestdt = dt
            break

    if bestdt:
        dialog = bestdt.dialog
        if dialog.greeting:
            dialog.setLine(player, dialog.greeting, dialog.title)
            if player.dialog:
                player.interacting = bestdt
                player.mind.callRemote('setVendorStock', False, None, 0)
                player.mind.callRemote('openNPCWnd', dialog.title)
    return


def gotCheckIgnoreTrade(ignored, player, oplayer):
    if ignored:
        player.sendGameText(RPG_MSG_GAME_DENIED, '%s is ignoring you.\\n' % oplayer.charName)
        return
    from mud.world.trading import Trade
    Trade(player, oplayer)


def gotCheckIgnoreTradeError(error):
    print 'Error in checkIgnore: %s' % str(error)


def CmdInteract(mob, args):
    target = mob.target
    if not target:
        return
    else:
        player = mob.player
        if player.interacting or player.trade:
            return
        if mob.character.dead:
            return
        if target.player:
            otherPlayer = target.player
            if otherPlayer == player:
                return
            if not player.cursorItem:
                return
            if otherPlayer.interacting or otherPlayer.trade:
                player.sendGameText(RPG_MSG_GAME_DENIED, '%s is busy.\\n' % otherPlayer.charName)
                return
            d = otherPlayer.mind.callRemote('checkIgnore', player.charName)
            d.addCallback(gotCheckIgnoreTrade, player, otherPlayer)
            d.addErrback(gotCheckIgnoreTradeError)
            return
        if IsKOS(target, mob):
            for c in player.party.members:
                c.mob.autoAttack = True
                c.mob.attackOn()

            return
        spawn = target.spawn
        if spawn.flags & RPG_SPAWN_INN:
            if not player.inn:
                if GetRangeMin(mob, target) <= 4:
                    player.inn = Inn(target, player)
                else:
                    player.sendGameText(RPG_MSG_GAME_DENIED, '%s is too far away.\\n' % target.name)
            return
        if target.master and target.master.player == player:
            player.mind.callRemote('setCurCharIndex', target.master.charIndex)
            player.mind.callRemote('openPetWindow')
            return
        if spawn.vendorProto and not target.vendor:
            spawn.vendorProto.createVendorInstance(target)
        vendor = target.vendor
        if not (spawn.dialog or vendor or spawn.flags & RPG_SPAWN_BANKER):
            return
        if GetRangeMin(mob, target) > 2:
            player.sendGameText(RPG_MSG_GAME_DENIED, '%s is too far away.\\n' % target.name)
            return
        if target.target or target.battle and not target.battle.over:
            player.sendGameText(RPG_MSG_GAME_DENIED, '%s is busy.\\n' % target.name)
            return
        if spawn.flags & RPG_SPAWN_BANKER:
            player.mind.callRemote('setVendorStock', False, None, 0)
            player.mind.callRemote('setInitialInteraction', None, None)
            player.mind.callRemote('openNPCWnd', spawn.name, True)
            return
        if not CoreSettings.SINGLEPLAYER and target.interactTimes.has_key(player):
            t = sysTime() - target.interactTimes[player]
            if t < 15:
                player.sendGameText(RPG_MSG_GAME_DENIED, '%s is busy and can be with you in %i seconds.\\n' % (target.name, 16 - t))
                return
        if target.interacting:
            t = sysTime() - target.interactTimes[target.interacting]
            if t > 60:
                target.interacting.endInteraction()
            else:
                interactingPlayer = target.interacting
                interactingCharName = interactingPlayer.fantasyName
                if interactingPlayer.curChar:
                    interactingCharName = interactingPlayer.curChar.name
                player.sendGameText(RPG_MSG_GAME_DENIED, '%s is now busy with %s and will be available in %i seconds.\\n' % (target.name, interactingCharName, 61 - t))
                return
        if not randint(0, 9):
            target.vocalize(VOX_LAUGH, player)
        elif not randint(0, 4):
            target.vocalize(VOX_GRUNT, player)
        else:
            target.vocalize(VOX_SURPRISED, player)
        if not vendor and (not spawn.dialog or not spawn.dialog.greeting):
            player.sendGameText(RPG_MSG_GAME_DENIED, '%s snorts at you.\\n' % target.name)
            return
        if vendor:
            vendor.sendStock(player)
        else:
            player.mind.callRemote('setVendorStock', False, None, 0)
        dialog = spawn.dialog
        if dialog and dialog.greeting:
            if not len(dialog.greeting.choices):
                player.sendGameText(RPG_MSG_GAME_NPC_SPEECH, '%s says, "%s"\\n' % (target.name, dialog.greeting.text))
                if not vendor:
                    return
            dialog.setLine(player, dialog.greeting, spawn.name)
        else:
            player.mind.callRemote('setInitialInteraction', None, None)
        player.interacting = target
        target.interacting = player
        target.interactTimes[player] = sysTime()
        player.mind.callRemote('openNPCWnd', spawn.name)
        return


def CmdAttack(mob, args):
    if len(args):
        if args[0].upper() == 'ON':
            attacking = True
        elif args[0].upper() == 'OFF':
            attacking = False
        else:
            attacking = not mob.autoAttack
    else:
        attacking = not mob.autoAttack
    mob.autoAttack = attacking
    if mob.character.dead:
        return
    if attacking and mob.target:
        if AllowHarmful(mob, mob.target):
            mob.attackOn()
        else:
            mob.attackOff()
    else:
        mob.attackOff()


def CmdRangedAttack(mob, args):
    mob.shootRanged()


def CmdTargetId(mob, args):
    if 2 > len(args):
        return
    else:
        mobToTargetId = int(args[0])
        cycle = int(args[1])
        if not mobToTargetId:
            mob.zone.setTarget(mob, None)
            return
        for char in mob.player.party.members:
            if not char.dead and char.mob.id == mobToTargetId:
                mob.zone.setTarget(mob, char.mob)
                return

        if mob.player.zone == None:
            return
        if mob.simObject == None:
            return
        simLookup = mob.zone.simAvatar.simLookup
        mobLookup = mob.zone.mobLookup
        for id in mob.simObject.canSee:
            try:
                mobInZone = mobLookup[simLookup[id]]
            except KeyError:
                continue

            if mobInZone.id == mobToTargetId:
                if not cycle:
                    mob.zone.setTarget(mob, mobInZone, checkVisibility=True)
                    return
                else:
                    playerToTarget = mobInZone.player
                    if not playerToTarget or not mob.target:
                        if not mobInZone.detached:
                            mob.zone.setTarget(mob, mobInZone, checkVisibility=True)
                        return
                    cycleMobs = [ char.mob for char in playerToTarget.party.members if not char.dead ]
                    if not cycleMobs:
                        return
                    if 1 == len(cycleMobs):
                        mob.zone.setTarget(mob, cycleMobs[0])
                        return
                    currentTargetId = mob.target.id
                    nextIndex = 0
                    for cycleMob in cycleMobs:
                        nextIndex += 1
                        if cycleMob.id == currentTargetId:
                            break
                    else:
                        return

                    mob.zone.setTarget(mob, cycleMobs[nextIndex % len(cycleMobs)])
                    return

        if 3 <= len(args):
            mob.player.sendGameText(RPG_MSG_GAME_DENIED, '%s cannot target %s.\\n' % (mob.name, ' '.join(args[2:])))
        return


def CmdWorldMsg(mob, args):
    if CheckMuted(mob):
        return
    player = mob.player
    if not len(args):
        return
    name = player.charName
    sname = name.replace(' ', '_')
    msg = ' '.join(args)
    msg = 'World: <<a:gamelinkcharlink%s>%s</a>> %s\\n' % (sname, name, msg)
    world = player.world
    if world.daemonPerspective:
        world.daemonPerspective.callRemote('propagateCmd', 'sendWorldMsg', name, msg)
    for p in world.activePlayers:
        p.sendSpeechText(RPG_MSG_SPEECH_WORLD, msg, name)


def CmdGuildMsg(mob, args):
    if CheckMuted(mob):
        return
    player = mob.player
    guild = player.guildName
    if not guild:
        player.sendGameText(RPG_MSG_GAME_DENIED, 'You are not a member of any guild.\\n')
        return
    if not len(args):
        return
    name = player.charName
    sname = name.replace(' ', '_')
    msg = ' '.join(args)
    msg = 'Guild: <<a:gamelinkcharlink%s>%s</a>> %s\\n' % (sname, name, msg)
    world = player.world
    if world.daemonPerspective:
        world.daemonPerspective.callRemote('propagateCmd', 'sendGuildMsg', name, msg, guild)
    for p in world.activePlayers:
        if p.guildName == guild:
            p.sendSpeechText(RPG_MSG_SPEECH_GUILD, msg, name)


def CmdZoneMsg(mob, args):
    if CheckMuted(mob):
        return
    if not len(args):
        return
    msg = ' '.join(args)
    charName = mob.player.charName
    scharName = charName.replace(' ', '_')
    msg = 'Zone: <<a:gamelinkcharlink%s>%s</a>> %s\\n' % (scharName, charName, msg)
    for p in mob.zone.players:
        p.sendSpeechText(RPG_MSG_SPEECH_ZONE, msg, charName)


def CmdSayMsg(mob, args):
    if CheckMuted(mob):
        return
    player = mob.player
    if not len(args):
        return
    msg = ' '.join(args)
    charName = mob.player.charName
    scharName = charName.replace(' ', '_')
    othermsg = '<a:gamelinkcharlink%s>%s</a> says, \\"%s\\"\\n' % (scharName, charName, msg)
    for p in mob.zone.players:
        if p == player:
            p.sendSpeechText(RPG_MSG_SPEECH_SAY, 'You say, \\"%s\\"\\n' % msg, charName)
        elif GetRange(mob, p.curChar.mob) < 30:
            p.sendSpeechText(RPG_MSG_SPEECH_SAY, othermsg, charName)


def CmdLaugh(mob, args):
    mob.cancelStatProcess('feignDeath', '$tgt is obviously not dead!\\n')
    mob.cancelStatProcess('sneak', '$tgt is no longer sneaking!\\n')
    mob.player.modelChar.mob.vocalize(VOX_LAUGH)
    if not args:
        if mob.target:
            args = ['laughs at %s.' % mob.target.name]
        else:
            args = ['laughs.']
    CmdEmote(mob, args)


def CmdScream(mob, args):
    mob.cancelStatProcess('feignDeath', '$tgt is obviously not dead!\\n')
    mob.cancelStatProcess('sneak', '$tgt is no longer sneaking!\\n')
    mob.player.modelChar.mob.vocalize(VOX_MADSCREAM)
    if not args:
        if mob.target:
            args = ['screams at %s.' % mob.target.name]
        else:
            args = ['screams.']
    CmdEmote(mob, args)


def CmdGroan(mob, args):
    mob.cancelStatProcess('feignDeath', '$tgt is obviously not dead!\\n')
    mob.cancelStatProcess('sneak', '$tgt is no longer sneaking!\\n')
    mob.player.modelChar.mob.vocalize(VOX_GROAN)
    if not args:
        if mob.target:
            args = ['groans at %s.' % mob.target.name]
        else:
            args = ['groans.']
    CmdEmote(mob, args)


def CmdEmote(mob, args):
    if CheckMuted(mob):
        return
    if not len(args):
        return
    charName = mob.player.charName
    scharName = charName.replace(' ', '_')
    msg = '<a:gamelinkcharlink%s>%s</a> %s\\n' % (scharName, charName, ' '.join(args))
    for p in mob.zone.players:
        if p == mob.player:
            p.sendSpeechText(RPG_MSG_SPEECH_EMOTE, msg, charName)
        elif GetRange(mob, p.curChar.mob) < 30:
            p.sendSpeechText(RPG_MSG_SPEECH_EMOTE, msg, charName)


def CmdCamp(mob, args):
    player = mob.player
    player.logout()


def CmdAllianceMsg(mob, args):
    if not len(args):
        return
    mob.player.alliance.message(mob.player, ' '.join(args))


def CmdTime(mob, args):
    time = mob.player.world.time
    am = True
    hour = time.hour
    if 10 >= hour >= 4:
        msg = 'It is %i in the morning.\\n' % hour
    elif 12 > hour > 10:
        msg = 'It is %i in the late morning.\\n' % hour
    elif hour == 12:
        msg = 'It is around noon.\\n'
    elif 16 >= hour > 12:
        msg = 'It is %i in the afternoon.\\n' % (hour - 12)
    elif 19 >= hour > 16:
        msg = 'It is %i in the early evening.\\n' % (hour - 12)
    elif 24 >= hour > 16:
        msg = 'It is %i at night.\\n' % (hour - 12)
    elif hour == 0:
        msg = 'It is around midnight.\\n'
    else:
        msg = 'It is %i at night.\\n' % hour
    mob.player.sendGameText(RPG_MSG_GAME_GLOBAL, msg)


def CmdUpTime(mob, args):
    uptime = sysTime() - mob.player.world.launchTime
    t = timedelta(0, uptime)
    msg = 'This world server has been up for %s.\\n' % str(t)
    mob.player.sendGameText(RPG_MSG_GAME_GLOBAL, msg)


def CmdVersion(mob, args):
    msg = 'Minions of Mirth UW:\\n  World Server 2.01\\n  Database 2.0\\n  %sClient %s\\n' % (GAMEBUILD_PREFIX, GAMEVERSION)
    mob.player.sendGameText(RPG_MSG_GAME_GLOBAL, msg)


def CmdDance(mob, args):
    mob.cancelStatProcess('feignDeath', '$tgt is obviously not dead!\\n')
    mob.zone.simAvatar.mind.callRemote('playAnimation', mob.simObject.id, 'dance')
    if not args:
        if mob.target:
            args = ['dances for %s.' % mob.target.name]
        else:
            args = ['dances.']
    CmdEmote(mob, args)


def CmdPoint(mob, args):
    mob.cancelStatProcess('feignDeath', '$tgt is obviously not dead!\\n')
    mob.zone.simAvatar.mind.callRemote('playAnimation', mob.simObject.id, 'point')
    if not args:
        if mob.target:
            args = ['points at %s.' % mob.target.name]
        else:
            args = ['points ahead.']
    CmdEmote(mob, args)


def CmdAgree(mob, args):
    mob.cancelStatProcess('feignDeath', '$tgt is obviously not dead!\\n')
    mob.zone.simAvatar.mind.callRemote('playAnimation', mob.simObject.id, 'agree')
    if not args:
        if mob.target:
            args = ['agrees with %s.' % mob.target.name]
        else:
            args = ['agrees.']
    CmdEmote(mob, args)


def CmdDisagree(mob, args):
    mob.cancelStatProcess('feignDeath', '$tgt is obviously not dead!\\n')
    mob.zone.simAvatar.mind.callRemote('playAnimation', mob.simObject.id, 'disagree')
    if not args:
        if mob.target:
            args = ['disagrees with %s.' % mob.target.name]
        else:
            args = ['disagrees.']
    CmdEmote(mob, args)


def CmdBow(mob, args):
    mob.cancelStatProcess('feignDeath', '$tgt is obviously not dead!\\n')
    mob.zone.simAvatar.mind.callRemote('playAnimation', mob.simObject.id, 'bow')
    if not args:
        if mob.target:
            args = ['bows before %s.' % mob.target.name]
        else:
            args = ['bows.']
    CmdEmote(mob, args)


def CmdWave(mob, args):
    mob.cancelStatProcess('feignDeath', '$tgt is obviously not dead!\\n')
    mob.zone.simAvatar.mind.callRemote('playAnimation', mob.simObject.id, 'wave')
    if not args:
        if mob.target:
            args = ['waves at %s.' % mob.target.name]
        else:
            args = ['waves.']
    CmdEmote(mob, args)


def CmdCycleTarget(mob, args, doMouse = True, useInputMob = False, reverse = False):
    if not useInputMob:
        mob = mob.player.curChar.mob
    zone = mob.zone
    simAvatar = zone.simAvatar
    targets = []
    for id in mob.simObject.canSee:
        try:
            otherMob = zone.mobLookup[simAvatar.simLookup[id]]
        except KeyError:
            continue

        kos = IsKOS(otherMob, mob)
        if otherMob.player or otherMob.master and otherMob.master.player:
            kos = kos or AllowHarmful(mob, otherMob)
        if not kos or otherMob.detached:
            continue
        if not IsVisible(mob, otherMob):
            continue
        if GetRange(otherMob, mob) < 100:
            targets.append(id)

    if not len(targets):
        return
    if not mob.target or mob.target.simObject.id not in targets or len(targets) == 1:
        tid = targets[0]
    else:
        index = targets.index(mob.target.simObject.id)
        if reverse:
            index -= 1
            if index < 0:
                index = len(targets) - 1
        else:
            index += 1
            if index == len(targets):
                index = 0
        tid = targets[index]
    tmob = zone.mobLookup[simAvatar.simLookup[tid]]
    zone.setTarget(mob, tmob)
    if doMouse:
        mob.player.mind.callRemote('mouseSelect', mob.charIndex, tmob.id)


def CmdCycleTargetBackwards(mob, args):
    CmdCycleTarget(mob, args, True, False, True)


def CmdTargetNearest(mob, args, doMouse = True, useInputMob = False):
    if not useInputMob:
        mob = mob.player.curChar.mob
    zone = mob.zone
    simAvatar = zone.simAvatar
    target = -1
    best = 999999
    for id in mob.simObject.canSee:
        try:
            otherMob = zone.mobLookup[simAvatar.simLookup[id]]
        except KeyError:
            continue

        kos = IsKOS(otherMob, mob)
        if otherMob.player or otherMob.master and otherMob.master.player:
            kos = kos or AllowHarmful(mob, otherMob)
        if not kos or otherMob.detached:
            continue
        if not IsVisible(mob, otherMob):
            continue
        r = GetRange(otherMob, mob)
        if r < best:
            target = id
            best = r

    if target == -1:
        return
    tmob = zone.mobLookup[simAvatar.simLookup[target]]
    zone.setTarget(mob, tmob)
    if doMouse:
        mob.player.mind.callRemote('mouseSelect', mob.charIndex, tmob.id)


def FindMobByName(src, nameToFind):
    nameToFind = nameToFind.upper()
    for character in src.player.party.members:
        if character.name.upper() == nameToFind:
            if not character.mob.detached:
                return character.mob
            else:
                return None

    zone = src.zone
    simLookup = zone.simAvatar.simLookup
    mobLookup = zone.mobLookup
    for id in src.simObject.canSee:
        try:
            otherMob = mobLookup[simLookup[id]]
        except KeyError:
            continue

        if otherMob.player:
            for character in otherMob.player.party.members:
                if character.name.upper() == nameToFind:
                    mobToTarget = character.mob
                    if not mobToTarget.detached and IsVisible(src, mobToTarget):
                        return mobToTarget
                    else:
                        return None

        elif otherMob.name.upper() == nameToFind:
            if not otherMob.detached and IsVisible(src, otherMob):
                return otherMob

    return None


def CmdAssist(mob, args):
    if not len(args):
        if mob.target:
            mob.zone.setTarget(mob, mob.target.target)
        return
    mobToAssistName = ' '.join(args)
    if mobToAssistName.upper() == 'PET':
        if mob.pet:
            mob.zone.setTarget(mob, mob.pet.target)
            return
        else:
            mob.player.sendGameText(RPG_MSG_GAME_DENIED, '%s cannot assist pet.\\n' % mob.name)
            return
    mobToAssist = FindMobByName(mob, mobToAssistName)
    if mobToAssist:
        mob.zone.setTarget(mob, mobToAssist.target, checkVisibility=True)
        return
    mob.player.sendGameText(RPG_MSG_GAME_DENIED, '%s cannot assist %s.\\n' % (mob.name, mobToAssistName))


def CmdTarget(mob, args):
    mobToTargetName = ' '.join(args)
    if mobToTargetName.upper() == 'PET':
        if mob.pet:
            mob.zone.setTarget(mob, mob.pet)
            return
        else:
            mob.player.sendGameText(RPG_MSG_GAME_DENIED, '%s cannot target pet.\\n' % mob.name)
            return
    mobToTarget = FindMobByName(mob, mobToTargetName)
    if mobToTarget:
        mob.zone.setTarget(mob, mobToTarget)
        return
    mob.player.sendGameText(RPG_MSG_GAME_DENIED, '%s cannot target %s.\\n' % (mob.name, mobToTargetName))


def CmdCast(mob, args):
    if mob.casting or mob.detached:
        return
    spellToCastName = ' '.join(args)
    spellToCastNameUpper = spellToCastName.upper()
    for knownSpell in mob.character.spells:
        spellToCastProto = knownSpell.spellProto
        if spellToCastProto.name.upper() == spellToCastNameUpper:
            if spellToCastProto.qualify(mob):
                mob.cast(spellToCastProto, knownSpell.level)
            else:
                mob.player.sendGameText(RPG_MSG_GAME_DENIED, '%s does not know how to cast %s.\\n' % (mob.name, spellToCastName))
            return
    else:
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, '%s cannot cast %s.\\n' % (mob.name, spellToCastName))


def CmdSkill(mob, args):
    skillToUseName = ' '.join(args)
    skillToUseNameUpper = skillToUseName.upper()
    for knownSkill in mob.mobSkillProfiles.iterkeys():
        if knownSkill.upper() == skillToUseNameUpper:
            from mud.world.skill import UseSkill
            UseSkill(mob, mob.target, knownSkill)
            return
    else:
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, '%s cannot use the %s skill.\\n' % (mob.name, skillToUseName))
        return


def CmdInvite(mob, args):
    mob.player.avatar.perspective_invite()


def CmdChannel(mob, args):
    player = mob.player
    if len(args) < 2:
        return
    channel = args[0].lower()
    mode = args[1].lower()
    if channel == 'world':
        if mode == 'off':
            player.channelWorld = False
            player.sendGameText(RPG_MSG_GAME_GAINED, 'You are no longer listening to world chat.\\n')
        else:
            player.channelWorld = True
            player.sendGameText(RPG_MSG_GAME_GAINED, 'You are now listening to world chat.\\n')
    if channel == 'zone':
        if mode == 'off':
            player.channelZone = False
            player.sendGameText(RPG_MSG_GAME_GAINED, 'You are no longer listening to zone chat.\\n')
        else:
            player.channelZone = True
            player.sendGameText(RPG_MSG_GAME_GAINED, 'You are now listening to zone chat.\\n')
    if channel == 'combat':
        if mode == 'off':
            player.channelCombat = False
            player.sendGameText(RPG_MSG_GAME_GAINED, "You are no longer listening to other's combat messages.\\n")
        else:
            player.channelCombat = True
            player.sendGameText(RPG_MSG_GAME_GAINED, "You are now listening to other's combat messages.\\n")


def CmdStopCast(mob, args):
    if mob.casting:
        if mob.stopCastingTimer:
            mob.player.sendGameText(RPG_MSG_GAME_DENIED, '%s cannot stop casting at this time.\\n' % mob.name)
            return
        mob.stopCastingTimer = 60
        mob.casting.cancel()
        mob.player.sendGameText(RPG_MSG_GAME_YELLOW, '%s stops casting.\\n' % mob.name)


def CmdCart(mob, args):
    player = mob.player
    player.didCheckGrants = -1
    player.sendGameText(RPG_MSG_GAME_GAINED, 'checking cart for %s...\\n' % player.publicName)


def CmdDisenchant(mob, args):
    from mud.world.crafting import DisenchantCmd
    DisenchantCmd(mob, ' '.join(args).upper())


def CmdEnchant(mob, args):
    from mud.world.crafting import EnchantCmd
    EnchantCmd(mob, ' '.join(args).upper())


def CmdRoll(mob, args):
    r = randint(1, 100)
    charName = mob.player.charName
    GameMessage(RPG_MSG_GAME_LEVELGAINED, mob.zone, mob, mob, '<a:gamelinkcharlink%s>%s</a> has rolled a %i.\\n' % (charName.replace(' ', '_'), charName, r), mob.simObject.position, 20)


def CmdUnlearn(mob, args):
    name = ' '.join(args)
    if not len(name):
        return
    name = name.lower()
    for spell in mob.character.spells:
        if spell.spellProto.name.lower() == name:
            sname = spell.spellProto.name
            spell.destroySelf()
            mob.character.spellsDirty = True
            mob.player.cinfoDirty = True
            mob.player.sendGameText(RPG_MSG_GAME_GAINED, '%s forgets all about the %s spell.\\n' % (mob.name, sname))
            return

    mob.player.sendGameText(RPG_MSG_GAME_DENIED, "%s doesn't know the %s spell.\\n" % (mob.name, name))


def CmdWalk(mob, args):
    player = mob.player
    if len(args):
        if 'ON' in args[0].upper():
            arg = True
        else:
            arg = False
    else:
        arg = not player.walk
    if arg != player.walk:
        if arg:
            player.sendGameText(RPG_MSG_GAME_EVENT, '%s slows to a casual pace.\\n' % mob.name)
        else:
            player.sendGameText(RPG_MSG_GAME_EVENT, '%s speeds up the pace.\\n' % mob.name)
    player.walk = arg


def CmdClearLastName(mob, args):
    player = mob.player
    if not player.curChar.lastName:
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, "%s doesn't have a last name.\\n" % player.curChar.name)
    player.curChar.lastName = ''
    player.zone.simAvatar.setDisplayName(player)
    mob.player.sendGameText(RPG_MSG_GAME_GAINED, "%s's last name has been cleared.\\n" % player.curChar.name)


def CmdLastName(mob, args):
    player = mob.player
    if player.curChar.mob.plevel < 25:
        player.sendGameText(RPG_MSG_GAME_DENIED, '%s must be level 25 before acquiring a last name.\\n' % mob.player.curChar.name)
        return
    if len(args) != 1:
        player.sendGameText(RPG_MSG_GAME_DENIED, 'lastname: incorrect number of arguments\\n')
        return
    last = args[0]
    if len(last) > 12:
        player.sendGameText(RPG_MSG_GAME_DENIED, 'lastname: must be less than 13 characters\\n')
        return
    if len(last) < 4:
        player.sendGameText(RPG_MSG_GAME_DENIED, 'lastname: must be at least 4 characters\\n')
        return
    if not last.isalpha():
        player.sendGameText(RPG_MSG_GAME_DENIED, 'Guild names must not contain numbers, spaces, or punctuation marks.\\n')
        return
    player.curChar.lastName = last.capitalize()
    player.zone.simAvatar.setDisplayName(player)
    c = player.curChar
    player.sendGameText(RPG_MSG_GAME_GAINED, '%s is now known as %s %s!\\n' % (c.name, c.name, c.lastName))


def CmdChangeClass(mob, args):
    if len(args) < 3:
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'changeclass: incorrect number of arguments')
        return
    which, name = args[:2]
    klass = ' '.join(args[2:])
    which = which.upper()
    if which not in ('PRIMARY', 'SECONDARY', 'TERTIARY'):
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'Please specify which class you which to change (primary, secondary, or tertiary)\\n')
        return
    if mob.player.name.lower() not in ('savage', 'palsgraph', 'masterdog'):
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'Sorry, the command is not allowed\\n')
        return
    if mob.name.upper() != name.upper():
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, "You must specify your active character's name (%s)\\n" % mob.name)
        return
    klasses = (mob.spawn.pclassInternal, mob.spawn.sclassInternal, mob.spawn.tclassInternal)
    if klass in klasses:
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, '%s is already a %s, unchanged.\\n' % (mob.name, klass))
        return
    if not mob.player.premium:
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, '\\nThis command requires Premium Account.\nPlease see www.prairiegames.com for more information.\\n\\n')
        return
    if mob.spawn.plevel + mob.spawn.slevel + mob.spawn.tlevel < 300:
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, '\\nThis command requires 100 of all levels (primary, secondary, and tertiary).\n')
        return
    if mob.spawn.realm == RPG_REALM_MONSTER:
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, '%s is a monster and cannot change class.\\n' % mob.name)
        return
    if mob.spawn.realm == RPG_REALM_LIGHT:
        if klass not in RPG_REALM_LIGHT_CLASSES:
            mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'Invalid class specified (case sensitive and make sure realm allows it).\\n')
            return
    if mob.spawn.realm == RPG_REALM_DARKNESS:
        if klass not in RPG_REALM_DARKNESS_CLASSES:
            mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'Invalid class specified (case sensitive and make sure realm allows it).\\n')
            return
    if which == 'PRIMARY':
        mob.spawn.pclassInternal = klass
        mob.levelChanged()
        mob.character.pchange = False
        mob.player.sendGameText(RPG_MSG_GAME_GAINED, "%s's primary class has been changed to %s.\\n" % (mob.name, klass))
        return
    if which == 'SECONDARY':
        if not mob.spawn.sclassInternal or not mob.spawn.slevel:
            mob.player.sendGameText(RPG_MSG_GAME_DENIED, '%s has no secondary class, unchanged.\\n' % mob.name)
            return
        mob.spawn.sclassInternal = klass
        mob.levelChanged()
        mob.character.schange = False
        mob.player.sendGameText(RPG_MSG_GAME_GAINED, "%s's secondary class has been changed to %s.\\n" % (mob.name, klass))
        return
    if which == 'TERTIARY':
        if not mob.spawn.tclassInternal or not mob.spawn.tlevel:
            mob.player.sendGameText(RPG_MSG_GAME_DENIED, '%s has no tertiary class, unchanged.\\n' % mob.name)
            return
        mob.spawn.tclassInternal = klass
        mob.levelChanged()
        mob.character.tchange = False
        mob.player.sendGameText(RPG_MSG_GAME_GAINED, "%s's tertiary class has been changed to %s.\\n" % (mob.name, klass))
        return


def CmdServer(mob, args):
    wname = mob.player.world.multiName.replace('_', ' ')
    mob.player.sendGameText(RPG_MSG_GAME_GAINED, 'You are on the %s server\\n' % wname)


def CmdResize(mob, args):
    player = mob.player
    if player.overrideScale:
        player.overrideScale = False
        mob.spawn.modifiedScale = mob.spawn.scale
    else:
        player.overrideScale = True
        mob.spawn.modifiedScale = 1.0


def CmdEmptyCraft(mob, args):
    items = dict(((item.slot, item) for item in mob.character.items if RPG_SLOT_CRAFTING_BEGIN <= item.slot < RPG_SLOT_CRAFTING_END or RPG_SLOT_CARRY_BEGIN <= item.slot < RPG_SLOT_CARRY_END))
    stackInventory(mob, items)
    CRAFTING_SLOT, CRAFTING_ITEM = range(2)
    craftingItems = []
    carrySlots = dict(((index, '') for index in xrange(RPG_SLOT_CARRY_BEGIN, RPG_SLOT_CARRY_END)))
    for slot, item in items.iteritems():
        if RPG_SLOT_CRAFTING_BEGIN <= slot:
            craftingItems.append([slot, item])
        else:
            del carrySlots[slot]

    craftingItems.sort()
    itemsBeingMoved = 0
    if len(craftingItems) > len(carrySlots):
        itemsBeingMoved = len(carrySlots)
    else:
        itemsBeingMoved = len(craftingItems)
    if itemsBeingMoved:
        freeSlots = carrySlots.keys()
        for index in xrange(itemsBeingMoved):
            craftingItems[index][CRAFTING_ITEM].slot = freeSlots[index]
            craftingItems[index][CRAFTING_ITEM].itemInfo.refreshDict({'SLOT': freeSlots[index]})

        mob.player.cinfoDirty = True


def CmdStackInventory(mob, args):
    items = dict(((item.slot, item) for item in mob.character.items if RPG_SLOT_CARRY_BEGIN <= item.slot < RPG_SLOT_CARRY_END))
    stackInventory(mob, items)


ALPHA_SORT, UNUSED_SORT = range(2)

def CmdInventorySort(mob, args):
    start = RPG_SLOT_CARRY_BEGIN
    end = RPG_SLOT_CARRY_END
    items = mob.character.items
    stack = True
    reverse = False
    sort = ALPHA_SORT
    for word in args:
        if word.upper() == 'PAGE1':
            start = RPG_SLOT_CARRY_BEGIN
            end = RPG_SLOT_CARRY0 + 30
        elif word.upper() == 'PAGE2':
            start = RPG_SLOT_CARRY0 + 30
            end = RPG_SLOT_CARRY_END
        elif word.upper() == 'NOSTACK':
            stack = False
        elif word.upper() == 'REVERSE':
            reverse = True

    itemSubsetDictionary = dict(((item.slot, item) for item in items if start <= item.slot < end))
    if stack:
        stackInventory(mob, itemSubsetDictionary)
    positionDictionary = createSortedPositionDictionary(sort, reverse, itemSubsetDictionary)
    if len(itemSubsetDictionary):
        if len(itemSubsetDictionary) == len(positionDictionary):
            for key, item in itemSubsetDictionary.iteritems():
                newSlot = start + positionDictionary[key]
                item.slot = newSlot
                item.itemInfo.refreshDict({'SLOT': newSlot})

        mob.player.cinfoDirty = True


def createSortedPositionDictionary(sort, reverse, itemSubsetDictionary):
    positionDictionary = {}
    itemSortedList = []
    itemSortedList = [ (item.name.lower(),
     item.itemProto.stackMax - item.stackCount,
     i,
     slot) for i, (slot, item) in enumerate(itemSubsetDictionary.iteritems()) ]
    itemSortedList.sort(reverse=reverse)
    if 0 < len(itemSortedList):
        for position, item in enumerate(itemSortedList):
            positionDictionary[item[-1]] = position

    return positionDictionary


FULL_STACKS, REMAINING_ITEMS, TOTAL_CHARGES = range(3)
ITEM_SLOT, ITEM_OBJECT = range(2)

def stackInventory(mob, items):
    stackableItems = {}
    stackData = {}
    for item in items.itervalues():
        iproto = item.itemProto
        if 1 < iproto.stackMax:
            chargesMax = iproto.useMax
            try:
                stackableItems[item.name].append(item)
            except KeyError:
                stackableItems[item.name] = [item]
                stackData[item.name] = [0, 0, 0]

            stackData[item.name][REMAINING_ITEMS] += item.stackCount
            if chargesMax:
                stackData[item.name][TOTAL_CHARGES] += chargesMax * (item.stackCount - 1) + item.useCharges

    for itemName, stackables in stackableItems.iteritems():
        iproto = stackables[0].itemProto
        stackMax = iproto.stackMax
        chargesMax = iproto.useMax
        if chargesMax:
            uncollapsedCount = stackData[itemName][REMAINING_ITEMS]
            stackData[itemName][REMAINING_ITEMS] = stackData[itemName][TOTAL_CHARGES] / chargesMax
            stackData[itemName][TOTAL_CHARGES] %= chargesMax
            if stackData[itemName][TOTAL_CHARGES]:
                stackData[itemName][REMAINING_ITEMS] += 1
            else:
                stackData[itemName][TOTAL_CHARGES] = chargesMax
            if uncollapsedCount > stackData[itemName][REMAINING_ITEMS]:
                mob.player.sendGameText(RPG_MSG_GAME_GAINED, "%s's charges collapsed into a single item.\\n" % itemName)
        stackData[itemName][FULL_STACKS] = stackData[itemName][REMAINING_ITEMS] / stackMax
        stackData[itemName][REMAINING_ITEMS] %= stackMax
        sortedList = [ (item.slot, item) for item in stackables ]
        sortedList.sort()
        for itemTuple in sortedList:
            item = itemTuple[ITEM_OBJECT]
            if stackData[itemName][FULL_STACKS]:
                item.stackCount = stackMax
                stackData[itemName][FULL_STACKS] -= 1
                if chargesMax:
                    if stackData[itemName][FULL_STACKS] or stackData[itemName][REMAINING_ITEMS]:
                        item.useCharges = chargesMax
                    else:
                        item.useCharges = stackData[itemName][TOTAL_CHARGES]
                    item.itemInfo.refreshDict({'STACKCOUNT': item.stackCount,
                     'USECHARGES': item.useCharges})
                else:
                    item.itemInfo.refreshDict({'STACKCOUNT': item.stackCount})
            elif stackData[itemName][REMAINING_ITEMS]:
                item.stackCount = stackData[itemName][REMAINING_ITEMS]
                stackData[itemName][REMAINING_ITEMS] = 0
                if chargesMax:
                    item.useCharges = stackData[itemName][TOTAL_CHARGES]
                    item.itemInfo.refreshDict({'STACKCOUNT': item.stackCount,
                     'USECHARGES': item.useCharges})
                else:
                    item.itemInfo.refreshDict({'STACKCOUNT': item.stackCount})
            else:
                del items[item.slot]
                mob.player.takeItem(item)

    if len(stackableItems):
        mob.player.cinfoDirty = True


COMMANDS = {}
COMMANDS['CHANGECLASS'] = CmdChangeClass
COMMANDS['ROLL'] = CmdRoll
COMMANDS['STACK'] = CmdStackInventory
COMMANDS['EMPTY'] = CmdEmptyCraft
COMMANDS['SORT'] = CmdInventorySort
COMMANDS['DANCE'] = CmdDance
COMMANDS['WAVE'] = CmdWave
COMMANDS['AGREE'] = CmdAgree
COMMANDS['YES'] = CmdAgree
COMMANDS['DISAGREE'] = CmdDisagree
COMMANDS['NO'] = CmdDisagree
COMMANDS['POINT'] = CmdPoint
COMMANDS['BOW'] = CmdBow
COMMANDS['SERVER'] = CmdServer
COMMANDS['ATTACK'] = CmdAttack
COMMANDS['RANGEDATTACK'] = CmdRangedAttack
COMMANDS['TARGETID'] = CmdTargetId
COMMANDS['INTERACT'] = CmdInteract
COMMANDS['BIND'] = CmdBind
COMMANDS['PET'] = CmdPet
COMMANDS['DISENCHANT'] = CmdDisenchant
COMMANDS['ENCHANT'] = CmdEnchant
COMMANDS['E'] = CmdEmote
COMMANDS['ME'] = CmdEmote
COMMANDS['EMOTE'] = CmdEmote
COMMANDS['LAUGH'] = CmdLaugh
COMMANDS['SCREAM'] = CmdScream
COMMANDS['GROAN'] = CmdGroan
COMMANDS['CHANNEL'] = CmdChannel
COMMANDS['S'] = CmdSayMsg
COMMANDS['SAY'] = CmdSayMsg
COMMANDS['W'] = CmdWorldMsg
COMMANDS['WORLD'] = CmdWorldMsg
COMMANDS['Z'] = CmdZoneMsg
COMMANDS['ZONE'] = CmdZoneMsg
COMMANDS['A'] = CmdAllianceMsg
COMMANDS['ALLIANCE'] = CmdAllianceMsg
COMMANDS['UPTIME'] = CmdUpTime
COMMANDS['CAST'] = CmdCast
COMMANDS['SKILL'] = CmdSkill
COMMANDS['CAMP'] = CmdCamp
COMMANDS['TIME'] = CmdTime
COMMANDS['EVAL'] = CmdEval
COMMANDS['DESC'] = CmdDesc
COMMANDS['MYDESC'] = CmdMyDesc
COMMANDS['AVATAR'] = CmdAvatar
COMMANDS['SUICIDE'] = CmdSuicide
COMMANDS['LADDER'] = CmdLadder
COMMANDS['CYCLETARGET'] = CmdCycleTarget
COMMANDS['CYCLETARGETBACKWARDS'] = CmdCycleTargetBackwards
COMMANDS['TARGETNEAREST'] = CmdTargetNearest
COMMANDS['TARGET'] = CmdTarget
COMMANDS['ASSIST'] = CmdAssist
COMMANDS['VERSION'] = CmdVersion
COMMANDS['LASTNAME'] = CmdLastName
COMMANDS['CLEARLASTNAME'] = CmdClearLastName
COMMANDS['WHO'] = CmdWho
COMMANDS['INVITE'] = CmdInvite
COMMANDS['UNSTICK'] = CmdUnstick
COMMANDS['RESIZE'] = CmdResize
COMMANDS['STOPCAST'] = CmdStopCast
COMMANDS['UNLEARN'] = CmdUnlearn
COMMANDS['WALK'] = CmdWalk
COMMANDS['GCREATE'] = GuildCreate
COMMANDS['GLEAVE'] = GuildLeave
COMMANDS['GINVITE'] = GuildInvite
COMMANDS['GJOIN'] = GuildJoin
COMMANDS['GDECLINE'] = GuildDecline
COMMANDS['GPROMOTE'] = GuildPromote
COMMANDS['GDEMOTE'] = GuildDemote
COMMANDS['GREMOVE'] = GuildRemove
COMMANDS['GSETMOTD'] = GuildSetMOTD
COMMANDS['GCLEARMOTD'] = GuildClearMOTD
COMMANDS['GROSTER'] = GuildRoster
COMMANDS['GSETLEADER'] = GuildSetLeader
COMMANDS['GDISBAND'] = GuildDisband
COMMANDS['GCHARACTERS'] = GuildCharacters
COMMANDS['G'] = CmdGuildMsg
COMMANDS['GUILD'] = CmdGuildMsg
COMMANDS['GPUBLICNAME'] = GuildPublicName
COMMANDS['CART'] = CmdCart

def CmdPing(mob, args):
    text = 'ping %s at %s' % (mob.player.publicName, datetime.now().strftime('%H:%M:%S'))
    print text
    mob.player.sendGameText(RPG_MSG_GAME_EVENT, '%s\\n' % text)


COMMANDS['PING'] = CmdPing

def DoCommand(mob, cmd, args):
    if type(args) != list:
        args = [args]
    cmd = cmd.upper()
    if COMMANDS.has_key(cmd):
        COMMANDS[cmd](mob, args)
        return
    mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'Unknown command: %s.\\n' % cmd)