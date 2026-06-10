#!/usr/bin/env python3
"""Headless combat/loot/dialog test: enter world, kill the test mob beside the
spawn, loot its corpse into the bags, then walk to Chancellor Tolip, run his
dialog and pick the first choice. Verifies the whole new UI bridge server-side:
target -> attack (auto-face) -> corpse streaming -> select_entity loot ->
getLoot/loot -> getInventory, and interact -> npc dialog -> choice -> journal.
"""
import asyncio, json, sys, time, math, random, string, os
import websockets

_suffix = "".join(random.choice(string.ascii_lowercase) for _ in range(4))
URI = "ws://localhost:9000"
USER = "Lt" + str(int(time.time()) % 100000)
CHARNAME = "Loot" + _suffix
MOB_NAME = os.environ.get("MOM_TEST_MOB_NAME", "Frail Skeleton")

S = {
    "entered": False, "enter_sent": False, "char_created": False,
    "phase": "boot", "mob_id": 0, "self_pos": None, "mob_pos": None,
    "mob_dead": False, "mob_seen_dead_in_stream": False,
    "loot_items": None, "inventory": None, "dialog": [], "journal": [],
    "facing_failures": 0, "drift_log": [],
}

def log(*a):
    print("[TEST]", *a); sys.stdout.flush()

async def send(ws, **msg):
    await ws.send(json.dumps(msg))

async def cmd(ws, command, **kw):
    await ws.send(json.dumps({"type": "gameplay_command", "command": command, **kw}))

async def run():
    async with websockets.connect(URI, max_size=4_000_000) as ws:
        await send(ws, type="register", username=USER, email=USER + "@x.com", password="pw12345")
        t0 = time.time()
        task = None
        while time.time() < t0 + 110:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
            except asyncio.TimeoutError:
                continue
            d = json.loads(raw)
            mt = d.get("type", "")
            if mt == "register_result":
                await send(ws, type="login", username=USER, password=d.get("password") or "pw12345")
            elif mt == "world_list" and d.get("worlds"):
                w = d["worlds"][0]
                await send(ws, type="select_world", world_name=w["name"], ip=w["ip"], port=w["port"],
                           has_password=w.get("has_password", False))
            elif mt in ("world_account_result", "world_password_result"):
                if d.get("success") and d.get("world_password"):
                    await send(ws, type="world_login", world_password=d["world_password"], role="Player")
            elif mt == "character_list":
                chars = d.get("characters", [])
                if chars and not S["enter_sent"]:
                    S["enter_sent"] = True
                    await send(ws, type="enter_world", character_name=chars[0]["name"])
                elif not chars and not S["char_created"]:
                    S["char_created"] = True
                    await send(ws, type="create_character", name=CHARNAME, race="Human",
                               klass="Warrior", sex="Male", look=0, realm=1)
            elif mt == "create_character_result" and d.get("success") and not S["enter_sent"]:
                S["enter_sent"] = True
                await send(ws, type="enter_world", character_name=CHARNAME)
            elif mt == "root_info" and not S["entered"]:
                S["entered"] = True
                log("ENTERED WORLD; starting scripted combat/loot/dialog")
                task = asyncio.create_task(script(ws))
            elif mt == "entity_snapshot":
                handle_snapshot(d.get("entities", []))
            elif mt == "game_text":
                txt = str(d.get("text", ""))
                if "facing the wrong way" in txt:
                    S["facing_failures"] += 1
                if txt.strip():
                    log("game_text:", txt.strip().replace("\\n", " ")[:110])
            elif mt == "loot":
                S["loot_items"] = d.get("items", {})
                log("LOOT TABLE:", {k: v.get("name") for k, v in S["loot_items"].items()})
            elif mt == "inventory":
                S["inventory"] = d
            elif mt in ("npc_window", "npc_dialog_start", "npc_dialog", "npc_window_close", "vendor_stock"):
                S["dialog"].append(d)
                log("DIALOG EVT:", mt, str({k: d[k] for k in d if k in ("npc", "text", "choices", "name")})[:160])
            elif mt == "journal_entry":
                S["journal"].append(d)
                log("JOURNAL ENTRY:", d.get("topic"), "/", d.get("entry"))
        if task:
            task.cancel()
        report()

def handle_snapshot(ents):
    for e in ents:
        if e.get("is_self"):
            S["self_pos"] = e.get("position")
    # Lock onto the Frail Skeleton test mob specifically (closest if several).
    if not S["mob_id"]:
        best = None
        for e in ents:
            if e.get("is_self"):
                continue
            if MOB_NAME not in str(e.get("name", "")):
                continue
            if best is None or e.get("distance", 999) < best.get("distance", 999):
                best = e
        if best:
            S["mob_id"] = best.get("id")
            S["mob_pos"] = best.get("position")
            S["mob_hp"] = best.get("health")
            log("TEST MOB:", best.get("name"), "id", S["mob_id"], "hp", best.get("health"),
                "d=%.1f" % best.get("distance", -1))
    for e in ents:
        if S["mob_id"] and e.get("id") == S["mob_id"]:
            S["mob_pos"] = e.get("position")
            S["mob_hp"] = e.get("health")
            if e.get("dead") or e.get("health", 1) <= 0:
                S["mob_dead"] = True
                S["mob_seen_dead_in_stream"] = True

def fmt(p):
    return "(%.1f,%.1f,%.1f)" % tuple(p) if p else "None"

async def walk_towards(ws, get_target, stop_dist, timeout=30.0):
    """Send held movement input toward a (possibly moving) server position."""
    t0 = time.time()
    moving = False
    while time.time() < t0 + timeout:
        tp = get_target()
        sp = S["self_pos"]
        if not tp or not sp:
            await asyncio.sleep(0.3); continue
        dx, dy = tp[0] - sp[0], tp[1] - sp[1]
        dist = math.hypot(dx, dy)
        if dist <= stop_dist:
            break
        n = max(dist, 0.001)
        fwd = [dx / n, dy / n, 0.0]
        await cmd(ws, "player_input", move_x=0.0, move_y=1.0, forward=fwd, jump=False,
                  position_z=sp[2])
        moving = True
        await asyncio.sleep(0.25)
    await cmd(ws, "player_input", move_x=0.0, move_y=0.0,
              forward=[0.0, 1.0, 0.0], jump=False, position_z=(S["self_pos"] or [0,0,0])[2])
    return moving

async def script(ws):
    try:
        await asyncio.sleep(2.5)
        # --- combat ---
        if not S["mob_id"]:
            log("no test mob seen yet; waiting"); await asyncio.sleep(3)
        if S["mob_id"]:
            await walk_towards(ws, lambda: S["mob_pos"], 2.5, 20)
            log("attacking mob", S["mob_id"], "self=", fmt(S["self_pos"]), "mob=", fmt(S["mob_pos"]))
            await cmd(ws, "target_entity", entity_id=S["mob_id"])
            await asyncio.sleep(0.5)
            await cmd(ws, "attack_toggle")
            t0 = time.time()
            while not S["mob_dead"] and time.time() < t0 + 75:
                await asyncio.sleep(1.0)
                drift = math.hypot(S["self_pos"][0] - S["mob_pos"][0],
                                   S["self_pos"][1] - S["mob_pos"][1]) if S["self_pos"] and S["mob_pos"] else -1
                S["drift_log"].append(round(drift, 2))
                S.setdefault("hp_log", []).append(S.get("mob_hp"))
            log("mob dead:", S["mob_dead"], " (fight took %.0fs)" % (time.time() - t0))
            await cmd(ws, "attack_toggle")
            # --- loot ---
            if S["mob_dead"]:
                await asyncio.sleep(1.0)
                await cmd(ws, "select_entity", entity_id=S["mob_id"], double_click=True)
                await asyncio.sleep(2.0)
                if S["loot_items"]:
                    for _ in range(len(S["loot_items"]) + 1):
                        await cmd(ws, "loot_item", slot=0, alt=True)
                        await asyncio.sleep(0.8)
                await cmd(ws, "get_inventory")
                await asyncio.sleep(1.5)
        # --- dialog with Chancellor Tolip ---
        tolip = {"pos": None, "id": 0}
        def remember_tolip():
            return tolip["pos"]
        # tolip's marker (server coords)
        tolip["pos"] = [36.4442, -250.456, 126.5]
        await walk_towards(ws, remember_tolip, 1.8, 35)
        log("at Tolip; self=", fmt(S["self_pos"]))
        await cmd(ws, "target_nearest")
        await asyncio.sleep(1.0)
        await cmd(ws, "interact")
        await asyncio.sleep(2.5)
        has_dialog = any(x.get("type") == "npc_dialog_start" and x.get("has_dialog") for x in S["dialog"])
        if has_dialog:
            await cmd(ws, "dialog_choice", index=0)
            await asyncio.sleep(2.5)
            await cmd(ws, "end_interaction")
    except asyncio.CancelledError:
        pass
    except Exception as e:
        import traceback; traceback.print_exc()

def report():
    inv = S["inventory"] or {}
    items = inv.get("items", [])
    log("=" * 60)
    log("RESULT mob_id=%s dead=%s dead_streamed=%s" % (S["mob_id"], S["mob_dead"], S["mob_seen_dead_in_stream"]))
    log("RESULT facing_failures=%d" % S["facing_failures"])
    log("RESULT loot_table=%s" % (S["loot_items"] is not None))
    log("RESULT inventory: %d items, tin=%s -> %s" % (
        len(items), inv.get("tin"), [i.get("name") for i in items][:8]))
    log("RESULT dialog events: %s" % [x.get("type") for x in S["dialog"]])
    for x in S["dialog"]:
        if x.get("type") == "npc_dialog_start":
            log("   greeting: %r choices=%s" % (str(x.get("text", ""))[:80], x.get("choices")))
        if x.get("type") == "npc_dialog":
            log("   line: %r choices=%s" % (str(x.get("text", ""))[:80], x.get("choices")))
    log("RESULT journal: %s" % [(j.get("topic"), j.get("entry")) for j in S["journal"]])
    log("RESULT drift(last10)=%s" % S["drift_log"][-10:])
    log("RESULT mob_hp(log)=%s" % S.get("hp_log", []))

asyncio.run(run())
