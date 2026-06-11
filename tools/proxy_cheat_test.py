#!/usr/bin/env python3
"""Headless test for the cheat API + class starting spells.

Creates a fresh Wizard (which should auto-scribe its StartingGear scrolls into
the spellbook), enters the world, then runs through every cheat action and
prints the results. Run the stack first (./run_servers.sh), then:
    python3 tools/proxy_cheat_test.py
"""
import asyncio, json, sys, time, random, string

import websockets

_suffix = "".join(random.choice(string.ascii_lowercase) for _ in range(5))

URI = "ws://localhost:9000"
USER = "Cheater" + str(int(time.time()) % 100000)
EMAIL = USER.lower() + "@example.com"
CHARNAME = "Zappy" + _suffix
RACE = "Human"
KLASS = "Wizard"

state = {
    "password": None,
    "entered": False,
    "char_created": False,
    "enter_sent": False,
    "abilities": [],
    "spellbook": None,
    "inventory": None,
    "cheat_results": {},
    "done": False,
}


def log(*a):
    print("[CHEAT]", *a)
    sys.stdout.flush()


async def send(ws, **msg):
    await ws.send(json.dumps(msg))


async def run():
    async with websockets.connect(URI, max_size=8_000_000) as ws:
        await send(ws, type="register", username=USER, email=EMAIL, password="mychosenpw")
        cheat_task = None
        deadline = time.time() + 120
        while time.time() < deadline and not state["done"]:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
            except asyncio.TimeoutError:
                continue
            data = json.loads(raw)
            mt = data.get("type", "")

            if mt == "register_result":
                if data.get("success"):
                    state["password"] = data.get("password")
                    await send(ws, type="login", username=USER, password=state["password"])
                else:
                    log("register failed:", data.get("message")); return

            elif mt == "world_list":
                worlds = data.get("worlds", [])
                if worlds:
                    w = worlds[0]
                    await send(ws, type="select_world", world_name=w["name"],
                               ip=w["ip"], port=w["port"], has_password=w.get("has_password", False))

            elif mt in ("world_account_result", "world_password_result"):
                if data.get("success") and data.get("world_password"):
                    await send(ws, type="world_login",
                               world_password=data.get("world_password"), role="Player")

            elif mt == "character_list":
                chars = data.get("characters", [])
                if not chars and not state["char_created"]:
                    state["char_created"] = True
                    await send(ws, type="create_character", name=CHARNAME,
                               race=RACE, klass=KLASS, sex="Male", look=0, realm=1)
                elif chars and not state["enter_sent"]:
                    state["enter_sent"] = True
                    await send(ws, type="enter_world", character_name=chars[0]["name"])

            elif mt == "create_character_result":
                if data.get("success"):
                    if not state["enter_sent"]:
                        state["enter_sent"] = True
                        await send(ws, type="enter_world", character_name=CHARNAME)
                else:
                    log("create char failed:", data.get("message")); return

            elif mt in ("root_info", "gameplay_state"):
                cis = data.get("char_infos", [])
                if cis and isinstance(cis[0], dict):
                    abil = cis[0].get("abilities", [])
                    if abil:
                        state["abilities"] = abil
                    state["level"] = cis[0].get("level")
                if not state["entered"]:
                    state["entered"] = True
                    log("ENTERED WORLD as %s %s." % (RACE, KLASS))
                    cheat_task = asyncio.create_task(cheat_loop(ws))

            elif mt == "spellbook":
                state["spellbook"] = data

            elif mt == "inventory":
                state["inventory"] = data

            elif mt == "cheat_result":
                action = data.get("action", "?")
                state["cheat_results"][action] = data
                log("<- cheat_result[%s]: success=%s  %s" % (
                    action, data.get("success"), data.get("message", "")))

        if cheat_task:
            cheat_task.cancel()
        summarize()


async def cheat_loop(ws):
    await asyncio.sleep(2.0)
    # Starting state: spellbook should already have the Wizard's starting spells.
    await send(ws, type="gameplay_command", command="get_spellbook")
    await send(ws, type="gameplay_command", command="get_inventory")
    await asyncio.sleep(2.0)
    sb = state.get("spellbook") or {}
    spells = sb.get("spells", [])
    log("STARTING SPELLBOOK (%d spells): %s" % (
        len(spells), [s.get("name") for s in spells]))
    log("STARTING ABILITIES: %s" % [
        (a.get("name"), a.get("icon")) for a in state["abilities"]])
    inv = state.get("inventory") or {}
    log("STARTING INVENTORY (%d items): %s" % (
        len(inv.get("items", [])), [i.get("name") for i in inv.get("items", [])]))

    tests = [
        ("status", {}),
        ("give_xp", {"amount": 5000}),
        ("set_level", {"level": 5}),
        ("give_money", {"platinum": 250}),
        ("list_items", {"filter": "longsword"}),
        ("give_item", {"name": "Longsword"}),
        ("list_spells", {"filter": "fire"}),
        ("learn_spell", {"name": "Fireball"}),
        ("learn_class_spells", {}),
        ("raise_skills", {"points": 3}),
        ("full_heal", {}),
    ]
    for action, params in tests:
        log("-> cheat", action, params)
        await send(ws, type="cheat", action=action, params=params)
        await asyncio.sleep(1.2)

    await asyncio.sleep(2.0)
    await send(ws, type="gameplay_command", command="get_spellbook")
    await asyncio.sleep(2.0)
    state["done"] = True


def summarize():
    print()
    log("=== SUMMARY ===")
    sb = state.get("spellbook") or {}
    spells = sb.get("spells", [])
    log("Final level: %s" % state.get("level"))
    log("Final spellbook (%d): %s" % (len(spells), [s.get("name") for s in spells][:25]))
    ok = [a for a, r in state["cheat_results"].items() if r.get("success")]
    bad = [a for a, r in state["cheat_results"].items() if not r.get("success")]
    log("Cheats OK:     %s" % ok)
    log("Cheats FAILED: %s" % bad)
    inv = state.get("inventory") or {}
    log("Final inventory (%d items): %s" % (
        len(inv.get("items", [])),
        [(i.get("name"), i.get("slot")) for i in inv.get("items", [])]))
    log("Money (tin): %s" % inv.get("tin"))


if __name__ == "__main__":
    asyncio.run(run())
