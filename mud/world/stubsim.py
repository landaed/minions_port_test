# Stub simulation objects for headless (no Torque engine) operation.
# When the pytge stub is in use, zones can't rely on the Torque game engine
# for physics, visibility, or bot spawning.  This module provides lightweight
# stand-ins so that the world server can bring zones "live", spawn mobs,
# and let the proxy's entity-snapshot polling work.

from twisted.internet import defer, reactor
from mud.world.core import CoreSettings
import traceback
from math import sqrt


_next_stub_id = 90000


def _alloc_id():
    global _next_stub_id
    _next_stub_id += 1
    return _next_stub_id


class StubSimObject:
    """Minimal stand-in for SimGhost (world-server side of a SimObject)."""

    def __init__(self, obj_id=None, position=None, rotation=None):
        self.id = obj_id or _alloc_id()
        self.position = tuple(position or (0.0, 0.0, 0.0))
        self.rotation = tuple(rotation or (0.0, 0.0, 0.0, 1.0))
        self.canSee = []
        self.simZombie = False
        self.canKite = False
        self.waterCoverage = 0.0
        self.rangedAttack = False
        self.dyingMob = None
        self.isPlayer = False

    def __repr__(self):
        return "StubSimObject(id=%s, pos=%s)" % (self.id, self.position)


def _parse_transform(transform):
    """Parse a transform into (position, rotation).

    *transform* may be a '0 0 0 1 0 0 0' string, a list/tuple of floats,
    or a ``map`` iterator (Python 3 property from Player.logTransform).
    """
    if not transform:
        return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0)
    if isinstance(transform, str):
        parts = [float(x) for x in transform.split()]
    else:
        parts = [float(x) for x in transform]
    pos = tuple(parts[:3]) if len(parts) >= 3 else (0.0, 0.0, 0.0)
    rot = tuple(parts[3:7]) if len(parts) >= 7 else (0.0, 0.0, 0.0, 1.0)
    return pos, rot


class StubSimAvatar:
    """Replaces SimAvatar + remote SimMind for headless zone operation.

    This object lives entirely inside the world-server process and handles
    the same interface that ``SimAvatar`` exposes, but without any PB
    connection to a zone-server process.
    """

    def __init__(self, world):
        self.world = world
        self.zone = None
        self.simLookup = {}
        self.simObjects = []
        self.playerLookup = {}
        self.mind = self          # self acts as its own "mind" for API compat

    # ---- helpers ----

    def addSimObject(self, so):
        self.simObjects.append(so)
        self.simLookup[so.id] = so

    def error(self, err):
        print("[StubSimAvatar] error:", err)

    # ---- SimAvatar interface used by zone / playeravatar ----

    def setDisplayName(self, player):
        pass  # no Torque client to update

    def sendWeather(self, weather):
        pass

    def setTarget(self, simObject, targetSimObject):
        pass

    def setFollowTarget(self, simObject, targetSimObject):
        pass

    def clearTarget(self, simObject):
        pass

    def immobilize(self, simObject):
        pass

    def deleteObject(self, simObject):
        try:
            self.simObjects.remove(simObject)
        except ValueError:
            pass
        self.simLookup.pop(simObject.id, None)

    def removePlayer(self, simObject):
        if not simObject:
            return
        self.playerLookup.pop(simObject, None)
        try:
            self.simObjects.remove(simObject)
        except ValueError:
            pass
        self.simLookup.pop(simObject.id, None)

    def setPlayerPasswords(self, passwords):
        return defer.succeed(True)

    def stop(self):
        pass

    def kickPlayer(self, player):
        pass

    def pause(self, pause):
        pass

    def setDeathMarker(self, publicName, charName, realm, pos, rot):
        pass

    def clearDeathMarker(self, publicName):
        pass

    def launchProjectile(self, p):
        pass

    def respawnPlayer(self, player, transform=None):
        if player.simObject and transform:
            pos, rot = _parse_transform(transform)
            player.simObject.position = pos
            player.simObject.rotation = rot
        return defer.succeed(True)

    # ---- bot spawning ----

    def spawnBot(self, spawn, transform, wanderGroup, mobInfo):
        """Create a stub sim object for a spawned mob."""
        pos, rot = _parse_transform(transform)
        so = StubSimObject(position=pos, rotation=rot)
        self.addSimObject(so)
        return defer.succeed(so)

    def botSpawned(self, bot):
        # Already added in spawnBot
        return bot

    # ---- spawnpoint / bindpoint loading (replaces remote calls to SimMind) ----

    def refreshBindpoints(self):
        # In the stub there is no mission file to query – just set empty
        if self.zone:
            self.zone.bindpoints = []

    def refreshSpawnPoints(self):
        """Load spawnpoints from the zone's SpawnGroups (DB) and feed them
        into the zone so it can start spawning mobs."""
        if not self.zone:
            return

        from mud.simulation.shared.simdata import SpawnpointInfo

        zone_obj = self.zone.zone  # the persistent Zone ORM object
        spawnpoints = []

        for sg in zone_obj.spawnGroups:
            for si in sg.spawninfos:
                spi = SpawnpointInfo()
                spi.group = sg.groupName
                spi.transform = si.transform if hasattr(si, 'transform') else "0 0 0 1 0 0 0"
                spi.wanderGroup = si.wanderGroup if hasattr(si, 'wanderGroup') else -1
                spawnpoints.append(spi)

        # Collect unique spawn names to send setSpawnInfos equivalent
        spawnnames = []
        for sp in spawnpoints:
            for g in zone_obj.spawnGroups:
                if sp.group == g.groupName:
                    for si in g.spawninfos:
                        s = si.spawn
                        if s.name not in spawnnames:
                            spawnnames.append(s.name)

        if spawnpoints:
            self.zone.createSpawnpoints(spawnpoints)

    # ---- visibility updates (replaces SimMind.updateCanSee) ----

    _VISIBILITY_RANGE_SQ = 500.0 * 500.0

    def _updateCanSee(self):
        """Periodically compute distance-based canSee for all sim objects."""
        try:
            objects = list(self.simObjects)
            player_count = 0
            for so in objects:
                if not so or not hasattr(so, 'position') or so.position is None:
                    continue
                visible = []
                for other in objects:
                    if other is so or not other or not hasattr(other, 'position') or other.position is None:
                        continue
                    dx = so.position[0] - other.position[0]
                    dy = so.position[1] - other.position[1]
                    dz = so.position[2] - other.position[2]
                    if dx * dx + dy * dy + dz * dz <= self._VISIBILITY_RANGE_SQ:
                        visible.append(other.id)
                if so.isPlayer and visible:
                    player_count += 1
                so.canSee = visible
            if not getattr(self, '_cansee_logged', False) and objects:
                print("[StubSimAvatar] _updateCanSee: %d objects, %d players with visible neighbors" % (len(objects), player_count))
                self._cansee_logged = True
        except Exception:
            traceback.print_exc()
        self._canSeeTick = reactor.callLater(2, self._updateCanSee)

    # ---- callRemote compatibility (when code calls self.mind.callRemote) ----

    def callRemote(self, method, *args, **kwargs):
        """Handle remote calls locally."""
        # setSelection: route to the sim brain (for NPC AI target setting)
        if method == "setSelection":
            srcId, tgtId, charIndex = args[0], args[1], args[2] if len(args) > 2 else 0
            src = self.simLookup.get(srcId)
            tgt = self.simLookup.get(tgtId) if tgtId else None
            if src and hasattr(src, 'brain'):
                src.brain.setTarget(tgt)
        return defer.succeed(None)

    # ---- start the zone ----

    def startZone(self, zoneInstanceName, pid=None):
        """Bring the zone live (replaces perspective_startSimulation)."""
        zinst = self.world.startSimulation(zoneInstanceName, pid)
        if not zinst:
            print("[StubSimAvatar] WARNING: startSimulation returned None for %s" % zoneInstanceName)
            return
        self.zone = zinst
        zinst.simAvatar = self

        self.refreshBindpoints()
        self.refreshSpawnPoints()

        zinst.start()
        print("[StubSimAvatar] Zone %s is live (headless stub)" % zoneInstanceName)
        # Start periodic canSee updates
        self._canSeeTick = reactor.callLater(3, self._updateCanSee)


def _is_stub_engine():
    """Return True if we are running with the pytge/pytorque stub."""
    try:
        import pytge
        # The real pytge is a C extension (.pyd); the stub is pure Python
        return not hasattr(pytge, '__file__') or (
            hasattr(pytge, '__file__') and pytge.__file__ and pytge.__file__.endswith('.py')
        )
    except ImportError:
        return True


def start_zones_headless(world):
    """For every zone sitting in *waitingZoneInstances*, create a
    StubSimAvatar and bring it live.  Call this from the world server
    after the normal zone-process spawn timeout."""
    for zinst in list(world.waitingZoneInstances):
        stub = StubSimAvatar(world)
        stub.startZone(zinst.name, pid=0)


def create_player_sim_object(player, zone):
    """Create a StubSimObject for a player entering a zone and wire
    everything up (mirrors SimAvatar.perspective_setPlayerSimObject)."""
    transform = player.logTransform
    if player.darkness:
        transform = player.darknessLogTransform
    elif player.monster:
        transform = player.monsterLogTransform

    pos, rot = _parse_transform(transform)
    so = StubSimObject(position=pos, rotation=rot)
    so.isPlayer = True
    player.simObject = so

    sim_avatar = zone.simAvatar
    sim_avatar.addSimObject(so)
    sim_avatar.playerLookup[so] = player

    # Now officially enter the zone
    zone.playerEnterZone(player)
