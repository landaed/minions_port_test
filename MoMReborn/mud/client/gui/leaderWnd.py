# Embedded file name: mud\client\gui\leaderWnd.pyo
from tgenative import *
from mud.tgepython.console import TGEExport
from math import floor
from mud.world.defines import *
from twisted.internet import reactor
LEADERWND = None

class LeaderWnd:

    def __init__(self):
        self.alliesList = TGEObject('LEADER_MEMBERSLIST')
        self.inviteButton = TGEObject('LEADER_INVITE_BTN')
        self.kickButton = TGEObject('LEADER_KICK_BTN')
        self.disbandButton = TGEObject('LEADER_DISBAND_BTN')
        self.allynames = []

    def disable(self):
        self.alliesList.visible = False
        self.inviteButton.setActive(False)
        self.kickButton.setActive(False)
        self.disbandButton.setActive(False)

    def enable(self):
        self.alliesList.visible = True
        self.inviteButton.setActive(True)
        self.kickButton.setActive(True)
        self.disbandButton.setActive(True)

    def clearAllianceInfo(self):
        if self.allianceInfo:
            self.allianceInfo.broker.transport.loseConnection()
        self.allianceInfo = None
        return

    def setAllianceInfo(self, ainfo):
        from mud.client.playermind import PLAYERMIND
        if not PLAYERMIND or not PLAYERMIND.rootInfo:
            return
        self.allianceInfo = ainfo
        if ainfo.LEADER == PLAYERMIND.rootInfo.PLAYERNAME:
            self.enable()
        else:
            self.alliesList.clear()
            self.disable()
            return
        self.alliesList.setVisible(False)
        self.alliesList.clear()
        self.allynames = []
        x = 0
        for i, pname in enumerate(ainfo.PNAMES):
            if pname != PLAYERMIND.rootInfo.PLAYERNAME:
                cname = ainfo.NAMES[i][0]
                self.alliesList.addRow(x, str(cname))
                self.allynames.append(cname)
                x += 1

        self.alliesList.setSelectedRow(0)
        self.alliesList.scrollVisible(0)
        self.alliesList.setActive(True)
        self.alliesList.setVisible(True)

    def tick(self):
        pass


def PyOnInvite():
    from partyWnd import PARTYWND
    PARTYWND.mind.perspective.callRemote('PlayerAvatar', 'invite')


def PyOnDisband():
    from partyWnd import PARTYWND
    PARTYWND.mind.perspective.callRemote('PlayerAvatar', 'disband')


def PyOnKick():
    global LEADERWND
    from partyWnd import PARTYWND
    if not len(LEADERWND.allynames):
        return
    id = int(LEADERWND.alliesList.getSelectedId())
    PARTYWND.mind.perspective.callRemote('PlayerAvatar', 'kick', LEADERWND.allynames[id])


def PyExec():
    global LEADERWND
    LEADERWND = LeaderWnd()
    TGEExport(PyOnInvite, 'Py', 'OnInvite', 'desc', 1, 1)
    TGEExport(PyOnDisband, 'Py', 'OnDisband', 'desc', 1, 1)
    TGEExport(PyOnKick, 'Py', 'OnKick', 'desc', 1, 1)