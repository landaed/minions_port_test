# Stub simulation objects for headless (no Torque engine) operation.
# When the pytge stub is in use, zones can't rely on the Torque game engine
# for physics, visibility, or bot spawning.  This module provides lightweight
# stand-ins so that the world server can bring zones "live", spawn mobs,
# and let the proxy's entity-snapshot polling work.

from twisted.internet import defer, reactor
from mud.world.core import CoreSettings
import traceback
import os
import random
from math import sqrt, atan2, sin, cos


def _yaw_toward(dx, dy):
    """Compute a TGE axis-angle rotation facing direction (dx, dy) in server XY plane.

    Returns a Torque-style axis-angle (ax, ay, az, angle) for rotation around Z-up axis.
    TGE stores rotations as (axis_x, axis_y, axis_z, angle_radians), NOT quaternions.
    """
    angle = atan2(dx, dy)  # angle from +Y axis (server forward)
    # Axis is always Z (0, 0, 1) for yaw; sign of axis encodes direction
    if angle >= 0:
        return (0.0, 0.0, 1.0, angle)
    else:
        return (0.0, 0.0, -1.0, -angle)


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
        self.moveTarget = None   # StubSimObject to chase
        self.moveSpeed = 5.0     # units per second
        self._client_input = None  # movement input from Godot client (player only)

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
        simObject.moveTarget = targetSimObject

    def setFollowTarget(self, simObject, targetSimObject):
        simObject.moveTarget = targetSimObject

    def clearTarget(self, simObject):
        simObject.moveTarget = None

    def immobilize(self, simObject):
        simObject.moveTarget = None

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
        so._home = pos  # anchor for idle wander/patrol
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

        # Test-zone mode: skip the zone's ~160 DB-driven background spawns so the
        # single-threaded reactor isn't saturated simulating them. You're left
        # with just your player + the 3 test skeletons -> much higher replication
        # rate / smoother. Enable with MOM_TEST_ZONE=1 (or ./run_servers.sh --test-zone).
        if os.environ.get("MOM_TEST_ZONE"):
            print("[StubSimAvatar] MOM_TEST_ZONE set: skipping background spawns for %s" % self.zone.name)
            return

        from mud.simulation.shared.simdata import SpawnpointInfo

        zone_obj = self.zone.zone  # the persistent Zone ORM object
        db_groups = set()
        for sg in zone_obj.spawnGroups:
            db_groups.add(sg.groupName)
        spawnpoints = []

        # Recover the real per-marker spawn positions from the mission file. The
        # DB only has spawn *groups* (no positions) and the headless stub can't
        # query the Torque engine, so without this every NPC spawned at the origin
        # (far from the player) and was never streamed.
        markers = []
        try:
            from mud.world.misspawns import find_and_parse_spawn_points
            markers = find_and_parse_spawn_points(getattr(zone_obj, "missionFile", "") or "")
        except Exception:
            traceback.print_exc()

        used_groups = set()
        for mk in markers:
            if mk["group"] not in db_groups:
                continue
            px, py, pz = mk["position"]
            ax, ay, az, ang = mk["rotation"]
            spi = SpawnpointInfo()
            spi.group = mk["group"]
            spi.transform = "%g %g %g %g %g %g %g" % (px, py, pz, ax, ay, az, ang)
            spi.wanderGroup = mk["wanderGroup"]
            spawnpoints.append(spi)
            used_groups.add(mk["group"])

        if spawnpoints:
            print("[StubSimAvatar] %s: %d mission spawn points across %d groups" % (
                self.zone.name, len(spawnpoints), len(used_groups)))
        else:
            # Fallback: no mission markers found — keep the old DB-at-origin
            # behaviour rather than spawning nothing.
            print("[StubSimAvatar] %s: no mission spawn points; falling back to DB groups at origin" % self.zone.name)
            for sg in zone_obj.spawnGroups:
                for si in sg.spawninfos:
                    spi = SpawnpointInfo()
                    spi.group = sg.groupName
                    spi.transform = si.transform if hasattr(si, "transform") else "0 0 0 1 0 0 0"
                    spi.wanderGroup = si.wanderGroup if hasattr(si, "wanderGroup") else -1
                    spawnpoints.append(spi)

        if spawnpoints:
            self.zone.createSpawnpoints(spawnpoints)

    # ---- visibility updates (replaces SimMind.updateCanSee) ----

    _VISIBILITY_RANGE_SQ = 500.0 * 500.0
    # The headless sim has no Torque BSP/portal LOS queries, so a pure radius
    # test makes NPCs on stacked tower floors see guards directly below them.
    # They then aggro/chase through the floor and get replicated on the ground.
    # Treat close horizontal / large vertical gaps as different visibility layers
    # (floors) while preserving normal long-range outdoor visibility over hills.
    _VISIBILITY_LAYER_RADIUS_SQ = 35.0 * 35.0
    _VISIBILITY_LAYER_MAX_DZ = 12.0

    def _same_visibility_layer(self, dx, dy, dz):
        if dx * dx + dy * dy <= self._VISIBILITY_LAYER_RADIUS_SQ:
            return abs(dz) <= self._VISIBILITY_LAYER_MAX_DZ
        return True

    def _updateCanSee(self):
        """Compute distance-based canSee for every sim object.

        Both the player snapshot (getVisibleEntities) AND mob AI need this: the
        tactical brain scans ``mob.simObject.canSee`` to find aggro targets, so
        mobs with an empty canSee never aggro or chase. Kept O(n^2) but with a
        squared-distance test and minimal attribute work."""
        try:
            objects = [so for so in self.simObjects
                       if so and getattr(so, 'position', None) is not None]
            rng = self._VISIBILITY_RANGE_SQ
            for so in objects:
                spos = so.position
                sx, sy, sz = spos[0], spos[1], spos[2]
                visible = []
                for other in objects:
                    if other is so:
                        continue
                    opos = other.position
                    dx = sx - opos[0]
                    dy = sy - opos[1]
                    dz = sz - opos[2]
                    in_range = dx * dx + dy * dy + dz * dz <= rng
                    if in_range and self._same_visibility_layer(dx, dy, dz):
                        visible.append(other.id)
                so.canSee = visible
            if not getattr(self, '_cansee_logged', False) and objects:
                print("[StubSimAvatar] _updateCanSee: %d objects scanned" % len(objects))
                self._cansee_logged = True
        except Exception:
            traceback.print_exc()
        self._canSeeTick = reactor.callLater(1, self._updateCanSee)

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
        # Start periodic canSee updates (soon, so mobs become visible fast)
        self._canSeeTick = reactor.callLater(0.5, self._updateCanSee)
        # Start NPC movement simulation
        self._moveTick = reactor.callLater(3, self._updateMovement)

    # ---- NPC movement simulation ----

    _MOVE_INTERVAL = 0.05  # seconds between movement ticks (50ms, matches client input sync)
    _ARRIVE_DIST = 2.5     # stop this far from target (melee range)
    # Idle-NPC wander/patrol: mill about near the spawn so the world feels alive.
    # (The original engine drove waypoint patrols; that lived in Torque, so this
    # is a lightweight stand-in until a navmesh-based path system exists.)
    _WANDER_RADIUS = 10.0    # max distance from home a wander point can be
    _WANDER_MIN = 3.0        # min distance so steps are worth taking
    _WANDER_ARRIVE = 1.0     # consider a wander point reached within this
    _WANDER_SPEED = 2.2      # slow stroll (client shows the walk, not run, anim)
    _WANDER_PAUSE_MIN = 1.5  # pause range between wander legs (seconds)
    _WANDER_PAUSE_MAX = 5.0

    _PLAYER_MOVE_SPEED = 8.0  # units/sec, should match Godot client MOVE_SPEED

    def _updateMovement(self):
        """Move NPCs toward their targets and process player input."""
        try:
            dt = self._MOVE_INTERVAL
            moved = 0
            for so in list(self.simObjects):
                if so.isPlayer:
                    # Process player movement from client inputs
                    self._processPlayerInput(so, dt)
                    # Auto-face the selected target so player melee isn't silently
                    # blocked by the combat facing check.
                    self._facePlayerTarget(so)
                    continue
                tgt = getattr(so, 'moveTarget', None)
                if not tgt:
                    # No combat target: idle NPCs wander/patrol near their spawn.
                    if self._wanderStep(so, dt):
                        moved += 1
                    continue
                if not hasattr(tgt, 'position') or tgt.position is None:
                    continue
                dx = tgt.position[0] - so.position[0]
                dy = tgt.position[1] - so.position[1]
                dz = tgt.position[2] - so.position[2]
                if not self._same_visibility_layer(dx, dy, dz):
                    # The radius-only stub LOS can leave pre-fix saves with an
                    # invalid cross-floor target. Drop it instead of flying the
                    # NPC down/up through tower floors toward guards/players.
                    so.moveTarget = None
                    continue
                dist = sqrt(dx * dx + dy * dy + dz * dz)
                # Always face target, even when arrived
                if abs(dx) > 0.01 or abs(dy) > 0.01:
                    so.rotation = _yaw_toward(dx, dy)
                if dist <= self._ARRIVE_DIST:
                    continue
                # Move toward target at moveSpeed units/sec
                speed = getattr(so, 'moveSpeed', 5.0)
                step = min(speed * dt, dist - self._ARRIVE_DIST)
                factor = step / dist
                so.position = (
                    so.position[0] + dx * factor,
                    so.position[1] + dy * factor,
                    so.position[2] + dz * factor,
                )
                moved += 1
            if moved and not getattr(self, '_move_logged', False):
                self._move_logged = True
                print("[StubSimAvatar] _updateMovement: moved %d NPCs" % moved)
        except Exception:
            traceback.print_exc()
        self._moveTick = reactor.callLater(self._MOVE_INTERVAL, self._updateMovement)

    def _wanderStep(self, so, dt):
        """Idle wander/patrol around the spawn home. Returns True if the NPC moved.
        Only the horizontal plane (x,y) changes; height is left to the client's
        ground-snap. Combat (moveTarget) always overrides this."""
        home = getattr(so, '_home', None)
        if home is None:
            home = so.position
            so._home = home
        now = reactor.seconds()
        wt = getattr(so, '_wanderTarget', None)
        if wt is None:
            if now < getattr(so, '_wanderPauseUntil', 0.0):
                return False
            ang = random.uniform(0.0, 6.2831853)
            rad = random.uniform(self._WANDER_MIN, self._WANDER_RADIUS)
            wt = (home[0] + cos(ang) * rad, home[1] + sin(ang) * rad, so.position[2])
            so._wanderTarget = wt
        dx = wt[0] - so.position[0]
        dy = wt[1] - so.position[1]
        dist = sqrt(dx * dx + dy * dy)
        if dist <= self._WANDER_ARRIVE:
            so._wanderTarget = None
            so._wanderPauseUntil = now + random.uniform(self._WANDER_PAUSE_MIN, self._WANDER_PAUSE_MAX)
            return False
        so.rotation = _yaw_toward(dx, dy)
        step = min(self._WANDER_SPEED * dt, dist - self._WANDER_ARRIVE)
        factor = step / dist if dist > 0 else 0.0
        so.position = (
            so.position[0] + dx * factor,
            so.position[1] + dy * factor,
            so.position[2],
        )
        return True

    def _facePlayerTarget(self, so):
        """Auto-face the player's selected target so melee isn't silently inhibited
        by the combat facing check (camera facing alone often isn't aimed at the
        target). Mirrors how NPCs auto-face their chase target. Runs every tick,
        independent of client input, so a stationary auto-attacker still faces."""
        tgt = getattr(so, "moveTarget", None)
        if tgt is None or getattr(tgt, "position", None) is None:
            return
        dx = tgt.position[0] - so.position[0]
        dy = tgt.position[1] - so.position[1]
        if abs(dx) > 0.01 or abs(dy) > 0.01:
            so.rotation = _yaw_toward(dx, dy)

    def _processPlayerInput(self, so, dt):
        """Process client movement inputs and update player simObject position.

        Server is authoritative — it applies movement based on the input
        state received from the Godot client.
        """
        client_input = getattr(so, '_client_input', None)
        if not client_input:
            return
        forward = client_input.get("forward", (0, 0, 0))
        # Always update rotation from facing direction (player can turn in place)
        fx, fy, fz = float(forward[0]), float(forward[1]), float(forward[2])
        f_len = sqrt(fx * fx + fy * fy)
        if f_len > 0.001:
            so.rotation = _yaw_toward(fx / f_len, fy / f_len)
        move_x = client_input.get("move_x", 0.0)
        move_y = client_input.get("move_y", 0.0)
        if abs(move_x) < 0.01 and abs(move_y) < 0.01:
            return
        # fx, fy already normalized above; compute right vector for strafing
        nfx = fx / f_len if f_len > 0.001 else 0.0
        nfy = fy / f_len if f_len > 0.001 else 0.0
        rx, ry = nfy, -nfx  # cross product of forward with up=[0,0,1]
        # Combine: move_y is forward/back, move_x is strafe left/right
        dx = nfx * move_y + rx * move_x
        dy = nfy * move_y + ry * move_x
        # Normalize diagonal movement
        mag = sqrt(dx * dx + dy * dy)
        if mag > 1.0:
            dx /= mag
            dy /= mag
        speed = self._PLAYER_MOVE_SPEED
        # The headless server does not own Godot collision, but it still needs to
        # replicate vertical placement for stairs and multi-story interiors. Trust
        # the client's collider-resolved Z when present; otherwise preserve the old
        # vertical coordinate for compatibility with non-Godot callers/tests.
        z = client_input.get("position_z", so.position[2])
        so.position = (
            so.position[0] + dx * speed * dt,
            so.position[1] + dy * speed * dt,
            float(z),
        )


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

    # Spawn test mobs near the player shortly after entry (kept brief so they
    # don't "pop in" several seconds late).
    from twisted.internet import reactor
    reactor.callLater(0.5, spawn_test_mobs, zone, pos)


def spawn_test_mobs(zone, player_pos):
    """Spawn aggressive test mob(s) near a player position for combat testing.

    Defaults to a single skeleton so combat is easy to follow; set the
    MOM_TEST_MOB_COUNT env var (1-3) to spawn more for stress testing.
    """
    from mud.world.spawn import Spawn
    import traceback
    import os

    # Guard against double-spawn (e.g. if the player re-enters the zone) so we
    # don't end up with overlapping duplicate skeletons.
    if getattr(zone, '_test_mobs_spawned', False):
        return
    zone._test_mobs_spawned = True

    # Offsets from the player position (x, y, z) — place them ~8-10 units away.
    # Only the first N (MOM_TEST_MOB_COUNT, default 1) are used.
    all_offsets = [
        (8.0, 0.0, 0.0),
        (-5.0, 7.0, 0.0),
        (-5.0, -7.0, 0.0),
    ]
    try:
        mob_count = int(os.environ.get("MOM_TEST_MOB_COUNT", "1"))
    except (TypeError, ValueError):
        mob_count = 1
    mob_count = max(1, min(mob_count, len(all_offsets)))
    offsets = all_offsets[:mob_count]

    try:
        # "Skeleton" is level 3, realm=Monster(3), flags=128(AGGRESSIVE), aggroRange=20
        con = Spawn._connection.getConnection()
        row = con.execute(
            "SELECT id FROM spawn WHERE lower(name)='skeleton' LIMIT 1;"
        ).fetchone()
        if not row:
            print("[spawn_test_mobs] WARNING: Spawn 'Skeleton' not found in DB")
            return
        spawn = Spawn.get(row[0])
        print("[spawn_test_mobs] Using spawn: %s (level=%d, realm=%d, flags=%d, aggroRange=%d)" % (
            spawn.name, spawn.plevel, spawn.realm, spawn.flags, spawn.aggroRange))
    except Exception:
        traceback.print_exc()
        return

    spawned = 0
    for i, (ox, oy, oz) in enumerate(offsets):
        try:
            x = player_pos[0] + ox
            y = player_pos[1] + oy
            z = player_pos[2] + oz
            transform = (x, y, z, 0.0, 0.0, 0.0, 1.0)

            mob = zone.spawnMob(spawn, transform, -1)
            spawned += 1
            print("[spawn_test_mobs] Spawned '%s' #%d at (%.1f, %.1f, %.1f)" % (
                spawn.name, mob.id, x, y, z))
        except Exception:
            traceback.print_exc()

    print("[spawn_test_mobs] Spawned %d/%d test mob(s) near player at (%.1f, %.1f, %.1f)" % (
        spawned, len(offsets), player_pos[0], player_pos[1], player_pos[2]))
