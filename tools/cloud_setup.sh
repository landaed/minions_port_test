#!/usr/bin/env bash
# Reproducible cloud toolchain for the Minions of Mirth -> Godot asset pipeline.
#
# Brings up, on a fresh Ubuntu 24.04 container (run as root):
#   * Godot 4.6 editor binary with software-Vulkan (lavapipe) rendering under Xvfb
#   * Blender 5.0 as the `bpy` Python module (headless mesh work, no GUI)
#   * Pillow + numpy for texture / heightmap processing
#
# Safe to re-run (idempotent-ish). After this, use tools/render.sh to screenshot scenes.
set -euo pipefail

GODOT_VER="4.6-stable"
GODOT_DIR="/opt/godot46"
GODOT_BIN="$GODOT_DIR/Godot_v${GODOT_VER}_linux.x86_64"

echo "== apt: software Vulkan (lavapipe) + Godot X/GL runtime libs + Xvfb =="
export DEBIAN_FRONTEND=noninteractive
apt-get update -o Acquire::Retries=3
apt-get install -y --no-install-recommends \
  xvfb mesa-vulkan-drivers vulkan-tools libvulkan1 \
  libgl1 libglu1-mesa libopengl0 \
  libx11-6 libxcursor1 libxinerama1 libxrandr2 libxi6 libxext6 libxrender1 libxfixes3 \
  fontconfig libfontconfig1 unzip curl

echo "== Godot $GODOT_VER =="
if [ ! -x "$GODOT_BIN" ]; then
  mkdir -p "$GODOT_DIR"; cd "$GODOT_DIR"
  curl -sS -L -o godot.zip \
    "https://github.com/godotengine/godot/releases/download/${GODOT_VER}/Godot_v${GODOT_VER}_linux.x86_64.zip"
  unzip -o godot.zip >/dev/null
  chmod +x "Godot_v${GODOT_VER}_linux.x86_64"
fi
ln -sf "$GODOT_BIN" /usr/local/bin/godot

echo "== Python: bpy (Blender) + Pillow + numpy =="
pip install --quiet bpy Pillow numpy

echo "== versions =="
godot --headless --version || true
python3 -c "import bpy,PIL,numpy; print('bpy',bpy.app.version_string,'| Pillow',PIL.__version__,'| numpy',numpy.__version__)"

cat <<'EOF'

Toolchain ready. To render a Godot scene/asset to a PNG headlessly:
  tools/render.sh path/to/asset.glb  /tmp/out.png  35
Render env (used internally by render.sh):
  VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/lvp_icd.json
  xvfb-run -a -s "-screen 0 1280x720x24" godot --path <project> --rendering-driver vulkan
EOF
