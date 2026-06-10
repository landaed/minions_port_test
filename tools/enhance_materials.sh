#!/bin/bash
# One-command offline material enhancement for the Godot port.
# Generates normal/roughness/AO maps from prop albedo textures, imports them,
# then applies shared enhanced materials to every editable trinst prop scene.
#
# Usage:  tools/enhance_materials.sh [--force]
# Requires the godot binary (4.6) on PATH.

set -e
cd "$(dirname "$0")/../minions-port"

GODOT="${GODOT:-godot}"
FORCE="${1:-}"

echo "[enhance_materials] phase 1/3: generating maps..."
"$GODOT" --headless --script res://tools/enhance_materials.gd -- --phase=generate $FORCE

echo "[enhance_materials] phase 2/3: importing textures..."
"$GODOT" --headless --import . >/dev/null 2>&1 || true

echo "[enhance_materials] phase 3/3: applying materials to editable scenes..."
"$GODOT" --headless --script res://tools/enhance_materials.gd -- --phase=apply $FORCE

echo "[enhance_materials] done. Toggle features any time with:"
echo "  godot --headless --script res://tools/toggle_material_features.gd -- --normal=off   (etc.)"
