#!/usr/bin/env bash
# Render a single asset (.glb/.gltf/.tscn) or nothing (grid+ref only) to a PNG,
# headlessly via the asset_viewer Godot project (software Vulkan under Xvfb).
#
# Usage: tools/render.sh [asset_path] [out_png] [orbit_deg]
#   asset_path : .glb/.gltf/.tscn to inspect (optional; omit for empty stage)
#   out_png    : output screenshot path (default /tmp/view.png)
#   orbit_deg  : camera yaw around the asset (default 35)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"

export VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/lvp_icd.json
export VIEW_PATH="${1:-}"
export OUT_PATH="${2:-/tmp/view.png}"
export ORBIT_DEG="${3:-35}"

xvfb-run -a -s "-screen 0 1280x720x24" \
  godot --path "$HERE/asset_viewer" --rendering-driver vulkan --resolution 1280x720 \
  >/tmp/godot_render.log 2>&1 || true

# Surface the useful lines from the run (AABB size, screenshot status)
grep -E "ASSET_AABB|SCREENSHOT_SAVE_ERR" /tmp/godot_render.log || true
echo "saved: $OUT_PATH  (full log: /tmp/godot_render.log)"
