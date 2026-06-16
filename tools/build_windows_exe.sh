#!/usr/bin/env bash
# Build ONE self-contained Windows .exe of the Godot client, from Linux.
#
# Why this exists: the trinst prop/building PBR textures (albedo .jpg plus the
# baked *_normal/_rough/_ao .png maps from tools/enhance_materials.gd) live only
# on disk on the Linux box -- they are derived from the .glb meshes and are not
# all committed to git. A fresh clone (e.g. the Windows machine opening the
# project in the editor) is therefore missing them, which is why prefabs_tower1
# is invisible and the trinst scene reports missing materials there.
#
# Exporting fixes this without syncing editors: Godot bundles the *imported*
# resources from THIS machine's disk into the PCK, and `embed_pck=true` puts the
# PCK inside the executable. So the single .exe built here already contains every
# texture, and "just works" when copied to Windows.
#
# Prerequisites:
#   * Godot 4.6 on PATH (or set GODOT=/path/to/godot) -- same version as your editor.
#   * Windows export templates for 4.6 installed. Get them from the editor
#     (Editor > Manage Export Templates > Download and Install), or download
#     Godot_v4.6-stable_export_templates.tpz and unzip its contents into:
#         ~/.local/share/godot/export_templates/4.6.stable/
#
# Usage:
#   tools/build_windows_exe.sh [output.exe]
#   GODOT=/opt/godot46/Godot_v4.6-stable_linux.x86_64 tools/build_windows_exe.sh
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PROJECT="$HERE/../minions-port"
GODOT="${GODOT:-godot}"
OUT="${1:-$HERE/../build/windows/MinionsOfMirth.exe}"
PRESET="Windows Desktop"

if ! command -v "$GODOT" >/dev/null 2>&1 && [ ! -x "$GODOT" ]; then
  echo "ERROR: Godot not found. Put 'godot' on PATH or set GODOT=/path/to/godot" >&2
  exit 1
fi

# Friendly heads-up if the export templates aren't installed yet.
TPL_DIR="$HOME/.local/share/godot/export_templates/4.6.stable"
if [ ! -d "$TPL_DIR" ]; then
  echo "WARNING: $TPL_DIR not found." >&2
  echo "         Install the 4.6 export templates (editor: Manage Export Templates," >&2
  echo "         or unzip the .tpz into that folder) or the export below will fail." >&2
fi

mkdir -p "$(dirname "$OUT")"

# Make sure imports are current so the PCK includes every texture/mesh.
echo "[build] importing assets (first run can take a while)..."
"$GODOT" --headless --path "$PROJECT" --import >/dev/null 2>&1 || true

echo "[build] exporting single Windows .exe (embedded PCK) -> $OUT"
"$GODOT" --headless --path "$PROJECT" --export-release "$PRESET" "$OUT"

echo "[build] done."
ls -lh "$OUT" 2>/dev/null || true
echo "[build] Copy that ONE file to the Windows machine and run it. The client"
echo "[build] still needs the server host:port (use the address field at login)."
