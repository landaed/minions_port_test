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
| **Form a party (alliance)** | ✅ works (now wired) | invite → accept → 2-member party; both clients show a party panel |
| **Buff another player** | ✅ works | A casts Blessed Armor on party member B → *"B is wrapped in a coat of pure light!"* |

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

## Party / alliance — now wired end to end

MoM's multi-player grouping is the **alliance** (up to 6 players;
`mob.player.party` is the *single* player's own 1–6 character party, a different
thing). The legacy server always implemented it; this pass wired it through the
proxy and built a Godot UI for it. Verified flow: A targets B → invites → B sees
a prompt → accepts → both clients show a 2-member party panel
(`tools/proxy_party_test.py` → `PARTY FORMED: PASS`, plus the screenshots).

What was added / fixed:

- **Proxy outbound commands** (`ClientProxy.py`): `invite` (legacy `INVITE`,
  invites your current target), and `accept_alliance` / `decline_alliance` /
  `leave_alliance` / `disband_alliance` → `PlayerAvatar.joinAlliance` /
  `leaveDecline` / `disband`.
- **`remote_checkIgnore`** (`ClientProxy.py`): `perspective_invite` first calls
  `target.mind.callRemote("checkIgnore", …)`; the proxy didn't implement it, so
  the call errbacked and the invite was silently dropped. Now returns `False`
  (not ignoring), so invites are delivered.
- **Alliance info forwarding** (`ClientProxy.py`): `remote_setAllianceInfo`
  flattens the `AllianceInfo` cacheable (PNAMES/NAMES/HEALTHS/MOBIDS) into a
  member list, and hooks `observe_updateChanged` so the **leader's** panel also
  updates when a new member joins (the join only pushes a fresh cacheable to the
  joiner). `remote_setAllianceInvite` forwards the inviter name.
- **Server bug fix** (`mud/world/alliance.py`): `Alliance.join` appended the
  `Character` *object* (not its name) to `masterAllianceInfo`, which PB then
  refused to jelly (*"Character deemed insecure"*), corrupting the member list.
  Now appends `…members[0].name`.
- **Godot UI** (`gameplay_view.gd`): a party panel (members + live health bars,
  Leave button), an invite prompt (Accept **Y** / Decline **N**), **G** to
  invite your target, and `alliance_info` / `alliance_invite` handling.

## Buff another player — verified

**Confirmed.** In a formed party, A (Cleric) targets B and casts **Blessed
Armor** → the server reports *"`<B>` is wrapped in a coat of pure light!"*, i.e.
the buff landed on the **other player** (`tools/proxy_party_test.py` →
`cross_party_heal=True`).

Things learned while verifying:

- **Spell target type matters.** Spells carry a `target` (SELF=0, PET=1,
  OTHER=2, PARTY=3, ALLIANCE=4). The Cleric's auto-learned **Minor Heal is
  self-target** — casting it heals the *caster* regardless of who's targeted, so
  it's the wrong spell to prove cross-player support. Player-targetable
  beneficial spells do exist (e.g. **Blessed Armor**, Light Heal, Words of
  Blessing, the Party/Alliance heals) — the test cheats one in and casts it.
- **The cast path is `spell_slot` → `onSpellSlot`**, using the spell's *grid
  slot* (not its list index), with the spellbook's `char_id`. It needs mana
  (cheat `full_heal` restores it) and you must wait out the spell's `cast_time`.
- **Staging combat damage in the start town is unreliable** — the test
  skeleton spawns next to powerful town **guards** that kill it (and kill any
  tester who swings at a guard), so a "heal restores HP" demo is best done with
  a buff (no damage needed) or in a quieter zone.

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
