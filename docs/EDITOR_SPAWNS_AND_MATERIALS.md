# Editor spawn placement, material enhancement, and movement-sync tuning

Three systems added in this change set.

## 1. Movement drift (was: ~8u, then 2u dead zone)

**Server** (`mud/world/stubsim.py`): the movement tick now integrates *real
elapsed time* instead of a fixed 50 ms step, so the server-side player speed is
exactly 8 u/s wall clock even when the reactor runs late. (Verified with
`tools/proxy_move_probe.py`: 40.03u traveled over a 5.00s key hold, expected
40.01u, zero post-release movement.)

**Client** (`minions-port/gameplay_view.gd`): reconciliation no longer compares
the server snapshot against the *current* predicted position (that difference is
dominated by snapshot latency while moving, which is why the old dead zone had
to be 2–8u). Instead the snapshot is matched against the client's recent
trajectory (`RECONCILE_HISTORY_WINDOW`, 0.8 s); the residual is true drift.

- `RECONCILE_DEAD_ZONE = 0.35` — drift below this is ignored (jitter floor).
- Corrections are consumed a little per physics frame *inside* `move_and_slide`
  (`RECONCILE_RATE`, capped at `RECONCILE_MAX_SPEED`), so they read as a gentle
  glide, never a 3–10 Hz stutter, and still can't push through walls.
- `SERVER_RECONCILE_SNAP_THRESHOLD = 12` still hard-snaps genuine teleports.

Tuning: lower `RECONCILE_DEAD_ZONE` for tighter tracking, raise
`RECONCILE_RATE` for faster (but more visible) corrections. Measure with:

```
xvfb-run godot --path minions-port --script res://tools/drift_test_driver.gd
```

## 2. Editor-placed NPC / monster spawns (server stays authoritative)

Spawn markers for trinst now live in the zone scene:
`minions-port/world/zones/trinst.tscn` → `Spawns` node → 374 `MoMSpawnPoint`
nodes (script: `minions-port/world/spawn_point.gd`).

- **Move/rotate a node in the editor = move the spawn.** The node's -Z is the
  mob's facing. The server parses the `.tscn` directly at zone start
  (`mud/world/godotspawns.py`, hooked in `stubsim.refreshSpawnPoints`), so a
  server restart picks up editor changes — no export step.
- Editor preview (only in the editor, never saved or loaded in game): the real
  mob model when a converted glb exists, name/level/respawn label, green ring =
  stationary NPC (`wander_group = -1`), orange ring + 10u radius circle =
  wandering mob.
- Per-node properties: `spawn_group` (must exist in the world DB — that's the
  server-authority boundary), `wander_group`, `enabled` (untick to disable a
  marker without deleting it).
- What spawns from a group, respawn timers, loot, levels and AI all stay in the
  server DB exactly as before. Zones without scene markers (e.g. kauldur) fall
  back to the legacy `.mis` markers automatically.

Re-import the legacy mission layout (replaces the whole `Spawns` node):

```
./venv/bin/python tools/godot_spawns.py --zone trinst
godot --headless --path minions-port --script res://tools/import_spawn_points.gd
```

## 3. Automated material enhancement (offline, toggleable)

`tools/enhance_materials.sh` (wraps `minions-port/tools/enhance_materials.gd`):

1. **generate** — for every prop albedo (`assets/trinst/{interiors,shapes}/*.jpg`)
   bakes `<name>_normal.png` (sobel height→normal), `<name>_rough.png`
   (luminance-based roughness variation) and `<name>_ao.png` (cavity AO) on
   disk. Nothing is generated at runtime.
2. **import** — standard Godot reimport of the new textures.
3. **apply** — builds shared `StandardMaterial3D` `.tres` resources under
   `assets/trinst/materials/generated/` (per-category normal strength /
   roughness / specular chosen from the legacy material name: wood, stone,
   shingle, metal, foliage, ...) and assigns them as surface overrides in the
   editable prop scenes. Hand-made overrides (e.g. the two hand-tuned tower1
   materials) are detected and left untouched.

Toggle features globally at any time (no regeneration):

```
godot --headless --path minions-port --script res://tools/toggle_material_features.gd -- --normal=off
  (also: --rough=on|off  --ao=on|off  --normal-scale=K  --specular=F)
```

Full removal: `enhance_materials.gd -- --phase=strip` restores plain GLB
albedo materials.

**Note:** this work also fixed the missing guard tower — the hand-edited
`interiors__prefabs_tower1.tscn` referenced `prefabs_tower1_{0,7}_normal.png`
which didn't exist in the repo, so Godot refused to load the whole scene and
the tower vanished. The generator now produces those files (and the rest).

## Visual debugging helpers

- `tools/zone_shot.gd` — renders the authored zone from any camera
  (`CAM_POS`/`CAM_LOOK`/`SHOT` env), `MOM_FORCE_SPAWN_PREVIEW=1` also draws
  spawn markers. No servers needed.
- `tools/drift_test_driver.gd` — full client boot + scripted run/strafe/stop
  movement with desync/jitter stats.
- `tools/proxy_move_probe.py` — pure-Python (no Godot) server movement probe.
