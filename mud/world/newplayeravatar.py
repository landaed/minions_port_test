# Copyright (C) 2004-2007 Prairie Games, Inc
# Please see LICENSE.TXT for details


from mud.common.avatar import Avatar
from mud.common.permission import User,Role
from mud.world.core import *
from mud.world.player import Player
from mud.world.theworld import World

from random import choice
import string
import traceback



def GenPasswd(length=8, chars=string.ascii_letters):
    return ''.join([choice(chars) for i in range(length)])

#also query
class NewPlayerAvatar(Avatar):
    ownerPublicName = None
    
    
    def __init__(self,username,role,mind):
        Avatar.__init__(self,username,role,mind)
        self.username = username
        self.world = World.byName("TheWorld")
    
    def perspective_newPlayer(self,publicName,fantasyName, playerPassword = None):
        #XXX if you change this function, also change it's mirror in cserveravatar!!!
        
        if self.world.pwNewPlayer and playerPassword != self.world.pwNewPlayer:
            return (-1,"Incorrect player password.",None)

        #does player already exist?
        try:
            player = Player.byPublicName(publicName)
        except:
            pass
        else:
            return (-1,"You already have an account on this world.",None)
     
        try:
            player = Player.byFantasyName(fantasyName)
        except:
            pass
        else:
            return (-1,"That avatar name is taken, please choose another.",None)
                
        password = GenPasswd().upper()

        try:
            #move me
            from mud.world.zone import Zone
            zone = Zone.byName(self.world.startZone)
            dzone = Zone.byName(self.world.dstartZone)
            mzone = Zone.byName(self.world.mstartZone)

            t = zone.immTransform
            dt = dzone.immTransform
            mt = mzone.immTransform
            
            p = Player(publicName=publicName,password=password,fantasyName=fantasyName,logZone=zone,bindZone=zone,darknessLogZone=dzone,darknessBindZone=dzone,monsterLogZone=mzone,monsterBindZone=mzone)
            #temp
            
            p.logTransformInternal=t
            p.bindTransformInternal=t

            p.darknessLogTransformInternal=dt
            p.darknessBindTransformInternal=dt

            p.monsterLogTransformInternal=mt
            p.monsterBindTransformInternal=mt

            
            user = User(name=publicName,password=password)
            user.addRole(Role.byName("Player"))
            
            if publicName == NewPlayerAvatar.ownerPublicName: 
                user.addRole(Role.byName("Immortal"))
                user.addRole(Role.byName("Guardian"))
                
                return (0,"Immortal Account Created.\nYour password is %s"%password,password)
            
            
            return (0,"Account Created.\nYour password is %s"%password,password)
        except Exception as exc:
            traceback.print_exc()
            return (-1,"Error creating world account: %s" % exc,None)
        
    #returns True if player has an account, otherwise false
    def perspective_queryPlayer(self,publicName):
        #does player already exist?
        try:
            player = Player.byPublicName(publicName)
        except:
            return False
        else:
            return True


    # The original logout flow extracts the player to the character server and
    # destroys the world-local Player/User rows; the official servers then
    # reinstalled the buffer through the master -> character-server transfer.
    # Direct-connect clients (the Godot proxy) skipped that reinstall, so every
    # re-login silently created a brand-new world account at the start zone
    # (losing the saved log position).  This restores the saved player instead:
    # returns (0, message, worldPassword) on success, (-1, message, None) when
    # there is nothing to restore (caller should fall back to newPlayer).
    def perspective_restorePlayer(self,publicName):
        # Still installed (e.g. unclean shutdown or active session)?  The local
        # row is at least as fresh as the last extracted buffer — reuse it.
        try:
            player = Player.byPublicName(publicName)
        except:
            player = None
        if player:
            password = player.password
            self._ensureUser(publicName,password)
            return (0,"Welcome back!",password)

        from mud.world.cserveravatar import AVATAR
        if not AVATAR or not AVATAR.mind:
            return (-1,"No saved player and no character server.",None)

        d = AVATAR.mind.callRemote("getPlayerBuffer",publicName)
        d.addCallback(self._gotPlayerBuffer,publicName)
        d.addErrback(self._restoreFailed)
        return d

    def _restoreFailed(self,reason):
        traceback.print_exc()
        return (-1,"Error restoring saved player: %s"%reason,None)

    def _gotPlayerBuffer(self,buffer,publicName):
        if not buffer:
            return (-1,"No saved player on this world.",None)

        from base64 import decodebytes
        from pickle import loads
        from mud.worldserver.charutil import InstallPlayerBuffer

        try:
            raw = loads(decodebytes(buffer))
        except Exception:
            raw = buffer

        error = InstallPlayerBuffer(raw)
        if error:
            return (-1,"Error installing saved player buffer.",None)

        try:
            player = Player.byPublicName(publicName)
        except Exception as exc:
            traceback.print_exc()
            return (-1,"Saved player buffer was missing the player: %s"%exc,None)

        # Keep the password stored in the buffer so anything the player wrote
        # down (or the master server cached from a world announce) stays valid.
        password = player.password
        self._ensureUser(publicName,password)
        print("Restored saved player %s from character server buffer"%publicName)
        return (0,"Welcome back!",password)

    def _ensureUser(self,publicName,password):
        try:
            user = User.byName(publicName)
            for r in user.roles:
                r.removeUser(user)
            user.destroySelf()
        except:
            pass
        user = User(name=publicName,password=password)
        user.addRole(Role.byName("Player"))
        if publicName == NewPlayerAvatar.ownerPublicName:
            user.addRole(Role.byName("Immortal"))
            user.addRole(Role.byName("Guardian"))
        
        
        
    
#also query
class QueryAvatar(Avatar):
    def perspective_retrieveWorldInfo(self):
        return CoreSettings.WORLDTEXT,CoreSettings.WORLDPIC

