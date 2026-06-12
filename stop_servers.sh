#!/bin/bash
# Stops all Minions of Mirth servers started by run_servers.sh.
#
# Order matters for not losing player data:
#   1. ClientProxy first — dropping the websocket/PB connections makes the
#      world log every player out (which saves positions and ships the
#      player/character buffers to the character server).
#   2. WorldServer next (SIGTERM) and WAIT for it to exit — its shutdown
#      handler finishes any remaining buffer saves and commits the world DB.
#   3. Only then the daemon/character/master/GM servers, so the character
#      server is still alive to receive those final saves.
set -u
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PIDFILE="logs/servers.pids"

kill_by_name_from_pidfile() {
    local target="$1"
    if [ -f "$PIDFILE" ]; then
        while read -r name pid; do
            [ "$name" = "$target" ] || continue
            [ -z "${pid:-}" ] && continue
            kill "$pid" 2>/dev/null && echo "[stop] Stopped ${name} (pid ${pid})"
        done < "$PIDFILE"
    fi
}

echo "[stop] Stopping ClientProxy (lets the world log players out cleanly)..."
kill_by_name_from_pidfile ClientProxy
pkill -f "ClientProxy.py" 2>/dev/null
# Give the world a moment to process the disconnect logouts and ship buffers.
sleep 2

# The WorldDaemon spawns WorldServer.py as a *child* process that is not in the
# pidfile, so match it by command line.
echo "[stop] Stopping WorldServer child process(es)..."
pkill -f "WorldServer.py" 2>/dev/null && echo "[stop]   sent SIGTERM to WorldServer.py"

# Wait for the world server to fully exit: its shutdown handler is still
# delivering final player saves to the character server, and an immediate
# restart would otherwise hit "Address already in use".
for _ in $(seq 1 30); do
    pgrep -f "WorldServer.py" >/dev/null 2>&1 || break
    sleep 0.5
done
if pgrep -f "WorldServer.py" >/dev/null 2>&1; then
    echo "[stop] WorldServer still alive after 15s; killing hard."
    pkill -9 -f "WorldServer.py" 2>/dev/null
fi

if [ -f "$PIDFILE" ]; then
    while read -r name pid; do
        [ -z "${pid:-}" ] && continue
        [ "$name" = "ClientProxy" ] && continue
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null && echo "[stop] Stopped ${name} (pid ${pid})"
        fi
    done < "$PIDFILE"
    rm -f "$PIDFILE"
else
    echo "[stop] No pidfile; falling back to pattern matching."
    for n in WorldDaemon.py CharacterServer.py GMServer.py MasterServer.py; do
        pkill -f "$n" 2>/dev/null && echo "[stop]   killed $n"
    done
fi

echo "[stop] Done."
