#!/usr/bin/env python3
"""Headless pet AUTO-ASSIST test: summon a pet, target a hostile mob and turn on
the player's auto-attack (NO manual pet command), then verify the pet engages the
same mob on its own (pet.target_id != 0). Exercises mob.py _pickAssistTarget + the
tick assist hook. Run the server stack first (./run_servers.sh)."""
import asyncio
import json
import time
import websockets

URI = "ws://localhost:9000"
USER = "petassist_" + str(int(time.time()) % 100000)
CHARNAME = "Assistnirb"

state = {"self": None, "pet": None, "enemies": {}, "log": [], "done": False,
         "char_created": False, "enter_sent": False, "entered": False,
         "spellbook": None}


def log(*a):
    print("[ASSIST]", *a, flush=True)


async def send(ws, **msg):
    await ws.send(json.dumps(msg))


async def run():
    async with websockets.connect(URI, max_size=8_000_000) as ws:
        await send(ws, type="register", username=USER, email=USER + "@x.com", password="testpass1")
        task = None
        deadline = time.time() + 150
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
                task = asyncio.create_task(assist_loop(ws))
            elif t == "spellbook":
                state["spellbook"] = d
            elif t == "entity_snapshot":
                for e in d.get("entities", []):
                    if e.get("is_self"):
                        state["self"] = e
                    elif e.get("is_my_pet"):
                        state["pet"] = e
                    elif e.get("is_enemy") and not e.get("dead"):
                        state["enemies"][int(e.get("id", 0))] = e
            elif t in ("game_text", "text_messages"):
                state["log"].append(json.dumps(d)[:160])
        if task:
            task.cancel()


async def assist_loop(ws):
    await asyncio.sleep(2)
    await send(ws, type="gameplay_command", command="get_spellbook")
    await asyncio.sleep(2)
    sb = state.get("spellbook") or {}
    summon = next((s for s in sb.get("spells", []) if "lemental" in s.get("name", "")), None)
    if not summon:
        log("FAIL: no summon spell"); state["done"] = True; return
    await send(ws, type="gameplay_command", command="spell_slot",
               char_id=sb.get("char_id", 0), slot=summon["slot"])
    for _ in range(18):
        await asyncio.sleep(1)
        if state.get("pet"):
            break
    if not state.get("pet"):
        log("FAIL: pet never appeared:", state["log"][-4:]); state["done"] = True; return
    log("PET APPEARED:", state["pet"].get("name"))

    # Acquire a hostile target by cycling (no manual pet command at all).
    target_id = 0
    for _ in range(8):
        await send(ws, type="gameplay_command", command="cycle_target")
        await asyncio.sleep(1.0)
        tid = int((state.get("self") or {}).get("target_id", 0))
        if tid and tid in state["enemies"]:
            target_id = tid
            break
    if not target_id:
        log("FAIL: could not target a hostile mob (enemies seen: %d)" % len(state["enemies"]))
        state["done"] = True; return
    log("player targeting enemy id=%d (%s)" % (target_id, state["enemies"][target_id].get("name")))

    # Turn ON the player's auto-attack. Do NOT send pet_attack.
    await send(ws, type="gameplay_command", command="attack_toggle")
    log("player auto-attack ON; watching whether the pet engages on its own...")

    pet_engaged = 0
    for _ in range(16):
        await asyncio.sleep(1.0)
        ptid = int((state.get("pet") or {}).get("target_id", 0))
        if ptid != 0:
            pet_engaged = ptid
            break
    ok = pet_engaged != 0
    log("pet.target_id =", pet_engaged, "(player target was %d)" % target_id)
    log("recent text:", state["log"][-4:])
    log("PET AUTO-ASSIST:", "PASS" if ok else "FAIL")
    state["done"] = True


asyncio.run(run())
