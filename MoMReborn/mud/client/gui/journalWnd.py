# Embedded file name: mud\client\gui\journalWnd.pyo
from tgenative import *
from mud.tgepython.console import TGEExport
from mud.world.defines import *
from mud.gamesettings import *
from math import floor
from tomeGui import TomeGui

def CreateDefaultJournal(realm):
    journal = {}
    defaultTopic = journal['Welcome to Minions of Mirth'] = [{}, False]
    defaultTopic = defaultTopic[0]
    defaultTopic['A little help please!!!!'] = ["<color:BBBBFF>Click on the 'Help' button on your Tome window.", False]
    if realm == RPG_REALM_LIGHT:
        defaultTopic['Getting Started'] = ["<color:BBBBFF>To get started, type the 'I' key to view your inventory. Each character has a starting item in their inventory.  To begin your character quest, click the 'I' button on your tome to bring up your information window.  Move your mouse cursor over the first item in your inventory to find out who your trainer in Trinst is. Take this road into town and locate your trainer in one of the 4 guild buildings.  To toggle autorun type 'V' and to toggle mouse look type 'X'.\\n", False]
        defaultTopic['How do I find my trainer?'] = ["<color:BBBBFF>Type 'M' to open your map.  Each player has a tracking range based upon their skill level.  Once your trainer is within range, you will see their name on your map.  All trainers can be found in one of the 4 guild buildings located in the city walls.  Make sure to complete the starting quest for each player in your party!\\n", False]
        defaultTopic['Where are the guild buildings?'] = ["<color:BBBBFF>The mage's guild is in the northwest corner of town.  The rogue's guild is in the southwest area of town in the residential district.  The combatant's guild and the priest's guild are in the northeast corner near the entrance into the Trinst Sewers.\\n", False]
        defaultTopic['Where can I get a quest?'] = ['<color:BBBBFF>Locate Chancellor Tolip, he will have something for you to do.\\n', False]
        defaultTopic['Where can I buy supplies?'] = ['<color:BBBBFF>There are several vendors inside of Trinst that sell armor, weapons, and various items.\\n', False]
    elif realm == RPG_REALM_DARKNESS:
        defaultTopic['Getting Started'] = ["<color:BBBBFF>To get started, type the 'I' key to view your inventory. Each character has a starting item in their inventory.  To begin your character quest, click the 'I' button on your tome to bring up your information window.  Move your mouse cursor over the first item in your inventory to find out who your trainer in Kauldur is. Locate your trainer in one of the 4 guild buildings, Lelo Snakedancer can give you a quick lift if you'd like.  To toggle autorun type 'V' and to toggle mouse look type 'X'.\\n", False]
        defaultTopic['How do I find my trainer?'] = ["<color:BBBBFF>Type 'M' to open your map.  Each player has a tracking range based upon their skill level.  Once your trainer is within range, you will see their name on your map.  All trainers can be found in one of the 4 guild buildings around town.  Make sure to complete the starting quest for each player in your party!\\n", False]
        defaultTopic['Where are the guild buildings?'] = ["<color:BBBBFF>The mage's guild is to the north of town across a narrow ridge.  The rogue's guild is to the east, slightly outside of town.  The combatant's guild can be found in the middle of Kauldur, behind the inn.  Lastly, the priest's guild is to the west, just across the bridge near the Bind Stones.  For easier navigation, Lelo Snakedancer can directly teleport you to any desired guild in Kauldur.\\n", False]
        defaultTopic['Where can I get a quest?'] = ['<color:BBBBFF>Locate Shon Grimclaw, he will have something for you to do.\\n', False]
        defaultTopic['Where can I buy supplies?'] = ['<color:BBBBFF>There are several vendors inside of Kauldur that sell armor, weapons, and various items.\\n', False]
    else:
        defaultTopic['Getting Started'] = ["<color:BBBBFF>Unlike characters of the other two realms, monsters don't get any starting quests or equipment. As it is, you will quickly get hungry so first thing to do is to hunt. Except for undead and constructs, all beings can provide you with 'Flesh and Blood'.\\n", False]
        defaultTopic['How do I get to Gurak Ord (Monster Town)?'] = ["<color:BBBBFF>The monster village of Gurak Ord is in Hazeroth Keep. After zoning in, follow the path that leads to the mouth of the bridge. Turn left before the bridge and follow the path up and over the hill. Turn right to go into the village, go straight to go to Mephite's Lair.\\n", False]
        defaultTopic['Where can I get a quest?'] = ['<color:BBBBFF>Locate Warmaster Giak in Gurak Ord, he will have something for you to do.', False]
        defaultTopic['Where can I buy supplies?'] = ['<color:BBBBFF>There are several vendors in Gurak Ord that sell armor, weapons, and various items.\\n', False]
    return journal


JOURNALWND = None

class JournalWnd():

    def __init__(self):
        self.journalScroll = TGEObject('JOURNAL_SCROLL')
        self.journalText = TGEObject('JOURNAL_TEXT')
        self.topicScroll = TGEObject('JOURNAL_TOPICSCROLL')
        self.topicTextList = TGEObject('JOURNAL_TOPICTEXTLIST')
        self.entryScroll = TGEObject('JOURNAL_ENTRYSCROLL')
        self.entryTextList = TGEObject('JOURNAL_ENTRYTEXTLIST')
        self.hideTopic = TGEObject('JOURNAL_HIDETOPIC')
        self.hideEntry = TGEObject('JOURNAL_HIDEENTRY')
        self.showHidden = TGEObject('JOURNAL_SHOWHIDDEN')
        self.showHidden.setValue(0)
        self.newEntryTopic = TGEObject('JournalNewEntry_Topic')
        self.newEntryEntry = TGEObject('JournalNewEntry_Entry')
        self.newEntryText = TGEObject('JournalNewEntry_Text')
        self.journal = None
        return

    def setJournal(self, journal, force = False):
        if force or self.journal != journal:
            self.journal = journal
            eTL = self.entryTextList
            eTL.setVisible(False)
            eTL.clear()
            eTL.setVisible(True)
            tTL = self.topicTextList
            tTL.setVisible(False)
            tTL.clear()
            topicIndex = 0
            for topic, topicData in sorted(journal.iteritems()):
                if int(self.showHidden.getValue()) or not topicData[1]:
                    tTL.addRow(topicIndex, topic)
                    topicIndex += 1

            topic = tTL.getRowText(0)
            self.setSelection(topic)
            tTL.setActive(True)
            tTL.setVisible(True)
            if topicIndex == 0:
                TGEEval('JOURNAL_TEXT.setText("");')
                eTL.clear()

    def setSelection(self, topic, entry = None):
        tTL = self.topicTextList
        eTL = self.entryTextList
        if topic:
            for x in xrange(0, int(tTL.rowCount())):
                if tTL.getRowText(x) == topic:
                    tTL.setSelectedRow(x)
                    tTL.scrollVisible(x)
                    if self.journal[topic][1]:
                        self.hideTopic.setText('Show Topic')
                    else:
                        self.hideTopic.setText('Hide Topic')
                    if entry:
                        for x in xrange(0, int(eTL.rowCount())):
                            if eTL.getRowText(x) == entry:
                                eTL.setSelectedRow(x)
                                eTL.scrollVisible(x)
                                if self.journal[topic][0][entry][1]:
                                    self.hideEntry.setText('Show Entry')
                                else:
                                    self.hideEntry.setText('Hide Entry')
                                break

                    break

    def addEntry(self, topic, entry, text, custom = False):
        from npcWnd import NPCWND
        from playerSettings import PLAYERSETTINGS
        tTL = self.topicTextList
        sr = int(tTL.getSelectedId())
        ptopic = tTL.getRowTextById(sr)
        eTL = self.entryTextList
        sr = int(eTL.getSelectedId())
        pentry = eTL.getRowTextById(sr)
        if NPCWND.title and not custom:
            text = '<color:FFFFFF>%s: <color:BBBBFF>%s' % (NPCWND.title, text)
        else:
            text = '<color:BBBBFF>%s' % text
        needsUpdate, journal = PLAYERSETTINGS.addJournalEntry(topic, entry, text)
        if needsUpdate:
            self.setJournal(journal, True)
            TomeGui.instance.receiveGameText(RPG_MSG_GAME_GAINED, 'Your journal\\\'s \\"%s\\" topic has been updated with a \\"%s\\" entry!\\n' % (topic, entry))
            eval = 'alxPlay(alxCreateSource(AudioMessage, "%s/data/sound/sfx/Pencil_WriteOnPaper2.ogg"));' % GAMEROOT
            TGEEval(eval)
            self.setSelection(ptopic, pentry)

    def OnJournalTopic(self):
        tTL = self.topicTextList
        sr = int(tTL.getSelectedId())
        topic = tTL.getRowTextById(sr)
        if self.journal[topic][1]:
            self.hideTopic.setText('Show Topic')
        else:
            self.hideTopic.setText('Hide Topic')
        eTL = self.entryTextList
        eTL.setVisible(False)
        eTL.clear()
        entryIndex = 0
        for entry, entryData in sorted(self.journal[topic][0].iteritems()):
            if int(self.showHidden.getValue()) or not entryData[1]:
                eTL.addRow(entryIndex, entry)
                entryIndex += 1

        eTL.setSelectedRow(0)
        eTL.scrollVisible(0)
        eTL.setActive(True)
        eTL.setVisible(True)
        entry = eTL.getRowTextById(0)
        if self.journal[topic][0][entry][1]:
            self.hideEntry.setText('Show Entry')
        else:
            self.hideEntry.setText('Hide Entry')
        if entryIndex == 0:
            TGEEval('JOURNAL_TEXT.setText("");')
            eTL.clear()

    def OnJournalEntry(self):
        tTL = self.topicTextList
        sr = int(tTL.getSelectedId())
        topic = tTL.getRowTextById(sr)
        eTL = self.entryTextList
        sr = int(eTL.getSelectedId())
        entry = eTL.getRowTextById(sr)
        if self.journal[topic][0][entry][1]:
            self.hideEntry.setText('Show Entry')
        else:
            self.hideEntry.setText('Hide Entry')
        try:
            fontsize = int(floor(float(TGEGetGlobal('$pref::Game::ChatFontSize'))))
            fontsize += 3
        except:
            fontsize = 13

        if fontsize < 13:
            fontsize = 13
        if fontsize > 23:
            fontsize = 23
        if not self.journal.get(topic) or not self.journal[topic][0].get(entry):
            eval = 'JOURNAL_TEXT.setText("");'
        else:
            eval = 'JOURNAL_TEXT.setText("<font:Arial:%i><shadowcolor:000000><shadow:1:1>%s");' % (fontsize, self.journal[topic][0][entry][0])
            eval = eval.replace('\n', '')
        TGEEval(eval)

    def OnJournalHideTopic(self):
        from playerSettings import PLAYERSETTINGS
        tTL = self.topicTextList
        sr = int(tTL.getSelectedId())
        topic = tTL.getRowTextById(sr)
        needsUpdate, journal = PLAYERSETTINGS.hideJournalTopic(topic, not self.journal[topic][1])
        if needsUpdate:
            self.setJournal(journal, True)
            self.setSelection(topic)

    def OnJournalHideEntry(self):
        from playerSettings import PLAYERSETTINGS
        tTL = self.topicTextList
        sr = int(tTL.getSelectedId())
        topic = tTL.getRowTextById(sr)
        eTL = self.entryTextList
        sr = int(eTL.getSelectedId())
        entry = eTL.getRowTextById(sr)
        needsUpdate, journal = PLAYERSETTINGS.hideJournalEntry(topic, entry, not self.journal[topic][0][entry][1])
        if needsUpdate:
            self.setJournal(journal, True)
            self.setSelection(topic, entry)

    def OnJournalReallyClearTopic(self):
        from playerSettings import PLAYERSETTINGS
        tTL = self.topicTextList
        sr = int(tTL.getSelectedId())
        topic = tTL.getRowTextById(sr)
        needsUpdate, journal = PLAYERSETTINGS.clearJournalTopic(topic)
        if needsUpdate:
            self.setJournal(journal, True)

    def OnJournalReallyClearEntry(self):
        from playerSettings import PLAYERSETTINGS
        tTL = self.topicTextList
        sr = int(tTL.getSelectedId())
        topic = tTL.getRowTextById(sr)
        eTL = self.entryTextList
        sr = int(eTL.getSelectedId())
        entry = eTL.getRowTextById(sr)
        needsUpdate, journal = PLAYERSETTINGS.clearJournalEntry(topic, entry)
        if needsUpdate:
            self.setJournal(journal, True)
            self.setSelection(topic)

    def OnJournalShowHidden(self):
        tTL = self.topicTextList
        sr = int(tTL.getSelectedId())
        topic = tTL.getRowTextById(sr)
        eTL = self.entryTextList
        sr = int(eTL.getSelectedId())
        entry = eTL.getRowTextById(sr)
        self.setJournal(self.journal, True)
        self.setSelection(topic, entry)

    def OnJournalApplyEntry(self):
        topic = self.newEntryTopic.getValue()
        entry = self.newEntryEntry.getValue()
        text = self.newEntryText.getValue()
        text = text.replace('\\r', '\n')
        text = text.replace('\r', '\n')
        text = text.replace('\\n', '\n')
        text = text.replace('\n', '\\n')
        self.addEntry(topic, entry, text, True)
        self.setSelection(topic, entry)

    def OnJournalEditEntry(self):
        tTL = self.topicTextList
        sr = int(tTL.getSelectedId())
        topic = tTL.getRowTextById(sr)
        eTL = self.entryTextList
        sr = int(eTL.getSelectedId())
        entry = eTL.getRowTextById(sr)
        self.newEntryTopic.setText(topic)
        self.newEntryEntry.setText(entry)
        self.newEntryText.setText(self.journal[topic][0][entry][0].replace('\\n', '\n'))

    def OnJournalClearTopic(self):
        tTL = self.topicTextList
        sr = int(tTL.getSelectedId())
        topic = tTL.getRowTextById(sr)
        TGEEval('MessageBoxYesNo("Delete Journal Topic?", "Do you really want to completely delete topic %s?","Py::OnJournalReallyClearTopic();");' % topic)

    def OnJournalClearEntry(self):
        eTL = self.entryTextList
        sr = int(eTL.getSelectedId())
        entry = eTL.getRowTextById(sr)
        TGEEval('MessageBoxYesNo("Delete Journal Entry?", "Do you really want to completely delete entry %s?","Py::OnJournalReallyClearEntry();");' % entry)


def PyExec():
    global JOURNALWND
    JOURNALWND = JournalWnd()
    TGEExport(JOURNALWND.OnJournalTopic, 'Py', 'OnJournalTopic', 'desc', 1, 1)
    TGEExport(JOURNALWND.OnJournalEntry, 'Py', 'OnJournalEntry', 'desc', 1, 1)
    TGEExport(JOURNALWND.OnJournalHideTopic, 'Py', 'OnJournalHideTopic', 'desc', 1, 1)
    TGEExport(JOURNALWND.OnJournalHideEntry, 'Py', 'OnJournalHideEntry', 'desc', 1, 1)
    TGEExport(JOURNALWND.OnJournalReallyClearTopic, 'Py', 'OnJournalReallyClearTopic', 'desc', 1, 1)
    TGEExport(JOURNALWND.OnJournalReallyClearEntry, 'Py', 'OnJournalReallyClearEntry', 'desc', 1, 1)
    TGEExport(JOURNALWND.OnJournalClearTopic, 'Py', 'OnJournalClearTopic', 'desc', 1, 1)
    TGEExport(JOURNALWND.OnJournalClearEntry, 'Py', 'OnJournalClearEntry', 'desc', 1, 1)
    TGEExport(JOURNALWND.OnJournalShowHidden, 'Py', 'OnJournalShowHidden', 'desc', 1, 1)
    TGEExport(JOURNALWND.OnJournalApplyEntry, 'Py', 'OnJournalApplyEntry', 'desc', 1, 1)
    TGEExport(JOURNALWND.OnJournalEditEntry, 'Py', 'OnJournalEditEntry', 'desc', 1, 1)