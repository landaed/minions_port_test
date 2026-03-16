# Embedded file name: mud\world\pet.pyo
from mud.world.core import AllowHarmful
from mud.world.defines import *
from random import randint
PETMSG_ATTACK = ['Attacking master!!!', 'Food!!!', 'I will protect you master!!!']

def PetCmdAttack(pet, target):
    pet.aggro.clear()
    player = pet.master.player
    if not target:
        if player:
            player.sendGameText(RPG_MSG_GAME_PET_SPEECH, 'Your pet says, \\"Are you seeing things again master?\\"\\n')
        pet.zone.setTarget(pet, None)
    if target == pet:
        if player:
            player.sendGameText(RPG_MSG_GAME_PET_SPEECH, 'Your pet says, \\"I will not attack myself master!\\"\\n')
        return
    elif target == pet.master:
        if player:
            player.sendGameText(RPG_MSG_GAME_PET_SPEECH, 'Your pet says, \\"I will not attack you master!\\"\\n')
        return
    elif not AllowHarmful(pet, target):
        if player:
            player.sendGameText(RPG_MSG_GAME_PET_SPEECH, 'Your pet says, \\"I cannot attack %s master!\\"\\n' % target.name)
        return
    else:
        pet.addAggro(target, (pet.master.level + RPG_PLAYERPET_AGGROTHRESHOLD) * pet.level)
        pet.zone.setTarget(pet, target)
        if player:
            player.sendGameText(RPG_MSG_GAME_PET_SPEECH, 'Your pet says, %s\\n' % PETMSG_ATTACK[randint(0, len(PETMSG_ATTACK) - 1)])
        return


def PetCmdStandDown(pet):
    player = pet.master.player
    pet.aggro.clear()
    pet.zone.setTarget(pet, None)
    if player:
        player.sendGameText(RPG_MSG_GAME_PET_SPEECH, 'Your pet says, \\"Standing down master.\\"\\n')
    return


def PetCmdStay(pet):
    pet.aggro.clear()
    player = pet.master.player
    mind = pet.zone.simAvatar.mind
    so = pet.simObject
    mind.callRemote('setHomeTransform', so.id, so.position, so.rotation)
    pet.zone.setFollowTarget(pet, None)
    if player:
        player.sendGameText(RPG_MSG_GAME_PET_SPEECH, 'Your pet says, \\"I will stay here master.\\"\\n')
    return


def PetCmdFollowMe(pet):
    pet.aggro.clear()
    player = pet.master.player
    if pet.followTarget != pet.master:
        pet.zone.setFollowTarget(pet, pet.master)
    if player:
        player.sendGameText(RPG_MSG_GAME_PET_SPEECH, 'Your pet says, \\"I will follow you master.\\"\\n')


def PetCmdDismiss(pet):
    player = pet.master.player
    if player:
        player.sendGameText(RPG_MSG_GAME_PET_SPEECH, 'Your pet says, \\"Goodbye master.  You know where to find me.\\"\\n')
    if pet.charmEffect:
        pet.charmEffect.parent.cancel()
    else:
        pet.zone.removeMob(pet)