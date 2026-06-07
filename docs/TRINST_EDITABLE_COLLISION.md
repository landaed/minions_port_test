# Trinst editable scene and collision baking

The live Godot client should use `res://world/zones/trinst.tscn` as the canonical
editable Trinst scene. That scene is supplied by the scene-conversion branch on
`master`; this branch keeps only the reusable editable GLB wrapper scenes under
`res://assets/trinst/editable/` plus optional bake tooling.

Normal editing should happen in `res://world/zones/trinst.tscn` or in one of the
wrapper scenes under `res://assets/trinst/editable/`. This branch intentionally no
longer commits its own generated `trinst.tscn`, so the `master` scene can merge
without an add/add conflict.

## Why this exists

The old live path loaded imported GLBs from JSON and called
`create_trimesh_collision()` during gameplay. That made the world hard to tune:
imported GLB nodes are awkward to edit directly, and collision was regenerated
every run instead of being normal editor-owned scene data.

Use the bake script only if the canonical scene has to be regenerated from the
converted JSON/GLB data:

1. Run the editor script once.
2. Open `res://world/trinst_baked.tscn` or move/merge it into
   `res://world/zones/trinst.tscn`.
3. Use Godot's **Editable Children** / inherited-scene workflow to tune individual
   placed assets or open a wrapper under `res://assets/trinst/editable/` to tune a
   source asset's shared collision.
4. Commit the generated/merged `.tscn` files when you are happy with them.

The script skips already-created wrapper scenes so hand edits to shared asset
wrappers are not overwritten on later runs. The placed `trinst_baked.tscn` is
rebuilt from `scene.json` each run.

The loader behavior for `res://world/zones/trinst.tscn` is owned by the
scene-conversion branch on `master`; keep this branch focused on wrappers, bake
tooling, and vertical replication so those files do not conflict.

## Collision policy in the bake script

- Terrain gets saved trimesh collision on the normal world layer and the terrain
  raycast layer.
- Interiors/buildings get saved trimesh collision unless listed as passthrough.
- Object/rock/tree statics get saved collision.
- Lanterns/plants remain decorative by default to avoid turning small visual
  clutter and alpha-card foliage into blockers.
- Large meshes also receive the same fallback floor slab used by the runtime
  loader, which helps converted interiors whose source meshes do not provide
  reliable walkable floors.

## Vertical replication note

Server positions already contain three coordinates, but the headless stub does not
have Godot's building/floor colliders. The Godot client now sends its
collision-resolved vertical coordinate with movement input as `position_z`; the
proxy forwards it to `PlayerAvatar.updateInput`, and the stub stores it on the
player sim object. Replicated NPC placement now snaps to the floor nearest the
server-provided height, so upper-floor NPCs and stair situations are not forced
back down to terrain height.
