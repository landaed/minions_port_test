# Embedded file name: mud\world\immortalcommand.pyo
import math
from defines import *
from zone import Zone
from spawn import Spawn
from core import *
import sys
from mud.common.permission import User
from damage import XPDamage
STASISDICT = {}
MOB_STASISDICT = {}

def addMobToStasisGroup(mob, groupName):
    zone = mob.zone
    zoneDict = STASISDICT.setdefault(zone, {})
    group = zoneDict.setdefault(groupName, [set(), False])
    group[0].add(mob)
    mobZoneDict = MOB_STASISDICT.get(zone)
    if mobZoneDict:
        mobInfo = mobZoneDict.get(mob)
        if mobInfo:
            if mobInfo[0] != groupName:
                stasisSet = zoneDict[mobInfo[0]][0]
                stasisSet.discard(mob)
                if not len(stasisSet):
                    del zoneDict[mobInfo[0]]
            if mobInfo[1]:
                mob.stun -= 5
                mob.invulnerable -= 1
                if mob.player:
                    mob.player.sendGameText(RPG_MSG_GAME_GAINED, '%s has been released from stasis!\\n' % mob.name)
    if group[1]:
        mob.stun += 5
        mob.invulnerable += 1
        if mob.player:
            mob.player.sendGameText(RPG_MSG_GAME_EVENT, '%s has been put into stasis!\\n' % mob.name)
    MOB_STASISDICT.setdefault(zone, {})[mob] = [groupName, group[1]]
    mob.mobInfo.refresh()


def CmdDespawn(mob, args):
    zone = mob.zone
    mobList = zone.spawnedMobs[:]
    mobList.extend(zone.activeMobs)
    for spMob in mobList:
        if not spMob.player and not (spMob.master and spMob.master.player):
            zone.removeMob(spMob)


def CmdKill(mob, args):
    from damage import Damage
    target = mob.target
    if target:
        if not target.player:
            if not target.mobInitialized:
                target.initMob()
        target.xpDamage = {}
        target.xpDamage[mob] = XPDamage()
        target.xpDamage[mob].addDamage(999999)
        target.die(True)
        mob.player.sendGameText(RPG_MSG_GAME_GAINED, '%s is struck down by lightning from the heavens!\\n' % target.name)
        if target.player:
            target.player.sendGameText(RPG_MSG_GAME_CHARDEATH, '%s is struck down by lightning from the heavens!\\n' % target.name)


def CmdStasis(mob, args):
    if not len(args):
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, "Syntax for immortal command stasis:\\n - '/imm stasis on/off <stasis group name>': Group name here is optional. Turn stasis for a specific group or the target on or off while adding the current target (if any) to this group.\\n - '/imm stasis add/remove <stasis group name>': Group name here is required. Add/remove the target to/from the specified group, without toggling stasis for this group. If group is in stasis, target will be set to stasis as well on add and taken out of stasis on removal.\\n - '/imm stasis info': Returns a list with all stasis groups in the current zone, their members and their status.\\n - '/imm stasis clear': Clear all stasis groups for the current zone, take all mobs out of stasis.\\n")
        return
    else:
        subcommand = args[0].lower()
        zone = mob.zone
        target = mob.target
        if subcommand == 'clear':
            try:
                del STASISDICT[zone]
            except KeyError:
                pass

            try:
                zoneDict = MOB_STASISDICT.pop(zone)
                for stmob, values in zoneDict.iteritems():
                    if values[1]:
                        stmob.stun -= 5
                        stmob.invulnerable -= 1
                        stmob.mobInfo.refresh()
                        if stmob.player:
                            stmob.player.sendGameText(RPG_MSG_GAME_GAINED, '%s has been released from stasis!\\n' % stmob.name)

            except KeyError:
                pass

            mob.player.sendGameText(RPG_MSG_GAME_GAINED, 'All stasis groups in %s have been cleared.\\n' % zone.zone.niceName)
            return
        if subcommand == 'info':
            zoneDict = STASISDICT.get(zone)
            if not zoneDict or not len(zoneDict):
                mob.player.sendGameText(RPG_MSG_GAME_GAINED, 'There are currently no stasis groups in %s.\\n' % zone.zone.niceName)
                return
            mobZoneDict = MOB_STASISDICT[zone]
            stasisGroups = '\\n'.join((' - %s:\\n%s' % (groupName, '\\n'.join(('  -- %s : %s' % (stmob.name, mobZoneDict[stmob][1]) for stmob in groupInfo[0]))) for groupName, groupInfo in zoneDict.iteritems()))
            mob.player.sendGameText(RPG_MSG_GAME_GAINED, 'Stasis groups in %s:\\n%s\\n' % (zone.zone.niceName, stasisGroups))
            return
        if subcommand == 'add':
            if not target:
                mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'Please select a target before using this command.\\n')
                return
            if len(args) == 1:
                mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'Please provide a stasis group name with this command.\\n')
                return
            groupName = ' '.join(args[1:])
            addMobToStasisGroup(target, groupName)
            mob.player.sendGameText(RPG_MSG_GAME_GAINED, 'Added %s to stasis group %s.\\n' % (target.name, groupName))
            return
        if subcommand == 'remove':
            if not target:
                mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'Please select a target before using this command.\\n')
                return
            if len(args) == 1:
                mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'Please provide a stasis group name with this command.\\n')
                return
            groupName = ' '.join(args[1:])
            zoneDict = MOB_STASISDICT.get(zone)
            if zoneDict:
                mobInfo = zoneDict.get(target)
                if mobInfo and mobInfo[0] == groupName:
                    stasisSet = STASISDICT[zone][groupName][0]
                    stasisSet.discard(target)
                    if not len(stasisSet):
                        del STASISDICT[zone][groupName]
                    if mobInfo[1]:
                        target.stun -= 5
                        target.invulnerable -= 1
                        target.mobInfo.refresh()
                        if target.player:
                            target.player.sendGameText(RPG_MSG_GAME_GAINED, '%s has been released from stasis!\\n' % target.name)
                    del MOB_STASISDICT[zone][target]
                    mob.player.sendGameText(RPG_MSG_GAME_GAINED, 'Removed %s from group %s.\\n' % (target.name, groupName))
                    return
            mob.player.sendGameText(RPG_MSG_GAME_DENIED, "%s isn't part of the stasis group %s.\\n" % (target.name, groupName))
            return
        if subcommand == 'on' or subcommand == 'off':
            if len(args) > 1:
                groupName = ' '.join(args[1:])
                if target:
                    addMobToStasisGroup(target, groupName)
                    group = STASISDICT[zone][groupName]
                else:
                    group = None
                    zoneDict = STASISDICT.get(zone)
                    if zoneDict:
                        group = zoneDict.get(groupName)
                    if not group:
                        mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'Stasis group %s does not exist.\\n' % groupName)
                        return
            else:
                if not target:
                    mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'Please provide a stasis group name or select a target before using this command.\\n')
                    return
                groupName = '%s - %i' % (target.name, target.id)
                addMobToStasisGroup(target, groupName)
                group = STASISDICT[zone][groupName]
            mobZoneDict = MOB_STASISDICT[zone]
            if subcommand == 'on':
                if not group[1]:
                    for stmob in group[0]:
                        if not mobZoneDict[stmob][1]:
                            stmob.stun += 5
                            stmob.invulnerable += 1
                            stmob.mobInfo.refresh()
                            if stmob.player:
                                stmob.player.sendGameText(RPG_MSG_GAME_EVENT, '%s has been put into stasis!\\n' % stmob.name)
                            mobZoneDict[stmob][1] = True

                    group[1] = True
                mob.player.sendGameText(RPG_MSG_GAME_GAINED, 'Stasis group %s has been put into stasis.\\n' % groupName)
            else:
                if group[1]:
                    for stmob in group[0]:
                        if mobZoneDict[stmob][1]:
                            stmob.stun -= 5
                            stmob.invulnerable -= 1
                            stmob.mobInfo.refresh()
                            if stmob.player:
                                stmob.player.sendGameText(RPG_MSG_GAME_GAINED, '%s has been released from stasis!\\n' % stmob.name)
                            mobZoneDict[stmob][1] = False

                    group[1] = False
                mob.player.sendGameText(RPG_MSG_GAME_GAINED, 'Stasis has been cancelled for stasis group %s.\\n' % groupName)
            return
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, "Syntax for immortal command stasis:\\n - '/imm stasis on/off <group name>': Group name here is optional. Turn stasis for a specific group or the target on or off while adding the current target (if any) to this group.\\n - '/imm stasis add/remove <group name>': Group name here is required. Add/remove the target to/from the specified group, without toggling stasis for this group. If group is in stasis, target will be set to stasis as well on add and taken out of stasis on removal.\\n - '/imm stasis info': Returns a list with all stasis groups, their members and their status.\\n - '/imm stasis clear': Clear all stasis groups for the current zone, take all mobs out of stasis.\\n")
        return


def CmdSet(mob, args):
    if not len(args):
        return
    what = args[0].upper()
    args = args[1:]
    if not len(args):
        return
    SetCommands = {'WIND': CmdSetWind,
     'TIME': CmdSetTime,
     'WEATHER': CmdSetWeather}
    try:
        SetCommands[what](mob, args)
    except KeyError:
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'Only %s can be used in conjunction with the set command.\\n' % ', '.join(SetCommands.iterkeys()))


def CmdSetWind(mob, args):
    wind = max(1, min(10, int(args[0])))
    mob.zone.weather.windspeed = wind
    mob.zone.weather.dirty = True
    mob.player.sendGameText(RPG_MSG_GAME_GAINED, 'Wind set.\\n')


def CmdSetWeather(mob, args):
    precip = min(10, int(args[0]))
    weather = mob.zone.weather
    weather.cloudCover = max(1, precip)
    weather.precip = precip
    weather.lastPrecipChange = 0
    weather.lastCoverChange = 0
    weather.dirty = True
    mob.player.sendGameText(RPG_MSG_GAME_GAINED, 'Weather set.\\n')


def CmdSetTime(mob, args):
    try:
        hour = int(args[0])
        minute = 0
        if len(args) == 2:
            minute = int(args[1])
        world = mob.player.world
        if world.daemonPerspective:
            world.daemonPerspective.callRemote('propagateCmd', 'setTime', hour, minute)
        world.time.hour = hour
        world.time.minute = minute
        for player in world.activePlayers:
            player.mind.callRemote('syncTime', world.time.hour, world.time.minute)
            player.sendSpeechText(RPG_MSG_SPEECH_SYSTEM, '\\n<Scribe of Mirth> And time moves...\\n\\n')

        mob.player.sendGameText(RPG_MSG_GAME_GAINED, 'The time is now: %i:%i\\n' % (world.time.hour, world.time.minute))
    except:
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'Problem setting time\\n')


def CmdGiveMonster(mob, args):
    if not len(args):
        return
    mspawn = ' '.join(args)
    lowerSpawn = mspawn.lower()
    for monsterSpawn in mob.player.monsterSpawns:
        if monsterSpawn.spawn.lower() == lowerSpawn:
            mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'You already have the %s monster template.\\n' % monsterSpawn.spawn)
            return

    from spawn import Spawn
    try:
        con = Spawn._connection.getConnection()
        spawn = Spawn.get(con.execute('SELECT id FROM spawn WHERE lower(name)="%s" LIMIT 1;' % lowerSpawn).fetchone()[0])
        mspawn = spawn.name
    except:
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'No such spawn %s.\\n' % mspawn)
        return

    from player import PlayerMonsterSpawn
    PlayerMonsterSpawn(player=mob.player, spawn=mspawn)
    mob.player.sendGameText(RPG_MSG_GAME_GAINED, 'You now have the %s monster template.\\n' % mspawn)


def CmdGrantMonster(mob, args):
    if len(args) < 2:
        return
    pname = args[0]
    lowerPName = pname.lower()
    args = args[1:]
    mspawn = ' '.join(args)
    lowerSpawn = mspawn.lower()
    from player import Player
    try:
        con = Player._connection.getConnection()
        player = Player.get(con.execute('SELECT id FROM player WHERE lower(public_name) = "%s" LIMIT 1;' % lowerPName).fetchone()[0])
        pname = player.publicName
    except:
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'No player by public name %s.\\n' % pname)
        return

    for monsterSpawn in player.monsterSpawns:
        if monsterSpawn.spawn.lower() == lowerSpawn:
            mob.player.sendGameText(RPG_MSG_GAME_DENIED, '%s already has the %s monster template.\\n' % (pname, monsterSpawn.spawn))
            return

    from spawn import Spawn
    try:
        con = Spawn._connection.getConnection()
        spawn = Spawn.get(con.execute('SELECT id FROM spawn WHERE lower(name) = "%s" LIMIT 1;' % lowerSpawn).fetchone()[0])
        mspawn = spawn.name
    except:
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'No such spawn %s.\\n' % mspawn)
        return

    from player import PlayerMonsterSpawn
    PlayerMonsterSpawn(player=player, spawn=mspawn)
    mob.player.sendGameText(RPG_MSG_GAME_GAINED, 'You have granted %s the %s monster template.\\n' % (pname, mspawn))
    if player.zone:
        player.sendGameText(RPG_MSG_GAME_GAINED, 'You now have the %s monster template.\\n' % mspawn)


def CmdListMonsters(mob, args):
    if len(args) < 1:
        return
    pname = args[0]
    lowerPName = pname.lower()
    from player import Player
    try:
        con = Player._connection.getConnection()
        player = Player.get(con.execute('SELECT id FROM player WHERE lower(public_name) = "%s" LIMIT 1;' % lowerPName).fetchone()[0])
        pname = player.publicName
    except:
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'No player by public name %s.\\n' % pname)
        return

    text = '%s has the following monster templates: %s\\n' % (pname, ', '.join((ms.spawn for ms in player.monsterSpawns)))
    mob.player.sendGameText(RPG_MSG_GAME_GAINED, text)


def CmdDenyMonster(mob, args):
    if len(args) < 2:
        return
    pname = args[0]
    lowerPName = pname.lower()
    args = args[1:]
    mspawn = ' '.join(args)
    lowerSpawn = mspawn.lower()
    from player import Player
    try:
        con = Player._connection.getConnection()
        player = Player.get(con.execute('SELECT id FROM player WHERE lower(public_name) = "%s" LIMIT 1;' % lowerPName).fetchone()[0])
        pname = player.publicName
    except:
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'No player by public name %s.\\n' % pname)
        return

    if not IsUserSuperior(mob.player.publicName, pname):
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'You do not have the required permission for this action.\\n')
        return
    if player.enteringWorld:
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'Player is entering the world and needs to log out first!\\n')
        return
    if player.zone:
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'Player is in the world and needs to log out first!\\n')
        return
    delete = []
    for c in player.characters:
        if c.spawn.template.lower() == lowerSpawn:
            delete.append(c)

    for x in delete[:]:
        mob.player.avatar.perspective_deleteCharacter(x.name)

    for ms in player.monsterSpawns:
        if ms.spawn.lower() == lowerSpawn:
            ms.destroySelf()
            break

    mob.player.sendGameText(RPG_MSG_GAME_GAINED, 'You have denied %s the %s monster template.\\n' % (pname, mspawn))
    if player.zone:
        player.sendGameText(RPG_MSG_GAME_DENIED, 'You no longer have the %s monster template.\\n' % mspawn)


def CmdGrantLevel(mob, args):
    if len(args) < 2:
        return
    pname = args[0]
    lowerPName = pname.lower()
    klass = args[1].lower()
    from player import Player
    try:
        con = Player._connection.getConnection()
        player = Player.get(con.execute('SELECT id FROM player WHERE lower(public_name) = "%s" LIMIT 1;' % lowerPName).fetchone()[0])
        pname = player.publicName
    except:
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'No player by public name %s.\\n' % pname)
        return

    if not player.party or not len(player.party.members):
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, "Player isn't logged in %s.\\n" % pname)
        return
    c = player.party.members[0]
    gained = False
    spawn = c.spawn
    if spawn.pclassInternal.lower() == klass:
        c.gainLevel(0)
        gained = True
    if spawn.sclassInternal.lower() == klass:
        c.gainLevel(1)
        gained = True
    if spawn.tclassInternal.lower() == klass:
        c.gainLevel(2)
        gained = True
    if gained:
        t = '%s %i / %s %i / %s %i' % (spawn.pclassInternal,
         spawn.plevel,
         spawn.sclassInternal,
         spawn.slevel,
         spawn.tclassInternal,
         spawn.tlevel)
        mob.player.sendGameText(RPG_MSG_GAME_GAINED, '%s is now a %s.\\n' % (c.name, t))
    else:
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, "Character doesn't have that class\\n")


def CmdModStat(mob, args):
    if not len(args):
        return
    target = mob.target
    if not target:
        target = mob
    duration = 30 * durMinute
    if args[-2].isdigit():
        try:
            duration = int(args[-1]) * durMinute
        except ValueError:
            mob.player.sendGameText(RPG_MSG_GAME_DENIED, "%s can't be used to set the effect duration." % args[-1])

    mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'Implementation of this command is not yet finished.')


def CmdGimme(mob, args):
    from item import ItemProto, getTomeAtLevelForScroll
    argUpper = args[0].upper()
    if argUpper == 'TOME':
        itemname = argUpper
        tomename = ' '.join(args[2:-1])
    elif argUpper not in ('PLEVEL', 'SLEVEL', 'TLEVEL', 'SKILL', 'MONEY', 'XP', 'RENEW', 'PRESENCE'):
        itemname = ' '.join(args)
    else:
        itemname = argUpper
        levels = 0
        if len(args) > 1:
            try:
                levels = int(args[1])
            except:
                pass

    if itemname == 'MONEY':
        if len(args) > 1:
            try:
                amount = int(args[1])
            except:
                amount = 1000

        else:
            amount = 1000
        mob.player.platinum += amount
        if mob.player.platinum < 0:
            mob.player.platinum = 0
        if amount > 0:
            mob.player.sendGameText(RPG_MSG_GAME_GAINED, 'Gained %i platinum.\\n' % amount)
        else:
            mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'Lost %i platinum.\\n' % -amount)
        return
    elif itemname == 'XP':
        for c in mob.player.party.members:
            c.gainXP(1000000)

        return
    elif itemname == 'PLEVEL':
        if levels == 0:
            return
        for x in xrange(0, levels):
            mob.player.curChar.gainLevel(0)

        return
    elif itemname == 'SLEVEL':
        if levels == 0:
            return
        for x in xrange(0, levels):
            mob.player.curChar.gainLevel(1)

        return
    elif itemname == 'TLEVEL':
        if levels == 0:
            return
        for x in xrange(0, levels):
            mob.player.curChar.gainLevel(2)

        return
    elif itemname == 'SKILL':
        if levels == 0:
            return
        m = mob.player.curChar.mob
        for x in xrange(0, levels):
            for skname in m.skillLevels.iterkeys():
                mob.player.curChar.checkSkillRaise(skname, 0, 0)

        return
    elif itemname == 'PRESENCE':
        if levels < 0:
            mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'The value provided must be a positive integer.\\n')
            return
        if levels > RPG_MAX_PRESENCE:
            levels = RPG_MAX_PRESENCE
        currentCharacter = mob.player.curChar
        currentCharacter.mob.pre = levels
        currentCharacter.mob.preBase = levels
        currentCharacter.spawn.preBase = levels
        currentCharacter.mob.derivedDirty = True
        mob.player.sendGameText(RPG_MSG_GAME_GAINED, 'You now have %i presence.\\n' % levels)
        return
    elif itemname == 'RENEW':
        for c in mob.player.party.members:
            m = c.mob
            m.health = m.maxHealth
            m.mana = m.maxMana
            m.stamina = m.maxStamina
            m.skillReuse = {}
            m.recastTimers = {}
            if m.pet:
                m.pet.health = m.pet.maxHealth

        mob.player.cinfoDirty = True
        return
    elif itemname == 'TOME':
        char = mob.player.curChar
        levels = ['1',
         '2',
         '3',
         '4',
         '5',
         '6',
         '7',
         '8',
         '9',
         '10']
        lupper = args[-1].upper()
        try:
            tomelevel = levels.index(lupper) + 1
        except:
            try:
                tomelevel = RPG_ROMAN.index(lupper) + 1
            except:
                mob.player.sendGameText(RPG_MSG_GAME_DENIED, "%s isn't a valid tome level!\\n" % args[-1])
                return

        if tomelevel <= 1:
            mob.player.sendGameText(RPG_MSG_GAME_DENIED, "%s isn't a valid tome level!\\n" % args[-1])
            return
        try:
            con = ItemProto._connection.getConnection()
            scroll = ItemProto.get(con.execute('SELECT id FROM item_proto WHERE lower(name)=lower("Scroll of %s") LIMIT 1;' % tomename).fetchone()[0])
        except:
            mob.player.sendGameText(RPG_MSG_GAME_DENIED, '%s is no spell name!\\n' % tomename)
            return

        nitem = getTomeAtLevelForScroll(scroll, tomelevel)
        if not char.giveItemInstance(nitem):
            nitem.destroySelf()
            mob.player.sendGameText(RPG_MSG_GAME_DENIED, "%s doesn't have enough inventory space\\n" % char.name)
            return
        char.refreshItems()
        mob.player.sendGameText(RPG_MSG_GAME_GAINED, 'Gained %s\\n' % nitem.name)
        return
    else:
        from crafting import FocusGenSpecific
        item = FocusGenSpecific(itemname)
        if item:
            if not mob.player.curChar.giveItemInstance(item):
                item.destroySelf()
                mob.player.sendGameText(RPG_MSG_GAME_DENIED, "%s doesn't have enough inventory space\\n" % char.name)
                return
        else:
            try:
                if True:
                    con = ItemProto._connection.getConnection()
                    proto = ItemProto.get(con.execute('SELECT id FROM item_proto WHERE lower(name)=lower("%s") LIMIT 1;' % itemname).fetchone()[0])
                else:
                    proto = ItemProto.byName(itemname)
                item = proto.createInstance()
                item.stackCount = proto.stackMax
                if not mob.player.curChar.giveItemInstance(item):
                    item.destroySelf()
                    item = None
            except:
                pass

        if item:
            if RPG_SLOT_WORN_END > item.slot >= RPG_SLOT_WORN_BEGIN:
                mob.equipItem(item.slot, item)
            mob.player.sendGameText(RPG_MSG_GAME_GAINED, 'Gained %s\\n' % item.name)
        else:
            mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'Failure getting %s\\n' % itemname)
        return


def CmdSpawn(mob, args):
    try:
        if args[-1].endswith(']'):
            x = float(args[-3][1:])
            y = float(args[-2])
            z = float(args[-1][:-1])
            spawnName = ' '.join(args[:-3])
        else:
            mypos = mob.simObject.position
            x = mypos[0]
            y = mypos[1]
            z = mypos[2]
            spawnName = ' '.join(args)
    except:
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, "Invalid arguments to immortal spawn command. Syntax is '/imm spawn <spawn name> [x-coord y-coord z-coord]' where the coords with their '[]' brackets are optional.\\n")
        return

    try:
        con = Spawn._connection.getConnection()
        mob.player.sendGameText(RPG_MSG_GAME_GAINED, 'Spawning %s at [%0.2f %0.2f %0.2f]...\\n' % (spawnName,
         x,
         y,
         z))
        spawn = Spawn.get(con.execute('SELECT id FROM spawn WHERE lower(name)=lower("%s") LIMIT 1;' % spawnName).fetchone()[0])
    except:
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'failed.\\n')
        return

    rot = mob.simObject.rotation
    transform = (x,
     y,
     z,
     rot[0],
     rot[1],
     rot[2],
     rot[3])
    mob.zone.spawnMob(spawn, transform, -1)
    mob.player.sendGameText(RPG_MSG_GAME_GAINED, 'done.\\n')


def CmdWorldAggro(mob, args):
    world = mob.player.world
    newAggroState = not world.aggroOn
    if len(args):
        if args[0].lower() == 'off':
            if newAggroState:
                mob.player.sendGameText(RPG_MSG_GAME_GLOBAL, "Monsters still won't initiate attacks.\\n")
                return
            newAggroState = False
        else:
            if not newAggroState:
                mob.player.sendGameText(RPG_MSG_GAME_GLOBAL, 'Monsters still will initiate attacks.\\n')
                return
            newAggroState = True
    world.aggroOn = newAggroState
    if world.daemonPerspective:
        world.daemonPerspective.callRemote('propagateCmd', 'setWorldAggro', newAggroState)
    if newAggroState:
        mob.player.sendGameText(RPG_MSG_GAME_GLOBAL, 'Monsters WILL initiate attacks.\\n')
    else:
        mob.player.sendGameText(RPG_MSG_GAME_GLOBAL, 'Monsters will NOT initiate any attacks.\\n')


def CmdMyAggro(mob, args):
    aggroOff = mob.aggroOff
    if not len(args):
        aggroOff = not aggroOff
    elif args[0].lower() == 'off':
        aggroOff = True
    else:
        aggroOff = False
    for c in mob.player.party.members:
        c.mob.aggroOff = aggroOff

    if aggroOff:
        mob.player.sendGameText(RPG_MSG_GAME_GLOBAL, 'Monsters will NOT attack your party.\\n')
    else:
        mob.player.sendGameText(RPG_MSG_GAME_GLOBAL, 'Monsters WILL attack your party.\\n')


def CmdTP(mob, args):
    player = mob.player
    zname = args[0]
    if zname.lower() == 'bindstone':
        if player.darkness:
            z = player.darknessBindZone
            trans = player.darknessBindTransform
        elif player.monster:
            z = player.monsterBindZone
            trans = player.monsterBindTransform
        else:
            z = player.bindZone
            trans = player.bindTransform
        dst = ' '.join((str(i) for i in trans))
    else:
        try:
            z = Zone.byName(zname)
            dst = z.immTransform
        except:
            mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'Unknown zone or zone not setup for immortal command %s.\\n' % zname)
            return

    if player.zone.zone == z:
        player.zone.respawnPlayer(player, dst)
    else:
        from zone import TempZoneLink
        zlink = TempZoneLink(zname, dst)
        player.world.onZoneTrigger(player, zlink)


def CmdSystemMsg(mob, args):
    if not len(args):
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'Need to specify a message to use with this command.')
        return
    msg = 'SYSTEM: %s\\n' % ' '.join(args)
    world = mob.player.world
    if world.daemonPerspective:
        world.daemonPerspective.callRemote('propagateCmd', 'sendSysMsg', msg)
    for p in world.activePlayers:
        p.sendSpeechText(RPG_MSG_SPEECH_SYSTEM, msg)


def CmdScribeMsg(mob, args):
    if not len(args):
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'Need to specify a message to use with this command.')
        return
    msg = '\\n<Scribe of Mirth> %s\\n\\n' % ' '.join(args)
    world = mob.player.world
    if world.daemonPerspective:
        world.daemonPerspective.callRemote('propagateCmd', 'sendSysMsg', msg)
    for p in world.activePlayers:
        p.sendSpeechText(RPG_MSG_SPEECH_SYSTEM, msg)


def CmdReloadCommands(mob, args):
    reload(sys.modules['mud.world.command'])


def CmdReloadModule(mob, args):
    reload(sys.modules[args[0]])


def CmdGrant(mob, args):
    from mud.common.permission import User, Role
    if len(args) < 2:
        return
    try:
        user = User.byName(args[0])
    except:
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'Unknown user %s.\\n' % args[0])
        return

    try:
        role = Role.byName(args[1])
    except:
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'Unknown role %s.\\n' % args[1])
        return

    for r in user.roles:
        if r.name == role.name:
            mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'User %s already has the %s role.\\n' % (args[0], args[1]))
            return

    if role.name == 'Immortal':
        from newplayeravatar import NewPlayerAvatar
        if mob.player.publicName != NewPlayerAvatar.ownerPublicName:
            mob.player.sendGameText(RPG_MSG_GAME_DENIED, "Immortal access can only be granted by the server's owner.\\n")
            return
    mob.player.sendGameText(RPG_MSG_GAME_GAINED, 'User %s granted the %s role.\\n' % (args[0], args[1]))
    user.addRole(role)


def CmdDeny(mob, args):
    from mud.common.permission import User, Role
    from player import Player
    if len(args) < 2:
        return
    try:
        user = User.byName(args[0])
    except:
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'Unknown user %s.\\n' % args[0])
        return

    if not IsUserSuperior(mob.player.publicName, user.name):
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'You do not have the required permission for this action.\\n')
        return
    try:
        role = Role.byName(args[1])
    except:
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'Unknown role %s.\\n' % args[1])
        return

    for r in user.roles:
        if r.name == role.name:
            user.removeRole(r)
            try:
                player = Player.byPublicName(args[0])
                if player.avatar and player.avatar.masterPerspective:
                    player.avatar.masterPerspective.removeAvatar('GuardianAvatar')
            except:
                pass

            mob.player.sendGameText(RPG_MSG_GAME_GAINED, 'User %s denied the %s role.\\n' % (args[0], args[1]))
            return

    mob.player.sendGameText(RPG_MSG_GAME_DENIED, "User %s doesn't have the %s role.\\n" % (args[0], args[1]))


def CmdSetPlayerPassword(mob, args):
    from player import Player
    if CoreSettings.SINGLEPLAYER:
        return
    if len(args) != 2:
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'Please specify a player and a password\\n')
        return
    try:
        player = Player.byPublicName(args[0])
    except:
        try:
            player = Player.byFantasyName(args[0])
        except:
            mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'Unknown player %s.\\n' % args[0])
            return

    try:
        user = User.byName(args[0])
    except:
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'Unknown user %s.\\n' % args[0])
        return

    if not IsUserSuperior(mob.player.publicName, user.name):
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'You do not have the required permission for this action.\\n')
        return
    pw = args[1]
    if len(pw) < 6:
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'Password must be at least 6 characters.\\n')
        return
    user.password = player.password = pw
    mob.player.sendGameText(RPG_MSG_GAME_GAINED, 'Player %s password set to %s\\n' % (player.publicName, pw))


def CmdGetPlayerPassword(mob, args):
    if CoreSettings.SINGLEPLAYER:
        return
    if len(args) != 1:
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'Please specify a player\\n')
        return
    try:
        user = User.byName(args[0])
    except:
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'Unknown user %s.\\n' % args[0])
        return

    if not IsUserSuperior(mob.player.publicName, user.name):
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'You do not have the required permission for this action.\\n')
        return
    mob.player.sendGameText(RPG_MSG_GAME_GAINED, 'Player %s password is: %s\\n' % (user.name, user.password))


def CmdTestAFX(mob, args):
    if not len(args):
        return
    effect = ' '.join(args)
    mob.testAFX(effect, mob.target)


def CmdGetDimensions(mob, args):
    source = mob
    if mob.target:
        source = mob.target
    mob.player.sendGameText(RPG_MSG_GAME_WHITE, 'Relevant dimensions of %s are:\\n Mob Size - %f\\n Spawn Scale - %f\\n Current Scale - %f\\n Spawn Radius - %f\\n' % (source.name,
     source.size,
     source.spawn.scale,
     source.spawn.modifiedScale,
     source.spawn.radius))


def CmdCheckWealth(mob, args):
    if not mob.target:
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'This command requires a target.\\n')
        return
    tplayer = mob.target.player
    ext = ('pp', 'gp', 'sp', 'cp', 'tp')
    worthLight = (tplayer.lightPlatinum,
     tplayer.lightGold,
     tplayer.lightSilver,
     tplayer.lightCopper,
     tplayer.lightTin)
    lightString = ', '.join(('%i%s' % (w, ext[i]) for i, w in enumerate(worthLight) if w != 0))
    worthDarkness = (tplayer.darknessPlatinum,
     tplayer.darknessGold,
     tplayer.darknessSilver,
     tplayer.darknessCopper,
     tplayer.darknessTin)
    darknessString = ', '.join(('%i%s' % (w, ext[i]) for i, w in enumerate(worthDarkness) if w != 0))
    worthMonster = (tplayer.monsterPlatinum,
     tplayer.monsterGold,
     tplayer.monsterSilver,
     tplayer.monsterCopper,
     tplayer.monsterTin)
    monsterString = ', '.join(('%i%s' % (w, ext[i]) for i, w in enumerate(worthMonster) if w != 0))
    mob.player.sendGameText(RPG_MSG_GAME_WHITE, "%s's wealth:\\n Light: %s\\n Darkness: %s\\n Monster: %s\\n" % (mob.target.name,
     lightString,
     darknessString,
     monsterString))


def CmdSetWealth(mob, args):
    if not mob.target:
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'This command requires a target.\\n')
        return
    if len(args) != 2:
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, 'Number of supplied arguments incorrect.\\nUsage: /imm setwealth <realm = light/darkness/monster> <amount in tin>.\\n')
        return
    try:
        tp, cp, sp, gp, pp = CollapseMoney(int(args[1]))
    except ValueError:
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, "Can't extract amount of tin argument.\\nUsage: /imm setwealth <realm = light/darkness/monster> <amount in tin>.\\n")
        return

    tplayer = mob.target.player
    realmText = args[0].upper()
    if realmText == 'LIGHT':
        tplayer.lightTin = tp
        tplayer.lightCopper = cp
        tplayer.lightSilver = sp
        tplayer.lightGold = gp
        tplayer.lightPlatinum = pp
    elif realmText == 'DARKNESS':
        tplayer.darknessTin = tp
        tplayer.darknessCopper = cp
        tplayer.darknessSilver = sp
        tplayer.darknessGold = gp
        tplayer.darknessPlatinum = pp
    elif realmText == 'MONSTER':
        tplayer.monsterTin = tp
        tplayer.monsterCopper = cp
        tplayer.monsterSilver = sp
        tplayer.monsterGold = gp
        tplayer.monsterPlatinum = pp
    else:
        mob.player.sendGameText(RPG_MSG_GAME_DENIED, "Can't extract realm argument.\\nUsage: /imm setwealth <realm = light/darkness/monster> <amount in tin>.\\n")
        return
    ext = ('pp', 'gp', 'sp', 'cp', 'tp')
    worth = (pp,
     gp,
     sp,
     cp,
     tp)
    moneyString = ', '.join(('%i%s' % (w, ext[i]) for i, w in enumerate(worth) if w != 0))
    mob.player.sendGameText(RPG_MSG_GAME_WHITE, "%s's wealth in the %s realm has been set to: %s.\\nPlease inform the player once all adjustments have taken place.\\n" % (mob.target.name, args[0], moneyString))
    print "Immortal %s has set %s's wealth in the %s realm to %s." % (mob.player.publicName,
     tplayer.fantasyName,
     args[0],
     moneyString)


COMMANDS = {}
COMMANDS['SPAWN'] = CmdSpawn
COMMANDS['DESPAWN'] = CmdDespawn
COMMANDS['SET'] = CmdSet
COMMANDS['KILL'] = CmdKill
COMMANDS['STASIS'] = CmdStasis
COMMANDS['WORLDAGGRO'] = CmdWorldAggro
COMMANDS['MYAGGRO'] = CmdMyAggro
COMMANDS['SYSMSG'] = CmdSystemMsg
COMMANDS['SCRIBE'] = CmdScribeMsg
COMMANDS['RELOADCOMMANDS'] = CmdReloadCommands
COMMANDS['RELOADMODULE'] = CmdReloadModule
COMMANDS['GIVEMONSTER'] = CmdGiveMonster
COMMANDS['GRANTMONSTER'] = CmdGrantMonster
COMMANDS['DENYMONSTER'] = CmdDenyMonster
COMMANDS['LISTMONSTERS'] = CmdListMonsters
COMMANDS['GETPLAYERPASSWORD'] = CmdGetPlayerPassword
COMMANDS['SETPLAYERPASSWORD'] = CmdSetPlayerPassword
COMMANDS['TP'] = CmdTP
COMMANDS['GIMME'] = CmdGimme
COMMANDS['MODSTAT'] = CmdModStat
COMMANDS['GRANTLEVEL'] = CmdGrantLevel
COMMANDS['GRANT'] = CmdGrant
COMMANDS['DENY'] = CmdDeny
COMMANDS['TESTAFX'] = CmdTestAFX
COMMANDS['GETDIMENSIONS'] = CmdGetDimensions
COMMANDS['CHECKWEALTH'] = CmdCheckWealth
COMMANDS['SETWEALTH'] = CmdSetWealth

def DoImmortalCommand(player, cmd, args):
    mob = player.curChar.mob
    if type(args) != list:
        args = [args]
    cmd = cmd.upper()
    if COMMANDS.has_key(cmd):
        COMMANDS[cmd](mob, args)
    else:
        print 'Unknown Command: %s' % cmd