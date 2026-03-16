# Embedded file name: mud\client\gui\newCharDlg.pyo
from tgenative import *
from mud.tgepython.console import TGEExport
from mud.world.shared.models import GetModelInfo
from mud.world.defines import *
from mud.gamesettings import *
from math import floor
PlayerPerspective = None
DARKNESS = False
SCORE_CONTROLS = {}
ADJ_CONTROLS = {}
MOD_CONTROLS = {}
TOTAL_CONTROLS = {}
from mud.world.shared.worlddata import NewCharacter
MyChar = NewCharacter()

def VerifyCharacter():
    race = TGEObject('RacePopup').getText()
    klass = TGEObject('ClassPopup').getText()
    sex = TGEObject('SexPopup').getText()
    name = TGEObject('CharacterNameTextCtrl').getValue()
    if not name or len(name) < 4:
        TGECall('MessageBoxOK', 'Invalid Character!', 'Character name must be at least 4 letters.')
        return False
    if len(name) > 11:
        TGECall('MessageBoxOK', 'Invalid Character!', 'Character name must be less than 12 letters.')
        return False
    if name.startswith(' ') or name.endswith(' '):
        TGECall('MessageBoxOK', 'Invalid Character!', 'Character name must not start or end with a space.')
        return False
    if not name.isalpha():
        TGECall('MessageBoxOK', 'Invalid Character!', 'Character name must not have numbers or other punctuation.')
        return False
    if not race or not len(race):
        TGECall('MessageBoxOK', 'Invalid Character!', 'You must choose a race.')
        return False
    if not klass or not len(klass):
        TGECall('MessageBoxOK', 'Invalid Character!', 'You must choose a class.')
        return False
    if not sex or not len(sex):
        TGECall('MessageBoxOK', 'Invalid Character!', 'You must choose a sex.')
        return False
    if MyChar.ptsRemaining:
        TGECall('MessageBoxOK', 'Invalid Character!', 'You must spend all your points.')
        return False
    return True


def GotNewCharacterResult(result):
    global PlayerPerspective
    TGECall('CloseMessagePopup')
    msg = result[1]
    if result[0]:
        title = 'Error!'
    else:
        title = 'Success!'
        TGEObject('CharacterNameTextCtrl').setValue('')
        TGEObject('NEWCHAR_GUIOBJECTVIEW').setEmpty()
        from worldGui import Setup
        Setup(PlayerPerspective, True)
        PlayerPerspective = None
    TGECall('MessageBoxOK', title, msg)
    return


def OnNewCharacterSubmit():
    global DARKNESS
    race = TGEObject('RacePopup').getText()
    if not VerifyCharacter():
        return
    klass = TGEObject('ClassPopup').getText()
    sex = TGEObject('SexPopup').getText()
    name = TGEObject('CharacterNameTextCtrl').getValue()
    name = name.capitalize()
    MyChar.name = name
    MyChar.sex = sex
    MyChar.klass = klass
    MyChar.race = race
    if DARKNESS:
        MyChar.realm = RPG_REALM_DARKNESS
    else:
        MyChar.realm = RPG_REALM_LIGHT
    if int(TGEObject('NEWCHARACTER_HEAVY').getValue()):
        MyChar.look = 2
    if int(TGEObject('NEWCHARACTER_SLIGHT').getValue()):
        MyChar.look = 0
    if int(TGEObject('NEWCHARACTER_MUSCULAR').getValue()):
        MyChar.look = 1
    TGECall('MessagePopup', 'Submitting Character...', 'Please wait...')
    d = PlayerPerspective.callRemote('PlayerAvatar', 'newCharacter', MyChar)
    d.addCallbacks(GotNewCharacterResult, Failure)


def OnModelChanged():
    race = TGEObject('RacePopup').getText()
    if int(TGEObject('NEWCHARACTER_HEAVY').getValue()):
        look = 2
    if int(TGEObject('NEWCHARACTER_SLIGHT').getValue()):
        look = 0
    if int(TGEObject('NEWCHARACTER_MUSCULAR').getValue()):
        look = 1
    sex = TGEObject('SexPopup').getText()
    nc = TGEObject('NEWCHAR_GUIOBJECTVIEW')
    nc.unmountObject('Sword1', 'mount0')
    nc.unmountObject('Sword2', 'mount1')
    size, model, tex, animation = GetModelInfo(race, sex, look)
    modelname = '~/data/shapes/character/models/%s' % model
    nc.setEmpty()
    nc.setObject('PlayerModel', modelname, '', 0)
    nc.setSkin(0, '~/data/shapes/character/textures/%s' % tex[0])
    nc.setSkin(1, '~/data/shapes/character/textures/%s' % tex[1])
    nc.setSkin(2, '~/data/shapes/character/textures/%s' % tex[2])
    nc.setSkin(3, '~/data/shapes/character/textures/%s' % tex[4])
    nc.setSkin(4, '~/data/shapes/character/textures/%s' % tex[5])
    nc.setSkin(5, '~/data/shapes/character/textures/%s' % tex[3])
    if race == 'Titan' and sex == 'Male':
        nc.setSkin(6, '~/data/shapes/character/textures/multi/titan_male_special')
    elif race == 'Titan' and sex == 'Female':
        nc.setSkin(6, '~/data/shapes/character/textures/multi/titan_female_special')
    animations = {'Human': ('humanoid', 'humanoidfemale'),
     'Titan': ('titanmale', 'titanmale'),
     'Elf': ('humanoid', 'humanoidfemale'),
     'Dark Elf': ('humanoid', 'humanoidfemale'),
     'Halfling': ('humanoidshort', 'humanoidshort'),
     'Dwarf': ('humanoidshort', 'humanoidshort'),
     'Gnome': ('humanoidshort', 'humanoidshort'),
     'Drakken': ('drakken', 'drakkenfemale'),
     'Ogre': ('humanoid', 'humanoid'),
     'Goblin': ('humanoidshort', 'humanoidshort'),
     'Orc': ('humanoidshort', 'humanoidshort'),
     'Troll': ('trollmale', 'trollmale')}
    index = 0
    if sex == 'Female':
        index = 1
    if not animations.has_key(race):
        race = 'Human'
    animation = animations[race][index]
    nc.loadDSQ('PlayerModel', '~/data/shapes/character/animations/%s/idle.dsq' % animation)
    nc.setSequence('PlayerModel', 'idle', 1)
    nc.mountObject('Sword1', '~/data/shapes/equipment/weapons/sword01.dts', '', 'PlayerModel', 'mount0', 0)
    nc.mountObject('Sword2', '~/data/shapes/equipment/weapons/sword01.dts', '', 'PlayerModel', 'mount1', 0)


def OnLookChanged():
    OnModelChanged()


def OnGenderChanged():
    OnModelChanged()


def OnRaceChanged():
    race = TGEObject('RacePopup').getText()
    rstat = RPG_RACE_STATS[race]
    MyChar.scores['STR'] = rstat.STR
    MyChar.scores['DEX'] = rstat.DEX
    MyChar.scores['REF'] = rstat.REF
    MyChar.scores['AGI'] = rstat.AGI
    MyChar.scores['BDY'] = rstat.BDY
    MyChar.scores['MND'] = rstat.MND
    MyChar.scores['WIS'] = rstat.WIS
    MyChar.scores['MYS'] = rstat.MYS
    classes = TGEObject('ClassPopup')
    classes.clear()
    clist = RPG_RACE_CLASSES[race]
    clist.sort()
    x = 0
    for s in clist:
        if DARKNESS:
            if s not in RPG_REALM_CLASSES[RPG_REALM_DARKNESS]:
                continue
        elif s not in RPG_REALM_CLASSES[RPG_REALM_LIGHT]:
            continue
        classes.add(s, x)
        x += 1

    SetControlsFromChar()
    TGEObject('ClassPopup').setSelected(0)
    OnModelChanged()


def SetControlsFromChar():
    TGEObject('NEWCHARPOINTSREMAINING').setText('Points Remaining: %s' % MyChar.ptsRemaining)
    for st in RPG_STATS:
        SCORE_CONTROLS[st].setText(MyChar.scores[st])
        total = MyChar.adjs[st] + MyChar.scores[st]
        if MyChar.adjs[st]:
            TGEEval('%s_ADJ.setText("\\c2%i");' % (st, MyChar.adjs[st]))
            TGEEval('%s_TOTAL.setText("\\c2%i");' % (st, total))
        else:
            TOTAL_CONTROLS[st].setText(total)
            ADJ_CONTROLS[st].setText(0)


def OnAddStat(args):
    statname = args[1]
    if MyChar.ptsRemaining >= 1:
        if MyChar.adjs[statname] < 50:
            MyChar.ptsRemaining -= 5
            MyChar.adjs[statname] += 5
        SetControlsFromChar()


def OnSubStat(args):
    statname = args[1]
    if not MyChar.adjs[statname]:
        return
    MyChar.ptsRemaining += 5
    MyChar.adjs[statname] -= 5
    SetControlsFromChar()


def Failure(reason):
    TGECall('CloseMessagePopup')
    TGECall('MessageBoxOK', 'Error!', reason.getErrorMessage())


def Setup(playerperp, darkness = False):
    global DARKNESS
    global PlayerPerspective
    DARKNESS = darkness
    PlayerPerspective = playerperp
    MyChar.reset()
    for s in RPG_STATS:
        MyChar.adjs[s] = 0

    MyChar.ptsRemaining = 100
    TGEObject('NEWCHARGUI_PORTRAITBUTTON').setBitmap('~/data/ui/charportraits/%s' % MyChar.portraitPic)
    for s in RPG_STATS:
        SCORE_CONTROLS[s] = TGEObject('%s_SCORE' % s)
        ADJ_CONTROLS[s] = TGEObject('%s_ADJ' % s)
        TOTAL_CONTROLS[s] = TGEObject('%s_TOTAL' % s)

    rctrl = TGEObject('RacePopup')
    rctrl.clear()
    x = 0
    races = RPG_REALM_RACES[RPG_REALM_LIGHT]
    if darkness:
        races = RPG_REALM_RACES[RPG_REALM_DARKNESS]
    races.sort()
    races.remove('Human')
    races.insert(0, 'Human')
    for r in races:
        rctrl.add(r, x)
        x += 1

    sexes = TGEObject('SexPopup')
    sexes.clear()
    x = 0
    for s in ['Male', 'Female']:
        sexes.add(s, x)
        x += 1

    TGEEval('canvas.setContent(NewCharacterGui);')
    TGEObject('NEWCHARACTER_HEAVY').setValue(0)
    TGEObject('NEWCHARACTER_SLIGHT').setValue(1)
    TGEObject('NEWCHARACTER_MUSCULAR').setValue(0)
    TGEObject('RacePopup').setSelected(0)
    TGEObject('SexPopup').setSelected(0)
    OnRaceChanged()
    SetControlsFromChar()
    TGEObject('CharacterNameTextCtrl').makeFirstResponder(1)


def OnNewCharacterCancel():
    global PlayerPerspective
    from worldGui import Setup
    Setup(PlayerPerspective)
    PlayerPerspective = None
    return


def ChoosePortrait(chosen):
    if not chosen:
        return
    from charPortraitWnd import SetChoosePortraitCallback
    MyChar.portraitPic = chosen
    TGEObject('NEWCHARGUI_PORTRAITBUTTON').setBitmap('~/data/ui/charportraits/%s' % chosen)


def OnNewCharChoosePortrait():
    from charPortraitWnd import SetChoosePortraitCallback
    SetChoosePortraitCallback(ChoosePortrait)
    TGEEval('canvas.pushDialog(CharPortraitWnd);')


def OnDefaultStats():
    klass = TGEObject('ClassPopup').getText()
    if RPG_DEFAULT_STATS.has_key(klass):
        MyChar.ptsRemaining = 0
        MyChar.adjs = {}
        for stat, value in zip(RPG_STATS, RPG_DEFAULT_STATS[klass]):
            MyChar.adjs[stat] = value

        SetControlsFromChar()


def PyExec():
    TGEExport(OnNewCharacterSubmit, 'Py', 'OnNewCharacterSubmit', 'desc', 1, 1)
    TGEExport(OnNewCharacterCancel, 'Py', 'OnNewCharacterCancel', 'desc', 1, 1)
    TGEExport(OnAddStat, 'Py', 'OnAddStat', 'desc', 2, 2)
    TGEExport(OnSubStat, 'Py', 'OnSubStat', 'desc', 2, 2)
    TGEExport(OnRaceChanged, 'Py', 'OnRaceChanged', 'desc', 1, 1)
    TGEExport(OnGenderChanged, 'Py', 'OnGenderChanged', 'desc', 1, 1)
    TGEExport(OnLookChanged, 'Py', 'OnLookChanged', 'desc', 1, 1)
    TGEExport(OnDefaultStats, 'Py', 'OnDefaultStats', 'desc', 1, 1)
    TGEExport(OnNewCharChoosePortrait, 'Py', 'OnNewCharChoosePortrait', 'desc', 1, 1)