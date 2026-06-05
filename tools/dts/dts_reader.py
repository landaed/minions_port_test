#!/usr/bin/env python3
"""Pure-Python reader for Torque Game Engine DTS (Dynamix Three Space) shapes.

Targets DTS version 24 (the version used by Minions of Mirth). Parses the
tri-stream "alloc" buffer (32/16/8-bit regions) including Torque's guard
checkpoints, then exposes nodes, objects, detail levels, meshes (vertices,
texcoords, normals, per-material triangle lists) and the material list.

The binary read order / guard scheme follows Torque's TSShape::read. Cross-checked
against the MIT-licensed reference implementation qoh/io_scene_dts
(https://github.com/qoh/io_scene_dts) for exact field ordering.

A correct parse is self-validating: at every guard the 32/16/8 streams all carry
the same incrementing dummy counter, and at end-of-shape all three stream cursors
must have consumed their regions exactly.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import List, Tuple

# TSDrawPrimitive flag bits (packed into the primitive "type" u32)
PRIM_TRIANGLES = 0x00000000
PRIM_STRIP     = 0x40000000
PRIM_FAN       = 0x80000000
PRIM_TYPE_MASK = 0xC0000000
PRIM_INDEXED   = 0x20000000
PRIM_NOMAT     = 0x10000000
PRIM_MAT_MASK  = 0x0FFFFFFF

# TSMesh types
MESH_STANDARD = 0
MESH_SKIN     = 1
MESH_DECAL    = 2
MESH_SORTED   = 3
MESH_NULL     = 4
MESH_TYPE_MASK = 0xFFFFFFFF


class GuardError(Exception):
    pass


class Stream:
    """Reader over the DTS tri-stream alloc buffer + raw tail."""

    def __init__(self, data: bytes):
        self.data = data
        self.version, self.exporter = struct.unpack_from("<HH", data, 0)
        size_mem, start16, start8 = struct.unpack_from("<III", data, 4)
        self.size_mem = size_mem
        self.start16 = start16
        self.start8 = start8
        # byte bases of each region (the 3 dwords of header live at bytes 4..16)
        self.base32 = 16
        self.base16 = 16 + start16 * 4
        self.base8 = 16 + start8 * 4
        self.end_buffer = 16 + size_mem * 4
        # element cursors
        self.t32 = 0  # word index within [0, start16)
        self.t16 = 0  # short index within 16-region
        self.t8 = 0   # byte index within 8-region
        self.guard_count = 0
        # raw tail cursor (sequences + material list), absolute byte offset
        self.tail = self.end_buffer

    # --- buffer reads ---
    def read32(self) -> int:
        v = struct.unpack_from("<i", self.data, self.base32 + self.t32 * 4)[0]
        self.t32 += 1
        return v

    def read_u32(self) -> int:
        v = struct.unpack_from("<I", self.data, self.base32 + self.t32 * 4)[0]
        self.t32 += 1
        return v

    def read_float(self) -> float:
        v = struct.unpack_from("<f", self.data, self.base32 + self.t32 * 4)[0]
        self.t32 += 1
        return v

    def read16(self) -> int:
        v = struct.unpack_from("<H", self.data, self.base16 + self.t16 * 2)[0]
        self.t16 += 1
        return v

    def read_s16(self) -> int:
        v = struct.unpack_from("<h", self.data, self.base16 + self.t16 * 2)[0]
        self.t16 += 1
        return v

    def read8(self) -> int:
        v = self.data[self.base8 + self.t8]
        self.t8 += 1
        return v

    def read_vec2(self) -> Tuple[float, float]:
        return (self.read_float(), self.read_float())

    def read_vec3(self) -> Tuple[float, float, float]:
        return (self.read_float(), self.read_float(), self.read_float())

    def read_box(self):
        return (self.read_vec3(), self.read_vec3())

    def read_quat16(self):
        # 4 signed int16 normalized by 32767 -> (x, y, z, w)
        x = self.read_s16() / 32767.0
        y = self.read_s16() / 32767.0
        z = self.read_s16() / 32767.0
        w = self.read_s16() / 32767.0
        return (x, y, z, w)

    def read_string(self) -> str:
        out = bytearray()
        while True:
            b = self.read8()
            if b == 0:
                break
            out.append(b)
        return out.decode("latin-1")

    def guard(self):
        a = self.read32()
        b = self.read16()
        c = self.read8()
        if not (a == b == c == self.guard_count):
            raise GuardError(
                f"guard #{self.guard_count} mismatch: 32={a} 16={b} 8={c} "
                f"(t32={self.t32} t16={self.t16} t8={self.t8})"
            )
        self.guard_count += 1

    # --- raw tail reads (material list / sequences) ---
    def tail_u32(self) -> int:
        v = struct.unpack_from("<I", self.data, self.tail)[0]
        self.tail += 4
        return v

    def tail_s32(self) -> int:
        v = struct.unpack_from("<i", self.data, self.tail)[0]
        self.tail += 4
        return v

    def tail_u8(self) -> int:
        v = self.data[self.tail]
        self.tail += 1
        return v

    def tail_pstring(self) -> str:
        n = self.tail_u8()
        s = self.data[self.tail:self.tail + n].decode("latin-1")
        self.tail += n
        return s


@dataclass
class Node:
    name: int
    parent: int
    first_object: int
    first_child: int
    next_sibling: int


@dataclass
class Object:
    name: int
    num_meshes: int
    first_mesh: int
    node: int
    next_sibling: int
    first_decal: int


@dataclass
class Detail:
    name: int
    subshape: int
    object_detail: int
    size: float
    avg_error: float
    max_error: float
    poly_count: int


@dataclass
class Mesh:
    mtype: int = MESH_NULL
    verts: List[Tuple[float, float, float]] = field(default_factory=list)
    tverts: List[Tuple[float, float]] = field(default_factory=list)
    normals: List[Tuple[float, float, float]] = field(default_factory=list)
    # triangle indices grouped by material index: {mat: [(i0,i1,i2), ...]}
    tris_by_mat: dict = field(default_factory=dict)
    bounds: tuple = None
    radius: float = 0.0


@dataclass
class Shape:
    version: int = 0
    radius: float = 0.0
    center: tuple = (0, 0, 0)
    bounds: tuple = None
    nodes: List[Node] = field(default_factory=list)
    objects: List[Object] = field(default_factory=list)
    details: List[Detail] = field(default_factory=list)
    meshes: List[Mesh] = field(default_factory=list)
    names: List[str] = field(default_factory=list)
    materials: List[str] = field(default_factory=list)
    default_translations: list = field(default_factory=list)
    default_rotations: list = field(default_factory=list)


def _triangulate(prim_type: int, elems: List[int]) -> List[Tuple[int, int, int]]:
    tris = []
    n = len(elems)
    kind = prim_type & PRIM_TYPE_MASK
    if kind == PRIM_STRIP:
        for i in range(n - 2):
            if i % 2 == 0:
                tris.append((elems[i], elems[i + 1], elems[i + 2]))
            else:
                tris.append((elems[i + 1], elems[i], elems[i + 2]))
    elif kind == PRIM_FAN:
        for i in range(1, n - 1):
            tris.append((elems[0], elems[i], elems[i + 1]))
    else:  # triangle list
        for i in range(0, n - 2, 3):
            tris.append((elems[i], elems[i + 1], elems[i + 2]))
    return tris


def _read_mesh(s: Stream) -> Mesh:
    mtype = s.read32() & MESH_TYPE_MASK
    mesh = Mesh(mtype=mtype)
    if mtype == MESH_NULL:
        return mesh
    s.guard()  # opening guard
    num_frames = s.read32()
    num_mat_frames = s.read32()
    parent = s.read32()
    mesh.bounds = s.read_box()
    center = s.read_vec3()
    mesh.radius = s.read_float()

    n_vert = s.read32()
    mesh.verts = [s.read_vec3() for _ in range(n_vert)]
    n_tvert = s.read32()
    mesh.tverts = [s.read_vec2() for _ in range(n_tvert)]
    mesh.normals = [s.read_vec3() for _ in range(n_vert)]
    _enc = [s.read8() for _ in range(n_vert)]  # encoded normals (unused)

    n_prim = s.read32()
    prims = [(s.read16(), s.read16(), s.read_u32()) for _ in range(n_prim)]
    n_idx = s.read32()
    indices = [s.read16() for _ in range(n_idx)]
    n_midx = s.read32()
    _midx = [s.read16() for _ in range(n_midx)]
    verts_per_frame = s.read32()
    flags = s.read_u32()

    if mtype == MESH_SKIN:
        # Skin meshes carry extra data after the standard block. Read it so the
        # stream stays aligned (geometry handled like a static mesh for now).
        n_iv = s.read32()
        [s.read_vec3() for _ in range(n_iv)]      # initial verts
        [s.read_vec3() for _ in range(n_iv)]      # initial norms
        n_node_index = s.read32()
        [s.read32() for _ in range(n_node_index)]  # node index
        n_vindex = s.read32()
        [s.read32() for _ in range(n_vindex)]      # vertex index
        n_weight = s.read32()
        [s.read_float() for _ in range(n_weight)]  # weights
        n_ntrans = s.read32()
        [tuple(s.read_float() for _ in range(16)) for _ in range(n_ntrans)]  # node transforms

    s.guard()  # closing guard

    # decode primitives into per-material triangle lists
    for start, count, ptype in prims:
        mat = ptype & PRIM_MAT_MASK if not (ptype & PRIM_NOMAT) else -1
        elems = indices[start:start + count]
        for tri in _triangulate(ptype, elems):
            mesh.tris_by_mat.setdefault(mat, []).append(tri)
    return mesh


def read_shape(data: bytes) -> Shape:
    s = Stream(data)
    if s.version != 24:
        # parser validated against v24; other versions may differ
        pass
    shape = Shape(version=s.version)

    n_node = s.read32()
    n_object = s.read32()
    n_decal = s.read32()
    n_subshape = s.read32()
    n_ifl = s.read32()
    n_node_rot = s.read32()
    n_node_trans = s.read32()
    n_scale_uniform = s.read32()
    n_scale_aligned = s.read32()
    n_scale_arbitrary = s.read32()
    n_ground = s.read32() if s.version > 23 else 0
    n_objectstate = s.read32()
    n_decalstate = s.read32()
    n_trigger = s.read32()
    n_detail = s.read32()
    n_mesh = s.read32()
    n_name = s.read32()
    _smallest_size = s.read_float()
    _smallest_dl = s.read32()
    s.guard()  # G0

    shape.radius = s.read_float()
    _tube = s.read_float()
    shape.center = s.read_vec3()
    shape.bounds = s.read_box()
    s.guard()  # G1

    shape.nodes = [Node(s.read32(), s.read32(), s.read32(), s.read32(), s.read32())
                   for _ in range(n_node)]
    s.guard()  # G2

    shape.objects = [Object(s.read32(), s.read32(), s.read32(), s.read32(), s.read32(), s.read32())
                     for _ in range(n_object)]
    s.guard()  # G3

    for _ in range(n_decal):  # decals (deprecated): 5 x s32
        [s.read32() for _ in range(5)]
    s.guard()  # G4

    for _ in range(n_ifl):  # IFL materials: name s32, slot s32, firstFrame s32, time s32, count s32
        [s.read32() for _ in range(5)]
    s.guard()  # G5

    # subshapes
    [s.read32() for _ in range(n_subshape)]  # firstNode
    [s.read32() for _ in range(n_subshape)]  # firstObject
    [s.read32() for _ in range(n_subshape)]  # firstDecal
    s.guard()  # G6
    [s.read32() for _ in range(n_subshape)]  # numNodes
    [s.read32() for _ in range(n_subshape)]  # numObjects
    [s.read32() for _ in range(n_subshape)]  # numDecals
    s.guard()  # G7

    # default + animation node transforms
    shape.default_rotations = [s.read_quat16() for _ in range(n_node)]
    shape.default_translations = [s.read_vec3() for _ in range(n_node)]
    [s.read_vec3() for _ in range(n_node_trans)]   # anim translations
    [s.read_quat16() for _ in range(n_node_rot)]   # anim rotations
    s.guard()  # G8

    [s.read_float() for _ in range(n_scale_uniform)]
    [s.read_vec3() for _ in range(n_scale_aligned)]
    [s.read_vec3() for _ in range(n_scale_arbitrary)]
    [s.read_quat16() for _ in range(n_scale_arbitrary)]
    s.guard()  # G9

    [s.read_vec3() for _ in range(n_ground)]
    [s.read_quat16() for _ in range(n_ground)]
    s.guard()  # G10

    for _ in range(n_objectstate):
        s.read_float(); s.read32(); s.read32()
    s.guard()  # G11

    [s.read32() for _ in range(n_decalstate)]
    s.guard()  # G12

    for _ in range(n_trigger):
        s.read_u32(); s.read_float()
    s.guard()  # G13

    shape.details = [Detail(s.read32(), s.read32(), s.read32(),
                            s.read_float(), s.read_float(), s.read_float(), s.read32())
                     for _ in range(n_detail)]
    s.guard()  # G14

    shape.meshes = [_read_mesh(s) for _ in range(n_mesh)]
    s.guard()  # G15

    shape.names = [s.read_string() for _ in range(n_name)]
    s.guard()  # G16

    # validate full buffer consumption
    shape._cursor_check = {
        "t32": s.t32, "start16": s.start16,
        "t16": s.t16, "expect16": 2 * (s.start8 - s.start16),
        "t8": s.t8, "expect8": 4 * (s.size_mem - s.start8),
    }

    # tail: sequences then material list
    try:
        n_seq = s.tail_s32()
        if n_seq == 0:
            n_mat = s.tail_u32()
            shape.materials = [s.tail_pstring() for _ in range(n_mat)]
    except Exception:
        pass

    return shape


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else \
        "MoMReborn/minions.of.mirth/data/shapes/objects/book_1.dts"
    data = open(path, "rb").read()
    sh = read_shape(data)
    cc = sh._cursor_check
    # 32-bit region must be consumed exactly; 16/8 regions are word-padded at the
    # end (<=2 bytes / <=3 bytes of alignment padding), so allow that slack.
    ok32 = cc["t32"] == cc["start16"]
    ok16 = 0 <= cc["expect16"] - cc["t16"] <= 1
    ok8 = 0 <= cc["expect8"] - cc["t8"] <= 3
    print(f"FILE {path}  v{sh.version}")
    print(f"  nodes={len(sh.nodes)} objects={len(sh.objects)} details={len(sh.details)} "
          f"meshes={len(sh.meshes)} names={len(sh.names)}")
    print(f"  radius={sh.radius:.3f} bounds={sh.bounds}")
    print(f"  names={sh.names}")
    print(f"  materials={sh.materials}")
    tot_tris = sum(sum(len(v) for v in m.tris_by_mat.values()) for m in sh.meshes)
    tot_verts = sum(len(m.verts) for m in sh.meshes)
    print(f"  total verts={tot_verts}  total tris={tot_tris}")
    print(f"  CURSOR CHECK  32:{ok32}({cc['t32']}/{cc['start16']})  "
          f"16:{ok16}({cc['t16']}/{cc['expect16']})  8:{ok8}({cc['t8']}/{cc['expect8']})")
    print("  PARSE_OK" if (ok32 and ok16 and ok8) else "  PARSE_MISALIGNED")
