# Embedded file name: mud\world\dialog.pyo
from mud.common.persistent import Persistent
from mud.world.core import CollapseMoney, CoreSettings, GenMoneyText
from mud.world.defines import *
from mud.gamesettings import *
from collections import defaultdict
from sqlobject import *
import traceback

class JournalEntry(Persistent):
    topic = StringCol(default='')
    entry = StringCol(default='')
    text = StringCol(default='')


class DialogTrigger():

    def __init__(self, tinfo):
        selection = list(Dialog.selectBy(name=tinfo.dialogTrigger))
        if len(selection) != 1:
            traceback.print_stack()
            print 'AssertionError: dialog selection returned multiple items for dialog trigger %s!' % tinfo.dialogTrigger
            return
        else:
            self.dialog = selection[0]
            self.range = tinfo.dialogRange
            self.position = tinfo.position
            self.interacting = None
            return


class DialogGiveItem(Persistent):
    dialogAction = ForeignKey('DialogAction')
    itemProto = ForeignKey('ItemProto')
    count = IntCol(default=1)


class DialogTakeItem(Persistent):
    dialogAction = ForeignKey('DialogAction')
    itemProto = ForeignKey('ItemProto')
    count = IntCol(default=1)


class DialogFaction(Persistent):
    dialogAction = ForeignKey('DialogAction')
    faction = ForeignKey('Faction')
    amount = IntCol(default=1)


class DialogTrainSkill(Persistent):
    dialogAction = ForeignKey('DialogAction')
    skill = StringCol(default='')


class DialogCheckItem(Persistent):
    dialogAction = ForeignKey('DialogAction')
    itemProto = ForeignKey('ItemProto')
    count = IntCol(default=1)


class DialogCheckMinFaction(Persistent):
    dialogAction = ForeignKey('DialogAction')
    faction = ForeignKey('Faction')
    amount = IntCol(default=0)


class DialogCheckMaxFaction(Persistent):
    dialogAction = ForeignKey('DialogAction')
    faction = ForeignKey('Faction')
    amount = IntCol(default=0)


class DialogCheckSkill(Persistent):
    dialogAction = ForeignKey('DialogAction')
    skillName = StringCol(default='')
    skillLevel = IntCol(default=0)


class DialogAction(Persistent):
    lines = RelatedJoin('DialogLine')
    dialog = ForeignKey('Dialog')
    castSpellOnMyself = ForeignKey('SpellProto', default=None)
    castSpellOnOther = ForeignKey('SpellProto', default=None)
    trainClass = StringCol(default='')
    trainSkills = MultipleJoin('DialogTrainSkill')
    teleportZone = StringCol(default='')
    teleportTransform = StringCol(default='')
    attack = BoolCol(default=False)
    endInteraction = BoolCol(default=False)
    checkItems = MultipleJoin('DialogCheckItem')
    checkSkills = MultipleJoin('DialogCheckSkill')
    checkMinFactions = MultipleJoin('DialogCheckMinFaction')
    checkMaxFactions = MultipleJoin('DialogCheckMaxFaction')
    giveItems = MultipleJoin('DialogGiveItem')
    giveXP = IntCol(default=0)
    giveTin = IntCol(default=0)
    givePresence = IntCol(default=0)
    takeItems = MultipleJoin('DialogTakeItem')
    takeXP = IntCol(default=0)
    takeTin = IntCol(default=0L)
    factions = MultipleJoin('DialogFaction')
    giveMonster = StringCol(default='')
    playSound = StringCol(default='')
    despawn = IntCol(default=0)
    respawn = ForeignKey('Spawn', default=None)
    triggerSpawnGroup = StringCol(default='')
    healthModPercent = FloatCol(default=1)
    triggerBattle = StringCol(default='')
    resurrect = BoolCol(default=False)
    resurrectXP = FloatCol(default=0)
    journalEntryID = IntCol(default=0)
    gameMessageType = IntCol(default=RPG_MSG_GAME_NPC_SPEECH)
    gameMessageText = StringCol(default='')

    def checkTakeMoney(self, player):
        enough = player.checkMoney(self.takeTin)
        if not enough:
            player.sendGameText(RPG_MSG_GAME_DENIED, "You don't have enough money.\\n")
        return enough

    def checkResurrect(self, player):
        if not self.resurrect:
            return True
        for m in player.party.members:
            if m.dead:
                return True

        return False

    def checkTriggerSpawnGroup(self, player):
        if not self.triggerSpawnGroup:
            return True
        z = player.zone
        for sp in z.spawnpoints:
            if not sp.spawngroup:
                if LOCALTEST:
                    print 'WARNING: None Spawngroup in Dialog.checkTriggerSpawnGroup'
                continue
            if sp.spawngroup.targetName == self.triggerSpawnGroup:
                if len(sp.activeMobs):
                    return False

        return True

    def checkTriggerBattle(self, player):
        if not self.triggerBattle:
            return True
        for battle in player.zone.battles:
            if battle.name == self.triggerBattle:
                player.sendGameText(RPG_MSG_GAME_DENIED, 'The battle is already raging!\\n')
                return False

        return True

    def checkGiveItems(self, player):
        numItems = 0
        for gitem in self.giveItems:
            if gitem.count <= 1:
                numItems += 1
            else:
                numItems += gitem.count

        if numItems <= 0:
            return True
        fc = player.getFreeCarrySlots()
        if numItems > fc:
            player.sendGameText(RPG_MSG_GAME_DENIED, 'You need %i more free carry slots.\\n' % (numItems - fc))
            return False
        return True

    def checkCheckItems(self, player, silent = False):
        itemDict = defaultdict(int)
        for checkItem in self.checkItems:
            if checkItem.count > 0:
                itemDict[checkItem.itemProto] += checkItem.count

        return player.checkItems(itemDict, silent)

    def checkTakeItems(self, player, silent = False):
        itemDict = defaultdict(int)
        for takeItem in self.takeItems:
            if takeItem.count > 0:
                itemDict[takeItem.itemProto] += takeItem.count

        return player.checkItems(itemDict, silent)

    def checkCheckSkills(self, player, silent = False):
        skillLevels = player.curChar.mob.skillLevels
        for checkSkill in self.checkSkills:
            if not skillLevels.has_key(checkSkill.skillName):
                if not silent:
                    player.sendGameText(RPG_MSG_GAME_DENIED, "%s doesn't know the %s skill.\\n" % (player.curChar.name, checkSkill.skillName))
                return False
            if checkSkill.skillLevel > skillLevels[checkSkill.skillName]:
                if not silent:
                    player.sendGameText(RPG_MSG_GAME_DENIED, "%s doesn't have enough skill levels in %s (%i needed).\\n" % (player.curChar.name, checkSkill.skillName, checkSkill.skillLevel))
                return False

        return True

    def checkTrainSkill(self, player):
        trainSkillList = list(self.trainSkills)
        if not len(trainSkillList):
            return True
        char = player.curChar
        spawn = char.spawn
        for ts in reversed(trainSkillList):
            if ts.skill in char.mob.skillLevels:
                player.sendGameText(RPG_MSG_GAME_DENIED, '%s already knows the %s skill.\\n' % (char.name, ts.skill))
                trainSkillList.remove(ts)

        if not len(trainSkillList):
            return False
        pneeded = {}
        sneeded = {}
        tneeded = {}
        noClassSkill = set()
        for ts in reversed(trainSkillList):
            noClassSkill.add(ts.skill)
            for skill in spawn.pclass.classSkills:
                if skill.skillname != ts.skill:
                    continue
                noClassSkill.discard(ts.skill)
                if skill.levelGained > spawn.plevel:
                    pneeded[skill.skillname] = skill.levelGained
                    break
                trainSkillList.remove(ts)
                break
            else:
                if spawn.sclass:
                    for skill in spawn.sclass.classSkills:
                        if skill.skillname != ts.skill:
                            continue
                        noClassSkill.discard(ts.skill)
                        if skill.levelGained > spawn.slevel:
                            if not pneeded.has_key(skill.skillname):
                                sneeded[skill.skillname] = skill.levelGained
                            break
                        try:
                            del pneeded[skill.skillname]
                        except KeyError:
                            pass

                        trainSkillList.remove(ts)
                        break
                    else:
                        if spawn.tclass:
                            for skill in spawn.tclass.classSkills:
                                if skill.skillname != ts.skill:
                                    continue
                                noClassSkill.discard(ts.skill)
                                if skill.levelGained > spawn.tlevel:
                                    if not pneeded.has_key(skill.skillname) and not sneeded.has_key(skill.skillname):
                                        tneeded[skill.skillname] = skill.levelGained
                                    break
                                try:
                                    del pneeded[skill.skillname]
                                except KeyError:
                                    try:
                                        del sneeded[skill.skillname]
                                    except KeyError:
                                        pass

                                trainSkillList.remove(ts)
                                break

        if not len(trainSkillList):
            return True
        for sk in reversed(trainSkillList):
            if sk.skill in noClassSkill:
                trainSkillList.remove(sk)

        if len(trainSkillList):
            stext = []
            if pneeded:
                stext.append('%s ' % spawn.pclassInternal)
                stext.append(', '.join(('(%s, %i)' % (sname, slevel) for sname, slevel in pneeded.iteritems())))
            if sneeded:
                if len(stext):
                    stext.append('; ')
                stext.append('%s ' % spawn.sclassInternal)
                stext.append(', '.join(('(%s, %i)' % (sname, slevel) for sname, slevel in sneeded.iteritems())))
            if tneeded:
                if len(stext):
                    stext.append('; ')
                stext.append('%s ' % spawn.tclassInternal)
                stext.append(', '.join(('(%s, %i)' % (sname, slevel) for sname, slevel in tneeded.iteritems())))
            stext = ''.join(stext)
            if len(trainSkillList) == 1:
                player.sendGameText(RPG_MSG_GAME_DENIED, "%s isn't experienced enough to learn this skill.\\n< %s >\\n" % (char.name, stext))
            else:
                player.sendGameText(RPG_MSG_GAME_DENIED, "%s isn't experienced enough to learn these skills.\\n< %s >\\n" % (char.name, stext))
        if len(noClassSkill):
            if len(noClassSkill) == 1:
                player.sendGameText(RPG_MSG_GAME_DENIED, "The %s skill is not in %s's class skills and cannot be learned.\\n" % (noClassSkill.pop(), char.name))
            else:
                noClassText = ', '.join(noClassSkill)
                player.sendGameText(RPG_MSG_GAME_DENIED, "The %s skills are not in %s's class skills and cannot be learned.\\n" % (noClassText, char.name))
        return False

    def doCheckMinFactions(self, player):
        minfactions = list(self.checkMinFactions)
        if not len(minfactions):
            return True
        char = player.curChar
        for cf in minfactions:
            for pf in char.characterFactions:
                if cf.faction != pf.faction:
                    continue
                if cf.amount > pf.points:
                    player.sendGameText(RPG_MSG_GAME_DENIED, '%s must be better liked by %s.\\n' % (char.name, cf.faction.name))
                    return False
                break
            else:
                if cf.amount > 0:
                    player.sendGameText(RPG_MSG_GAME_DENIED, '%s must be better liked by %s.\\n' % (char.name, cf.faction.name))
                    return False

        return True

    def doCheckMaxFactions(self, player):
        maxfactions = list(self.checkMaxFactions)
        if not len(maxfactions):
            return True
        char = player.curChar
        for cf in maxfactions:
            for pf in char.characterFactions:
                if cf.faction != pf.faction:
                    continue
                if cf.amount < pf.points:
                    player.sendGameText(RPG_MSG_GAME_DENIED, '%s must be be less liked by %s.\\n' % (char.name, cf.faction.name))
                    return False
                break
            else:
                if cf.amount < 0:
                    player.sendGameText(RPG_MSG_GAME_DENIED, '%s must be less liked by %s.\\n' % (char.name, cf.faction.name))
                    return False

        return True

    def checkTrainClass(self, player):
        if not self.trainClass:
            return True
        char = player.curChar
        spawn = char.spawn
        try:
            if self.trainClass not in RPG_RACE_CLASSES[spawn.race]:
                player.sendGameText(RPG_MSG_GAME_DENIED, '%ss cannot train in the %s class.\\n' % (spawn.race, self.trainClass))
                return False
        except KeyError:
            pass

        if player.realm == RPG_REALM_DARKNESS:
            if self.trainClass not in RPG_REALM_CLASSES[RPG_REALM_DARKNESS]:
                player.sendGameText(RPG_MSG_GAME_DENIED, 'The Minions of Darkness cannot train in the %s class.\\n' % self.trainClass)
                return False
        elif player.realm == RPG_REALM_LIGHT:
            if self.trainClass not in RPG_REALM_CLASSES[RPG_REALM_LIGHT]:
                player.sendGameText(RPG_MSG_GAME_DENIED, 'The Fellowship of Light cannot train in the %s class.\\n' % self.trainClass)
                return False
        if spawn.pclassInternal == self.trainClass or spawn.sclassInternal == self.trainClass or spawn.tclassInternal == self.trainClass:
            player.sendGameText(RPG_MSG_GAME_DENIED, '%s is already a member of this class.  You can gain a secondary class at level %i and a tertiary one at level %i.\\n' % (char.name, RPG_MULTICLASS_SECONDARY_LEVEL_REQUIREMENT, RPG_MULTICLASS_TERTIARY_LEVEL_REQUIREMENT))
            return
        if not spawn.slevel:
            if spawn.plevel < RPG_MULTICLASS_SECONDARY_LEVEL_REQUIREMENT:
                player.sendGameText(RPG_MSG_GAME_DENIED, '%s must be level %i before selecting a secondary class.\\n' % (char.name, RPG_MULTICLASS_SECONDARY_LEVEL_REQUIREMENT))
                return False
        else:
            if not player.premium:
                player.sendGameText(RPG_MSG_GAME_DENIED, 'Premium Account is required to add a tertiary multiclass.\\nPlease see www.prairiegames.com for more information.\\n\\n')
                return False
            if not spawn.tlevel and spawn.plevel < RPG_MULTICLASS_TERTIARY_LEVEL_REQUIREMENT:
                player.sendGameText(RPG_MSG_GAME_DENIED, '%s must be level %i before selecting a tertiary class.\\n' % (char.name, RPG_MULTICLASS_TERTIARY_LEVEL_REQUIREMENT))
                return False
        if spawn.slevel and spawn.tlevel:
            player.sendGameText(RPG_MSG_GAME_DENIED, '%s can learn no more classes.\\n' % char.name)
            return False
        return True

    def check(self, player):
        if not self.checkCheckItems(player):
            return False
        if not self.checkTakeItems(player):
            return False
        if not self.checkCheckSkills(player):
            return False
        if not self.checkGiveItems(player):
            return False
        if not self.checkTrainClass(player):
            return False
        if not self.checkTrainSkill(player):
            return False
        if not self.checkTriggerSpawnGroup(player):
            return False
        if not self.checkResurrect(player):
            return False
        if not self.checkTakeMoney(player):
            return False
        if not self.doCheckMinFactions(player):
            return False
        if not self.doCheckMaxFactions(player):
            return False
        if not self.checkTriggerBattle(player):
            return False
        return True

    def doResurrect(self, player):
        if not self.resurrect:
            return
        for c in player.party.members:
            if c.dead:
                c.resurrect(self.resurrectXP)

    def doTeleport(self, player):
        if not self.teleportZone or not self.teleportTransform:
            return False
        czone = player.zone.zone
        from mud.world.zone import TempZoneLink, Zone
        z = Zone.byName(self.teleportZone)
        self.doTakeMoney(player)
        player.endInteraction()
        if czone == z:
            player.zone.respawnPlayer(player, self.teleportTransform)
        else:
            zlink = TempZoneLink(self.teleportZone, self.teleportTransform)
            player.world.onZoneTrigger(player, zlink)
        return True

    def doTrainClass(self, player):
        if not self.trainClass:
            return
        char = player.curChar
        char.trainClass(self.trainClass)
        player.sendGameText(RPG_MSG_GAME_GAINED, ' %s has learned basic knowledge of the %s class!!!\\n' % (char.name, self.trainClass))

    def doGiveItems(self, player):
        c = player.curChar
        itemProtos = []
        counts = []
        for gitem in self.giveItems:
            itemProtos.append(gitem.itemProto)
            counts.append(gitem.count)

        items = []
        for proto, count in zip(itemProtos, counts):
            for c in xrange(0, count):
                item = proto.createInstance()
                if proto.name == 'Guild Charter':
                    item.descOverride = 'This document is a guild charter.  You need 3 signed member charters to form a new guild.\\n\\nThis charter has been signed by %s' % player.publicName
                    item.itemInfo.reset()
                items.append(item)

        for item in items:
            player.giveItemInstance(item)
            if not item.character:
                traceback.print_stack()
                print "AssertionError: player didn't receive item %s!" % item.name
                continue
            player.sendGameText(RPG_MSG_GAME_GAINED, '%s has gained %s!\\n' % (item.character.name, item.name))

    def doTakeItems(self, player):
        if len(self.takeItems):
            itemProtoCounts = defaultdict(int)
            for takeItem in self.takeItems:
                if takeItem.count > 0:
                    itemProtoCounts[takeItem.itemProto] += takeItem.count

            player.takeItems(itemProtoCounts)

    def doAttack(self, player):
        if self.attack:
            mob = player.interacting
            player.endInteraction()
            for c in player.party.members:
                mob.addAggro(c.mob, 10)

            return True
        return False

    def doTriggerSpawnGroup(self, player):
        if not self.triggerSpawnGroup:
            return
        if self.healthModPercent < 0.01:
            self.healthModPercent = 0.01
        elif self.healthModPercent > 1.0:
            self.healthModPercent = 1.0
        z = player.zone
        for sp in z.spawnpoints:
            if not sp.spawngroup:
                continue
            if sp.spawngroup.targetName == self.triggerSpawnGroup:
                mob = sp.triggeredSpawn()
                if mob:
                    mob.preventZombieRegen = True
                    mob.initMob()
                    mob.health = int(self.healthModPercent * float(mob.maxHealth))

    def doTriggerBattle(self, player):
        if not self.triggerBattle:
            return
        from mud.world.battle import Battle, BattleProto
        try:
            bproto = BattleProto.byName(self.triggerBattle)
        except:
            print 'WARNING: Unknown Battle %s' % self.triggerBattle
            return

        Battle(player.zone, bproto)

    def doRespawn(self, player):
        if not self.respawn:
            return False
        from mud.world.mob import Mob
        if isinstance(player.interacting, Mob) and player.interacting.spawnpoint:
            player.interacting.spawnpoint.spawnMobByName(self.respawn.name)
        player.endInteraction()
        return True

    def doFactions(self, player):
        for f in self.factions:
            player.alliance.rewardFaction(player, f.faction, f.amount)

    def doGiveXP(self, player):
        if self.giveXP > 0:
            player.alliance.rewardXP(player, self.giveXP)

    def doGivePresence(self, player):
        if not self.givePresence:
            return
        c = player.curChar
        preBase = c.spawn.preBase
        adjustedReward = self.givePresence
        player.sendGameText(RPG_MSG_GAME_LEVELGAINED, '%s has gained %i presence!!!\\n' % (c.name, adjustedReward))
        if preBase + adjustedReward > RPG_MAX_PRESENCE:
            adjustedReward = RPG_MAX_PRESENCE - preBase
            player.sendGameText(RPG_MSG_GAME_DENIED, "The presence %s gained couldn't be fully attributed.\\n" % c.name)
        c.spawn.preBase = preBase + adjustedReward
        c.mob.preBase += adjustedReward
        c.mob.pre += adjustedReward
        c.mob.derivedDirty = True
        player.mind.callRemote('playSound', 'sfx/Pickup_Magic33.ogg')

    def doGiveMonster(self, player):
        if not self.giveMonster:
            return
        from mud.world.spawn import Spawn
        try:
            s = Spawn.byName(self.giveMonster)
        except:
            print 'WARNING: GIVE MONSTER %s has no spawn!!!!' % self.giveMonster
            return

        for ms in player.monsterSpawns:
            if ms.spawn == self.giveMonster:
                player.sendGameText(RPG_MSG_GAME_DENIED, 'You already have the %s monster template.\\n' % self.giveMonster)
                return

        from mud.world.player import PlayerMonsterSpawn
        PlayerMonsterSpawn(player=player, spawn=self.giveMonster)
        player.mind.callRemote('playSound', 'sfx/EvilMonster_TauntGrowl.ogg')
        player.sendGameText(RPG_MSG_GAME_LEVELGAINED, 'You have unlocked the %s monster template!!!\\n' % self.giveMonster)

    def doTakeMoney(self, player):
        if self.takeTin:
            player.sendGameText(RPG_MSG_GAME_LOST, 'You lose %s.\\n' % GenMoneyText(self.takeTin))
            player.takeMoney(self.takeTin)

    def doTrainSkill(self, player):
        trainSkillList = list(self.trainSkills)
        if not len(trainSkillList):
            return
        char = player.curChar
        for ts in trainSkillList[:]:
            if ts.skill in char.mob.skillLevels:
                trainSkillList.remove(ts)

        if not len(trainSkillList):
            return
        from character import CharacterSkill
        stext = ''
        for train in trainSkillList:
            CharacterSkill(character=char, level=1, skillname=train.skill)
            stext += '%s, ' % train.skill

        char.mob.updateClassStats()
        stext = stext[:-2]
        if len(trainSkillList) == 1:
            player.sendGameText(RPG_MSG_GAME_GAINED, '%s has learned the %s skill!!!\\n' % (char.name, stext))
        else:
            player.sendGameText(RPG_MSG_GAME_GAINED, '%s has learned the %s skills!!!\\n' % (char.name, stext))

    def doJournal(self, player):
        if self.journalEntryID:
            player.mind.callRemote('addJournalEntry', self.journalEntryID)

    def doGameMessage(self, player):
        if self.gameMessageText:
            player.sendGameText(self.gameMessageType, '%s\\n' % self.gameMessageText)

    def do(self, player):
        self.doTakeItems(player)
        end = self.doAttack(player)
        self.doTrainClass(player)
        self.doTrainSkill(player)
        self.doGiveItems(player)
        teleported = self.doTeleport(player)
        self.doTriggerSpawnGroup(player)
        end |= self.doRespawn(player)
        self.doGiveXP(player)
        self.doFactions(player)
        self.doResurrect(player)
        if not teleported:
            self.doTakeMoney(player)
        self.doJournal(player)
        self.doTriggerBattle(player)
        self.doGameMessage(player)
        if teleported:
            end = True
        else:
            if self.endInteraction and not self.despawn:
                player.endInteraction()
                end = True
            tin, copper, silver, gold, platinum = CollapseMoney(self.giveTin)
            if tin:
                player.sendGameText(RPG_MSG_GAME_GAINED, 'Gained %i tin pieces.\\n' % tin)
                player.tin += tin
            if copper:
                player.sendGameText(RPG_MSG_GAME_GAINED, 'Gained %i copper pieces.\\n' % copper)
                player.copper += copper
            if silver:
                player.sendGameText(RPG_MSG_GAME_GAINED, 'Gained %i silver pieces.\\n' % silver)
                player.silver += silver
            if gold:
                player.sendGameText(RPG_MSG_GAME_GAINED, 'Gained %i gold pieces.\\n' % gold)
                player.gold += gold
            if platinum:
                player.sendGameText(RPG_MSG_GAME_GAINED, 'Gained %i platinum pieces.\\n' % platinum)
                player.platinum += platinum
            player.collapseMoney()
        if self.playSound:
            player.mind.callRemote('playSound', self.playSound)
        if self.despawn:
            from mud.world.mob import Mob
            if isinstance(player.interacting, Mob):
                player.zone.removeMob(player.interacting, self.despawn)
            end = True
        self.doGiveMonster(player)
        self.doGivePresence(player)
        return end


class DialogRequireClass(Persistent):
    dialogRequirement = ForeignKey('DialogRequirement')
    positiveCheck = BoolCol(default=True)
    className = StringCol(default='')
    classLevel = IntCol(default=0)

    def check(self, spawn):
        if not self.className or not spawn:
            return True
        elif self.positiveCheck:
            if self.className == spawn.pclassInternal:
                if spawn.plevel >= self.classLevel:
                    return True
            elif self.className == spawn.sclassInternal:
                if spawn.slevel >= self.classLevel:
                    return True
            elif self.className == spawn.tclassInternal:
                if spawn.tlevel >= self.classLevel:
                    return True
            return False
        else:
            if not self.classLevel:
                if spawn.pclassInternal != self.className and spawn.sclassInternal != self.className and spawn.tclassInternal != self.className:
                    return True
            elif self.className == spawn.pclassInternal:
                if spawn.plevel < self.classLevel:
                    return True
            elif self.className == spawn.sclassInternal:
                if spawn.slevel < self.classLevel:
                    return True
            elif self.className == spawn.tclassInternal:
                if spawn.tlevel < self.classLevel:
                    return True
            return False

    def getFailLine(self, positive = True):
        if not self.className:
            return ''
        if not self.positiveCheck ^ positive:
            if self.classLevel:
                return 'a level %i %s or higher' % (self.classLevel, self.className)
            else:
                return 'a %s' % self.className
        else:
            if self.classLevel:
                return 'a level %i %s or lower' % (self.classLevel - 1, self.className)
            return 'no %s' % self.className


class DialogRequireRace(Persistent):
    dialogRequirement = ForeignKey('DialogRequirement')
    positiveCheck = BoolCol(default=True)
    raceName = StringCol(default='')

    def check(self, spawn):
        if not self.raceName or not spawn:
            return True
        if self.positiveCheck:
            if self.raceName == spawn.race:
                return True
        elif self.raceName != spawn.race:
            return True
        return False

    def getFailLine(self, positive = True):
        if not self.raceName:
            return ''
        elif not self.positiveCheck ^ positive:
            return 'a %s' % self.raceName
        else:
            return 'no %s' % self.raceName


class DialogRequireRealm(Persistent):
    dialogRequirement = ForeignKey('DialogRequirement')
    positiveCheck = BoolCol(default=True)
    realm = IntCol(default=-1)
    realmLevel = IntCol(default=0)

    def check(self, spawn):
        if self.realm == -1 or not spawn:
            return True
        if self.positiveCheck:
            if self.realm == spawn.realm:
                if spawn.plevel >= self.realmLevel:
                    return True
        elif not self.realmLevel:
            if self.realm != spawn.realm:
                return True
        elif self.realm == spawn.realm:
            if spawn.plevel < self.realmLevel:
                return True
        return False

    def getFailLine(self, positive = True):
        if self.realm == -1:
            return ''
        if not self.positiveCheck ^ positive:
            if self.realm == RPG_REALM_LIGHT:
                realmText = 'member of the Fellowship of Light'
            elif self.realm == RPG_REALM_DARKNESS:
                realmText = 'member of the Minions of Darkness'
            else:
                realmText = 'Monster'
            if self.realmLevel:
                return 'a level %i %s or higher' % (self.realmLevel, realmText)
            else:
                return 'a %s' % realmText
        elif self.realmLevel:
            if self.realm == RPG_REALM_LIGHT:
                return 'a level %i member of the Fellowship of Light or lower' % (self.realmLevel - 1)
            elif self.realm == RPG_REALM_DARKNESS:
                return 'a level %i member of the Minions of Darkness or lower' % (self.realmLevel - 1)
            else:
                return 'a level %i Monster or lower' % self.realmLevel
        else:
            if self.realm == RPG_REALM_LIGHT:
                return 'a member of the Minions of Darkness or a Monster'
            if self.realm == RPG_REALM_DARKNESS:
                return 'a member of the Fellowship of Light or a Monster'
            return 'a member of the Fellowship of Light or the Minions of Darkness'


class DialogRequireSkill(Persistent):
    dialogRequirement = ForeignKey('DialogRequirement')
    positiveCheck = BoolCol(default=True)
    skillName = StringCol(default='')
    skillLevel = IntCol(default=0)

    def check(self, mob):
        if not self.skillName or not mob:
            return True
        if self.positiveCheck:
            if mob.skillLevels.has_key(self.skillName) and mob.skillLevels[self.skillName] >= self.skillLevel:
                return True
        else:
            if self.skillLevel and mob.skillLevels.has_key(self.skillName) and mob.skillLevels[self.skillName] < self.skillLevel:
                return True
            if not mob.skillLevels.has_key(self.skillName):
                return True
        return False

    def getFailLine(self, positive = True):
        if not self.skillName:
            return ''
        if not self.positiveCheck ^ positive:
            if self.skillLevel:
                return 'know the %s skill at skill level %i or higher' % (self.skillName, self.skillLevel)
            else:
                return 'know the %s skill' % self.skillName
        else:
            if self.skillLevel:
                return 'know the %s skill at skill level %i or lower' % (self.skillName, self.skillLevel)
            return 'not know the %s skill' % self.skillName


class DialogRequireItem(Persistent):
    dialogRequirement = ForeignKey('DialogRequirement')
    positiveCheck = BoolCol(default=True)
    itemProto = ForeignKey('ItemProto', default=None)
    count = IntCol(default=1)

    def getFailLine(self, positive = True):
        if not self.itemProto:
            return ''
        if not self.positiveCheck ^ positive:
            if self.count > 1:
                return '%i %s or more' % (self.count, self.itemProto.name)
            else:
                return 'a %s' % self.itemProto.name
        else:
            if self.count > 1:
                return '%i %s or less' % (self.count - 1, self.itemProto.name)
            return 'no %s' % self.itemProto.name


class DialogRequirement(Persistent):
    requires = RelatedJoin('DialogChoice')
    requireClasses = MultipleJoin('DialogRequireClass')
    requireRaces = MultipleJoin('DialogRequireRace')
    requireRealms = MultipleJoin('DialogRequireRealm')
    requireSkills = MultipleJoin('DialogRequireSkill')
    requireItems = MultipleJoin('DialogRequireItem')
    requireLevel = IntCol(default=0)
    requireClassNumber = IntCol(default=0)
    exclusiveFlags = IntCol(default=0)
    positiveCheck = BoolCol(default=True)
    hideOnFailure = BoolCol(default=False)

    def check(self, player):
        char = player.curChar
        spawn = char.spawn
        passed = True
        posItems = defaultdict(int)
        negItems = defaultdict(int)
        for req in self.requireItems:
            if req.positiveCheck:
                posItems[req.itemProto] += req.count
            else:
                negItems[req.itemProto] += req.count

        if self.positiveCheck:
            if spawn.plevel < self.requireLevel:
                passed = False
            elif 3 >= self.requireClassNumber > 1:
                classes = 1
                if spawn.sclassInternal:
                    if spawn.tclassInternal:
                        classes = 3
                    else:
                        classes = 2
                if classes < self.requireClassNumber:
                    passed = False
            if passed:
                for reqList, exclusiveFlag in [(self.requireClasses, RPG_DIALOG_REQUIREMENT_EXCLUSIVE_CLASSES), (self.requireRaces, RPG_DIALOG_REQUIREMENT_EXCLUSIVE_RACES), (self.requireRealms, RPG_DIALOG_REQUIREMENT_EXCLUSIVE_REALMS)]:
                    for req in reqList:
                        if req.check(spawn):
                            if self.exclusiveFlags & exclusiveFlag:
                                passed = True
                                break
                        else:
                            passed = False
                            if not self.exclusiveFlags & exclusiveFlag:
                                break

                    if not passed:
                        break

            if passed:
                for req in self.requireSkills:
                    if req.check(char.mob):
                        if self.exclusiveFlags & RPG_DIALOG_REQUIREMENT_EXCLUSIVE_SKILLS:
                            passed = True
                            break
                    else:
                        passed = False
                        if not self.exclusiveFlags & RPG_DIALOG_REQUIREMENT_EXCLUSIVE_SKILLS:
                            break

            if passed and (len(posItems) or len(negItems)):
                validated = False
                itemList = []
                for member in player.party.members:
                    itemList.extend(member.items)

                for item in itemList:
                    if RPG_SLOT_TRADE_END > item.slot >= RPG_SLOT_TRADE_BEGIN:
                        continue
                    if RPG_SLOT_LOOT_END > item.slot >= RPG_SLOT_LOOT_BEGIN:
                        continue
                    itemProto = item.itemProto
                    if posItems.has_key(itemProto):
                        if item.stackCount >= posItems[itemProto]:
                            del posItems[itemProto]
                            if self.exclusiveFlags & RPG_DIALOG_REQUIREMENT_EXCLUSIVE_ITEMS:
                                passed = True
                                validated = True
                                break
                        else:
                            posItems[itemProto] -= item.stackCount
                    if negItems.has_key(itemProto):
                        if item.stackCount >= negItems[itemProto]:
                            passed = False
                            if not self.exclusiveFlags & RPG_DIALOG_REQUIREMENT_EXCLUSIVE_ITEMS:
                                validated = True
                                break
                        else:
                            negItems[itemProto] -= item.stackCount
                    if item.container:
                        for citem in item.container.content:
                            citemProto = citem.itemProto
                            if posItems.has_key(citemProto):
                                if citem.stackCount >= posItems[citemProto]:
                                    del posItems[citemProto]
                                    if self.exclusiveFlags & RPG_DIALOG_REQUIREMENT_EXCLUSIVE_ITEMS:
                                        passed = True
                                        validated = True
                                        break
                                else:
                                    posItems[citemProto] -= citem.stackCount
                            if negItems.has_key(citemProto):
                                if citem.stackCount >= negItems[citemProto]:
                                    passed = False
                                    if not self.exclusiveFlags & RPG_DIALOG_REQUIREMENT_EXCLUSIVE_ITEMS:
                                        validated = True
                                        break
                                else:
                                    negItems[citemProto] -= citem.stackCount
                            if not len(posItems) and not len(negItems):
                                break

                    if not len(negItems) and not len(posItems):
                        break

                if not validated and passed:
                    if self.exclusiveFlags & RPG_DIALOG_REQUIREMENT_EXCLUSIVE_ITEMS:
                        if not len(negItems):
                            passed = False
                    elif len(posItems):
                        passed = False
        else:
            if self.requireLevel and spawn.plevel >= self.requireLevel:
                passed = False
            elif 3 >= self.requireClassNumber > 1:
                classes = 1
                if spawn.sclassInternal:
                    if spawn.tclassInternal:
                        classes = 3
                    else:
                        classes = 2
                if classes >= self.requireClassNumber:
                    passed = False
            if passed:
                for reqList, exclusiveFlag in [(self.requireClasses, RPG_DIALOG_REQUIREMENT_EXCLUSIVE_CLASSES), (self.requireRaces, RPG_DIALOG_REQUIREMENT_EXCLUSIVE_RACES), (self.requireRealms, RPG_DIALOG_REQUIREMENT_EXCLUSIVE_REALMS)]:
                    for req in reqList:
                        if not req.check(spawn):
                            if not self.exclusiveFlags & exclusiveFlag:
                                passed = True
                                break
                        else:
                            passed = False
                            if self.exclusiveFlags & exclusiveFlag:
                                break

                    if not passed:
                        break

            if passed:
                for req in self.requireSkills:
                    if not req.check(char.mob):
                        if not self.exclusiveFlags & RPG_DIALOG_REQUIREMENT_EXCLUSIVE_SKILLS:
                            passed = True
                            break
                    else:
                        passed = False
                        if self.exclusiveFlags & RPG_DIALOG_REQUIREMENT_EXCLUSIVE_SKILLS:
                            break

            if passed and (len(posItems) or len(negItems)):
                validated = False
                itemList = []
                for member in player.party.members:
                    itemList.extend(member.items)

                for item in itemList:
                    if RPG_SLOT_TRADE_END > item.slot >= RPG_SLOT_TRADE_BEGIN:
                        continue
                    if RPG_SLOT_LOOT_END > item.slot >= RPG_SLOT_LOOT_BEGIN:
                        continue
                    itemProto = item.itemProto
                    if posItems.has_key(itemProto):
                        if item.stackCount >= posItems[itemProto]:
                            passed = False
                            if self.exclusiveFlags & RPG_DIALOG_REQUIREMENT_EXCLUSIVE_ITEMS:
                                validated = True
                                break
                        else:
                            posItems[itemProto] -= item.stackCount
                    if negItems.has_key(itemProto):
                        if item.stackCount >= negItems[itemProto]:
                            del negItems[itemProto]
                            if not self.exclusiveFlags & RPG_DIALOG_REQUIREMENT_EXCLUSIVE_ITEMS:
                                passed = True
                                validated = True
                                break
                        else:
                            negItems[itemProto] -= item.stackCount
                    if item.container:
                        for citem in item.container.content:
                            citemProto = citem.itemProto
                            if posItems.has_key(citemProto):
                                if citem.stackCount >= posItems[citemProto]:
                                    passed = False
                                    if self.exclusiveFlags & RPG_DIALOG_REQUIREMENT_EXCLUSIVE_ITEMS:
                                        validated = True
                                        break
                                else:
                                    posItems[citemProto] -= citem.stackCount
                            if negItems.has_key(citemProto):
                                if citem.stackCount >= negItems[citemProto]:
                                    del negItems[citemProto]
                                    if not self.exclusiveFlags & RPG_DIALOG_REQUIREMENT_EXCLUSIVE_ITEMS:
                                        passed = True
                                        validated = True
                                        break
                                else:
                                    negItems[citemProto] -= citem.stackCount
                            if not len(posItems) and not len(negItems):
                                break

                    if not len(posItems) and not len(negItems):
                        break

                if not validated and passed:
                    if not self.exclusiveFlags & RPG_DIALOG_REQUIREMENT_EXCLUSIVE_ITEMS:
                        if not len(posItems):
                            passed = False
                    elif len(negItems):
                        passed = False
        if passed:
            return (True, '')
        if self.hideOnFailure:
            return (False, '')
        failText = ''
        if self.positiveCheck:
            if len(self.requireRealms) == 1:
                failText += '%s must be %s.\\n' % (char.name, self.requireRealms[0].getFailLine())
            elif len(self.requireRealms):
                failText += '%s must be %s' % (char.name, ', '.join((realm.getFailLine() for realm in self.requireRealms[0:-1])))
                if self.exclusiveFlags & RPG_DIALOG_REQUIREMENT_EXCLUSIVE_REALMS:
                    failText += ' or %s.\\n' % self.requireRealms[-1].getFailLine()
                else:
                    failText += ' and %s.\\n' % self.requireRealms[-1].getFailLine()
            if len(self.requireRaces) == 1:
                failText += '%s must be %s.\\n' % (char.name, self.requireRaces[0].getFailLine())
            elif len(self.requireRaces):
                failText += '%s must be %s' % (char.name, ', '.join((race.getFailLine() for race in self.requireRaces[0:-1])))
                if self.exclusiveFlags & RPG_DIALOG_REQUIREMENT_EXCLUSIVE_RACES:
                    failText += ' or %s.\\n' % self.requireRaces[-1].getFailLine()
                else:
                    failText += ' and %s.\\n' % self.requireRaces[-1].getFailLine()
            if len(self.requireClasses) == 1:
                failText += '%s must be %s.\\n' % (char.name, self.requireClasses[0].getFailLine())
            elif len(self.requireClasses):
                failText += '%s must be %s' % (char.name, ', '.join((cl.getFailLine() for cl in self.requireClasses[0:-1])))
                if self.exclusiveFlags & RPG_DIALOG_REQUIREMENT_EXCLUSIVE_CLASSES:
                    failText += ' or %s.\\n' % self.requireClasses[-1].getFailLine()
                else:
                    failText += ' and %s.\\n' % self.requireClasses[-1].getFailLine()
            if len(self.requireSkills) == 1:
                failText += '%s must %s.\\n' % (char.name, self.requireSkills[0].getFailLine())
            elif len(self.requireSkills):
                failText += '%s must %s' % (char.name, ', '.join((sk.getFailLine() for sk in self.requireSkills[0:-1])))
                if self.exclusiveFlags & RPG_DIALOG_REQUIREMENT_EXCLUSIVE_SKILLS:
                    failText += ' or %s.\\n' % self.requireSkills[-1].getFailLine()
                else:
                    failText += ' and %s.\\n' % self.requireSkills[-1].getFailLine()
            if len(self.requireItems) == 1:
                failText += '%s must have %s.\\n' % (char.name, self.requireItems[0].getFailLine())
            elif len(self.requireItems):
                failText += '%s must have %s' % (char.name, ', '.join((ir.getFailLine() for ir in self.requireItems[0:-1])))
                if self.exclusiveFlags & RPG_DIALOG_REQUIREMENT_EXCLUSIVE_ITEMS:
                    failText += ' or %s.\\n' % self.requireItems[-1].getFailLine()
                else:
                    failText += ' and %s.\\n' % self.requireItems[-1].getFailLine()
            if self.requireClassNumber == 2:
                failText += '%s needs to learn the basics of at least two classes.\\n' % char.name
            elif self.requireClassNumber == 3:
                failText += '%s needs to learn the basics of three classes.\\n' % char.name
            if self.requireLevel > 0:
                failText += '%s must be level %i or higher.\\n' % (char.name, self.requireLevel)
        else:
            if len(self.requireRealms) == 1:
                failText += '%s must be %s.\\n' % (char.name, self.requireRealms[0].getFailLine(False))
            elif len(self.requireRealms):
                failText += '%s must be %s' % (char.name, ', '.join((realm.getFailLine(False) for realm in self.requireRealms[0:-1])))
                if self.exclusiveFlags & RPG_DIALOG_REQUIREMENT_EXCLUSIVE_REALMS:
                    failText += ' and %s.\\n' % self.requireRealms[-1].getFailLine(False)
                else:
                    failText += ' or %s.\\n' % self.requireRealms[-1].getFailLine(False)
            if len(self.requireRaces) == 1:
                failText += '%s must be %s.\\n' % (char.name, self.requireRaces[0].getFailLine(False))
            elif len(self.requireRaces):
                failText += '%s must be %s' % (char.name, ', '.join((race.getFailLine(False) for race in self.requireRaces[0:-1])))
                if self.exclusiveFlags & RPG_DIALOG_REQUIREMENT_EXCLUSIVE_RACES:
                    failText += ' and %s.\\n' % self.requireRaces[-1].getFailLine(False)
                else:
                    failText += ' or %s.\\n' % self.requireRaces[-1].getFailLine(False)
            if len(self.requireClasses) == 1:
                failText += '%s must be %s.\\n' % (char.name, self.requireClasses[0].getFailLine(False))
            elif len(self.requireClasses):
                failText += '%s must be %s' % (char.name, ', '.join((cl.getFailLine(False) for cl in self.requireClasses[0:-1])))
                if self.exclusiveFlags & RPG_DIALOG_REQUIREMENT_EXCLUSIVE_CLASSES:
                    failText += ' and %s.\\n' % self.requireClasses[-1].getFailLine(False)
                else:
                    failText += ' or %s.\\n' % self.requireClasses[-1].getFailLine(False)
            if len(self.requireSkills) == 1:
                failText += '%s must %s.\\n' % (char.name, self.requireSkills[0].getFailLine(False))
            elif len(self.requireSkills):
                failText += '%s must %s' % (char.name, ', '.join((sk.getFailLine(False) for sk in self.requireSkills[0:-1])))
                if self.exclusiveFlags & RPG_DIALOG_REQUIREMENT_EXCLUSIVE_SKILLS:
                    failText += ' and %s.\\n' % self.requireSkills[-1].getFailLine(False)
                else:
                    failText += ' or %s.\\n' % self.requireSkills[-1].getFailLine(False)
            if len(self.requireItems) == 1:
                failText += '%s must have %s.\\n' % (char.name, self.requireItems[0].getFailLine(False))
            elif len(self.requireItems):
                failText += '%s must have %s' % (char.name, ', '.join((ir.getFailLine(False) for ir in self.requireItems[0:-1])))
                if self.exclusiveFlags & RPG_DIALOG_REQUIREMENT_EXCLUSIVE_ITEMS:
                    failText += ' and %s.\\n' % self.requireItems[-1].getFailLine(False)
                else:
                    failText += ' or %s.\\n' % self.requireItems[-1].getFailLine(False)
            if self.requireClassNumber == 2:
                failText += '%s must have learned the basics of only one class.\\n' % char.name
            elif self.requireClassNumber == 3:
                failText += '%s must have learned the basics of less than three classes.\\n' % char.name
            if self.requireLevel > 0:
                failText += '%s must be level %i or lower.\\n' % (char.name, self.requireLevel - 1)
        return (False, failText)


class DialogLine(Persistent):
    text = StringCol(default='')
    journalEntryID = IntCol(default=0)
    actions = RelatedJoin('DialogAction')
    choices = RelatedJoin('DialogChoice')
    dialog = ForeignKey('Dialog')

    def _init(self, *args, **kw):
        Persistent._init(self, *args, **kw)
        self.numChoices = len(self.choices)


class DialogChoice(Persistent):
    identifier = StringCol(default='')
    maxTimes = IntCol(default=0)
    maxBump = BoolCol(default=False)
    hideOnMaxBump = BoolCol(default=False)
    text = StringCol(default='')
    requirements = RelatedJoin('DialogRequirement')
    requirementsInclusive = BoolCol(default=True)
    failLine = ForeignKey('DialogLine', default=None)
    successLine = ForeignKey('DialogLine', default=None)
    lines = RelatedJoin('DialogLine')
    dialogs = RelatedJoin('Dialog')

    def _init(self, *args, **kw):
        Persistent._init(self, *args, **kw)

    def checkHide(self, player, dialogTrigger = False):
        if self.hideOnMaxBump and self.identifier and self.maxTimes:
            from character import CharacterDialogChoice
            dcs = list(CharacterDialogChoice.select(AND(CharacterDialogChoice.q.identifier == self.identifier, CharacterDialogChoice.q.characterID == player.curChar.id)))
            try:
                if dcs[0].count >= self.maxTimes:
                    return True
            except:
                pass

        failure = False
        for req in self.requirements:
            if req.hideOnFailure:
                if not req.check(player)[0]:
                    failure = True
                    if self.requirementsInclusive:
                        break
                elif not self.requirementsInclusive:
                    failure = False
                    break

        if failure:
            return True
        if self.successLine and not dialogTrigger:
            for action in self.successLine.actions:
                if not action.checkCheckItems(player, True) or not action.checkTakeItems(player, True) or not action.checkCheckSkills(player, True):
                    return True

        return False

    def checkRequirements(self, player):
        failure = False
        failText = ''
        for req in self.requirements:
            if req.hideOnFailure:
                continue
            passed, ftext = req.check(player)
            if ftext:
                failText += ftext
            if not passed:
                failure = True
                if self.requirementsInclusive:
                    break
            elif not self.requirementsInclusive:
                failure = False
                break

        if not failure:
            failText = ''
            if self.successLine:
                for action in self.successLine.actions:
                    if not action.check(player):
                        failure = True
                        break

        return (failure, failText)


class Dialog(Persistent):
    name = StringCol(alternateID=True)
    title = StringCol(default='')
    greeting = ForeignKey('DialogLine', default=None)
    rebuke = ForeignKey('DialogLine', default=None)
    lines = MultipleJoin('DialogLine')
    choices = RelatedJoin('DialogChoice')
    actions = MultipleJoin('DialogAction')
    spawns = MultipleJoin('Spawn')

    def _init(self, *args, **kw):
        Persistent._init(self, *args, **kw)

    def handleLine(self, pane, player, newline):
        from mud.world.mob import Mob
        interacting = player.interacting
        dialogTrigger = not isinstance(interacting, Mob)
        end = False
        for a in newline.actions:
            if a.attack or a.endInteraction or a.despawn:
                end = True
            end |= a.do(player)

        text = str(newline.text)
        if not end:
            self.curChoices = []
            choices = []
            player.curDialogLine = newline
            for c in newline.choices:
                if not c.checkHide(player, dialogTrigger):
                    self.curChoices.append(c)
                    choices.append(str(c.text))

            if not len(choices):
                player.curDialogLine = self.greeting
                for c in self.greeting.choices:
                    if not c.checkHide(player, dialogTrigger):
                        self.curChoices.append(c)
                        choices.append(str(c.text))

            pane.callRemote('set', text, choices, newline.journalEntryID)
        elif text:
            if not dialogTrigger:
                player.sendGameText(RPG_MSG_GAME_NPC_SPEECH, '%s says, \\"%s\\"\\n' % (interacting.name, text), interacting, player.curChar.mob)
            else:
                player.sendGameText(RPG_MSG_GAME_EVENT, '%s\\n' % text, None, player.curChar.mob)
            if newline.journalEntryID:
                player.mind.callRemote('addJournalEntry', newline.journalEntryID)
            player.curDialogLine = None
        return

    def setLine(self, player, line, name):
        player.curDialogLine = line
        dialog = line.dialog
        dialog.curChoices = []
        choices = []
        for choice in line.choices:
            if not choice.checkHide(player):
                dialog.curChoices.append(choice)
                choices.append(choice.text)

        if len(choices):
            player.dialog = dialog
            player.mind.callRemote('setInitialInteraction', line.id, choices, name)
        else:
            player.mind.callRemote('setInitialInteraction', None, None)
        return

    def handleChoice(self, player, choiceIndex, pane):
        from character import CharacterDialogChoice
        curLine = player.curDialogLine
        if hasattr(self, 'curChoices'):
            choice = self.curChoices[choiceIndex]
        else:
            choice = self.choices[choiceIndex]
        char = player.curChar
        charDialogChoice = None
        if choice.identifier and choice.maxTimes:
            dcs = list(CharacterDialogChoice.select(AND(CharacterDialogChoice.q.identifier == choice.identifier, CharacterDialogChoice.q.characterID == char.id)))
            if dcs and len(dcs):
                charDialogChoice = dcs[0]
                if charDialogChoice.count >= choice.maxTimes:
                    pane.callRemote('set', '\\n%s has chosen this option the maximum times.\\n\\n' % char.name, [])
                    player.sendGameText(RPG_MSG_GAME_DENIED, '%s has chosen this option the maximum times.\\n' % char.name)
                    self.handleLine(pane, player, self.greeting)
                    return
        failure, failText = choice.checkRequirements(player)
        if failure:
            newline = choice.failLine
            if failText:
                player.sendGameText(RPG_MSG_GAME_DENIED, failText)
        else:
            newline = choice.successLine
            if choice.identifier and choice.maxTimes and choice.maxBump:
                if not charDialogChoice:
                    charDialogChoice = CharacterDialogChoice(character=char, identifier=choice.identifier, count=1)
                else:
                    charDialogChoice.count += 1
        if not newline:
            newline = self.greeting
        if newline:
            self.handleLine(pane, player, newline)
        return