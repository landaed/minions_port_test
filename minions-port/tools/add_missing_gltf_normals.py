#!/usr/bin/env python3
"""Add generated NORMAL attributes to converted GLB triangle primitives.

The Trinst interior GLBs came across with POSITION/TEXCOORD data only, which
left Godot without per-vertex normals for directional lighting. This helper is
idempotent: primitives that already have NORMAL data are left unchanged.
"""

import json, math, struct, sys
from pathlib import Path

COMPONENT_FORMAT = {5126: 'f', 5125: 'I', 5123: 'H', 5121: 'B', 5122: 'h', 5120: 'b'}
COMPONENT_SIZE = {k: struct.calcsize('<' + v) for k, v in COMPONENT_FORMAT.items()}
TYPE_COUNT = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}

def read_glb(path):
    data = path.read_bytes()
    magic, version, length = struct.unpack_from('<4sII', data, 0)
    if magic != b'glTF' or version != 2 or length != len(data):
        raise ValueError(f'{path}: not a GLB v2')
    off = 12
    chunks = []
    while off < len(data):
        clen, ctype = struct.unpack_from('<I4s', data, off)
        off += 8
        chunks.append((ctype, data[off:off + clen]))
        off += clen
    gltf = json.loads(chunks[0][1].decode('utf-8'))
    bin_chunk = next((c for t, c in chunks if t == b'BIN\x00'), b'')
    return gltf, bytearray(bin_chunk)

def accessor_values(gltf, bin_chunk, index):
    acc = gltf['accessors'][index]
    view = gltf['bufferViews'][acc['bufferView']]
    comps = TYPE_COUNT[acc['type']]
    fmt = COMPONENT_FORMAT[acc['componentType']]
    elem_size = COMPONENT_SIZE[acc['componentType']] * comps
    stride = view.get('byteStride', elem_size)
    offset = view.get('byteOffset', 0) + acc.get('byteOffset', 0)
    values = []
    for i in range(acc['count']):
        raw = struct.unpack_from('<' + fmt * comps, bin_chunk, offset + i * stride)
        values.append(raw if comps > 1 else raw[0])
    return values

def sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
def add(a, b): return (a[0] + b[0], a[1] + b[1], a[2] + b[2])
def norm(v):
    l = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    if l <= 1e-12:
        return (0.0, 1.0, 0.0)
    return (v[0] / l, v[1] / l, v[2] / l)

def pad4_bytes(buf, pad=b'\x00'):
    while len(buf) % 4:
        buf.extend(pad)

def add_accessor(gltf, bin_chunk, normals):
    pad4_bytes(bin_chunk)
    offset = len(bin_chunk)
    for n in normals:
        bin_chunk.extend(struct.pack('<fff', *n))
    byte_length = len(normals) * 12
    buffer_view_index = len(gltf.setdefault('bufferViews', []))
    gltf['bufferViews'].append({
        'buffer': 0,
        'byteOffset': offset,
        'byteLength': byte_length,
        'target': 34962,
    })
    accessor_index = len(gltf.setdefault('accessors', []))
    gltf['accessors'].append({
        'bufferView': buffer_view_index,
        'byteOffset': 0,
        'componentType': 5126,
        'count': len(normals),
        'type': 'VEC3',
    })
    gltf['buffers'][0]['byteLength'] = len(bin_chunk)
    return accessor_index

def write_glb(path, gltf, bin_chunk):
    pad4_bytes(bin_chunk)
    json_bytes = json.dumps(gltf, separators=(',', ':')).encode('utf-8')
    while len(json_bytes) % 4:
        json_bytes += b' '
    length = 12 + 8 + len(json_bytes) + 8 + len(bin_chunk)
    out = bytearray(struct.pack('<4sII', b'glTF', 2, length))
    out.extend(struct.pack('<I4s', len(json_bytes), b'JSON'))
    out.extend(json_bytes)
    out.extend(struct.pack('<I4s', len(bin_chunk), b'BIN\x00'))
    out.extend(bin_chunk)
    path.write_bytes(out)

def process(path):
    gltf, bin_chunk = read_glb(path)
    changed = 0
    for mesh in gltf.get('meshes', []):
        for prim in mesh.get('primitives', []):
            attrs = prim.get('attributes', {})
            if prim.get('mode', 4) != 4 or 'POSITION' not in attrs or 'NORMAL' in attrs:
                continue
            positions = accessor_values(gltf, bin_chunk, attrs['POSITION'])
            indices = accessor_values(gltf, bin_chunk, prim['indices']) if 'indices' in prim else list(range(len(positions)))
            accum = [(0.0, 0.0, 0.0) for _ in positions]
            for i in range(0, len(indices) - 2, 3):
                ia, ib, ic = int(indices[i]), int(indices[i + 1]), int(indices[i + 2])
                n = cross(sub(positions[ib], positions[ia]), sub(positions[ic], positions[ia]))
                accum[ia] = add(accum[ia], n)
                accum[ib] = add(accum[ib], n)
                accum[ic] = add(accum[ic], n)
            normals = [norm(v) for v in accum]
            attrs['NORMAL'] = add_accessor(gltf, bin_chunk, normals)
            changed += 1
    if changed:
        write_glb(path, gltf, bin_chunk)
    return changed

if __name__ == '__main__':
    total = 0
    for arg in sys.argv[1:]:
        changed = process(Path(arg))
        if changed:
            print(f'{arg}: added normals to {changed} primitives')
            total += changed
    print(f'total_primitives={total}')
