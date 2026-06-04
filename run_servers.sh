#!/bin/bash
# Headless launcher for all Minions of Mirth servers.
#
# Unlike start_servers.sh (which opens a GUI terminal window per server and is
# useless over SSH / in a container), this runs every server as a background
# process, writes logs to logs/<name>.log, and records PIDs in logs/servers.pids
# so stop_servers.sh can shut everything down cleanly.
#
# Usage:
#   ./run_servers.sh            # start the whole stack
#   ./run_servers.sh --setup    # (re)create databases first, then start
#   ./stop_servers.sh           # stop everything
#
# Tail a server:  tail -f logs/ClientProxy.log   (or MasterServer.log, etc.)

set -u
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

WORLDNAME="TestDaemon"
PUBLICNAME="TestWorld"
WORLDPASS="mmo"
GAMECONFIG="gameconfig=mom.cfg"

PYTHON="${PYTHON:-python3}"
# Activate a virtualenv if one is present.
if [ -z "${VIRTUAL_ENV:-}" ]; then
    if [ -f "venv/bin/activate" ]; then source venv/bin/activate; PYTHON=python3
    elif [ -f ".venv/bin/activate" ]; then source .venv/bin/activate; PYTHON=python3
    fi
fi

mkdir -p logs
PIDFILE="logs/servers.pids"
: > "$PIDFILE"

# Parse flags (order-independent): --setup [--reset], --test-zone
DO_SETUP=""
RESET_FLAG=""
for arg in "$@"; do
    case "$arg" in
        --setup) DO_SETUP=1 ;;
        --reset) DO_SETUP=1; RESET_FLAG="--reset" ;;
        --test-zone) export MOM_TEST_ZONE=1 ;;
    esac
done

if [ -n "$DO_SETUP" ]; then
    echo "[run] Setting up databases for world '$WORLDNAME' $RESET_FLAG..."
    "$PYTHON" setup_databases.py $RESET_FLAG --worldname="$WORLDNAME" || { echo "[run] setup failed"; exit 1; }
fi

if [ -n "${MOM_TEST_ZONE:-}" ]; then
    echo "[run] MOM_TEST_ZONE=1 — running a light test zone (player + 3 skeletons, no background spawns)"
fi

# Bail out early if the master DB is missing/empty (common first-run mistake).
if [ ! -s "data/master/master.db" ]; then
    echo "[run] data/master/master.db is missing or empty."
    echo "[run] Run once with:  ./run_servers.sh --setup"
    exit 1
fi

# Wait until a TCP port can be bound (a just-killed WorldServer may still hold
# it for a moment, which otherwise crashes the freshly spawned one).
wait_port_free() {
    local port="$1"
    for _ in $(seq 1 30); do
        if "$PYTHON" -c "import socket,sys
s=socket.socket()
try:
    s.bind(('0.0.0.0',$port)); s.close()
except OSError:
    sys.exit(1)" 2>/dev/null; then
            return 0
        fi
        echo "[run] waiting for port $port to free up..."
        sleep 0.5
    done
    echo "[run] WARNING: port $port still in use after 15s"
}

# start_server <name> <readiness-substring> <command...>
start_server() {
    local name="$1"; shift
    local ready="$1"; shift
    local log="logs/${name}.log"
    echo "[run] Starting ${name}..."
    nohup "$@" > "$log" 2>&1 &
    local pid=$!
    echo "${name} ${pid}" >> "$PIDFILE"
    # Wait (up to ~20s) for the readiness string before moving on.
    if [ -n "$ready" ]; then
        for _ in $(seq 1 40); do
            if ! kill -0 "$pid" 2>/dev/null; then
                echo "[run] ERROR: ${name} exited early. Last log lines:"; tail -n 8 "$log"; return 1
            fi
            if grep -q "$ready" "$log" 2>/dev/null; then
                echo "[run]   ${name} ready (pid ${pid})"; return 0
            fi
            sleep 0.5
        done
        echo "[run]   ${name} started (pid ${pid}) [readiness '${ready}' not seen yet; continuing]"
    fi
}

start_server MasterServer    "Server is up"            "$PYTHON" MasterServer.py    "$GAMECONFIG"
start_server GMServer        "GM Server is up"         "$PYTHON" GMServer.py        "$GAMECONFIG"
start_server CharacterServer "Character Server is up"  "$PYTHON" CharacterServer.py "$GAMECONFIG"
wait_port_free 2008
start_server WorldDaemon     "Zone Cluster 0 is live"  "$PYTHON" WorldDaemon.py     "$GAMECONFIG" \
    -worldname="$WORLDNAME" -publicname="$PUBLICNAME" -password="$WORLDPASS"
start_server ClientProxy     "Proxy is up"             "$PYTHON" ClientProxy.py     "$GAMECONFIG"

echo ""
echo "[run] All servers launched. PIDs in $PIDFILE"
echo "[run]   Master 2002 | GM 2003 | World 2008 | Proxy ws://localhost:9000"
echo "[run] Logs: logs/<ServerName>.log   (WorldServer child logs: logs/ZoneCluster0.txt)"
echo "[run] Stop with: ./stop_servers.sh"
