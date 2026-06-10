"""Read NPC/monster spawn markers from a Godot zone scene (.tscn).

The Godot editor is where spawn markers are authored (MoMSpawnPoint nodes under
the zone scene's "Spawns" node — see minions-port/world/spawn_point.gd). At zone
start the world server parses those nodes straight out of the .tscn text, so
marker placement is editor-driven while the server keeps authority over what
actually spawns (DB spawn groups), respawn timing, loot and AI.

Only plain text parsing of the narrow node shape the importer/editor produce is
attempted; anything unexpected is skipped. Falls back to the legacy .mis markers
upstream (stubsim.refreshSpawnPoints) when no scene markers are found.

Coordinate notes (must mirror the Godot client's conversions):
  godot (x, y, z) -> server (x, -z, y)          [server z is up]
  node yaw (radians about +Y) == mission true CCW angle about +Z; emitted here
  as axis-angle (0,0,1,yaw) to match misspawns.parse_spawn_points output, and
  later converted by stubsim._marker_rotation_to_sim like any mission marker.
"""
import os
import re
from math import atan2

DEFAULT_ZONE_DIR = os.path.join("minions-port", "world", "zones")

_NODE_RE = re.compile(r'\[node\s+(?P<header>[^\]]*)\](?P<body>[^\[]*)', re.DOTALL)
_ATTR_RE = re.compile(r'(\w+)="([^"]*)"')
_TRANSFORM_RE = re.compile(r'^transform\s*=\s*Transform3D\(([^)]*)\)', re.MULTILINE)
_PROP_STR_RE = {
    "spawn_group": re.compile(r'^spawn_group\s*=\s*"([^"]*)"', re.MULTILINE),
}
_PROP_NUM_RE = {
    "wander_group": re.compile(r'^wander_group\s*=\s*(-?\d+)', re.MULTILINE),
}
_PROP_BOOL_RE = {
    "enabled": re.compile(r'^enabled\s*=\s*(true|false)', re.MULTILINE),
}


def zone_scene_path(zone_name, zone_dir=None):
    base = zone_dir or os.environ.get("MOM_GODOT_ZONE_DIR", DEFAULT_ZONE_DIR)
    return os.path.join(base, "%s.tscn" % zone_name)


def parse_godot_spawnpoints(zone_name, zone_dir=None):
    """Return mission-marker dicts ({group, position, rotation, wanderGroup})
    for every enabled MoMSpawnPoint in the zone scene, or [] if the scene file
    is missing / has no Spawns markers."""
    path = zone_scene_path(zone_name, zone_dir)
    if not os.path.isfile(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            txt = f.read()
    except OSError:
        return []

    out = []
    for m in _NODE_RE.finditer(txt):
        attrs = dict(_ATTR_RE.findall(m.group("header")))
        if attrs.get("parent") != "Spawns":
            continue
        body = m.group("body")
        grp_m = _PROP_STR_RE["spawn_group"].search(body)
        if not grp_m or not grp_m.group(1):
            continue  # not a spawn point (or empty group)
        en_m = _PROP_BOOL_RE["enabled"].search(body)
        if en_m and en_m.group(1) == "false":
            continue
        pos = (0.0, 0.0, 0.0)
        yaw = 0.0
        t_m = _TRANSFORM_RE.search(body)
        if t_m:
            try:
                vals = [float(v) for v in t_m.group(1).split(",")]
            except ValueError:
                continue
            if len(vals) >= 12:
                gx, gy, gz = vals[9], vals[10], vals[11]
                pos = (gx, -gz, gy)
                # Basis rows are serialized row-major; for a yaw-only basis the
                # first row is (cos, 0, sin).
                yaw = atan2(vals[2], vals[0])
        wg_m = _PROP_NUM_RE["wander_group"].search(body)
        wander = int(wg_m.group(1)) if wg_m else -1
        out.append({
            "group": grp_m.group(1),
            "position": pos,
            "rotation": (0.0, 0.0, 1.0, yaw),
            "wanderGroup": wander,
        })
    return out
