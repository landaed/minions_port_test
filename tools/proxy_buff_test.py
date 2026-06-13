#!/usr/bin/env python3
"""Definitive 'buff/heal each other' test.

A (Cleric) and B (Warrior) enter the same world. The test skeleton damages B;
then A targets B and casts a healing/buff spell. We watch B's health: if it
rises (or a beneficial effect lands), cross-player support casting works.
"""
import asyncio, json, time, random, string, sys
import websockets
URI = "ws://localhost:9000"
SUF = "".join(random.choice(string.ascii_lowercase) for _ in range(4))

class C:
    def __init__(self, tag, name, klass):
        self.tag=tag; self.user="Bf"+tag+SUF+str(int(time.time())%10000)
        self.name=name; self.klass=klass; self.ws=None; self.ents=[]; self.entered=False
        self.enter_sent=False; self.made=False; self.mid=None; self.texts=[]; self.spells=[]
    async def send(self,**m): await self.ws.send(json.dumps(m))
    async def go(self):
        self.ws=await websockets.connect(URI,max_size=8_000_000)
        asyncio.create_task(self.listen())
        await self.send(type="register",username=self.user,email=self.user+"@e.com",password="pw"+SUF)
        for _ in range(200):
            if self.entered: return True
            await asyncio.sleep(0.25)
        return False
    async def listen(self):
        try:
            async for raw in self.ws:
                d=json.loads(raw); mt=d.get("type","")
                if mt=="register_result" and d.get("success"):
                    await self.send(type="login",username=self.user,password=d.get("password"))
                elif mt=="world_list" and d.get("worlds"):
                    w=d["worlds"][0]
                    await self.send(type="select_world",world_name=w["name"],ip=w["ip"],port=w["port"],has_password=w.get("has_password",False))
                elif mt=="world_account_result" and d.get("success"):
                    await self.send(type="world_login",world_password=d.get("world_password"),role="Player")
                elif mt=="world_password_result" and d.get("success") and d.get("world_password"):
                    await self.send(type="world_login",world_password=d.get("world_password"),role="Player")
                elif mt=="character_list":
                    ch=d.get("characters",[])
                    if ch and not self.enter_sent:
                        self.enter_sent=True; self.name=ch[0]["name"]
                        await asyncio.sleep(1.5); await self.send(type="enter_world",character_name=self.name)
                    elif not ch and not self.made:
                        self.made=True
                        await self.send(type="create_character",name=self.name,race="Human",klass=self.klass,sex="Male",look=0,realm=1)
                elif mt=="create_character_result" and d.get("success") and not self.enter_sent:
                    self.enter_sent=True; self.name=d.get("name",self.name)
                    await asyncio.sleep(2.0); await self.send(type="enter_world",character_name=self.name)
                elif mt=="enter_world_result":
                    if "not found" in str(d.get("result","")).lower():
                        self.enter_sent=False; await asyncio.sleep(1.5); self.enter_sent=True
                        await self.send(type="enter_world",character_name=self.name)
                elif mt in ("root_info","gameplay_state"): self.entered=True
                elif mt=="entity_snapshot":
                    self.ents=d.get("entities",[])
                    for e in self.ents:
                        if e.get("is_self"): self.mid=e.get("id")
                elif mt=="spellbook":
                    self.spells=d.get("spells",[]) or d.get("entries",[])
                elif mt=="text_messages":
                    for line in d.get("messages",[]): self.texts.append(str(line))
                elif mt=="cheat_result":
                    print("[%s] cheat %s -> %s"%(self.tag,d.get("action"),d.get("success")))
        except Exception as ex: print("[%s] err %s"%(self.tag,ex))
    def find_other(self,name):
        return next((e for e in self.ents if e.get("name")==name and not e.get("is_self")),{})
    def myhp(self):
        for e in self.ents:
            if e.get("is_self"): return e.get("health"),e.get("max_health")
        return None,None
    async def cheat(self,a,**p): await self.send(type="cheat",action=a,params=p); await asyncio.sleep(1.2)
    async def target(self,eid): await self.send(type="gameplay_command",command="target_entity",entity_id=int(eid)); await asyncio.sleep(0.5)
    async def spell_slot(self,slot): await self.send(type="gameplay_command",command="spell_slot",char_id=0,slot=int(slot)); await asyncio.sleep(0.6)
    async def attack(self,eid):
        await self.send(type="gameplay_command",command="target_entity",entity_id=int(eid)); await asyncio.sleep(0.4)
        await self.send(type="gameplay_command",command="attack_toggle"); await asyncio.sleep(0.4)
    def nearest_enemy(self):
        best=None; bd=9e9
        for e in self.ents:
            if e.get("is_enemy") and not e.get("dead") and (e.get("health") or 0)>0:
                d=e.get("distance",9e9)
                if d<bd: bd=d; best=e
        return best

async def main():
    A=C("A","Heal"+SUF.capitalize(),"Cleric"); B=C("B","Tank"+SUF.capitalize(),"Warrior")
    print("entering..."); print("A",await A.go(),"B",await B.go())
    if not (A.entered and B.entered): print("ABORT"); return
    await asyncio.sleep(3)
    # Give A levels + the Cleric heal/buff list.
    await A.cheat("set_level",level=14)
    await A.cheat("learn_class_spells")
    await asyncio.sleep(1.0)
    print("A spellbook:",[ (s.get("name") if isinstance(s,dict) else s) for s in A.spells][:14])

    # Damage B: have B fight the test skeleton so its HP drops.
    print("B engages the test skeleton to take damage...")
    sk=B.nearest_enemy()
    if sk: await B.attack(sk.get("id"))
    start=time.time()
    while time.time()-start<45:
        hp,mx=B.myhp()
        if hp is not None and mx and hp < mx - 3:
            print("B damaged: hp=%.0f/%.0f"%(hp,mx)); break
        sk=B.nearest_enemy()
        if sk: await B.attack(sk.get("id"))
        await asyncio.sleep(1.5)
    hp0,mx0=B.myhp()
    print("B hp before heal: %s/%s"%(hp0,mx0))

    # A targets B and casts its beneficial spell (Minor Heal) via the spell-slot
    # cast path (spells go through onSpellSlot, NOT the SKILL command).
    bview=A.find_other(B.name)
    if not bview:
        print("A cannot see B; abort"); return
    B.texts.clear(); A.texts.clear()
    for _ in range(6):
        await A.target(bview.get("id"))
        for slot in range(4):          # try the first few spellbook slots
            await A.spell_slot(slot)
        await asyncio.sleep(2.0)
        hp,_=B.myhp()
        if hp is not None and hp0 is not None and hp>hp0+1:
            break
        bview=A.find_other(B.name) or bview
    await asyncio.sleep(2.0)
    hp1,mx1=B.myhp()
    print("B hp after heal:  %s/%s"%(hp1,mx1))
    lines=[t for t in (B.texts+A.texts)]
    healed = (hp0 is not None and hp1 is not None and hp1>hp0+1)
    # Strict: a heal actually landing (exclude "cannot use ... skill" denials).
    pos = [t for t in lines if any(k in t.lower() for k in
            ["is healed","heals ","feels better","healthier","restored","health is restored","mends"])
           and "cannot" not in t.lower()]
    cast = [t for t in lines if any(k in t.lower() for k in ["begins casting","completes","casts ","conjures"])
            and "cannot" not in t.lower()]
    print("--- relevant text ---")
    for t in lines:
        if any(k in t.lower() for k in ["heal","cast","cannot","mend","restore"]):
            print("  ",t[:160])
    verdict = "WORKS" if (healed or pos) else ("CAST OK (effect unconfirmed)" if cast else "NOT OBSERVED")
    print("\nRESULT: B_HP %s->%s (increased=%s)  heal_text=%s  cast_text=%s  => buff/heal another player: %s"%(
        hp0, hp1, healed, bool(pos), bool(cast), verdict))
    await A.ws.close(); await B.ws.close()

asyncio.run(main())
