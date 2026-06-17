#!/usr/bin/env python3
"""Regenerate minions-port/assets/sound/sound_manifest.json.

Exported Godot builds cannot enumerate imported .ogg files with DirAccess (only
the imported resource is packed, not the source file at its res:// path). The
client's music jukebox (world/audio.gd) and VFX sound index (world/vfx.gd) fall
back to this committed manifest of every .ogg under assets/sound/ so music and
combat/spell/vocal sounds still resolve in the .exe. Run this after adding or
removing sound files:

    python3 tools/gen_sound_manifest.py
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "minions-port", "assets", "sound")

rels = []
for dirpath, _dirs, files in os.walk(ROOT):
    for f in files:
        if f.lower().endswith(".ogg"):
            rel = os.path.relpath(os.path.join(dirpath, f), ROOT).replace("\\", "/")
            rels.append(rel)
rels.sort()

out = os.path.join(ROOT, "sound_manifest.json")
with open(out, "w") as fh:
    json.dump(rels, fh, indent=0)

print("wrote %s with %d entries" % (out, len(rels)))
