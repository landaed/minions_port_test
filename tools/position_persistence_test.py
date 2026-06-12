#!/usr/bin/env python3
"""Reproduce the 'log back in where you logged out' bug:
phase 1: register -> create char -> enter -> MOVE for a few seconds -> disconnect
phase 2: reconnect -> enter same char -> compare spawn position with logout position.

Pass --phase2-only to skip registration/creation (e.g. after a server restart) and
just log back in with credentials saved in /tmp/pos_persist_creds.json.
"""
import asyncio, json, sys, time, random, string

import websockets

URI = "ws://localhost:9000"
CREDS_FILE = "/tmp/pos_persist_creds.json"

def log(*a): print("[POSTEST]", *a); sys.stdout.flush()

async def drive(label, register, creds, move_seconds=5.0, settle_seconds=2.0,
                create_if_missing=None):
    """Run the full flow. If move_seconds > 0, hold forward input that long.
    Returns (first_self_pos, last_self_pos) observed while in world."""
    if create_if_missing is None:
        create_if_missing = register
    first_pos = None
    last_pos = None
    got_root = False
    async with websockets.connect(URI, max_size=4_000_000) as ws:
        async def send(**m): await ws.send(json.dumps(m))
        if register:
            await send(type="register", username=creds["user"], email=creds["user"].lower() + "@ex.com", password=creds["pw"])
        else:
            await send(type="login", username=creds["user"], password=creds["pw"])
        deadline = time.time() + 40
        move_until = None
        move_task_started = False

        async def mover():
            # ~20 Hz forward input like the Godot client, then a stop input.
            t_end = time.time() + move_seconds
            while time.time() < t_end:
                await send(type="gameplay_command", command="player_input",
                           move_x=0.0, move_y=1.0, forward=[0.0, 1.0, 0.0], jump=False)
                await asyncio.sleep(0.05)
            await send(type="gameplay_command", command="player_input",
                       move_x=0.0, move_y=0.0, forward=[0.0, 1.0, 0.0], jump=False)
            log(label, "movement finished; settling", settle_seconds, "s")
            await asyncio.sleep(settle_seconds)

        mover_task = None
        while time.time() < deadline:
            if got_root and mover_task is not None and mover_task.done():
                break
            try:
                data = json.loads(await asyncio.wait_for(ws.recv(), timeout=2))
            except asyncio.TimeoutError:
                continue
            mt = data.get("type", "")
            if mt == "register_result":
                if data.get("success"):
                    await send(type="login", username=creds["user"], password=creds["pw"])
                else:
                    log(label, "register FAILED:", data.get("message")); return None
            elif mt == "login_result":
                if not data.get("success"):
                    log(label, "login FAILED:", data.get("message")); return None
            elif mt == "world_list":
                ws_ = data.get("worlds", [])
                if ws_:
                    w = ws_[0]
                    await send(type="select_world", world_name=w["name"], ip=w["ip"],
                               port=w["port"], has_password=w.get("has_password", False))
            elif mt == "world_account_result" and data.get("success"):
                await send(type="world_login", world_password=data.get("world_password"), role="Player")
            elif mt == "world_password_result" and data.get("success") and data.get("world_password"):
                await send(type="world_login", world_password=data.get("world_password"), role="Player")
            elif mt == "player_login_result":
                if not data.get("success"):
                    log(label, "world login FAILED:", data.get("message")); return None
            elif mt == "character_list":
                chars = data.get("characters", [])
                names = [c.get("name") for c in chars]
                log(label, "characters:", names)
                if creds["char"] in names:
                    await send(type="enter_world", character_name=creds["char"])
                elif create_if_missing:
                    await send(type="create_character", name=creds["char"], race="Human",
                               klass="Paladin", sex="Male", look=0, realm=1)
                else:
                    log(label, "existing char not found!"); return None
            elif mt == "create_character_result":
                if data.get("success"):
                    await send(type="enter_world", character_name=creds["char"])
                else:
                    log(label, "create char FAILED:", data.get("message")); return None
            elif mt == "enter_world_result" and not data.get("success", True):
                log(label, "enter_world FAILED:", data.get("message")); return None
            elif mt == "root_info":
                got_root = True
                log(label, "*** root_info RECEIVED — in world ***")
                if mover_task is None:
                    mover_task = asyncio.ensure_future(mover()) if move_seconds > 0 else asyncio.ensure_future(asyncio.sleep(settle_seconds))
            elif mt == "entity_snapshot":
                for e in data.get("entities", []):
                    if isinstance(e, dict) and e.get("is_self"):
                        pos = e.get("position")
                        if pos:
                            if first_pos is None:
                                first_pos = list(pos)
                                log(label, "first self pos:", ["%.1f" % p for p in first_pos])
                            last_pos = list(pos)
            elif mt == "error":
                log(label, "ERROR:", data.get("message"))
        if mover_task is not None and not mover_task.done():
            mover_task.cancel()
    if not got_root:
        log(label, "NEVER got root_info!")
        return None
    log(label, "last self pos:", ["%.1f" % p for p in (last_pos or [])])
    return (first_pos, last_pos)

async def main():
    phase2_only = "--phase2-only" in sys.argv
    if phase2_only:
        with open(CREDS_FILE) as f:
            creds = json.load(f)
        log("PHASE 2 ONLY: re-login as", creds["user"], "char", creds["char"])
        r2 = await drive("phase2", register=False, creds=creds, move_seconds=0)
        if r2 is None:
            log("RESULT: PHASE2 FAILED (could not enter world)")
            return
        first2, _ = r2
        log("RESULT: spawn pos after restart:", ["%.1f" % p for p in (first2 or [])])
        if "expect" in creds and first2:
            exp = creds["expect"]
            d = sum((a - b) ** 2 for a, b in zip(first2, exp)) ** 0.5
            log("RESULT: distance from logout pos: %.1f -> %s" % (d, "OK (persisted)" if d < 5 else "BUG (reset to spawn)"))
        return

    suf = "".join(random.choice(string.ascii_lowercase) for _ in range(5))
    creds = {"user": "Pos" + suf, "pw": "pospw12345", "char": "Walker" + suf}
    log("PHASE 1: register + create + enter + walk 5s as", creds["user"])
    r1 = await drive("phase1", register=True, creds=creds, move_seconds=5.0)
    if r1 is None:
        log("RESULT: PHASE1 FAILED"); return
    first1, last1 = r1
    moved = sum((a - b) ** 2 for a, b in zip(first1, last1)) ** 0.5 if (first1 and last1) else 0
    log("phase1 moved %.1f units" % moved)
    creds["expect"] = last1
    with open(CREDS_FILE, "w") as f:
        json.dump(creds, f)
    await asyncio.sleep(4)  # let server-side logout/cleanup settle
    log("PHASE 2: reconnect + re-enter SAME character")
    r2 = await drive("phase2", register=False, creds=creds, move_seconds=0)
    if r2 is None:
        log("RESULT: PHASE2 FAILED (could not re-enter)"); return
    first2, _ = r2
    d_spawn = sum((a - b) ** 2 for a, b in zip(first2, first1)) ** 0.5
    d_logout = sum((a - b) ** 2 for a, b in zip(first2, last1)) ** 0.5
    log("spawn-after-relogin distance from ORIGINAL SPAWN: %.1f, from LOGOUT POS: %.1f" % (d_spawn, d_logout))
    if d_logout < 5:
        log("RESULT: POSITION PERSISTED OK")
    else:
        log("RESULT: POSITION BUG REPRODUCED (respawned at original spawn, not logout position)")

# --- second-character mode ---------------------------------------------------
# Usage: python3 tools/position_persistence_test.py --second-char
# After a normal run (creds in /tmp/pos_persist_creds.json with a walked-out
# position), log into the SAME account, create a NEW character, enter, and
# verify it spawns at the start point rather than the first character's spot.
async def second_char():
    with open(CREDS_FILE) as f:
        creds = json.load(f)
    second = dict(creds)
    second["char"] = "Newbie" + "".join(random.choice(string.ascii_lowercase) for _ in range(4))
    log("SECOND CHAR: same account", second["user"], "new char", second["char"])
    r = await drive("second", register=False, creds=second, move_seconds=0,
                    create_if_missing=True)
    if r is None:
        log("RESULT: SECOND-CHAR FAILED (could not enter)")
        return
    first, _ = r
    d_old = sum((a - b) ** 2 for a, b in zip(first, creds["expect"])) ** 0.5
    log("new char spawn:", ["%.1f" % p for p in first],
        "| distance from other char's logout pos: %.1f" % d_old)
    log("RESULT:", "OK (fresh start point)" if d_old > 5 else "BUG (inherited other character's position)")


if __name__ == "__main__":
    if "--second-char" in sys.argv:
        asyncio.run(second_char())
    else:
        asyncio.run(main())
