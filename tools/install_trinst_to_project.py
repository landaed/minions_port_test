#!/usr/bin/env python3
"""Copy the converted Trinst build into the Godot project and rewrite scene.json
with res://-relative asset paths plus a player spawn point.

Reads /tmp/trinst_build (produced by build_trinst.py) and populates
minions-port/assets/trinst/ so the project can load Trinst with load("res://...").
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

SRC = Path("/tmp/trinst_build")
DST = Path("minions-port/assets/trinst")


def main():
    data = json.loads((SRC / "scene.json").read_text())
    for sub in ("shapes", "interiors", "textures"):
        (DST / sub).mkdir(parents=True, exist_ok=True)

    shutil.copy2(SRC / "terrain.glb", DST / "terrain.glb")
    data["terrain_glb"] = "terrain.glb"

    tt = {}
    for key, p in data.get("terrain_textures", {}).items():
        name = Path(p).name
        shutil.copy2(p, DST / "textures" / name)
        tt[key] = "textures/" + name
    data["terrain_textures"] = tt

    for s in data.get("statics", []):
        g = s.get("glb")
        if not g:
            continue
        shutil.copy2(g, DST / "shapes" / Path(g).name)
        s["glb"] = "shapes/" + Path(g).name
    for it in data.get("interiors", []):
        g = it.get("glb")
        if not g:
            continue
        shutil.copy2(g, DST / "interiors" / Path(g).name)
        it["glb"] = "interiors/" + Path(g).name

    # spawn above the city: centroid of building positions, above rooftops
    pts = [it["pos"] for it in data.get("interiors", []) if it.get("glb")]
    if pts:
        cx = sum(p[0] for p in pts) / len(pts)
        cy = max(p[1] for p in pts)
        cz = sum(p[2] for p in pts) / len(pts)
        data["spawn"] = [cx, cy + 25.0, cz]

    (DST / "scene.json").write_text(json.dumps(data, indent=1))
    n_glb = len(list((DST / "shapes").glob("*.glb"))) + len(list((DST / "interiors").glob("*.glb"))) + 1
    print(f"installed {n_glb} glb + {len(tt)} terrain textures to {DST}")
    print("spawn =", data.get("spawn"))


if __name__ == "__main__":
    main()
