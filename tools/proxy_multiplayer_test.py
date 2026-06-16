#!/usr/bin/env python3
"""Headless TWO-CLIENT multiplayer test.

Drives two independent ClientProxy WebSocket sessions (exactly like two Godot
clients), brings both characters into the same world/zone, and verifies the
multiplayer-specific behaviour that a single-client test can't:

  1. Mutual visibility   - A sees B and B sees A as is_player entities.
  2. Movement replication - when A walks, B's snapshots of A update.
  3. Equipment replication - when B equips gear (via cheat), A's snapshot of B
     shows the new weapon/shield/helm "mounts" (and armour "tex").
  4. Party / alliance     - probe whether forming a group is wired end-to-end.
  5. Buff each other       - A (Cleric) targets B and casts a beneficial spell;
     check whether it lands on B.

Run with the server stack up (./run_servers.sh).  A third client can be added
trivially; kept at two for a clear, fast run.
"""
import asyncio, json, sys, time, random, string
import websockets

URI = "ws://localhost:9000"
SUF = "".join(random.choice(string.ascii_lowercase) for _ in range(4))

def log(tag, *a):
    print(("[%s]" % tag), *a); sys.stdout.flush()


class Client:
    def __init__(self, tag, charname, klass, realm=1):
        self.tag = tag
        self.user = "Mp%s%s%d" % (tag, SUF, int(time.time()) % 10000)
        self.charname = charname
        self.klass = klass
        self.realm = realm
        self.ws = None
        self.password = None
        self.entered = False
        self.enter_sent = False
        self.char_created = False
        self.enter_attempts = 0
        self.verbose = False
        self.last_entities = []     # most recent entity_snapshot
        self.my_id = None
        self.texts = []             # combat / game text lines
        self._listen_task = None

    async def send(self, **m):
        await self.ws.send(json.dumps(m))

    async def connect_and_enter(self):
        self.ws = await websockets.connect(URI, max_size=8_000_000)
        self._listen_task = asyncio.create_task(self._listen())
        await self.send(type="register", username=self.user,
                        email=self.user.lower() + "@example.com", password="pw" + SUF)
        # wait until in-world (allow time for create + enter retries)
        for _ in range(240):
            if self.entered:
                return True
            await asyncio.sleep(0.25)
        return self.entered

    async def _listen(self):
        try:
            async for raw in self.ws:
                data = json.loads(raw)
                mt = data.get("type", "")
                await self._on(mt, data)
        except Exception:
            pass

    async def _do_enter(self, delay=2.0):
        """Enter the world after a short settle so the freshly-created character
        has propagated to the world server (avoids '(-1, Character not found')."""
        if self.entered:
            return
        await asyncio.sleep(delay)
        self.enter_attempts += 1
        self.enter_sent = True
        await self.send(type="enter_world", character_name=self.charname)

    async def _on(self, mt, data):
        if self.verbose and mt not in ("entity_snapshot", "world_time"):
            log(self.tag, "<<", mt, "" if mt in ("character_list",) else str(data)[:90])
        if mt == "register_result" and data.get("success"):
            self.password = data.get("password")
            await self.send(type="login", username=self.user, password=self.password)
        elif mt == "world_list":
            worlds = data.get("worlds", [])
            if worlds:
                w = worlds[0]
                await self.send(type="select_world", world_name=w["name"], ip=w["ip"],
                                port=w["port"], has_password=w.get("has_password", False))
        elif mt == "world_account_result" and data.get("success"):
            await self.send(type="world_login", world_password=data.get("world_password"), role="Player")
        elif mt == "world_password_result" and data.get("success") and data.get("world_password"):
            await self.send(type="world_login", world_password=data.get("world_password"), role="Player")
        elif mt == "character_list":
            chars = data.get("characters", [])
            if chars and not self.enter_sent:
                self.charname = chars[0]["name"]   # canonical stored name
                asyncio.create_task(self._do_enter(delay=1.0))
            elif not chars and not self.char_created:
                self.char_created = True
                await self.send(type="create_character", name=self.charname, race="Human",
                                klass=self.klass, sex="Male", look=0, realm=self.realm)
        elif mt == "create_character_result":
            if data.get("success") and not self.enter_sent:
                self.charname = data.get("name", self.charname)  # canonical (capitalize()d)
                log(self.tag, "character created:", self.charname)
                asyncio.create_task(self._do_enter(delay=2.0))
            elif not data.get("success"):
                log(self.tag, "create char FAILED:", data.get("message"))
        elif mt == "enter_world_result":
            res = str(data.get("result", "") or "")
            if "not found" in res.lower() and self.enter_attempts < 5:
                log(self.tag, "enter retry (%d): %s" % (self.enter_attempts, res))
                self.enter_sent = False
                asyncio.create_task(self._do_enter(delay=2.0))
        elif mt in ("root_info", "gameplay_state"):
            self.entered = True
        elif mt == "entity_snapshot":
            self.last_entities = data.get("entities", [])
            for e in self.last_entities:
                if e.get("is_self"):
                    self.my_id = e.get("id")
        elif mt == "text_messages":
            for line in data.get("messages", []):
                self.texts.append(str(line))
        elif mt == "cheat_result":
            log(self.tag, "cheat[%s]:" % data.get("action"), data.get("success"), str(data.get("message", ""))[:80])

    # --- helpers ---
    def self_entity(self):
        for e in self.last_entities:
            if e.get("is_self"):
                return e
        return {}

    def see_player(self, name):
        """Return the entity dict for another player by name, if visible."""
        for e in self.last_entities:
            if e.get("is_player") and not e.get("is_self") and e.get("name") == name:
                return e
        return {}

    def other_players(self):
        return [e for e in self.last_entities if e.get("is_player") and not e.get("is_self")]

    async def move_forward(self, secs):
        await self.send(type="gameplay_command", command="player_input",
                        move_x=0.0, move_y=1.0, forward=[0.0, 1.0, 0.0], jump=False)
        await asyncio.sleep(secs)
        await self.send(type="gameplay_command", command="player_input",
                        move_x=0.0, move_y=0.0, forward=[0.0, 1.0, 0.0], jump=False)

    async def cheat(self, action, **params):
        await self.send(type="cheat", action=action, params=params)
        await asyncio.sleep(1.2)

    async def target(self, entity_id):
        await self.send(type="gameplay_command", command="target_entity", entity_id=int(entity_id))
        await asyncio.sleep(0.6)

    async def use_ability(self, name):
        await self.send(type="gameplay_command", command="use_ability", ability_name=name)
        await asyncio.sleep(0.6)


def mounts_summary(e):
    m = e.get("mounts", {}) or {}
    out = {}
    for slot, info in m.items():
        if isinstance(info, dict):
            out[slot] = info.get("model", "?")
    return out


async def main():
    A = Client("A", "Alpha" + SUF.capitalize(), "Cleric")   # healer/buffer
    B = Client("B", "Bravo" + SUF.capitalize(), "Warrior")  # melee/equipment
    results = {}

    log("MP", "Connecting two clients...")
    okA = await A.connect_and_enter()
    okB = await B.connect_and_enter()
    log("MP", "A entered:", okA, "| B entered:", okB)
    if not (okA and okB):
        log("MP", "ABORT: both clients failed to enter world"); return
    log("MP", "A=%s (Cleric, mob id %s)  B=%s (Warrior, mob id %s)" %
        (A.charname, A.my_id, B.charname, B.my_id))

    # Let snapshots flow and canSee settle.
    await asyncio.sleep(4)

    # ---- TEST 1: mutual visibility -------------------------------------
    a_sees_b = A.see_player(B.charname)
    b_sees_a = B.see_player(A.charname)
    log("T1", "A's visible players:", [e.get("name") for e in A.other_players()])
    log("T1", "B's visible players:", [e.get("name") for e in B.other_players()])
    results["mutual_visibility"] = bool(a_sees_b) and bool(b_sees_a)
    log("T1", "MUTUAL VISIBILITY:", "PASS" if results["mutual_visibility"] else "FAIL",
        "(A sees B: %s, B sees A: %s)" % (bool(a_sees_b), bool(b_sees_a)))
    if a_sees_b:
        log("T1", "  A sees B as: name=%s is_player=%s race=%s pclass=%s dist=%.1f" % (
            a_sees_b.get("name"), a_sees_b.get("is_player"), a_sees_b.get("race"),
            a_sees_b.get("pclass"), a_sees_b.get("distance", -1)))

    # ---- TEST 2: movement replication (A walks, B watches A) -----------
    b_view_a0 = B.see_player(A.charname).get("position")
    await A.move_forward(5.0)
    await asyncio.sleep(2.0)
    b_view_a1 = B.see_player(A.charname).get("position")
    moved = 0.0
    if b_view_a0 and b_view_a1:
        moved = sum((b_view_a1[i] - b_view_a0[i]) ** 2 for i in range(2)) ** 0.5
    results["movement_replication"] = moved > 3.0
    log("T2", "B's view of A moved %.1f units (%s -> %s)" % (
        moved, b_view_a0, b_view_a1))
    log("T2", "MOVEMENT REPLICATION:", "PASS" if results["movement_replication"] else "FAIL")

    # ---- TEST 3: equipment replication (B equips, A watches B) ---------
    a_view_b_before = mounts_summary(A.see_player(B.charname))
    log("T3", "A's view of B mounts BEFORE:", a_view_b_before)
    await B.cheat("set_level", level=12)
    await B.cheat("give_item", name="Longsword", equip=True)
    await B.cheat("give_item", name="Tower Shield", equip=True)
    await B.cheat("give_item", name="Plain Helm", equip=True)
    await B.cheat("give_item", name="Plate Mail", equip=True)
    await asyncio.sleep(3.0)  # let snapshot + cache invalidation propagate
    a_view_b_after = mounts_summary(A.see_player(B.charname))
    log("T3", "A's view of B mounts AFTER :", a_view_b_after)
    results["equipment_replication"] = len(a_view_b_after) > len(a_view_b_before)
    log("T3", "EQUIPMENT REPLICATION:", "PASS" if results["equipment_replication"] else "FAIL",
        "(other player sees newly-equipped weapon/shield/helm mounts)")

    # ---- TEST 4: party / alliance probe --------------------------------
    # A targets B, then attempt to invite. The proxy command map does not (yet)
    # expose INVITE; this probe records whether it is wired end-to-end.
    party_wired = False
    if a_sees_b:
        await A.target(a_sees_b.get("id"))
        await A.send(type="gameplay_command", command="invite")
        await asyncio.sleep(1.0)
        # If wired, B would receive an alliance_invite -> party membership.
        party_wired = any("alliance" in t.lower() and "invite" in t.lower() for t in B.texts)
    results["party_wired_through_proxy"] = party_wired
    log("T4", "PARTY/ALLIANCE via proxy:", "WIRED" if party_wired else "NOT WIRED (server has CmdInvite; port doesn't expose it)")

    # ---- TEST 5: buff each other ---------------------------------------
    # Give A (Cleric) levels + class spells, target B, cast. Look for a buff/heal
    # landing on B (combat text or a beneficial effect).
    await A.cheat("set_level", level=12)
    await A.cheat("learn_class_spells")
    await asyncio.sleep(1.0)
    buff_landed = False
    bb = B.see_player(A.charname)  # A re-find B
    a_view_b = A.see_player(B.charname)
    if a_view_b:
        B.texts.clear()
        await A.target(a_view_b.get("id"))
        # Try a few likely beneficial spells by name (Cleric buffs/heals).
        for spell in ["Minor Heal", "Bless", "Heroism", "Valor", "Healing", "Aegis"]:
            await A.use_ability(spell)
            await asyncio.sleep(1.5)
        await asyncio.sleep(2.0)
        joined = " ".join(B.texts + A.texts).lower()
        buff_landed = any(k in joined for k in ["heal", "bless", "heroism", "valor", "aegis", "feel", "blessed", "protect"])
        log("T5", "combat/effect text after casts (sample):", " | ".join((B.texts + A.texts)[:4])[:300])
    results["buff_attempt"] = buff_landed
    log("T5", "BUFF EACH OTHER:", "EFFECT SEEN" if buff_landed else "NO CLEAR EFFECT")

    # ---- summary -------------------------------------------------------
    log("SUMMARY", "=" * 50)
    for k, v in results.items():
        log("SUMMARY", "%-28s %s" % (k, "PASS/YES" if v else "no"))
    await A.ws.close(); await B.ws.close()


if __name__ == "__main__":
    asyncio.run(main())
