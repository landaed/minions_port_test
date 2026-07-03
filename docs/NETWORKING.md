# Networking: what goes over the wire, when, and why

The Godot client never talks to the MoM servers directly. Everything rides one
WebSocket to `ClientProxy.py` (port 9000), which translates JSON to Twisted PB
calls against the master/world servers:

```
Godot client  <—JSON/WebSocket—>  ClientProxy.py  <—Twisted PB—>  world server stack
```

## Client → server (sending)

| Message | Cadence | Notes |
| --- | --- | --- |
| `player_input` (move vector, facing, jump, floor height) | every 50 ms **only while it changes** | deduped against the last-sent state, so standing still costs zero |
| `gameplay_command` (interact, attack, hotbar, loot, dialog, …) | event-driven one-offs | direct result of a click/keypress |
| login / world / character flow messages | one-offs | register, login, select world, enter world, … |

## Server → client (receiving)

| Message | Cadence | Notes |
| --- | --- | --- |
| `entity_snapshot` | ~13 Hz poll (`MOM_ENTITY_SYNC_INTERVAL`, default 0.075 s) | the big one — see below |
| `gameplay_state` (HP/MP/XP, char sheet, party) | 0.25 s poll, sent **only when changed** | payload-compared against the last send |
| active skills / cooldowns | 1 s poll | ability bar reuse timers |
| `world_time` | 60 s push | drives the day/night sky |
| text, inventory, loot, spellbook, vendor, dialog, VFX events | event-driven one-offs | VFX events piggyback on `entity_snapshot` |

So: the two **interval** streams are entity snapshots (13 Hz) and gameplay
state (4 Hz, change-gated); everything else is **trigger/one-shot**.

## The entity stream, layer by layer

The entity snapshot is the only stream that is allowed to be expensive, and it
has three cost-cutting layers:

1. **World server, activity-driven build** (`playeravatar.getVisibleEntities`,
   `MOM_ENTITY_ACTIVITY_DRIVEN=1`): per player, an entity is only *built* when
   its dynamic signature (position/rotation/health/target/flags) changed since
   the last poll. Idle mobs cost ~zero CPU. Despawns are reported explicitly in
   a `removed` list; a full rebuild happens every `MOM_ENTITY_RESYNC` (2 s) so
   drift self-heals.
2. **Proxy, static/dynamic delta compression** (`ClientProxy`): per entity,
   static identity (name/model/race/appearance/equipment/level) is sent once,
   then only the dynamic remainder; totally unchanged entities shrink to an
   `{id, sim_id}` heartbeat. Full static resync every 4 s
   (`MOM_ENTITY_STATIC_RESYNC`). Floats are rounded (1 cm / ~0.06°).
3. **Client, render-behind interpolation** (`gameplay_view`): each snapshot is
   timestamped into a per-entity sample buffer and the entity is drawn at
   `now − 0.12 s`, lerped between bracketing samples — smooth motion despite
   13 Hz updates and network jitter. The local player uses client-side
   prediction plus a smoothed reconcile toward the server position.

### Range: why mobs used to pop in "super close"

Two different radii were fighting each other:

* the proxy forwarded entities within `MOM_ENTITY_STREAM_RADIUS` (was 120 u),
* but the world server **hard-capped its build range at 60 u**
  (`SNAPSHOT_MAX_RANGE`, with a comment still describing an even older 50 u
  proxy bubble), so nothing past 60 u ever reached the client.

Both ends now read the same `MOM_ENTITY_STREAM_RADIUS` knob (default **250 u**;
server adds a 10 u margin). Zone fog starts at 500 u, so a 250 u stream fills
the visible mid-ground. The AI/visibility sweep (`canSee`) was already 500 u,
and the activity-driven layers keep the wider bubble cheap: a distant idle mob
costs one full record when first seen, then approximately nothing until it
moves. The per-snapshot payload cap is `MOM_ENTITY_STREAM_LIMIT` (default 64,
nearest-first), which bounds worst-case bandwidth regardless of radius.

### Knobs (env vars, read at server start)

| Var | Default | Meaning |
| --- | --- | --- |
| `MOM_ENTITY_STREAM_RADIUS` | 250 | stream radius in world units (proxy filter + server build range) |
| `MOM_ENTITY_STREAM_LIMIT` | 64 | max entities per snapshot (nearest first, self always included) |
| `MOM_ENTITY_SYNC_INTERVAL` | 0.075 | seconds between snapshot polls per client |
| `MOM_ENTITY_RESYNC` | 2.0 | world-server full-rebuild period |
| `MOM_ENTITY_STATIC_RESYNC` | 4.0 | proxy static-field resend period |
| `MOM_ENTITY_ACTIVITY_DRIVEN` | 1 | set 0 for legacy "send everything every poll" |
| `MOM_ENTITY_DELTA` / `MOM_ENTITY_ROUND` | 1 | proxy delta compression / float rounding toggles |

The proxy logs `entity replication: X snapshots/sec, Y KB/sec to client` every
5 s, so regressions are visible at a glance.

## Assessment / possible next steps

The poll-based snapshot (client-agnostic pull at 13 Hz) is simple and, with the
three layers above, cheap in the common case. If it ever needs to scale
further, the obvious candidates are, in order of value:

* push snapshots from the world server on its own tick instead of per-client
  PB polls (halves the PB round-trips);
* distance-tiered update rates (a mob 200 u away doesn't need 13 Hz);
* hysteresis on the nearest-N cap so entities at the boundary don't flicker
  in/out of the stream in very crowded zones;
* a binary encoding (the JSON keys dominate small dynamic records).
