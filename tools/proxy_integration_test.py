#!/usr/bin/env python3
"""Headless integration test: drives the ClientProxy WebSocket exactly like the
Godot client would, all the way into the world, then moves the player and logs
whether the nearest mob follows. Used to debug AI-following / coordinate issues.
"""
import asyncio, json, sys, time, math, random, string
import websockets

_suffix = "".join(random.choice(string.ascii_lowercase) for _ in range(4))

URI = "ws://localhost:9000"
USER = "Tester" + str(int(time.time()) % 100000)
EMAIL = USER.lower() + "@example.com"
CHOSEN_PASSWORD = "mychosenpw"   # tests the account-password override
WORLD_ACCESS_PW = "mmo"          # serverconfig PLAYERPASSWORD
FANTASY = "Hero" + _suffix
CHARNAME = "Bonk" + _suffix

state = {
    "password": None,            # master account pw (assigned)
    "world": None,
    "world_pw": None,            # per-world account pw
    "snapshots": [],             # (t, self_pos, nearest_mob_id, nearest_mob_pos, nearest_dist)
    "entered": False,
    "char_created": False,
}

def log(*a):
    print("[TEST]", *a); sys.stdout.flush()

async def send(ws, **msg):
    await ws.send(json.dumps(msg))
    log("-> ", msg.get("type"), {k: v for k, v in msg.items() if k != "type"})

def nearest_mob(entities):
    self_pos = None
    best = None
    for e in entities:
        if e.get("is_self"):
            self_pos = e.get("position")
    for e in entities:
        if e.get("is_self"):
            continue
        d = e.get("distance", 9e9)
        if best is None or d < best[3]:
            best = (e.get("id"), e.get("name"), e.get("position"), d)
    return self_pos, best

async def run():
    async with websockets.connect(URI, max_size=4_000_000) as ws:
        await send(ws, type="register", username=USER, email=EMAIL, password=CHOSEN_PASSWORD)
        move_task = None
        t0 = time.time()
        deadline = t0 + 32
        while time.time() < deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
            except asyncio.TimeoutError:
                # Nudge the flow forward if stuck
                continue
            data = json.loads(raw)
            mt = data.get("type", "")
            if mt not in ("entity_snapshot", "gameplay_state", "world_time", "game_text"):
                log("<- ", mt, {k: data[k] for k in data if k not in ("type", "characters", "worlds", "entities")})

            if mt == "register_result":
                if data.get("success"):
                    state["password"] = data.get("password")
                    chose_ok = (state["password"] == CHOSEN_PASSWORD)
                    log("ACCOUNT PASSWORD returned:", state["password"],
                        "(chosen-password override %s)" % ("WORKED" if chose_ok else "did NOT take"))
                    await send(ws, type="login", username=USER, password=state["password"])
                else:
                    log("register failed:", data.get("message")); return

            elif mt == "login_result":
                if not data.get("success"):
                    log("login failed:", data.get("message")); return
                # proxy auto-sends world_list next

            elif mt == "world_list":
                worlds = data.get("worlds", [])
                log("WORLDS:", [(w["name"], w["ip"], w["port"]) for w in worlds])
                if not worlds:
                    continue
                w = worlds[0]
                state["world"] = w
                await send(ws, type="select_world", world_name=w["name"],
                           ip=w["ip"], port=w["port"], has_password=w.get("has_password", False))

            elif mt == "world_connected":
                if not data.get("success"):
                    log("world connect failed:", data.get("message")); return
                if data.get("has_world_account"):
                    # will receive world_password_result; just wait
                    pass
                else:
                    await send(ws, type="create_world_account",
                               fantasy_name=FANTASY, player_password=WORLD_ACCESS_PW)

            elif mt == "world_account_result":
                if data.get("success"):
                    state["world_pw"] = data.get("world_password")
                    log("WORLD ACCOUNT PASSWORD:", state["world_pw"])
                    await send(ws, type="world_login", world_password=state["world_pw"], role="Player")
                else:
                    log("world account failed:", data.get("message")); return

            elif mt == "world_password_result":
                if data.get("success") and data.get("world_password"):
                    state["world_pw"] = data.get("world_password")
                    await send(ws, type="world_login", world_password=state["world_pw"], role="Player")

            elif mt == "player_login_result":
                if not data.get("success"):
                    log("player login failed:", data.get("message")); return
                # character_list will follow

            elif mt == "character_list":
                chars = data.get("characters", [])
                log("CHARACTERS:", [c.get("name") for c in chars])
                if chars:
                    await send(ws, type="enter_world", character_name=chars[0]["name"])
                elif not state["char_created"]:
                    state["char_created"] = True
                    await send(ws, type="create_character", name=CHARNAME,
                               race="Human", klass="Warrior", sex="Male", look=0, realm=1)

            elif mt == "create_character_result":
                if data.get("success"):
                    await send(ws, type="enter_world", character_name=CHARNAME)
                else:
                    log("create char failed:", data.get("message")); return

            elif mt in ("root_info", "gameplay_state"):
                if not state["entered"]:
                    state["entered"] = True
                    log("ENTERED WORLD. Beginning movement test in 3s...")
                    move_task = asyncio.create_task(move_loop(ws))

            elif mt == "entity_snapshot":
                ents = data.get("entities", [])
                self_pos, best = nearest_mob(ents)
                state["snapshots"].append((round(time.time()-t0,2), self_pos,
                                           best[0] if best else None,
                                           best[2] if best else None,
                                           round(best[3],2) if best else None))

        log("=== DONE. Captured", len(state["snapshots"]), "snapshots ===")
        summarize()

async def move_loop(ws):
    """Move forward 5s (to provoke aggro/pursuit), then STOP and stand for 16s
    so we can see whether mobs close the gap and reach the player."""
    await asyncio.sleep(3)
    forward = [0.0, 1.0, 0.0]   # server +Y forward
    log(">>> MOVING FORWARD for 5s")
    end = time.time() + 5
    while time.time() < end:
        await ws.send(json.dumps({"type": "gameplay_command", "command": "player_input",
                                  "move_x": 0.0, "move_y": 1.0, "forward": forward, "jump": False}))
        await asyncio.sleep(0.05)
    log(">>> STOP; standing still to watch mobs close in")
    end = time.time() + 16
    while time.time() < end:
        await ws.send(json.dumps({"type": "gameplay_command", "command": "player_input",
                                  "move_x": 0.0, "move_y": 0.0, "forward": forward, "jump": False}))
        await asyncio.sleep(0.05)

def summarize():
    log("time | self_pos | nearest_mob | mob_pos | dist")
    last = None
    for t, sp, mid, mp, d in state["snapshots"]:
        # Only print when something changed meaningfully
        sp_s = "(%.1f,%.1f,%.1f)" % tuple(sp) if sp else "None"
        mp_s = "(%.1f,%.1f,%.1f)" % tuple(mp) if mp else "None"
        print("   %5.1f  self=%-22s mob#%s=%-22s d=%s" % (t, sp_s, mid, mp_s, d))
        sys.stdout.flush()

if __name__ == "__main__":
    asyncio.run(run())
