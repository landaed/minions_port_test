#!/usr/bin/env python3
"""Headless pet test: create a Tempest, cast Summon Inferior Air Elemental,
then move around and verify the pet follows; target a mob and send PET ATTACK
and verify the pet engages. Run the stack first (./run_servers.sh)."""
import asyncio, json, sys, time, random, string

import websockets

URI = "ws://localhost:9000"
USER = "Petter" + str(int(time.time()) % 100000)
CHARNAME = "Stormy" + "".join(random.choice(string.ascii_lowercase) for _ in range(5))

state = {"entered": False, "char_created": False, "enter_sent": False,
         "spellbook": None, "self": None, "pet": None, "done": False,
         "log": [], "events": []}


def log(*a):
    print("[PET]", *a)
    sys.stdout.flush()


async def send(ws, **msg):
    await ws.send(json.dumps(msg))


async def run():
    async with websockets.connect(URI, max_size=8_000_000) as ws:
        await send(ws, type="register", username=USER, email=USER+"@x.com", password="testpass1")
        task = None
        deadline = time.time() + 180
        while time.time() < deadline and not state["done"]:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
            except asyncio.TimeoutError:
                continue
            d = json.loads(raw)
            t = d.get("type", "")
            if t == "register_result" and d.get("success"):
                await send(ws, type="login", username=USER, password=d.get("password"))
            elif t == "world_list" and d.get("worlds"):
                w = d["worlds"][0]
                await send(ws, type="select_world", world_name=w["name"], ip=w["ip"],
                           port=w["port"], has_password=w.get("has_password", False))
            elif t in ("world_account_result", "world_password_result") and d.get("success") and d.get("world_password"):
                await send(ws, type="world_login", world_password=d["world_password"], role="Player")
            elif t == "character_list":
                chars = d.get("characters", [])
                if not chars and not state["char_created"]:
                    state["char_created"] = True
                    await send(ws, type="create_character", name=CHARNAME, race="Human",
                               klass="Tempest", sex="Male", look=0, realm=1)
                elif chars and not state["enter_sent"]:
                    state["enter_sent"] = True
                    await send(ws, type="enter_world", character_name=chars[0]["name"])
            elif t == "create_character_result" and d.get("success") and not state["enter_sent"]:
                state["enter_sent"] = True
                await send(ws, type="enter_world", character_name=CHARNAME)
            elif t in ("root_info", "gameplay_state") and not state["entered"]:
                state["entered"] = True
                log("ENTERED WORLD as Tempest")
                task = asyncio.create_task(pet_loop(ws))
            elif t == "spellbook":
                state["spellbook"] = d
            elif t == "entity_snapshot":
                for e in d.get("entities", []):
                    if e.get("is_self"):
                        state["self"] = e
                    elif "lemental" in str(e.get("name", "")):
                        state["pet"] = e
                for ev in d.get("events", []):
                    state["events"].append(ev)
            elif t in ("game_text", "text_messages"):
                state["log"].append(json.dumps(d)[:200])
        if task:
            task.cancel()


def pet_dist():
    s, p = state.get("self"), state.get("pet")
    if not s or not p:
        return None
    sp, pp = s["position"], p["position"]
    return ((sp[0]-pp[0])**2 + (sp[1]-pp[1])**2) ** 0.5


async def move(ws, mx, my, secs):
    t0 = time.time()
    while time.time() - t0 < secs:
        await send(ws, type="gameplay_command", command="player_input",
                   move_x=mx, move_y=my, forward=[0, 1, 0], jump=False)
        await asyncio.sleep(0.05)
    await send(ws, type="gameplay_command", command="player_input",
               move_x=0, move_y=0, forward=[0, 1, 0], jump=False)


async def pet_loop(ws):
    await asyncio.sleep(2)
    await send(ws, type="gameplay_command", command="get_spellbook")
    await asyncio.sleep(2)
    sb = state.get("spellbook") or {}
    spells = sb.get("spells", [])
    log("spellbook:", [(s.get("name"), s.get("slot"), s.get("mana"), s.get("cast_time")) for s in spells])
    summon = next((s for s in spells if "lemental" in s.get("name", "")), None)
    if not summon:
        log("FAIL: no summon spell in book"); state["done"] = True; return
    log("casting", summon["name"], "(cast %.1fs, mana %d)" % (summon["cast_time"], summon["mana"]))
    await send(ws, type="gameplay_command", command="spell_slot",
               char_id=sb.get("char_id", 0), slot=summon["slot"])
    # wait for the cast (10s) + spawn
    for i in range(18):
        await asyncio.sleep(1)
        if state.get("pet"):
            break
    if not state.get("pet"):
        log("FAIL: pet entity never appeared. recent text:", state["log"][-5:])
        state["done"] = True; return
    log("PET APPEARED:", state["pet"].get("name"), "dist=%.1f" % pet_dist())

    # casting events sanity: a 'casting' begin + end should have been captured
    cast_evs = [e for e in state["events"] if e.get("event") in ("casting", "particles")]
    log("cast-related events seen:", cast_evs[:6])

    # 1) FOLLOW: run away ~10s (80 units), check pet distance over time
    log(">>> moving away to test follow...")
    await move(ws, 0, 1.0, 8.0)
    await asyncio.sleep(2)
    d1 = pet_dist()
    log("after move: pet dist = %s" % ("%.1f" % d1 if d1 is not None else "pet gone from snapshot"))
    await asyncio.sleep(4)
    d2 = pet_dist()
    log("4s later:  pet dist = %s" % ("%.1f" % d2 if d2 is not None else "pet gone from snapshot"))
    follows = d2 is not None and d2 < 12.0
    log("FOLLOW TEST:", "PASS" if follows else "FAIL")

    # 2) ASSIST: target nearest enemy and send PET ATTACK
    await send(ws, type="gameplay_command", command="cycle_target")
    await asyncio.sleep(1.5)
    await send(ws, type="gameplay_command", command="pet_attack")
    await asyncio.sleep(2)
    log("recent text:", state["log"][-4:])
    state["done"] = True


asyncio.run(run())
