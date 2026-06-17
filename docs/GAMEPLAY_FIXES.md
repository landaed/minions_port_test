# Gameplay fixes: corpses, player death, performance, controls

Four issues from the Godot port, with the changes made and how each was verified
(real Godot 4.6 client driven headless against the full Python server stack via
`tools/death_corpse_test.gd`; software Vulkan / lavapipe under `xvfb`).

## 1. Dead enemies slide around

**Cause (client):** `gameplay_view._physics_process` interpolated *every*
replicated body toward the latest server position each frame, including corpses,
and re-ground-snapped them. Any server jitter (or a mob that died mid-stride)
made the corpse drift/slide.

**Fix:** the first frame an entity is dead, snap its body to the death spot once,
ground-snap once, and mark it `dead_frozen`. After that the body ignores all
server position/rotation updates and is skipped by the interpolation loop (it
still holds the death animation). See `_sync_entity_markers` and the body loop in
`_physics_process`.

**Verified:** corpse sampled for 28 frames after death → `max_drift = 0.0000
units`.

## 2. A dead player is stuck until they relog

**Cause:** on death the server sets `character.dead = True`, drops the mob, and
sets HP/MP/SP to 1; `getVisibleEntities` then returns nothing for that character.
The client had no death UI and there was **no respawn command** — the only thing
that resets `dead` was `enterWorld`'s "all characters dead" branch, i.e. a relog.

**Fix:**
- Server `PlayerAvatar.perspective_respawn` (`mud/world/playeravatar.py`) revives
  the dead party members, restores stats, and teleports to the bind point
  (`zone.respawnPlayer` → `playerRespawned` reattaches the mobs). Mirrors the
  relog reset without relogging.
- `getVisibleEntities` now returns an explicit `{"dead": True}` marker instead of
  a bare empty list so the proxy can tell "you died" from "nothing nearby".
- Proxy (`ClientProxy.py`) detects the death↔alive edge and sends
  `player_death` / `player_alive`; adds a `respawn` gameplay command.
- Client shows a "You have died" overlay with a Release/Respawn button
  (Enter / controller A), blocks movement while dead, and clears on revive.
- A `suicide` cheat (`mud/world/cheats.py`) was added to exercise the flow.

**Verified:** suicide → overlay shown (`_is_dead=true`) → respawn → `_is_dead=false`,
HP restored to full at the bind point. No relog.

## 3. Severe lag with several clients on a VPS

**Cause:** each client polled `getVisibleEntities` at **~33 Hz**, and every
snapshot re-sent *all* fields (identity, model, per-part textures, worn
equipment, …) for up to 50 entities. Fine on a LAN; on a VPS the proxy→client
hop (the bandwidth-limited one) and the single-threaded world server both
saturate. It is primarily a **bandwidth + replication-volume** problem, not raw
game logic.

**Fix (`ClientProxy.py` + `gameplay_view.set_entities`):**
- Poll rate → **~13 Hz** (`MOM_ENTITY_SYNC_INTERVAL`, default 0.075s). The client
  already interpolates between snapshots, so motion stays smooth.
- **Static/dynamic delta split:** identity/model/appearance/equipment are sent
  once (and again only when they change, plus a full resync every few seconds for
  self-healing); between those, only the small dynamic remainder
  (position/rotation/health/combat flags) is streamed. The client merges each
  partial onto a per-id cache.
- Position/rotation floats are rounded (1 cm / ~0.006°) to shorten the JSON.
- Toggles for profiling: `MOM_ENTITY_DELTA`, `MOM_ENTITY_ROUND`,
  `MOM_ENTITY_SYNC_INTERVAL`, `MOM_ENTITY_STATIC_RESYNC`.

**Measured (same town spot, identical visible set):**

| Config | Snapshots/s | Bandwidth per client |
|---|---|---|
| Before (33 Hz, full snapshots) | ~24 | **~100 KB/s** |
| After (13 Hz, delta + rounding) | ~11.5 | **~20 KB/s** |

≈ **5× less bandwidth** and ≈ **2× less world-server CPU** per client; both scale
with the number of clients. A heavier, longer-term option (not done here) is to
compute the zone's visible set once per tick and fan it out to all clients
instead of per-client polling.

## 4. Controls: controller support + action-MMO feel + bigger hotbar

**Fix (`gameplay_view.gd`, `ui/hotbar.gd`):**
- Input actions are defined in code (`_setup_input_actions`) bound to **both**
  keyboard/mouse and a gamepad:
  - Left stick / WASD = move; right stick / mouse = camera (twin-stick feel).
  - A = jump, X = interact/loot, B = target, RB = attack.
  - D-pad = hotbar slots 1–4; keys 1–0 = slots 1–10.
  - **Y / R = cycle the active hotbar page.**
  - **Hold LB / Shift = reveal + use the second hotbar.**
  - Back = inventory.
- The hotbar is now **two pages** (20 abilities, "limit to 2 hotbars"): only the
  active page shows; cycling swaps it; holding the secondary modifier reveals
  both rows and routes activations to the second page. Both pages persist per
  character and auto-fill from the character's skills + spells.

**Verified:** page cycle swaps the visible bar; holding Shift shows both bars
(`bar1 visible=true bar2 visible=true`). Gamepad bindings are defined and load
cleanly; physical-controller feel can only be confirmed with a device attached.
