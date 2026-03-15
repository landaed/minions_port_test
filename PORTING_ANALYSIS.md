# Minions of Mirth Server — Ubuntu Porting Analysis

## Executive Summary

**Good news: pytorque/pytge is NOT the main blocker.** It is only used by `zoneserver.py`
(the individual zone simulation processes). The entire management/orchestration layer
(MasterServer, CharacterServer, WorldDaemon, GMServer) is **pure Python + Twisted** and
can run on Linux without any Torque dependency.

**The actual blocker** is the missing `mud/` Python package — the TMMOKit framework library.
It is not in this repo, but exists as pure Python in the
[solinia fork](https://github.com/mixxit/solinia_depreciated/tree/master/mud) and can be
obtained from the [Internet Archive TMMOKit download](https://archive.org/details/tmmokit).

---

## 1. Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                    MANAGEMENT LAYER                          │
│              (Pure Python + Twisted PB)                      │
│                  NO pytorque dependency                      │
│                                                              │
│  ┌──────────────┐  ┌──────────────────┐  ┌───────────────┐  │
│  │ MasterServer │  │ CharacterServer  │  │   GMServer    │  │
│  │  port 2002   │  │  (connects to    │  │  port 2003    │  │
│  │              │  │   master+worlds) │  │               │  │
│  └──────┬───────┘  └────────┬─────────┘  └───────┬───────┘  │
│         │                   │                     │          │
│  ┌──────┴───────────────────┴─────────────────────┴───────┐  │
│  │                    WorldDaemon                         │  │
│  │              port 7000 (world services)                │  │
│  │              port 7001 (char services)                 │  │
│  │              port 7002 (manhole/admin)                 │  │
│  │         Process manager: spawns WorldServer            │  │
│  └──────────────────────┬────────────────────────────────┘  │
│                         │ spawns                             │
└─────────────────────────┼────────────────────────────────────┘
                          │
┌─────────────────────────┼────────────────────────────────────┐
│                    SIMULATION LAYER                          │
│                                                              │
│  ┌──────────────────────┴────────────────────────────────┐   │
│  │              WorldServer.py                           │   │
│  │   (Pure Python + Twisted PB — game world logic)       │   │
│  │   Manages zones, players, world state                 │   │
│  │   Connects back to WorldDaemon on port 7000           │   │
│  │   NO pytorque dependency                              │   │
│  └──────────────────────┬────────────────────────────────┘   │
│                         │ spawns                              │
│  ┌──────────────────────┴────────────────────────────────┐   │
│  │              zoneserver.py                             │   │
│  │   *** ONLY FILE USING pytorque/pytge ***               │   │
│  │   Runs Torque engine tick loop for zone simulation     │   │
│  │   Provides: physics, AI, combat, client networking     │   │
│  └───────────────────────────────────────────────────────┘   │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

## 2. pytorque/pytge Dependency Map

### What pytorque.py actually is
```python
# pytorque.py — the entire file:
from pytge import *
```
It's just a re-export of `pytge`, the Torque Game Engine compiled as a `.pyd` (Windows Python C extension).

### Where pytorque/pytge is used — ONLY in zoneserver.py

| Function | File | Line | Purpose |
|----------|------|------|---------|
| `pytorque.Init(sys.argv)` | zoneserver.py | 174 | Initialize Torque engine with CLI args |
| `pytorque.Tick()` | zoneserver.py | 199 | Main game loop — tick the engine |
| `pytorque.Shutdown()` | zoneserver.py | 224 | Clean shutdown of engine |
| `TGEGetGlobal()` | zoneserver.py | 190 | Read Torque console variable (from `tgenative`) |
| `TGESetGlobal()` | zoneserver.py | 190,196,204 | Set Torque console variable (from `tgenative`) |

### Where pytorque is NOT used
- MasterServer.py — **NO** pytorque
- CharacterServer.py — **NO** pytorque
- WorldDaemon.py — **NO** pytorque
- WorldServer.py — **NO** pytorque (despite the name!)
- GMServer.py — **NO** pytorque
- WorldManager.py — **NO** pytorque
- All of mud_ext/ — **NO** pytorque (0 imports across 70+ files)

### What pytge actually provides (the Torque engine runtime)
- **Game loop tick** — frame update for physics, AI, rendering (server-side)
- **Client networking** — Torque's proprietary UDP protocol for ghosting/object replication
- **Console system** — TGEGetGlobal/TGESetGlobal for engine configuration
- **Zone simulation** — the actual game world: NPCs, combat, movement, spawning
- **TorqueScript bridge** — executes .cs scripts for game logic

## 3. The `mud` Package — The Real Blocker

The `mud/` package is the **TMMOKit Python framework**. It is NOT in this repo but is
required by every server component. It is **pure Python** (Twisted + SQLObject ORM).

### Source
Available at: https://github.com/mixxit/solinia_depreciated/tree/master/mud

### What it provides

| Module | Used By | Purpose |
|--------|---------|---------|
| `mud.gamesettings` | ALL servers | Config: MASTERIP, MASTERPORT, GAMEROOT, etc. |
| `mud.server.app.Server` | MasterServer, WorldServer, GMServer | Twisted PB server wrapper with auth |
| `mud.common.persistent` | MasterServer, WorldServer | SQLObject ORM base class for SQLite |
| `mud.common.avatar` | MasterServer, GMServer | Twisted PB Avatar base class |
| `mud.common.permission` | MasterServer, GMServer, WorldServer | Role/User auth models (SQLObject) |
| `mud.common.dbconfig` | Config, WorldServer | SQLite connection setup |
| `mud.world.defines` | WorldServer, many mud_ext modules | RPG constants (message types, etc.) |
| `mud.world.theworld` | WorldServer | World singleton — manages zones, players |
| `mud.world.core` | WorldServer, zoneserver | CoreSettings, game configuration |
| `mud.world.shared.worlddata` | MasterServer, WorldManager | WorldConfig, WorldInfo data classes |
| `mud.world.*` | WorldServer, worlddocs | Game data models (items, spells, NPCs, etc.) |
| `mud.simulation.simmind` | zoneserver.py ONLY | NumPlayersInZone — simulation layer |
| `mud.worldserver.charutil` | WorldServer | Character buffer management |
| `mud.utils` | Config | getSQLiteURL helper |

### Files importing from `mud.*`

44 files across the codebase import from `mud.*`. The heaviest users:
- `mud_ext/worldserver/main.py` — 15 imports
- `mud_ext/masterserver/main.py` — 9 imports
- `mud_ext/characterserver/upgradedb.py` — 8 imports

## 4. Networking / Protocol Analysis

### Server-to-Server: Twisted Perspective Broker (PB)
ALL inter-server communication uses **Twisted PB** over TCP. This is a Python-native RPC
protocol — no Torque involvement.

| Connection | Port | Protocol | Auth |
|-----------|------|----------|------|
| Client → MasterServer | 2002 | Twisted PB | Username + MD5(password) |
| Client → WorldServer | dynamic | Twisted PB | "NewPlayer" role |
| CharacterServer → MasterServer | 2002 | Twisted PB | "CharacterServer" user |
| WorldServer → WorldDaemon | 7000 | Twisted PB | cluster# + MD5("daemon") |
| CharacterServer → WorldDaemon | 7001 | Twisted PB | username + MD5(password) |
| WorldDaemon → MasterServer | 2002 | Twisted PB | "username-World" |
| WorldDaemon → GMServer | 2003 | Twisted PB | worlddaemon user |
| GMTool → GMServer | 2003 | Twisted PB | GM credentials |

### Client → Zone: Torque Protocol (via pytge)
The actual game client connects to zone servers using the **Torque network protocol**:
- **UDP-based** with reliability layer
- **Object ghosting** — server replicates game objects to client
- **Move events** — client sends input, server validates
- **RPC** — TorqueScript `commandToServer`/`commandToClient`
- This is the part that requires pytge and would need replacement for a Godot client

### Client Login Flow
```
1. Client → MasterServer (PB): Register/Login, enumerate worlds
2. Client → MasterServer (PB): submitPlayerToWorld(worldName)
3. MasterServer → CharacterServer (PB): installPlayer(name, world)
4. CharacterServer → WorldServer (PB): installPlayer(name, buffer, ...)
5. Client → WorldServer (PB): Connect as "NewPlayer", create/select character
6. WorldServer assigns zone → Client connects to ZoneServer
7. Client ↔ ZoneServer: Torque UDP protocol (gameplay)
```

## 5. Recommended Porting Path

### Phase 1: Get management servers running (LOW effort)
**Goal:** MasterServer, CharacterServer, WorldDaemon, GMServer start on Ubuntu

1. **Obtain the `mud/` package** from the solinia fork or TMMOKit archive
   - Copy it into the repo root as `mud/`
   - It's pure Python, should work as-is

2. **Fix Python 2 → 3 issues** (or use Python 2.7 initially):
   - `print` statements → `print()` functions
   - `xrange` → `range`
   - `has_key()` → `in` operator
   - `md5` module → `hashlib.md5`
   - `cPickle` → `pickle`
   - `string.letters` → `string.ascii_letters`
   - `ConfigParser` → `configparser`
   - `thread` → `_thread`
   - `imp` module → `importlib`
   - SQLObject unicode handling

3. **Fix platform-specific code**:
   - `win32api`/`win32process` imports already have `try/except ImportError` guards
   - `iocpreactor` → already falls back to other reactors on non-Windows
   - `wx` imports are behind `USE_WX` flags — can skip GUI for headless
   - `os.system('start ...')` in worldservices.py needs Linux equivalent

4. **Fix reactor selection** for headless Linux:
   - Several files default to `wxreactor` on non-Windows
   - Need to use `selectreactor` or `epollreactor` instead when not using GUI

5. **Create missing directories**: `data/master/`, `data/character/`, etc.

### Phase 2: Stub out zoneserver.py (MEDIUM effort)
**Goal:** WorldDaemon can "spawn" zone processes that connect back

- Create a `pytorque_stub.py` that provides `Init()`, `Tick()`, `Shutdown()` as no-ops
- Create a `tgenative_stub.py` with `TGEGetGlobal`/`TGESetGlobal` as dict-backed stubs
- The zone won't simulate anything, but the management layer will think zones are live

### Phase 3: Replace Torque zone simulation (HIGH effort, long-term)
**Goal:** Game logic runs without Torque engine

Options (in order of preference):
1. **Rewrite zone server in pure Python** — the `mud.simulation` and `mud.world` modules
   already contain most game logic in Python. The Torque engine mainly provides:
   - Tick scheduling (trivially replaceable)
   - TorqueScript execution (would need to port remaining .cs scripts)
   - Network ghosting (replace with custom protocol)

2. **Build pytge as .so from source** — TMMOKit C++ source is available as a patch against
   Torque Game Engine. Could theoretically compile for Linux, but this is fragile and
   ties you to the old engine.

### Phase 4: Godot client (SEPARATE track)
The Godot client needs to speak:
1. **Twisted PB** for login/character selection (Python-native protocol, well-documented)
2. **Custom game protocol** to replace Torque UDP ghosting (design from scratch)

The Twisted PB protocol is documented at:
https://docs.twisted.org/en/stable/core/howto/pb-usage.html

Key PB concepts for the Godot client:
- AMP or PB-compatible protocol in GDScript/C++
- `callRemote()` for RPC
- `perspective_*` methods are the server API
- MD5 password hashing for auth

## 6. Immediate Next Steps

1. **Clone the `mud/` package** from solinia fork into this repo
2. **Fix reactor selection** — use `selectreactor` on Linux when no GUI
3. **Run MasterServer.py** — fix import errors iteratively
4. **Run CharacterServer.py** — needs master server running
5. **Run WorldDaemon.py** — needs master + character servers
6. **Create pytorque/tgenative stubs** — minimal zone server skeleton

## 7. Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| `mud/` package version mismatch with MoM server | Medium | Solinia fork is TMMOKit 1.3 based, same as MoM |
| Python 2→3 migration in `mud/` package | Medium | Can run Python 2.7 initially |
| SQLite schema differences | Low | Schema is defined by SQLObject models |
| Twisted version compatibility | Medium | requirements.txt says 10.1.0, modern Twisted has breaking changes |
| Missing game data files | Low | `data/` directory needs world.db etc from game install |
| wx dependency for GUI servers | Low | Already guarded behind USE_WX flag |
