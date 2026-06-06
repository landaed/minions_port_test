#!/usr/bin/env python3
"""Pure-Python reader for Torque DSQ animation files (sequence-only export).

A .dsq is the sequence/keyframe half of a TSShape, written separately so one set
of animations can be shared across every model that uses the same skeleton (node
names). Targets the MoM version (<= 24). Plain sequential little-endian reads
(no alloc-buffer / guard scheme — that is DTS-only).

Read order cross-checked against qoh/io_scene_dts (DsqFile.py / Sequence.read),
the same reference the DTS reader follows.

Per sequence, a node's keyframe value is indexed node-major:
    rotations[seq.base_rotation + j*seq.num_keyframes + frame]
where j is the ordinal of that node among the nodes whose `rotationMatters` bit
is set (translations use base_translation / translationMatters likewise).
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass
class Sequence:
    name: str = ""
    flags: int = 0
    num_keyframes: int = 0
    duration: float = 0.0
    priority: int = 0
    first_ground_frame: int = 0
    num_ground_frames: int = 0
    base_rotation: int = 0
    base_translation: int = 0
    base_scale: int = 0
    base_objectstate: int = 0
    base_decalstate: int = 0
    first_trigger: int = 0
    num_triggers: int = 0
    tool_begin: float = 0.0
    rotation_matters: List[bool] = field(default_factory=list)
    translation_matters: List[bool] = field(default_factory=list)
    scale_matters: List[bool] = field(default_factory=list)


@dataclass
class Dsq:
    version: int = 0
    nodes: List[str] = field(default_factory=list)        # node names this anim drives
    rotations: list = field(default_factory=list)         # [(x,y,z,w), ...] quat16
    translations: list = field(default_factory=list)      # [(x,y,z), ...]
    uniform_scales: list = field(default_factory=list)
    aligned_scales: list = field(default_factory=list)
    sequences: List[Sequence] = field(default_factory=list)


class _R:
    def __init__(self, data: bytes):
        self.d = data
        self.o = 0

    def i32(self) -> int:
        v = struct.unpack_from("<i", self.d, self.o)[0]; self.o += 4; return v

    def u32(self) -> int:
        v = struct.unpack_from("<I", self.d, self.o)[0]; self.o += 4; return v

    def f32(self) -> float:
        v = struct.unpack_from("<f", self.d, self.o)[0]; self.o += 4; return v

    def vec3(self):
        v = struct.unpack_from("<3f", self.d, self.o); self.o += 12; return v

    def quat16(self):
        x, y, z, w = struct.unpack_from("<4h", self.d, self.o); self.o += 8
        return (x / 32767.0, y / 32767.0, z / 32767.0, w / 32767.0)

    def name(self) -> str:
        n = self.u32()
        s = self.d[self.o:self.o + n].decode("cp1252", "replace")
        self.o += n
        return s

    def bit_set(self) -> List[bool]:
        _dummy = self.i32()
        num_words = self.i32()
        words = struct.unpack_from("<%di" % num_words, self.d, self.o)
        self.o += 4 * num_words
        total = num_words * 32
        return [(words[i >> 5] & (1 << (i & 31))) != 0 for i in range(total)]


def _read_sequence(r: _R) -> Sequence:
    s = Sequence()
    s.flags = r.u32()
    s.num_keyframes = r.i32()
    s.duration = r.f32()
    s.priority = r.i32()
    s.first_ground_frame = r.i32()
    s.num_ground_frames = r.i32()
    s.base_rotation = r.i32()
    s.base_translation = r.i32()
    s.base_scale = r.i32()
    s.base_objectstate = r.i32()
    s.base_decalstate = r.i32()
    s.first_trigger = r.i32()
    s.num_triggers = r.i32()
    s.tool_begin = r.f32()
    s.rotation_matters = r.bit_set()
    s.translation_matters = r.bit_set()
    s.scale_matters = r.bit_set()
    _decal = r.bit_set()
    _ifl = r.bit_set()
    _vis = r.bit_set()
    _frame = r.bit_set()
    _matframe = r.bit_set()
    return s


def read_dsq(data: bytes) -> Dsq:
    r = _R(data)
    dsq = Dsq()
    dsq.version = r.i32()
    num_nodes = r.i32()
    dsq.nodes = [r.name() for _ in range(num_nodes)]
    r.i32()  # legacy size
    r.i32()  # old_shape_num_objects
    if dsq.version > 21:
        dsq.rotations = [r.quat16() for _ in range(r.i32())]
        dsq.translations = [r.vec3() for _ in range(r.i32())]
        dsq.uniform_scales = [r.f32() for _ in range(r.i32())]
        dsq.aligned_scales = [r.vec3() for _ in range(r.i32())]
        sz = r.i32()  # arbitrary scales: rot quat + factor vec
        [r.quat16() for _ in range(sz)]
        [r.vec3() for _ in range(sz)]
        sz = r.i32()  # ground transforms
        [r.vec3() for _ in range(sz)]
        [r.quat16() for _ in range(sz)]
    else:
        sz = r.i32()
        for _ in range(sz):
            dsq.rotations.append(r.quat16())
            dsq.translations.append(r.vec3())
    r.i32()  # legacy
    num_seqs = r.i32()
    for _ in range(num_seqs):
        name = r.name()
        seq = _read_sequence(r)
        seq.name = name
        dsq.sequences.append(seq)
    return dsq


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else \
        "MoMReborn/minions.of.mirth/data/shapes/character/animations/humanoid/1hwalk.dsq"
    dsq = read_dsq(open(path, "rb").read())
    print("FILE", path, "v%d" % dsq.version)
    print("  nodes(%d):" % len(dsq.nodes), dsq.nodes[:6], "...")
    print("  rotations=%d translations=%d uscale=%d aligned=%d" % (
        len(dsq.rotations), len(dsq.translations),
        len(dsq.uniform_scales), len(dsq.aligned_scales)))
    print("  sequences(%d):" % len(dsq.sequences))
    for s in dsq.sequences:
        nrot = sum(s.rotation_matters)
        ntrans = sum(s.translation_matters)
        print("    %-16s frames=%-3d dur=%.3f rotNodes=%d transNodes=%d baseRot=%d baseTrans=%d" % (
            s.name, s.num_keyframes, s.duration, nrot, ntrans,
            s.base_rotation, s.base_translation))
