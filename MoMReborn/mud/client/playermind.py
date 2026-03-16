# Embedded file name: mud\client\playermind.pyo
from tgenative import *
from mud.tgepython.console import TGEExport
from twisted.spread import pb
from twisted.internet import defer, reactor
from twisted.cred.credentials import UsernamePassword
from mud.gamesettings import *
from mud.client.sounds import SOUNDS
from mud.client.gui.clientcommands import DoClientCommand
from mud.client.gui.encyclopediaWnd import encyclopediaGetLink, OnEncyclopediaOnURL, encyclopediaSearch
from mud.client.gui.friendsWnd import FriendsWnd
FriendsWnd = FriendsWnd.instance
from mud.client.gui.itemContainerWnd import ItemContainerWnd
ItemContainerWnd = ItemContainerWnd.instance
from mud.client.gui.lootWnd import LootWnd
LootWnd = LootWnd.instance
from mud.client.gui.macroWnd import MacroWnd
MacroWnd = MacroWnd.instance
from mud.client.gui.masterLoginDlg import DoMasterLogin
from mud.client.gui.tomeGui import TomeGui
TomeGui = TomeGui.instance
receiveGameText = TomeGui.receiveGameText
from mud.simulation.simmind import SimMind
from mud.world.shared.playdata import IsDirty
from mud.world.shared.worlddata import ZoneConnectionInfo
from mud.world.core import CoreSettings
from mud.world.defines import *
from mud.world.shared.vocals import *
from md5 import md5
import re
from pysqlite2 import dbapi2 as sqlite
import sys
from time import time as sysTime
import traceback
import types
LASTCHANNEL = 'M'
IRCCHANNELS = ('H',
 'HELP',
 'O',
 'OFFTOPIC',
 'M',
 'MOM')
CHATCHANNELS = ('H',
 'HELP',
 'O',
 'OFFTOPIC',
 'M',
 'MOM',
 'W',
 'WORLD',
 'Z',
 'ZONE',
 'S',
 'SAY',
 'A',
 'ALLIANCE',
 'G',
 'GUILD',
 'E',
 'EMOTE',
 'ME',
 'GC',
 'GMCHAT')
TOGGLEABLECHANNELS = {'H': 1,
 'HELP': 1,
 'O': 1 << 1,
 'OFFTOPIC': 1 << 1,
 'M': 1 << 2,
 'MOM': 1 << 2,
 'W': 1 << 3,
 'WORLD': 1 << 3,
 'Z': 1 << 4,
 'ZONE': 1 << 4,
 'COMBAT': 1 << 5}
QUOTE_REPLACER = re.compile('(?<!\\\\)"')
PLAYERMIND = None
CLIENTEXITED = False
EXITFORCED = False
CEREBRUM = None

def GetMoMClientDBConnection():
    global CEREBRUM
    if not CEREBRUM:
        CEREBRUM = sqlite.connect('./%s/data/worlds/multiplayer.baseline/world.db' % GAMEROOT)
        CEREBRUM.text_factory = sqlite.OptimizedUnicode
    return CEREBRUM


class PerspectiveWrapper():

    def __init__(self, perp):
        self.perspective = perp
        self.broker = perp.broker
        self.commands = []
        self.running = None
        self.lasttime = sysTime()
        return

    def commandDone(self, result):
        self.running = False
        return result

    def commandFailed(self, result):
        self.running = False
        print 'commandFailed'

    def tick(self):
        if self.running or not len(self.commands):
            return
        delta = sysTime() - self.lasttime
        if delta < 0.25:
            return
        self.lasttime = sysTime()
        d, _name, args, kw = self.commands.pop(0)
        nd = self.perspective.callRemote(_name, *args, **kw)
        nd.chainDeferred(d)
        self.running = True

    def callRemote(self, _name, *args, **kw):
        global PLAYERMIND
        num = 25
        if PLAYERMIND and PLAYERMIND.charInfos and len(PLAYERMIND.charInfos):
            num = len(PLAYERMIND.charInfos) * 8
        if len(self.commands) < num:
            d = defer.Deferred()
            d.addCallback(self.commandDone)
            d.addErrback(self.commandFailed)
            c = (d,
             _name,
             args,
             kw)
            self.commands.append(c)
            return d
        receiveGameText(RPG_MSG_GAME_DENIED, 'The command buffer is full.\\n')


class PlayerMind(pb.Root):
    directConnect = ''

    def __init__(self):
        global PLAYERMIND
        from gui.partyWnd import PARTYWND
        PLAYERMIND = self
        self.perspective = None
        self.simMind = None
        PARTYWND.mind = self
        self.cursor = TGEObject('DefaultCursor')
        self.cursorItem = None
        self.nagTime = 180
        self.inventoryCmdAvailableTime = 0
        self.resizeCmdAvailableTime = 0
        self.running = True
        self.rootInfo = None
        t = sysTime()
        self.stopCastingTimers = {0: t,
         1: t,
         2: t,
         3: t,
         4: t,
         5: t}
        self.paused = False
        TGESetGlobal('$GamePaused', self.paused)
        self.lastAdTime = sysTime()
        self.party = None
        self.ircNick = None
        self.charInfos = {}
        self.singleplayer = 0
        self.initialFriendsSubmit = False
        return

    def setPerspective(self, perp):
        self.perspective = PerspectiveWrapper(perp)

    def gotJumpServerResult(self, perspective):
        self.setPerspective(perspective)
        perspective.callRemote('PlayerAvatar', 'jumpIntoWorld', self.party[0])

    def gotJumpServerFailure(self, reason):
        print 'jump failure %s' % reason

    def remote_jumpServer(self, wip, wport, wpassword, zport, zpassword, party):
        if self.rootInfo:
            from gui.playerSettings import PLAYERSETTINGS
            PLAYERSETTINGS.storeWindowSettings()
        ip = wip if wip else self.worldIP
        print 'JumpServer %s:%d' % (ip, wport)
        mind = PlayerMind()
        mind.worldIP = self.worldIP
        mind.ircNick = self.ircNick
        self.running = False
        TGEEval('disconnect();Canvas.setContent(LoadingGui);')
        mind.party = party
        factory = pb.PBClientFactory()
        factory.unsafeTracebacks = LOCALTEST or GAMEBUILD_TEST
        reactor.connectTCP(ip, wport, factory, timeout=DEF_TIMEOUT)
        MASTER_LOGIN_PLAYER = TGEObject('MASTER_LOGIN_PLAYER')
        MASTER_LOGIN_GUARDIAN = TGEObject('MASTER_LOGIN_GUARDIAN')
        MASTER_LOGIN_IMMORTAL = TGEObject('MASTER_LOGIN_IMMORTAL')
        role = 'Player'
        if TGEGetGlobal('$pref::GM_LOGIN') == '1':
            TGESetGlobal('$pref::GM_LOGIN_ROLE', 'Player')
            if int(MASTER_LOGIN_GUARDIAN.getValue()):
                TGESetGlobal('$pref::GM_LOGIN_ROLE', 'Guardian')
                role = 'Guardian'
            if int(MASTER_LOGIN_IMMORTAL.getValue()):
                TGESetGlobal('$pref::GM_LOGIN_ROLE', 'Immortal')
                role = 'Immortal'
        password = md5(wpassword).digest()
        d = factory.login(UsernamePassword('%s-%s' % (TGEGetGlobal('$pref::PublicName'), role), password), mind)
        d.addCallbacks(mind.gotJumpServerResult, mind.gotJumpServerFailure)
        return d

    def tick(self):
        if self.perspective:
            if self.perspective.broker.disconnected:
                self.running = False
                from mud.client.irc import IRCDisconnect
                try:
                    IRCDisconnect()
                except:
                    traceback.print_exc()

                TGEEval('\n                if (PlayGui.isAwake())\n                {\n                    disconnect();\n                    Canvas.setContent(MainMenuGui);\n                    MessageBoxOK( "Disconnected", "You have been disconnected from the server." );\n                }\n                ')
                TGESetGlobal('$Py::WORLDNAME', '')
            else:
                self.perspective.tick()
            if not self.initialFriendsSubmit:
                self.initialFriendsSubmit = True
                FriendsWnd.submitFriendsList()
        if not self.running:
            return
        try:
            from gui.partyWnd import PARTYWND
            from gui.tacticalGui import TACTICALGUI
            from gui.itemInfoWnd import ITEMINFOWND
            from gui.charMiniWnd import CHARMINIWND
            from gui.npcWnd import NPCWND
            from gui.allianceWnd import ALLIANCEWND
            from gui.leaderWnd import LEADERWND
            from gui.buffWnd import BUFFWND
            itemInfo = self.cursorItem
            cursor = self.cursor
            if not itemInfo and not cursor.bitmapName.startswith('%s/data/ui/icons/' % GAMEROOT) and not cursor.bitmapName.startswith('%s/data/ui/spellicons/' % GAMEROOT):
                cursor.bitmapName = ''
                cursor.sizeX = -1
                cursor.sizeY = -1
                cursor.hotSpot = '0 0'
                cursor.number = -1
                cursor.u0 = 0
                cursor.v0 = 0
                cursor.u1 = 1
                cursor.v1 = 1
            elif itemInfo:
                cursor.bitmapName = '%s/data/ui/items/%s/0_0_0' % (GAMEROOT, itemInfo.BITMAP)
                cursor.sizeX = 50
                cursor.sizeY = 50
                cursor.u0 = 0
                cursor.v0 = 0
                cursor.u1 = 1
                cursor.v1 = 1
                cursor.hotSpot = '0 0'
                cursor.number = -1
                if itemInfo.STACKMAX > 1:
                    cursor.number = itemInfo.STACKCOUNT
            if self.rootInfo.bankDirty:
                NPCWND.bankPane.set(self.rootInfo.BANK)
                self.rootInfo.bankDirty = False
            cinfo = self.charInfos[PARTYWND.curIndex]
            TGESetGlobal('$Py::SelectionCharacterIndex', PARTYWND.curIndex)
            if False:
                for x, c in self.charInfos.iteritems():
                    linktarget = c.clientSettings['LINKTARGET']
                    if linktarget:
                        for y, lt in self.charInfos.iteritems():
                            if lt.NAME == linktarget:
                                if lt.RAPIDMOBINFO.TGTID:
                                    if lt.RAPIDMOBINFO.TGTID != c.RAPIDMOBINFO.TGTID:
                                        self.perspective.callRemote('PlayerAvatar', 'doCommand', 'TARGETID', [x, lt.RAPIDMOBINFO.TGTID, 0])
                                        break

                    defaulttarget = c.clientSettings['DEFAULTTARGET']
                    if defaulttarget and not c.RAPIDMOBINFO.TGTID:
                        for y, lt in self.charInfos.iteritems():
                            if lt.NAME == defaulttarget:
                                self.perspective.callRemote('PlayerAvatar', 'doCommand', 'TARGETID', [x, lt.MOBID, 0])
                                break

            if not self.singleplayer:
                try:
                    if self.ircNick != self.charInfos[0].NAME:
                        self.ircNick = self.charInfos[0].NAME
                        from irc import ChangeNick
                        ChangeNick(self.ircNick)
                except:
                    pass

            PARTYWND.tick()
            CHARMINIWND.tick()
            NPCWND.tick()
            ALLIANCEWND.tick()
            BUFFWND.tick()
            MacroWnd.setFromCharacterInfos(self.charInfos)
            ITEMINFOWND.tick(cinfo)
            from gui.trackingWnd import TRACKINGWND
            if TRACKINGWND.trackingId or TRACKINGWND.trackInterest:
                frame = TGEGetTrackingFrame(TRACKINGWND.trackLocation)
                TRACKINGWND.trackingBitmap.setBitmap('~/data/ui/tracking/tracking%i' % frame)
            else:
                TRACKINGWND.trackingBitmap.setBitmap('')
            from gui.macro import MACROMASTER
            MACROMASTER.tick()
        except:
            traceback.print_exc()

        t = TGEGetGlobal('$Gui::ToolTip')
        if not t or t == 'None':
            TGEObject('MOM_TOOLTIP_BORDER').visible = False
        else:
            tips = TGEGetGlobal('$pref::game::tooltips')
            if not tips or tips == 'None':
                tips = 1
                TGESetGlobal('$pref::game::tooltips', '1')
            tips = int(tips)
            if not tips and not t.startswith('XXX:'):
                TGEObject('MOM_TOOLTIP_BORDER').visible = False
            else:
                tt = TGEObject('MOM_TOOLTIP')
                if t.startswith('XXX:'):
                    t = t[4:]
                border = TGEObject('MOM_TOOLTIP_BORDER')
                tt.setText(t)
                extentx = int(tt.getTextWidth())
                border.visible = True
                border.setExtent(extentx + 48, 27)
        self.playermindTick = reactor.callLater(0.1, self.tick)

    def camp(self, result, quit = False):
        global EXITFORCED
        TGESetGlobal('$Py::CAMPQUIT', 1)
        try:
            self.simMind.canSeeTick.cancel()
        except:
            pass

        try:
            self.simMind.updateSimObjectsTick.cancel()
        except:
            pass

        try:
            self.simMind.brainsTick.cancel()
        except:
            pass

        try:
            self.playermindTick.cancel()
        except:
            pass

        if reactor.running:
            reactor.runUntilCurrent()
            reactor.doIteration(0)
        if not EXITFORCED:
            try:
                d = self.perspective.perspective.callRemote('PlayerAvatar', 'logout')
                d.addCallback(self.camp_main, quit)
                d.addErrback(self.camp_main, quit)
                return d
            except:
                traceback.print_exc()
                self.camp_main(None, quit)

        else:
            self.camp_main(None, quit)
        return

    def camp_main(self, result, quit = False):
        from mud.client.gui.worldGui import ClearPlayerPerspective
        from mud.client.irc import IRCDisconnect
        try:
            IRCDisconnect()
        except:
            traceback.print_exc()

        self.running = False
        if self.rootInfo:
            try:
                from gui.petWnd import PETWND
                PETWND.charInfo = None
                from gui.tacticalGui import TACTICALGUI
                TACTICALGUI.charInfo = None
                from gui.craftingWnd import CRAFTINGWND
                CRAFTINGWND.charInfo = None
                from gui.advancePane import ADVANCEPANE
                ADVANCEPANE.cinfo = None
                from gui.vaultWnd import VAULTWND
                VAULTWND.cinfo = None
                from gui.partyWnd import PARTYWND
                PARTYWND.skillPane.charInfo = None
                PARTYWND.spellPane.charInfo = None
                PARTYWND.statsPane.charInfo = None
                PARTYWND.invPane.charInfo = None
                PARTYWND.settingsPane.currentChar = None
                PARTYWND.charInfos = None
                from gui.charMiniWnd import CHARMINIWND
                CHARMINIWND.charInfos = None
                from gui.buffWnd import BUFFWND
                BUFFWND.charInfos = None
                from gui.playerSettings import PLAYERSETTINGS
                PLAYERSETTINGS.charInfos = None
                from gui.worldGui import CHARINFOS
                CHARINFOS = None
                for cinfo in self.charInfos.itervalues():
                    for item in cinfo.ITEMS.itervalues():
                        item.broker.transport.loseConnection()

                    cinfo.ITEMS.clear()
                    for spell in cinfo.SPELLS.itervalues():
                        spell.broker.transport.loseConnection()

                    cinfo.SPELLS.clear()
                    cinfo.SPELLEFFECTS = []
                    cinfo.RAPIDMOBINFO.broker.transport.loseConnection()
                    cinfo.RAPIDMOBINFO = None
                    cinfo.broker.transport.loseConnection()

                self.charInfos.clear()
                self.clearAllianceInfo()
                from gui.npcWnd import NPCWND
                NPCWND.bankPane.set({})
                for bankItem in self.rootInfo.BANK.itervalues():
                    bankItem.broker.transport.loseConnection()

                self.rootInfo.BANK.clear()
                self.rootInfo.CHARINFOS = None
                self.rootInfo.broker.transport.loseConnection()
                self.rootInfo = None
            except:
                traceback.print_exc()

        if self.perspective and self.perspective.perspective:
            self.perspective.perspective.broker.transport.loseConnection()
            self.perspective.perspective = None
        ClearPlayerPerspective()
        self.perspective = None
        if not EXITFORCED:
            reactor.callLater(0, self.quitting, quit)
        else:
            self.quitting(quit)
        return

    def quitting(self, quit = False):
        TGEEval('disconnect();')
        TGESetGlobal('$Py::WORLDNAME', '')
        TGESetGlobal('$Py::CAMPQUIT', 0)
        TGEEval('Canvas.setContent(MainMenuGui);')
        if quit:
            TGEEval('Py::OnQuit();')
        else:
            try:
                SPVal = TGEGetGlobal('$Py::ISSINGLEPLAYER')
                if SPVal and int(SPVal):
                    from mud.worldserver.embedded import ShutdownEmbeddedWorld
                    ShutdownEmbeddedWorld()
                    TGEEval('Canvas.setContent(SinglePlayerGui);')
                    return
            except:
                pass

            DoMasterLogin()

    def campQuit(self):
        self.camp(None, True)
        return

    def doCommand(self, cmd, args):
        if cmd.upper() == 'QUIT' or cmd.upper() == 'CAMP':
            from gui.partyWnd import PARTYWND
            from gui.playerSettings import PLAYERSETTINGS
            self.running = False
            PLAYERSETTINGS.storeWindowSettings()
            PARTYWND.encounterBlock = -1
            PARTYWND.settingsPane.encounterSettingCurrent = RPG_ENCOUNTER_PVE
            PARTYWND.settingsPane.encounterSetting.SetValue(RPG_ENCOUNTER_SETTING_FORINDEX[RPG_ENCOUNTER_PVE])
            self.camp(None, cmd.upper() == 'QUIT')
            return
        else:
            try:
                if cmd.upper() == 'STOPCAST':
                    t = sysTime()
                    index = int(args[0])
                    if t - self.stopCastingTimers[index] < 12:
                        receiveGameText(RPG_MSG_GAME_DENIED, '%s cannot stop casting at this time.\\n' % self.charInfos[index].NAME)
                        return
                    self.stopCastingTimers[index] = t
            except:
                traceback.print_exc()

            d = self.perspective.callRemote('PlayerAvatar', 'doCommand', cmd, args)
            return

    def remote_setItemSlot(self, charId, itemInfo, slot):
        from gui.partyWnd import PARTYWND
        for index, cinfo in self.charInfos.iteritems():
            if cinfo.CHARID == charId:
                if itemInfo:
                    itemInfo.SLOT = slot
                    cinfo.ITEMS[slot] = itemInfo
                elif cinfo.ITEMS.has_key(slot):
                    del cinfo.ITEMS[slot]
                if index == PARTYWND.curIndex:
                    PARTYWND.invPane.setFromCharacterInfo(cinfo)
                return

    def onInvSlot(self, cinfo, slot):
        self.perspective.callRemote('PlayerAvatar', 'onInvSlot', cinfo.CHARID, slot)

    def onInvSlotAlt(self, cinfo, slot):
        clickedItem = cinfo.ITEMS.get(slot)
        if not clickedItem:
            return
        if clickedItem.CONTAINERSIZE:
            ItemContainerWnd.openContainer(clickedItem)
            return
        self.perspective.callRemote('PlayerAvatar', 'onInvSlotAlt', cinfo.CHARID, slot)

    def onBankSlot(self, slot):
        self.perspective.callRemote('PlayerAvatar', 'onBankSlot', slot)

    def onInvSlotCtrl(self, cinfo, slot):
        clickedItem = cinfo.ITEMS.get(slot)
        if not clickedItem:
            return
        if clickedItem.CONTAINERSIZE:
            ItemContainerWnd.openContainer(clickedItem)
            return
        self.perspective.callRemote('PlayerAvatar', 'onInvSlotCtrl', cinfo.CHARID, slot)

    def onSpellSlot(self, cinfo, slot):
        if cinfo.DEAD:
            return
        self.perspective.callRemote('PlayerAvatar', 'onSpellSlot', cinfo.CHARID, slot)

    def onSpellSlotSwap(self, cinfo, source, dest):
        self.perspective.callRemote('PlayerAvatar', 'onSpellSlotSwap', cinfo.CHARID, source, dest)

    def remote_setCursorItem(self, itemInfo):
        from gui.partyWnd import PARTYWND
        if itemInfo:
            itemInfo.SLOT = RPG_SLOT_CURSOR
        self.cursorItem = itemInfo
        PARTYWND.setCursorItem()

    def remote_checkIgnore(self, charName):
        from gui.playerSettings import PLAYERSETTINGS
        if charName and charName.upper() in PLAYERSETTINGS.ignored:
            return True
        return False

    def remote_receiveTextList(self, messages):
        from gui.playerSettings import PLAYERSETTINGS
        for t, textCode, text, src, stripML in messages:
            if src and src in PLAYERSETTINGS.ignored:
                continue
            if t == 0:
                self.remote_receiveGameText(textCode, text, stripML)
            elif t == 1:
                self.remote_receiveSpeechText(textCode, text)

    def remote_receiveGameText(self, textCode, text, stripML):
        text = QUOTE_REPLACER.sub('\\"', text)
        if stripML:
            text = TGECall('StripMLControlChars', text)
        receiveGameText(textCode, text)

    def remote_receiveSpeechText(self, textCode, text):
        text = QUOTE_REPLACER.sub('\\"', text)
        TomeGui.receiveSpeechText(textCode, text)

    def remote_createServer(self, zconnect):
        print 'createServer %s' % zconnect.instanceName
        if self.simMind:
            self.simMind.destroyServer()
        self.simMind = SimMind(self.perspective, zconnect.instanceName)
        TGEEval('\n            LOAD_ZONEBITMAP.setBitmap("~/data/ui/loading/SPCreateZone");\n            LoadingProgress.setValue(0);\n            LOAD_MapDescription.setText("");\n            LoadingProgressTxt.setText("... Populating Zone ... Please Wait ...");\n            canvas.setcontent(LoadingGui);\n            LOAD_MapName.setText("Traveling");\n            canvas.repaint();')
        TGEEval('CreateLocalMission("%s","%s");' % (zconnect.missionFile, zconnect.password))

    def remote_connect(self, zconnect, fantasyName = None):
        from gui.playerSettings import PLAYERSETTINGS
        PLAYERSETTINGS.updateZone(zconnect.niceName)
        if fantasyName:
            TGESetGlobal('$pref::FantasyName', fantasyName)
        TGEEval('Canvas.repaint();')
        TGESetGlobal('$Py::RPG::ShowPlayers', 1)
        TGESetGlobal('$Py::RPG::ShowNPCs', 1)
        TGESetGlobal('$Py::RPG::ShowEnemies', 1)
        TGESetGlobal('$Py::RPG::ShowPoints', 1)
        TGESetGlobal('$Py::playerZoneConnectPassword', zconnect.playerZoneConnectPassword)
        if SimMind.directConnect:
            zconnect.ip = SimMind.directConnect
        if int(TGEGetGlobal('$Py::ISSINGLEPLAYER')):
            print 'CONNECT %s' % zconnect.ip
            TGEEval('ConnectLocalMission();')
        else:
            connectstring = '%s:%i' % (zconnect.ip, zconnect.port)
            print 'CONNECT %s' % connectstring
            TGEEval('ConnectRemoteMission("%s","%s");' % (connectstring, ''))

    def remote_setRootInfo(self, rootInfo, pauseTime = None):
        if int(TGEGetGlobal('$mvAutoForward')):
            TGESetGlobal('$mvAutoForward', 2)
        hadNoRootInfo = not self.rootInfo
        if pauseTime:
            self.lastAdTime = sysTime() - pauseTime
        self.rootInfo = rootInfo
        self.charInfos = rootInfo.CHARINFOS
        from gui.partyWnd import SetFromCharacterInfos
        SetFromCharacterInfos(self.charInfos)
        MacroWnd.setFromCharacterInfos(self.charInfos)
        for x in xrange(0, 6):
            if x < len(self.charInfos):
                TGEObject('PARTYWND_CHAR%i' % x).visible = True
            else:
                TGEObject('PARTYWND_CHAR%i' % x).visible = False

        from gui.allianceWnd import ALLIANCEWND
        ALLIANCEWND.setCharInfo(self.charInfos[0])
        from gui.charMiniWnd import CHARMINIWND
        CHARMINIWND.setCharInfos(self.charInfos)
        from gui.buffWnd import BUFFWND
        BUFFWND.setCharInfos(self.charInfos)
        TGEObject('MACROWND_CHAR0').performClick()
        TGEObject('INVPANE_PAGEBUTTON0').performClick()
        if hadNoRootInfo:
            self.tick()

    def remote_setCurCharIndex(self, index):
        from gui.partyWnd import PARTYWND
        PARTYWND.setFromCharacterInfo(index)

    def remote_openPetWindow(self):
        TGEEval('canvas.pushDialog(PetWnd);')

    def charSetTarget(self, charIndex, mobId, cycle = False):
        self.perspective.callRemote('PlayerAvatar', 'doCommand', 'TARGETID', [charIndex, mobId, cycle])

    def remote_mouseSelect(self, charIndex, mobId):
        for x, cinfo in self.charInfos.iteritems():
            if x == charIndex:
                if cinfo.clientSettings['LINKTARGET']:
                    from gui.partyWnd import PARTYWND
                    cinfo.clientSettings['LINKTARGET'] = None
                    if PARTYWND.settingsPane.currentChar == cinfo:
                        PARTYWND.settingsPane.setFromCharacterInfo(cinfo, True)
                continue
            if cinfo.clientSettings['LINKMOUSETARGET']:
                self.perspective.callRemote('PlayerAvatar', 'doCommand', 'TARGETID', [x, mobId, 0])

        return

    def remote_beginCasting(self, charIndex, time):
        from gui.charMiniWnd import CHARMINIWND
        from gui.allianceWnd import ALLIANCEWND
        CHARMINIWND.beginCasting(charIndex, time)
        ALLIANCEWND.beginCasting(time)

    def remote_setLoot(self, loot, kind = None):
        LootWnd.setLoot(loot, kind)

    def expungeItem(self):
        self.perspective.callRemote('PlayerAvatar', 'expungeItem')

    def splitItem(self, newStackSize):
        self.perspective.callRemote('PlayerAvatar', 'splitItem', newStackSize)

    def remote_getInnWnd(self):
        from gui.innWnd import INNWND
        return INNWND

    def remote_setZoneOptions(self, zoptions):
        from gui.playerSettings import PLAYERSETTINGS
        PLAYERSETTINGS.storeWindowSettings()
        self.simMind = None
        TGEEval('disconnect();')
        if not len(zoptions):
            self.perspective.callRemote('PlayerAvatar', 'chooseZone', 'new')
            return
        else:
            self.perspective.callRemote('PlayerAvatar', 'chooseZone', zoptions[0].zoneInstanceName)
            return

    def remote_syncTime(self, hour, minute):
        TGEEval('TGEDayNightSyncTime(%i,%i);' % (hour, minute))

    def remote_openNPCWnd(self, title, banker = False):
        TGEObject('NPCWnd_Window').setText(title)
        from gui.npcWnd import NPCWND
        NPCWND.openWindow(self.perspective, title, banker)

    def remote_closeNPCWnd(self):
        from gui.npcWnd import NPCWND
        NPCWND.closeWindow()

    def remote_setVendorStock(self, isVendor, stock, markup):
        from gui.npcWnd import NPCWND
        NPCWND.setStock(isVendor, stock, markup)

    def remote_setInitialInteraction(self, dialogLine, choices, title = None):
        from gui.npcWnd import NPCWND
        NPCWND.setInitialInteraction(dialogLine, choices, title)

    def clearAllianceInfo(self):
        from gui.allianceWnd import ALLIANCEWND
        from gui.leaderWnd import LEADERWND
        ALLIANCEWND.clearAllianceInfo()
        LEADERWND.clearAllianceInfo()

    def remote_setAllianceInfo(self, ainfo):
        from gui.allianceWnd import ALLIANCEWND
        from gui.leaderWnd import LEADERWND
        ALLIANCEWND.setAllianceInfo(ainfo)
        LEADERWND.setAllianceInfo(ainfo)

    def remote_setAllianceInvite(self, who):
        from gui.allianceWnd import ALLIANCEWND
        ALLIANCEWND.setInvite(who)
        if who:
            TGEEval('canvas.pushDialog(AllianceWnd);')

    def remote_openTradeWindow(self, tradeInfo):
        from gui.tradeWnd import TRADEWND
        TRADEWND.open(tradeInfo)

    def remote_closeTradeWindow(self):
        from gui.tradeWnd import TRADEWND
        TRADEWND.close()

    def remote_setMuteTime(self, t):
        from irc import SetMuteTime
        SetMuteTime(t)

    def remote_setTracking(self, tracking):
        from gui.trackingWnd import TRACKINGWND
        TRACKINGWND.set(tracking)

    def remote_setTell(self, teller):
        teller = teller.replace(' ', '_')
        TGESetGlobal('$Py::LastTell', teller)

    def remote_setTgtDesc(self, infoDict):
        from gui.tgtDescWnd import TGTDESCWND
        TGTDESCWND.setInfo(infoDict)

    def remote_vocalize(self, sexcode, set, vox, which):
        sex = 'Male'
        if sexcode == 1:
            sex = 'Female'
        if which < 10:
            num = '0%i' % which
        else:
            num = str(which)
        filename = 'vocalsets/%s_LongSet_%s/%s_LS_%s_%s%s.ogg' % (sex,
         set,
         sex,
         set,
         VOCALFILENAMES[vox],
         num)
        self.remote_playSound(filename)

    def remote_playSound(self, sound):
        try:
            if type(sound) == types.IntType:
                sound = SOUNDS[sound]
            eval = 'alxPlay(alxCreateSource(AudioMessage, "%s/data/sound/%s"));' % (GAMEROOT, sound)
            TGEEval(eval)
        except:
            traceback.print_exc()

    def remote_addJournalEntry(self, journalEntryID):
        from gui.journalWnd import JOURNALWND
        con = GetMoMClientDBConnection()
        journalTopic, journalEntry, text = con.execute('SELECT topic,entry,text FROM journal_entry WHERE id = %i LIMIT 1;' % journalEntryID).fetchone()
        JOURNALWND.addEntry(journalTopic, journalEntry, text)

    def remote_setResurrectNames(self, names):
        if len(names):
            from gui.resurrectionGui import RESURRECTIONWND
            RESURRECTIONWND.set(names)
            TGEEval('Canvas.pushDialog("ResurrectionGui");')
        else:
            TGEEval('Canvas.popDialog("ResurrectionGui");')

    def resurrect(self, cname):
        self.perspective.callRemote('PlayerAvatar', 'onResurrect', cname)

    def remote_resurrectionRequest(self, resurrector, xp):
        TGEEval('MessageBoxYesNo("Resurrection", "Would you like to be resurrected by %s with %i%% experience recovery?","Py::OnResurrectAccept();");' % (resurrector, int(xp * 100.0)))

    def acceptResurrect(self):
        self.perspective.callRemote('PlayerAvatar', 'onAcceptResurrect')

    def remote_partyWipe(self, xpLoss = -1):
        from gui.partyWnd import PARTYWND
        self.remote_playSound('sfx/HauntingVoices1.ogg')
        if xpLoss == 0:
            self.remote_receiveGameText(RPG_MSG_GAME_PARTYDEATH, 'Your party has been wiped out!!!\\n', False)
        elif xpLoss == 1:
            self.remote_receiveGameText(RPG_MSG_GAME_PARTYDEATH, 'Your party has been wiped out and permanently lost experience!!!\\n', False)
        PARTYWND.encounterBlock = -1
        if int(PARTYWND.settingsPane.encounterPVEDie.GetValue()):
            PARTYWND.settingsPane.encounterSettingCurrent = RPG_ENCOUNTER_PVE
            PARTYWND.settingsPane.encounterSetting.SetValue(RPG_ENCOUNTER_SETTING_FORINDEX[RPG_ENCOUNTER_PVE])
            self.perspective.callRemote('PlayerAvatar', 'setEncounterSetting', RPG_ENCOUNTER_PVE, True)

    def remote_checkEncounterSetting(self, zoning = False, newIndex = RPG_ENCOUNTER_PVE, force = False):
        from gui.partyWnd import PARTYWND
        settingsPane = PARTYWND.settingsPane
        if not force and (PARTYWND.encounterBlock > 0 or PARTYWND.encounterTimer):
            self.perspective.callRemote('PlayerAvatar', 'setEncounterSetting', settingsPane.encounterSettingCurrent, True)
            if zoning:
                PARTYWND.encounterBlock = 0
        elif zoning:
            if int(settingsPane.encounterPVEZone.GetValue()):
                settingsPane.encounterSettingCurrent = RPG_ENCOUNTER_PVE
                settingsPane.encounterSetting.SetValue(RPG_ENCOUNTER_SETTING_FORINDEX[RPG_ENCOUNTER_PVE])
            else:
                self.perspective.callRemote('PlayerAvatar', 'setEncounterSetting', settingsPane.encounterSettingCurrent, True)
        else:
            settingsPane.encounterSettingCurrent = newIndex
            settingsPane.encounterSetting.SetValue(RPG_ENCOUNTER_SETTING_FORINDEX[newIndex])
            if force:
                PARTYWND.encounterSettingDisturbed()
            else:
                settingsPane.encounterSettingStatic.setVisible(False)
                settingsPane.encounterSettingTimer.setVisible(False)
                settingsPane.encounterSetting.setVisible(True)

    def remote_disturbEncounterSetting(self):
        from gui.partyWnd import PARTYWND
        PARTYWND.encounterSettingDisturbed()

    def chooseAdvancement(self, cname, advancement):
        self.perspective.callRemote('PlayerAvatar', 'chooseAdvancement', cname, advancement)

    def remote_setFriendsInfo(self, finfo):
        FriendsWnd.setFriendsInfo(finfo)


def OnClientQuit():
    global CLIENTEXITED
    if not CLIENTEXITED:
        OnReallyQuit(True)


def OnReallyQuit(forced = False):
    global PLAYERMIND
    global EXITFORCED
    EXITFORCED = forced
    if PLAYERMIND:
        PLAYERMIND.doCommand('QUIT', [0])
        PLAYERMIND = None
    else:
        OnQuit()
    return


def OnGameOptionsQuit():
    TGEEval('MessageBoxYesNo( "Quit?", "Do you really want to venture forth to reality?", "Py::OnReallyQuit();", "");')


def OnReallyCamp():
    global PLAYERMIND
    if PLAYERMIND:
        PLAYERMIND.doCommand('CAMP', [0])
        PLAYERMIND = None
    return


def OnGameOptionsCamp():
    TGEEval('MessageBoxYesNo("Camp?", "Do you really want to camp and return to the Main Menu?","Py::OnReallyCamp();");')


SUB_MALE, SUB_FEMALE, SUB_OTHER = range(3)
SUBSTITUTION_SUBJECTIVE = ('he', 'she', 'it')
SUBSTITUTION_OBJECTIVE = ('him', 'her', 'it')
SUBSTITUTION_POSSESSIVE = ('his', 'her', 'its')

def substituteContext(characterInfo, str):
    mobInfo = characterInfo.RAPIDMOBINFO
    words = str.split()
    for index in xrange(len(words)):
        words[index] = words[index].replace('\\', '\\\\')
        if mobInfo.TGTID:
            words[index] = words[index].replace('%t', mobInfo.TGT)
            words[index] = words[index].replace('%r', mobInfo.TGTRACE)
            words[index] = words[index].replace('%g', mobInfo.TGTSEX)
            if RPG_SEXES[SUB_MALE] == mobInfo.TGTSEX:
                tgtSexIndex = SUB_MALE
            elif RPG_SEXES[SUB_FEMALE] == mobInfo.TGTSEX:
                tgtSexIndex = SUB_FEMALE
            else:
                tgtSexIndex = SUB_OTHER
            words[index] = words[index].replace('%s', SUBSTITUTION_SUBJECTIVE[tgtSexIndex])
            words[index] = words[index].replace('%o', SUBSTITUTION_OBJECTIVE[tgtSexIndex])
            words[index] = words[index].replace('%p', SUBSTITUTION_POSSESSIVE[tgtSexIndex])

    return ' '.join(words)


MARKUP_PARSER = re.compile('(<([^<>]*)>)')

def formatMLString(formatString):
    if not formatString:
        return ''
    formatString = TGECall('StripMLControlChars', formatString)
    for match in MARKUP_PARSER.findall(formatString):
        link = encyclopediaGetLink(match[1])
        if link:
            formatString = formatString.replace(match[0], link)

    return formatString


def formatChatString(sendString):
    if len(sendString) < 7:
        return sendString
    else:
        if sendString.isupper():
            sendString = sendString.lower()
        charList = list(sendString)
        charNum = len(set(charList))
        if charNum < 3:
            TGECall('MessageBoxOK', 'Message ignored', "The chat message you tried to send was filtered out, it didn't seem to make much sense.")
            return None
        prevChar = ''
        repeatCount = 0
        nonAlphanumCount = 0
        for i, char in enumerate(charList):
            if char == ' ' or char.isalpha() or char.isdigit():
                nonAlphanumCount = 0
            else:
                nonAlphanumCount += 1
                if nonAlphanumCount > 5:
                    charList[i] = ''
                    continue
            if char == prevChar:
                repeatCount += 1
                if repeatCount > 3:
                    charList[i] = ''
            else:
                repeatCount = 0
            prevChar = char

        sendString = ''.join(charList)
        sendString.replace(' u ', 'you')
        sendString.replace(' r ', 'are')
        return sendString


def PyDoCommand(myargs, insertCurChar = True, indexHack = None):
    global LASTCHANNEL
    try:
        from gui.partyWnd import PARTYWND
        from mud.client.irc import SendIRCMsg, IRCConnect, IRCTell, IRCEmote, SetAwayMessage
        text = myargs[1]
        if PLAYERMIND:
            if insertCurChar:
                index = PARTYWND.curIndex
            else:
                index = indexHack
            if index != None:
                text = substituteContext(PLAYERMIND.charInfos[index], text)
        if DoClientCommand((0, text), indexHack):
            return
        if text.startswith('/imm'):
            text = text.split(' ')
            cmd = text[1].upper()
            args = text[2:]
            PLAYERMIND.perspective.callRemote('ImmortalAvatar', 'command', cmd, args)
            return
        if text.startswith('/gm'):
            text = text.split(' ')
            cmd = text[1].upper()
            args = text[2:]
            PLAYERMIND.perspective.callRemote('GuardianAvatar', 'command', cmd, args)
            return
        if not text.startswith('/'):
            cmd = LASTCHANNEL
            args = [text]
        else:
            text = text.strip().split(' ')
            cmd = text[0][1:].upper()
            if not cmd:
                return
            args = text[1:]
        if cmd in CHATCHANNELS:
            if cmd not in ('E', 'EMOTE', 'ME'):
                LASTCHANNEL = cmd
            args = formatChatString(' '.join(args))
            if cmd not in IRCCHANNELS:
                args = formatMLString(args).split()
                if not args:
                    return
                if cmd in ('GC', 'GMCHAT'):
                    PLAYERMIND.perspective.callRemote('GuardianAvatar', 'chat', args)
                    return
                if insertCurChar:
                    args.insert(0, PARTYWND.curIndex)
                elif indexHack != None:
                    args.insert(0, indexHack)
                PLAYERMIND.doCommand(cmd, args)
                return
            elif not args:
                return
            else:
                SendIRCMsg(cmd, args)
                return
        if '/' == cmd[0]:
            receiveGameText(RPG_MSG_GAME_YELLOW, 'Memo: %s\\n' % formatMLString(' '.join(text)[2:].replace('\\', '\\\\')))
            return
        if cmd == 'CHANNEL':
            if len(args) != 2:
                receiveGameText(RPG_MSG_GAME_DENIED, 'Usage: /channel <channel> <on|off>\\n')
                return
            if args[1].upper() == 'ON':
                on = True
            else:
                on = False
            channelUpper = args[0].upper()
            chatChannel = TOGGLEABLECHANNELS.get(channelUpper, 0)
            if chatChannel <= 0:
                receiveGameText(RPG_MSG_GAME_DENIED, "Channel %s can't be toggled.\\n" % args[0])
                return
            from gui.playerSettings import PLAYERSETTINGS
            PLAYERSETTINGS.setChannel(chatChannel, on)
            if channelUpper in ('M', 'MOM'):
                TomeGui.onGlobalChannelToggle(on)
                return
            if channelUpper in ('O', 'OFFTOPIC'):
                TomeGui.onOffTopicChannelToggle(on)
                return
            if channelUpper in ('H', 'HELP'):
                TomeGui.onHelpChannelToggle(on)
                return
        if cmd == 'MCONNECT' and PLAYERMIND.ircNick:
            IRCConnect(PLAYERMIND.ircNick)
            return
        if cmd == 'T' or cmd == 'TELL':
            if len(args) > 1:
                IRCTell(args[0], ' '.join(args[1:]))
            return
        if cmd == 'GE' or cmd == 'GEMOTE':
            args = formatChatString(' '.join(args))
            if args:
                IRCEmote(LASTCHANNEL, args)
            return
        if cmd in ('SORT', 'EMPTY', 'STACK'):
            timestamp = sysTime()
            timeDelta = int(PLAYERMIND.inventoryCmdAvailableTime - timestamp)
            if 0 < timeDelta:
                receiveGameText(RPG_MSG_GAME_DENIED, 'You cannot use this command for another %u seconds.\\n' % timeDelta)
                return
            PLAYERMIND.inventoryCmdAvailableTime = timestamp + 15
        elif 'RESIZE' == cmd:
            timestamp = sysTime()
            timeDelta = int(PLAYERMIND.resizeCmdAvailableTime - timestamp)
            if 0 < timeDelta:
                receiveGameText(RPG_MSG_GAME_DENIED, 'You cannot use the resize command for another %u seconds.\\n' % timeDelta)
                return
            PLAYERMIND.resizeCmdAvailableTime = timestamp + 120
        if insertCurChar:
            args.insert(0, PARTYWND.curIndex)
        elif indexHack != None:
            args.insert(0, indexHack)
        PLAYERMIND.doCommand(cmd, args)
    except:
        traceback.print_exc()

    return


def PyMissionDownloadComplete():
    from gui.playerSettings import PLAYERSETTINGS
    from gui.partyWnd import PyOnSendXPSliders
    PLAYERSETTINGS.loadWindowSettings()
    TGEEval('\n    FadeWnd.fadeinTime = 2000;\n    Canvas.pushDialog( FadeWnd );\n    ')
    PyOnSendXPSliders([0,
     1,
     2,
     3,
     4,
     5])


def PyClearCharTarget():
    from gui.partyWnd import PARTYWND
    try:
        curIndex = PARTYWND.curIndex
        PLAYERMIND.charSetTarget(curIndex, 0)
    except:
        pass


def OnCharEffect(args):
    cindex, slot = int(args[1]), int(args[2])
    cinfo = PLAYERMIND.charInfos[cindex]
    sinfo = cinfo.SPELLEFFECTS[slot]
    PLAYERMIND.perspective.callRemote('PlayerAvatar', 'cancelProcess', cinfo.CHARID, sinfo.PID)


def OnCharEffectShift(args):
    characterIndex, slot = int(args[1]), int(args[2])
    effectName = PLAYERMIND.charInfos[characterIndex].SPELLEFFECTS[slot].NAME.split()
    if effectName[-1] in RPG_ROMAN:
        effectName.pop()
    encyclopediaSearch(' '.join(effectName))


def OnCharEffectShiftRight(args):
    characterIndex, slot = int(args[1]), int(args[2])
    effectName = PLAYERMIND.charInfos[characterIndex].SPELLEFFECTS[slot].NAME.split()
    if effectName[-1] in RPG_ROMAN:
        effectName.pop()
    OnEncyclopediaOnURL((None, 'chatlink%s' % ' '.join(effectName)))
    return


def OnQuit():
    global CLIENTEXITED
    try:
        SPVal = TGEGetGlobal('$Py::ISSINGLEPLAYER')
        if SPVal and int(SPVal):
            from mud.worldserver.embedded import ShutdownEmbeddedWorld
            ShutdownEmbeddedWorld()
    except:
        traceback.print_exc()

    TGEEval('quit();')
    CLIENTEXITED = True


def OnResurrectAccept():
    PLAYERMIND.acceptResurrect()


def OnCampQuit():
    global PLAYERMIND
    if not PLAYERMIND:
        return
    else:
        PLAYERMIND.campQuit()
        PLAYERMIND = None
        return


def OnCamp():
    global PLAYERMIND
    if not PLAYERMIND:
        return
    else:
        PLAYERMIND.camp(None, False)
        PLAYERMIND = None
        return


TGEExport(PyMissionDownloadComplete, 'Py', 'MissionDownloadComplete', 'desc', 1, 1)
TGEExport(PyDoCommand, 'Py', 'DoCommand', 'desc', 2, 2)
TGEExport(OnGameOptionsCamp, 'Py', 'OnGameOptionsCamp', 'desc', 1, 1)
TGEExport(OnGameOptionsQuit, 'Py', 'OnGameOptionsQuit', 'desc', 1, 1)
TGEExport(OnCharEffect, 'Py', 'OnCharEffect', 'desc', 3, 3)
TGEExport(OnCharEffectShift, 'Py', 'OnCharEffectShift', 'desc', 3, 3)
TGEExport(OnCharEffectShiftRight, 'Py', 'OnCharEffectShiftRight', 'desc', 3, 3)
TGEExport(OnReallyCamp, 'Py', 'OnReallyCamp', 'desc', 1, 1)
TGEExport(OnReallyQuit, 'Py', 'OnReallyQuit', 'desc', 1, 1)
TGEExport(OnQuit, 'Py', 'OnQuit', 'desc', 1, 1)
TGEExport(OnCampQuit, 'Py', 'OnCampQuit', 'desc', 1, 1)
TGEExport(OnCamp, 'Py', 'OnCamp', 'desc', 1, 1)
TGEExport(OnResurrectAccept, 'Py', 'OnResurrectAccept', 'desc', 1, 1)
TGEExport(PyClearCharTarget, 'Py', 'ClearCharTarget', 'desc', 1, 1)