#!/usr/bin/env python3
"""Convert a Torque DIF interior (MoM: difVersion 44 / interiorVersion 0) to glTF.

Parses the interior geometry up to and including the surfaces (points, planes,
normals, texgen equations, material list, windings, surfaces), triangulates each
surface's winding strip, projects texture UVs from the texgen planes, converts
Torque Z-up to Godot Y-up, resolves material textures, and writes a .glb.

Read order / struct layouts follow Torque's Interior::read, cross-checked against
the MIT-licensed RandomityGuy/hxDIF reference. MoM interiors are interiorVersion 0,
so the many version>=N gates collapse to the base layout.

Usage: dif_to_gltf.py <in.dif> <out.glb>
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "dts"))
from dts_to_gltf import GLB, embed_material_texture, axis  # noqa: E402

RESERVED_MATERIALS = {"NULL", "ORIGIN", "TRIGGER", "FORCEFIELD"}


class R:
    def __init__(self, data, off=0):
        self.d = data
        self.o = off

    def u8(self):
        v = self.d[self.o]; self.o += 1; return v

    def s16(self):
        v = struct.unpack_from("<h", self.d, self.o)[0]; self.o += 2; return v

    def u16(self):
        v = struct.unpack_from("<H", self.d, self.o)[0]; self.o += 2; return v

    def s32(self):
        v = struct.unpack_from("<i", self.d, self.o)[0]; self.o += 4; return v

    def u32(self):
        v = struct.unpack_from("<I", self.d, self.o)[0]; self.o += 4; return v

    def f32(self):
        v = struct.unpack_from("<f", self.d, self.o)[0]; self.o += 4; return v

    def vec3(self):
        return (self.f32(), self.f32(), self.f32())

    def pstr(self):
        # DIF strings are length-prefixed (U8 length + chars), not null-terminated
        n = self.d[self.o]; self.o += 1
        s = self.d[self.o:self.o + n].decode("latin-1"); self.o += n
        return s

    def array(self, fn):
        n = self.s32()
        return [fn() for _ in range(n)]

    def array_as(self, fn):
        n = self.s32()
        if n & 0x80000000:
            n &= 0x7FFFFFFF
            self.u8()  # param byte (width selector); MoM v0 uses default width
        return [fn() for _ in range(n)]


def parse_interior(data, off):
    r = R(data, off)
    iv = r.s32()                 # interiorVersion (0 for MoM)
    r.s32()                      # detailLevel
    r.s32()                      # minPixels
    [r.f32() for _ in range(6)]  # bounding box
    [r.f32() for _ in range(4)]  # bounding sphere
    r.u8()                       # hasAlarmState
    r.s32()                      # numLightStateEntries

    normals = r.array(r.vec3)
    planes = r.array(lambda: (r.s16(), r.f32()))      # normalIndex, distance
    points = r.array(r.vec3)
    r.array(r.u8)                                     # point visibility
    texgens = r.array(lambda: tuple(r.f32() for _ in range(8)))
    r.array(lambda: (r.u16(), r.u16(), r.u16()))      # BSP nodes
    r.array(lambda: (r.s32(), r.s16()))               # BSP solid leaves
    r.u8()                                            # material list version
    materials = r.array(r.pstr)
    windings = r.array_as(r.u32)                      # point indices
    r.array(lambda: (r.s32(), r.s32()))               # winding indices
    # edges: version >= 12 only -> skipped at v0
    r.array(lambda: (r.u16(), r.u16(), r.s32(), r.u16(), r.u16()))  # zones
    r.array_as(r.u16)                                 # zone surfaces
    r.array_as(r.u16)                                 # zone portal list
    r.array(lambda: (r.u16(), r.u16(), r.s32(), r.u16(), r.u16()))  # portals

    surfaces = []
    n = r.s32()
    for _ in range(n):
        wstart = r.s32()
        wcount = r.u8()
        plane_idx = r.u16()
        tex_idx = r.u16()
        texgen_idx = r.s32()
        r.u8()              # surfaceFlags
        r.s32()             # fanMask
        r.s16()             # lightmap finalWord
        r.f32(); r.f32()    # lightmap texgen X/Y distance
        r.s16()             # lightCount
        r.s32()             # lightStateInfoStart
        r.u8(); r.u8(); r.u8(); r.u8()  # map offset/size (byte each, non-large lightmaps)
        surfaces.append({"wstart": wstart, "wcount": wcount,
                         "plane": plane_idx, "tex": tex_idx, "texgen": texgen_idx})

    return {"version": iv, "points": points, "planes": planes, "normals": normals,
            "texgens": texgens, "materials": materials, "windings": windings,
            "surfaces": surfaces, "end": r.o}


def parse_dif(data):
    r = R(data, 0)
    r.s32()        # difVersion (44)
    r.u8()         # previewIncluded
    n = r.s32()    # interior count
    interiors = []
    off = r.o
    for _ in range(max(n, 1)):
        it = parse_interior(data, off)
        interiors.append(it)
        off = it["end"]
        break  # MoM interiors: take the first (primary) interior
    return interiors


def _uv(plane, p):
    return plane[0] * p[0] + plane[1] * p[1] + plane[2] * p[2] + plane[3]


def convert(dif_path, glb_path):
    data = Path(dif_path).read_bytes()
    interiors = parse_dif(data)
    dif_dir = Path(dif_path).resolve().parent

    glb = GLB()
    mat_map = {}
    prims = []
    for it in interiors:
        pts = it["points"]
        tg = it["texgens"]
        # group triangles per material with their own vertex stream (UVs are
        # per-surface via texgen, so vertices aren't shared across surfaces)
        by_mat = {}
        mats = it["materials"]
        for s in it["surfaces"]:
            if 0 <= s["tex"] < len(mats) and mats[s["tex"]] in RESERVED_MATERIALS:
                continue  # non-visual (editor markers / trigger volumes)
            w = it["windings"][s["wstart"]:s["wstart"] + s["wcount"]]
            if len(w) < 3:
                continue
            tgp = tg[s["texgen"]] if 0 <= s["texgen"] < len(tg) else None
            verts = []
            for idx in w:
                p = pts[idx]
                u = _uv(tgp[0:4], p) if tgp else 0.0
                v = _uv(tgp[4:8], p) if tgp else 0.0
                verts.append((axis(p), (u, -v)))
            entry = by_mat.setdefault(s["tex"], {"v": [], "t": [], "i": []})
            base = len(entry["v"])
            for gp, uv in verts:
                entry["v"].append(gp); entry["t"].append(uv)
            # triangle-strip winding
            for k in range(len(w) - 2):
                a, b, c = base + k, base + k + 1, base + k + 2
                if k % 2:
                    a, b = b, a
                entry["i"] += [a, b, c]

        for mat, e in by_mat.items():
            if not e["i"]:
                continue
            pos = glb.acc_f(e["v"], 3)
            uv = glb.acc_f(e["t"], 2)
            prim = {"attributes": {"POSITION": pos, "TEXCOORD_0": uv},
                    "indices": glb.acc_idx(e["i"]), "mode": 4}
            if mat not in mat_map:
                name = it["materials"][mat] if mat < len(it["materials"]) else "mat%d" % mat
                tex_idx, is_mask = embed_material_texture(glb, name, dif_dir)
                mat_map[mat] = glb.material(name, tex_idx, alpha_mask=is_mask)
            prim["material"] = mat_map[mat]
            prims.append(prim)

    if not prims:
        raise SystemExit("no geometry from %s" % dif_path)
    glb.save(glb_path, prims, mesh_name=Path(dif_path).stem)
    nverts = sum(a["count"] for a in glb.accessors if a["type"] == "VEC3")
    return len(prims), nverts


if __name__ == "__main__":
    if len(sys.argv) < 3:
        # validation mode on the small obelisk
        p = sys.argv[1] if len(sys.argv) > 1 else \
            "MoMReborn/minions.of.mirth/data/interiors/components/desert_obelisk.dif"
        its = parse_dif(Path(p).read_bytes())
        it = its[0]
        print(f"{Path(p).name}: v{it['version']} points={len(it['points'])} "
              f"planes={len(it['planes'])} texgens={len(it['texgens'])} "
              f"materials={it['materials']} windings={len(it['windings'])} "
              f"surfaces={len(it['surfaces'])} end={it['end']}/{len(Path(p).read_bytes())}")
    else:
        np_, nv = convert(sys.argv[1], sys.argv[2])
        print(f"wrote {sys.argv[2]}: {np_} primitive(s), {nv} verts")
