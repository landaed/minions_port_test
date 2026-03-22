#!/usr/bin/env python3
"""
Torque DTS model to glTF 2.0 (.glb) converter.

Reads Torque Game Engine DTS v24 binary files using the format documented
in the existing DTSPython library, and outputs glTF Binary (.glb) files
that Godot 4 can import natively.

Handles: meshes, materials (texture references), nodes/bones, skinning weights.
Does NOT handle: animations (DSQ files need separate handling).
"""

import struct
import json
import math
import os
import sys
from collections import namedtuple

# ─── DTS Binary Reader ───────────────────────────────────────────────

class DtsStream:
    """Reads the DTS v24 triple-buffer binary format."""

    def __init__(self, path):
        with open(path, 'rb') as f:
            raw = f.read()

        # Header: 4 x int32
        ver_raw, total_size, off16, off8 = struct.unpack_from('<4i', raw, 0)
        self.version = ver_raw & 0xFF
        self.exporter_version = ver_raw >> 16

        if self.version != 24:
            raise ValueError(f"DTS version {self.version}, expected 24")

        buf_start = 16  # after 4-int header

        # 32-bit buffer
        n32 = off16
        self.buf32 = list(struct.unpack_from(f'<{n32}i', raw, buf_start))
        # 16-bit buffer
        n16 = (off8 - off16) * 2
        self.buf16 = list(struct.unpack_from(f'<{n16}h', raw, buf_start + n32 * 4))
        # 8-bit buffer
        n8 = (total_size - off8) * 4
        self.buf8 = list(struct.unpack_from(f'<{n8}b', raw, buf_start + n32 * 4 + n16 * 2))

        self.pos32 = 0
        self.pos16 = 0
        self.pos8 = 0
        self.check_count = 0

        # Remainder of file after buffers (sequences + materials)
        self.tail_offset = buf_start + n32 * 4 + n16 * 2 + n8
        self.tail = raw[self.tail_offset:]

    def read32(self):
        v = self.buf32[self.pos32]; self.pos32 += 1; return v
    def read16(self):
        v = self.buf16[self.pos16]; self.pos16 += 1; return v
    def read8(self):
        v = self.buf8[self.pos8]; self.pos8 += 1; return v

    def s32(self): return self.read32()
    def u32(self):
        v = self.read32()
        return struct.unpack('I', struct.pack('i', v))[0]
    def f32(self):
        v = self.read32()
        return struct.unpack('f', struct.pack('i', v))[0]
    def s16(self): return self.read16()
    def u16(self):
        v = self.read16()
        return struct.unpack('H', struct.pack('h', v))[0]
    def s8(self): return self.read8()
    def u8(self):
        v = self.read8()
        return struct.unpack('B', struct.pack('b', v))[0]

    def check(self):
        c8 = self.u8()
        c16 = self.u16()
        c32 = self.u32()
        if not (c8 == c16 == c32 == self.check_count):
            print(f"  Warning: checkpoint mismatch at {self.check_count}: {c8},{c16},{c32}")
        self.check_count += 1

    def point2f(self): return (self.f32(), self.f32())
    def point3f(self): return (self.f32(), self.f32(), self.f32())
    def point4f(self): return (self.f32(), self.f32(), self.f32(), self.f32())
    def box(self): return (self.point3f(), self.point3f())

    def quat16(self):
        """Read compressed quaternion (4 x int16 -> normalized floats)."""
        x = self.s16() / 32767.0
        y = self.s16() / 32767.0
        z = self.s16() / 32767.0
        w = self.s16() / 32767.0
        return (x, y, z, w)

    def matrix_f(self):
        return [self.f32() for _ in range(16)]

    def string_t(self):
        """Read null-terminated string from 8-bit buffer."""
        chars = []
        while True:
            c = self.u8()
            if c == 0:
                break
            chars.append(chr(c))
        return ''.join(chars)

    def node(self):
        name = self.s32()
        parent = self.s32()
        self.s32()  # firstObject (runtime)
        self.s32()  # firstChild (runtime)
        self.s32()  # nextSibling (runtime)
        return {'name': name, 'parent': parent}

    def object(self):
        name = self.s32()
        num_meshes = self.s32()
        first_mesh = self.s32()
        node = self.s32()
        self.s32()  # sibling
        self.s32()  # firstDecal
        return {'name': name, 'numMeshes': num_meshes, 'firstMesh': first_mesh, 'node': node}

    def detail_level(self):
        return {
            'name': self.s32(), 'subshape': self.s32(), 'objectDetail': self.s32(),
            'size': self.f32(), 'avgError': self.f32(), 'maxError': self.f32(),
            'polyCount': self.s32(),
        }

    def object_state(self):
        return {'vis': self.f32(), 'frame': self.s32(), 'matFrame': self.s32()}

    def trigger(self):
        return {'state': self.s32(), 'pos': self.f32()}

    def primitive(self):
        return {'firstElement': self.s16(), 'numElements': self.s16(), 'matindex': self.s32()}

    def ifl_material(self):
        return {k: self.s32() for k in ('name', 'slot', 'firstFrame', 'time', 'numFrames')}

    def decal(self):
        return {k: self.s32() for k in ('name', 'numMeshes', 'firstMesh', 'object', 'sibling')}

    def decal_state(self):
        return {'frame': self.s32()}


# ─── DTS Shape Reader ────────────────────────────────────────────────

# Primitive type masks
PRIM_STRIP = 0x40000000
PRIM_FAN = 0x80000000
PRIM_TYPE_MASK = 0xC0000000
PRIM_MATERIAL_MASK = 0x0FFFFFFF
PRIM_NO_MATERIAL = 0x10000000

# Mesh types
MESH_STANDARD = 0
MESH_SKIN = 1
MESH_DECAL = 2
MESH_SORTED = 3
MESH_NULL = 4


def read_mesh(ds, meshes_so_far):
    """Read a single DTS mesh from the stream."""
    mtype = ds.u32()
    mesh = {'type': mtype, 'verts': [], 'tverts': [], 'normals': [],
            'primitives': [], 'indices': [], 'parent': -1,
            'nodeIndex': [], 'nodeTransforms': [], 'vindex': [], 'bindex': [], 'vweight': []}

    if mtype == MESH_NULL:
        return mesh

    if mtype != MESH_DECAL:
        ds.check()
        mesh['numFrames'] = ds.s32()
        mesh['matFrames'] = ds.s32()
        mesh['parent'] = ds.s32()
        mesh['bounds'] = ds.box()
        mesh['center'] = ds.point3f()
        mesh['radius'] = ds.f32()

        parent = mesh['parent']

        # Verts
        nv = ds.s32()
        if parent < 0:
            mesh['verts'] = [ds.point3f() for _ in range(nv)]
        else:
            mesh['verts'] = meshes_so_far[parent]['verts']

        # Texture coords
        nt = ds.s32()
        if parent < 0:
            mesh['tverts'] = [ds.point2f() for _ in range(nt)]
        else:
            mesh['tverts'] = meshes_so_far[parent]['tverts']

        # Normals + encoded normals
        if parent < 0:
            mesh['normals'] = [ds.point3f() for _ in range(len(mesh['verts']))]
            for _ in range(len(mesh['verts'])):
                ds.u8()  # skip encoded normals
        else:
            mesh['normals'] = meshes_so_far[parent]['normals']

        # Primitives
        np_ = ds.s32()
        mesh['primitives'] = [ds.primitive() for _ in range(np_)]

        # Indices
        ni = ds.s32()
        mesh['indices'] = [ds.u16() for _ in range(ni)]

        # Merge indices (unused)
        nm = ds.s32()
        for _ in range(nm):
            ds.u16()

        mesh['vertsPerFrame'] = ds.s32()
        mesh['flags'] = ds.u32()
        ds.check()

    # Skin mesh extra data
    if mtype == MESH_SKIN:
        parent = mesh['parent']
        # Initial verts (appended to existing verts for skin)
        niv = ds.s32()
        if parent < 0:
            mesh['verts'] = [ds.point3f() for _ in range(niv)]

        # Normals for skin
        if parent < 0:
            for _ in range(len(mesh['verts'])):
                ds.read8()  # skip encoded normals
            mesh['normals'] = [ds.point3f() for _ in range(len(mesh['verts']))]

        if parent < 0:
            # Node transforms
            nt = ds.s32()
            mesh['nodeTransforms'] = [ds.matrix_f() for _ in range(nt)]
            # Vertex/bone/weight arrays
            sz = ds.s32()
            mesh['vindex'] = [ds.s32() for _ in range(sz)]
            mesh['bindex'] = [ds.s32() for _ in range(sz)]
            mesh['vweight'] = [ds.f32() for _ in range(sz)]
            # Node indices
            nn = ds.s32()
            mesh['nodeIndex'] = [ds.s32() for _ in range(nn)]
        else:
            for _ in range(3):
                ds.s32()

        ds.check()

    elif mtype == MESH_SORTED:
        # Sorted mesh clusters
        nc = ds.s32()
        for _ in range(nc):
            ds.s32(); ds.s32(); ds.point3f(); ds.f32(); ds.s32(); ds.s32()
        nsc = ds.s32()
        for _ in range(nsc): ds.s32()
        nsp = ds.s32()
        for _ in range(nsp): ds.s32()
        nfv = ds.s32()
        for _ in range(nfv): ds.s32()
        nnv = ds.s32()
        for _ in range(nnv): ds.s32()
        nft = ds.s32()
        for _ in range(nft): ds.s32()
        ds.check()

    elif mtype == MESH_DECAL:
        # Skip decal mesh data
        ds.check()
        ds.s32()  # numFrames
        ds.s32()  # matFrames
        parent = ds.s32()
        ds.box()  # bounds
        ds.point3f()  # center
        ds.f32()  # radius
        nt = ds.s32()  # texgens
        for _ in range(nt): ds.point4f()
        for _ in range(nt): ds.point4f()
        ds.s32()  # materialIndex
        np_ = ds.s32()
        for _ in range(np_): ds.primitive()
        ni = ds.s32()
        for _ in range(ni): ds.u16()
        nm = ds.s32()
        for _ in range(nm): ds.u16()
        ds.check()

    return mesh


def read_materials(tail_data):
    """Read sequences and material list from the tail of the DTS file."""
    offset = 0
    # Number of sequences
    num_seq = struct.unpack_from('<i', tail_data, offset)[0]
    offset += 4

    sequences = []
    # Sequence format: 13 x S32 + 1 x F32 + 1 x F32 (toolBegin) = 15 fields
    # Some older shapes omit toolBegin = 14 fields
    fmt_full = '<iIif' + 'i' * 10 + 'f'   # 15 fields, 60 bytes
    fmt_short = '<iIif' + 'i' * 10          # 14 fields, 56 bytes
    sz_full = struct.calcsize(fmt_full)
    sz_short = struct.calcsize(fmt_short)

    for _ in range(num_seq):
        seq = {}
        remaining = len(tail_data) - offset
        if remaining < sz_short:
            break  # Not enough data

        if remaining >= sz_full:
            fields = struct.unpack_from(fmt_full, tail_data, offset)
            offset += sz_full
            seq['toolBegin'] = fields[14]
        else:
            fields = struct.unpack_from(fmt_short, tail_data, offset)
            offset += sz_short
            seq['toolBegin'] = 0.0

        seq['nameIndex'] = fields[0]
        seq['flags'] = fields[1]
        seq['numKeyFrames'] = fields[2]
        seq['duration'] = fields[3]
        seq['priority'] = fields[4]
        seq['firstGroundFrame'] = fields[5]
        seq['numGroundFrames'] = fields[6]
        seq['baseRotation'] = fields[7]
        seq['baseTranslation'] = fields[8]
        seq['baseScale'] = fields[9]
        seq['baseObjectState'] = fields[10]
        seq['baseDecalState'] = fields[11]
        seq['firstTrigger'] = fields[12]
        seq['numTriggers'] = fields[13]
        # Skip 8 integer sets
        for _ in range(8):
            if offset + 8 > len(tail_data):
                break
            num_ints = struct.unpack_from('<i', tail_data, offset)[0]; offset += 4
            sz = struct.unpack_from('<i', tail_data, offset)[0]; offset += 4
            offset += sz * 4
        sequences.append(seq)

    # Material list
    materials = []
    if offset < len(tail_data):
        ver = struct.unpack_from('<b', tail_data, offset)[0]; offset += 1
        if ver == 1:
            num_mats = struct.unpack_from('<i', tail_data, offset)[0]; offset += 4
            names = []
            for _ in range(num_mats):
                slen = struct.unpack_from('<B', tail_data, offset)[0]; offset += 1
                name = tail_data[offset:offset+slen].decode('ascii', errors='replace')
                offset += slen
                names.append(name)
            flags_list = []
            for _ in range(num_mats):
                flags_list.append(struct.unpack_from('<I', tail_data, offset)[0]); offset += 4
            # Skip reflectance, bump, detail (each U32 per mat)
            offset += num_mats * 4 * 3
            # Skip detailScale, reflection (each F32 per mat)
            offset += num_mats * 4 * 2
            for i, name in enumerate(names):
                materials.append({'name': name, 'flags': flags_list[i]})

    return sequences, materials


def read_dts(path):
    """Read an entire DTS shape file."""
    ds = DtsStream(path)

    # Read sequences + materials from tail
    sequences, materials = read_materials(ds.tail)

    # Now read from the triple buffers
    num_nodes = ds.s32()
    num_objects = ds.s32()
    num_decals = ds.s32()
    num_subshapes = ds.s32()
    num_ifl_materials = ds.s32()
    num_node_rots = ds.s32()
    num_node_trans = ds.s32()
    num_node_uniform_scales = ds.s32()
    num_node_aligned_scales = ds.s32()
    num_node_arbitrary_scales = ds.s32()
    num_ground_frames = ds.s32()
    num_object_states = ds.s32()
    num_decal_states = ds.s32()
    num_triggers = ds.s32()
    num_details = ds.s32()
    num_meshes = ds.s32()
    num_names = ds.s32()
    smallest_visible_size = ds.s32()
    smallest_visible_dl = ds.s32()

    ds.check()

    # Bounds
    radius = ds.f32()
    tube_radius = ds.f32()
    center = ds.point3f()
    bounds = ds.box()

    ds.check()

    # Nodes
    nodes = [ds.node() for _ in range(num_nodes)]
    ds.check()

    # Objects
    objects = [ds.object() for _ in range(num_objects)]
    ds.check()

    # Decals
    decals = [ds.decal() for _ in range(num_decals)]
    ds.check()

    # IFL materials
    ifl_materials = [ds.ifl_material() for _ in range(num_ifl_materials)]
    ds.check()

    # Subshapes
    ss_first_node = [ds.s32() for _ in range(num_subshapes)]
    ss_first_object = [ds.s32() for _ in range(num_subshapes)]
    ss_first_decal = [ds.s32() for _ in range(num_subshapes)]
    ds.check()
    ss_num_nodes = [ds.s32() for _ in range(num_subshapes)]
    ss_num_objects = [ds.s32() for _ in range(num_subshapes)]
    ss_num_decals = [ds.s32() for _ in range(num_subshapes)]
    ds.check()

    # Default rotations/translations
    default_rotations = [ds.quat16() for _ in range(num_nodes)]
    default_translations = [ds.point3f() for _ in range(num_nodes)]

    node_translations = [ds.point3f() for _ in range(num_node_trans)]
    node_rotations = [ds.quat16() for _ in range(num_node_rots)]
    ds.check()

    # Scales
    for _ in range(num_node_uniform_scales): ds.f32()
    for _ in range(num_node_aligned_scales): ds.point3f()
    for _ in range(num_node_arbitrary_scales): ds.point3f()
    for _ in range(num_node_arbitrary_scales): ds.quat16()
    ds.check()

    # Ground frames
    for _ in range(num_ground_frames): ds.point3f()
    for _ in range(num_ground_frames): ds.quat16()
    ds.check()

    # Object states
    object_states = [ds.object_state() for _ in range(num_object_states)]
    ds.check()

    # Decal states
    for _ in range(num_decal_states): ds.decal_state()
    ds.check()

    # Triggers
    triggers = [ds.trigger() for _ in range(num_triggers)]
    ds.check()

    # Detail levels
    detail_levels = [ds.detail_level() for _ in range(num_details)]
    ds.check()

    # Meshes
    meshes = []
    for _ in range(num_meshes):
        m = read_mesh(ds, meshes)
        meshes.append(m)
    ds.check()

    # Names
    names = [ds.string_t() for _ in range(num_names)]
    ds.check()

    return {
        'nodes': nodes, 'objects': objects, 'meshes': meshes,
        'materials': materials, 'names': names, 'sequences': sequences,
        'detail_levels': detail_levels, 'default_rotations': default_rotations,
        'default_translations': default_translations,
        'node_rotations': node_rotations, 'node_translations': node_translations,
        'bounds': bounds, 'center': center, 'radius': radius,
        'subshapes': [{'firstNode': ss_first_node[i], 'firstObject': ss_first_object[i],
                        'numNodes': ss_num_nodes[i], 'numObjects': ss_num_objects[i]}
                       for i in range(num_subshapes)],
    }


# ─── glTF Binary Writer ──────────────────────────────────────────────

def align4(n):
    return (n + 3) & ~3


def triangulate_strip(indices):
    """Convert a triangle strip to triangle list."""
    tris = []
    for i in range(len(indices) - 2):
        if i % 2 == 0:
            tris.extend([indices[i], indices[i+1], indices[i+2]])
        else:
            tris.extend([indices[i], indices[i+2], indices[i+1]])
    return tris


def build_gltf(shape, texture_search_dirs=None):
    """Convert parsed DTS shape to glTF 2.0 data structures."""
    gltf = {
        'asset': {'version': '2.0', 'generator': 'MoM DTS Converter'},
        'scene': 0, 'scenes': [{'nodes': []}],
        'nodes': [], 'meshes': [], 'accessors': [], 'bufferViews': [],
        'buffers': [], 'materials': [],
    }
    bin_data = bytearray()

    def add_buffer_view(data_bytes, target=None):
        """Add raw bytes to the binary buffer and create a bufferView."""
        # Pad to 4-byte alignment
        while len(bin_data) % 4 != 0:
            bin_data.append(0)
        offset = len(bin_data)
        bin_data.extend(data_bytes)
        bv = {'buffer': 0, 'byteOffset': offset, 'byteLength': len(data_bytes)}
        if target:
            bv['target'] = target
        idx = len(gltf['bufferViews'])
        gltf['bufferViews'].append(bv)
        return idx

    def add_accessor(bv_idx, comp_type, count, acc_type, min_vals=None, max_vals=None):
        acc = {
            'bufferView': bv_idx, 'componentType': comp_type,
            'count': count, 'type': acc_type,
        }
        if min_vals is not None:
            acc['min'] = min_vals
        if max_vals is not None:
            acc['max'] = max_vals
        idx = len(gltf['accessors'])
        gltf['accessors'].append(acc)
        return idx

    # ── Materials ──
    for mat in shape['materials']:
        mat_name = mat['name']
        # Strip extension if present, add to texture search
        base = os.path.splitext(mat_name)[0]
        gltf_mat = {
            'name': mat_name,
            'pbrMetallicRoughness': {
                'baseColorFactor': [1, 1, 1, 1],
                'metallicFactor': 0.0,
                'roughnessFactor': 0.8,
            },
        }
        flags = mat.get('flags', 0)
        if flags & 0x00000004:  # Translucent
            gltf_mat['alphaMode'] = 'BLEND'
        if flags & 0x00000020:  # SelfIlluminating
            gltf_mat['emissiveFactor'] = [0.5, 0.5, 0.5]
        gltf['materials'].append(gltf_mat)

    if not gltf['materials']:
        gltf['materials'].append({
            'name': 'default',
            'pbrMetallicRoughness': {'baseColorFactor': [0.8, 0.8, 0.8, 1]},
        })

    # ── Find the highest detail level meshes ──
    # For each object, pick detail 0 (highest detail) mesh
    best_detail = 0
    meshes_to_export = []

    for obj in shape['objects']:
        if obj['numMeshes'] > 0:
            mesh_idx = obj['firstMesh'] + best_detail
            if mesh_idx < len(shape['meshes']):
                mesh = shape['meshes'][mesh_idx]
                if mesh['type'] != MESH_NULL and len(mesh['verts']) > 0:
                    obj_name = shape['names'][obj['name']] if obj['name'] < len(shape['names']) else f"object_{obj['name']}"
                    meshes_to_export.append((obj, mesh, obj_name))

    # ── Convert meshes ──
    for obj, mesh, obj_name in meshes_to_export:
        verts = mesh['verts']
        normals = mesh['normals']
        tverts = mesh['tverts']
        primitives = mesh['primitives']
        indices = mesh['indices']

        if not verts or not primitives:
            continue

        # Split by material into glTF primitives
        prim_groups = {}  # mat_idx -> list of triangle indices
        for prim in primitives:
            mat_idx = prim['matindex'] & PRIM_MATERIAL_MASK
            if prim['matindex'] & PRIM_NO_MATERIAL:
                mat_idx = 0
            prim_type = prim['matindex'] & PRIM_TYPE_MASK

            first = prim['firstElement']
            count = prim['numElements']
            prim_indices = [indices[first + i] for i in range(count) if first + i < len(indices)]

            if prim_type == PRIM_STRIP:
                tri_indices = triangulate_strip(prim_indices)
            else:
                tri_indices = prim_indices

            if mat_idx not in prim_groups:
                prim_groups[mat_idx] = []
            prim_groups[mat_idx].extend(tri_indices)

        if not prim_groups:
            continue

        # Coordinate system: Torque Y-forward Z-up -> glTF Y-up Z-backward
        # Swap Y and Z, negate new Z
        conv_verts = [(v[0], v[2], -v[1]) for v in verts]
        conv_normals = [(n[0], n[2], -n[1]) for n in normals] if normals else []
        # Flip V for glTF (glTF V = 1 - Torque V)
        conv_tverts = [(t[0], 1.0 - t[1]) for t in tverts] if tverts else []

        # Pack vertex data
        vert_bytes = b''.join(struct.pack('<3f', *v) for v in conv_verts)
        mins = [min(v[i] for v in conv_verts) for i in range(3)]
        maxs = [max(v[i] for v in conv_verts) for i in range(3)]

        vert_bv = add_buffer_view(vert_bytes, 34962)
        vert_acc = add_accessor(vert_bv, 5126, len(conv_verts), 'VEC3', mins, maxs)

        norm_acc = None
        if conv_normals and len(conv_normals) == len(conv_verts):
            norm_bytes = b''.join(struct.pack('<3f', *n) for n in conv_normals)
            norm_bv = add_buffer_view(norm_bytes, 34962)
            norm_acc = add_accessor(norm_bv, 5126, len(conv_normals), 'VEC3')

        uv_acc = None
        if conv_tverts and len(conv_tverts) == len(conv_verts):
            uv_bytes = b''.join(struct.pack('<2f', *t) for t in conv_tverts)
            uv_bv = add_buffer_view(uv_bytes, 34962)
            uv_acc = add_accessor(uv_bv, 5126, len(conv_tverts), 'VEC2')

        gltf_prims = []
        for mat_idx, tri_list in prim_groups.items():
            if not tri_list:
                continue
            # Filter out degenerate triangles
            filtered = []
            for i in range(0, len(tri_list) - 2, 3):
                a, b, c = tri_list[i], tri_list[i+1], tri_list[i+2]
                if a != b and b != c and a != c:
                    if a < len(conv_verts) and b < len(conv_verts) and c < len(conv_verts):
                        filtered.extend([a, b, c])
            if not filtered:
                continue

            idx_bytes = b''.join(struct.pack('<H', i) for i in filtered)
            idx_bv = add_buffer_view(idx_bytes, 34963)
            idx_acc = add_accessor(idx_bv, 5123, len(filtered), 'SCALAR',
                                   [min(filtered)], [max(filtered)])

            p = {'attributes': {'POSITION': vert_acc}, 'indices': idx_acc}
            if norm_acc is not None:
                p['attributes']['NORMAL'] = norm_acc
            if uv_acc is not None:
                p['attributes']['TEXCOORD_0'] = uv_acc
            if mat_idx < len(gltf['materials']):
                p['material'] = mat_idx
            gltf_prims.append(p)

        if gltf_prims:
            mesh_idx = len(gltf['meshes'])
            gltf['meshes'].append({'name': obj_name, 'primitives': gltf_prims})

            node_idx = len(gltf['nodes'])
            gltf['nodes'].append({'name': obj_name, 'mesh': mesh_idx})
            gltf['scenes'][0]['nodes'].append(node_idx)

    # ── Finalize buffer ──
    while len(bin_data) % 4 != 0:
        bin_data.append(0)
    gltf['buffers'].append({'byteLength': len(bin_data)})

    # Clean up empty arrays
    for key in list(gltf.keys()):
        if isinstance(gltf[key], list) and len(gltf[key]) == 0 and key not in ('scenes', 'buffers'):
            del gltf[key]

    return gltf, bytes(bin_data)


def write_glb(gltf_dict, bin_data, output_path):
    """Write a GLB (binary glTF) file."""
    json_str = json.dumps(gltf_dict, separators=(',', ':')).encode('utf-8')
    # Pad JSON to 4-byte alignment with spaces
    while len(json_str) % 4 != 0:
        json_str += b' '
    # Pad BIN to 4-byte alignment with zeros
    bin_padded = bin_data
    while len(bin_padded) % 4 != 0:
        bin_padded += b'\x00'

    total_length = 12 + 8 + len(json_str) + 8 + len(bin_padded)

    with open(output_path, 'wb') as f:
        # GLB header
        f.write(struct.pack('<4sII', b'glTF', 2, total_length))
        # JSON chunk
        f.write(struct.pack('<I4s', len(json_str), b'JSON'))
        f.write(json_str)
        # BIN chunk
        f.write(struct.pack('<I4s', len(bin_padded), b'BIN\x00'))
        f.write(bin_padded)


# ─── Batch Conversion ────────────────────────────────────────────────

def convert_dts(dts_path, output_path):
    """Convert a single DTS file to GLB."""
    try:
        shape = read_dts(dts_path)
    except Exception as e:
        print(f"  ERROR reading {dts_path}: {e}")
        return False

    if not shape['meshes'] or all(m['type'] == MESH_NULL for m in shape['meshes']):
        print(f"  SKIP {dts_path}: no geometry")
        return False

    try:
        gltf, bin_data = build_gltf(shape)
    except Exception as e:
        print(f"  ERROR building glTF for {dts_path}: {e}")
        return False

    if not gltf.get('meshes'):
        print(f"  SKIP {dts_path}: no exportable meshes")
        return False

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    write_glb(gltf, bin_data, output_path)
    return True


def batch_convert(input_dir, output_dir, limit=None):
    """Convert all DTS files under input_dir to GLB files under output_dir."""
    import glob as globmod
    dts_files = sorted(globmod.glob(os.path.join(input_dir, '**', '*.dts'), recursive=True))
    print(f"Found {len(dts_files)} DTS files")

    if limit:
        dts_files = dts_files[:limit]

    success = 0
    failed = 0
    skipped = 0

    for dts_path in dts_files:
        rel = os.path.relpath(dts_path, input_dir)
        out_path = os.path.join(output_dir, os.path.splitext(rel)[0] + '.glb')

        result = convert_dts(dts_path, out_path)
        if result:
            success += 1
            print(f"  OK: {rel}")
        elif result is False:
            # Could be skip or error (already printed)
            if os.path.exists(out_path):
                failed += 1
            else:
                skipped += 1

    print(f"\nResults: {success} converted, {skipped} skipped, {failed} failed out of {len(dts_files)}")
    return success, skipped, failed


def main():
    if len(sys.argv) < 2:
        print("Usage: dts_to_gltf.py <input.dts|input_dir> [output.glb|output_dir]")
        print("  Single file: dts_to_gltf.py model.dts model.glb")
        print("  Batch:       dts_to_gltf.py shapes/ output/models/")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None

    if os.path.isfile(input_path):
        if not output_path:
            output_path = os.path.splitext(input_path)[0] + '.glb'
        print(f"Converting: {input_path} -> {output_path}")
        if convert_dts(input_path, output_path):
            print(f"Done! Wrote {output_path}")
        else:
            print("Conversion failed.")
            sys.exit(1)
    elif os.path.isdir(input_path):
        if not output_path:
            output_path = './output/models'
        batch_convert(input_path, output_path)
    else:
        print(f"Error: {input_path} not found")
        sys.exit(1)


if __name__ == '__main__':
    main()
