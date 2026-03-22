#!/usr/bin/env python3
"""
Master conversion script for the Trinst (City of Trinst) zone.

Runs all three converters:
1. TER -> heightmap PNG (terrain)
2. MIS -> TSCN (Godot scene with object placement)
3. DTS -> GLB (all referenced 3D models)

Usage: python3 convert_trinst.py [output_dir]
"""

import os
import sys
import json
import time

# Add tools dir to path
TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS_DIR)

# Base data directory
BASE_DIR = os.path.join(os.path.dirname(TOOLS_DIR), 'MoMReborn', 'minions.of.mirth', 'data')
MISSIONS_DIR = os.path.join(BASE_DIR, 'missions')

# Trinst uses city.mis
TRINST_MIS = os.path.join(MISSIONS_DIR, 'city.mis')
TRINST_TER = os.path.join(MISSIONS_DIR, 'city.ter')


def convert_terrain(output_dir):
    """Convert city.ter to heightmap."""
    from ter_to_heightmap import convert_ter
    print("=" * 60)
    print("STEP 1: Converting terrain heightmap")
    print("=" * 60)
    terrain_dir = os.path.join(output_dir, 'terrain')
    meta = convert_ter(TRINST_TER, terrain_dir, TRINST_MIS)
    print()
    return meta


def convert_scene(output_dir):
    """Convert city.mis to Godot scene."""
    from mis_to_tscn import convert_mis
    print("=" * 60)
    print("STEP 2: Converting mission file to Godot scene")
    print("=" * 60)
    scene_dir = os.path.join(output_dir, 'scenes')
    manifest = convert_mis(TRINST_MIS, scene_dir)
    print()
    return manifest


def convert_models(output_dir, manifest):
    """Convert all DTS models referenced by the mission."""
    from dts_to_gltf import convert_dts
    print("=" * 60)
    print("STEP 3: Converting DTS models to GLB")
    print("=" * 60)

    models_dir = os.path.join(output_dir, 'converted_assets')

    # Collect all unique DTS files from the manifest
    dts_files = set()
    for shape_ref in manifest.get('unique_dts_shapes', []):
        if shape_ref and shape_ref.endswith('.dts'):
            dts_files.add(shape_ref)

    print(f"  Found {len(dts_files)} unique DTS models to convert")

    success = 0
    failed = 0
    skipped = 0

    for shape_ref in sorted(dts_files):
        # Convert ~/data/shapes/foo/bar.dts -> full path
        rel_path = shape_ref.replace('~/', '')
        if rel_path.startswith('data/'):
            rel_path = rel_path[5:]

        full_path = os.path.join(BASE_DIR, rel_path)
        out_path = os.path.join(models_dir, os.path.splitext(rel_path)[0] + '.glb')

        if not os.path.exists(full_path):
            print(f"  MISSING: {rel_path}")
            skipped += 1
            continue

        result = convert_dts(full_path, out_path)
        if result:
            success += 1
            print(f"  OK: {rel_path}")
        else:
            failed += 1

    print(f"\n  Models: {success} converted, {skipped} missing, {failed} failed")
    print()
    return success, skipped, failed


def convert_all_models(output_dir):
    """Convert ALL DTS models in the data directory (not just trinst-referenced ones)."""
    from dts_to_gltf import batch_convert
    print("=" * 60)
    print("STEP 3b: Converting ALL DTS models to GLB")
    print("=" * 60)
    shapes_dir = os.path.join(BASE_DIR, 'shapes')
    models_dir = os.path.join(output_dir, 'converted_assets', 'shapes')
    return batch_convert(shapes_dir, models_dir)


def main():
    output_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(TOOLS_DIR), 'output', 'trinst')
    all_models = '--all-models' in sys.argv

    print(f"Converting Trinst zone to Godot assets")
    print(f"Output directory: {output_dir}")
    print(f"Mission file: {TRINST_MIS}")
    print(f"Terrain file: {TRINST_TER}")
    print()

    os.makedirs(output_dir, exist_ok=True)
    start = time.time()

    # Step 1: Terrain
    terrain_meta = convert_terrain(output_dir)

    # Step 2: Scene
    manifest = convert_scene(output_dir)

    # Step 3: Models
    if all_models:
        convert_all_models(output_dir)
    else:
        convert_models(output_dir, manifest)

    elapsed = time.time() - start

    # Summary
    print("=" * 60)
    print(f"CONVERSION COMPLETE ({elapsed:.1f}s)")
    print("=" * 60)
    print(f"Output: {output_dir}")
    print(f"  terrain/     - Heightmap PNG + raw float32 + metadata")
    print(f"  scenes/      - Godot .tscn scene file + asset manifest")
    print(f"  converted_assets/ - GLB models converted from DTS")
    print()
    print("Next steps:")
    print("  1. Create a Godot 4 project")
    print("  2. Copy the output/ directory into your Godot project")
    print("  3. Install Terrain3D plugin for terrain import")
    print("  4. Open the .tscn scene file")
    print("  5. DIF interiors need separate conversion (not yet automated)")
    print("  6. Set up materials/textures in Godot's material editor")


if __name__ == '__main__':
    main()
