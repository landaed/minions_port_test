#!/usr/bin/env python3
"""Extract AudioEmitter placements from a Torque .mis mission file into a
Godot-friendly audio.json for the port's zone ambience (positions converted
from Torque Z-up to Godot Y-up, with the original attenuation distances that
the scene.json pipeline drops).

Usage:
    python3 tools/extract_audio_emitters.py city trinst
    (mission name without .mis, then target zone asset dir under
     minions-port/assets/)
"""
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MISSIONS = os.path.join(REPO, "MoMReborn", "minions.of.mirth", "data", "missions")
ASSETS = os.path.join(REPO, "minions-port", "assets")

BLOCK_RE = re.compile(r"new AudioEmitter\([^)]*\)\s*\{(.*?)\n\s*\};", re.S)
FIELD_RE = re.compile(r"(\w+)\s*=\s*\"([^\"]*)\";")


def torque_to_godot(x, y, z):
    return [x, z, -y]


def extract(mission, zone):
    mis_path = os.path.join(MISSIONS, mission + ".mis")
    with open(mis_path, "r", errors="replace") as f:
        text = f.read()

    emitters = []
    for m in BLOCK_RE.finditer(text):
        fields = dict(FIELD_RE.findall(m.group(1)))
        fname = fields.get("fileName", "")
        if not fname:
            continue
        # "~/data/sound/environment/Fire_FireplaceLoop1.ogg" -> "environment/Fire_FireplaceLoop1.ogg"
        rel = fname.split("data/sound/")[-1].replace("\\", "/")
        pos = [float(v) for v in fields.get("position", "0 0 0").split()]
        emitters.append({
            "pos": torque_to_godot(*pos[:3]),
            "file": rel,
            "volume": float(fields.get("volume", "1")),
            "reference_distance": float(fields.get("referenceDistance", "5")),
            "max_distance": float(fields.get("maxDistance", "30")),
            "looping": True,  # all MoM zone emitters are ambient loops
            "outside": fields.get("outsideAmbient", "0") == "1",
        })

    out_dir = os.path.join(ASSETS, zone)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "audio.json")
    with open(out_path, "w") as f:
        json.dump({"mission": mission, "emitters": emitters}, f, indent=1)
    print("Wrote %d emitters -> %s" % (len(emitters), out_path))


if __name__ == "__main__":
    mission = sys.argv[1] if len(sys.argv) > 1 else "city"
    zone = sys.argv[2] if len(sys.argv) > 2 else "trinst"
    extract(mission, zone)
