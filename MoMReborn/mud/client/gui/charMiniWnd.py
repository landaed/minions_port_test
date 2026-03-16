# Embedded file name: mud\client\gui\charMiniWnd.pyo
from tgenative import *
from mud.tgepython.console import TGEExport
from twisted.internet import reactor
CHARMINIWND = None

class CharMiniPane:

    def __init__(self, index):
        self.castingTick = None
        self.paneCtrl = TGEObject('MINIWND_CHAR%i_PANE' % index)
        self.nameCtrl = TGEObject('MINIWND_CHAR%i_NAME' % index)
        self.targetCtrl = TGEObject('MINIWND_CHAR%i_TARGET' % index)
        self.targetHealthCtrl = TGEObject('MINIWND_CHAR%i_TARGETHEALTH' % index)
        self.manaCtrl = TGEObject('MINIWND_CHAR%i_MANA' % index)
        self.healthCtrl = TGEObject('MINIWND_CHAR%i_HEALTH' % index)
        self.staminaCtrl = TGEObject('MINIWND_CHAR%i_STAMINA' % index)
        self.picCtrl = TGEObject('MINIWND_CHAR%i_PIC' % index)
        self.castingCtrl = TGEObject('MINIWND_CHAR%i_CASTING' % index)
        self.castingCtrl.visible = False
        self.pxpBar = TGEObject('CMDWND_CHAR%i_XP1' % index)
        self.sxpBar = TGEObject('CMDWND_CHAR%i_XP2' % index)
        self.txpBar = TGEObject('CMDWND_CHAR%i_XP3' % index)
        self.petHealth = TGEObject('MINIWND_CHAR%i_PETHEALTH' % index)
        return

    def setCharInfo(self, cinfo):
        if cinfo.DEAD:
            self.picCtrl.setBitmap('~/data/ui/icons/dead')
        else:
            self.picCtrl.setBitmap('~/data/ui/charportraits/%s' % cinfo.PORTRAITPIC)
        self.pxpBar.setValue(cinfo.PXPPERCENT)
        self.sxpBar.setValue(cinfo.SXPPERCENT)
        self.txpBar.setValue(cinfo.TXPPERCENT)
        rInfo = cinfo.RAPIDMOBINFO
        self.picCtrl.pulseRed = rInfo.AUTOATTACK and not cinfo.DEAD
        self.nameCtrl.SetValue(cinfo.NAME)
        self.healthCtrl.SetValue(rInfo.HEALTH / rInfo.MAXHEALTH)
        if rInfo.MAXMANA:
            self.manaCtrl.SetValue(rInfo.MANA / rInfo.MAXMANA)
        else:
            self.manaCtrl.SetValue(0)
        if rInfo.PETNAME:
            self.petHealth.setValue(rInfo.PETHEALTH)
            self.petHealth.visible = True
        else:
            self.petHealth.visible = False
        if cinfo.UNDERWATERRATIO != 1.0:
            self.staminaCtrl.setProfile('GuiBreathBarProfile')
            self.staminaCtrl.SetValue(cinfo.UNDERWATERRATIO)
        else:
            self.staminaCtrl.setProfile('GuiStaminaBarProfile')
            self.staminaCtrl.SetValue(rInfo.STAMINA / rInfo.MAXSTAMINA)
        if rInfo.TGT:
            self.targetCtrl.SetValue(rInfo.TGT)
            self.targetCtrl.visible = True
            self.targetHealthCtrl.SetValue(rInfo.TGTHEALTH)
            self.targetHealthCtrl.visible = True
        else:
            self.targetCtrl.visible = False
            self.targetHealthCtrl.visible = False

    def tickCasting(self):
        self.castingTime += 0.1
        if self.castingTime >= self.castingMaxTime:
            self.castingTime = 0
            self.castingCtrl.visible = False
            self.castingTick = None
            return
        else:
            percent = 1 - self.castingTime / self.castingMaxTime
            self.castingCtrl.SetValue(percent)
            self.castingTick = reactor.callLater(0.1, self.tickCasting)
            return

    def beginCasting(self, time):
        if self.castingTick:
            self.castingTick.cancel()
            self.castingTick = None
        self.castingMaxTime = time
        self.castingTime = 0
        self.castingTick = reactor.callLater(0.1, self.tickCasting)
        self.castingCtrl.visible = True
        self.castingCtrl.SetValue(1)
        return

    def endCasting(self):
        if self.castingTick:
            self.castingTick.cancel()
            self.castingTick = None
        self.castingCtrl.visible = False
        return


class CharMiniWnd:

    def __init__(self):
        self.window = TGEObject('CharMiniWnd_Window')
        self.window.visible = False
        self.window.setActive(False)
        self.charInfos = None
        self.panes = tuple((CharMiniPane(x) for x in xrange(0, 6)))
        for pane in self.panes:
            pane.paneCtrl.visible = False

        return

    def tick(self):
        if not self.charInfos:
            return
        from partyWnd import PARTYWND
        for index, cinfo in self.charInfos.iteritems():
            pane = self.panes[index]
            if index == PARTYWND.curIndex:
                pane.paneCtrl.setProfile('MoMSelectedWndProfile')
            else:
                pane.paneCtrl.setProfile('MoMWndProfile')
            pane.setCharInfo(cinfo)

    def setCharInfos(self, cinfos):
        for x in xrange(0, 6):
            self.panes[x].paneCtrl.visible = False

        self.charInfos = cinfos
        num = len(cinfos)
        self.window.visible = True
        self.window.extent = '121 %i' % int(121 + 92 * (num - 1))
        self.window.setActive(True)
        for x in xrange(0, num):
            self.panes[x].paneCtrl.visible = True

    def beginCasting(self, charIndex, time):
        self.panes[charIndex].beginCasting(time)

    def endCasting(self, charIndex):
        self.panes[charIndex].endCasting()


def PyOnTargetPet(args):
    cindex = int(args[1])
    from partyWnd import PARTYWND
    args = [cindex, 'PET']
    PARTYWND.mind.doCommand('TARGET', args)


def PyExec():
    global CHARMINIWND
    CHARMINIWND = CharMiniWnd()
    TGEExport(PyOnTargetPet, 'Py', 'OnTargetPet', 'desc', 2, 2)