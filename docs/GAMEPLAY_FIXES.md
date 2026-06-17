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

---

# Round 2: targeting/range, replication detail, wall phasing, ability effects

## Combat: "I'm clearly hitting the bear but it says out of range / not facing"

The headless server validates every swing against THREE gates using its own
positions and a once-per-second `canSee` list: `canSee` (obstructed), `isFacing`,
and `GetRangeMin > weaponRange/5` (often only ~2-3u). The Godot client shows
mobs an interpolation interval behind and the player a hair off the server, so
those strict gates reject hits that clearly connect on screen.

Fix (the standard tab-target approach — trust the player's selection):
- `isFacing` already auto-passes for a selected target. Now `combat.py` and
  `spell.py` also **skip the `canSee` gate** and **add melee/cast leeway**
  (`MOM_MELEE_LEEWAY`, default 3.5u, in `core.py`) when a player acts on the mob
  they explicitly selected. Incidental/NPC attacks are unchanged.
- Verified: a full kill now produces **zero** "out of melee range / obstructed /
  facing the wrong way" denials.

## What is replicated, and how often

Per nearby entity (≤120u, ≤50), the proxy streams a snapshot at
`MOM_ENTITY_SYNC_INTERVAL` (~13 Hz). It is now a 3-tier delta:
- **static** (name/race/class/model/textures/equipment/level) — sent once, resent
  only on change (+ a full resync every few seconds to self-heal);
- **dynamic** (position/rotation/health/combat flags/visibility/flying) — sent
  only when it changes;
- **heartbeat** (`{id}`) — when nothing changed, so an idle town NPC costs ~one
  field per snapshot instead of a full record.
Proxy-internal fields (`distance`/`visibility_source`) are no longer sent.
The client merges each partial onto a per-id cache. So no — not everything is
resent every cycle. The player→server channel is just movement input (~20 Hz);
the server is authoritative for the player's position and all combat.

## Player position deviation / wall phasing

The client predicts movement and the server (which has **no collision**)
integrates the same inputs. The reconcile dead zone is 0.35u and it corrects
continuously — normal deviation is well under 1u, not 8. The old hard-snap
threshold (12u) is now only triggered by a **sudden** server jump (real
teleport: zone link, respawn, GM warp). Gradual divergence — e.g. holding into a
wall, where the no-collision server slides forward — is corrected smoothly via
`move_and_slide`, so the player slides along geometry and is never teleported
**through** a wall.

## Is it the VPS? (KVM2: 2 vCPU / 8 GB)

Adequate for a small group, not the cause of the targeting bug. The single
zone-sim thread is the ceiling (2 cores), and 8 GB RAM / 8 TB bandwidth are
ample. Round-1 cut per-client bandwidth ~5x; the delta above cuts it further in
populated areas. The targeting issues were design/tuning, fixed in code.

## Abilities that "did nothing" — replication gaps

These change server-side mob attributes that weren't streamed, so the client
showed no change. Now replicated + rendered:
- **Enlarge / Shrink** → `size`: streamed as live `scale` (= spawn scale ×
  mob.size); client resizes the model.
- **Erar Invisibility** → `visibility`: streamed; client fades the model
  (`CharacterRig.set_fade`, floored so it's a faint outline).
- **Urug's Sandals Fly / levitate** → `flying`: streamed; client lifts the model
  and applies slow-fall gravity to the player.
- **Transmutation of Volsh** → it's a buff (haste/str/offense) **and an illusion**
  (`illusion_id 23 = dragon/dragon_blue.dts`): you turn into a **blue dragon**.
  Illusions/forms (Werewolf, Illusion-races, etc.) were never replicated.
  `getVisibleEntities` now overrides the streamed model/animation/size with the
  active `illusionEffect`, and the client rebuilds the rig — so you actually
  become the dragon. `DoIllusion` was also made headless-safe (it crashed on the
  player's missing Torque `spawnInfo`, so the illusion never even registered).
- Test cheats added: `suicide`, `apply_spell <name>` (apply any spell instantly).

Verified end to end: Enlarge 1.0→1.5, Volsh → `dragon_dragon_blue.glb`,
Fly flying=1, Invisibility visibility=0 — with no server tracebacks.
