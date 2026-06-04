#!/bin/bash
# Stops all Minions of Mirth servers started by run_servers.sh.
set -u
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PIDFILE="logs/servers.pids"

# The WorldDaemon spawns WorldServer.py as a *child* process that is not in the
# pidfile, so match it (and the daemon) by command line as well.
echo "[stop] Stopping WorldServer child process(es)..."
pkill -f "WorldServer.py" 2>/dev/null && echo "[stop]   killed WorldServer.py"

if [ -f "$PIDFILE" ]; then
    while read -r name pid; do
        [ -z "${pid:-}" ] && continue
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null && echo "[stop] Stopped ${name} (pid ${pid})"
        fi
    done < "$PIDFILE"
    rm -f "$PIDFILE"
else
    echo "[stop] No pidfile; falling back to pattern matching."
    for n in ClientProxy.py WorldDaemon.py CharacterServer.py GMServer.py MasterServer.py; do
        pkill -f "$n" 2>/dev/null && echo "[stop]   killed $n"
    done
fi

echo "[stop] Done."
