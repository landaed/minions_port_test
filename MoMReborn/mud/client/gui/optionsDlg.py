# Embedded file name: mud\client\gui\optionsDlg.pyo
from tgenative import *
from mud.tgepython.console import TGEExport
import os, sys
INVALID = ['mouse2']

def KeyCanBeRemapped(args):
    key = args[1]
    if key in INVALID:
        return 0
    return 1


def SetGameDifficulty():
    from mud.world.core import CoreSettings
    v = int(TGEGetGlobal('$pref::gameplay::difficulty'))
    if v == 1:
        CoreSettings.DIFFICULTY = 0
    elif v == 2:
        CoreSettings.DIFFICULTY = 2
    else:
        CoreSettings.DIFFICULTY = 1


def OnRespawnTime():
    value = float(TGEGetGlobal('$pref::gameplay::monsterrespawn'))
    from mud.world.core import CoreSettings
    CoreSettings.RESPAWNTIME = value


def getSystemFonts():
    return ['Arial', 'Arial Bold', 'Lucida Console']


def OnLoadFontOptions():
    gameFontOptions = TGEObject('OptChatGameFont')
    chatFontOptions = TGEObject('OptChatSpeechFont')
    for index, font in enumerate(getSystemFonts()):
        gameFontOptions.add(font, 1 + index)
        chatFontOptions.add(font, 1 + index)

    gameFontOptions.setText('Arial')
    chatFontOptions.setText('Arial')


def PyExec():
    OnLoadFontOptions()
    from playerSettings import PLAYERSETTINGS
    if PLAYERSETTINGS:
        TGEEval('GameplayExtendedMacros.setValue(%i);' % PLAYERSETTINGS.useExtendedMacros)
    TGEExport(KeyCanBeRemapped, 'Py', 'KeyCanBeRemapped', 'desc', 2, 2)
    TGEExport(OnRespawnTime, 'Py', 'OnRespawnTimeChanged', 'desc', 1, 1)
    TGEExport(SetGameDifficulty, 'Py', 'SetGameDifficulty', 'desc', 1, 1)