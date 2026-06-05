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
zone bind point for a new character); the client uses whatever position the
server sends. Trinst's bind point is `rpgBindPoint = 257 134 152` in `city.mis`
(outside the gates). The client honours it.

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
