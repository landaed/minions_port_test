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

# Optional database (re)setup.
if [ "${1:-}" = "--setup" ]; then
    echo "[run] Setting up databases for world '$WORLDNAME'..."
    "$PYTHON" setup_databases.py --worldname="$WORLDNAME" || { echo "[run] setup failed"; exit 1; }
fi

# Bail out early if the master DB is missing/empty (common first-run mistake).
if [ ! -s "data/master/master.db" ]; then
    echo "[run] data/master/master.db is missing or empty."
    echo "[run] Run once with:  ./run_servers.sh --setup"
    exit 1
fi

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
start_server WorldDaemon     "Zone Cluster 0 is live"  "$PYTHON" WorldDaemon.py     "$GAMECONFIG" \
    -worldname="$WORLDNAME" -publicname="$PUBLICNAME" -password="$WORLDPASS"
start_server ClientProxy     "Proxy is up"             "$PYTHON" ClientProxy.py     "$GAMECONFIG"

echo ""
echo "[run] All servers launched. PIDs in $PIDFILE"
echo "[run]   Master 2002 | GM 2003 | World 2008 | Proxy ws://localhost:9000"
echo "[run] Logs: logs/<ServerName>.log   (WorldServer child logs: logs/ZoneCluster0.txt)"
echo "[run] Stop with: ./stop_servers.sh"
