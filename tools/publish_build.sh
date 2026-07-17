#!/usr/bin/env bash
# Write one platform update manifest.
# Usage: tools/publish_build.sh <windows|linux|macos> <game.zip> <version> <executable>
set -euo pipefail
PLATFORM="${1:?platform required}"
ZIP="${2:?game zip required}"
VERSION="${3:?version required}"
EXE="${4:?executable path required}"
case "$PLATFORM" in windows|linux|macos) ;; *) echo "Unknown platform: $PLATFORM" >&2; exit 1;; esac
[[ -f "$ZIP" ]] || { echo "No such file: $ZIP" >&2; exit 1; }
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ASSET="MinionsOfMirth-${PLATFORM}.zip"
URL="https://github.com/landaed/minions_port_test/releases/download/v${VERSION}/${ASSET}"
if command -v sha256sum >/dev/null; then SHA="$(sha256sum "$ZIP" | awk '{print $1}')"; else SHA="$(shasum -a 256 "$ZIP" | awk '{print $1}')"; fi
OUT="$ROOT/dist/version-${PLATFORM}.json"
printf '{\n  "version": "%s",\n  "url": "%s",\n  "sha256": "%s",\n  "exe": "%s",\n  "notes": "Build %s"\n}\n' "$VERSION" "$URL" "$SHA" "$EXE" "$VERSION" > "$OUT"
echo "Wrote $OUT ($SHA)"
