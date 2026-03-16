# Embedded file name: mud\client\gui\worldGui.pyo
from tgenative import *
from mud.tgepython.console import TGEExport
from mud.world.defines import *
from mud.gamesettings import *
from os import makedirs, path as osPath
from md5 import new as newMD5
from mud.worldserver.embedded import ShutdownEmbeddedWorld
from mud.client.irc import IRCConnect
from mud.client.gui.masterGui import MasterLogout
from mud.client.gui.tomeGui import TomeGui
from mud.client.gui.masterLoginDlg import DoMasterLogin
PlayerPerspective = None
CHARACTERS = []
CHARINFOS = {}
LIGHTCHARACTERS = []
DARKCHARACTERS = []
MONSTERCHARACTERS = []
REALMCHARACTERS = LIGHTCHARACTERS
MAXPARTY = 6
MAXCHARS = 16
REALM = RPG_REALM_DEFAULT
PARTY = []
DOLASTPARTY = True
MONSTERCHOICES = []

def OnReallyEnterWorld():
    global PARTY
    global REALM
    global DOLASTPARTY
    global PlayerPerspective
    DOLASTPARTY = True
    from mud.client.playermind import PLAYERMIND
    PLAYERMIND.singleplayer = int(TGEGetGlobal('$Py::ISSINGLEPLAYER'))
    if not PLAYERMIND.singleplayer:
        from mud.client.gui.masterGui import WORLDINFO
        if WORLDINFO:
            PLAYERMIND.ircNick = PARTY[0].name
            try:
                IRCConnect(PLAYERMIND.ircNick)
            except:
                pass

    MasterLogout()
    TGESetGlobal('$Py::REALM', REALM)
    TGEObject('CHATGUI_GLOBAL_TOGGLE').setValue(1)
    TGEObject('CHATGUI_WORLD_TOGGLE').setValue(1)
    TGEObject('CHATGUI_ZONE_TOGGLE').setValue(1)
    TGEObject('CHATGUI_HELP_TOGGLE').setValue(1)
    TGEObject('CHATGUI_OFFTOPIC_TOGGLE').setValue(1)
    party = [ p.name for p in PARTY ]
    TGEEval('\n        LOAD_ZONEBITMAP.setBitmap("~/data/ui/loading/SPCreateZone");\n        LoadingProgress.setValue(0);\n        LOAD_MapDescription.setText("");\n        LoadingProgressTxt.setText("... Please Wait ... This may take a moment ...");\n        canvas.setcontent(LoadingGui);\n        LOAD_MapName.setText("Traveling");\n        canvas.repaint();\n    ')
    TGEEval('Canvas.setContent(LoadingGui);')
    PlayerPerspective.callRemote('PlayerAvatar', 'enterWorld', party, 0, '')


def OnEnterWorld():
    global CHARINFOS
    global MAXPARTY
    if not len(PARTY):
        TGECall('MessageBoxOK', 'Empty Party!', 'You should add at least one character to your party before entering the world.')
        return
    if len(PARTY) > MAXPARTY:
        TGECall('MessageBoxOK', 'Maximum Party Members!', 'This world allows up to %i characters in a party.' % MAXPARTY)
        return
    ci = CHARINFOS[PARTY[0].name]
    if ci.rename:
        DoRename(ci)
        return
    TGEEval('MessageBoxYesNo("Enter World?", "Are you ready?","Py::OnReallyEnterWorld();");')


def UpdatePartyList():
    global PARTY
    global CHARACTERS
    newlist = []
    for p in PARTY:
        found = False
        for c in CHARACTERS:
            if c.name == p.name:
                found = True
                break

        if found:
            newlist.append(p)

    PARTY = newlist
    tc = TGEObject('PartyList')
    tc.setVisible(False)
    tc.clear()
    for i, ci in enumerate(PARTY):
        name = ci.name
        klass = ci.klasses[0]
        level = ci.levels[0]
        status = ci.status
        race = ci.race
        TGEEval('PartyList.addRow(%i,"%s" TAB "%s" TAB "%s (%i)" TAB "%s");' % (i,
         name,
         race,
         klass,
         level,
         status))

    tc.setSelectedRow(0)
    tc.scrollVisible(0)
    tc.setActive(True)
    tc.setVisible(True)


def OnAddToParty():
    global PARTY
    global REALMCHARACTERS
    if REALM == RPG_REALM_MONSTER and len(PARTY):
        TGECall('MessageBoxOK', 'Rawr!', "Monsters don't like to party.")
        return
    if len(PARTY) == 6:
        return
    if MAXPARTY == 1:
        PARTY = []
    if len(PARTY) == MAXPARTY:
        TGECall('MessageBoxOK', 'Maximum Party Members!', 'This world allows up to %i characters in a party.' % MAXPARTY)
        return
    tc = TGEObject('CharacterList')
    sr = int(tc.getSelectedId())
    try:
        cinfo = REALMCHARACTERS[sr]
    except IndexError:
        return

    found = False
    for c in PARTY:
        if c.name == cinfo.name:
            found = True
            break

    if found:
        return
    PARTY.append(cinfo)
    UpdatePartyList()


def OnRemoveFromParty():
    if len(PARTY) == 0:
        return
    tc = TGEObject('PartyList')
    sr = int(tc.getSelectedId())
    p = PARTY[sr]
    PARTY.remove(p)
    UpdatePartyList()


def FillCharacters():
    tc = TGEObject('CharacterList')
    tc.setVisible(False)
    tc.clear()
    for i, ci in enumerate(REALMCHARACTERS):
        name = ci.name
        klass = ci.klasses[0]
        level = ci.levels[0]
        status = ci.status
        race = ci.race
        alignment = ci.realm
        e = 'CharacterList.addRow(%i,"%s" TAB "%s" TAB "%s (%i)" TAB "%s");' % (i,
         name,
         race,
         klass,
         level,
         status)
        TGEEval(e)

    tc.sort(0)
    tc.setSelectedRow(0)
    tc.scrollVisible(0)
    tc.setActive(True)
    tc.setVisible(True)
    UpdatePartyList()


def QueryCharactersResults(results):
    global MONSTERCHARACTERS
    global REALM
    global CHARACTERS
    global LIGHTCHARACTERS
    global MONSTERCHOICES
    global CHARINFOS
    global DARKCHARACTERS
    global DOLASTPARTY
    global MAXPARTY
    global REALMCHARACTERS
    if len(results) == 2:
        cinfos, mspawns = results
        maxparty = 6
    else:
        cinfos, mspawns, maxparty = results
    TGECall('CloseMessagePopup')
    MAXPARTY = maxparty
    CHARACTERS = cinfos
    DARKCHARACTERS = []
    LIGHTCHARACTERS = []
    MONSTERCHARACTERS = []
    MONSTERCHOICES = mspawns
    CHARINFOS = {}
    for ci in cinfos:
        CHARINFOS[ci.name] = ci
        if ci.realm == RPG_REALM_DARKNESS:
            DARKCHARACTERS.append(ci)
        elif ci.realm == RPG_REALM_MONSTER:
            MONSTERCHARACTERS.append(ci)
        else:
            LIGHTCHARACTERS.append(ci)

    gotone = False
    if DOLASTPARTY:
        DOLASTPARTY = False
        from playerSettings import PLAYERSETTINGS
        REALM, lastParty = PLAYERSETTINGS.loadLastParty()
        if REALM == RPG_REALM_DARKNESS:
            TGEObject('REALM_MOD_BUTTON').performClick()
            REALMCHARACTERS = DARKCHARACTERS
        elif REALM == RPG_REALM_MONSTER:
            TGEObject('REALM_MONSTER_BUTTON').performClick()
            REALMCHARACTERS = MONSTERCHARACTERS
        else:
            TGEObject('REALM_FOL_BUTTON').performClick()
            REALMCHARACTERS = LIGHTCHARACTERS
        for lp in lastParty:
            for ci in REALMCHARACTERS:
                if ci.name == lp:
                    gotone = True
                    PARTY.append(ci)

    elif REALM == RPG_REALM_DARKNESS:
        REALMCHARACTERS = DARKCHARACTERS
    elif REALM == RPG_REALM_MONSTER:
        REALMCHARACTERS = MONSTERCHARACTERS
    else:
        REALMCHARACTERS = LIGHTCHARACTERS
    FillCharacters()
    UpdatePartyList()
    tc = TGEObject('MOM_MONSTER_LIST')
    tc.setVisible(False)
    tc.clear()
    for i, name in enumerate(mspawns):
        TGEEval('MOM_MONSTER_LIST.addRow(%i,"%s");' % (i, name))

    tc.sort(0)
    tc.setSelectedRow(0)
    tc.scrollVisible(0)
    tc.setActive(True)
    tc.setVisible(True)


def OnQueryCharacters():
    TGECall('MessagePopup', 'Retrieving Characters...', 'Please wait...')
    PlayerPerspective.callRemote('PlayerAvatar', 'queryCharacters').addCallbacks(QueryCharactersResults, Failure)


def Failure(reason):
    TGECall('CloseMessagePopup')
    TGECall('MessageBoxOK', 'Error!', reason.getErrorMessage())


def GotDeleteCharacterResult(result):
    TGECall('CloseMessagePopup')
    msg = result[1]
    if result[0]:
        title = 'Error!'
    else:
        title = 'Success!'
        OnQueryCharacters()
    TGECall('MessageBoxOK', title, msg)


def OnReallyDeleteCharacter():
    tc = TGEObject('CharacterList')
    sr = int(tc.getSelectedId())
    if sr >= len(REALMCHARACTERS):
        return
    cinfo = REALMCHARACTERS[sr]
    cName = TGEObject('CharDeleteWnd_Name').getValue()
    if cName.upper() != cinfo.name.upper():
        TGECall('MessageBoxOK', 'Deletion cancelled', 'Deletion of the character has been cancelled.\n\nThe character selected in the list was %s, you entered %s.' % (cinfo.name, cName))
        return
    TGECall('MessagePopup', 'Deleting Character...', 'Please wait...')
    PlayerPerspective.callRemote('PlayerAvatar', 'deleteCharacter', cinfo.name).addCallbacks(GotDeleteCharacterResult, Failure)
    from playerSettings import PLAYERSETTINGS
    PLAYERSETTINGS.characterDeleted(cinfo.name)


def OnDeleteCharacter():
    tc = TGEObject('CharacterList')
    sr = int(tc.getSelectedId())
    if sr >= len(REALMCHARACTERS):
        return
    cinfo = REALMCHARACTERS[sr]
    TGEObject('CharDeleteWnd_Message').setText('<font:Arial Bold:14><just:center>To make absolutely sure that the correct character gets deleted, please type its name here.\n\nYou selected %s.' % cinfo.name)
    TGEObject('CharDeleteWnd_Name').setText('')
    TGEEval('Canvas.pushDialog(CharDeleteWnd);')
    TGEObject('CharDeleteWnd_Name').makeFirstResponder(1)


def OnNewCharacter():
    if len(REALMCHARACTERS) >= MAXCHARS:
        TGECall('MessageBoxOK', 'Too many characters', 'You currently more than %d characters.\nDelete old ones to create new.' % MAXCHARS)
        return
    if REALM != RPG_REALM_MONSTER:
        from newCharDlg import Setup
        Setup(PlayerPerspective, REALM == RPG_REALM_DARKNESS)
    else:
        if not len(MONSTERCHOICES):
            TGECall('MessageBoxOK', 'No Monsters Available', 'You currently have no monster templates available.\nMonster templates can be unlocked in the Fellowship of Light and Minions of Darkness Realms.')
            return
        TGEEval('Canvas.pushDialog(NewMonsterSelection);MONSTER_NAME.makeFirstResponder(true);')


def Setup(playerperp, fromNewChar = False):
    global PARTY
    global PlayerPerspective
    TomeGui.instance.reset()
    if not fromNewChar:
        PARTY = []
    PlayerPerspective = None
    TGEObject('CharacterList').clear()
    TGEObject('PartyList').clear()
    TGEEval('Canvas.setContent(WorldGui);')
    PlayerPerspective = playerperp
    OnQueryCharacters()
    from mud.client.gui.masterGui import WORLDINFO
    if WORLDINFO:
        if 'RvR Premium ' in WORLDINFO.worldName:
            TGECall('MessageBoxOK', 'Player vs Player Server', 'Players may harm other players on this server.\n\nYou may lose equipment to other players.\n\nEnter at your own risk!')
    return


def ClearPlayerPerspective():
    global PlayerPerspective
    global DOLASTPARTY
    PlayerPerspective = None
    DOLASTPARTY = True
    return


def OnRealmFOL():
    global PARTY
    global REALM
    global REALMCHARACTERS
    if REALM == RPG_REALM_LIGHT:
        return
    PARTY = []
    REALM = RPG_REALM_LIGHT
    REALMCHARACTERS = LIGHTCHARACTERS
    FillCharacters()
    from playerSettings import PLAYERSETTINGS
    getRealm, lastParty = PLAYERSETTINGS.loadLastParty(RPG_REALM_LIGHT)
    for lp in lastParty:
        for ci in REALMCHARACTERS:
            if ci.name == lp:
                gotone = True
                PARTY.append(ci)

    UpdatePartyList()


def OnRealmMOD():
    global PARTY
    global REALM
    global REALMCHARACTERS
    if REALM == RPG_REALM_DARKNESS:
        return
    PARTY = []
    REALM = RPG_REALM_DARKNESS
    REALMCHARACTERS = DARKCHARACTERS
    FillCharacters()
    from playerSettings import PLAYERSETTINGS
    getRealm, lastParty = PLAYERSETTINGS.loadLastParty(RPG_REALM_DARKNESS)
    for lp in lastParty:
        for ci in REALMCHARACTERS:
            if ci.name == lp:
                gotone = True
                PARTY.append(ci)

    UpdatePartyList()


def OnRealmMonster():
    global PARTY
    global REALM
    global REALMCHARACTERS
    if REALM == RPG_REALM_MONSTER:
        return
    PARTY = []
    REALM = RPG_REALM_MONSTER
    REALMCHARACTERS = MONSTERCHARACTERS
    FillCharacters()
    from playerSettings import PLAYERSETTINGS
    getRealm, lastParty = PLAYERSETTINGS.loadLastParty(RPG_REALM_MONSTER)
    for lp in lastParty:
        for ci in REALMCHARACTERS:
            if ci.name == lp:
                gotone = True
                PARTY.append(ci)

    UpdatePartyList()


def GotNewMonsterResult(result):
    TGECall('CloseMessagePopup')
    code = result[0]
    msg = result[1]
    if code:
        title = 'Error!'
    else:
        title = 'Success!'
        TGEObject('CharacterNameTextCtrl').setValue('')
    TGECall('MessageBoxOK', title, msg)
    if not code:
        Setup(PlayerPerspective, True)


def PyOnMakeMonster():
    tc = TGEObject('MOM_MONSTER_LIST')
    sr = int(tc.getSelectedId())
    mspawn = MONSTERCHOICES[sr]
    name = TGEObject('MONSTER_NAME').getValue()
    if not name or len(name) < 4:
        TGECall('MessageBoxOK', 'Invalid Monster!', 'Monster name must be at least 4 letters.')
        return False
    if len(name) > 18:
        TGECall('MessageBoxOK', 'Invalid Monster!', 'Monster name must be less than 18 letters.')
        return False
    if not name.replace(' ', '').isalpha():
        TGECall('MessageBoxOK', 'Invalid Monster!', 'Monster name must not have numbers or other punctuation.')
        return False
    if name.endswith(' '):
        TGECall('MessageBoxOK', 'Invalid Monster!', 'Monster name must not end with a space.')
        return False
    TGEEval('Canvas.popDialog(NewMonsterSelection);')
    TGECall('MessagePopup', 'Submitting Character...', 'Please wait...')
    PlayerPerspective.callRemote('PlayerAvatar', 'newMonster', name, mspawn).addCallbacks(GotNewMonsterResult, Failure)


def CheckName(name):
    if not name or len(name) < 4:
        TGECall('MessageBoxOK', 'Invalid Name!', 'Character name must be at least 4 letters.')
        return False
    mx = 11
    if REALM == RPG_REALM_MONSTER:
        mx = 18
    if len(name) > mx:
        TGECall('MessageBoxOK', 'Invalid Name!', 'Character name must be less than %i letters.' % mx)
        return False
    if name.endswith(' '):
        TGECall('MessageBoxOK', 'Invalid Name!', 'Character name must not end with a space.')
        return False
    if REALM != RPG_REALM_MONSTER:
        if not name.isalpha():
            TGECall('MessageBoxOK', 'Invalid Name!', 'Character name must not have numbers or other punctuation.')
            return False
    elif not name.replace(' ', '').isalpha():
        TGECall('MessageBoxOK', 'Invalid Name!', 'Character name must not have numbers or other punctuation.')
        return False
    return True


MUSTRENAME = False
RENAMENAME = ''
NEWNAME = ''

def GotRename(results):
    global NEWNAME
    global RENAMENAME
    TGECall('CloseMessagePopup')
    r, msg = results
    if r:
        TGECall('MessageBoxOK', 'Rename problem!', msg)
        TGEEval('Canvas.popDialog(CharRenameWnd);')
        return False
    from playerSettings import PLAYERSETTINGS
    PLAYERSETTINGS.renameCharacter(RENAMENAME, NEWNAME)
    PARTY[0].name = NEWNAME
    TGEEval('Canvas.popDialog(CharRenameWnd);')
    OnReallyEnterWorld()


def OnRenameCharacter():
    global NEWNAME
    global MUSTRENAME
    name = TGEObject('CHARRENAMEWND_NAME').getValue()
    if not name:
        name = RENAMENAME
    if REALM != RPG_REALM_MONSTER:
        name = name.capitalize()
    else:
        name = name.title()
        name = name.replace('The ', 'the ')
        name = name.replace('To ', 'to ')
        name = name.replace('And ', 'and ')
    if MUSTRENAME and name.lower() == RENAMENAME.lower():
        TGECall('MessageBoxOK', 'Invalid Name!', 'Please choose a name that is different than your existing one.')
        return False
    if not CheckName(name):
        return False
    NEWNAME = name
    TGECall('MessagePopup', 'Communicating with server...', 'Please wait...')
    PlayerPerspective.callRemote('PlayerAvatar', 'renameCharacter', RENAMENAME, NEWNAME).addCallbacks(GotRename, Failure)


def DoRename(cinfo):
    global RENAMENAME
    global MUSTRENAME
    MUSTRENAME = False
    if cinfo.rename == 2:
        MUSTRENAME = True
    RENAMENAME = cinfo.name
    if MUSTRENAME:
        TGEObject('CharRenameWnd_Window').setText('Rename %s (Required)' % cinfo.name)
        TGEObject('CHARRENAMEWND_MESSAGE').SetValue('Please rename %s.  The name should be fantasy themed and inoffensive.' % cinfo.name)
    else:
        TGEObject('CharRenameWnd_Window').setText('Rename %s (Optional)' % cinfo.name)
        TGEObject('CHARRENAMEWND_MESSAGE').SetValue('You may rename %s.  The name should be fantasy themed and inoffensive.\n\nIf you wish to keep your existing name, simply leave the text blank and click rename.' % cinfo.name)
    TGEObject('CHARRENAMEWND_NAME').setValue('')
    TGEEval('Canvas.pushDialog(CharRenameWnd);')
    TGEObject('CHARRENAMEWND_NAME').makeFirstResponder(1)


def PyExec():
    TGEEval('REALM_FOL_BUTTON.performClick();')
    TGEExport(OnReallyEnterWorld, 'Py', 'OnReallyEnterWorld', 'desc', 1, 1)
    TGEExport(OnEnterWorld, 'Py', 'OnEnterWorld', 'desc', 1, 1)
    TGEExport(OnAddToParty, 'Py', 'OnAddToParty', 'desc', 1, 1)
    TGEExport(OnRemoveFromParty, 'Py', 'OnRemoveFromParty', 'desc', 1, 1)
    TGEExport(OnNewCharacter, 'Py', 'OnNewCharacter', 'desc', 1, 1)
    TGEExport(OnDeleteCharacter, 'Py', 'OnDeleteCharacter', 'desc', 1, 1)
    TGEExport(OnReallyDeleteCharacter, 'Py', 'OnReallyDeleteCharacter', 'desc', 1, 1)
    TGEExport(OnRealmFOL, 'Py', 'OnRealmFOL', 'desc', 1, 1)
    TGEExport(OnRealmMOD, 'Py', 'OnRealmMOD', 'desc', 1, 1)
    TGEExport(OnRealmMonster, 'Py', 'OnRealmMonster', 'desc', 1, 1)
    TGEExport(PyOnMakeMonster, 'Py', 'OnMakeMonster', 'desc', 1, 1)
    TGEExport(OnRenameCharacter, 'Py', 'OnRenameCharacter', 'desc', 1, 1)