#!/usr/bin/env bash
# Build ONE self-contained Linux executable of the Godot client, from Linux.
#
# Mirrors tools/build_windows_exe.sh: imports assets so the PCK contains every
# generated texture/mesh, then exports a single self-contained binary with the
# PCK embedded (embed_pck=true), so it "just works" when copied to another Linux
# box. The client still needs the server host:port (entered at login).
#
# Prerequisites:
#   * Godot 4.6 on PATH (or set GODOT=/path/to/godot) -- same version as your editor.
#   * Linux export templates for 4.6 installed (Editor > Manage Export Templates >
#     Download and Install, or unzip the .tpz into
#     ~/.local/share/godot/export_templates/4.6.stable/).
#
# Usage:
#   tools/build_linux.sh [output.x86_64]
#   GODOT=/opt/godot46/Godot_v4.6-stable_linux.x86_64 tools/build_linux.sh
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PROJECT="$HERE/../minions-port"
GODOT="${GODOT:-godot}"
OUT="${1:-$HERE/../build/linux/MinionsOfMirth.x86_64}"
PRESET="Linux"

if ! command -v "$GODOT" >/dev/null 2>&1 && [ ! -x "$GODOT" ]; then
  echo "ERROR: Godot not found. Put 'godot' on PATH or set GODOT=/path/to/godot" >&2
  exit 1
fi

TPL_DIR="$HOME/.local/share/godot/export_templates/4.6.stable"
if [ ! -d "$TPL_DIR" ]; then
  echo "WARNING: $TPL_DIR not found." >&2
  echo "         Install the 4.6 export templates (editor: Manage Export Templates," >&2
  echo "         or unzip the .tpz into that folder) or the export below will fail." >&2
fi

mkdir -p "$(dirname "$OUT")"

# Force a filesystem re-scan so newly un-ignored folders are imported into the PCK.
rm -rf "$PROJECT/.godot/editor" 2>/dev/null || true

# Two import passes: discover/import newly-visible assets, then settle dependents.
echo "[build] importing assets (first run can take a while)..."
"$GODOT" --headless --path "$PROJECT" --import >/dev/null 2>&1 || true
"$GODOT" --headless --path "$PROJECT" --import >/dev/null 2>&1 || true

echo "[build] exporting single Linux binary (embedded PCK) -> $OUT"
"$GODOT" --headless --path "$PROJECT" --export-release "$PRESET" "$OUT"

chmod +x "$OUT" 2>/dev/null || true
echo "[build] done."
ls -lh "$OUT" 2>/dev/null || true
echo "[build] Run it directly: '$OUT'  (enter the server host:port at login)."
