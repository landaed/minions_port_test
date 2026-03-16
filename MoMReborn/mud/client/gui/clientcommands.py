# Embedded file name: mud\client\gui\clientcommands.pyo
from tgenative import *
from mud.tgepython.console import TGEExport
from mud.gamesettings import *
from mud.client.gui.friendsWnd import FriendsWnd
FriendsWnd = FriendsWnd.instance
from mud.client.gui.tomeGui import TomeGui
TomeGui = TomeGui.instance
receiveGameText = TomeGui.receiveGameText
from mud.world.core import GenMoneyText
from mud.world.defines import *
from mud.worlddocs.utils import GetTWikiName
from datetime import datetime

def CmdAutoWalk(args, charIndex):
    if int(TGEGetGlobal('$mvAutoForward')):
        TGESetGlobal('$mvAutoForward', 2)
    else:
        TGESetGlobal('$mvAutoForward', 1)


def CmdPlayTrack(args, charIndex):
    from mud.client.jukebox import PlaySong
    song = ' '.join(args)
    PlaySong(song)


def CmdLocalTime(args, charIndex):
    n = datetime.now()
    s = n.strftime('%Y-%m-%d %H:%M:%S')
    receiveGameText(RPG_MSG_GAME_WHITE, 'The local time is %s.\\n' % s)


def CmdIgnore(args, charIndex):
    from playerSettings import PLAYERSETTINGS
    nick = ' '.join(args)
    if PLAYERSETTINGS.ignore(nick):
        receiveGameText(RPG_MSG_GAME_GAINED, 'You are now ignoring %s.\\n' % nick)
    else:
        receiveGameText(RPG_MSG_GAME_GAINED, 'You are already ignoring %s.\\n' % nick)


def CmdUnignore(args, charIndex):
    from playerSettings import PLAYERSETTINGS
    nick = ' '.join(args)
    if PLAYERSETTINGS.unignore(nick):
        receiveGameText(RPG_MSG_GAME_GAINED, 'You are no longer ignoring %s.\\n' % nick)
    else:
        receiveGameText(RPG_MSG_GAME_GAINED, 'You were not ignoring %s before, neither do you now.\\n' % nick)


def CmdIgnored(args, charIndex):
    from playerSettings import PLAYERSETTINGS
    IGNORED = PLAYERSETTINGS.ignored
    if len(IGNORED):
        text = 'You are currently ignoring: %s\\n' % ', '.join(IGNORED)
    else:
        text = "You aren't ignoring anyone.\\n"
    receiveGameText(RPG_MSG_GAME_WHITE, text)


def CmdFriend(args, charIndex):
    if len(args) >= 2:
        if args[0].lower() == 'add':
            name = ' '.join(args[1:])
            FriendsWnd.onAddFriend(name)
        elif args[0].lower() == 'remove':
            name = ' '.join(args[1:])
            FriendsWnd.onRemoveFriend(name)


def CmdGuildWho(args, charIndex):
    from mud.client.playermind import PLAYERMIND
    guildName = PLAYERMIND.rootInfo.GUILDNAME
    if not guildName:
        receiveGameText(RPG_MSG_GAME_DENIED, 'You are not a member of a guild.\\n')
        return
    text = 'Members of <%s> in the worlds of "%s":\\n' % (guildName, GAMENAME)
    for cname, info in FriendsWnd.remoteFriendsInfo.iteritems():
        matchGuild, wname, zname = info
        if matchGuild:
            text += '%s in %s on %s\\n' % (cname, zname, wname)

    text += '\\n'
    receiveGameText(RPG_MSG_GAME_EVENT, text)


def CmdAway(args, charIndex):
    from mud.client.irc import SetAwayMessage
    SetAwayMessage(' '.join(args))


def CmdMemo(args, charIndex):
    from mud.client.playermind import formatMLString
    receiveGameText(RPG_MSG_GAME_YELLOW, 'Memo: %s\\n' % formatMLString(' '.join(args).replace('\\', '\\\\')))


def ClearSpeechText(args, charIndex):
    TomeGui.speechText = ''
    TomeGui.speechTextCtrl.setText('')


def CmdCoords(args, charIndex):
    from mud.client.playermind import PLAYERMIND
    from playerSettings import PLAYERSETTINGS
    pos = PLAYERMIND.rootInfo.POSITION
    zoneName = PLAYERSETTINGS.zone
    text = 'Your position is %.2f %.2f %.2f in %s\\n' % (pos[0],
     pos[1],
     pos[2],
     zoneName)
    receiveGameText(RPG_MSG_GAME_EVENT, text)


def CmdMap(args, charIndex):
    from mud.client.playermind import PLAYERMIND
    from playerSettings import PLAYERSETTINGS
    pos = PLAYERMIND.rootInfo.POSITION
    desc = ' '.join(args)
    PLAYERSETTINGS.addPOI(desc, pos)


def CmdUnmap(args, charIndex):
    from playerSettings import PLAYERSETTINGS
    desc = ' '.join(args)
    PLAYERSETTINGS.removePOI(desc)


def CmdStopMacro(args, charIndex):
    from partyWnd import PARTYWND
    from macro import MACROMASTER
    if charIndex == None:
        charIndex = PARTYWND.curIndex
    MACROMASTER.stopNamedMacroForChar(charIndex, ' '.join(args))
    return


def CmdStopMacros(args, charIndex):
    from partyWnd import PARTYWND
    from macro import MACROMASTER
    if charIndex == None:
        charIndex = PARTYWND.curIndex
    MACROMASTER.stopMacrosForChar(charIndex)
    return


def CmdCraft(args, charIndex):
    from mud.client.playermind import formatMLString, GetMoMClientDBConnection
    from partyWnd import PARTYWND
    con = GetMoMClientDBConnection()
    if not len(args):
        receiveGameText(RPG_MSG_GAME_DENIED, 'Please specify a recipe name.\\n')
        return
    else:
        recipeName = formatMLString(' '.join(args).replace('\\', '\\\\'))
        result = con.execute('SELECT id,name,skillname,skill_level,cost_t_p FROM recipe WHERE LOWER(name) = LOWER("%s") LIMIT 1;' % recipeName).fetchone()
        if not result:
            receiveGameText(RPG_MSG_GAME_DENIED, '%s is not a valid recipe.  Please check the recipe name and try again.\\n' % recipeName)
            return
        recipeID, recipeName, skillname, skill_level, costTP = result
        if charIndex == None:
            charIndex = PARTYWND.curIndex
        cinfo = PARTYWND.charInfos[charIndex]
        charSkillLevel = cinfo.SKILLS.get(skillname, 0)
        if charSkillLevel < skill_level:
            receiveGameText(RPG_MSG_GAME_DENIED, '%s requires a %i skill in <a:Skill%s>%s</a>.\\n' % (cinfo.NAME,
             skill_level,
             GetTWikiName(skillname),
             skillname))
            return
        if PARTYWND.mind.rootInfo.TIN < costTP:
            receiveGameText(RPG_MSG_GAME_DENIED, 'This <a:Skill%s>%s</a> requires %s.\\n' % (GetTWikiName(skillname), skillname, GenMoneyText(costTP)))
            return
        if skillname.upper() in cinfo.SKILLREUSE:
            TomeGui.receiveGameTextPersonalized(RPG_MSG_GAME_DENIED, '$src is still cleaning $srchis tools,\\n$srche can use the <a:Skill%s>%s</a> skill again in about %i seconds.\\n' % (GetTWikiName(skillname), skillname, cinfo.SKILLREUSE[skillname.upper()]), cinfo)
            return
        ingredients = dict(((item_proto_id, count) for item_proto_id, count in con.execute('SELECT item_proto_id,count FROM recipe_ingredient WHERE recipe_id=%i AND count!=0' % recipeID).fetchall()))
        for item in cinfo.ITEMS.itervalues():
            for item_proto_id, count in ingredients.iteritems():
                if item.PROTOID == item_proto_id:
                    sc = item.STACKCOUNT
                    if not sc:
                        sc = 1
                    ingredients[item_proto_id] -= sc
                    if ingredients[item_proto_id] <= 0:
                        del ingredients[item_proto_id]
                    break

            if not len(ingredients):
                PARTYWND.mind.perspective.callRemote('PlayerAvatar', 'onCraft', charIndex, recipeID)
                return

        missing = dict(((con.execute('SELECT name FROM item_proto WHERE id=%i LIMIT 1;' % protoID).fetchone()[0], count) for protoID, count in ingredients.iteritems()))
        receiveGameText(RPG_MSG_GAME_DENIED, '%s lacks %s for this craft.\\n' % (cinfo.NAME, ', '.join(('%i <a:Item%s>%s</a>' % (count, GetTWikiName(name), name) for name, count in missing.iteritems()))))
        return


def CmdUseItem(args, charIndex):
    from mud.client.playermind import formatMLString
    from partyWnd import PARTYWND
    if not len(args):
        receiveGameText(RPG_MSG_GAME_DENIED, 'Please specify an item name.\\n')
        return
    else:
        if charIndex == None:
            charIndex = PARTYWND.curIndex
        charInfo = PARTYWND.charInfos[charIndex]
        itemName = formatMLString(' '.join(args).replace('\\', '\\\\'))
        itemNameUpper = itemName.upper()
        for itemSlot, itemInfo in charInfo.ITEMS.iteritems():
            if itemSlot == RPG_SLOT_CURSOR:
                continue
            if itemInfo.NAME.upper() == itemNameUpper:
                if not itemInfo.REUSETIMER:
                    PARTYWND.mind.perspective.callRemote('PlayerAvatar', 'onInvSlotCtrl', charInfo.CHARID, itemSlot)
                    break
        else:
            receiveGameText(RPG_MSG_GAME_DENIED, '%s has no %s ready for use.\\n' % (charInfo.NAME, itemName))

        return


def CmdPoison(args, charIndex):
    from mud.client.playermind import formatMLString
    from partyWnd import PARTYWND
    validSlots = {'PRIMARY': RPG_SLOT_PRIMARY,
     'SECONDARY': RPG_SLOT_SECONDARY,
     'OFFHAND': RPG_SLOT_SECONDARY,
     'RANGED': RPG_SLOT_RANGED,
     'PETPRIMARY': RPG_SLOT_PET_PRIMARY,
     'PETSECONDARY': RPG_SLOT_PET_SECONDARY,
     'PETRANGED': RPG_SLOT_PET_RANGED}
    if not len(args):
        receiveGameText(RPG_MSG_GAME_DENIED, 'Please specify a slot to apply a poison to and the poison name. Valid slots for poisoning are %s.\\n' % ', '.join(validSlots))
        return
    elif not len(args) > 1:
        receiveGameText(RPG_MSG_GAME_DENIED, 'Please specify a poison name after the slot to apply it to.\\n')
        return
    else:
        if charIndex == None:
            charIndex = PARTYWND.curIndex
        charInfo = PARTYWND.charInfos[charIndex]
        slotName = args[0].upper()
        applicationSlot = validSlots.get(slotName)
        if not applicationSlot:
            receiveGameText(RPG_MSG_GAME_DENIED, '%s is not a valid slot for poison application.  Valid slots are %s.\\n' % (args[0], ', '.join(validSlots)))
            return
        weaponCheck = charInfo.ITEMS.get(applicationSlot)
        if not weaponCheck:
            if applicationSlot > RPG_SLOT_PET_BEGIN:
                if not charInfo.RAPIDMOBINFO.PETNAME:
                    receiveGameText(RPG_MSG_GAME_DENIED, "Can't apply poison, %s has no pet.\\n" % charInfo.NAME)
                else:
                    receiveGameText(RPG_MSG_GAME_DENIED, "Can't apply poison, %s's pet has nothing equipped in this slot.\\n" % charInfo.NAME)
            else:
                receiveGameText(RPG_MSG_GAME_DENIED, "Can't apply poison, %s has nothing equipped in this slot.\\n" % charInfo.NAME)
            return
        poisonName = formatMLString(' '.join(args[1:]).replace('\\', '\\\\'))
        poisonNameUpper = poisonName.upper()
        for itemSlot, itemInfo in charInfo.ITEMS.iteritems():
            if itemSlot == RPG_SLOT_CURSOR:
                continue
            if itemInfo.NAME.upper() == poisonNameUpper:
                if not itemInfo.ISPOISON:
                    receiveGameText(RPG_MSG_GAME_DENIED, '%s is no poison.\\n' % poisonName)
                    return
                PARTYWND.mind.perspective.callRemote('PlayerAvatar', 'onApplyPoison', charInfo.CHARID, itemSlot, applicationSlot)
                break
        else:
            receiveGameText(RPG_MSG_GAME_DENIED, '%s has no %s ready for application.\\n' % (charInfo.NAME, poisonName))
            return

        return


def CmdCamp(args, charIndex):
    TGEEval('MessageBoxYesNo("Camp?", "Do you really want to camp and return to the Main Menu?","Py::OnReallyCamp();");')


CLIENTCOMMANDS = {}
CLIENTCOMMANDS['AUTOWALK'] = CmdAutoWalk
CLIENTCOMMANDS['PLAYTRACK'] = CmdPlayTrack
CLIENTCOMMANDS['LOCALTIME'] = CmdLocalTime
CLIENTCOMMANDS['IGNORE'] = CmdIgnore
CLIENTCOMMANDS['UNIGNORE'] = CmdUnignore
CLIENTCOMMANDS['IGNORED'] = CmdIgnored
CLIENTCOMMANDS['FRIEND'] = CmdFriend
CLIENTCOMMANDS['GWHO'] = CmdGuildWho
CLIENTCOMMANDS['AFK'] = CmdAway
CLIENTCOMMANDS['AWAY'] = CmdAway
CLIENTCOMMANDS['MEMO'] = CmdMemo
CLIENTCOMMANDS['CLEAR'] = ClearSpeechText
CLIENTCOMMANDS['COORDS'] = CmdCoords
CLIENTCOMMANDS['MAP'] = CmdMap
CLIENTCOMMANDS['UNMAP'] = CmdUnmap
CLIENTCOMMANDS['STOPMACRO'] = CmdStopMacro
CLIENTCOMMANDS['STOPMACROS'] = CmdStopMacros
CLIENTCOMMANDS['CRAFT'] = CmdCraft
CLIENTCOMMANDS['USEITEM'] = CmdUseItem
CLIENTCOMMANDS['POISON'] = CmdPoison
CLIENTCOMMANDS['CAMP'] = CmdCamp

def DoClientCommand(cmd, indexHack = None):
    cmd = cmd[1]
    args = cmd.split(' ')
    cmd = args[0][1:].upper()
    if cmd == 'CLIENT' and len(args) > 1:
        args = args[1:]
        cmd = args[0].upper()
    try:
        CLIENTCOMMANDS[cmd](args[1:], indexHack)
        return True
    except KeyError:
        return False


TGEExport(DoClientCommand, 'Py', 'DoClientCommand', 'desc', 2, 2)