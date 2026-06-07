# Godot rendering, post-processing, materials, and camera tuning

## Post-processing effects

There is no post-processing shader attached to `Camera3D` right now. The live
zone creates a `WorldEnvironment` in `minions-port/world/zone_loader.gd` and all
current post-processing-style settings live on that `Environment` resource:

- ACES tonemapping (`tonemap_mode`, `tonemap_white`),
- SSAO/SSIL,
- glow/bloom,
- depth fog,
- color adjustment contrast/saturation, and
- sky/ambient lighting.

To adjust global post-processing for Trinst, start in `_setup_environment()` in
`world/zone_loader.gd`. If you want an editor-authored workflow later, the next
step should be moving those `Environment` settings into a `.tres` resource and
having the loader instance/use that resource instead of constructing it fully in
code.

Camera-specific post effects in Godot are usually done with either:

1. a `WorldEnvironment`/`Environment` for built-in effects, or
2. a full-screen shader pass (for example a `ColorRect`/SubViewport effect or a
   screen-reading shader) for custom color grading, outlines, CRT effects, etc.

Use the built-in `Environment` path first for fog, glow, exposure/tonemap, SSAO,
and color adjustments; use full-screen shaders only when the effect is not
available on `Environment`.

## Editing terrain, prop, building, and character materials

### Terrain

Trinst terrain uses `world/zone_terrain.gdshader` and
`world/zone_terrain_material.tres`. The generated scene assigns that material to
the imported terrain mesh so it is visible in-editor, and `zone_loader.gd`
reapplies the same shader at runtime.

### Props and buildings

Most props/buildings are instanced GLBs under `world/zones/trinst.tscn`. For a
one-off edit:

1. open `world/zones/trinst.tscn`,
2. select the prop/building instance,
3. enable/edit children if needed,
4. select its `MeshInstance3D`, and
5. set `surface_material_override/<surface>` or `material_override` in the
   inspector.

For a reusable edit across every instance of an asset, change the source GLB or
add a loader/generator rule that assigns a material override based on
`metadata/source_glb` or `metadata/zone_glb`. Avoid editing generated scene lines
by hand if you plan to regenerate the scene.

### Characters

Characters are loaded through `world/character_rig.gd`. Player/NPC texture swaps
come from `CharacterRig.apply_appearance()`, which overrides surfaces whose
materials are named like `base.head`, `base.body`, etc. Monsters generally keep
their embedded GLB textures.

For character material work:

- edit converted character GLB materials/textures for broad changes,
- update `CharacterRig.apply_appearance()` for race/body-part texture logic, or
- add a new material pass in `CharacterRig.setup()` if every loaded character
  should get shared settings such as roughness/emission tweaks.

## Camera zoom

The gameplay camera is a child of `PlayerBody/CameraYaw/CameraPitch`. The live
client now supports mouse-wheel zoom by changing the camera's local Z offset.
The tuning constants are in `gameplay_view.gd`:

- `CAMERA_ZOOM_MIN`,
- `CAMERA_ZOOM_MAX`, and
- `CAMERA_ZOOM_STEP`.

## Server/client visual reconciliation

Movement is still server authoritative. The client predicts locally, receives
server snapshots, and reconciles toward the server. The relevant tuning constants
are in `gameplay_view.gd`:

- `SERVER_RECONCILE_THRESHOLD` — how much X/Z disagreement is allowed before the
  player is nudged toward the server,
- `SERVER_RECONCILE_BLEND` — how strongly to correct moderate disagreement,
- `SERVER_RECONCILE_SNAP_THRESHOLD` — large disagreement snaps/corrects fully,
- `ENTITY_INTERPOLATION_SPEED` — how quickly NPC/player markers chase server
  snapshot targets, and
- `ENTITY_SNAP_DISTANCE` — marker disagreement above this distance snaps to the
  latest server target.

Tighter values reduce visible disagreement but can make latency/rubber-banding
more noticeable, so tune these while watching both responsiveness and collision.
