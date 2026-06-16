#!/bin/bash
# ---------------------------------------------------------------------------
# Build a SINGLE self-contained Windows .exe of the Godot client, FROM LINUX.
#
# Why: the export bundles whatever assets are in your project at build time, so
# building on the machine that has the full project (including locally-generated
# textures/normal maps that are .gitignored) produces a complete build with no
# editor / import needed on the Windows side. Send the one .exe and run it.
#
# Usage:
#   ./build_windows.sh                      # -> build/MinionsOfMirth.exe
#   ./build_windows.sh /path/to/Game.exe
#   GODOT=/path/to/godot ./build_windows.sh
# ---------------------------------------------------------------------------
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 1. Locate the Godot 4.6 editor binary.
if [ -z "${GODOT:-}" ]; then
    for c in tools/godot_bin/Godot_v4.6-stable_linux.x86_64 \
             "$(command -v godot4 2>/dev/null || true)" \
             "$(command -v godot 2>/dev/null || true)"; do
        if [ -n "$c" ] && [ -x "$c" ]; then GODOT="$c"; break; fi
    done
fi
if [ -z "${GODOT:-}" ] || [ ! -x "$GODOT" ]; then
    echo "ERROR: Godot 4.6 binary not found. Set GODOT=/path/to/godot and retry."
    exit 1
fi
echo "Using Godot: $GODOT"

# 2. Make sure the Windows export template for 4.6 is installed.
TPL="$HOME/.local/share/godot/export_templates/4.6.stable/windows_release_x86_64.exe"
if [ ! -f "$TPL" ]; then
    echo "ERROR: Windows export template not found at:"
    echo "    $TPL"
    echo
    echo "Install it once, either way:"
    echo "  A) In Godot: Editor -> Manage Export Templates -> Download and Install."
    echo "  B) Download Godot_v4.6-stable_export_templates.tpz from the Godot 4.6"
    echo "     release page and unzip its templates/* into:"
    echo "       $HOME/.local/share/godot/export_templates/4.6.stable/"
    exit 1
fi

# 3. Resolve an absolute output path.
OUT="${1:-build/MinionsOfMirth.exe}"
OUT_DIR="$(cd "$(dirname "$OUT")" 2>/dev/null && pwd || (mkdir -p "$(dirname "$OUT")" && cd "$(dirname "$OUT")" && pwd))"
OUT_ABS="$OUT_DIR/$(basename "$OUT")"

# 4. Refresh the import cache, then export the single embedded-PCK exe.
#    (Run the Godot editor on this project at least once first if the import
#     cache doesn't exist yet; on a headless box prefix both lines with
#     'xvfb-run -a'.)
echo "Importing project (fast if you've opened it in the editor before)..."
"$GODOT" --headless --path minions-port --import >/dev/null 2>&1 || true

echo "Exporting Windows build -> $OUT_ABS"
"$GODOT" --headless --path minions-port --export-release "Windows Desktop" "$OUT_ABS"

echo
echo "Done: $OUT_ABS"
ls -la "$OUT_ABS"
echo "Copy that single .exe to your Windows PC and double-click it."
echo "(It only needs the servers running somewhere reachable; set the Server"
echo " field on the login screen to that host.)"
