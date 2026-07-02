#!/usr/bin/env python3
"""Prove the character-select appearance flow end to end, headlessly:

  register -> world login -> create char -> (character_list #1: no gear)
  -> enter world -> cheat-equip armor/helm/shield -> leave_world
  -> (character_list #2: must now carry "mounts" AND per-part "tex")

Exits 0 when the refreshed roster carries non-empty tex+mounts, 1 otherwise.
"""
import asyncio, json, sys, time, random, string
import websockets

URI = "ws://localhost:9000"
suf = "".join(random.choice(string.ascii_lowercase) for _ in range(6))
USER = "gear" + suf
EMAIL = USER + "@ex.com"
PW = "gearpw123"
CHARNAME = "Gear" + suf.capitalize()

GIVE = ["Apprentice's Chain Hauberk of the Bear",
        "Apprentice's Plate Leggings of the Bear",
        "Plain Helm", "Tower Shield"]


def log(*a):
    print("[GEARTEST]", *a)
    sys.stdout.flush()


async def main() -> int:
    lists = []          # every character_list payload seen, in order
    entered = False
    left = False
    async with websockets.connect(URI, max_size=8_000_000) as ws:
        async def send(**m):
            await ws.send(json.dumps(m))

        await send(type="register", username=USER, email=EMAIL, password=PW)
        deadline = time.time() + 90
        equip_done_at = None
        while time.time() < deadline:
            # After equipping, give the server a beat, then leave. (Checked on
            # every loop pass: entity snapshots keep recv() from ever timing out.)
            if equip_done_at and not left and time.time() - equip_done_at > 2:
                left = True
                log("sending leave_world")
                await send(type="leave_world")
            try:
                data = json.loads(await asyncio.wait_for(ws.recv(), timeout=2))
            except asyncio.TimeoutError:
                continue
            mt = data.get("type", "")
            if mt == "register_result" and data.get("success"):
                await send(type="login", username=USER, password=PW)
            elif mt == "world_list" and data.get("worlds"):
                w = data["worlds"][0]
                await send(type="select_world", world_name=w["name"], ip=w["ip"],
                           port=w["port"], has_password=w.get("has_password", False))
            elif mt == "world_account_result" and data.get("success"):
                await send(type="world_login",
                           world_password=data.get("world_password"), role="Player")
            elif mt == "world_password_result" and data.get("success") and data.get("world_password"):
                await send(type="world_login",
                           world_password=data.get("world_password"), role="Player")
            elif mt == "player_login_result" and not data.get("success"):
                log("world login FAILED:", data.get("message"))
                return 1
            elif mt == "character_list":
                chars = data.get("characters", [])
                lists.append(chars)
                log("character_list #%d: %s" % (
                    len(lists),
                    [(c.get("name"), "mounts=%d" % len(c.get("mounts") or {}),
                      "tex=%d" % len(c.get("tex") or {})) for c in chars]))
                if not chars and len(lists) == 1:
                    await send(type="create_character", name=CHARNAME,
                               race="Human", klass="Warrior", sex="Male",
                               look=1, bonus={}, realm=1)
                elif chars and not entered:
                    entered = True
                    await send(type="enter_world", character_name=chars[0]["name"])
                elif chars and left:
                    c = chars[0]
                    tex = c.get("tex") or {}
                    mounts = c.get("mounts") or {}
                    log("FINAL roster: tex=%s mounts=%s" % (tex, mounts))
                    ok = bool(tex) and bool(mounts)
                    log("RESULT:", "PASS" if ok else "FAIL")
                    return 0 if ok else 1
            elif mt == "create_character_result":
                if not data.get("success"):
                    log("create FAILED:", data.get("message"))
                    return 1
            elif mt == "root_info" and not equip_done_at:
                log("in world; equipping via cheats")
                await send(type="cheat", action="set_level", params={"level": 10})
                for item in GIVE:
                    await send(type="cheat", action="give_item",
                               params={"name": item, "equip": True})
                    await asyncio.sleep(0.6)
                equip_done_at = time.time()
            elif mt == "cheat_result":
                log("cheat:", data.get("action"), data.get("success"), data.get("message", ""))
    log("TIMEOUT")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
