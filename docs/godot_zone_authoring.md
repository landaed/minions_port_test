# Godot zone authoring for Trinst

Trinst now has an editable Godot scene at `minions-port/world/zones/trinst.tscn`.
The login/gameplay flow prefers that scene after the server sends the player's
first authoritative entity snapshot. `scene.json` is still kept as source data and
as a fallback for zones that have not been converted to `.tscn` yet, but Trinst is
no longer instantiated from JSON in the live client.

## Editing the world

1. Open `minions-port/project.godot` in Godot.
2. Open `world/zones/trinst.tscn`.
3. Move, rotate, add, hide, or delete children under `Statics` and `Interiors`.
4. Save the scene and run the client normally.

The root scene script (`world/zone_loader.gd`) only adds runtime details that are
not convenient to store in the generated scene: terrain material, collision, the
fallback building floor slabs, and the sky/sun environment.

## Regenerating from `scene.json`

If the converted assets or JSON are rebuilt, regenerate the editable scene with:

```bash
python3 tools/generate_godot_zone_scene.py
```

Regeneration overwrites `minions-port/world/zones/trinst.tscn`, so commit or copy
any manual editor work before running it.

## Pathfinding and server authority

There is currently no Godot navigation mesh used for authoritative movement. The
legacy Python world server remains authoritative for entity state and combat. The
Godot client sends movement inputs, predicts local player motion for responsiveness,
and reconciles against server snapshots. NPCs and other replicated entities are
rendered from server snapshots and locally snapped to visible terrain/collision so
they do not visually sink into hills or floors.

That means moving visual/collision objects in `trinst.tscn` does **not** require a
Godot navmesh rebake right now. What you do need to watch is collision:

- Terrain must keep `metadata/zone_role = "terrain"` so its collider receives the
  terrain-only collision bit used by NPC ground-snap rays.
- Walkable buildings/interiors should keep `metadata/zone_collide = true` if the
  player should collide with them.
- Decorative pass-through interiors such as `architecture_bindpoint` are exempted
  by `world/zone_loader.gd` so new characters do not spawn trapped.
- If you later add actual Godot `NavigationRegion3D` nodes for client-side click
  movement or local NPC preview, then those navigation meshes would need to be
  rebaked after geometry/collision edits. That would still be client-side unless
  the server starts consuming exported nav data.
