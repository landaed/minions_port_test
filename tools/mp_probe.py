#!/usr/bin/env python3
"""Focused 2-client probe: raw entity structure, equip-on-other-player, movement."""
import asyncio, json, time, random, string, sys
sys.path.insert(0, "tools")
import websockets
URI = "ws://localhost:9000"
SUF = "".join(random.choice(string.ascii_lowercase) for _ in range(4))

class C:
    def __init__(self, tag, name, klass):
        self.tag=tag; self.user="Pb"+tag+SUF+str(int(time.time())%10000)
        self.name=name; self.klass=klass; self.ws=None; self.ents=[]; self.entered=False
        self.enter_sent=False; self.made=False; self.mid=None
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
                    r=str(d.get("result","") or "")
                    if "not found" in r.lower():
                        self.enter_sent=False
                        await asyncio.sleep(1.5); self.enter_sent=True
                        await self.send(type="enter_world",character_name=self.name)
                elif mt in ("root_info","gameplay_state"): self.entered=True
                elif mt=="entity_snapshot":
                    self.ents=d.get("entities",[])
                    for e in self.ents:
                        if e.get("is_self"): self.mid=e.get("id")
                elif mt=="cheat_result":
                    print("[%s] cheat %s -> %s %s"%(self.tag,d.get("action"),d.get("success"),str(d.get("message",""))[:70]))
        except Exception as ex:
            print("[%s] listen err %s"%(self.tag,ex))
    def find(self,name):
        # return ALL entities matching a player name
        return [e for e in self.ents if e.get("name")==name]
    async def cheat(self,a,**p): await self.send(type="cheat",action=a,params=p); await asyncio.sleep(1.3)
    async def move(self,s):
        await self.send(type="gameplay_command",command="player_input",move_x=0.0,move_y=1.0,forward=[0.0,1.0,0.0],jump=False)
        await asyncio.sleep(s)
        await self.send(type="gameplay_command",command="player_input",move_x=0.0,move_y=0.0,forward=[0.0,1.0,0.0],jump=False)

def dump(tag, ents):
    print("--- %s sees %d entities ---"%(tag,len(ents)))
    for e in ents:
        print("   id=%s sim=%s self=%s player=%s name=%-12s pos=%s mounts=%s tex=%d"%(
            e.get("id"),e.get("sim_id"),int(bool(e.get("is_self"))),int(bool(e.get("is_player"))),
            e.get("name"),[round(x,1) for x in e.get("position",[])[:3]],
            {k:(v.get("model","?") if isinstance(v,dict) else v) for k,v in (e.get("mounts") or {}).items()},
            len(e.get("tex") or {})))

async def main():
    A=C("A","Alpha"+SUF.capitalize(),"Cleric"); B=C("B","Bravo"+SUF.capitalize(),"Warrior")
    print("entering..."); print("A",await A.go(),"B",await B.go())
    if not (A.entered and B.entered): print("ABORT"); return
    await asyncio.sleep(4)
    print("\n=== RAW ENTITIES (A's snapshot) ==="); dump("A",A.ents)

    print("\n=== MOVEMENT: A's own self pos before/after walking ===")
    def selfpos(c):
        for e in c.ents:
            if e.get("is_self"): return [round(x,1) for x in e.get("position",[])[:3]]
        return None
    print("A self before:",selfpos(A))
    await A.move(5.0); await asyncio.sleep(2)
    print("A self after :",selfpos(A))
    bview=[e for e in B.find(A.name) if not e.get("is_self")]
    print("B's view(s) of A pos:",[[round(x,1) for x in e.get("position",[])[:3]] for e in bview])

    print("\n=== EQUIPMENT: B equips, then A's view of B ===")
    print("B mounts (B's own self) BEFORE:",[ {k:v.get('model') for k,v in (e.get('mounts') or {}).items()} for e in B.find(B.name) if e.get("is_self")])
    for it in ["Tower Shield","Plain Helm","Longsword"]:
        await B.cheat("give_item",name=it,equip=True)
    await asyncio.sleep(4)
    print("B mounts (B's own self) AFTER :",[ {k:v.get('model') for k,v in (e.get('mounts') or {}).items()} for e in B.find(B.name) if e.get("is_self")])
    aview=[e for e in A.find(B.name) if not e.get("is_self")]
    print("A's view of B mounts AFTER:",[ {k:v.get('model') for k,v in (e.get('mounts') or {}).items()} for e in aview])
    await A.ws.close(); await B.ws.close()

asyncio.run(main())
