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
for sub in ("mis", "ter", "dts"):
    sys.path.insert(0, str(HERE / sub))

from mis_parser import build_manifest          # noqa: E402
from ter_reader import read_ter, export_mesh_glb, export_heightmap_png  # noqa: E402
import dts_to_gltf                              # noqa: E402


def shape_glb_name(dts_path):
    s = dts_path.replace("\\", "/")
    if "data/shapes/" in s:
        s = s.split("data/shapes/")[-1]
    return s.replace("/", "_").rsplit(".", 1)[0] + ".glb"


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

    (out / "scene.json").write_text(json.dumps(man, indent=1))
    placed = sum(1 for s in man["statics"] if s["glb"])
    print(f"terrain -> {out/'terrain.glb'}  grid={man['terrain_grid']}")
    print(f"shapes converted: {len(glbmap)}/{len(man['referenced_shapes'])}")
    print(f"statics with geometry: {placed}/{len(man['statics'])}")
    if fails:
        print("failures:")
        for d, e in fails:
            print("  ", Path(d).name, "->", e)
    print("wrote", out / "scene.json")


if __name__ == "__main__":
    mis = sys.argv[1] if len(sys.argv) > 1 else \
        "MoMReborn/minions.of.mirth/data/missions/city.mis"
    outdir = sys.argv[2] if len(sys.argv) > 2 else "/tmp/trinst_build"
    main(mis, outdir)
