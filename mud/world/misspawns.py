"""Parse NPC spawn-point markers from a Torque .mis mission file.

The headless stub sim has no Torque engine to query for rpgSpawnPoint object
transforms, and the world DB carries spawn *groups* but not their positions —
those live only in the mission file. Without them every NPC spawns at the world
origin (far from the player) and is never streamed. This recovers the real
positions so the zone's guards/vendors/monsters spawn where they belong.

Pure text parsing; no Torque dependency.
"""
import os
import re
from math import radians

_BLOCK_RE = re.compile(r'new\s+rpgSpawnPoint\s*\([^)]*\)\s*\{(.*?)\};', re.DOTALL)


def _field(body, name):
    m = re.search(r'%s\s*=\s*"([^"]*)"' % name, body)
    return m.group(1) if m else None


def parse_spawn_points(mis_path):
    """Return a list of {group, position:(x,y,z), rotation:(ax,ay,az,angle_rad),
    wanderGroup:int}. Rotation angle is converted from .mis degrees to radians
    (the convention the world server / client use). Positions stay in Torque
    world space (z = height), matching the rest of the sim."""
    out = []
    try:
        txt = open(mis_path, encoding="latin-1").read()
    except Exception:
        return out
    for m in _BLOCK_RE.finditer(txt):
        body = m.group(1)
        grp = _field(body, "SpawnGroup")
        pos = _field(body, "position")
        if not grp or not pos:
            continue
        rot = _field(body, "rotation")
        wg = _field(body, "WanderGroup")
        try:
            p = tuple(float(x) for x in pos.split())[:3]
        except ValueError:
            continue
        if len(p) < 3:
            continue
        r = (0.0, 0.0, 1.0, 0.0)
        if rot:
            try:
                rv = tuple(float(x) for x in rot.split())
                if len(rv) >= 4:
                    r = (rv[0], rv[1], rv[2], radians(rv[3]))
            except ValueError:
                pass
        try:
            wgi = int(float(wg)) if wg else -1
        except ValueError:
            wgi = -1
        out.append({"group": grp, "position": p, "rotation": r, "wanderGroup": wgi})
    return out


def _candidates(mission_file):
    bases = []
    if mission_file:
        cleaned = mission_file.replace("~/", "").replace("~", "")
        bases = [mission_file, cleaned, os.path.basename(mission_file)]
    else:
        bases = ["city.mis"]
    roots = [
        "",
        "minions.of.mirth/",
        "MoMReborn/minions.of.mirth/",
        "minions.of.mirth/data/missions/",
        "MoMReborn/minions.of.mirth/data/missions/",
        "data/missions/",
    ]
    seen, out = set(), []
    for b in bases:
        bn = os.path.basename(b)
        for r in roots:
            for cand in (os.path.join(r, b), os.path.join(r, bn)):
                if cand not in seen:
                    seen.add(cand)
                    out.append(cand)
    return out


def find_and_parse_spawn_points(mission_file):
    """Locate the mission file (trying several data roots) and parse it."""
    for p in _candidates(mission_file):
        if os.path.isfile(p):
            pts = parse_spawn_points(p)
            if pts:
                return pts
    return []
