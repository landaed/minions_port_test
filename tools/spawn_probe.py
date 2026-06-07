#!/usr/bin/env python3
"""Drive the proxy like the Godot client: register -> login -> world -> create a
NEW Human Warrior -> enter world. Print the RAW server spawn position, zone, and
root_info. Captures the player's true spawn (no movement)."""
import asyncio, json, sys, time, random, string
import websockets

_sfx = "".join(random.choice(string.ascii_lowercase) for _ in range(5))
URI = "ws://localhost:9000"
USER = "Probe" + str(int(time.time()) % 100000)
EMAIL = USER.lower() + "@example.com"
PW = "probepw123"
CHARNAME = "Probe" + _sfx

st = {"pw": None, "enter_sent": False, "char_created": False, "entered": False,
      "first_self": None, "zone": None, "root": None, "selfs": []}

def log(*a): print("[PROBE]", *a); sys.stdout.flush()

async def send(ws, **m):
    await ws.send(json.dumps(m)); log("->", m.get("type"))

async def run():
    async with websockets.connect(URI, max_size=8_000_000) as ws:
        await send(ws, type="register", username=USER, email=EMAIL, password=PW)
        t0 = time.time(); deadline = t0 + 35
        while time.time() < deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
            except asyncio.TimeoutError:
                continue
            d = json.loads(raw); mt = d.get("type", "")
            if mt == "register_result":
                if not d.get("success"): log("register FAIL", d.get("message")); return
                st["pw"] = d.get("password")
                await send(ws, type="login", username=USER, password=st["pw"])
            elif mt == "login_result":
                if not d.get("success"): log("login FAIL", d.get("message")); return
            elif mt == "world_list":
                ws_ = d.get("worlds", [])
                if not ws_: continue
                w = ws_[0]
                await send(ws, type="select_world", world_name=w["name"], ip=w["ip"],
                           port=w["port"], has_password=w.get("has_password", False))
            elif mt == "world_account_result" and d.get("success"):
                await send(ws, type="world_login", world_password=d.get("world_password"), role="Player")
            elif mt == "world_password_result" and d.get("success") and d.get("world_password"):
                await send(ws, type="world_login", world_password=d.get("world_password"), role="Player")
            elif mt == "character_list":
                chars = d.get("characters", [])
                log("CHARACTERS:", [c.get("name") for c in chars])
                if chars and not st["enter_sent"]:
                    st["enter_sent"] = True
                    await send(ws, type="enter_world", character_name=chars[0]["name"])
                elif not chars and not st["char_created"]:
                    st["char_created"] = True
                    await send(ws, type="create_character", name=CHARNAME,
                               race="Human", klass="Warrior", sex="Male", look=0, realm=1)
            elif mt == "create_character_result":
                if not d.get("success"): log("create FAIL", d.get("message")); return
                if not st["enter_sent"]:
                    st["enter_sent"] = True
                    await send(ws, type="enter_world", character_name=CHARNAME)
            elif mt == "root_info":
                st["root"] = {k: d[k] for k in d if k not in ("type",)}
                st["zone"] = d.get("zone")
                log("ROOT_INFO zone=", d.get("zone"), " keys=", list(d.keys()))
            elif mt == "gameplay_state":
                if d.get("zone"): st["zone"] = d.get("zone")
            elif mt == "entity_snapshot":
                for e in d.get("entities", []):
                    if e.get("is_self"):
                        p = e.get("position")
                        st["selfs"].append(p)
                        if st["first_self"] is None:
                            st["first_self"] = p
                            log("FIRST SELF POSITION (raw server):", p)
                            log("  rotation:", e.get("rotation"), " name:", e.get("name"),
                                " model:", e.get("model"))
                if len(st["selfs"]) >= 8:
                    break
        log("=== RESULT ===")
        log("zone:", st["zone"])
        log("raw spawn:", st["first_self"])
        log("first 8 self positions:", st["selfs"][:8])
        if st["first_self"]:
            x, y, z = st["first_self"]
            log("godot (x,z,-y):", [round(x,2), round(z,2), round(-y,2)])

if __name__ == "__main__":
    asyncio.run(run())
