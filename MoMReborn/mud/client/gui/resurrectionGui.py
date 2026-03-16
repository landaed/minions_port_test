# Embedded file name: mud\client\gui\resurrectionGui.pyo
from tgenative import *
from mud.tgepython.console import TGEExport
import traceback
RESURRECTIONWND = None

class ResurrectionWnd:

    def __init__(self):
        self.resList = TGEObject('ResurrectionList')
        self.resScroll = TGEObject('ResurrectionScroll')

    def set(self, names):
        tc = self.resList
        tc.setVisible(False)
        tc.clear()
        i = 0
        for name in names:
            TGEEval('ResurrectionList.addRow(%i,"%s");' % (i, name))
            i += 1

        tc.sort(0)
        tc.setSelectedRow(0)
        tc.scrollVisible(0)
        tc.setActive(True)
        tc.setVisible(True)


def OnResurrect():
    global RESURRECTIONWND
    r = RESURRECTIONWND.resList.getValue()
    TGEEval('Canvas.popDialog("ResurrectionGui");')
    from mud.client.playermind import PLAYERMIND
    PLAYERMIND.resurrect(r)


def PyExec():
    global RESURRECTIONWND
    RESURRECTIONWND = ResurrectionWnd()
    TGEExport(OnResurrect, 'Py', 'OnResurrect', 'desc', 1, 1)