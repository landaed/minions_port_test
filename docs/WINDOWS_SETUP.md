# Running the Godot port on Windows

This is the **modern (Godot + Python 3)** way to run the project on Windows.
It is self-contained: the original game data ships in the `MoMReborn/` folder in
this repo, so you do **not** need to buy or install the old Minions of Mirth
client. (The old Python-2 / Torque instructions in the top-level `README.md` are
for the *legacy* client and are superseded by this guide.)

The stack is:

```
 Godot 4.6 client  ──ws://localhost:9000──►  ClientProxy.py  ──►  MoM servers
 (minions-port/)        (WebSocket)          (bridge)             (Master/GM/
                                                                   Character/World)
```

## 0. Prerequisites (install once)

1. **Python 3.11 or newer** — https://www.python.org/downloads/
   During install **tick "Add python.exe to PATH"**.
   (Verified on 3.11; 3.12/3.13 also have wheels for every dependency.)
2. **Godot 4.6 — Standard edition** (NOT .NET/Mono) —
   https://godotengine.org/download/windows/
   It's a single `Godot_v4.6-stable_win64.exe`; no installer.
3. You already cloned the repo. Use a path **without spaces** if you hit any
   tooling quirks (the legacy code is old).

## 1. One-time setup

Open **Command Prompt** in the repo root and run:

```bat
setup_windows.bat
```

That script creates a `venv`, installs the server dependencies, and builds the
runtime databases from the bundled `MoMReborn` baseline. It is equivalent to:

```bat
python -m venv venv
venv\Scripts\activate
pip install "Twisted>=22,<24" sqlobject pyopenssl service_identity bcrypt pyasn1
pip install --no-deps autobahn txaio hyperlink
pip install websockets            REM only needed for the headless test clients
python setup_databases.py --worldname=TestDaemon
```

If the databases ever get into a weird state (e.g. "can't load into world"),
rebuild them from scratch with:

```bat
venv\Scripts\python setup_databases.py --reset --worldname=TestDaemon
```

## 2. Start the servers

```bat
run_servers.bat
```

This opens **five console windows** — MasterServer, GMServer, CharacterServer,
WorldDaemon and ClientProxy. Leave them running. Ports:

| Server        | Port                 |
|---------------|----------------------|
| Master        | 2002                 |
| GM            | 2003                 |
| World         | 2008                 |
| **ClientProxy** | **ws://localhost:9000** (the Godot client connects here) |

`run_servers.bat` sets `MOM_ENABLE_CHEATS=1` so the in-game testing cheat window
works. Set it to `0` in the script to play without cheats.

To stop everything, close the five windows (or Ctrl+C in each).

## 3. Launch the game client

1. Start Godot 4.6, click **Import**, and select the `minions-port` folder
   (pick its `project.godot`). Let it import once.
2. Press **Play (F5)**.

On Windows the renderer uses Direct3D 12 (`project.godot` →
`rendering_device/driver.windows="d3d12"`), so you get full GPU rendering.

## 4. Create an account and play

The login screen walks you through 4 steps:

1. **Register / Log in.** Type a username + password and click **Register**
   (you may choose your own master password — type it before clicking Register,
   or leave it blank for a random one). Then **Log in**.
2. **Choose world** — select `TestWorld` / `TestDaemon` and join. (The per-world
   account is created and logged into automatically.)
3. **Character slot** — pick the slot.
4. **Pick / create a character** — name (4–11 letters), race, class, then
   **Enter World**.

### In-game keys
- **`` ` `` (backquote)** — open the **cheat window** (give XP / set level /
  give + auto-equip items / learn spells / full heal). Handy for testing.
  *(F8 also opens it in a standalone build, but F8 is "Stop" when the game runs
  embedded in the Godot editor.)*
- **W A S D** move, mouse look, **Q** toggle auto-attack, **Tab** cycle target,
  **1–0** hotbar, **F3** debug overlay.

## 5. Playing with other people (multiplayer)

Every Godot client that connects to the same `ClientProxy` enters the same world
and **sees the others** (movement, combat, equipment, summoned pets and parties
are all replicated). Only **one machine hosts** the servers; everyone else just
runs the client and points it at the host.

### Architecture (why only one port matters)

```
 your friend's PC                 the HOST PC (runs run_servers)
 ┌──────────────┐  ws://HOST:9000 ┌─────────────────────────────────────┐
 │ Godot client │ ───────────────▶│ ClientProxy :9000                   │
 └──────────────┘   (internet)    │   └─ talks to Master/World on        │
                                   │      127.0.0.1 (local to the host)   │
                                   └─────────────────────────────────────┘
```

The client only ever talks to the **proxy (port 9000)**. The proxy reaches the
Master (2002) and World (2008) servers locally on the host, so **only port 9000
needs to be reachable from the internet** — you do *not* port-forward 2002/2008.

### Host setup (the person running the servers)

1. Run `run_servers.bat` (or `./run_servers.sh`). The proxy now binds to
   **all interfaces** (`0.0.0.0:9000`) by default, so it accepts remote clients.
   *(Override with `MOM_PROXY_PORT` / `MOM_PROXY_BIND` env vars if needed.)*
2. **Same LAN (you + friends on the same router/Wi-Fi):** find the host's local
   IP (`ipconfig` on Windows → e.g. `192.168.1.20`). Allow the app through
   Windows Firewall (or open TCP **9000**). Friends connect to `192.168.1.20`.
3. **Over the internet:** on the host's router, **port-forward external TCP 9000
   → the host PC's local IP : 9000**. Friends connect to the host's **public IP**
   (find it at e.g. whatismyip.com → `203.0.113.7`). A static IP / dynamic-DNS
   name makes this stable. (No router access? A VPN like Tailscale/ZeroTier, or
   an SSH/`ngrok tcp 9000` tunnel, also works — friends connect to the tunnel
   address.)

### Client setup (everyone, including remote players)

1. Launch the Godot client. On the **Step 1 login screen** there is now a
   **Server** field at the top and a **Connect** button.
2. Type the host's address and click **Connect**:
   - blank → `localhost` (you're hosting on this same PC)
   - `192.168.1.20` → same-LAN host (defaults to port 9000)
   - `203.0.113.7` or `203.0.113.7:9000` → internet host
   - a hostname like `myserver.duckdns.org` also works
   The status line shows "Connected to ws://…". The address is remembered
   between sessions.
3. Register your own account, pick the world, create a character, Enter World.
   Walk up to your friends and party up (target them, press **G** to invite).

> ⚠️ Security: this is decade-old game-server code with no transport encryption.
> Only expose port 9000 to people you trust, and prefer a VPN/tunnel over a raw
> public port-forward. See the warning in the top-level `README.md`.

## Three passwords (this confuses everyone)

Legacy MoM has three independent credentials; the port hides #2 and #3 from you:

| Password | Set where | Used for |
|----------|-----------|----------|
| **Master account password** | chosen by you (or random) at Register | logging into the Master server |
| World *access* password | `serverconfig/<World>.py` → `PLAYERPASSWORD` (default `mmo`) | gate to create a world account (handled automatically) |
| World *account* password | auto-generated per world | logging into the world (handled automatically) |

You only ever type the **master account password**.

## Troubleshooting

- **Client says it can't connect** → the ClientProxy window isn't up, or you
  skipped `run_servers.bat`. Confirm `ws://localhost:9000` is listening.
- **"no such table: user" / Master crashes** → the DB wasn't built; run
  `setup_windows.bat` (or `setup_databases.py`).
- **`ModuleNotFoundError: No module named 'pywintypes'`** (Master/GM/Character
  server) → fixed: the servers no longer force the Windows IOCP reactor; they
  fall back to the default reactor. `git pull` to get the fix. *(Optional: for
  IOCP performance install `pip install pywin32`.)*
- **`WinError 123 ... syntax is incorrect: ''`** (WorldDaemon) or the World
  server never spawns → fixed: Windows `chdir`/path and the world-server spawn
  (no more `os.system('start …')`) are corrected. `git pull`.
- **`Port could not be cast to integer`** during DB setup → fixed Windows SQLite
  path; `git pull` then `setup_databases.py --reset`.
- **Enter-world hangs / character missing after code or schema changes** →
  `venv\Scripts\python setup_databases.py --reset`.
- **No terminal/headless box?** You can run the servers under WSL or Git-Bash
  with `./run_servers.sh` instead of the `.bat`.

## Headless smoke test (no Godot needed)

With the servers up, you can verify the whole gameplay path from the command
line — these drive the proxy exactly like the Godot client does:

```bat
venv\Scripts\python tools\proxy_integration_test.py   REM login->char->enter->move->mob follows
venv\Scripts\python tools\proxy_multiplayer_test.py   REM two clients see each other + equipment
venv\Scripts\python tools\proxy_pet_test.py           REM summon a pet, it follows
```
