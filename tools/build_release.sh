#!/usr/bin/env bash
# Build a full auto-updating Windows release in one shot:
#   * the launcher .exe (players run this once; it self-updates thereafter)
#   * a zip of the self-contained game .exe (the launcher downloads + runs this)
#   * a refreshed dist/version.json manifest (the launcher reads this to detect
#     updates)
#
# How auto-update works: the launcher (launcher/launcher.gd) GETs
#   https://raw.githubusercontent.com/landaed/minions_port_test/main/dist/version.json
# and, if its "version" differs from what the player has installed, downloads the
# manifest "url" (the zip), verifies its sha256, extracts it next to the launcher,
# and runs "exe". So shipping an update = build, upload the zip to a GitHub
# Release, and commit the new dist/version.json.
#
# Usage:
#   GODOT=/path/to/Godot_v4.6-stable_linux.x86_64 tools/build_release.sh <version>
#   e.g.  tools/build_release.sh 2026.06.19
#
# Prerequisites: Godot 4.6 on PATH (or $GODOT) + the Windows export templates for
# 4.6 (Editor > Manage Export Templates, or unzip the .tpz into
# ~/.local/share/godot/export_templates/4.6.stable/). Needs `zip`.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
GODOT="${GODOT:-godot}"
VERSION="${1:?usage: build_release.sh <version>   e.g. 2026.06.19}"

OUT="$ROOT/build/windows"
GAME_DIR="$OUT/game"
LAUNCHER_DIR="$OUT/launcher"
GAME_EXE_NAME="Minions_port.exe"          # must match dist/version.json "exe"
GAME_EXE="$GAME_DIR/$GAME_EXE_NAME"
LAUNCHER_EXE="$LAUNCHER_DIR/MinionsLauncher.exe"
ZIP="$OUT/MinionsOfMirth-windows.zip"

command -v zip >/dev/null 2>&1 || { echo "ERROR: 'zip' is required." >&2; exit 1; }
mkdir -p "$GAME_DIR" "$LAUNCHER_DIR"

# 1) Game: the existing self-contained build (embedded PCK), named to match the
#    manifest's "exe" so the launcher can run it after extracting the zip.
echo "[release] building game client -> $GAME_EXE"
GODOT="$GODOT" "$HERE/build_windows_exe.sh" "$GAME_EXE"

# 2) Launcher: a tiny self-contained exe from the launcher/ project.
echo "[release] exporting launcher -> $LAUNCHER_EXE"
"$GODOT" --headless --path "$ROOT/launcher" --import >/dev/null 2>&1 || true
"$GODOT" --headless --path "$ROOT/launcher" --export-release "Windows Desktop" "$LAUNCHER_EXE"

# 3) Zip just the game exe (the launcher extracts this next to itself and runs it).
echo "[release] packaging $ZIP"
( cd "$GAME_DIR" && rm -f "$ZIP" && zip -j "$ZIP" "$GAME_EXE_NAME" >/dev/null )

# 4) Refresh dist/version.json (version + sha256 + GitHub Release url + exe).
"$HERE/publish_build.sh" "$ZIP" "$VERSION" "" "$GAME_EXE_NAME"

echo ""
echo "[release] done:"
echo "  launcher : $LAUNCHER_EXE        <- give players this ONE file"
echo "  game zip : $ZIP                  <- upload to the v$VERSION GitHub Release"
echo "  manifest : $ROOT/dist/version.json (updated)"
echo ""
echo "Publish the update:"
echo "  1) Create the release with the zip attached, e.g.:"
echo "       gh release create v$VERSION '$ZIP' --title 'Minions of Mirth v$VERSION'"
echo "     (the manifest url already points at that release asset)"
echo "  2) Commit the manifest so the launcher sees the new version:"
echo "       git add dist/version.json && git commit -m 'Release v$VERSION' && git push origin main"
echo ""
echo "Players just run MinionsLauncher.exe — it downloads/updates the client automatically."
