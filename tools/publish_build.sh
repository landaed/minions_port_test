#!/bin/bash
# Publish a launcher build manifest.
#
#   tools/publish_build.sh <build.zip> <version> [download_url] [exe_name]
#
# Computes the zip's SHA-256 and writes dist/version.json. The launcher
# (launcher/) fetches that JSON, and if its "version" differs from what the
# player has installed it downloads "url", verifies "sha256", extracts it, and
# launches "exe". Host dist/version.json + the zip wherever the launcher's
# MANIFEST_URL points (raw GitHub, a GitHub Release asset, Google Drive direct
# link, your VPS, ...).
set -eu

ZIP="${1:?usage: publish_build.sh <build.zip> <version> [url] [exe]}"
VERSION="${2:?need a version, e.g. 2026.06.18}"
URL="${3:-https://github.com/landaed/minions_port_test/releases/download/v${VERSION}/$(basename "$ZIP")}"
EXE="${4:-Minions_port.exe}"

[ -f "$ZIP" ] || { echo "no such file: $ZIP"; exit 1; }

SHA=$(sha256sum "$ZIP" | awk '{print $1}')
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$SCRIPT_DIR/dist/version.json"
mkdir -p "$SCRIPT_DIR/dist"

cat > "$OUT" <<JSON
{
  "version": "$VERSION",
  "url": "$URL",
  "sha256": "$SHA",
  "exe": "$EXE",
  "notes": "Build $VERSION"
}
JSON

echo "Wrote $OUT"
echo "  version: $VERSION"
echo "  sha256 : $SHA"
echo "  url    : $URL"
echo ""
echo "Next: upload '$ZIP' to that url, and publish dist/version.json where the"
echo "launcher's MANIFEST_URL can GET it (commit it, or host it on your VPS)."
