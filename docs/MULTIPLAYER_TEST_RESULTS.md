# Multiplayer Verification — Results

This is a record of an end-to-end multiplayer test of the Godot port, run
headless on Linux (the same way it would run on a Windows desktop, just with a
software renderer instead of a GPU).

## How it was run

- **Servers:** the full Python stack via `./run_servers.sh` (Master / GM /
  Character / WorldDaemon / ClientProxy), Python 3.11, `MOM_ENABLE_CHEATS=1`.
- **Client:** real **Godot 4.6** game client (`minions-port/`), Forward+
  renderer on software Vulkan (Mesa **lavapipe**) under `xvfb`. Multiple
  independent client *processes* connect to the same proxy (`ws://localhost:9000`).
- **Drivers (automation):**
  - `minions-port/tools/multiplayer_driver.gd` — one per client process;
    registers its own account, creates a character, enters the world, then runs
    a role (observer / equip / summoner). Screenshots + a live
    `visible_players` dump per frame.
  - `minions-port/tools/autotest_driver.gd` — existing single-client tour
    (spawn → combat → NPC → inventory → spellbook → cheats → casting).
- **Headless protocol tests** (drive the proxy exactly like the client, no
  rendering — fast and deterministic): `tools/proxy_multiplayer_test.py`,
  `tools/mp_probe.py`, `tools/proxy_pet_test.py`, `tools/proxy_integration_test.py`,
  `tools/proxy_buff_test.py`.

## Summary table

| Feature | Status | Evidence |
|---|---|---|
| Register / login / create character / enter world | ✅ works | every run; `proxy_integration_test` |
| Walk around (server-authoritative + replicated) | ✅ works | ~24 snapshots/sec; positions replicate exactly |
| **Players see each other** | ✅ works | client A's target frame reads *"Bravoofm Lv 14 Player"*; `visible_players` lists the other player every frame |
| **One player sees another move** | ✅ works | `mp_probe`: A walks −275→−235; B's view of A updates to the same −235 |
| **Equipment/armour replication** | ✅ works | B equips sword+shield+helm → A's snapshot of B goes `mounts:1 → mounts:4`; shield visible on B in A's screenshot |
| Summoned pet follows the summoner | ✅ works | `proxy_pet_test`: pet stays at d≈2.5 as master moves; *"I will follow you master"* |
| Combat (aggro, melee, abilities, death) | ✅ works | skeleton aggros + attacks; Kick lands ~20 dmg; HP bars track |
| Cheats (level / items / spells / money / heal) | ✅ works | all cheat actions return success; gear auto-equips |
| **Buff/heal another player** | ⚠️ see "Buff" below | `proxy_buff_test` |
| **Form a party (alliance)** | ❌ not wired in the port | server has it; proxy + client UI don't expose it |

## What "see each other / equipment replication" looks like

Two client processes, **Alpha** (Ranger/Tempest) and **Bravo** (Warrior), enter
the same zone. They spawn on the same point; one walks a few units out. Each
client's per-frame log proves the replication independent of the screenshots:

```
[A] A_03_observe  visible_players=[Bravoofm(d=0,mounts=2)]   <- before B finishes equipping
[A] A_04_observe  visible_players=[Bravoofm(d=0,mounts=4)]   <- after  B equips shield+helm+sword
[B] B_04          visible_players=[Alpharly(d=10,mounts=1)]  <- B sees A 10 units away
```

`mounts` is the worn-equipment dict the server streams per entity
(`{0:primary hand, 1:off hand, 2:shield, 3:head}`). Watching it grow from 1→4
on **the other player's** avatar is the equipment-replication proof; the matching
screenshot shows Bravo holding the tower shield, with Alpha's target frame
reading "Bravoofm **Lv 14 Player**".

### Why this works (server side)

There is **one** `StubSimAvatar` per zone (`zone.simAvatar`). Every player who
enters is added to its shared sim-object list (`create_player_sim_object` →
`addSimObject`), and `_updateCanSee` computes visibility for all of them within a
500-unit radius. `PlayerAvatar.perspective_getVisibleEntities` then returns the
other players with `is_player:true` plus their `mounts`/`tex` (armour), so any
client polling it sees every other nearby player, their live position, and their
current gear. Equip/unequip invalidates the cached `mob._godot_mounts`/`_godot_tex`,
so a gear change shows up on everyone's next snapshot.

## Party / alliance — not wired through the port

MoM's multi-player grouping is the **alliance** (up to 6 players;
`mob.player.party` is the *single* player's own 1–6 character party, a different
thing). The legacy server fully implements it: `CmdInvite` →
`PlayerAvatar.perspective_invite()` (invite your targeted player),
`perspective_joinAlliance()`, and the proxy even *receives* `setAllianceInvite`
and forwards an `alliance_invite` message to the client.

What's missing is the **outbound** path: the proxy's `gameplay_command` map has
no `invite` / `accept_alliance` command, and the Godot client has no
party/alliance UI (only debug labels that print the current party). So two
players cannot currently form a group from the client. This is a port gap, not a
server limitation — wiring it is a small, well-scoped task (add `INVITE` +
accept to the proxy command map and a couple of buttons/inbox to the HUD).

## Buff / heal another player

**Partly verified — building blocks work, clean end-to-end not captured.**

- A Cleric does get a beneficial spell (`Minor Heal`) in its spellbook.
- Spell casting works in general — the **summon** is a spell cast through the
  same `spell_slot` → `onSpellSlot` path, and it succeeds.
- Targeting another player works (A's target frame reads "Bravoofm Lv 14
  Player").

What I could **not** cleanly demonstrate was a heal *landing on another player
and restoring their HP*: the headless harness couldn't reliably get the target
damaged first (sending `attack` alone doesn't always pull the attacker into
melee range to take return damage), and a heal on a full-HP target is a no-op
with no log line, so there was nothing to measure. The mechanic almost
certainly works (it's core original-game behaviour and every prerequisite is
functional), but treat "buff/heal each other" as **likely-works /
not-proven-here** rather than confirmed.

Note also that beneficial support between players may be gated by the same
**missing alliance wiring** (below) — in the original game you typically buff
your own party/alliance — so a fuller fix is: wire alliances, then re-test
cross-player heals/buffs inside a group. `tools/proxy_buff_test.py` is the
harness to finish this with.

## Reproduce

```bash
./run_servers.sh --setup            # once
./run_servers.sh                    # start the stack

# headless (fast, deterministic):
python3 tools/proxy_multiplayer_test.py     # 2 clients: see each other + equipment
python3 tools/proxy_pet_test.py             # summon follows
python3 tools/proxy_buff_test.py            # heal/buff another player

# real Godot client (needs a display; xvfb + lavapipe works headless):
#   download Godot 4.6, then per client process:
MOM_MP_NAME=Bravo MOM_MP_CLASS=Warrior MOM_MP_ROLE=equip \
MOM_SHOT_DIR=/tmp/b MOM_SHOT_PREFIX=B \
  xvfb-run -a godot --path minions-port \
    --script res://tools/multiplayer_driver.gd --resolution 1280x720
# (run a second process with ROLE=observer to watch the first)
```
