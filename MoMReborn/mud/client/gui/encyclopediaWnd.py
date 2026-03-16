# Embedded file name: mud\client\gui\encyclopediaWnd.pyo
from tgenative import *
from mud.tgepython.console import TGEExport
from mud.gamesettings import *
from mud.worlddocs.utils import GetTWikiName
from tomeGui import TomeGui
TomeGui = TomeGui.instance
import traceback
import cPickle, zlib
import re
PURGE_PARSER = re.compile('(<a +[\\s\\S]*?</a>+\\s+)|(%META:TOPICINFO+[\\s\\S]*?%+\\s+)|(\\*Quick Links:+.*\\s+)|(#[a-zA-Z]*\\s+)')
LINK_PARSER = re.compile('\\[\\[(.*?)\\]\\[(.*?)\\]\\]')
HEADER1_PARSER = re.compile('(---\\+)+(.*)')
HEADER2_PARSER = re.compile('(---\\+\\+)+(.*)')
HEADER3_PARSER = re.compile('(---\\+\\+\\+)+(.*)')
HEADER4_PARSER = re.compile('(---\\+\\+\\+\\+)+(.*)')
HEADER5_PARSER = re.compile('(---\\+\\+\\+\\+\\+)+(.*)')
BOLD_PARSER = re.compile('\\*+(.*?)\\*+')
ENCYC = {}
HEADER = '<color:2DCBC9><linkcolor:AAAA00><shadowcolor:000000><shadow:1:1><just:center><lmargin%%:2><rmargin%%:98><font:Arial Bold:20>Minions of Mirth Encyclopedia\n<font:Arial:14><just:right><a:chatlink%s>Add to Chat</a>\n<just:left>'
HOME = '\n<a:ZoneIndex>Zones</a>\n<a:SpawnIndex>Spawns (NPCs)</a>\n<a:SpawnIndexByLevel>Spawns by Level</a>\n<a:FactionIndex>Factions</a>\n<a:ItemIndex>Items</a>\n<a:ItemSetIndex>Item Sets</a>\n<a:QuestIndex>Quests</a>\n<a:SpellIndex>Spells</a>\n<a:SkillIndex>Skills</a>\n<a:ClassIndex>Classes</a>\n<a:RecipeIndex>Recipes</a><br>\n<a:EnchantingDisenchantingIndex>Enchanting / Disenchanting</a><br>\n<a:HistoryOfMirth>History of Mirth</a>\n'
PAGECACHE = {}
ENCWND = None

class EncWindow:

    def __init__(self):
        self.encText = TGEObject('ENCYC_TEXT')
        self.encScroll = TGEObject('ENCYC_SCROLL')
        self.history = []
        self.positions = {}
        self.curIndex = -1

    def setPage(self, mypage, append = True):
        try:
            page = ENCYC[mypage]
        except:
            return False

        try:
            text = PAGECACHE[mypage]
        except KeyError:
            text = ''

        pos = self.encScroll.childRelPos.split(' ')
        self.positions[self.curIndex] = (pos[0], pos[1])
        if append:
            if self.curIndex >= 0:
                self.history = self.history[:self.curIndex + 1]
                self.history.append(mypage)
                self.curIndex = len(self.history) - 1
            else:
                self.history.append(mypage)
                self.curIndex += 1
        if not text:
            text = HEADER % mypage + page
            text = PURGE_PARSER.sub('', text)
            text = BOLD_PARSER.sub('<font:Arial Bold:14>\\1<font:Arial:14>', text)
            text = HEADER5_PARSER.sub('<font:Arial Bold:15><color:2DCBC9><just:center>\\2<font:Arial:14><just:left><color:D5E70A>', text)
            text = HEADER4_PARSER.sub('<font:Arial Bold:16><color:2DCBC9><just:center>\\2<font:Arial:14><just:left><color:D5E70A>', text)
            text = HEADER3_PARSER.sub('<font:Arial Bold:17><color:2DCBC9><just:center>\\2<font:Arial:14><just:left><color:D5E70A>', text)
            text = HEADER2_PARSER.sub('<font:Arial Bold:18><color:2DCBC9><just:center>\\2<font:Arial:14><just:left><color:D5E70A>', text)
            text = HEADER1_PARSER.sub('<font:Arial Bold:20><color:2DCBC9><just:center>\\2<font:Arial:14><just:left><color:D5E70A>', text)
            text = text.replace('%GREEN%', '<color:00FF00>')
            text = text.replace('%BLUE%', '<color:3030FF>')
            text = text.replace('%RED%', '<color:FF0000>')
            text = text.replace('%YELLOW%', '<color:FFC000>')
            text = text.replace('%ENDCOLOR%', '<color:D5E70A>')
            text = text.replace('\r', '\\r')
            text = text.replace('\n', '\\n')
            text = text.replace('\x07', '\\a')
            text = text.replace('"', '\\"')
            text = LINK_PARSER.sub('<a:\\1>\\2</a>', text)
        TGEEval('ENCYC_TEXT.setText("");')
        x = 0
        while x < len(text):
            add = 1024
            t = text[x:x + add]
            if t[len(t) - 1] == '\\':
                add += 1
                t = text[x:x + add]
            TGEEval('ENCYC_TEXT.addText("%s",false);' % t)
            x += add

        PAGECACHE[mypage] = text
        TGEEval('ENCYC_TEXT.addText("\\n",true);')
        return True

    def home(self):
        self.curIndex = -1
        self.history = []
        self.setPage('Home')

    def back(self):
        if self.curIndex < 1:
            return
        pos = self.encScroll.childRelPos.split(' ')
        self.positions[self.curIndex] = (pos[0], pos[1])
        self.setPage(self.history[self.curIndex - 1], False)
        self.curIndex -= 1
        pos = self.positions[self.curIndex]
        self.encScroll.scrollRectVisible(pos[0], pos[1], 1, 444)

    def forward(self):
        if self.curIndex >= len(self.history) - 1 or not len(self.history):
            return
        pos = self.encScroll.childRelPos.split(' ')
        self.positions[self.curIndex] = (pos[0], pos[1])
        self.setPage(self.history[self.curIndex + 1], False)
        self.curIndex += 1
        pos = self.positions[self.curIndex]
        self.encScroll.scrollRectVisible(pos[0], pos[1], 1, 444)


def encyclopediaSearch(searchvalue):
    global ENCWND
    if not ENCWND:
        PyExec()
    formatted = GetTWikiName(searchvalue)
    page = None
    if ENCYC.has_key('Item%s' % formatted):
        page = 'Item%s' % formatted
    elif ENCYC.has_key('ItemSet%s' % formatted):
        page = 'ItemSet%s' % formatted
    elif ENCYC.has_key('Spell%s' % formatted):
        page = 'Spell%s' % formatted
    elif ENCYC.has_key('Recipe%s' % formatted):
        page = 'Recipe%s' % formatted
    elif ENCYC.has_key('Skill%s' % formatted):
        page = 'Skill%s' % formatted
    elif ENCYC.has_key('Class%s' % formatted):
        page = 'Class%s' % formatted
    elif ENCYC.has_key('Spawn%s' % formatted):
        page = 'Spawn%s' % formatted
    elif ENCYC.has_key('Quest%s' % formatted):
        page = 'Quest%s' % formatted
    elif ENCYC.has_key('Zone%s' % formatted):
        page = 'Zone%s' % formatted
    elif ENCYC.has_key('Faction%s' % formatted):
        page = 'Faction%s' % formatted
    if page:
        ENCWND.setPage(page)
        TGEEval('canvas.pushDialog(EncyclopediaWnd);')
    else:
        TGECall('MessageBoxOK', 'Entry not found', 'No entry for %s in encyclopedia.' % searchvalue)
    return


def encyclopediaGetLink(searchvalue):
    if not searchvalue:
        return
    else:
        if not ENCWND:
            PyExec()
        formatted = GetTWikiName(searchvalue)
        link = None
        if ENCYC.has_key(formatted):
            link = '<a:%s>%s</a>' % (formatted, searchvalue)
        elif ENCYC.has_key('Item%s' % formatted):
            link = '<a:Item%s>%s</a>' % (formatted, searchvalue)
        elif ENCYC.has_key('ItemSet%s' % formatted):
            link = '<a:ItemSet%s>%s</a>' % (formatted, searchvalue)
        elif ENCYC.has_key('Spell%s' % formatted):
            link = '<a:Spell%s>%s</a>' % (formatted, searchvalue)
        elif ENCYC.has_key('Recipe%s' % formatted):
            link = '<a:Recipe%s>%s</a>' % (formatted, searchvalue)
        elif ENCYC.has_key('Skill%s' % formatted):
            link = '<a:Skill%s>%s</a>' % (formatted, searchvalue)
        elif ENCYC.has_key('Class%s' % formatted):
            link = '<a:Class%s>%s</a>' % (formatted, searchvalue)
        elif ENCYC.has_key('Spawn%s' % formatted):
            link = '<a:Spawn%s>%s</a>' % (formatted, searchvalue)
        elif ENCYC.has_key('Quest%s' % formatted):
            link = '<a:Quest%s>%s</a>' % (formatted, searchvalue)
        elif ENCYC.has_key('Zone%s' % formatted):
            link = '<a:Zone%s>%s</a>' % (formatted, searchvalue)
        elif ENCYC.has_key('Faction%s' % formatted):
            link = '<a:Faction%s>%s</a>' % (formatted, searchvalue)
        return link


def OnEncyclopediaOnURL(args):
    page = args[1]
    if page.startswith('chatlink'):
        commandCtrl = TomeGui.tomeCommandCtrl
        TGECall('PushChatGui')
        commandCtrl.visible = True
        commandCtrl.makeFirstResponder(True)
        txt = commandCtrl.GetValue()
        commandCtrl.SetValue('%s <%s>' % (txt, page[8:]))
    elif not ENCWND.setPage(page):
        TGECall('MessageBoxOK', 'Invalid Link', 'Sorry, you just stumbled upon an invalid encyclopedia link, page %s not found.' % page)


def externEncyclopediaLinkURL(args):
    page = args[1].replace('gamelink', '')
    if page.startswith('charlink'):
        commandCtrl = TomeGui.tomeCommandCtrl
        if not commandCtrl.visible:
            TGECall('PushChatGui')
            commandCtrl.visible = True
            commandCtrl.makeFirstResponder(True)
        commandCtrl.SetValue('/tell %s ' % page[8:].replace(' ', '_'))
    elif not ENCWND.setPage(page):
        TGECall('MessageBoxOK', 'Invalid Link', 'Sorry, you just stumbled upon an invalid encyclopedia link, page %s not found.' % page)
    else:
        TGEEval('canvas.pushDialog(EncyclopediaWnd);')


def OnEncyclopediaHome():
    ENCWND.home()


def OnEncyclopediaBack():
    ENCWND.back()


def OnEncyclopediaForward():
    ENCWND.forward()


def PyExec():
    global ENCWND
    ENCWND = EncWindow()
    if not IN_PATCHING:
        try:
            f = open('./%s/data/ui/encyclopedia/MoMWorld.cpz' % GAMEROOT, 'rb')
            zd = f.read()
            f.close()
            ud = cPickle.loads(zlib.decompress(zd))
            for n, text in ud:
                ENCYC[n] = text

        except:
            traceback.print_exc()

    ENCYC['Home'] = HOME
    ENCWND.setPage('Home')
    TGEExport(OnEncyclopediaOnURL, 'Py', 'OnEncyclopediaOnURL', 'desc', 2, 2)
    TGEExport(externEncyclopediaLinkURL, 'Py', 'ExternEncyclopediaLinkURL', 'desc', 2, 2)
    TGEExport(OnEncyclopediaHome, 'Py', 'OnEncyclopediaHome', 'desc', 1, 1)
    TGEExport(OnEncyclopediaForward, 'Py', 'OnEncyclopediaForward', 'desc', 1, 1)
    TGEExport(OnEncyclopediaBack, 'Py', 'OnEncyclopediaBack', 'desc', 1, 1)