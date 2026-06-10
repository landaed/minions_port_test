#!/usr/bin/env python3
"""Movement-latency probe, no Godot involved: drives the ClientProxy WebSocket
into the world, holds 'forward' for exactly HOLD_SECONDS of wall clock, then
stops, sampling the server's view of the player position from every
entity_snapshot. Reports server speed while held, travel after stop, and the
end-to-end distance vs the expected MOVE_SPEED * HOLD_SECONDS.

Usage: ./venv/bin/python tools/proxy_move_probe.py
"""
import asyncio, json, sys, time, random, string

import websockets

URI = "ws://localhost:9000"
HOLD_SECONDS = 5.0
TAIL_SECONDS = 6.0
MOVE_SPEED = 8.0

_suffix = "".join(random.choice(string.ascii_lowercase) for _ in range(5))
USER = "probe" + str(int(time.time()) % 100000)
CHARNAME = "Probe" + _suffix

state = {"entered": False, "enter_sent": False, "char_created": False, "samples": []}


def log(*a):
    print("[PROBE]", *a)
    sys.stdout.flush()


async def send(ws, **msg):
    await ws.send(json.dumps(msg))


async def move_loop(ws):
    await asyncio.sleep(3.0)
    state["samples"].clear()
    log("HOLD forward for %.1fs..." % HOLD_SECONDS)
    state["t_press"] = time.time()
    await send(ws, type="gameplay_command", command="player_input",
               move_x=0.0, move_y=1.0, forward=[0.0, 1.0, 0.0], jump=False)
    await asyncio.sleep(HOLD_SECONDS)
    state["t_release"] = time.time()
    await send(ws, type="gameplay_command", command="player_input",
               move_x=0.0, move_y=0.0, forward=[0.0, 1.0, 0.0], jump=False)
    log("RELEASE after %.2fs" % (state["t_release"] - state["t_press"]))
    await asyncio.sleep(TAIL_SECONDS)
    summarize()
    raise SystemExit(0)


def summarize():
    t_press = state.get("t_press")
    t_release = state.get("t_release")
    samples = [(t, p) for (t, p) in state["samples"] if p]
    if not samples or t_press is None:
        log("no samples!")
        return
    p_start = None
    p_at_release = None
    p_final = samples[-1][1]
    last_move_t = None
    prev = None
    for (t, p) in samples:
        if t <= t_press:
            p_start = p
        if t <= t_release:
            p_at_release = p
        if prev is not None:
            d = ((p[0] - prev[0]) ** 2 + (p[1] - prev[1]) ** 2) ** 0.5
            if d > 0.05:
                last_move_t = t
        prev = p
    if p_start is None:
        p_start = samples[0][1]

    def dist(a, b):
        return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5

    total = dist(p_final, p_start)
    at_release = dist(p_at_release, p_start) if p_at_release else 0.0
    expected = MOVE_SPEED * (t_release - t_press)
    log("server pos start=%s release=%s final=%s" % (p_start, p_at_release, p_final))
    log("distance at release=%.2f  final=%.2f  expected=%.2f  (deficit %.2f)" %
        (at_release, total, expected, expected - total))
    if last_move_t is not None:
        log("server kept moving %.2fs after release" % max(0.0, last_move_t - t_release))
    # speed curve, 1s buckets
    buckets = {}
    prev = None
    for (t, p) in samples:
        if prev is not None:
            dt = t - prev[0]
            if dt > 0:
                b = int(t - t_press)
                buckets.setdefault(b, [0.0, 0.0])
                buckets[b][0] += dist(p, prev[1])
                buckets[b][1] += dt
        prev = (t, p)
    for b in sorted(buckets):
        d, dt = buckets[b]
        if dt > 0:
            log("  t=%+d..%+ds  server speed %.2f u/s" % (b, b + 1, d / dt))


async def run():
    async with websockets.connect(URI, max_size=4_000_000) as ws:
        await send(ws, type="register", username=USER, email=USER + "@example.com", password="probepw1")
        while True:
            raw = await ws.recv()
            data = json.loads(raw)
            mt = data.get("type", "")
            if mt == "register_result":
                if not data.get("success"):
                    log("register failed", data); return
                await send(ws, type="login", username=USER, password=data.get("password"))
            elif mt == "world_list":
                worlds = data.get("worlds", [])
                if worlds:
                    w = worlds[0]
                    await send(ws, type="select_world", world_name=w["name"], ip=w["ip"],
                               port=w["port"], has_password=w.get("has_password", False))
            elif mt == "world_account_result" and data.get("success"):
                await send(ws, type="world_login", world_password=data.get("world_password"), role="Player")
            elif mt == "world_password_result" and data.get("success") and data.get("world_password"):
                await send(ws, type="world_login", world_password=data.get("world_password"), role="Player")
            elif mt == "character_list":
                chars = data.get("characters", [])
                if chars and not state["enter_sent"]:
                    state["enter_sent"] = True
                    await send(ws, type="enter_world", character_name=chars[0]["name"])
                elif not chars and not state["char_created"]:
                    state["char_created"] = True
                    await send(ws, type="create_character", name=CHARNAME,
                               race="Human", klass="Warrior", sex="Male", look=0, realm=1)
            elif mt == "create_character_result" and data.get("success") and not state["enter_sent"]:
                state["enter_sent"] = True
                await send(ws, type="enter_world", character_name=CHARNAME)
            elif mt in ("root_info", "gameplay_state"):
                if not state["entered"]:
                    state["entered"] = True
                    log("entered world; starting move test")
                    asyncio.create_task(move_loop(ws))
            elif mt == "entity_snapshot":
                for e in data.get("entities", []):
                    if e.get("is_self"):
                        state["samples"].append((time.time(), e.get("position")))
                        break


if __name__ == "__main__":
    try:
        asyncio.run(asyncio.wait_for(run(), timeout=90))
    except (SystemExit, asyncio.TimeoutError):
        pass
