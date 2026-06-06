#!/usr/bin/env python3
"""Convert a Torque skinned DTS character + shared DSQ animations into an
animated, skinned binary glTF (.glb) that Godot imports with a Skeleton3D,
a skinned MeshInstance3D and an AnimationPlayer.

Unlike dts_to_gltf.py (which bakes node transforms into a static mesh), this
preserves the skeleton: it emits one glTF joint node per DTS node (local TRS
from the bind pose), a skin (inverse-bind matrices + per-vertex JOINTS_0/
WEIGHTS_0), and one glTF animation per DSQ sequence. DSQ animations are matched
to model bones by node *name*, so the shared humanoid/undead/etc. animation sets
apply to any model built on that skeleton.

Torque is Z-up right-handed; glTF/Godot are Y-up. We convert with a single
rotation C: (x,y,z) -> (x, z, -y), applied to vertices, to the inverse-bind
matrices, and to the root joint's local transform (children inherit it). Torque
stores node quaternions conjugated vs. the math convention, so the vector part is
negated to get a standard glTF quaternion.

Usage:
  dts_skin_to_gltf.py <model.dts> <out.glb> [name=path.dsq[:loop] ...]
"""
from __future__ import annotations

import json
import math
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dts_reader import read_shape, MESH_SKIN, MESH_NULL  # noqa: E402
from dsq_reader import read_dsq  # noqa: E402
import dts_to_gltf as static  # reuse texture resolution + material embedding  # noqa: E402


# ---------- small math (pure python, 3x3 + translation) ----------
IDENT3 = ((1.0, 0, 0), (0, 1.0, 0), (0, 0, 1.0))
# C: Torque Z-up -> glTF Y-up, (x,y,z)->(x,z,-y). Rotation, det +1.
C3 = ((1.0, 0, 0), (0, 0, 1.0), (0, -1.0, 0))
# quaternion (x,y,z,w) for C = Rx(-90deg)
SQRT_HALF = math.sqrt(0.5)
C_QUAT = (-SQRT_HALF, 0.0, 0.0, SQRT_HALF)


def quat_to_mat(q):
    # standard rotation matrix from a *standard* quaternion (x,y,z,w)
    x, y, z, w = q
    return (
        (1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)),
        (2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)),
        (2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)),
    )


def mat_mul(a, b):
    return tuple(tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)) for i in range(3))


def mat_vec(m, v):
    return tuple(sum(m[i][k] * v[k] for k in range(3)) for i in range(3))


def mat_t(m):
    return tuple(tuple(m[j][i] for j in range(3)) for i in range(3))


def vadd(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def vneg(a):
    return (-a[0], -a[1], -a[2])


def quat_mul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )


def torque_quat_to_std(q):
    # DTS/DSQ store node quats conjugated: negate the vector part for a std quat.
    return (-q[0], -q[1], -q[2], q[3])


def axisC(p):
    # apply C to a point/vector: (x,y,z)->(x,z,-y)
    return (p[0], p[2], -p[1])


def node_worlds(shape):
    """Per-node (rot3x3, translation) world bind transforms in Torque space."""
    worlds = []
    for i, node in enumerate(shape.nodes):
        r = quat_to_mat(torque_quat_to_std(shape.default_rotations[i])) \
            if i < len(shape.default_rotations) else IDENT3
        t = shape.default_translations[i] if i < len(shape.default_translations) else (0, 0, 0)
        if 0 <= node.parent < len(worlds):
            pr, pt = worlds[node.parent]
            r = mat_mul(pr, r)
            t = vadd(mat_vec(pr, t), pt)
        worlds.append((r, t))
    return worlds


# ---------- glTF/glb writer (skins + animations) ----------
class GLB:
    def __init__(self):
        self.bin = bytearray()
        self.bufferViews = []
        self.accessors = []
        self.materials = []
        self.images = []
        self.textures = []
        self.samplers = []
        self._tex_cache = {}

    # texture/material helpers reused from the static converter
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

    def acc_f(self, vecs, ncomp, minmax=False):
        flat = [c for v in vecs for c in v] if ncomp > 1 else list(vecs)
        data = struct.pack("<%df" % len(flat), *flat)
        bv = self._view(data, 34962)
        typ = {1: "SCALAR", 2: "VEC2", 3: "VEC3", 4: "VEC4", 16: "MAT4"}[ncomp]
        acc = {"bufferView": bv, "componentType": 5126, "count": len(vecs), "type": typ}
        if minmax and ncomp == 3 and vecs:
            acc["min"] = [min(v[i] for v in vecs) for i in range(3)]
            acc["max"] = [max(v[i] for v in vecs) for i in range(3)]
        if minmax and ncomp == 1 and flat:
            acc["min"] = [min(flat)]
            acc["max"] = [max(flat)]
        self.accessors.append(acc)
        return len(self.accessors) - 1

    def acc_scalar_f(self, vals, minmax=True):
        data = struct.pack("<%df" % len(vals), *vals)
        bv = self._view(data, 34962)
        acc = {"bufferView": bv, "componentType": 5126, "count": len(vals), "type": "SCALAR"}
        if minmax and vals:
            acc["min"] = [min(vals)]
            acc["max"] = [max(vals)]
        self.accessors.append(acc)
        return len(self.accessors) - 1

    def acc_mat4(self, mats):
        flat = [c for m in mats for c in m]
        data = struct.pack("<%df" % len(flat), *flat)
        bv = self._view(data)  # no target for IBM
        self.accessors.append({"bufferView": bv, "componentType": 5126,
                               "count": len(mats), "type": "MAT4"})
        return len(self.accessors) - 1

    def acc_joints(self, quads):
        flat = [c for q in quads for c in q]
        data = struct.pack("<%dH" % len(flat), *flat)
        bv = self._view(data, 34962)
        self.accessors.append({"bufferView": bv, "componentType": 5123,
                               "count": len(quads), "type": "VEC4"})
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

    # texture passthrough to the static module's GLB API
    def add_texture(self, path):
        return static.GLB.add_texture(self, path)

    def add_texture_png_bytes(self, b, k):
        return static.GLB.add_texture_png_bytes(self, b, k)

    def _add_image_bytes(self, data, mime):
        return static.GLB._add_image_bytes(self, data, mime)

    def material(self, name, tex_index=None, alpha_mask=False):
        return static.GLB.material(self, name, tex_index, alpha_mask)


def _mat4_colmajor(m3, t):
    """3x3 rotation m3 + translation t -> column-major 16-float 4x4."""
    return [
        m3[0][0], m3[1][0], m3[2][0], 0.0,
        m3[0][1], m3[1][1], m3[2][1], 0.0,
        m3[0][2], m3[1][2], m3[2][2], 0.0,
        t[0], t[1], t[2], 1.0,
    ]


CHAR_PARTS = ("head", "body", "arms", "legs", "feet", "hands", "special")


def _resolve_part_texture(glb, mat_name, tex_dir, tex_indices):
    """MoM character models use template material names 'base.<part>'; the real
    texture is a numbered variant chosen per character (body0.jpg ...). Map the
    part to <tex_dir>/<part>/<part><idx>.<ext> using a default/override index."""
    if not tex_dir:
        return None
    part = mat_name.split(".")[-1].lower()
    if part not in CHAR_PARTS:
        return None
    idx = tex_indices.get(part, 0) if tex_indices else 0
    for ext in (".jpg", ".png", ".jpeg"):
        p = Path(tex_dir) / part / ("%s%d%s" % (part, idx, ext))
        if p.exists():
            return glb.add_texture(str(p))
    return None


def convert(model_path, out_path, anims, tex_dir=None, tex_indices=None):
    shape = read_shape(Path(model_path).read_bytes())
    n_nodes = len(shape.nodes)
    worlds = node_worlds(shape)
    name_to_node = {}
    for i, nd in enumerate(shape.nodes):
        if 0 <= nd.name < len(shape.names):
            name_to_node[shape.names[nd.name]] = i

    glb = GLB()

    # ---- joint nodes (one per DTS node), local TRS; root gets C ----
    gltf_nodes = [None] * n_nodes
    children = {i: [] for i in range(n_nodes)}
    roots = []
    for i, nd in enumerate(shape.nodes):
        t = shape.default_translations[i] if i < len(shape.default_translations) else (0, 0, 0)
        q = torque_quat_to_std(shape.default_rotations[i]) if i < len(shape.default_rotations) else (0, 0, 0, 1)
        if nd.parent < 0:
            t = axisC(t)
            q = quat_mul(C_QUAT, q)
            roots.append(i)
        else:
            children[nd.parent].append(i)
        nm = shape.names[nd.name] if 0 <= nd.name < len(shape.names) else ("node%d" % i)
        gltf_nodes[i] = {"name": nm,
                         "translation": [t[0], t[1], t[2]],
                         "rotation": [q[0], q[1], q[2], q[3]]}
    for i in range(n_nodes):
        if children[i]:
            gltf_nodes[i]["children"] = children[i]

    # ---- inverse-bind matrices (converted world space) ----
    ibms = []
    for i in range(n_nodes):
        r, t = worlds[i]
        M = mat_mul(C3, r)           # converted world rotation
        T = axisC(t)                 # converted world translation
        Mt = mat_t(M)                # inverse rotation
        Tinv = vneg(mat_vec(Mt, T))  # -M^-1 * T
        ibms.append(_mat4_colmajor(Mt, Tinv))
    ibm_acc = glb.acc_mat4(ibms)

    # ---- skinned mesh: gather skin meshes from highest detail ----
    objdetail = 0
    vis = [d for d in shape.details if d.size >= 0]
    if vis:
        objdetail = max(0, max(vis, key=lambda d: d.size).object_detail)

    prims = []
    static_children = []  # (node_index, primitive) for non-skin meshes
    mat_map = {}
    dts_dir = Path(model_path).resolve().parent
    for obj in shape.objects:
        mi = obj.first_mesh + objdetail
        if not (0 <= mi < len(shape.meshes)):
            mi = obj.first_mesh
        if not (0 <= mi < len(shape.meshes)):
            continue
        mesh = shape.meshes[mi]
        if mesh.mtype == MESH_NULL or not mesh.verts or not mesh.tris_by_mat:
            continue

        def emit_material(mat):
            if mat < 0:
                return None
            if mat not in mat_map:
                name = shape.materials[mat] if mat < len(shape.materials) else "mat%d" % mat
                part_tex = _resolve_part_texture(glb, name, tex_dir, tex_indices)
                if part_tex is not None:
                    mat_map[mat] = glb.material(name, part_tex, alpha_mask=False)
                else:
                    tex_idx, is_mask = static.embed_material_texture(glb, name, dts_dir)
                    mat_map[mat] = glb.material(name, tex_idx, alpha_mask=is_mask)
            return mat_map[mat]

        if mesh.mtype == MESH_SKIN and mesh.influences:
            verts = [axisC(v) for v in mesh.verts]
            pos = glb.acc_f(verts, 3, minmax=True)
            nrm = None
            if mesh.normals and len(mesh.normals) == len(mesh.verts):
                nrm = glb.acc_f([axisC(n) for n in mesh.normals], 3)
            uv = None
            if mesh.tverts and len(mesh.tverts) == len(mesh.verts):
                uv = glb.acc_f([(u, 1.0 - vv) for (u, vv) in mesh.tverts], 2)
            # per-vertex up-to-4 (joint, weight)
            acc = [[] for _ in range(len(mesh.verts))]
            for (vi, bone, w) in mesh.influences:
                if 0 <= vi < len(acc) and 0 <= bone < len(mesh.skin_node_index):
                    acc[vi].append((mesh.skin_node_index[bone], w))
            joints, weights = [], []
            for infl in acc:
                infl.sort(key=lambda x: -x[1])
                infl = infl[:4]
                js = [j for (j, _) in infl] + [0] * (4 - len(infl))
                ws = [w for (_, w) in infl] + [0.0] * (4 - len(infl))
                s = sum(ws)
                if s > 0:
                    ws = [w / s for w in ws]
                else:
                    ws = [1.0, 0, 0, 0]
                joints.append(tuple(js[:4]))
                weights.append(tuple(ws[:4]))
            jacc = glb.acc_joints(joints)
            wacc = glb.acc_f(weights, 4)
            for mat, tris in mesh.tris_by_mat.items():
                idx = [i for tri in tris for i in tri]
                if not idx:
                    continue
                attrs = {"POSITION": pos, "JOINTS_0": jacc, "WEIGHTS_0": wacc}
                if nrm is not None:
                    attrs["NORMAL"] = nrm
                if uv is not None:
                    attrs["TEXCOORD_0"] = uv
                prim = {"attributes": attrs, "indices": glb.acc_idx(idx), "mode": 4}
                m = emit_material(mat)
                if m is not None:
                    prim["material"] = m
                prims.append(prim)
        else:
            # non-skin mesh: keep in node-local space, attach as child of its joint
            verts = mesh.verts
            pos = glb.acc_f([(v[0], v[1], v[2]) for v in verts], 3, minmax=True)
            nrm = glb.acc_f(mesh.normals, 3) if mesh.normals and len(mesh.normals) == len(verts) else None
            uv = glb.acc_f([(u, 1.0 - vv) for (u, vv) in mesh.tverts], 2) \
                if mesh.tverts and len(mesh.tverts) == len(verts) else None
            for mat, tris in mesh.tris_by_mat.items():
                idx = [i for tri in tris for i in tri]
                if not idx:
                    continue
                attrs = {"POSITION": pos}
                if nrm is not None:
                    attrs["NORMAL"] = nrm
                if uv is not None:
                    attrs["TEXCOORD_0"] = uv
                prim = {"attributes": attrs, "indices": glb.acc_idx(idx), "mode": 4}
                m = emit_material(mat)
                if m is not None:
                    prim["material"] = m
                static_children.append((obj.node, prim))

    meshes = []
    extra_nodes = []
    scene_nodes = list(roots)

    skin_node_index = None
    if prims:
        meshes.append({"primitives": prims, "name": "body"})
        skin_node_index = n_nodes + len(extra_nodes)
        extra_nodes.append({"name": "body", "mesh": 0, "skin": 0})
        scene_nodes.append(skin_node_index)

    # non-skin meshes -> child nodes under their joint (animate with the bone)
    for (node_idx, prim) in static_children:
        meshes.append({"primitives": [prim]})
        ni = n_nodes + len(extra_nodes)
        extra_nodes.append({"name": "static%d" % ni, "mesh": len(meshes) - 1})
        if 0 <= node_idx < n_nodes:
            gltf_nodes[node_idx].setdefault("children", []).append(ni)
        else:
            scene_nodes.append(ni)

    all_nodes = gltf_nodes + extra_nodes

    # ---- animations from DSQ ----
    animations = []
    for entry in anims:
        path = entry["dsq"]
        loop = entry.get("loop", False)
        try:
            dsq = read_dsq(Path(path).read_bytes())
        except Exception as e:
            sys.stderr.write("  skip %s: %s\n" % (path, e))
            continue
        for seq in dsq.sequences:
            samplers = []
            channels = []
            K = seq.num_keyframes
            if K <= 0:
                continue
            spacing = (seq.duration / K) if loop else (seq.duration / max(K - 1, 1))
            times = [f * spacing for f in range(K)]
            if loop:
                times.append(K * spacing)  # wrap frame == frame 0, seamless loop
            time_acc = glb.acc_scalar_f(times)

            # rotation tracks
            j = 0
            for di, dnode in enumerate(dsq.nodes):
                if di < len(seq.rotation_matters) and seq.rotation_matters[di]:
                    ni = name_to_node.get(dnode)
                    base = seq.base_rotation + j * K
                    j += 1
                    if ni is None:
                        continue
                    out = []
                    for f in range(K):
                        q = torque_quat_to_std(dsq.rotations[base + f])
                        if shape.nodes[ni].parent < 0:
                            q = quat_mul(C_QUAT, q)
                        out.append((q[0], q[1], q[2], q[3]))
                    if loop:
                        out.append(out[0])
                    s_idx = len(samplers)
                    samplers.append({"input": time_acc, "output": glb.acc_f(out, 4), "interpolation": "LINEAR"})
                    channels.append({"sampler": s_idx, "target": {"node": ni, "path": "rotation"}})
            # translation tracks
            j = 0
            for di, dnode in enumerate(dsq.nodes):
                if di < len(seq.translation_matters) and seq.translation_matters[di]:
                    ni = name_to_node.get(dnode)
                    base = seq.base_translation + j * K
                    j += 1
                    if ni is None:
                        continue
                    out = []
                    for f in range(K):
                        t = dsq.translations[base + f]
                        if shape.nodes[ni].parent < 0:
                            t = axisC(t)
                        out.append((t[0], t[1], t[2]))
                    if loop:
                        out.append(out[0])
                    s_idx = len(samplers)
                    samplers.append({"input": time_acc, "output": glb.acc_f(out, 3), "interpolation": "LINEAR"})
                    channels.append({"sampler": s_idx, "target": {"node": ni, "path": "translation"}})

            if channels:
                animations.append({"name": entry.get("name", seq.name),
                                   "samplers": samplers, "channels": channels})

    # ---- assemble glTF ----
    gltf = {
        "asset": {"version": "2.0", "generator": "mom-dts-skin-to-gltf"},
        "scene": 0,
        "scenes": [{"nodes": scene_nodes}],
        "nodes": all_nodes,
        "accessors": glb.accessors,
        "bufferViews": glb.bufferViews,
        "buffers": [{"byteLength": len(glb.bin)}],
    }
    if meshes:
        gltf["meshes"] = meshes
    if skin_node_index is not None:
        gltf["skins"] = [{"joints": list(range(n_nodes)),
                          "inverseBindMatrices": ibm_acc,
                          "skeleton": roots[0] if roots else 0}]
    if animations:
        gltf["animations"] = animations
    if glb.materials:
        gltf["materials"] = glb.materials
    for key, val in (("images", glb.images), ("textures", glb.textures), ("samplers", glb.samplers)):
        if val:
            gltf[key] = val

    js = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    while len(js) % 4:
        js += b" "
    b = bytearray(glb.bin)
    while len(b) % 4:
        b.append(0)
    out = bytearray()
    total = 12 + 8 + len(js) + 8 + len(b)
    out += struct.pack("<III", 0x46546C67, 2, total)
    out += struct.pack("<II", len(js), 0x4E4F534A) + js
    out += struct.pack("<II", len(b), 0x004E4942) + b
    Path(out_path).write_bytes(out)
    return {"nodes": n_nodes, "prims": len(prims), "anims": len(animations),
            "static_parts": len(static_children)}


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit("usage: dts_skin_to_gltf.py <model.dts> <out.glb> [name=path.dsq[:loop] ...]")
    model, out = sys.argv[1], sys.argv[2]
    anims = []
    tex_dir = None
    tex_indices = {}
    for a in sys.argv[3:]:
        if a.startswith("--tex="):
            tex_dir = a[len("--tex="):]
            continue
        if a.startswith("--texidx="):
            for kv in a[len("--texidx="):].split(","):
                if ":" in kv:
                    k, v = kv.split(":")
                    tex_indices[k.strip()] = int(v)
            continue
        nm, _, rest = a.partition("=")
        path, _, loopflag = rest.partition(":")
        anims.append({"name": nm, "dsq": path, "loop": loopflag == "loop"})
    info = convert(model, out, anims, tex_dir=tex_dir, tex_indices=tex_indices)
    print("wrote %s: %s" % (out, info))
