# Embedded file name: mud\simulation\simobject.pyo
from twisted.spread import pb
import traceback
from math import fabs, sqrt
from random import randint
from mud.world.core import CoreSettings
try:
    from tgenative import *
    from mud.tgepython.console import TGEExport
except:
    pass

ANIM_IDLE = 0
ANIM_WALK = 1
ANIM_RUN = 1
ANIMS = {'twohanded': ('2hslash',
               '2hslash2',
               '2hslash3',
               '2hthrust'),
 'onehanded': ('1hslashleft',
               '1hslashright',
               '1hslash2left',
               '1hslash2right',
               '1hslash3left',
               '1hslash3right',
               '1hthrustleft',
               '1hthrustright'),
 'onehanded_left': ('1hslashleft',
                    '1hslash2left',
                    '1hslash3left',
                    '1hthrustleft',
                    'unarmedleft'),
 'onehanded_right': ('1hslashright',
                     '1hslash2right',
                     '1hslash3right',
                     '1hthrustright',
                     'unarmedright'),
 'unarmed': ('unarmedleft', 'unarmedright')}

class Brain():

    def __init__(self, simObject):
        self.simObject = simObject
        self.reset()

    def reset(self):
        self.target = None
        self.followTarget = None
        self.targetPos = None
        self.attacking = False
        self.rangedAttack = False
        self.iscasting = 0
        self.dead = False
        self.anim = -1
        self.death = 0
        self.feignDeath = 0
        self.noanim = True
        self.twohanded = False
        tge = self.simObject.tgeObject
        if int(tge.isSwimming()):
            tge.playThread(0, 'swimidle')
        elif int(tge.isFlying()):
            tge.playThread(0, 'flyidle')
        else:
            tge.playThread(0, 'idle')
        self.returnHomeTimer = 0
        self.walk = False
        return

    def returnHome(self):
        so = self.simObject
        so.tgeObject.setVelocity('0 0 0')
        so.tgeObject.setTransform(so.homePoint)

    def setTarget(self, tgt):
        if tgt == self.target:
            return
        if self.simObject.wanderGroup <= 0:
            if not tgt:
                if not self.simObject.isPlayer and not self.returnHomeTimer and not self.death:
                    self.returnHomeTimer = 600
            else:
                self.returnHomeTimer = 0
        self.target = tgt

    def setFollowTarget(self, tgt):
        self.followTarget = tgt

    def casting(self, casting):
        self.iscasting = casting
        if casting and not self.death and self.noanim and not self.attacking and not self.rangedAttack:
            self.simObject.tgeObject.playThread(0, 'spellprepare')

    def cast(self, projectile = False):
        self.iscasting = False
        so = self.simObject
        tge = so.tgeObject
        if self.death:
            return
        if int(tge.isFlying()) or self.attacking or self.rangedAttack:
            return
        if projectile:
            tge.playThread(0, 'spellcast')
        else:
            tge.playThread(0, 'spellcast2')

    def playAnimation(self, anim):
        if anim == 'bowattack':
            return
            self.rangedAttack = True
            if self.simObject.observer:
                self.simObject.observer.callRemote('updateRangedAttack', self.rangedAttack)
        self.noanim = False
        self.simObject.tgeObject.playThread(0, anim)

    def pain(self):
        if self.death:
            print 'WARNING: mob pain after death'
            return
        so = self.simObject
        tge = so.tgeObject
        if int(tge.isFlying()):
            return
        self.noanim = False
        if not randint(0, 1):
            self.simObject.tgeObject.playThread(0, 'pain1')
        else:
            self.simObject.tgeObject.playThread(0, 'pain2')

    def tick(self):
        global ANIMS
        so = self.simObject
        tge = so.tgeObject
        isPlayer = so.isPlayer
        mobInfo = so.mobInfo
        target = self.target
        if self.returnHomeTimer:
            self.returnHomeTimer -= 1
            if not self.returnHomeTimer:
                self.returnHome()
        vel = tge.getVelocity()
        spd = 0
        if fabs(vel[0]) > 0.1 or fabs(vel[1]) > 0.1:
            spd = 1
        dist = 1000000
        if not isPlayer:
            if target:
                tge.setFollowObject(target.id)
            elif self.followTarget:
                tge.setFollowObject(self.followTarget.id)
            else:
                tge.setFollowObject(0)
            if mobInfo.FEAR:
                tge.setAvoidFollowObject(True)
            else:
                tge.setAvoidFollowObject(False)
        if mobInfo.FEIGNDEATH:
            if not self.feignDeath:
                self.doFeignDeath()
        else:
            self.feignDeath = 0
        if self.noanim and not self.death and not self.feignDeath:
            cansee = False
            if target:
                if target.id in so.canSee:
                    cansee = True
                    x = target.position[0] - so.position[0]
                    y = target.position[1] - so.position[1]
                    z = target.position[2] - so.position[2]
                    dist = sqrt(x * x + y * y + z * z)
                    dist -= target.spawnInfo.radius * target.spawnInfo.scale
            if mobInfo.SLEEP:
                tge.playThread(0, 'idle')
                if not isPlayer:
                    tge.setMoveSpeed(0.0)
            else:
                if not isPlayer:
                    tge.setMoveSpeed(1.0)
                if spd:
                    if int(tge.isSwimming()):
                        tge.playThread(0, 'swim')
                    else:
                        slow = self.walk
                        if not isPlayer and not (target or self.followTarget):
                            slow = True
                            tge.setMoveSpeed(0.5)
                        if slow:
                            if int(tge.isFlying()) and int(tge.hasFlyingAnimation()):
                                tge.playThread(0, 'flyglide')
                            elif self.twohanded:
                                tge.playThread(0, '2hwalk')
                            else:
                                tge.playThread(0, '1hwalk')
                        elif int(tge.isFlying()) and int(tge.hasFlyingAnimation()):
                            tge.playThread(0, 'fly')
                        elif self.twohanded:
                            tge.playThread(0, '2hrun')
                        else:
                            tge.playThread(0, '1hrun')
                elif target and self.attacking:
                    if not self.rangedAttack:
                        if all([cansee,
                         not randint(0, 3),
                         dist < so.spawnInfo.radius * so.spawnInfo.scale,
                         not mobInfo.FEAR]):
                            if self.twohanded:
                                anims = ANIMS['twohanded']
                            elif mobInfo.MOUNT0:
                                if mobInfo.MOUNT1:
                                    anims = ANIMS['onehanded']
                                else:
                                    anims = ANIMS['onehanded_right']
                            elif mobInfo.MOUNT1:
                                anims = ANIMS['onehanded_left']
                            else:
                                anims = ANIMS['unarmed']
                            tge.playThread(0, anims[randint(0, len(anims) - 1)])
                            self.noanim = False
                        elif self.twohanded:
                            tge.playThread(0, 'cready2h')
                        else:
                            tge.playThread(0, 'cready1h')
                    else:
                        tge.playThread(0, 'cready1h')
                elif self.iscasting:
                    tge.playThread(0, 'spellprepare')
                elif int(tge.isSwimming()):
                    tge.playThread(0, 'swimidle')
                elif int(tge.isFlying()):
                    tge.playThread(0, 'flyidle')
                else:
                    tge.playThread(0, 'idle')

    def doFeignDeath(self):
        self.feignDeath = 1
        self.noanim = False
        self.simObject.tgeObject.playThread(0, 'death')

    def die(self):
        self.returnHomeTimer = 0
        self.death = 1
        self.noanim = False
        self.simObject.tgeObject.playThread(0, 'death')

    def onEndSequence(self):
        tge = self.simObject.tgeObject
        self.noanim = True
        if self.rangedAttack:
            self.rangedAttack = False
            if self.simObject.observer:
                self.simObject.observer.callRemote('updateRangedAttack', self.rangedAttack)
        if self.death:
            self.simObject.observer.callRemote('finishDeath')
        elif not self.feignDeath:
            if self.iscasting:
                tge.playThread(0, 'spellcast2')
            elif self.target and self.attacking:
                if self.twohanded:
                    tge.playThread(0, 'cready2h')
                else:
                    tge.playThread(0, 'cready1h')
            else:
                if int(tge.isSwimming()):
                    tge.playThread(0, 'swimidle')
                if int(tge.isFlying()):
                    tge.playThread(0, 'flyidle')
                else:
                    tge.playThread(0, 'idle')


class SimObject(pb.Cacheable):

    def __init__(self, id, spawnInfo, mobInfo, transform = [0,
 0,
 0,
 0,
 0,
 0,
 0], wanderGroup = -1, isPlayer = False):
        self.observer = None
        self.id = id
        self.wanderGroup = wanderGroup
        self.tgeObject = TGEObject(id)
        self.tgeObject.wanderGroup = wanderGroup
        self.isPlayer = isPlayer
        self.spawnInfo = spawnInfo
        self.mobInfo = mobInfo
        self.position = tuple(transform[:3])
        self.rotation = tuple(transform[3:])
        self.canSee = []
        self.simZombie = False
        self.waypoint = -1
        self.homePoint = ' '.join(map(str, transform))
        self.brain = Brain(self)
        self.canKite = False
        self.backupHomePoint = self.homePoint
        return

    def getStateToCacheAndObserveFor(self, perspective, observer):
        self.observer = observer
        state = {}
        state['id'] = self.id
        state['position'] = self.position
        state['rotation'] = self.rotation
        state['cansee'] = self.canSee
        state['simZombie'] = self.simZombie
        return state

    def stoppedObserving(self, perspective, observer):
        self.observer = None
        self.mobInfo = None
        self.brain = None
        self.canSee = []
        return

    def updateCanSee(self, cansee):
        if not self.observer:
            return
        if cansee != self.canSee:
            self.canSee = cansee
            self.observer.callRemote('updateCanSee', cansee)

    def updateTransform(self):
        if not self.observer:
            return None
        else:
            transform = self.tgeObject.getTransform()
            pos = tuple(transform[:3])
            rot = tuple(transform[3:])
            try:
                role = self.tgeObject.role
            except:
                role = 'Player'

            if self.isPlayer:
                if pos == self.position and rot == self.rotation:
                    return None
                deltaX = fabs(pos[0] - self.position[0])
                deltaY = fabs(pos[1] - self.position[1])
                deltaZ = fabs(pos[2] - self.position[2])
                distance = deltaX * deltaX + deltaY * deltaY
                dangle = fabs(rot[3] * rot[2] - self.rotation[3] * self.rotation[2])
                if distance + deltaZ * deltaZ < 0.5 and dangle < 0.05:
                    return None
                if role != 'Immortal' and distance > 5000.0:
                    print 'WARNING: displacement ignored for %s, old position: %s, requested position: %s' % (self.spawnInfo.name, self.position, pos)
                    transform = list(self.tgeObject.getTransform())
                    transform[0] = self.position[0]
                    transform[1] = self.position[1]
                    transform[2] = self.position[2]
                    self.tgeObject.setTransform(transform)
                    return None
                self.position = pos
                self.rotation = rot
                return (self.id,
                 pos,
                 rot,
                 float(self.tgeObject.waterCoverage))
            canKite = self.tgeObject.canKite
            if canKite == self.canKite:
                if pos == self.position and rot == self.rotation:
                    return None
                if fabs(pos[0] - self.position[0]) < 1.0:
                    if fabs(pos[1] - self.position[1]) < 1.0:
                        if fabs(pos[2] - self.position[2]) < 1.0:
                            if rot[2] == self.rotation[2]:
                                if fabs(rot[3] - self.rotation[3]) < 0.1:
                                    return None
            self.canKite = canKite
            self.position = pos
            self.rotation = rot
            return (self.id,
             pos,
             rot,
             canKite)
            return None

    def remote_mountImage(self, rpgslot, model):
        print 'mountImage %d: %s' % (rpgslot, model)


class SimGhost(pb.RemoteCache):

    def __init__(self):
        self.canKite = False
        self.waterCoverage = 0.0
        self.rangedAttack = False
        self.dyingMob = None
        return

    def setCopyableState(self, state):
        self.id = state['id']
        self.position = state['position']
        self.rotation = state['rotation']
        self.canSee = state['cansee']
        self.simZombie = state['simZombie']

    def observe_updatePosition(self, position, canKite):
        self.position = position
        self.canKite = canKite

    def observe_updateTransform(self, position, rotation, waterCoverage):
        self.position = position
        self.rotation = rotation
        self.waterCoverage = waterCoverage

    def observe_updateCanSee(self, canSee):
        self.canSee = canSee

    def observe_updateSimZombie(self, zombie):
        self.simZombie = zombie

    def observe_updateRangedAttack(self, rangedAttack):
        self.rangedAttack = rangedAttack

    def observe_finishDeath(self):
        if self.dyingMob:
            player = self.dyingMob.player
            if player:
                if CoreSettings.MAXPARTY == 1:
                    player.world.setDeathMarker(player, player.curChar)
                player.world.onPlayerDeath(player)
            self.dyingMob = None
        return


pb.setUnjellyableForClass(SimObject, SimGhost)