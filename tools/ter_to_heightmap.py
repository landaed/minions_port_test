#!/usr/bin/env python3
"""
Torque TGE .ter terrain file to PNG heightmap converter.

TGE terrain format (version 4):
  - 1 byte: version (4)
  - 256*256 uint16 LE: heightmap grid values
  - Remaining bytes: material/texture map data (8 bytes per grid cell)

The terrain grid is 256x256 with squareSize controlling world-space scale.
Height values are raw uint16 scaled by the engine (typically height = value * scale).

Output: 16-bit grayscale PNG suitable for Godot Terrain3D or Godot's built-in heightmap.
Also outputs a metadata JSON with terrain parameters from the .mis file.
"""

import struct
import sys
import os
import json
import re

def read_ter_file(ter_path):
    """Read a Torque .ter terrain file and return the 256x256 heightmap grid."""
    with open(ter_path, 'rb') as f:
        data = f.read()

    version = data[0]
    if version != 4:
        print(f"Warning: TER version is {version}, expected 4. Attempting to parse anyway.")

    grid_size = 256
    num_cells = grid_size * grid_size
    expected_height_bytes = num_cells * 2

    if len(data) < 1 + expected_height_bytes:
        raise ValueError(f"TER file too small: {len(data)} bytes, need at least {1 + expected_height_bytes}")

    # Read uint16 LE heightmap starting at offset 1
    heights = struct.unpack_from(f'<{num_cells}H', data, 1)

    # Reshape into 2D grid (row-major, Y then X)
    grid = []
    for y in range(grid_size):
        row = heights[y * grid_size:(y + 1) * grid_size]
        grid.append(list(row))

    # Parse material data from remaining bytes
    material_offset = 1 + expected_height_bytes
    remaining = data[material_offset:]
    material_grid = None
    if len(remaining) >= num_cells:
        # First byte per cell is typically the material/texture index
        material_grid = []
        for y in range(grid_size):
            row = []
            for x in range(grid_size):
                idx = (y * grid_size + x) * (len(remaining) // num_cells)
                if idx < len(remaining):
                    row.append(remaining[idx])
                else:
                    row.append(0)
            material_grid.append(row)

    return {
        'version': version,
        'grid_size': grid_size,
        'heights': grid,
        'height_min': min(heights),
        'height_max': max(heights),
        'material_grid': material_grid,
        'total_bytes': len(data),
        'material_bytes': len(remaining),
    }


def parse_terrain_from_mis(mis_path):
    """Extract TerrainBlock parameters from a .mis file."""
    params = {}
    if not os.path.exists(mis_path):
        return params

    with open(mis_path, 'r', errors='replace') as f:
        content = f.read()

    # Find TerrainBlock section
    match = re.search(r'new TerrainBlock\([^)]*\)\s*\{([^}]+)\}', content, re.DOTALL)
    if match:
        block = match.group(1)
        for line in block.split('\n'):
            line = line.strip().rstrip(';')
            if '=' in line:
                key, _, val = line.partition('=')
                key = key.strip()
                val = val.strip().strip('"')
                params[key] = val

    return params


def save_heightmap_png(grid, output_path, bit_depth=16):
    """Save heightmap grid as a 16-bit grayscale PNG."""
    from PIL import Image

    grid_size = len(grid)
    arr = []
    for row in grid:
        arr.extend(row)

    # Normalize to full range for maximum precision
    min_h = min(arr)
    max_h = max(arr)
    h_range = max_h - min_h if max_h != min_h else 1

    if bit_depth == 16:
        # Scale to 0-65535 range, save as 16-bit grayscale
        normalized = []
        for h in arr:
            normalized.append(int((h - min_h) / h_range * 65535))
        img = Image.new('I;16', (grid_size, grid_size))
        img.putdata(normalized)
    else:
        # 8-bit fallback
        normalized = []
        for h in arr:
            normalized.append(int((h - min_h) / h_range * 255))
        img = Image.new('L', (grid_size, grid_size))
        img.putdata(normalized)

    img.save(output_path)
    return min_h, max_h


def convert_ter(ter_path, output_dir, mis_path=None):
    """Convert a .ter file to PNG heightmap + metadata JSON."""
    os.makedirs(output_dir, exist_ok=True)

    base_name = os.path.splitext(os.path.basename(ter_path))[0]

    print(f"Reading terrain file: {ter_path}")
    terrain = read_ter_file(ter_path)

    print(f"  Version: {terrain['version']}")
    print(f"  Grid size: {terrain['grid_size']}x{terrain['grid_size']}")
    print(f"  Height range: {terrain['height_min']} - {terrain['height_max']}")
    print(f"  File size: {terrain['total_bytes']} bytes")

    # Get MIS parameters
    mis_params = {}
    if mis_path:
        mis_params = parse_terrain_from_mis(mis_path)
        print(f"  Terrain params from MIS: {mis_params}")

    # Save heightmap PNG
    png_path = os.path.join(output_dir, f"{base_name}_heightmap.png")
    min_h, max_h = save_heightmap_png(terrain['heights'], png_path, bit_depth=16)
    print(f"  Saved heightmap: {png_path}")

    # Also save an 8-bit version for easy preview
    preview_path = os.path.join(output_dir, f"{base_name}_heightmap_preview.png")
    save_heightmap_png(terrain['heights'], preview_path, bit_depth=8)
    print(f"  Saved preview: {preview_path}")

    # Save raw float32 heightmap (for Terrain3D)
    raw_path = os.path.join(output_dir, f"{base_name}_heightmap.raw")
    square_size = float(mis_params.get('squareSize', '8'))
    position = mis_params.get('position', '-1024 -1024 0').split()
    pos_x, pos_y, pos_z = float(position[0]), float(position[1]), float(position[2])

    with open(raw_path, 'wb') as f:
        for row in terrain['heights']:
            for h in row:
                # Convert from engine units: raw height value represents Z coordinate
                # Torque TGE uses: worldZ = rawHeight * (1.0 / fixedPointScale)
                # The fixedPointScale for TGE is typically 1.0 (heights are already in world units)
                # But the values seem to be in a fixed-point format where actual height ≈ value / 64
                world_height = h / 64.0
                f.write(struct.pack('<f', world_height))
    print(f"  Saved raw float32: {raw_path}")

    # Save metadata
    metadata = {
        'source_file': os.path.basename(ter_path),
        'version': terrain['version'],
        'grid_size': terrain['grid_size'],
        'height_min_raw': terrain['height_min'],
        'height_max_raw': terrain['height_max'],
        'height_min_world': terrain['height_min'] / 64.0,
        'height_max_world': terrain['height_max'] / 64.0,
        'square_size': square_size,
        'terrain_world_size': terrain['grid_size'] * square_size,
        'position': {'x': pos_x, 'y': pos_y, 'z': pos_z},
        'mis_params': mis_params,
        'output_files': {
            'heightmap_16bit': f"{base_name}_heightmap.png",
            'heightmap_preview': f"{base_name}_heightmap_preview.png",
            'heightmap_raw_f32': f"{base_name}_heightmap.raw",
        },
        'godot_import_notes': {
            'terrain_plugin': 'Use Terrain3D plugin (https://github.com/TokisanGames/Terrain3D)',
            'heightmap_format': '16-bit grayscale PNG, normalized to 0-65535',
            'raw_format': 'float32 little-endian, 256x256 grid, values in world units',
            'world_scale': f'{terrain["grid_size"]} cells x {square_size} units/cell = {terrain["grid_size"] * square_size} world units',
            'coordinate_system': 'Torque Y-forward Z-up; Godot uses Y-up, so swap Y<->Z',
        }
    }

    meta_path = os.path.join(output_dir, f"{base_name}_terrain_meta.json")
    with open(meta_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    print(f"  Saved metadata: {meta_path}")

    return metadata


def main():
    if len(sys.argv) < 2:
        print("Usage: ter_to_heightmap.py <input.ter> [output_dir] [input.mis]")
        print("  Converts Torque TGE .ter terrain files to PNG heightmaps")
        print()
        print("Examples:")
        print("  ter_to_heightmap.py city.ter ./output/terrain")
        print("  ter_to_heightmap.py city.ter ./output/terrain city.mis")
        sys.exit(1)

    ter_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else './output/terrain'
    mis_path = sys.argv[3] if len(sys.argv) > 3 else None

    convert_ter(ter_path, output_dir, mis_path)
    print("\nDone!")


if __name__ == '__main__':
    main()
