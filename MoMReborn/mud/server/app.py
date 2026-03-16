# Embedded file name: mud\server\app.pyo
from sqlobject import *
from mud.common.dbconfig import GetDBConnection
from zope.interface import implements
from twisted.internet import reactor, protocol, defer
from twisted.spread import pb
from twisted.cred.portal import Portal, IRealm
from twisted.cred.credentials import IUsernamePassword, IUsernameHashedPassword
from twisted.cred.checkers import ICredentialsChecker
from twisted.cred import error, credentials, checkers
from twisted.python import components, failure, log
from mud.common.avatar import Avatar
from mud.common.permission import Role, User, BannedUser, BannedIP
from md5 import md5
from time import time as sysTime
import traceback

class UnauthorizedError(Exception):

    def __str__(self):
        return 'login information is incorrect'


class InUseError(Exception):

    def __str__(self):
        return 'account is currently in use'


class BannedError(Exception):

    def __str__(self):
        return 'banned from this server'


class BannedIPError(Exception):

    def __str__(self):
        return 'IP address you are connecting from is banned'


class ServerFullError(Exception):

    def __str__(self):
        return 'server is full'


class AllowConnectionsError(Exception):

    def __str__(self):
        return 'server is currently unavailable, please try again later'


class PerspectiveCallError(Exception):

    def __str__(self):
        return 'perspective call'


class NoAvatarError(Exception):

    def __str__(self):
        return 'no avatar'


class NoFunctionError(Exception):

    def __str__(self):
        return 'no function'


class PerspectiveCallError(Exception):

    def __str__(self):
        return 'perspective call'


class Checker:
    implements(ICredentialsChecker)
    credentialInterfaces = (IUsernamePassword, IUsernameHashedPassword)

    def __init__(self):
        pass

    def requestAvatarId(self, credentials):
        global THESERVER
        if len(credentials.username.split('-')) != 2:
            return failure.Failure(UnauthorizedError())
        username, role = credentials.username.split('-')
        try:
            banned = BannedUser.byName(username)
            return failure.Failure(BannedError())
        except:
            pass

        if THESERVER.roleLimits.has_key(role):
            limit = THESERVER.roleLimits[role]
            if not limit:
                return failure.Failure(ServerFullError())
            n = 0
            for x in MasterPerspective.users:
                if role == x[1]:
                    n += 1
                    if n >= limit:
                        return failure.Failure(ServerFullError())

        roles = ['Player',
         'Immortal',
         'Guardian',
         'World']
        for r in roles:
            if (username, r) in MasterPerspective.users[:]:
                for avatar in THESERVER.realm.avatars[:]:
                    if avatar.username == username and avatar.role.name == r:
                        try:
                            avatar.logout()
                        except:
                            traceback.print_exc()

        try:
            user = User.byName(username)
        except SQLObjectNotFound:
            print 'requestAvatarId: no user %s' % username
            return failure.Failure(UnauthorizedError())

        matched = 0
        if not matched and user.password:
            matched = credentials.checkPassword(md5(user.password).digest())
        if not matched and user.tempPassword:
            matched = credentials.checkPassword(md5(user.tempPassword).digest())
        if not matched:
            print 'requestAvatarId: invalid password for %s (%s) (%s)' % (username, user.password, user.tempPassword)
            return failure.Failure(UnauthorizedError())
        r = user.getRole(role)
        if r:
            return credentials.username
        print 'requestAvatarId: no role %s' % credentials.username
        return failure.Failure(UnauthorizedError())


class MasterPerspective(pb.Avatar):
    users = []
    deferredCalls = {}

    def __init__(self, role, username, mind, realm):
        self.avatars = {}
        self.role = role
        self.mind = mind
        self.username = username
        self.cpuTime = 0
        self.throttle = role.name in ('Player', 'Guardian', 'Immortal')
        MasterPerspective.users.append((self.username, self.role.name))
        MasterPerspective.deferredCalls[self] = []
        for avatar in role.avatars:
            a = Avatar.createAvatar(avatar.name)
            a.setup(username, role, mind)
            a.realm = realm
            self.avatars[avatar.name] = a
            a.masterPerspective = self

    def removeAvatar(self, name):
        if self.avatars.has_key(name):
            del self.avatars[name]

    def __getattr__(self, attr):
        if attr.startswith('perspective_'):
            self._interface = attr[12:]
            return self.perspective_call
        raise AttributeError

    def perspective_enumAvatars(self):
        return self.avatars.keys()

    def perspective_call(self, *args):
        if THESERVER.throttleUsage and self.throttle:
            if self.cpuTime > 0.2:
                dc = MasterPerspective.deferredCalls[self]
                d = defer.Deferred()
                dc.append((d, args))
                return d
        return self.perspective_act(*args)

    def perspective_act(self, *args):
        tm = sysTime()
        function = args[0]
        interface = self._interface
        try:
            avatar = self.avatars[interface]
        except KeyError:
            try:
                interface = interface + 'Avatar'
                avatar = self.avatars[interface]
            except:
                return failure.Failure(NoAvatarError())

        function = 'perspective_' + function
        if not hasattr(avatar, function):
            return failure.Failure(NoFunctionError())
        nargs = args[1:]
        if hasattr(avatar, 'player'):
            if avatar.player:
                avatar.player.cinfoDirty = True
        try:
            result = getattr(avatar, function)(*nargs)
        except:
            traceback.print_exc()
            return failure.Failure(PerspectiveCallError())

        t = sysTime() - tm
        if t > 0.5:
            print 'WARNING: %s %s took %.1f seconds' % (self.username, args, t)
        self.cpuTime += t
        return result

    def logout(self):
        if (self.username, self.role.name) not in MasterPerspective.users:
            return
        else:
            MasterPerspective.users.remove((self.username, self.role.name))
            try:
                del MasterPerspective.deferredCalls[self]
                for avatar in self.avatars.itervalues():
                    try:
                        avatar.logout()
                        avatar.masterPerspective = None
                    except AttributeError:
                        pass

                try:
                    if self.realm:
                        self.realm.avatars.remove(self)
                except AttributeError:
                    pass

                if self.mind:
                    self.mind.broker.transport.loseConnection()
                    self.mind = None
            except:
                traceback.print_exc()

            return


class Realm:
    implements(IRealm)

    def __init__(self, server):
        self.avatars = []
        self.server = server

    def requestAvatar(self, avatarId, mind, *interfaces):
        if pb.IPerspective in interfaces:
            username, role = avatarId.split('-')
            if mind:
                ip = mind.broker.transport.getPeer()
                try:
                    subnet = ip.host[:ip.host.rfind('.')]
                except:
                    print "WARNING:  IP logging isn't working... Windows 2000?"
                    subnet = ''

                if role == 'Registration' and subnet:
                    try:
                        bi = BannedIP.byAddress(subnet)
                        return failure.Failure(BannedIPError())
                    except:
                        pass

                if role in ('Player', 'Guardian', 'Immortal'):
                    u = User.byName(username)
                    if subnet:
                        u.lastConnectSubnet = subnet
            if role in ('Player', 'Guardian', 'Immortal'):
                if not THESERVER.allowConnections:
                    return failure.Failure(AllowConnectionsError())
            role = Role.byName(role)
            avatar = MasterPerspective(role, username, mind, self)
            avatar.realm = self
            self.avatars.append(avatar)
            return (pb.IPerspective, avatar, avatar.logout)
        raise NotImplementedError('no interface')


THESERVER = None

class Server:

    def __init__(self, port):
        global THESERVER
        if THESERVER:
            traceback.print_stack()
            print 'AssertionError: server already exists!'
            return
        else:
            THESERVER = self
            self.port = port
            self.realm = None
            self.portal = None
            self.checker = None
            self.listen = None
            self.allowConnections = True
            self.roleLimits = {}
            MasterPerspective.users = []
            self.throttleUsage = False
            self.throttleTickCallback = None
            return

    def getActiveUsersByRole(self, role):
        n = 0
        for username, urole in MasterPerspective.users:
            if urole == role:
                n += 1

        return n

    def throttleTick(self):
        for avatar in MasterPerspective.deferredCalls.iterkeys():
            if avatar.cpuTime > 0:
                avatar.cpuTime -= 0.2
            else:
                dc = MasterPerspective.deferredCalls[avatar]
                if len(dc):
                    d, args = dc.pop(0)
                    try:
                        result = avatar.perspective_act(*args)
                        if isinstance(result, defer.Deferred):
                            result.chainDeferred(d)
                        else:
                            d.callback(result)
                    except:
                        traceback.print_exc()

                    break

        reactor.callLater(0.1, self.throttleTick)

    def startServices(self):
        port = self.port
        self.realm = Realm(self)
        self.portal = Portal(self.realm)
        self.checker = Checker()
        self.portal.registerChecker(self.checker)
        self.listen = reactor.listenTCP(port, pb.PBServerFactory(self.portal))
        self.throttleTickCallback = self.throttleTick()

    def shutdown(self):
        global THESERVER
        THESERVER = None
        for avatar in self.realm.avatars:
            avatar.mind.broker.transport.loseConnection()

        if self.listen:
            self.listen.stopListening()
        if self.throttleTickCallback:
            self.throttleTickCallback.cancel()
            self.throttleTickCallback = None
        return