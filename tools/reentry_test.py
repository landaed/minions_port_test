#!/usr/bin/env python3
"""Reproduce the 're-enter an existing character' path: do the full flow once
(register -> create char -> enter), then DISCONNECT and reconnect and enter the
SAME character again. Reports whether root_info arrives each time."""
import asyncio, json, sys, time, random, string
import websockets

URI = "ws://localhost:9000"
suf = "".join(random.choice(string.ascii_lowercase) for _ in range(5))
USER = "Reent" + suf
EMAIL = USER.lower() + "@ex.com"
PW = "reentpw123"
FANTASY = "Hero" + suf
CHARNAME = "Char" + suf
WORLD_ACCESS_PW = "mmo"

def log(*a): print("[REENTRY]", *a); sys.stdout.flush()

async def phase(label, register):
    """Run the flow; return True if root_info (world load) was received."""
    got_root = False
    world_pw = None
    async with websockets.connect(URI, max_size=4_000_000) as ws:
        async def send(**m): await ws.send(json.dumps(m))
        if register:
            await send(type="register", username=USER, email=EMAIL, password=PW)
        else:
            await send(type="login", username=USER, password=PW)
        deadline = time.time() + 25
        while time.time() < deadline and not got_root:
            try:
                data = json.loads(await asyncio.wait_for(ws.recv(), timeout=2))
            except asyncio.TimeoutError:
                continue
            mt = data.get("type", "")
            if mt == "register_result" and data.get("success"):
                await send(type="login", username=USER, password=PW)
            elif mt == "login_result":
                if not data.get("success"):
                    log(label, "login FAILED:", data.get("message")); return False
            elif mt == "world_list":
                ws_ = data.get("worlds", [])
                if ws_:
                    w = ws_[0]
                    await send(type="select_world", world_name=w["name"], ip=w["ip"],
                               port=w["port"], has_password=w.get("has_password", False))
            elif mt == "world_connected":
                pass  # proxy auto-handles world account -> player_login_result
            elif mt == "world_account_result" and data.get("success"):
                world_pw = data.get("world_password")
                await send(type="world_login", world_password=world_pw, role="Player")
            elif mt == "world_password_result" and data.get("success") and data.get("world_password"):
                world_pw = data.get("world_password")
                await send(type="world_login", world_password=world_pw, role="Player")
            elif mt == "player_login_result":
                if not data.get("success"):
                    log(label, "world login FAILED:", data.get("message")); return False
            elif mt == "character_list":
                chars = data.get("characters", [])
                names = [c.get("name") for c in chars]
                log(label, "characters:", names)
                if CHARNAME in names:
                    await send(type="enter_world", character_name=CHARNAME)
                elif register:
                    await send(type="create_character", name=CHARNAME, race="Human",
                               klass="Paladin", sex="Male", look=0, realm=1)
                else:
                    log(label, "existing char not found!"); return False
            elif mt == "create_character_result" and data.get("success"):
                await send(type="enter_world", character_name=CHARNAME)
            elif mt == "root_info":
                got_root = True
                log(label, "*** root_info RECEIVED — world loaded ***")
            elif mt == "error":
                log(label, "ERROR:", data.get("message"))
    return got_root

async def main():
    log("PHASE 1: register + create + enter")
    ok1 = await phase("phase1", register=True)
    log("phase1 loaded world:", ok1)
    await asyncio.sleep(3)  # let logout/cleanup settle
    log("PHASE 2: reconnect + re-enter SAME character")
    ok2 = await phase("phase2", register=False)
    log("phase2 loaded world:", ok2)
    log("RESULT:", "RE-ENTRY OK" if ok2 else "RE-ENTRY BROKEN (no root_info)")

asyncio.run(main())
