# Trinst → gameplay_view integration & findings

How the converted Trinst zone is loaded into the live, server-connected game,
and the resolved questions about scale, spawning, and NPC navigation.

## Loading (live path)

The zone art loads into the **existing `gameplay_view`** (the post-login,
server-connected scene), not a standalone scene:

- `minions-port/world/zone_loader.gd` — canonical loader: builds terrain
  (triplanar grass/rock/sand shader + trimesh collision), interiors (collision),
  props, and a modern environment (ACES, PhysicalSky, soft-shadow sun, SSAO/SSIL,
  bloom, explicit colour ambient) from `res://assets/<zone>/scene.json`.
- `gameplay_view._load_zone_art()` runs on the first **self-entity snapshot**,
  once the server spawn offset (`_server_origin_offset`) is known. It adds the
  loader to `WorldRoot` at that offset so terrain/buildings line up with the
  server-driven `PlayerBody` and replicated entities, then removes the greybox.
- Defaults to `trinst`; reads `current_payload.zone` once the proxy forwards it.
- Coordinate convention matches the existing client exactly:
  `server (x, y, z) -> godot (x, z, -y)`.

## Scale — verified faithful (not a bug)

Measured against the asset viewer's 1.8 m human-reference capsule (1 unit = 1 m):

| Asset | Size | Note |
|---|---|---|
| Human avatar (DTS) | **1.82 u** | Human race `size = 1.0` in `mud/world/shared/models.py` |
| Guild sign | 2.75 u | correct human scale |
| Anvil | 1.4 u | correct |
| City house | ~17 u tall, 13×19 footprint | genuinely large in MoM |
| Tavern / guildhall | 16 u / 46 u | large |

Props/signs convert to correct human scale, so there is **no conversion scale
bug**. MoM simply has large, imposing architecture (EverQuest-era style), so a
1.8 m character is small next to buildings — that is authentic. A third-person
camera foreshortens distant buildings, which can make them *look* small relative
to the foreground player; that is a perspective artifact, not the real scale.

Buildings are **not** rescaled: it would be unfaithful and would desync the
geometry from the server, which places players/NPCs at these exact coordinates.
A deliberately smaller-feeling world would require a global re-scale of terrain +
buildings + server coordinates together (a design decision, not a fix).

## Spawn

Spawn position is **server-authoritative** (saved character position, or the
realm start for a new character); the client uses whatever position the server
sends and re-origins the world on it (`_server_origin_offset`).

**A new character does NOT spawn at the bind-point obelisk.** Captured live from
the world server, a fresh Human/Warrior spawns at the **guard-tower outpost**:
server `(31.80, -275.43, 126.0)` → godot `(31.80, 126.0, 275.43)`, a few metres
in front of the `GuardTower` (`prefabs/tower1.dif`, a peaked-roof gate tower)
at godot `(40.98, 125.35, 254.04)`. That tower — not the obelisk — is the
structure you see at spawn.

`rpgBindPoint = 257 134 152` (the `architecture/bindpoint.dif` obelisk, godot
`256.7, 147.5, -133.1`) is the **death-respawn** bind point, a separate location
~280 m away. Use `tools/spawn_probe.py` to re-capture the live spawn (it drives
the proxy like the Godot client and prints the raw self position).

## Spawn-area fidelity fixes (interiors were black; terrain was a desert)

Three issues made the spawn look wrong versus the original game:

- **Interiors rendered black.** `tools/dif/dif_to_gltf.py` emitted only
  `POSITION` + `TEXCOORD_0`, **no `NORMAL`s**, so every converted building
  (the guard tower, walls, houses…) had no normals and lit to near-black under
  any light — a dark monolith instead of stone. The converter already parsed the
  interior planes/normals but discarded them. Fixed: emit a per-surface flat
  normal from each surface's plane (`_surface_normal`, honouring the plane flip
  bit; materials are double-sided so sign is forgiving). All 40 Trinst interiors
  regenerated with normals.
- **City rendered as desert.** The terrain shader chose sand/grass/rock from
  **world-space** Y (`sand_height = 63`). Because the live game re-origins the
  whole zone on the player's spawn (shifting terrain world-Y down ~124 m), the
  city dropped below the sand threshold and the ground turned to sand. Fixed:
  key the sand blend off **object-space** elevation (`oheight = VERTEX.y`),
  which is invariant to the re-origin shift (`world/zone_loader.gd`,
  `tools/trinst_preview/preview.gd`).
- **Ground was green, not brown.** The build hardcoded the green `grass01.jpg`
  and the shader tinted it *further* toward green, but `city.ter`'s primary
  ground layer is `drygrass3` (brown). Fixed: use `drygrass3.jpg` as the ground
  texture and drop the green tint (`tools/build_trinst.py`, both shaders).

## NPCs / characters on the ground

Replicated entities raycast down onto the zone collision (terrain/buildings)
instead of sitting at a fixed height, so they stand on the ground.

## NPC navigation

- **Server-authoritative.** The client only renders the positions the server
  streams (now ground-snapped); it does not path anything.
- The nav **data is in the `.mis`**: Trinst has 374 `rpgSpawnPoint` (NPC spawns)
  and 151 `rpgWayPoint` (patrol routes / nav nodes).
- Original MoM ran the zone simulation (AI, pathfinding, collision) inside the
  Torque engine (`pytge`) — exactly the piece stubbed on Linux. The Python AI
  (`mud/simulation`, `mud/world`) drives high-level behaviour but relies on
  Torque (`TGEObject`) for movement/pathing.
- **Path forward (server-side):** bake a Godot `NavigationMesh` from the
  converted terrain+buildings (geometry already exists) and run pathfinding (in a
  Godot-based zone server, or feed results to the Python server); simple patrols
  can just follow `rpgWayPoint` sequences + ground-snap. Client needs nothing more.

## Open follow-ups

- Render the **real character avatar** (skinned DTS) instead of a capsule so
  scale reads naturally — in progress.
- Extract `rpgSpawnPoint`/`rpgWayPoint` + bake a navmesh as the nav foundation.
- Forward the zone name from `ClientProxy` so all 17 zones auto-load.
