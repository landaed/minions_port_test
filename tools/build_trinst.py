#!/usr/bin/env python3
"""Orchestrate the pure-Python conversion of a MoM zone for Godot assembly.

Parses the mission, converts the terrain (.ter -> .glb + heightmap PNG) and every
referenced TSStatic shape (.dts -> .glb), and writes a scene.json (the placement
manifest with a glb path attached to each static).

Usage: build_trinst.py [mission.mis] [out_dir]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for sub in ("mis", "ter", "dts", "dif"):
    sys.path.insert(0, str(HERE / sub))

from mis_parser import build_manifest          # noqa: E402
from ter_reader import read_ter, export_mesh_glb, export_heightmap_png  # noqa: E402
import dts_to_gltf                              # noqa: E402
import dif_to_gltf                              # noqa: E402


def _glb_name(path, marker):
    s = path.replace("\\", "/")
    if marker in s:
        s = s.split(marker)[-1]
    return s.replace("/", "_").rsplit(".", 1)[0] + ".glb"


def shape_glb_name(dts_path):
    return _glb_name(dts_path, "data/shapes/")


def main(mis, outdir):
    out = Path(outdir)
    (out / "shapes").mkdir(parents=True, exist_ok=True)
    game_root = Path(mis).resolve().parents[2]
    man = build_manifest(mis, game_root)

    # terrain
    terr = man["terrain"]
    ter_path = (Path(mis).parent / terr["file"].replace("./", "")).resolve()
    _v, heights, _layers = read_ter(ter_path)
    export_mesh_glb(heights, str(out / "terrain.glb"), square=terr["squareSize"])
    export_heightmap_png(heights, str(out / "terrain_height.png"))
    man["terrain_glb"] = (out / "terrain.glb").as_posix()
    man["terrain_grid"] = heights.shape[0]
    tdir = game_root / "data/terrains/mountain"
    man["terrain_textures"] = {
        "grass": (tdir / "grass01.jpg").as_posix(),
        "rock": (tdir / "rock009.jpg").as_posix(),
        "sand": (tdir / "sand006.jpg").as_posix(),
    }

    # shapes
    glbmap = {}
    fails = []
    for dts in man["referenced_shapes"]:
        if not Path(dts).exists():
            continue
        glb = out / "shapes" / shape_glb_name(dts)
        try:
            dts_to_gltf.convert(dts, str(glb))
            glbmap[dts] = glb.as_posix()
        except Exception as e:  # noqa: BLE001
            fails.append((dts, str(e)))
    for s in man["statics"]:
        s["glb"] = glbmap.get(s["shape"])

    # interiors (buildings)
    (out / "interiors").mkdir(parents=True, exist_ok=True)
    imap = {}
    ifails = []
    for dif in man["referenced_interiors"]:
        if not Path(dif).exists():
            continue
        glb = out / "interiors" / _glb_name(dif, "data/interiors/")
        try:
            dif_to_gltf.convert(dif, str(glb))
            imap[dif] = glb.as_posix()
        except Exception as e:  # noqa: BLE001
            ifails.append((dif, str(e)))
    for it in man["interiors"]:
        it["glb"] = imap.get(it["interior"])

    (out / "scene.json").write_text(json.dumps(man, indent=1))
    placed = sum(1 for s in man["statics"] if s["glb"])
    iplaced = sum(1 for it in man["interiors"] if it["glb"])
    print(f"terrain -> {out/'terrain.glb'}  grid={man['terrain_grid']}")
    print(f"shapes converted: {len(glbmap)}/{len(man['referenced_shapes'])}")
    print(f"statics with geometry: {placed}/{len(man['statics'])}")
    print(f"interiors converted: {len(imap)}/{len(man['referenced_interiors'])}")
    print(f"interiors placed: {iplaced}/{len(man['interiors'])}")
    if fails or ifails:
        print("failures:")
        for d, e in fails + ifails:
            print("  ", Path(d).name, "->", e)
    print("wrote", out / "scene.json")


if __name__ == "__main__":
    mis = sys.argv[1] if len(sys.argv) > 1 else \
        "MoMReborn/minions.of.mirth/data/missions/city.mis"
    outdir = sys.argv[2] if len(sys.argv) > 2 else "/tmp/trinst_build"
    main(mis, outdir)
