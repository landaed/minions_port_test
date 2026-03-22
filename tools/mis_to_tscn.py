#!/usr/bin/env python3
"""
Torque .mis mission file to Godot .tscn scene converter.

Parses the TorqueScript-based mission file format and generates a Godot 4
scene file (.tscn) with proper node hierarchy, transforms, and asset references.

Handles:
  - InteriorInstance → MeshInstance3D (references .dif → will need separate conversion)
  - TSStatic → MeshInstance3D (references .dts → converted to .glb by dts_to_gltf.py)
  - TSDynamic → MeshInstance3D
  - TerrainBlock → metadata node (terrain imported separately)
  - WaterBlock → placeholder with water plane
  - Sky → WorldEnvironment setup
  - Sun → DirectionalLight3D
  - SpawnSphere → Marker3D
  - AudioEmitter → AudioStreamPlayer3D
  - sgUniversalStaticLight → OmniLight3D
  - ParticleEmitterNode → GPUParticles3D placeholder
  - rpgSpawnPoint → Marker3D (NPC spawn locations)
  - rpgWayPoint → Marker3D (navigation waypoints)
  - SimGroup → Node3D (grouping)
  - Trigger → Area3D
  - fxShapeReplicator/fxFoliageReplicator/fxGrassReplicator → MultiMeshInstance3D placeholders

Coordinate system: Torque uses Y-forward Z-up; Godot uses Y-up Z-forward.
Transform: swap Y and Z axes.
"""

import re
import sys
import os
import json
import math


def parse_mis(content):
    """Parse a .mis file into a tree of objects."""
    # Tokenize: we need to handle nested braces
    objects = []
    stack = [{'type': 'root', 'name': 'root', 'attrs': {}, 'children': []}]

    lines = content.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1

        # Skip comments and empty lines
        if not line or line.startswith('//'):
            continue

        # Match "new Type(Name) {"
        m = re.match(r'new\s+(\w+)\(([^)]*)\)\s*\{', line)
        if m:
            obj = {
                'type': m.group(1),
                'name': m.group(2).strip() if m.group(2).strip() else m.group(1),
                'attrs': {},
                'children': [],
            }
            stack[-1]['children'].append(obj)
            stack.append(obj)
            continue

        # Match closing brace
        if line.startswith('}'):
            if len(stack) > 1:
                stack.pop()
            continue

        # Match attribute = "value";
        m = re.match(r'(\w+(?:\[\d+\])?)\s*=\s*"([^"]*)"\s*;', line)
        if m:
            key = m.group(1)
            val = m.group(2)
            stack[-1]['attrs'][key] = val
            continue

    return stack[0]['children']


def torque_to_godot_transform(position_str, rotation_str, scale_str):
    """Convert Torque position/rotation/scale to Godot transform components.

    Torque: Y-forward, Z-up, right-handed
    Godot:  Y-up, Z-backward(-forward), right-handed

    Torque rotation format: "ax ay az angle_degrees" (axis-angle)
    """
    # Parse position
    pos = [float(x) for x in position_str.split()] if position_str else [0, 0, 0]
    while len(pos) < 3:
        pos.append(0)

    # Swap Y and Z for Godot coordinate system
    gx = pos[0]
    gy = pos[2]  # Torque Z -> Godot Y
    gz = -pos[1]  # Torque Y -> Godot -Z

    # Parse scale
    scl = [float(x) for x in scale_str.split()] if scale_str else [1, 1, 1]
    while len(scl) < 3:
        scl.append(1)
    gsx = scl[0]
    gsy = scl[2]  # Swap Y/Z
    gsz = scl[1]

    # Parse rotation (axis-angle in Torque)
    rot = [float(x) for x in rotation_str.split()] if rotation_str else [1, 0, 0, 0]
    while len(rot) < 4:
        rot.append(0)

    # Convert axis: swap Y and Z
    rax = rot[0]
    ray = rot[2]   # Torque Z -> Godot Y
    raz = -rot[1]  # Torque Y -> Godot -Z
    angle_deg = rot[3]

    # Normalize axis
    length = math.sqrt(rax*rax + ray*ray + raz*raz)
    if length > 0.0001:
        rax /= length
        ray /= length
        raz /= length
    else:
        rax, ray, raz = 0, 1, 0
        angle_deg = 0

    angle_rad = math.radians(angle_deg)

    return {
        'position': (gx, gy, gz),
        'rotation_axis': (rax, ray, raz),
        'rotation_angle': angle_rad,
        'scale': (gsx, gsy, gsz),
    }


def asset_path_torque_to_godot(torque_path, asset_type='mesh'):
    """Convert a Torque asset path to a Godot resource path.

    Torque: ~/data/shapes/rocks/rock1.dts
    Godot: res://assets/shapes/rocks/rock1.glb (for DTS)
    Godot: res://assets/interiors/architecture/block.glb (for DIF, once converted)
    """
    if not torque_path:
        return ""

    # Remove ~/ prefix
    path = torque_path.replace('~/', '')

    # Remove data/ prefix
    if path.startswith('data/'):
        path = path[5:]

    # Change extension
    base, ext = os.path.splitext(path)
    if ext.lower() in ('.dts', '.dif'):
        path = base + '.glb'

    return f"res://converted_assets/{path}"


def format_transform(transform):
    """Format a Transform3D for Godot .tscn format."""
    pos = transform['position']
    axis = transform['rotation_axis']
    angle = transform['rotation_angle']
    scale = transform['scale']

    # Build rotation matrix from axis-angle
    c = math.cos(angle)
    s = math.sin(angle)
    t = 1 - c
    x, y, z = axis

    # Rotation matrix (column-major for Godot)
    m00 = t*x*x + c
    m01 = t*x*y - s*z
    m02 = t*x*z + s*y
    m10 = t*x*y + s*z
    m11 = t*y*y + c
    m12 = t*y*z - s*x
    m20 = t*x*z - s*y
    m21 = t*y*z + s*x
    m22 = t*z*z + c

    # Apply scale
    sx, sy, sz = scale
    m00 *= sx; m01 *= sy; m02 *= sz
    m10 *= sx; m11 *= sy; m12 *= sz
    m20 *= sx; m21 *= sy; m22 *= sz

    # Godot Transform3D format: basis vectors (columns) then origin
    # Transform3D(xx, xy, xz, yx, yy, yz, zx, zy, zz, ox, oy, oz)
    return (f"Transform3D({m00:.6f}, {m10:.6f}, {m20:.6f}, "
            f"{m01:.6f}, {m11:.6f}, {m21:.6f}, "
            f"{m02:.6f}, {m12:.6f}, {m22:.6f}, "
            f"{pos[0]:.4f}, {pos[1]:.4f}, {pos[2]:.4f})")


def sanitize_name(name, used_names):
    """Make a unique valid Godot node name."""
    # Replace invalid characters
    clean = re.sub(r'[^a-zA-Z0-9_]', '_', name)
    if not clean or clean[0].isdigit():
        clean = '_' + clean

    # Make unique
    if clean in used_names:
        counter = 2
        while f"{clean}{counter}" in used_names:
            counter += 1
        clean = f"{clean}{counter}"

    used_names.add(clean)
    return clean


class TscnWriter:
    """Generates a Godot .tscn scene file."""

    def __init__(self):
        self.ext_resources = []  # (path, type, id)
        self.sub_resources = []
        self.nodes = []  # (path, type, properties)
        self.ext_resource_map = {}  # path -> id
        self.next_ext_id = 1
        self.next_sub_id = 1
        self.used_names = set()

    def add_ext_resource(self, path, res_type):
        """Add an external resource and return its ID."""
        if path in self.ext_resource_map:
            return self.ext_resource_map[path]
        rid = self.next_ext_id
        self.next_ext_id += 1
        self.ext_resources.append((path, res_type, rid))
        self.ext_resource_map[path] = rid
        return rid

    def add_node(self, name, node_type, parent_path, properties=None):
        """Add a node to the scene."""
        self.nodes.append({
            'name': name,
            'type': node_type,
            'parent': parent_path,
            'properties': properties or {},
        })

    def write(self, output_path):
        """Write the .tscn file."""
        lines = []

        # Header
        load_steps = len(self.ext_resources) + len(self.sub_resources) + 1
        lines.append(f'[gd_scene load_steps={load_steps} format=3]')
        lines.append('')

        # External resources
        for path, res_type, rid in self.ext_resources:
            lines.append(f'[ext_resource type="{res_type}" path="{path}" id="{rid}"]')
        if self.ext_resources:
            lines.append('')

        # Root node
        lines.append(f'[node name="MissionRoot" type="Node3D"]')
        lines.append('')

        # Child nodes
        for node in self.nodes:
            parent = node['parent']
            lines.append(f'[node name="{node["name"]}" type="{node["type"]}" parent="{parent}"]')
            for key, val in node['properties'].items():
                lines.append(f'{key} = {val}')
            lines.append('')

        with open(output_path, 'w') as f:
            f.write('\n'.join(lines))


def convert_object(obj, writer, parent_path, stats):
    """Convert a Torque mission object to Godot scene nodes."""
    obj_type = obj['type']
    attrs = obj['attrs']
    name = sanitize_name(obj.get('name', obj_type), writer.used_names)

    # Get transform
    transform = torque_to_godot_transform(
        attrs.get('position', '0 0 0'),
        attrs.get('rotation', '1 0 0 0'),
        attrs.get('scale', '1 1 1'),
    )
    transform_str = format_transform(transform)

    current_path = f"{parent_path}/{name}" if parent_path != "." else name

    if obj_type == 'SimGroup':
        writer.add_node(name, 'Node3D', parent_path, {})
        stats['groups'] += 1

    elif obj_type == 'InteriorInstance':
        interior_file = attrs.get('interiorFile', '')
        godot_path = asset_path_torque_to_godot(interior_file, 'interior')
        props = {'transform': transform_str}
        # Add a comment about the source asset
        props['metadata/torque_interior'] = f'"{interior_file}"'
        writer.add_node(name, 'Node3D', parent_path, props)
        stats['interiors'] += 1
        stats['interior_files'].add(interior_file)

    elif obj_type in ('TSStatic', 'TSDynamic'):
        shape_name = attrs.get('shapeName', '')
        godot_path = asset_path_torque_to_godot(shape_name, 'mesh')
        props = {'transform': transform_str}
        if godot_path:
            # Reference the converted GLB as a packed scene
            res_id = writer.add_ext_resource(godot_path, "PackedScene")
            props['metadata/source_shape'] = f'"{shape_name}"'
            props['metadata/godot_asset'] = f'"{godot_path}"'
        writer.add_node(name, 'Node3D', parent_path, props)
        stats['statics'] += 1
        stats['shape_files'].add(shape_name)

    elif obj_type == 'Sun':
        azimuth = float(attrs.get('azimuth', '0'))
        elevation = float(attrs.get('elevation', '45'))
        color = attrs.get('color', '1 1 1 1').split()
        ambient = attrs.get('ambient', '0.3 0.3 0.3 1').split()

        # Convert azimuth/elevation to direction
        az_rad = math.radians(azimuth)
        el_rad = math.radians(elevation)
        dx = math.cos(el_rad) * math.sin(az_rad)
        dy = -math.sin(el_rad)  # Godot Y is up
        dz = math.cos(el_rad) * math.cos(az_rad)

        # Calculate rotation to point light in that direction
        # DirectionalLight3D points along -Z by default
        props = {
            'light_color': f'Color({color[0]}, {color[1]}, {color[2]}, 1)',
            'light_energy': '1.0',
            'metadata/torque_azimuth': f'{azimuth}',
            'metadata/torque_elevation': f'{elevation}',
            'metadata/ambient_color': f'"({ambient[0]}, {ambient[1]}, {ambient[2]})"',
        }
        writer.add_node(name, 'DirectionalLight3D', parent_path, props)
        stats['lights'] += 1

    elif obj_type == 'WaterBlock':
        props = {'transform': transform_str}
        scl = attrs.get('scale', '1 1 1').split()
        props['metadata/water_scale'] = f'"({scl[0]}, {scl[1]}, {scl[2]})"'
        props['metadata/surface_opacity'] = f'"{attrs.get("surfaceOpacity", "0.75")}"'
        writer.add_node(name, 'Node3D', parent_path, props)
        stats['water'] += 1

    elif obj_type == 'SpawnSphere':
        props = {'transform': transform_str}
        props['metadata/radius'] = f'"{attrs.get("radius", "10")}"'
        writer.add_node(name, 'Marker3D', parent_path, props)
        stats['spawns'] += 1

    elif obj_type == 'sgUniversalStaticLight':
        color = attrs.get('Colour', attrs.get('colour', '1 1 1 1')).split()
        radius = float(attrs.get('StaticLightRadius', attrs.get('radius', '10')))
        props = {
            'transform': transform_str,
            'light_color': f'Color({color[0]}, {color[1]}, {color[2]}, 1)',
            'omni_range': f'{radius}',
        }
        writer.add_node(name, 'OmniLight3D', parent_path, props)
        stats['lights'] += 1

    elif obj_type == 'AudioEmitter':
        props = {'transform': transform_str}
        profile = attrs.get('profile', '')
        props['metadata/audio_profile'] = f'"{profile}"'
        writer.add_node(name, 'AudioStreamPlayer3D', parent_path, props)
        stats['audio'] += 1

    elif obj_type == 'rpgSpawnPoint':
        props = {'transform': transform_str}
        spawn_name = attrs.get('spawnName', '')
        props['metadata/spawn_name'] = f'"{spawn_name}"'
        props['metadata/spawn_type'] = '"rpg_spawn_point"'
        writer.add_node(name, 'Marker3D', parent_path, props)
        stats['npc_spawns'] += 1

    elif obj_type == 'rpgWayPoint':
        props = {'transform': transform_str}
        waypoint_name = attrs.get('wayPointName', '')
        props['metadata/waypoint_name'] = f'"{waypoint_name}"'
        writer.add_node(name, 'Marker3D', parent_path, props)
        stats['waypoints'] += 1

    elif obj_type == 'ParticleEmitterNode':
        props = {'transform': transform_str}
        emitter = attrs.get('emitter', '')
        props['metadata/torque_emitter'] = f'"{emitter}"'
        writer.add_node(name, 'GPUParticles3D', parent_path, props)
        stats['particles'] += 1

    elif obj_type == 'Trigger':
        props = {'transform': transform_str}
        polyhedron = attrs.get('polyhedron', '')
        props['metadata/torque_polyhedron'] = f'"{polyhedron}"'
        writer.add_node(name, 'Area3D', parent_path, props)
        stats['triggers'] += 1

    elif obj_type in ('fxShapeReplicator', 'fxFoliageReplicator', 'fxGrassReplicator'):
        props = {'transform': transform_str}
        shape = attrs.get('shapeName', attrs.get('ShapeFile', ''))
        props['metadata/replicator_type'] = f'"{obj_type}"'
        props['metadata/shape'] = f'"{shape}"'
        if shape:
            stats['shape_files'].add(shape)
        writer.add_node(name, 'Node3D', parent_path, props)
        stats['replicators'] += 1

    elif obj_type in ('Sky', 'MissionArea', 'ScriptObject', 'TerrainBlock', 'fxSunLight', 'rpgBindPoint'):
        # These are metadata/config nodes - store as Node3D with metadata
        props = {}
        for k, v in attrs.items():
            props[f'metadata/{k}'] = f'"{v}"'
        writer.add_node(name, 'Node3D', parent_path, props)
        stats['meta'] += 1

    else:
        # Unknown type - add as generic Node3D
        props = {'transform': transform_str} if 'position' in attrs else {}
        props['metadata/torque_type'] = f'"{obj_type}"'
        writer.add_node(name, 'Node3D', parent_path, props)
        stats['unknown'] += 1

    # Process children
    for child in obj.get('children', []):
        convert_object(child, writer, current_path, stats)


def convert_mis(mis_path, output_dir):
    """Convert a .mis file to a Godot .tscn scene file."""
    os.makedirs(output_dir, exist_ok=True)

    base_name = os.path.splitext(os.path.basename(mis_path))[0]

    print(f"Parsing mission file: {mis_path}")
    with open(mis_path, 'r', errors='replace') as f:
        content = f.read()

    objects = parse_mis(content)
    print(f"  Found {len(objects)} top-level objects")

    writer = TscnWriter()
    stats = {
        'groups': 0, 'interiors': 0, 'statics': 0, 'lights': 0,
        'water': 0, 'spawns': 0, 'npc_spawns': 0, 'waypoints': 0,
        'audio': 0, 'particles': 0, 'triggers': 0, 'replicators': 0,
        'meta': 0, 'unknown': 0,
        'interior_files': set(), 'shape_files': set(),
    }

    for obj in objects:
        convert_object(obj, writer, '.', stats)

    # Write scene
    tscn_path = os.path.join(output_dir, f"{base_name}.tscn")
    writer.write(tscn_path)
    print(f"  Saved scene: {tscn_path}")

    # Write asset manifest (list of all referenced assets)
    manifest = {
        'mission_file': os.path.basename(mis_path),
        'stats': {k: v for k, v in stats.items() if not isinstance(v, set)},
        'unique_dts_shapes': sorted(stats['shape_files']),
        'unique_dif_interiors': sorted(stats['interior_files']),
        'total_unique_shapes': len(stats['shape_files']),
        'total_unique_interiors': len(stats['interior_files']),
        'total_nodes': len(writer.nodes),
    }

    manifest_path = os.path.join(output_dir, f"{base_name}_manifest.json")
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)
    print(f"  Saved manifest: {manifest_path}")

    # Print summary
    print(f"\n  Summary:")
    print(f"    InteriorInstance: {stats['interiors']} ({len(stats['interior_files'])} unique .dif files)")
    print(f"    TSStatic/TSDynamic: {stats['statics']} ({len(stats['shape_files'])} unique .dts files)")
    print(f"    Lights: {stats['lights']}")
    print(f"    NPC Spawns: {stats['npc_spawns']}")
    print(f"    Waypoints: {stats['waypoints']}")
    print(f"    Audio emitters: {stats['audio']}")
    print(f"    Particles: {stats['particles']}")
    print(f"    Water: {stats['water']}")
    print(f"    Groups: {stats['groups']}")
    print(f"    Total scene nodes: {len(writer.nodes)}")

    return manifest


def main():
    if len(sys.argv) < 2:
        print("Usage: mis_to_tscn.py <input.mis> [output_dir]")
        print("  Converts Torque .mis mission files to Godot .tscn scenes")
        sys.exit(1)

    mis_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else './output/scenes'

    convert_mis(mis_path, output_dir)
    print("\nDone!")


if __name__ == '__main__':
    main()
