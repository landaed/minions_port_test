#!/usr/bin/env python3
"""Generate an editable Godot .tscn scene from a converted MoM scene.json.

The generated scene instances the already-converted GLB assets once and stores
object transforms directly in the .tscn, so designers can move/rotate/delete
objects with Godot's editor instead of editing JSON. Runtime-only behavior such
as collision setup and terrain material is handled by world/zone_loader.gd.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "minions-port"
DEFAULT_ZONE = "trinst"
OUT_DIR = PROJECT / "world" / "zones"


def esc(value: str) -> str:
    return value.replace('\\', '\\\\').replace('"', '\\"')


def safe_name(prefix: str, rel: str, index: int) -> str:
    stem = Path(rel).stem
    name = re.sub(r"[^A-Za-z0-9_]+", "_", stem).strip("_") or prefix
    return f"{prefix}_{index:03d}_{name}"


def basis_from_axis_angle(axis: list[float], angle_degrees: float, scale: list[float]) -> list[list[float]]:
    x, y, z = axis
    length = math.sqrt(x * x + y * y + z * z)
    if length <= 1e-6 or abs(angle_degrees) <= 1e-6:
        # Columns of an identity basis scaled per-axis.
        return [[scale[0], 0.0, 0.0], [0.0, scale[1], 0.0], [0.0, 0.0, scale[2]]]
    x, y, z = x / length, y / length, z / length
    a = math.radians(angle_degrees)
    c = math.cos(a)
    s = math.sin(a)
    t = 1.0 - c
    # Row-major rotation matrix.
    r = [
        [t * x * x + c, t * x * y - s * z, t * x * z + s * y],
        [t * x * y + s * z, t * y * y + c, t * y * z - s * x],
        [t * x * z - s * y, t * y * z + s * x, t * z * z + c],
    ]
    # Godot Basis constructor in Transform3D text takes basis columns, and scale
    # is applied by scaling those columns.
    return [
        [r[0][0] * scale[0], r[1][0] * scale[0], r[2][0] * scale[0]],
        [r[0][1] * scale[1], r[1][1] * scale[1], r[2][1] * scale[1]],
        [r[0][2] * scale[2], r[1][2] * scale[2], r[2][2] * scale[2]],
    ]


def fmt_num(v: float) -> str:
    if abs(v) < 0.0000005:
        v = 0.0
    return f"{v:.6f}".rstrip("0").rstrip(".") or "0"


def transform_text(pos: list[float], rot: list[float], scale: list[float]) -> str:
    cols = basis_from_axis_angle(rot[:3], rot[3], scale)
    values = [*cols[0], *cols[1], *cols[2], *pos]
    return "Transform3D(" + ", ".join(fmt_num(float(v)) for v in values) + ")"


def collect_resources(data: dict, zone: str) -> list[str]:
    resources = ["res://world/zone_loader.gd"]
    terrain = data.get("terrain_glb")
    if terrain:
        resources.append(f"res://assets/{zone}/{terrain}")
    for section in ("statics", "interiors"):
        for item in data.get(section, []):
            rel = item.get("glb")
            if rel:
                resources.append(f"res://assets/{zone}/{rel}")
    # Stable de-dup preserving order.
    seen: set[str] = set()
    unique: list[str] = []
    for r in resources:
        if r not in seen:
            seen.add(r)
            unique.append(r)
    return unique


def emit_instance(lines: list[str], parent: str, name: str, res_id: int, item: dict, role: str, collide: bool) -> None:
    rel = item.get("glb", "")
    lines.append(f'[node name="{esc(name)}" parent="{esc(parent)}" instance=ExtResource("{res_id}")]')
    lines.append(f'transform = {transform_text(item.get("pos", [0, 0, 0]), item.get("rot", [1, 0, 0, 0]), item.get("scale", [1, 1, 1]))}')
    lines.append(f'metadata/zone_glb = "{esc(Path(rel).stem)}"')
    lines.append(f'metadata/source_glb = "{esc(rel)}"')
    lines.append(f'metadata/zone_role = "{role}"')
    if collide:
        lines.append('metadata/zone_collide = true')
    lines.append("")


def generate(zone: str = DEFAULT_ZONE) -> Path:
    src = PROJECT / "assets" / zone / "scene.json"
    data = json.loads(src.read_text())
    resources = collect_resources(data, zone)
    res_ids = {path: idx + 1 for idx, path in enumerate(resources)}

    lines: list[str] = []
    lines.append(f'[gd_scene load_steps={len(resources) + 1} format=3 uid="uid://mom_{zone}_authored_scene"]')
    lines.append("")
    for path in resources:
        typ = "Script" if path.endswith(".gd") else "PackedScene"
        lines.append(f'[ext_resource type="{typ}" path="{esc(path)}" id="{res_ids[path]}"]')
    lines.append("")
    lines.append(f'[node name="{zone.capitalize()}Zone" type="Node3D"]')
    lines.append('script = ExtResource("1")')
    lines.append(f'authored_zone_name = "{esc(zone)}"')
    lines.append("")

    terrain = data.get("terrain_glb")
    if terrain:
        item = {
            "glb": terrain,
            "pos": data.get("terrain", {}).get("pos", [0, 0, 0]),
            "rot": [1, 0, 0, 0],
            "scale": [1, 1, 1],
        }
        emit_instance(lines, ".", "Terrain", res_ids[f"res://assets/{zone}/{terrain}"], item, "terrain", False)

    lines.append('[node name="Statics" type="Node3D" parent="."]')
    lines.append("")
    for i, item in enumerate(data.get("statics", []), 1):
        rel = item.get("glb")
        if not rel:
            continue
        emit_instance(lines, "Statics", safe_name("Static", rel, i), res_ids[f"res://assets/{zone}/{rel}"], item, "static", False)

    lines.append('[node name="Interiors" type="Node3D" parent="."]')
    lines.append("")
    for i, item in enumerate(data.get("interiors", []), 1):
        rel = item.get("glb")
        if not rel:
            continue
        emit_instance(lines, "Interiors", safe_name("Interior", rel, i), res_ids[f"res://assets/{zone}/{rel}"], item, "interior", True)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{zone}.tscn"
    out.write_text("\n".join(lines))
    return out


if __name__ == "__main__":
    out = generate()
    print(out.relative_to(ROOT))
