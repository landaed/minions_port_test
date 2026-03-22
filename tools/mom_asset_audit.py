#!/usr/bin/env python3
"""Inventory Torque-era Minions of Mirth assets for a Godot port.

This script does not attempt to fully convert proprietary asset formats.
Instead it builds a machine-readable manifest that tells you:
- what assets exist,
- which missions reference which terrain/interiors/shapes/textures,
- where to focus manual converter work first.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

MISSION_PROPERTY_RE = re.compile(r'^\s*([A-Za-z0-9_]+)\s*=\s*"([^"]*)";')
MISSION_OBJECT_RE = re.compile(r'^\s*new\s+([A-Za-z0-9_]+)(?:\([^)]*\))?\s*\{')
FILE_REF_RE = re.compile(r'(~?/[^"\s;]+|\./[^"\s;]+|[A-Za-z0-9_./\-]+\.(?:dts|dif|ter|png|jpg|jpeg|dds|ogg|wav|dml|ml))', re.IGNORECASE)

CONVERTIBLE_COPY_EXTS = {'.png', '.jpg', '.jpeg', '.ogg', '.wav'}
PROPRIETARY_EXTS = {'.dts', '.dif', '.ter', '.ml', '.dml', '.dsq', '.dso', '.hfl'}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default='MoMReborn/minions.of.mirth', help='Game asset root to scan.')
    parser.add_argument('--output', default='docs/generated/mom_asset_manifest.json', help='JSON manifest output path.')
    parser.add_argument('--mission', action='append', default=[], help='Specific mission basename(s) to include detailed object dumps for.')
    return parser.parse_args()


def scan_files(root: Path) -> Tuple[List[Path], Counter]:
    files = [p for p in root.rglob('*') if p.is_file()]
    counts = Counter(p.suffix.lower().lstrip('.') or '<noext>' for p in files)
    return files, counts


def normalize_ref(ref: str, mission_dir: Path, root: Path) -> str:
    ref = ref.replace('~/', '').lstrip('./')
    candidate = (mission_dir / ref).resolve()
    try:
        if candidate.is_file():
            return candidate.relative_to(root.resolve()).as_posix()
    except Exception:
        pass
    alt = (root / ref).resolve()
    try:
        if alt.is_file():
            return alt.relative_to(root.resolve()).as_posix()
    except Exception:
        pass
    return ref


def parse_mission_file(path: Path, root: Path, include_objects: bool = False) -> Dict:
    text = path.read_text(errors='ignore').splitlines()
    mission_dir = path.parent
    objects: List[Dict] = []
    stack: List[Dict] = []
    refs = set()
    object_counts = Counter()

    for line in text:
        match = MISSION_OBJECT_RE.match(line)
        if match:
            obj = {'class': match.group(1), 'properties': {}}
            stack.append(obj)
            continue

        prop = MISSION_PROPERTY_RE.match(line)
        if prop and stack:
            key, value = prop.groups()
            stack[-1]['properties'][key] = value
            for ref in FILE_REF_RE.findall(value):
                refs.add(normalize_ref(ref, mission_dir, root))
            continue

        if line.strip().startswith('};') and stack:
            obj = stack.pop()
            object_counts[obj['class']] += 1
            if include_objects:
                objects.append(obj)

    terrain_files = sorted({obj['properties']['terrainFile'] for obj in objects if 'terrainFile' in obj['properties']}) if include_objects else []
    interior_files = sorted({obj['properties']['interiorFile'] for obj in objects if 'interiorFile' in obj['properties']}) if include_objects else []
    shape_files = sorted({obj['properties']['shapeName'] for obj in objects if 'shapeName' in obj['properties']}) if include_objects else []

    # collect common references even when not dumping all objects
    if not include_objects:
        raw_text = path.read_text(errors='ignore')
        for ref in FILE_REF_RE.findall(raw_text):
            refs.add(normalize_ref(ref, mission_dir, root))

    return {
        'path': path.relative_to(root).as_posix(),
        'object_counts': dict(object_counts),
        'references': sorted(refs),
        'terrain_files': terrain_files,
        'interior_files': interior_files,
        'shape_files': shape_files,
        'objects': objects if include_objects else None,
    }


def build_manifest(root: Path, mission_names: Iterable[str]) -> Dict:
    files, counts = scan_files(root)
    missions = sorted(root.glob('data/missions/*.mis'))
    requested = {name.lower().removesuffix('.mis') for name in mission_names}

    manifest = {
        'root': root.as_posix(),
        'totals': {
            'files': len(files),
            'by_extension': dict(counts.most_common()),
            'copy_ready_files': sum(1 for p in files if p.suffix.lower() in CONVERTIBLE_COPY_EXTS),
            'proprietary_files': sum(1 for p in files if p.suffix.lower() in PROPRIETARY_EXTS),
        },
        'missions': {},
        'high_level': {
            'textures_audio_ready': sorted(
                p.relative_to(root).as_posix() for p in files if p.suffix.lower() in CONVERTIBLE_COPY_EXTS
            )[:200],
            'proprietary_examples': sorted(
                p.relative_to(root).as_posix() for p in files if p.suffix.lower() in PROPRIETARY_EXTS
            )[:200],
        },
    }

    for mission in missions:
        name = mission.stem.lower()
        include_objects = not requested or name in requested
        manifest['missions'][mission.stem] = parse_mission_file(mission, root, include_objects=include_objects)

    return manifest


def main() -> int:
    args = parse_args()
    root = Path(args.root)
    if not root.exists():
        raise SystemExit(f'Asset root not found: {root}')

    manifest = build_manifest(root, args.mission)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True))

    print(f'Wrote asset manifest to {output}')
    print(f"Scanned {manifest['totals']['files']} files under {root}")
    for ext, count in list(manifest['totals']['by_extension'].items())[:10]:
        print(f'  .{ext}: {count}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
