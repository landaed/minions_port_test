#!/usr/bin/env python3
"""Batch-convert MoM character models + shared animations into animated, skinned
.glb files in the Godot project (minions-port/assets/characters/).

Output naming:
  - playable races:  <race>_<sex>.glb   (e.g. human_male.glb)  keyed by race+sex
  - monsters:        <sanitized model path>.glb (e.g. undead_skeleton.glb)
The Godot client maps a streamed entity's (model | race+sex) to one of these.

Animations are bound to bones by name, so the biped (humanoid) animation set
applies to every humanoid race even where a race-specific folder is missing.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "dts"))
import dts_skin_to_gltf as conv  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SHAPES = ROOT / "MoMReborn/minions.of.mirth/data/shapes/character"
MODELS = SHAPES / "models"
ANIMS = SHAPES / "animations"
TEX = SHAPES / "textures"
OUT = ROOT / "minions-port/assets/characters"


def pick(folder, *cands):
    for c in cands:
        p = ANIMS / folder / (c + ".dsq")
        if p.exists():
            return str(p)
    return None


def anims_for(folder):
    """Resolve idle/walk/run/attack/death within an animation folder, tolerating
    the humanoid (1hwalk/unarmedright) vs creature (walk/attack1) naming."""
    spec = [
        ("idle", True, ("idle", "swimidle")),
        ("walk", True, ("1hwalk", "walk")),
        ("run", True, ("1hrun", "run", "1hwalk", "walk")),
        ("attack", False, ("unarmedright", "1hslashright", "attack1", "1hslash", "attack")),
        ("attack2", False, ("unarmedleft", "1hslashleft", "attack2")),
        ("death", False, ("death",)),
    ]
    out = []
    for name, loop, cands in spec:
        p = pick(folder, *cands)
        if p:
            out.append({"name": name, "dsq": p, "loop": loop})
    return out


# (output key, model rel path under models/, animation folder, texture index overrides)
JOBS = [
    ("human_male",     "human/human_male_0.dts",       "humanoid",       {}),
    ("human_female",   "human/human_female_0.dts",     "humanoidfemale", {}),
    ("orc_male",       "orc/orc_male_0.dts",           "humanoid",       {}),
    ("orc_female",     "orc/orc_female_0.dts",         "humanoidfemale", {}),
    ("goblin_male",    "goblin/goblin_male_0.dts",     "humanoid",       {}),
    ("goblin_female",  "goblin/goblin_female_0.dts",   "humanoidfemale", {}),
    ("troll_male",     "troll/troll_male_0.dts",       "trollmale",      {}),
    ("troll_female",   "troll/troll_female_0.dts",     "humanoidfemale", {}),
    ("elf_male",       "elf/elf_male_0.dts",           "humanoid",       {}),
    ("elf_female",     "elf/elf_female_0.dts",         "humanoidfemale", {}),
    ("gnome_male",     "gnome/gnome_male_0.dts",       "humanoid",       {}),
    ("gnome_female",   "gnome/gnome_female_0.dts",     "humanoidfemale", {}),
    ("dwarf_male",     "dwarf/dwarf_male_0.dts",       "humanoid",       {}),
    ("dwarf_female",   "dwarf/dwarf_female_0.dts",     "humanoidfemale", {}),
    ("halfling_male",  "halfling/halfling_male_0.dts", "humanoid",       {}),
    ("halfling_female","halfling/halfling_female_0.dts","humanoidfemale",{}),
    ("titan_male",     "titan/titan_male_0.dts",       "titanmale",      {}),
    ("titan_female",   "titan/titan_female_0.dts",     "humanoidfemale", {}),
    ("drakken_male",   "drakken/drakken_male_0.dts",   "drakken",        {}),
    ("drakken_female", "drakken/drakken_female_0.dts", "drakkenfemale",  {}),
    # monsters (keyed by sanitized model path the server sends)
    ("undead_skeleton","undead/skeleton.dts",          "humanoid",       {}),
    ("undead_undead",  "undead/undead.dts",            "humanoid",       {}),
]


_RACIAL_DIRS = {"human", "elf", "gnome", "dwarf", "halfling", "titan",
                "drakken", "orc", "goblin", "troll", "ogre"}


def _find_db():
    import glob
    hits = glob.glob(str(ROOT / "**" / "world.db"), recursive=True)
    return hits[0] if hits else None


def creatures_from_db():
    """Every non-racial monster model the world DB references, keyed by its
    sanitized model path (animal/bear.dts -> animal_bear), with its animation
    folder and a default whole-body texture (single/ or multi/)."""
    db = _find_db()
    if not db:
        print("  (no world.db found; skipping creatures)")
        return []
    import sqlite3
    cur = sqlite3.connect(db).cursor()
    cur.execute("SELECT model, animation, texture_single, texture_body FROM spawn WHERE model!=''")
    best = {}
    for m, a, ts, tb in cur.fetchall():
        if not m or m.split("/")[0].lower() in _RACIAL_DIRS or "/" not in m:
            continue
        key = m.lower().replace(".dts", "").replace("/", "_")
        tex = ts if ts else (tb if tb and tb.lower().startswith("multi/") else "")
        prev = best.get(key)
        if prev is None or (tex and not prev[2]):
            best[key] = (m, (a or "").lower(), tex)
    return [(k, v[0], v[1], v[2]) for k, v in sorted(best.items())]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    only = sys.argv[1:] or None
    for key, model_rel, folder, texidx in JOBS:
        if only and key not in only:
            continue
        model = MODELS / model_rel
        if not model.exists():
            print("  SKIP %-16s (missing %s)" % (key, model_rel))
            continue
        anims = anims_for(folder)
        out = OUT / (key + ".glb")
        try:
            info = conv.convert(str(model), str(out), anims,
                                tex_dir=str(TEX), tex_indices=texidx)
            print("  %-16s <- %-28s anims=%s nodes=%d prims=%d" % (
                key, model_rel, info["anims"], info["nodes"], info["prims"]))
        except Exception as e:
            print("  FAIL %-16s %s: %s" % (key, model_rel, e))

    # Creatures / monsters (bears, wolves, spiders, golems, dragons, ...).
    for key, model_rel, folder, single_tex in creatures_from_db():
        if only and key not in only:
            continue
        model = MODELS / model_rel
        if not model.exists():
            print("  SKIP %-22s (missing %s)" % (key, model_rel))
            continue
        anims = anims_for(folder)
        out = OUT / (key + ".glb")
        try:
            info = conv.convert(str(model), str(out), anims,
                                tex_dir=str(TEX), single_tex=single_tex or None)
            print("  %-22s <- %-26s anims=%s nodes=%d prims=%d tex=%s" % (
                key, model_rel, info["anims"], info["nodes"], info["prims"], single_tex or "-"))
        except Exception as e:
            print("  FAIL %-22s %s: %s" % (key, model_rel, e))


if __name__ == "__main__":
    main()
