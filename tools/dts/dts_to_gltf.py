#!/usr/bin/env python3
"""Convert a Torque DTS shape to a Godot-friendly binary glTF (.glb).

Exports the highest detail level: for each object, bakes its node's world
transform into the vertices, converts Torque's Z-up right-handed space to
glTF/Godot's Y-up (x, z, -y), flips the V texcoord, and writes one glTF mesh
with one primitive per material group.

Usage: dts_to_gltf.py <in.dts> <out.glb>
"""
from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dts_reader import read_shape, MESH_NULL  # noqa: E402


# ---------- small math (pure python) ----------
def quat_to_mat(q):
    # Torque stores node rotations conjugated relative to the standard math
    # convention, so negate the vector part before building the matrix.
    x, y, z, w = -q[0], -q[1], -q[2], q[3]
    return (
        (1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)),
        (2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)),
        (2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)),
    )


def mat_mul(a, b):
    return tuple(
        tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3))
        for i in range(3)
    )


def mat_vec(m, v):
    return tuple(sum(m[i][k] * v[k] for k in range(3)) for i in range(3))


def vec_add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def axis(p):
    # Torque Z-up RH -> glTF/Godot Y-up: (x, z, -y). Proper rotation (det +1).
    return (p[0], p[2], -p[1])


def node_worlds(shape):
    """Return per-node (rot3x3, translation) in Torque space."""
    worlds = []
    for i, node in enumerate(shape.nodes):
        r = quat_to_mat(shape.default_rotations[i]) if i < len(shape.default_rotations) else \
            ((1, 0, 0), (0, 1, 0), (0, 0, 1))
        t = shape.default_translations[i] if i < len(shape.default_translations) else (0, 0, 0)
        if 0 <= node.parent < len(worlds):
            pr, pt = worlds[node.parent]
            r = mat_mul(pr, r)
            t = vec_add(mat_vec(pr, t), pt)
        worlds.append((r, t))
    return worlds


# ---------- minimal glTF/glb writer ----------
class GLB:
    def __init__(self):
        self.bin = bytearray()
        self.bufferViews = []
        self.accessors = []
        self.materials = []

    def _align(self, n=4):
        while len(self.bin) % n:
            self.bin.append(0)

    def _view(self, data, target=None):
        self._align()
        off = len(self.bin)
        self.bin += data
        bv = {"buffer": 0, "byteOffset": off, "byteLength": len(data)}
        if target:
            bv["target"] = target
        self.bufferViews.append(bv)
        return len(self.bufferViews) - 1

    def acc_f(self, vecs, ncomp):
        flat = [c for v in vecs for c in v]
        data = struct.pack("<%df" % len(flat), *flat)
        bv = self._view(data, 34962)
        typ = {1: "SCALAR", 2: "VEC2", 3: "VEC3", 4: "VEC4"}[ncomp]
        acc = {"bufferView": bv, "componentType": 5126, "count": len(vecs), "type": typ}
        if ncomp == 3 and vecs:
            acc["min"] = [min(v[i] for v in vecs) for i in range(3)]
            acc["max"] = [max(v[i] for v in vecs) for i in range(3)]
        self.accessors.append(acc)
        return len(self.accessors) - 1

    def acc_idx(self, idx):
        mx = max(idx) if idx else 0
        if mx < 65535:
            comp, data = 5123, struct.pack("<%dH" % len(idx), *idx)
        else:
            comp, data = 5125, struct.pack("<%dI" % len(idx), *idx)
        bv = self._view(data, 34963)
        self.accessors.append({"bufferView": bv, "componentType": comp,
                               "count": len(idx), "type": "SCALAR"})
        return len(self.accessors) - 1

    def material(self, name):
        self.materials.append({
            "name": name,
            "pbrMetallicRoughness": {"baseColorFactor": [0.8, 0.8, 0.8, 1.0],
                                     "metallicFactor": 0.0, "roughnessFactor": 0.9},
            "doubleSided": True,
        })
        return len(self.materials) - 1

    def save(self, path, mesh_primitives, mesh_name="shape"):
        gltf = {
            "asset": {"version": "2.0", "generator": "mom-dts-to-gltf"},
            "scene": 0,
            "scenes": [{"nodes": [0]}],
            "nodes": [{"mesh": 0, "name": mesh_name}],
            "meshes": [{"primitives": mesh_primitives}],
            "accessors": self.accessors,
            "bufferViews": self.bufferViews,
            "buffers": [{"byteLength": len(self.bin)}],
        }
        if self.materials:
            gltf["materials"] = self.materials
        js = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
        while len(js) % 4:
            js += b" "
        b = bytearray(self.bin)
        while len(b) % 4:
            b.append(0)
        out = bytearray()
        total = 12 + 8 + len(js) + 8 + len(b)
        out += struct.pack("<III", 0x46546C67, 2, total)
        out += struct.pack("<II", len(js), 0x4E4F534A) + js
        out += struct.pack("<II", len(b), 0x004E4942) + b
        Path(path).write_bytes(out)


def convert(dts_path, glb_path):
    shape = read_shape(Path(dts_path).read_bytes())
    worlds = node_worlds(shape)

    # highest detail level -> object detail offset
    objdetail = 0
    vis_details = [d for d in shape.details if d.size >= 0]
    if vis_details:
        objdetail = max(0, max(vis_details, key=lambda d: d.size).object_detail)

    glb = GLB()
    mat_map = {}
    prims = []

    for obj in shape.objects:
        mi = obj.first_mesh + objdetail
        if not (0 <= mi < len(shape.meshes)):
            mi = obj.first_mesh
        if not (0 <= mi < len(shape.meshes)):
            continue
        mesh = shape.meshes[mi]
        if mesh.mtype == MESH_NULL or not mesh.verts or not mesh.tris_by_mat:
            continue
        r, t = worlds[obj.node] if 0 <= obj.node < len(worlds) else \
            (((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0, 0, 0))

        verts = [axis(vec_add(mat_vec(r, v), t)) for v in mesh.verts]
        pos = glb.acc_f(verts, 3)
        nrm = None
        if mesh.normals and len(mesh.normals) == len(mesh.verts):
            norms = [axis(mat_vec(r, n)) for n in mesh.normals]
            nrm = glb.acc_f(norms, 3)
        uv = None
        if mesh.tverts and len(mesh.tverts) == len(mesh.verts):
            uvs = [(u, 1.0 - vv) for (u, vv) in mesh.tverts]
            uv = glb.acc_f(uvs, 2)

        for mat, tris in mesh.tris_by_mat.items():
            idx = [i for tri in tris for i in tri]
            if not idx:
                continue
            prim = {"attributes": {"POSITION": pos}, "indices": glb.acc_idx(idx), "mode": 4}
            if nrm is not None:
                prim["attributes"]["NORMAL"] = nrm
            if uv is not None:
                prim["attributes"]["TEXCOORD_0"] = uv
            if mat >= 0:
                if mat not in mat_map:
                    name = shape.materials[mat] if mat < len(shape.materials) else "mat%d" % mat
                    mat_map[mat] = glb.material(name)
                prim["material"] = mat_map[mat]
            prims.append(prim)

    if not prims:
        raise SystemExit("no renderable geometry produced from %s" % dts_path)
    name = Path(dts_path).stem
    glb.save(glb_path, prims, mesh_name=name)
    return len(prims), sum(a["count"] for a in glb.accessors if a["type"] == "VEC3")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit("usage: dts_to_gltf.py <in.dts> <out.glb>")
    np, nv = convert(sys.argv[1], sys.argv[2])
    print(f"wrote {sys.argv[2]}: {np} primitive(s)")
