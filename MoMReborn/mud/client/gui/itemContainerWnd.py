# Embedded file name: mud\client\gui\itemContainerWnd.pyo
from tgenative import *
from mud.tgepython.console import TGEExport
from mud.world.defines import *
from tomeGui import TomeGui
receiveGameText = TomeGui.instance.receiveGameText
TEXT_HEADER = '<font:Arial Bold:14><just:center><shadow:1:1><shadowcolor:000000>'

class ItemContainerWnd(object):
    instance = None

    def __new__(cl, *p, **k):
        if not ItemContainerWnd.instance:
            ItemContainerWnd.instance = object.__new__(cl, *p, **k)
        return ItemContainerWnd.instance

    def __init__(self):
        self.container = None
        self.content = {}
        self.lastSelectedID = -1
        return

    def initTGEObjects(self):
        self.window = TGEObject('ItemContainerWnd')
        self.pane = TGEObject('ItemContainerWnd_Window')
        self.tgeContentCount = TGEObject('ItemContainerWnd_ContentCount')
        self.tgeContentInfoPic = TGEObject('ItemContainerWnd_ContentInfoPic')
        self.tgeContentInfoText = TGEObject('ItemContainerWnd_ContentInfoText')
        self.tgeContentInfoFlags = TGEObject('ItemContainerWnd_ContentInfoFlags')
        self.tgeContentInfoName = TGEObject('ItemContainerWnd_ContentInfoName')
        self.tgeContentList = TGEObject('ItemContainerWnd_ContentList')

    def getMouseOver(self):
        pass

    def openContainer(self, container):
        if not container.CONTAINERSIZE:
            return
        self.container = container
        self.pane.setText(str(container.NAME))
        contentCount = len(container.CONTENT)
        self.tgeContentCount.setText('%sStorage used: %i / %i' % (TEXT_HEADER, contentCount, container.CONTAINERSIZE))
        self.tgeContentList.clear()
        self.lastSelectedID = -1
        self.content.clear()
        if contentCount:
            for i, citem in enumerate(container.CONTENT):
                self.content[i] = citem
                self.tgeContentList.addRow(i, '%i\t%s' % (citem.STACKCOUNT, citem.NAME))

            self.tgeContentList.sort(1)
            self.tgeContentList.setSelectedRow(0)
            self.tgeContentList.scrollVisible(0)
        else:
            self.tgeContentInfoName.setText('')
            self.tgeContentInfoFlags.setText('')
            self.tgeContentInfoText.setText('')
            self.tgeContentInfoPic.setBitmap('')
        if not int(self.window.isAwake()):
            TGEEval('canvas.pushDialog(ItemContainerWnd);')

    def closeContainer(self):
        self.container = None
        TGEEval('canvas.popDialog(ItemContainerWnd);')
        return

    def onSelect(self):
        selectedID = int(self.tgeContentList.getSelectedId())
        if selectedID == self.lastSelectedID:
            return
        self.lastSelectedID = selectedID
        try:
            ghost = self.content[selectedID]
        except KeyError:
            self.tgeContentInfoName.setText('')
            self.tgeContentInfoFlags.setText('')
            self.tgeContentInfoText.setText('')
            self.tgeContentInfoPic.setBitmap('')
            return

        TGEEval('ItemContainerWnd_ContentInfoName.setText("%s%s");' % (TEXT_HEADER, ghost.NAME))
        text = ' '.join(('\\cp\\c2%s\\co ' % ftext for f, ftext in RPG_ITEM_FLAG_TEXT.iteritems() if f & ghost.FLAGS))
        TGEEval('ItemContainerWnd_ContentInfoFlags.setText("%s%s");' % (TEXT_HEADER, text))
        text = ''
        if ghost.SPELLINFO:
            text = '\\n\\n%s' % ghost.SPELLINFO.text
        TGEEval('ItemContainerWnd_ContentInfoText.setText("%s%s%s");' % (TEXT_HEADER, ghost.text, text))
        self.tgeContentInfoPic.setBitmap('~/data/ui/items/%s/0_0_0' % ghost.BITMAP)

    def onInsert(self):
        container = self.container
        if not container:
            return
        from mud.client.playermind import PLAYERMIND
        if not PLAYERMIND.cursorItem:
            return
        if PLAYERMIND.cursorItem.CONTAINERSIZE:
            return
        PLAYERMIND.perspective.callRemote('PlayerAvatar', 'insertItem', container.SLOT, container.OWNERCHARID)

    def onExtract(self):
        selectedID = int(self.tgeContentList.getSelectedId())
        try:
            ghost = self.content[selectedID]
        except KeyError:
            return

        from mud.client.playermind import PLAYERMIND
        if PLAYERMIND.cursorItem:
            receiveGameText(RPG_MSG_GAME_DENIED, 'Please put down the item in your cursor first.\\n')
            return
        container = self.container
        PLAYERMIND.perspective.callRemote('PlayerAvatar', 'extractItem', container.SLOT, container.OWNERCHARID, selectedID)


ItemContainerWnd()

def PyExec():
    ITEMCONTAINERWND = ItemContainerWnd.instance
    ITEMCONTAINERWND.initTGEObjects()
    TGEExport(ITEMCONTAINERWND.closeContainer, 'Py', 'OnItemContainerClose', 'desc', 1, 1)
    TGEExport(ITEMCONTAINERWND.onSelect, 'Py', 'OnItemContainerSelect', 'desc', 1, 1)
    TGEExport(ITEMCONTAINERWND.onInsert, 'Py', 'OnItemContainerInsert', 'desc', 1, 1)
    TGEExport(ITEMCONTAINERWND.onExtract, 'Py', 'OnItemContainerExtract', 'desc', 1, 1)