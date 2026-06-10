#!/usr/bin/env python3
"""Export legacy mission spawn markers (plus DB preview info) to a JSON file
that minions-port/tools/import_spawn_points.gd bakes into the zone scene as
editable MoMSpawnPoint nodes.

This is a ONE-TIME (or occasional) import aid: after baking, the Godot zone
scene becomes the authoritative source of spawn-marker positions (the server
reads them directly from the .tscn via mud/world/godotspawns.py). Re-running
the bake replaces the Spawns node, so only re-run if you want to reset to the
legacy mission layout.

Usage:
  ./venv/bin/python tools/godot_spawns.py --zone trinst [--out /tmp/mom_spawn_import.json]
"""
import argparse
import json
import os
import sqlite3
import sys
from math import atan2, cos, sin

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mud.world.misspawns import find_and_parse_spawn_points

WORLD_DB_CANDIDATES = [
    "data/worlds/multiplayer.baseline/world.db",
    "MoMReborn/minions.of.mirth/data/worlds/multiplayer.baseline/world.db",
]


def world_db_path():
    for p in WORLD_DB_CANDIDATES:
        if os.path.isfile(p):
            return p
    raise SystemExit("world.db not found (tried %s)" % WORLD_DB_CANDIDATES)


def load_group_info(db, zone_name):
    """Map group_name -> preview info from the spawn DB (read-only)."""
    cur = db.cursor()
    row = cur.execute("SELECT id, mission_file FROM zone WHERE name=?", (zone_name,)).fetchone()
    if not row:
        raise SystemExit("zone '%s' not found in world.db" % zone_name)
    zone_id, mission_file = row
    info = {}
    q = """
      SELECT sg.group_name, s.name, s.model, s.scale, s.respawn_timer, si.frequency, s.plevel,
             s.race, s.sex
      FROM spawn_group sg
      JOIN spawn_group_spawn_info sgsi ON sgsi.spawn_group_id = sg.id
      JOIN spawn_info si ON si.id = sgsi.spawn_info_id
      JOIN spawn s ON s.id = si.spawn_id
      WHERE sg.zone_id = ?
      ORDER BY sg.group_name, si.frequency
    """
    try:
        rows = cur.execute(q, (zone_id,)).fetchall()
    except sqlite3.OperationalError:
        # plevel column name varies across kit versions; retry without it
        q = q.replace(", s.plevel", ", 0")
        rows = cur.execute(q, (zone_id,)).fetchall()
    for group, name, model, scale, respawn, freq, plevel, race, sex in rows:
        if not model and race:
            # Same fallback the client uses: race+sex glb (e.g. human_male).
            s = "female" if (sex or "").lower().startswith("f") else "male"
            model = "%s_%s" % ((race or "").lower().replace(" ", ""), s)
        e = info.setdefault(group, {"spawns": [], "respawn": 0})
        e["spawns"].append({"name": name, "model": model or "", "scale": scale or 1.0,
                            "freq": freq, "level": plevel})
        if respawn:
            e["respawn"] = max(e["respawn"], int(respawn))
    return mission_file, info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zone", default="trinst")
    ap.add_argument("--out", default="/tmp/mom_spawn_import.json")
    args = ap.parse_args()

    db = sqlite3.connect("file:%s?mode=ro" % world_db_path(), uri=True)
    mission_file, group_info = load_group_info(db, args.zone)
    markers = find_and_parse_spawn_points(mission_file)
    if not markers:
        raise SystemExit("no spawn markers parsed from mission '%s'" % mission_file)

    points = []
    missing_groups = set()
    for mk in markers:
        grp = mk["group"]
        sx, sy, sz = mk["position"]
        ax, ay, az, ang = mk["rotation"]
        # Mission rotation: axis-angle (radians after parse); true CCW yaw about
        # +Z carries the sign of the Z axis component. Godot node yaw (about +Y,
        # with -Z forward) uses the same signed angle (see _server_rotation_to_
        # godot_y / _marker_rotation_to_sim round trip).
        yaw = ang if az >= 0.0 else -ang
        gi = group_info.get(grp)
        preview = {"name": "", "model": "", "scale": 1.0, "info": ""}
        if gi:
            spawns = gi["spawns"]
            main_spawn = spawns[0]
            preview["name"] = main_spawn["name"]
            preview["model"] = main_spawn["model"]
            preview["scale"] = float(main_spawn["scale"])
            bits = []
            if main_spawn.get("level"):
                bits.append("Lv%s" % main_spawn["level"])
            if gi["respawn"]:
                bits.append("respawn %ds" % gi["respawn"])
            if len(spawns) > 1:
                bits.append("+%d variants" % (len(spawns) - 1))
            preview["info"] = "  ".join(bits)
        else:
            missing_groups.add(grp)
            preview["info"] = "group NOT in DB (ignored by server)"
        points.append({
            "group": grp,
            "godot_position": [sx, sz, -sy],
            "godot_yaw": yaw,
            "wander_group": mk["wanderGroup"],
            "preview": preview,
        })

    out = {"zone": args.zone, "points": points}
    with open(args.out, "w") as f:
        json.dump(out, f, indent=1)
    print("[godot_spawns] %s: wrote %d markers (%d groups) -> %s" % (
        args.zone, len(points), len({p['group'] for p in points}), args.out))
    if missing_groups:
        print("[godot_spawns] note: %d marker groups not in DB (kept, server will skip): %s" % (
            len(missing_groups), ", ".join(sorted(missing_groups)[:8]) + ("..." if len(missing_groups) > 8 else "")))


if __name__ == "__main__":
    main()
