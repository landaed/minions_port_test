#!/usr/bin/env python3
"""Parse a Torque .mis mission into a Godot-space placement manifest.

Walks the TorqueScript object tree and extracts the objects needed to assemble a
zone: terrain, sun, sky/fog, water, static shapes (TSStatic), interiors
(InteriorInstance), lights, audio emitters and particle emitter nodes. Converts
every transform from Torque (Z-up, right-handed) to Godot (Y-up):

    position (x, y, z) -> (x, z, -y)
    rotation axis-angle: axis -> (x, z, -y), angle unchanged
    scale (x, y, z) -> (x, z, y)

Usage: mis_parser.py <in.mis> [out.json]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

OBJ_RE = re.compile(r'^\s*new\s+([A-Za-z0-9_]+)\s*\(([^)]*)\)\s*\{')
PROP_RE = re.compile(r'^\s*([A-Za-z0-9_]+)(?:\[\d+\])?\s*=\s*"([^"]*)"\s*;')
CLOSE_RE = re.compile(r'^\s*\};')

WANT = {"TSStatic", "InteriorInstance", "Sun", "Sky", "WaterBlock", "TerrainBlock",
        "sgUniversalStaticLight", "fxSunLight", "AudioEmitter", "ParticleEmitterNode"}


def _floats(s):
    try:
        return [float(x) for x in s.split()]
    except ValueError:
        return []


def t2g_pos(p):
    return [p[0], p[2], -p[1]] if len(p) == 3 else [0, 0, 0]


def t2g_axis_angle(r):
    # "ax ay az angle_deg" -> godot axis (x, z, -y) + angle
    if len(r) != 4:
        return [0, 1, 0, 0]
    ax, ay, az, ang = r
    return [ax, az, -ay, ang]


def t2g_scale(s):
    return [s[0], s[2], s[1]] if len(s) == 3 else [1, 1, 1]


def parse_tree(path):
    """Return a flat list of objects: {class, name, props, depth}."""
    objs = []
    stack = []
    for line in Path(path).read_text(errors="ignore").splitlines():
        m = OBJ_RE.match(line)
        if m:
            obj = {"class": m.group(1), "name": m.group(2).strip(), "props": {}}
            stack.append(obj)
            continue
        m = PROP_RE.match(line)
        if m and stack:
            stack[-1]["props"][m.group(1)] = m.group(2)
            continue
        if CLOSE_RE.match(line) and stack:
            obj = stack.pop()
            obj["depth"] = len(stack)
            objs.append(obj)
    return objs


def resolve_ref(ref, root):
    return (root / ref.replace("~/", "").lstrip("./")).as_posix()


def build_manifest(mis_path, game_root):
    objs = parse_tree(mis_path)
    root = Path(game_root)
    man = {"mission": Path(mis_path).stem, "terrain": None, "sun": None, "sky": None,
           "water": [], "statics": [], "interiors": [], "lights": [], "audio": [],
           "particles": [], "referenced_shapes": set(), "referenced_interiors": set()}

    for o in objs:
        c, p = o["class"], o["props"]
        pos = t2g_pos(_floats(p.get("position", "")))
        rot = t2g_axis_angle(_floats(p.get("rotation", "")))
        scl = t2g_scale(_floats(p.get("scale", "1 1 1")))

        if c == "TSStatic" and "shapeName" in p:
            ref = resolve_ref(p["shapeName"], root)
            man["referenced_shapes"].add(ref)
            man["statics"].append({"name": o["name"], "shape": ref,
                                   "pos": pos, "rot": rot, "scale": scl})
        elif c == "InteriorInstance" and "interiorFile" in p:
            ref = resolve_ref(p["interiorFile"], root)
            man["referenced_interiors"].add(ref)
            man["interiors"].append({"name": o["name"], "interior": ref,
                                     "pos": pos, "rot": rot, "scale": scl})
        elif c == "TerrainBlock":
            man["terrain"] = {"file": p.get("terrainFile", ""),
                              "squareSize": float(p.get("squareSize", "8")),
                              "pos": pos}
        elif c == "Sun":
            man["sun"] = {"azimuth": float(p.get("azimuth", "0")),
                          "elevation": float(p.get("elevation", "45")),
                          "color": _floats(p.get("color", "1 1 1 1")),
                          "ambient": _floats(p.get("ambient", "0.3 0.3 0.3 1")),
                          "direction": _floats(p.get("direction", ""))}
        elif c == "Sky":
            man["sky"] = {"materialList": p.get("materialList", ""),
                          "fogDistance": float(p.get("fogDistance", "0") or 0),
                          "fogColor": _floats(p.get("fogColor", "0.6 0.6 0.6 1")),
                          "visibleDistance": float(p.get("visibleDistance", "0") or 0)}
        elif c == "WaterBlock":
            man["water"].append({"pos": pos, "scale": scl,
                                 "height": _floats(p.get("position", "0 0 0"))[2]
                                 if _floats(p.get("position", "")) else 0})
        elif c in ("sgUniversalStaticLight", "fxSunLight"):
            man["lights"].append({"pos": pos, "color": _floats(p.get("color", "1 1 1 1")),
                                  "radius": float(p.get("radius", "10") or 10)})
        elif c == "AudioEmitter":
            man["audio"].append({"pos": pos, "file": p.get("fileName", "")})
        elif c == "ParticleEmitterNode":
            man["particles"].append({"pos": pos, "datablock": p.get("datablock", ""),
                                     "emitter": p.get("emitter", "")})

    man["referenced_shapes"] = sorted(man["referenced_shapes"])
    man["referenced_interiors"] = sorted(man["referenced_interiors"])
    return man


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: mis_parser.py <in.mis> [out.json]")
    mis = sys.argv[1]
    game_root = Path(mis).resolve().parents[2]  # .../minions.of.mirth
    man = build_manifest(mis, game_root)
    print(f"mission '{man['mission']}'  root={game_root}")
    print(f"  statics={len(man['statics'])} (unique shapes={len(man['referenced_shapes'])})")
    print(f"  interiors={len(man['interiors'])} (unique={len(man['referenced_interiors'])})")
    print(f"  lights={len(man['lights'])} audio={len(man['audio'])} particles={len(man['particles'])}")
    print(f"  terrain={man['terrain']}")
    print(f"  sun={man['sun']}")
    miss = [s for s in man["referenced_shapes"] if not Path(s).exists()]
    print(f"  missing shape files: {len(miss)}")
    out = sys.argv[2] if len(sys.argv) > 2 else None
    if out:
        Path(out).write_text(json.dumps(man, indent=1))
        print("wrote", out)
