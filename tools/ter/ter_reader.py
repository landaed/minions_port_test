#!/usr/bin/env python3
"""Reader for Torque Game Engine terrain (.ter, version 4) as used by MoM.

Layout: u8 version, then a 256x256 little-endian u16 heightmap, then per-layer
material/alpha maps, then a tab/newline texture-layer script in the tail.

Heights convert to meters with TGE's 1/32 fixed-point scale; horizontal spacing
is the mission's squareSize (8 m for Trinst), so the field is 2048 m across.

Exports a verification mesh (.glb) and a 16-bit heightmap PNG (for Terrain3D).

Usage: ter_reader.py <in.ter> <out.glb> [out_height.png] [square_size]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "dts"))
from dts_to_gltf import GLB  # noqa: E402

GRID = 256
HEIGHT_SCALE = 1.0 / 32.0  # TGE fixed-point: u16 height -> meters


def read_ter(path):
    d = Path(path).read_bytes()
    version = d[0]
    heights = (np.frombuffer(d, "<u2", GRID * GRID, 1)
               .astype(np.float32).reshape(GRID, GRID))
    layers = [m.decode("latin-1") for m in
              re.findall(rb"minions\.of\.mirth/data/terrains/[^\t\\\n\"]+", d)]
    return version, heights, layers


def export_heightmap_png(heights, path):
    from PIL import Image
    Image.fromarray(heights.astype(np.uint16), mode="I;16").save(path)


def export_mesh_glb(heights, path, square=8.0, scale=HEIGHT_SCALE):
    g = heights.shape[0]
    gx, gy = np.meshgrid(np.arange(g), np.arange(g))
    # Torque (x, y, height) -> Godot Y-up (x, height, -y)
    pos = np.stack([(gx * square),
                    (heights * scale),
                    (-gy * square)], axis=-1).reshape(-1, 3).astype("<f4")

    hy, hx = np.gradient(heights)
    nrm = np.stack([-scale * hx,
                    np.full_like(hx, square),
                    scale * hy], axis=-1).reshape(-1, 3)
    nrm /= (np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-9)
    nrm = nrm.astype("<f4")

    r, c = np.meshgrid(np.arange(g - 1), np.arange(g - 1), indexing="ij")
    v00 = (r * g + c).ravel(); v01 = (r * g + c + 1).ravel()
    v10 = ((r + 1) * g + c).ravel(); v11 = ((r + 1) * g + c + 1).ravel()
    # wind triangles so faces point up (front-facing from above)
    tris = np.concatenate([np.stack([v00, v11, v10], 1),
                           np.stack([v00, v01, v11], 1)], 1).reshape(-1).astype("<u4")

    glb = GLB()
    bv = glb._view(pos.tobytes(), 34962)
    glb.accessors.append({"bufferView": bv, "componentType": 5126, "count": len(pos),
                          "type": "VEC3", "min": pos.min(0).tolist(), "max": pos.max(0).tolist()})
    pos_acc = len(glb.accessors) - 1
    bv = glb._view(nrm.tobytes(), 34962)
    glb.accessors.append({"bufferView": bv, "componentType": 5126, "count": len(nrm), "type": "VEC3"})
    nrm_acc = len(glb.accessors) - 1
    bv = glb._view(tris.tobytes(), 34963)
    glb.accessors.append({"bufferView": bv, "componentType": 5125, "count": len(tris), "type": "SCALAR"})
    idx_acc = len(glb.accessors) - 1

    mat = glb.material("terrain")
    prim = {"attributes": {"POSITION": pos_acc, "NORMAL": nrm_acc},
            "indices": idx_acc, "material": mat, "mode": 4}
    glb.save(path, [prim], mesh_name="city_terrain")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit("usage: ter_reader.py <in.ter> <out.glb> [height.png] [square]")
    inp, outglb = sys.argv[1], sys.argv[2]
    square = float(sys.argv[4]) if len(sys.argv) > 4 else 8.0
    version, heights, layers = read_ter(inp)
    lo, hi = heights.min() * HEIGHT_SCALE, heights.max() * HEIGHT_SCALE
    print(f"ter v{version}  grid={heights.shape}  square={square}m  "
          f"world={GRID * square:.0f}m  height={lo:.1f}..{hi:.1f}m (relief {hi - lo:.1f}m)")
    print("layers:", layers)
    export_mesh_glb(heights, outglb, square=square)
    print("wrote", outglb)
    if len(sys.argv) > 3:
        export_heightmap_png(heights, sys.argv[3])
        print("wrote", sys.argv[3])
