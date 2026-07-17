#!/usr/bin/env bash
# Export launchers and game update archives for Windows, Ubuntu/Linux, and macOS.
# Usage: GODOT=/path/to/godot tools/build_release.sh 1.2.3
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GODOT="${GODOT:-godot}"
VERSION="${1:?usage: tools/build_release.sh <version>}"
command -v "$GODOT" >/dev/null 2>&1 || { echo "Godot not found: $GODOT" >&2; exit 1; }
command -v zip >/dev/null 2>&1 || { echo "zip is required" >&2; exit 1; }
mkdir -p "$ROOT/build/windows/game" "$ROOT/build/windows/launcher" "$ROOT/build/linux/game" "$ROOT/build/linux/launcher" "$ROOT/build/macos/game" "$ROOT/build/macos/launcher"

echo "Importing projects…"
"$GODOT" --headless --path "$ROOT/minions-port" --import
"$GODOT" --headless --path "$ROOT/launcher" --import

echo "Exporting game clients…"
"$GODOT" --headless --path "$ROOT/minions-port" --export-release "Windows Desktop" "$ROOT/build/windows/game/MinionsOfMirth.exe"
"$GODOT" --headless --path "$ROOT/minions-port" --export-release "Linux" "$ROOT/build/linux/game/MinionsOfMirth.x86_64"
"$GODOT" --headless --path "$ROOT/minions-port" --export-release "macOS" "$ROOT/build/macos/game/MinionsOfMirth.zip"
chmod +x "$ROOT/build/linux/game/MinionsOfMirth.x86_64"

echo "Packaging game updates…"
(cd "$ROOT/build/windows/game" && zip -q -j -FS ../MinionsOfMirth-windows.zip MinionsOfMirth.exe)
(cd "$ROOT/build/linux/game" && zip -q -j -FS ../MinionsOfMirth-linux.zip MinionsOfMirth.x86_64)
cp "$ROOT/build/macos/game/MinionsOfMirth.zip" "$ROOT/build/macos/MinionsOfMirth-macos.zip"
"$ROOT/tools/publish_build.sh" windows "$ROOT/build/windows/MinionsOfMirth-windows.zip" "$VERSION" "MinionsOfMirth.exe"
"$ROOT/tools/publish_build.sh" linux "$ROOT/build/linux/MinionsOfMirth-linux.zip" "$VERSION" "MinionsOfMirth.x86_64"
"$ROOT/tools/publish_build.sh" macos "$ROOT/build/macos/MinionsOfMirth-macos.zip" "$VERSION" "Minions_port.app/Contents/MacOS/Minions_port"

echo "Exporting player launchers…"
"$GODOT" --headless --path "$ROOT/launcher" --export-release "Windows Desktop" "$ROOT/build/windows/launcher/MinionsLauncher.exe"
"$GODOT" --headless --path "$ROOT/launcher" --export-release "Linux" "$ROOT/build/linux/launcher/MinionsLauncher.x86_64"
"$GODOT" --headless --path "$ROOT/launcher" --export-release "macOS" "$ROOT/build/macos/launcher/MinionsLauncher.zip"
chmod +x "$ROOT/build/linux/launcher/MinionsLauncher.x86_64"

echo
printf 'Release v%s assets:\n' "$VERSION"
printf '  %s\n' build/windows/MinionsOfMirth-windows.zip build/linux/MinionsOfMirth-linux.zip build/macos/MinionsOfMirth-macos.zip
printf 'Player launchers:\n  %s\n' build/windows/launcher/MinionsLauncher.exe build/linux/launcher/MinionsLauncher.x86_64 build/macos/launcher/MinionsLauncher.zip
printf 'Upload the three game archives to GitHub Release v%s, then commit dist/version-*.json.\n' "$VERSION"
