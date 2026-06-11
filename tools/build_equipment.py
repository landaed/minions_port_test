#!/usr/bin/env python3
"""Batch-convert MoM equipment models (weapons/shields/helmets) to .glb files
in the Godot project (minions-port/assets/equipment/).

These are rigid shapes mounted onto a character skeleton's Mount0..Mount3
bones (Mount0 = primary hand, 1 = off hand, 2 = shield, 3 = head). The server
streams each entity's worn mount model paths (e.g. "weapons/sword01.dts");
the Godot client maps that to assets/equipment/<sanitized>.glb — the same
sanitization used here: path below shapes/equipment with "/" -> "_", no .dts.

Usage:
    python3 tools/build_equipment.py            # convert everything
    python3 tools/build_equipment.py sword01    # only files matching a substring
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "dts"))
import dts_to_gltf as conv  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
EQUIP = ROOT / "MoMReborn/minions.of.mirth/data/shapes/equipment"
OUT = ROOT / "minions-port/assets/equipment"


def main():
    only = [a.lower() for a in sys.argv[1:]]
    OUT.mkdir(parents=True, exist_ok=True)
    sources = sorted(EQUIP.rglob("*.dts"))
    done = failed = skipped = 0
    for src in sources:
        rel = src.relative_to(EQUIP)
        if only and not any(o in str(rel).lower() for o in only):
            continue
        key = str(rel.with_suffix("")).lower().replace("/", "_")
        dst = OUT / (key + ".glb")
        try:
            conv.convert(str(src), str(dst))
            print("  %-34s -> %s" % (rel, dst.name))
            done += 1
        except Exception as exc:
            print("  %-34s FAILED: %s" % (rel, exc))
            failed += 1
    print("converted %d, failed %d (of %d dts files)" % (done, failed, len(sources)))


if __name__ == "__main__":
    main()
