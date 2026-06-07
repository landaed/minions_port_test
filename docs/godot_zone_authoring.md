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

The root scene script (`world/zone_loader.gd`) adds runtime details that are not
convenient to store in the generated scene: collision, the fallback building
floor slabs, and the sky/sun environment. It is also a `@tool` script now, so
when `world/zones/trinst.tscn` is open in the editor it previews the same terrain
material used at runtime.

## Terrain material/shader

The terrain GLB itself has little/no useful material data from the conversion, so
it appears white if nothing overrides it. The Trinst loader applies
`world/zone_terrain.gdshader`, a triplanar spatial shader that blends:

- `assets/trinst/textures/grass01.jpg` on flatter areas,
- `assets/trinst/textures/rock009.jpg` on steep slopes, and
- `assets/trinst/textures/sand006.jpg` below the shoreline height.

That material is assigned directly to the generated terrain sub-node for
immediate editor visibility, applied again in editor tool mode as a safety net,
and applied again at runtime when the authored scene is finalized.

## Should Trinst become a "real Godot terrain"?

Godot does not have a built-in Unity-style terrain object in core 4.x. The
converted GLB is currently the safest authoritative representation because it
keeps the exact legacy height mesh and works with the existing collision and
server-coordinate offsets. Converting it to a heightmap-terrain addon later could
make sculpting/painting nicer, but it would be a separate pipeline decision and
would need validation that collision, spawn alignment, and server/client position
conversion still match.

For foliage placement, keeping the terrain as a mesh does not block us. The next
practical step is to add editor-side foliage/scatter helpers (for example
MultiMesh-based grass/tree painters or marker nodes) that raycast against the
terrain mesh, rather than replacing the terrain format first.


## Building collision notes

Authored interiors now receive two collision passes at runtime:

1. normal concave mesh collision for walls and solid geometry, and
2. an extra floor-only concave collider generated from upward-facing visual
   triangles.

The second pass is specifically to fix structures whose visible floors did not
produce reliable collision from the imported GLB. Broad rectangular footprint
slabs are now opt-in only in `world/zone_loader.gd` because they can create an
invisible vertical edge across entrances/gates; this is what made
`prefabs_tower1` gate openings hard to walk through. If a future building truly
has no usable floor triangles, add its asset key to `FOOTPRINT_FLOOR_INTERIORS`
only after confirming the slab does not cover a doorway.

NPC visual ground snapping now probes for collision near the server-provided
height before falling back to terrain. This keeps mobs that the server spawned on
upper/interior floors (for example inside `prefabs_tower1`) from being visually
dropped to the outside terrain. Dead mobs are also retained briefly on the client
so their death animation can play before the marker despawns.

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
they do not visually sink into hills or floors. The WebSocket proxy streams nearby
entities within `MOM_ENTITY_STREAM_RADIUS` units (default `120`) up to
`MOM_ENTITY_STREAM_LIMIT` entities (default `50`), so town NPC wandering remains
visible without making payloads unbounded.

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
