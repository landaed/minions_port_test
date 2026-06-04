#!/usr/bin/env python3
"""Headless combat integration test: drives the ClientProxy WebSocket exactly
like the Godot client, enters the world, targets the test skeleton, toggles
auto-attack, optionally fires abilities, and tracks both the player's and the
skeleton's health over time so we can verify the player can actually harm /
kill the mob.

Run the server stack first (./run_servers.sh), then:
    python3 tools/proxy_combat_test.py
"""
import asyncio, json, sys, time, random, string

import websockets

_suffix = "".join(random.choice(string.ascii_lowercase) for _ in range(5))

URI = "ws://localhost:9000"
USER = "Fighter" + str(int(time.time()) % 100000)
EMAIL = USER.lower() + "@example.com"
CHOSEN_PASSWORD = "mychosenpw"
CHARNAME = "Smash" + _suffix
RACE = "Human"
KLASS = "Warrior"

# How long to keep attacking before giving up (seconds)
COMBAT_DURATION = 150.0

state = {
    "password": None,
    "world": None,
    "world_pw": None,
    "entered": False,
    "char_created": False,
    "enter_sent": False,
    "abilities": [],          # ability dicts from char_infos
    "self_hp": None,          # (hp, maxhp)
    "mob": {},                # mob_id -> latest entity dict
    "target_id": 0,
    "phase": "idle",
}


def log(*a):
    print("[COMBAT]", *a)
    sys.stdout.flush()


async def send(ws, **msg):
    await ws.send(json.dumps(msg))
    t = msg.get("type")
    if t == "gameplay_command":
        log("->", t, msg.get("command"), {k: v for k, v in msg.items() if k not in ("type", "command")})
    else:
        log("->", t)


def parse_entities(ents):
    """Update self HP and the nearest hostile mob's HP from a snapshot."""
    self_pos = None
    for e in ents:
        if e.get("is_self"):
            self_pos = e.get("position")
            state["self_pos"] = self_pos
            state["self_hp"] = (e.get("health"), e.get("max_health"))
    nearest = None
    for e in ents:
        if e.get("is_self"):
            continue
        d = e.get("distance", 9e9)
        if nearest is None or d < nearest.get("distance", 9e9):
            nearest = e
        state["mob"][e.get("id")] = e
    return self_pos, nearest


def hp_str(hp_tuple):
    if not hp_tuple or hp_tuple[0] is None:
        return "?"
    return "%.0f/%.0f" % (hp_tuple[0], hp_tuple[1])


async def run():
    async with websockets.connect(URI, max_size=4_000_000) as ws:
        await send(ws, type="register", username=USER, email=EMAIL, password=CHOSEN_PASSWORD)
        combat_task = None
        t0 = time.time()
        deadline = t0 + 30 + COMBAT_DURATION
        while time.time() < deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
            except asyncio.TimeoutError:
                continue
            data = json.loads(raw)
            mt = data.get("type", "")

            if mt not in ("entity_snapshot", "world_time", "gameplay_state"):
                # surface combat-relevant chatter
                if mt in ("game_text", "text_messages", "gameplay_command_result",
                          "set_selection", "mouse_select", "target_description"):
                    log("<-", mt, {k: data[k] for k in data if k != "type"})
                else:
                    log("<-", mt, {k: data[k] for k in data if k not in ("type", "characters", "worlds", "entities", "char_infos")})

            if mt == "register_result":
                if data.get("success"):
                    state["password"] = data.get("password")
                    await send(ws, type="login", username=USER, password=state["password"])
                else:
                    log("register failed:", data.get("message")); return

            elif mt == "login_result":
                if not data.get("success"):
                    log("login failed:", data.get("message")); return

            elif mt == "world_list":
                worlds = data.get("worlds", [])
                if not worlds:
                    continue
                w = worlds[0]
                state["world"] = w
                await send(ws, type="select_world", world_name=w["name"],
                           ip=w["ip"], port=w["port"], has_password=w.get("has_password", False))

            elif mt == "world_account_result":
                if data.get("success"):
                    state["world_pw"] = data.get("world_password")
                    await send(ws, type="world_login", world_password=state["world_pw"], role="Player")

            elif mt == "world_password_result":
                if data.get("success") and data.get("world_password"):
                    state["world_pw"] = data.get("world_password")
                    await send(ws, type="world_login", world_password=state["world_pw"], role="Player")

            elif mt == "character_list":
                chars = data.get("characters", [])
                log("CHARACTERS:", [c.get("name") for c in chars])
                if chars and not state["enter_sent"]:
                    state["enter_sent"] = True
                    await send(ws, type="enter_world", character_name=chars[0]["name"])
                elif not chars and not state["char_created"]:
                    state["char_created"] = True
                    await send(ws, type="create_character", name=CHARNAME,
                               race=RACE, klass=KLASS, sex="Male", look=0, realm=1)

            elif mt == "create_character_result":
                if data.get("success"):
                    if not state["enter_sent"]:
                        state["enter_sent"] = True
                        await send(ws, type="enter_world", character_name=CHARNAME)
                else:
                    log("create char failed:", data.get("message")); return

            elif mt in ("root_info", "gameplay_state"):
                # capture abilities from char_infos
                cis = data.get("char_infos", [])
                if cis and isinstance(cis[0], dict):
                    abil = cis[0].get("abilities", [])
                    if abil:
                        state["abilities"] = abil
                if not state["entered"]:
                    state["entered"] = True
                    log("ENTERED WORLD as %s %s." % (RACE, KLASS))
                    combat_task = asyncio.create_task(combat_loop(ws))

            elif mt == "entity_snapshot":
                ents = data.get("entities", [])
                _, nearest = parse_entities(ents)
                if nearest:
                    state["nearest_id"] = nearest.get("id")
                    state["nearest_dist"] = nearest.get("distance")

        log("=== DONE ===")
        summarize()


async def combat_loop(ws):
    await asyncio.sleep(2.0)
    log("Abilities reported by server:", [a.get("name") for a in state["abilities"]],
        "(source=%s)" % (state["abilities"][0].get("source") if state["abilities"] else "none"))

    # 1) Target the skeleton specifically (click-to-target by entity id).
    skel = _find_skeleton()
    if skel:
        log(">>> TARGET skeleton id=%s via target_entity (click)" % skel.get("id"))
        await send(ws, type="gameplay_command", command="target_entity", entity_id=int(skel.get("id")))
    else:
        log(">>> No skeleton in snapshot yet; falling back to cycle_target (TAB)")
        await send(ws, type="gameplay_command", command="cycle_target")
    await asyncio.sleep(1.5)

    # 1b) Face + step toward the skeleton so the server-side isFacing check
    #     passes (melee attacks are inhibited if you're not facing the target).
    await _face_and_approach(ws)

    # 2) Toggle auto-attack ON (Q)
    log(">>> ATTACK toggle (Q)")
    await send(ws, type="gameplay_command", command="attack_toggle")
    await asyncio.sleep(0.5)

    # Snapshot starting HP
    start = _mob_hp_snapshot()
    log("Start HP — self=%s  skeleton=%s" % (hp_str(state["self_hp"]), start))

    # 3) Watch melee for a while; re-target periodically in case aggro shifts.
    interval = 3.0
    elapsed = 0.0
    fired_abilities = False
    while elapsed < COMBAT_DURATION:
        await asyncio.sleep(interval)
        elapsed += interval
        # Keep facing the skeleton (it may drift); melee needs isFacing() true.
        skel0 = _find_skeleton()
        sp0 = state.get("self_pos")
        if skel0 and sp0:
            tp = skel0.get("position")
            dx, dy = tp[0] - sp0[0], tp[1] - sp0[1]
            mag = (dx * dx + dy * dy) ** 0.5 or 1.0
            await ws.send(json.dumps({
                "type": "gameplay_command", "command": "player_input",
                "move_x": 0.0, "move_y": 0.0, "forward": [dx / mag, dy / mag, 0.0], "jump": False,
            }))
        nearest = _find_skeleton()
        log("t+%4.0fs  self=%s  skeleton=%s  dist=%s  attacking_self=%s" % (
            elapsed, hp_str(state["self_hp"]),
            _mob_hp_snapshot(),
            ("%.1f" % nearest.get("distance")) if nearest else "?",
            nearest.get("attacking") if nearest else "?"))

        # Fire every active ability each round; the server enforces cooldowns,
        # so repeated calls while on reuse are harmless. This grinds the mob
        # down with auto-attack + abilities (e.g. Kick) to verify a full kill.
        for ab in state["abilities"]:
            name = ab.get("name")
            if ab.get("source") != "server":
                continue
            await send(ws, type="gameplay_command", command="use_ability", ability_name=name)
            await asyncio.sleep(0.3)
        fired_abilities = True

        # Stop early if the skeleton is dead.
        if nearest and nearest.get("dead"):
            log("*** Skeleton reported DEAD — combat success ***")
            break
        m = _mob_hp_snapshot_val()
        if m is not None and m <= 0:
            log("*** Skeleton HP <= 0 — combat success ***")
            break


async def _face_and_approach(ws, steps=6):
    """Send player_input that faces and walks toward the skeleton in server coords.

    Snapshot positions are server coords (Z-up). 'forward' is a server-space
    direction vector; move_y=1 walks along it. This makes the server set the
    player's rotation toward the skeleton so isFacing() passes.
    """
    for _ in range(steps):
        skel = _find_skeleton()
        sp = state.get("self_pos")
        if skel and sp:
            tp = skel.get("position")
            dx = tp[0] - sp[0]
            dy = tp[1] - sp[1]
            mag = (dx * dx + dy * dy) ** 0.5 or 1.0
            forward = [dx / mag, dy / mag, 0.0]
            await ws.send(json.dumps({
                "type": "gameplay_command", "command": "player_input",
                "move_x": 0.0, "move_y": 1.0, "forward": forward, "jump": False,
            }))
        await asyncio.sleep(0.4)
    # stop moving but keep facing
    skel = _find_skeleton()
    sp = state.get("self_pos")
    if skel and sp:
        tp = skel.get("position")
        dx, dy = tp[0] - sp[0], tp[1] - sp[1]
        mag = (dx * dx + dy * dy) ** 0.5 or 1.0
        await ws.send(json.dumps({
            "type": "gameplay_command", "command": "player_input",
            "move_x": 0.0, "move_y": 0.0, "forward": [dx / mag, dy / mag, 0.0], "jump": False,
        }))


def _find_skeleton():
    """Prefer the actual test Skeleton; fall back to nearest mob."""
    skels = [e for e in state["mob"].values() if "skeleton" in str(e.get("name", "")).lower()]
    if skels:
        return min(skels, key=lambda e: e.get("distance", 9e9))
    return _nearest_mob()


def _nearest_mob():
    best = None
    for e in state["mob"].values():
        d = e.get("distance", 9e9)
        if best is None or d < best.get("distance", 9e9):
            best = e
    return best


def _mob_hp_snapshot():
    m = _find_skeleton()
    if not m:
        return "?"
    return "%.0f/%.0f%s" % (m.get("health", 0), m.get("max_health", 0),
                            " DEAD" if m.get("dead") else "")


def _mob_hp_snapshot_val():
    m = _find_skeleton()
    if not m:
        return None
    return m.get("health")


def summarize():
    log("Final self HP:", hp_str(state["self_hp"]))
    log("Final skeleton HP:", _mob_hp_snapshot())
    log("Abilities:", [(a.get("name"), a.get("source")) for a in state["abilities"]])


if __name__ == "__main__":
    asyncio.run(run())
