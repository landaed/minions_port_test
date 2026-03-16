# Embedded file name: mud\client\gui\encyclopediaSearchDlg.pyo
from tgenative import *
from mud.tgepython.console import TGEExport
from encyclopediaWnd import encyclopediaSearch

def OnEncyclopediaSearchDlgSearch():
    searchvalue = TGEObject('ENCYCLOPEDIA_SEARCH').getValue()
    encyclopediaSearch(searchvalue)


def PyExec():
    TGEExport(OnEncyclopediaSearchDlgSearch, 'Py', 'OnEncyclopediaSearchDlgSearch', 'desc', 1, 1)