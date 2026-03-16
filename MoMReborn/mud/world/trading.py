# Embedded file name: mud\world\trading.pyo
from mud.world.shared.playdata import TradeInfo
from defines import *

class Trade:

    def __init__(self, p0, p1):
        self.traded = False
        p0.trade = p1.trade = self
        self.p0 = p0
        self.p0Accepted = False
        self.p0Items = {}
        for item in p0.curChar.items:
            if RPG_SLOT_TRADE_BEGIN <= item.slot < RPG_SLOT_TRADE_END:
                self.p0Items[item.slot - RPG_SLOT_TRADE_BEGIN] = item

        self.p0Tin = 0L
        self.p1 = p1
        self.p1Accepted = False
        self.p1Items = {}
        for item in p1.curChar.items:
            if RPG_SLOT_TRADE_BEGIN <= item.slot < RPG_SLOT_TRADE_END:
                self.p1Items[item.slot - RPG_SLOT_TRADE_BEGIN] = item

        self.p1Tin = 0L
        self.tradeInfo = TradeInfo(self)
        p0.mind.callRemote('openTradeWindow', self.tradeInfo)
        p1.mind.callRemote('openTradeWindow', self.tradeInfo)

    def end(self):
        p0 = self.p0
        p1 = self.p1
        if self.traded:
            p0.sendGameText(RPG_MSG_GAME_GAINED, 'The trade has been completed.\\n')
            p1.sendGameText(RPG_MSG_GAME_GAINED, 'The trade has been completed.\\n')
        else:
            p0.sendGameText(RPG_MSG_GAME_DENIED, 'The trade has been canceled.\\n')
            p1.sendGameText(RPG_MSG_GAME_DENIED, 'The trade has been canceled.\\n')
        p0.trade = p1.trade = None
        if not p0.loggingOut:
            p0.mind.callRemote('closeTradeWindow')
        if not p1.loggingOut:
            p1.mind.callRemote('closeTradeWindow')
        p0.cinfoDirty = True
        p1.cinfoDirty = True
        return

    def submitMoney(self, player, money):
        if self.p0Accepted or self.p1Accepted:
            if self.p0 == player:
                return self.p0Tin
            else:
                return self.p1Tin
        if not player.checkMoney(money):
            print 'WARNING: trading.py submitMoney Player with insufficient funds!'
            money = 0L
        if self.p0 == player:
            self.p0Tin = money
        else:
            self.p1Tin = money
        self.refresh()
        return money

    def cancel(self):
        self.p0.restoreTradeItems()
        self.p1.restoreTradeItems()
        self.end()

    def accept(self, player):
        if self.p0 == player:
            self.p0Accepted = True
        if self.p1 == player:
            self.p1Accepted = True
        if self.p0Accepted and self.p1Accepted:
            p0Items = self.p0Items.values()
            p1Items = self.p1Items.values()
            p1ItemsCopy = p1Items[:]
            p0FreeSlots = 0
            p1FreeSlots = 0
            p0CheckStack = {}
            p1CheckStack = {}
            for item in p0Items:
                if RPG_SLOT_CARRY_END > item.slot >= RPG_SLOT_CARRY_BEGIN:
                    p0FreeSlots += 1
                if item.itemProto.stackMax > item.stackCount > 1:
                    if not p0CheckStack.has_key(item.name):
                        p0CheckStack[item.name] = []
                    p0CheckStack[item.name].append([item, item.stackCount])

            for item in p1Items:
                if RPG_SLOT_CARRY_END > item.slot >= RPG_SLOT_CARRY_BEGIN:
                    p1FreeSlots += 1
                if item.itemProto.stackMax > item.stackCount > 1:
                    if not p1CheckStack.has_key(item.name):
                        p1CheckStack[item.name] = []
                    p1CheckStack[item.name].append([item, item.stackCount])

            p0UpdatedStacks = {}
            p1Erase = []
            for char in self.p0.party.members:
                freeSlots = range(RPG_SLOT_CARRY_BEGIN, RPG_SLOT_CARRY_END)
                for item in char.items:
                    stackMax = item.itemProto.stackMax
                    if stackMax > 1 and item not in p0Items and item.name in p1CheckStack:
                        diff = stackMax - item.stackCount
                        for stackItem in p1CheckStack[item.name][:]:
                            if diff <= 0:
                                break
                            if diff >= stackItem[1]:
                                if item in p0UpdatedStacks:
                                    p0UpdatedStacks[item] += stackItem[1]
                                else:
                                    p0UpdatedStacks[item] = item.stackCount + stackItem[1]
                                diff -= stackItem[1]
                                p1Items.remove(stackItem[0])
                                p1Erase.append(stackItem[0])
                                p1CheckStack[item.name].remove(stackItem)
                                if not len(p1CheckStack[item.name]):
                                    del p1CheckStack[item.name]
                                    break
                            else:
                                p0UpdatedStacks[item] = stackMax
                                stackItem[1] -= diff
                                p0UpdatedStacks[stackItem[0]] = stackItem[1]
                                break

                    try:
                        freeSlots.remove(item.slot)
                    except:
                        continue

                p0FreeSlots += len(freeSlots)

            p1UpdatedStacks = {}
            p0Erase = []
            for char in self.p1.party.members:
                freeSlots = range(RPG_SLOT_CARRY_BEGIN, RPG_SLOT_CARRY_END)
                for item in char.items:
                    stackMax = item.itemProto.stackMax
                    if stackMax > 1 and item not in p1ItemsCopy and item.name in p0CheckStack:
                        diff = stackMax - item.stackCount
                        for stackItem in p0CheckStack[item.name][:]:
                            if diff <= 0:
                                break
                            if diff >= stackItem[1]:
                                if item in p1UpdatedStacks:
                                    p1UpdatedStacks[item] += stackItem[1]
                                else:
                                    p1UpdatedStacks[item] = item.stackCount + stackItem[1]
                                diff -= stackItem[1]
                                p0Items.remove(stackItem[0])
                                p0Erase.append(stackItem[0])
                                p0CheckStack[item.name].remove(stackItem)
                                if not len(p0CheckStack[item.name]):
                                    del p0CheckStack[item.name]
                                    break
                            else:
                                p1UpdatedStacks[item] = stackMax
                                stackItem[1] -= diff
                                p1UpdatedStacks[stackItem[0]] = stackItem[1]
                                break

                    try:
                        freeSlots.remove(item.slot)
                    except:
                        continue

                p1FreeSlots += len(freeSlots)

            p0Needed = len(p1Items) - p0FreeSlots
            p1Needed = len(p0Items) - p1FreeSlots
            if p0Needed > 0:
                self.p0.sendGameText(RPG_MSG_GAME_DENIED, 'You need %i more free carry slot to complete this trade.\\n' % p0Needed)
                self.p1.sendGameText(RPG_MSG_GAME_DENIED, "%s doesn't have enough free slots to complete this trade.\\n" % self.p0.charName)
            if p1Needed > 0:
                self.p1.sendGameText(RPG_MSG_GAME_DENIED, 'You need %i more free carry slot to complete this trade.\\n' % p1Needed)
                self.p0.sendGameText(RPG_MSG_GAME_DENIED, "%s doesn't have enough free slots to complete this trade.\\n" % self.p1.charName)
            if p0Needed > 0 or p1Needed > 0:
                self.p0Accepted = False
                self.p1Accepted = False
                self.refresh({'P0ACCEPTED': False,
                 'P1ACCEPTED': False})
                return
            for item in p0Items:
                item.setCharacter(None)
                self.p1.giveItemInstance(item)

            for item in p1Items:
                item.setCharacter(None)
                self.p0.giveItemInstance(item)

            for item, amount in p0UpdatedStacks.iteritems():
                item.stackCount = amount
                item.itemInfo.refreshDict({'STACKCOUNT': item.stackCount})

            for item, amount in p1UpdatedStacks.iteritems():
                item.stackCount = amount
                item.itemInfo.refreshDict({'STACKCOUNT': item.stackCount})

            for item in p0Erase:
                self.p0.takeItem(item)

            for item in p1Erase:
                self.p1.takeItem(item)

            self.p0.takeMoney(self.p0Tin)
            self.p1.takeMoney(self.p1Tin)
            self.p0.giveMoney(self.p1Tin)
            self.p1.giveMoney(self.p0Tin)
            self.traded = True
            self.end()
        else:
            self.refresh()
        return

    def refresh(self, dict = None):
        if dict:
            self.tradeInfo.refreshDict(dict)
        else:
            self.tradeInfo.refresh()
        try:
            self.p0.cinfoDirty = True
            self.p1.cinfoDirty = True
        except:
            pass