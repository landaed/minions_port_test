# Embedded file name: mud\client\gui\macro.pyo
from tgenative import *
from mud.tgepython.console import TGEExport
from twisted.internet import reactor
from mud.world.defines import *
from mud.gamesettings import *
from defaultCommandsWnd import GetDefaultCommand
from skillinfo import GetSkillInfo
from mud.client.playermind import PyDoCommand
from macroWnd import MacroWnd
MacroWnd = MacroWnd.instance
from time import time
from copy import deepcopy
from operator import itemgetter
MACROMASTER = None
CURSORMACRO = None
MACRO_IDLE, MACRO_RUNNING, MACRO_RECOVERING = range(3)

class CursorMacro():

    def __init__(self):
        self.macroType = None
        self.macroInfo = None
        self.charIndex = -1
        self.clearingTimer = None
        self.cursor = TGEObject('DefaultCursor')
        return

    def clear(self):
        if not self.clearingTimer:
            return
        else:
            try:
                self.clearingTimer.cancel()
            except:
                pass

            self.clearingTimer = None
            self.setMacro(None, None)
            MACROMASTER.showEmptySlots(False)
            return

    def setMacro(self, macroType, macroInfo, button = None, charIndex = -1):
        cursor = self.cursor
        cursor.bitmapName = ''
        cursor.u0 = cursor.v0 = 0
        cursor.u1 = cursor.v1 = 1
        cursor.sizeX = -1
        cursor.sizeY = -1
        if self.clearingTimer:
            try:
                self.clearingTimer.cancel()
            except:
                pass

            self.clearingTimer = None
        if macroType:
            self.clearingTimer = reactor.callLater(14, self.clear)
            MACROMASTER.showEmptySlots(True)
        self.macroType, self.macroInfo, self.charIndex = macroType, macroInfo, charIndex
        if button:
            cursor.cursorControl = button
        else:
            cursor.cursorControl = ''
        return


class MacroLine():

    def __init__(self, command = '', mandatory = True, delayAfter = 0):
        self.command = command
        self.mandatory = mandatory
        self.delayAfter = delayAfter
        self.skill = ''
        self.spell = ''
        self.item = ''
        self.retarget = ''
        self.realCommand = ''

    def checkAvailability(self, charIndex):
        from partyWnd import PARTYWND
        commandCharIndex = charIndex
        commandCharInfo = None
        if self.retarget:
            command = self.realCommand
            for charIndex, charInfo in PARTYWND.charInfos.iteritems():
                if charInfo.NAME.upper() == self.retarget:
                    commandCharIndex = charIndex
                    commandCharInfo = charInfo
                    break
            else:
                return True

        else:
            command = self.command
            commandCharInfo = PARTYWND.charInfos[commandCharIndex]
        if not command:
            return True
        else:
            return checkCommandAvailability(commandCharInfo, command)

    def execute(self, charIndex):
        from partyWnd import PARTYWND
        commandCharIndex = charIndex
        commandCharInfo = None
        if self.retarget:
            command = self.realCommand
            for charIndex, charInfo in PARTYWND.charInfos.iteritems():
                if charInfo.NAME.upper() == self.retarget:
                    commandCharIndex = charIndex
                    commandCharInfo = charInfo
                    break
            else:
                return (True, self.delayAfter == 0)

        else:
            command = self.command
            commandCharInfo = PARTYWND.charInfos[commandCharIndex]
        if not command:
            return (True, self.delayAfter == 0)
        else:
            available = checkCommandAvailability(commandCharInfo, command)
            if not available:
                if self.mandatory:
                    return (False, False)
                else:
                    return (False, True)
            if len(command) and command[0] == '/':
                PyDoCommand(['PyDoCommand', command], False, commandCharIndex)
            return (True, False)


class Macro():

    def __init__(self, charIndex, page, slot, name = '', hotkey = '', icon = '', description = '', waitAll = True, manualDelay = 0):
        self.charIndex = charIndex
        self.page = page
        self.slot = slot
        self.name = name
        self.hotkey = hotkey
        if not self.hotkey:
            self.hotkey = str((slot + 1) % 10)
        self.icon = icon
        self.description = description
        self.waitAll = waitAll
        self.manualDelay = manualDelay
        self.macroLines = dict()
        self.macroLineNextIndex = 0
        self.macroLineNum = 0
        self.skills = list()
        self.spells = list()
        self.items = list()
        self.hasAttack = 0
        self.hasRangedAttack = 0
        self.status = MACRO_IDLE
        self.activeLine = -1
        self.startTime = 0
        self.recoveryDelay = 0
        self.visible = False
        self.macroButton = TGEObject('MACROWND_MACRO%i_%i' % (charIndex, slot))
        self.appearanceAggressive = False
        self.resetPulseTimer = None
        return

    def appendMacroLine(self, macroLine):
        command = macroLine.command
        self.macroLines[self.macroLineNextIndex] = macroLine
        self.macroLineNextIndex += 1
        self.macroLineNum += 1
        try:
            if command[0] == '*':
                charName, command = command[1:].split('* ', 1)
                command = command.lstrip()
                charName = charName.upper()
                macroLine.retarget = charName
                macroLine.realCommand = command
            if command[0] == '/':
                args = command[1:].upper().split(' ', 1)
                if len(args) > 1:
                    command, arg = args
                    arg = arg.lstrip()
                else:
                    command, arg = args[0], ''
                if command == 'SKILL':
                    macroLine.skill = arg
                    self.skills.append(arg)
                elif command == 'CAST':
                    macroLine.spell = arg
                    self.spells.append(arg)
                elif command == 'USEITEM':
                    macroLine.item = arg
                    self.items.append(arg)
                elif command == 'ATTACK':
                    self.hasAttack += 1
                elif command == 'RANGEDATTACK':
                    self.hasRangedAttack += 1
        except IndexError:
            pass

    def appendMacroLines(self, lineIterable):
        for macroLine in lineIterable:
            command = macroLine.command
            self.macroLines[self.macroLineNextIndex] = macroLine
            self.macroLineNextIndex += 1
            self.macroLineNum += 1
            try:
                if command[0] == '*':
                    charName, command = command[1:].split('* ', 1)
                    command = command.lstrip()
                    charName = charName.upper()
                    macroLine.retarget = charName
                    macroLine.realCommand = command
                if command[0] == '/':
                    args = command[1:].upper().split(' ', 1)
                    if len(args) > 1:
                        command, arg = args
                        arg = arg.lstrip()
                    else:
                        command, arg = args[0], ''
                    if command == 'SKILL':
                        macroLine.skill = arg
                        self.skills.append(arg)
                    elif command == 'CAST':
                        macroLine.spell = arg
                        self.spells.append(arg)
                    elif command == 'USEITEM':
                        macroLine.item = arg
                        self.items.append(arg)
                    elif command == 'ATTACK':
                        self.hasAttack += 1
                    elif command == 'RANGEDATTACK':
                        self.hasRangedAttack += 1
            except IndexError:
                continue

    def insertMacroLine(self, lineIndex, macroLine):
        if lineIndex >= self.macroLineNextIndex:
            self.macroLineNextIndex = lineIndex + 1
        oldLine = self.macroLines.get(lineIndex)
        if oldLine:
            if oldLine.skill:
                self.skills.remove(oldLine.skill)
            if oldLine.spell:
                self.spells.remove(oldLine.spell)
            if oldLine.item:
                self.items.remove(oldLine.item)
            if oldLine.command.upper().find('/ATTACK') != -1:
                self.hasAttack -= 1
            if oldLine.command.upper().find('/RANGEDATTACK') != -1:
                self.hasRangedAttack -= 1
            del oldLine
        else:
            self.macroLineNum += 1
        self.macroLines[lineIndex] = macroLine
        command = macroLine.command
        try:
            if command[0] == '*':
                charName, command = command[1:].split('* ', 1)
                command = command.lstrip()
                charName = charName.upper()
                macroLine.retarget = charName
                macroLine.realCommand = command
            if command[0] == '/':
                args = command[1:].upper().split(' ', 1)
                if len(args) > 1:
                    command, arg = args
                    arg = arg.lstrip()
                else:
                    command, arg = args[0], ''
                if command == 'SKILL':
                    macroLine.skill = arg
                    self.skills.append(arg)
                elif command == 'CAST':
                    macroLine.spell = arg
                    self.spells.append(arg)
                elif command == 'USEITEM':
                    macroLine.item = arg
                    self.items.append(arg)
                elif command == 'ATTACK':
                    self.hasAttack += 1
                elif command == 'RANGEDATTACK':
                    self.hasRangedAttack += 1
        except IndexError:
            pass

    def setVisibility(self, visible):
        if visible != self.visible:
            self.visible = visible
            if visible:
                macroButton = self.macroButton
                icon = self.icon
                if icon:
                    if icon.startswith('SPELLICON_'):
                        split = icon.split('_')
                        index = int(split[2])
                        u0 = float(index % 6) * 40.0 / 256.0
                        v0 = float(index / 6) * 40.0 / 256.0
                        u1 = 40.0 / 256.0
                        v1 = 40.0 / 256.0
                        macroButton.setBitmapUV('~/data/ui/icons/spells0%s' % split[1], u0, v0, u1, v1)
                    else:
                        macroButton.setBitmap('~/data/ui/%s' % icon)
                else:
                    macroButton.setBitmap('')
                macroButton.setText(self.name)
                macroButton.hotKey = self.hotkey
                macroButton.tooltip = self.description
                if self.appearanceAggressive:
                    macroButton.pulseGreen = False
                    macroButton.pulseRed = True
                    macroButton.setValue(1)
                    macroButton.toggleLocked = False
                elif self.status == MACRO_RUNNING:
                    macroButton.pulseGreen = False
                    macroButton.pulseRed = True
                    macroButton.setValue(1)
                    macroButton.toggleLocked = False
                elif self.status == MACRO_RECOVERING:
                    macroButton.pulseGreen = False
                    macroButton.pulseRed = False
                    macroButton.setValue(1)
                    macroButton.toggleLocked = True
                else:
                    macroButton.pulseGreen = False
                    macroButton.pulseRed = False
                    macroButton.setValue(0)
                    macroButton.toggleLocked = False

    def resetPulsing(self):
        if self.resetPulseTimer:
            try:
                self.resetPulseTimer.cancel()
            except:
                pass

            self.resetPulseTimer = None
        if self.visible:
            self.macroButton.pulseGreen = False
        return

    def tick(self):
        finished = False
        if self.activeLine == -1:
            self.activeLine = 0
            self.startTime = time()
            self.status = MACRO_RUNNING
        done = False
        executed = False
        while not done:
            try:
                executed, skipped = self.macroLines[self.activeLine].execute(self.charIndex)
                if skipped:
                    self.activeLine += 1
                else:
                    done = True
            except KeyError:
                self.activeLine += 1

            if self.activeLine >= self.macroLineNextIndex:
                done = True
                finished = True

        delay = 0
        if not finished and executed:
            delay = self.macroLines[self.activeLine].delayAfter
        if executed:
            self.activeLine += 1
            lineIndex = self.activeLine
            done = False
            while not done:
                try:
                    nextLine = self.macroLines[lineIndex]
                    if not nextLine.command and not nextLine.delayAfter:
                        lineIndex += 1
                    else:
                        done = True
                except KeyError:
                    lineIndex += 1

                if lineIndex >= self.macroLineNextIndex:
                    done = True
                    finished = True

        curTime = time()
        if finished:
            manualDelay = self.manualDelay + self.startTime - curTime
            if manualDelay > 0:
                if manualDelay > delay:
                    self.recoveryDelay = manualDelay
                else:
                    self.recoveryDelay = delay
            else:
                self.recoveryDelay = delay
            self.startTime = curTime
        else:
            if self.visible:
                self.macroButton.pulseGreen = False
                self.macroButton.pulseRed = True
                self.macroButton.setValue(1)
                self.macroButton.toggleLocked = False
            if delay < 1:
                delay = 1
        return (finished, delay + curTime)

    def recover(self):
        recovered = True
        if self.macroLineNum == 1:
            for macroLine in self.macroLines.itervalues():
                recovered = macroLine.checkAvailability(self.charIndex)

        else:
            for macroLine in self.macroLines.itervalues():
                if macroLine.mandatory or self.waitAll:
                    if not macroLine.checkAvailability(self.charIndex):
                        recovered = False
                        break

        if recovered:
            if self.startTime + self.recoveryDelay > time():
                recovered = False
        if recovered:
            if not self.appearanceAggressive and self.visible:
                self.macroButton.pulseRed = False
                self.macroButton.setValue(0)
                self.macroButton.toggleLocked = False
                if self.status == MACRO_RECOVERING:
                    self.macroButton.pulseGreen = True
                    self.resetPulseTimer = reactor.callLater(0.5, self.resetPulsing)
            self.recoveryDelay = 0
            self.activeLine = -1
            self.status = MACRO_IDLE
            return True
        self.status = MACRO_RECOVERING
        if self.visible and not self.appearanceAggressive:
            self.macroButton.pulseGreen = False
            self.macroButton.pulseRed = False
            self.macroButton.setValue(1)
            self.macroButton.toggleLocked = True
        return False

    def skillUsed(self, skill):
        if self.status != MACRO_IDLE:
            return False
        if self.macroLineNum == 1:
            return True
        for line in self.macroLines.itervalues():
            if line.mandatory:
                if line.skill == skill:
                    return True

        return False

    def spellUsed(self, spell):
        if self.status != MACRO_IDLE:
            return False
        if self.macroLineNum == 1:
            return True
        for line in self.macroLines.itervalues():
            if line.mandatory:
                if line.spell == spell:
                    return True

        return False

    def itemUsed(self, item):
        if self.status != MACRO_IDLE:
            return False
        if self.macroLineNum == 1:
            return True
        for line in self.macroLines.itervalues():
            if line.mandatory:
                if line.item == item:
                    return True

        return False

    def updateAttacking(self, attacking = True, ranged = False):
        if not ranged:
            if attacking != self.appearanceAggressive:
                self.appearanceAggressive = attacking
                if self.visible:
                    macroButton = self.macroButton
                    if attacking:
                        macroButton.pulseGreen = False
                        macroButton.pulseRed = True
                        macroButton.setValue(1)
                        macroButton.toggleLocked = False
                    elif self.status == MACRO_RUNNING:
                        macroButton.pulseGreen = False
                        macroButton.pulseRed = True
                        macroButton.setValue(1)
                        macroButton.toggleLocked = False
                    elif self.status == MACRO_RECOVERING:
                        macroButton.pulseGreen = False
                        macroButton.pulseRed = False
                        macroButton.setValue(1)
                        macroButton.toggleLocked = True
                    else:
                        macroButton.pulseGreen = False
                        macroButton.pulseRed = False
                        macroButton.setValue(0)
                        macroButton.toggleLocked = False
            return False
        elif self.status != MACRO_IDLE:
            return False
        elif self.macroLineNum == 1:
            return True
        else:
            for line in self.macroLines.itervalues():
                if line.mandatory:
                    if line.command.upper().find('/RANGEDATTACK') != -1:
                        return True

            return False


TOOLTIP_TEXT = 'Macro Button. Ctrl + Number to switch pages. Right Click to edit. Drag & Drop spells, items or skills to create.'

class MacroMaster():

    def __init__(self):
        self.extendedMacros = True
        self.macros = dict()
        self.hotkeyDict = dict()
        self.activePage = 0
        self.runningMacros = dict()
        self.recoveringMacros = dict()
        self.skillDict = dict()
        self.spellDict = dict()
        self.itemDict = dict()
        self.attackMacros = dict()
        self.rangedAttackMacros = dict()
        self.emptyVisibleSlots = dict()

    def installMacroCollection(self, macroCollection):
        self.macros = macroCollection
        self.hotkeyDict.clear()
        self.activePage = 0
        MacroWnd.updateActivePage(0)
        self.runningMacros.clear()
        self.recoveringMacros.clear()
        self.skillDict.clear()
        self.spellDict.clear()
        self.itemDict.clear()
        self.attackMacros.clear()
        self.rangedAttackMacros.clear()
        self.emptyVisibleSlots.clear()
        for charIndex, macroDict in macroCollection.iteritems():
            emptyVisibleSlots = self.emptyVisibleSlots[charIndex] = set(range(10))
            charHotkeys = self.hotkeyDict[charIndex] = dict()
            for position, macro in macroDict.iteritems():
                hotkey = macro.hotkey
                if hotkey:
                    if hotkey[0] != 'F':
                        hotkey = '%i - %s' % (position[0], hotkey)
                    charHotkeys.setdefault(hotkey, set()).add(macro)
                for skill in macro.skills:
                    self.skillDict.setdefault(skill, set()).add(macro)

                for spell in macro.spells:
                    self.spellDict.setdefault(spell, set()).add(macro)

                for item in macro.items:
                    self.itemDict.setdefault(item, set()).add(macro)

                if macro.hasAttack:
                    self.attackMacros.setdefault(charIndex, set()).add(macro)
                if macro.hasRangedAttack:
                    self.rangedAttackMacros.setdefault(charIndex, set()).add(macro)
                if self.activePage == position[0]:
                    emptyVisibleSlots.discard(position[1])
                    macro.setVisibility(True)
                self.recoveringMacros.setdefault(charIndex, set()).add(macro)

            for slot in emptyVisibleSlots:
                control = TGEObject('MACROWND_MACRO%i_%i' % (charIndex, slot))
                control.setText('')
                control.setBitmap('')
                control.hotKey = -1
                control.pulseGreen = False
                control.pulseRed = False
                control.toggleLocked = True
                control.setValue(0)
                control.tooltip = TOOLTIP_TEXT

    def insertMacro(self, charIndex, page, slot, macro = None):
        from playerSettings import PLAYERSETTINGS
        visible = self.activePage == page
        charMacros = self.macros.setdefault(charIndex, dict())
        oldMacro = charMacros.get((page, slot), None)
        if oldMacro:
            try:
                del self.runningMacros[charIndex][oldMacro]
            except KeyError:
                pass

            try:
                self.recoveringMacros[charIndex].discard(oldMacro)
            except KeyError:
                pass

            try:
                hotkey = oldMacro.hotkey
                if hotkey:
                    if hotkey[0] != 'F':
                        hotkey = '%i - %s' % (page, hotkey)
                    self.hotkeyDict[charIndex][hotkey].discard(oldMacro)
            except KeyError:
                pass

            for skill in oldMacro.skills:
                try:
                    self.skillDict[skill].discard(oldMacro)
                    if len(self.skillDict[skill]) == 0:
                        del self.skillDict[skill]
                except KeyError:
                    continue

            for spell in oldMacro.spells:
                try:
                    self.spellDict[spell].discard(oldMacro)
                    if len(self.spellDict[spell]) == 0:
                        del self.spellDict[spell]
                except KeyError:
                    continue

            for item in oldMacro.items:
                try:
                    self.itemDict[item].discard(oldMacro)
                    if len(self.itemDict[item]) == 0:
                        del self.itemDict[item]
                except KeyError:
                    continue

            if oldMacro.hasAttack:
                self.attackMacros[charIndex].discard(oldMacro)
            if oldMacro.hasRangedAttack:
                self.rangedAttackMacros[charIndex].discard(oldMacro)
            if visible:
                self.emptyVisibleSlots.setdefault(charIndex, set(range(10))).add(slot)
            del charMacros[page, slot]
            if not macro:
                PLAYERSETTINGS.deleteMacro(charIndex, page, slot)
                if visible:
                    control = TGEObject('MACROWND_MACRO%i_%i' % (charIndex, slot))
                    control.setText('')
                    control.setBitmap('')
                    control.hotKey = -1
                    control.pulseGreen = False
                    control.pulseRed = False
                    control.toggleLocked = True
                    control.setValue(0)
                    control.tooltip = TOOLTIP_TEXT
                return
        if not macro:
            return
        else:
            hotkey = macro.hotkey
            if hotkey:
                if hotkey[0] != 'F':
                    hotkey = '%i - %s' % (page, hotkey)
                self.hotkeyDict.setdefault(charIndex, dict()).setdefault(hotkey, set()).add(macro)
            self.macros.setdefault(charIndex, dict())[page, slot] = macro
            for skill in macro.skills:
                self.skillDict.setdefault(skill, set()).add(macro)

            for spell in macro.spells:
                self.spellDict.setdefault(spell, set()).add(macro)

            for item in macro.items:
                self.itemDict.setdefault(item, set()).add(macro)

            if macro.hasAttack:
                self.attackMacros.setdefault(charIndex, set()).add(macro)
            if macro.hasRangedAttack:
                self.rangedAttackMacros.setdefault(charIndex, set()).add(macro)
            if visible:
                self.emptyVisibleSlots.setdefault(charIndex, set(range(10))).discard(slot)
                macro.setVisibility(True)
            PLAYERSETTINGS.saveMacro(macro, oldMacro != None)
            self.recoveringMacros.setdefault(charIndex, set()).add(macro)
            return

    def setMacroPage(self, page):
        global CURSORMACRO
        if page != self.activePage:
            from partyWnd import PARTYWND
            self.emptyVisibleSlots.clear()
            pulseGreen = CURSORMACRO.macroType or PARTYWND.mind.cursorItem
            for charIndex, macroDict in self.macros.iteritems():
                emptyVisibleSlots = self.emptyVisibleSlots.setdefault(charIndex, set(range(10)))
                for position, macro in macroDict.iteritems():
                    if position[0] == self.activePage:
                        macro.setVisibility(False)
                    elif position[0] == page:
                        macro.setVisibility(True)
                        emptyVisibleSlots.discard(position[1])

                for emptySlot in emptyVisibleSlots:
                    control = TGEObject('MACROWND_MACRO%i_%i' % (charIndex, emptySlot))
                    control.setText('')
                    control.setBitmap('')
                    control.hotKey = -1
                    control.pulseGreen = pulseGreen
                    control.pulseRed = False
                    control.toggleLocked = pulseGreen
                    control.setValue(0)
                    control.tooltip = TOOLTIP_TEXT

            self.activePage = page
            MacroWnd.updateActivePage(page)

    def showEmptySlots(self, show = True):
        for charIndex, emptyVisibleSlots in self.emptyVisibleSlots.iteritems():
            for emptySlot in emptyVisibleSlots:
                control = TGEObject('MACROWND_MACRO%i_%i' % (charIndex, emptySlot))
                control.pulseGreen = show
                control.toggleLocked = show

    def tick(self):
        if not self.extendedMacros:
            page = 0
            try:
                if int(TGEGetGlobal('$Py::Input::ShiftDown')):
                    page = 1
            except:
                pass

            try:
                if int(TGEGetGlobal('$Py::Input::ControlDown')):
                    page = 2
            except:
                pass

            self.setMacroPage(page)
        curTime = time()
        for charIndex, runningMacros in self.runningMacros.iteritems():
            if not runningMacros:
                continue
            try:
                oneGetter = itemgetter(1)
                handleMacro, fireTime = min(runningMacros.iteritems(), key=oneGetter)
                if fireTime > curTime:
                    continue
                finished, nextFireTime = handleMacro.tick()
                if handleMacro not in runningMacros:
                    continue
                if not finished:
                    runningMacros[handleMacro] = nextFireTime
                else:
                    del runningMacros[handleMacro]
                    self.recoveringMacros.setdefault(charIndex, set()).add(handleMacro)
            except IndexError:
                continue

        for charIndex, recoveringMacros in self.recoveringMacros.iteritems():
            recoveredMacros = set()
            for macro in recoveringMacros:
                if macro.recover():
                    recoveredMacros.add(macro)

            recoveringMacros.difference_update(recoveredMacros)

    def stopMacrosForChar(self, charIndex):
        runningMacros = self.runningMacros.get(charIndex)
        if runningMacros:
            self.recoveringMacros.setdefault(charIndex, set()).update(runningMacros.iterkeys())
            runningMacros.clear()

    def stopNamedMacroForChar(self, charIndex, macroName):
        runningMacros = self.runningMacros.get(charIndex)
        if runningMacros:
            macroName = macroName.upper()
            recoveringMacros = self.recoveringMacros.setdefault(charIndex, set())
            needRemoval = set()
            for macro in runningMacros:
                if macroName == macro.name.upper():
                    recoveringMacros.add(macro)
                    needRemoval.add(macro)

            for macro in needRemoval:
                del runningMacros[macro]

    def updateSkillUsingMacros(self, skill = '', iterableSkills = None):
        if not iterableSkills:
            iterableSkills = [skill]
        for skill in iterableSkills:
            skill = skill.upper()
            skillMacros = self.skillDict.get(skill)
            if skillMacros:
                for macro in skillMacros:
                    needsRecovery = macro.skillUsed(skill)
                    if needsRecovery:
                        self.recoveringMacros.setdefault(macro.charIndex, set()).add(macro)

    def updateSpellUsingMacros(self, spell):
        spell = spell.upper()
        spellMacros = self.spellDict.get(spell)
        if spellMacros:
            for macro in spellMacros:
                needsRecovery = macro.spellUsed(spell)
                if needsRecovery:
                    self.recoveringMacros.setdefault(macro.charIndex, set()).add(macro)

    def updateItemUsingMacros(self, itemName):
        itemName = itemName.upper()
        itemMacros = self.itemDict.get(itemName)
        if itemMacros:
            for macro in itemMacros:
                needsRecovery = macro.itemUsed(itemName)
                if needsRecovery:
                    self.recoveringMacros.setdefault(macro.charIndex, set()).add(macro)

    def updateAttackMacros(self, charIndex, attacking):
        attackMacros = self.attackMacros.get(charIndex)
        if attackMacros:
            for macro in attackMacros:
                macro.updateAttacking(attacking)

    def updateRangedAttackMacros(self, charIndex):
        rangedAttackMacros = self.rangedAttackMacros.get(charIndex)
        if rangedAttackMacros:
            for macro in rangedAttackMacros:
                needsRecovery = macro.updateAttacking(ranged=True)
                if needsRecovery:
                    self.recoveringMacros.setdefault(charIndex, set()).add(macro)

    def onMacroButtonClick(self, args):
        from partyWnd import PARTYWND
        charIndex = int(args[1])
        macroSlot = int(args[2])
        page = self.activePage
        if charIndex >= len(PARTYWND.charInfos):
            page += charIndex
            charIndex = 0
        charInfo = PARTYWND.charInfos[charIndex]
        macroType = CURSORMACRO.macroType
        macroInfo = CURSORMACRO.macroInfo
        if macroType:
            newMacro = Macro(charIndex, page, macroSlot)
            newMacroLines = list()
            if CURSORMACRO.charIndex != -1:
                charInfo = PARTYWND.charInfos[CURSORMACRO.charIndex]
            if macroType == 'INV':
                pass
            elif macroType == 'SKILL':
                skillInfo = GetSkillInfo(macroInfo)
                newMacro.name = skillInfo.name
                newMacro.icon = skillInfo.icon
                if newMacro.icon and not newMacro.icon.startswith('SPELLICON_'):
                    newMacro.icon = 'icons/%s' % newMacro.icon
                newMacro.description = skillInfo.name
                newMacroLines.append(MacroLine('/skill %s' % skillInfo.name))
            elif macroType == 'SPELL':
                spell = charInfo.SPELLS.get(macroInfo)
                if spell:
                    spellInfo = spell.SPELLINFO
                    newMacro.name = spellInfo.NAME
                    newMacro.icon = spellInfo.SPELLBOOKPIC
                    if newMacro.icon and not newMacro.icon.startswith('SPELLICON_'):
                        newMacro.icon = 'spellicons/%s' % newMacro.icon
                    newMacro.description = spellInfo.NAME
                    newMacroLines.append(MacroLine('/cast %s' % spellInfo.BASENAME))
            elif macroType == 'CMD':
                newMacro.name = macroInfo.name
                newMacro.icon = macroInfo.icon
                if newMacro.icon and not newMacro.icon.startswith('SPELLICON_'):
                    newMacro.icon = 'icons/%s' % newMacro.icon
                newMacro.description = macroInfo.tooltip
                newMacroLines.append(MacroLine(macroInfo.command))
            elif macroType == 'CUSTOMMACRO':
                newMacro.name = macroInfo.name
                newMacro.icon = macroInfo.icon
                newMacro.description = macroInfo.description
                newMacro.waitAll = macroInfo.waitAll
                newMacro.manualDelay = macroInfo.manualDelay
                newMacroLines = deepcopy(macroInfo.macroLines.values())
            if CURSORMACRO.charIndex != -1:
                if charIndex != CURSORMACRO.charIndex:
                    charName = charInfo.NAME
                    for macroLine in newMacroLines:
                        macroLine.command = '*%s* %s' % (charName, macroLine.command)

            newMacro.appendMacroLines(newMacroLines)
            self.insertMacro(charIndex, page, macroSlot, newMacro)
            CURSORMACRO.clear()
        elif PARTYWND.mind.cursorItem:
            cursorItem = PARTYWND.mind.cursorItem
            newMacro = Macro(charIndex, page, macroSlot)
            if RPG_SLOT_RANGED in cursorItem.SLOTS:
                defaultCommand = GetDefaultCommand('Ranged Attack')
                newMacro.name = defaultCommand.name
                newMacro.icon = defaultCommand.icon
                if newMacro.icon and not newMacro.icon.startswith('SPELLICON_'):
                    newMacro.icon = 'icons/%s' % newMacro.icon
                newMacro.description = defaultCommand.tooltip
                newMacro.appendMacroLine(MacroLine(defaultCommand.command))
            else:
                newMacro.name = cursorItem.NAME
                newMacro.icon = 'items/%s/0_0_0' % cursorItem.BITMAP
                newMacro.description = 'Use %s' % cursorItem.NAME
                newMacro.appendMacroLine(MacroLine('/useitem %s' % cursorItem.NAME))
            self.insertMacro(charIndex, page, macroSlot, newMacro)
        else:
            activate = True
            if self.extendedMacros:
                try:
                    if int(TGEGetGlobal('$Py::Input::ShiftDown')):
                        activate = False
                except:
                    pass

            charMacros = self.macros.get(charIndex)
            if not charMacros:
                return
            clickedMacro = charMacros.get((page, macroSlot))
            if not clickedMacro:
                return
            if activate:
                try:
                    if clickedMacro in self.recoveringMacros[charIndex]:
                        return
                except KeyError:
                    pass

                self.runningMacros.setdefault(charIndex, dict())[clickedMacro] = time()
            else:
                try:
                    del self.runningMacros[charIndex][clickedMacro]
                    self.recoveringMacros.setdefault(charIndex, set()).add(clickedMacro)
                except KeyError:
                    pass

    def onMacroButtonClickAlt(self, args):
        from partyWnd import PARTYWND
        charIndex = int(args[1])
        macroSlot = int(args[2])
        page = self.activePage
        if charIndex >= len(PARTYWND.charInfos):
            page += charIndex
            charIndex = 0
        macro = None
        charMacros = self.macros.get(charIndex)
        if charMacros:
            macro = charMacros.get((page, macroSlot))
        from macroEditorWnd import MACROEDITOR
        MACROEDITOR.openMacroEditor(charIndex, page, macroSlot, macro)
        return

    def onSetMacroPage(self, args):
        index = args[1]
        if not self.extendedMacros:
            return
        self.setMacroPage(int(index) % 10)

    def onHotKey(self, args):
        hotkey = args[1]
        if hotkey[0] != 'F':
            if self.extendedMacros:
                try:
                    if int(TGEGetGlobal('$Py::Input::ControlDown')):
                        self.setMacroPage((int(hotkey) - 1) % 10)
                        return
                except:
                    pass

            hotkey = '%i - %s' % (self.activePage, hotkey)
        activate = True
        if self.extendedMacros:
            try:
                if int(TGEGetGlobal('$Py::Input::ShiftDown')):
                    activate = False
            except:
                pass

        if activate:
            curTime = time()
            for charIndex, hotkeyDict in self.hotkeyDict.iteritems():
                try:
                    macroSet = hotkeyDict[hotkey]
                    runningMacros = self.runningMacros.setdefault(charIndex, dict())
                    recoveringMacros = self.recoveringMacros.setdefault(charIndex, set())
                    for macro in macroSet:
                        if macro in recoveringMacros:
                            continue
                        runningMacros[macro] = curTime

                except KeyError:
                    continue

        else:
            for charIndex, hotkeyDict in self.hotkeyDict.iteritems():
                runningMacros = self.runningMacros.setdefault(charIndex, dict())
                recoveringMacros = self.recoveringMacros.setdefault(charIndex, set())
                try:
                    for macro in hotkeyDict[hotkey]:
                        try:
                            del runningMacros[macro]
                            recoveringMacros.add(macro)
                        except KeyError:
                            continue

                except KeyError:
                    continue


def checkCommandAvailability(charInfo, command):
    if not command:
        return True
    if charInfo.DEAD:
        return False
    if command[0] == '/':
        args = command[1:].upper().split(' ', 1)
        if len(args) > 1:
            command, arg = args
            arg = arg.lstrip()
        else:
            command, arg = args[0], ''
        if command == 'SKILL':
            if charInfo.SKILLREUSE.has_key(arg):
                return False
            return True
        if command == 'CAST':
            if charInfo.RAPIDMOBINFO.CASTING:
                return False
            for spellSlot, charSpell in charInfo.SPELLS.iteritems():
                if charSpell.SPELLINFO.BASENAME.upper() == arg:
                    if charSpell.RECASTTIMER:
                        return False
                    break

            return True
        if command == 'USEITEM':
            for itemSlot, itemInfo in charInfo.ITEMS.iteritems():
                if itemSlot == RPG_SLOT_CURSOR:
                    continue
                if itemInfo.NAME.upper() == arg:
                    if not itemInfo.REUSETIMER:
                        return True

            return False
        if command == 'RANGEDATTACK':
            if charInfo.RAPIDMOBINFO.RANGEDREUSE > 0:
                return False
            return True
    return True


MACROMASTER = MacroMaster()

def PyExec():
    global CURSORMACRO
    CURSORMACRO = CursorMacro()
    TGEExport(MACROMASTER.onHotKey, 'Py', 'OnHotKey', 'desc', 2, 2)
    TGEExport(MACROMASTER.onSetMacroPage, 'Py', 'OnSetMacroPage', 'desc', 2, 2)
    TGEExport(MACROMASTER.onMacroButtonClick, 'Py', 'OnMacroButtonClick', 'desc', 3, 3)
    TGEExport(MACROMASTER.onMacroButtonClickAlt, 'Py', 'OnMacroButtonClickAlt', 'desc', 3, 3)