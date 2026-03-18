#!/bin/bash
# Launches all Minions of Mirth servers in separate terminal windows.
# Usage: ./start_servers.sh
#
# Supports: gnome-terminal, xfce4-terminal, konsole, xterm (tries in order)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Detect virtual environment
if [ -d "venv" ]; then
    ACTIVATE="source venv/bin/activate && "
elif [ -d ".venv" ]; then
    ACTIVATE="source .venv/bin/activate && "
else
    ACTIVATE=""
fi

# Server commands
declare -A SERVERS
SERVERS=(
    ["1-MasterServer"]="${ACTIVATE}python3 MasterServer.py gameconfig=mom.cfg"
    ["2-GMServer"]="${ACTIVATE}python3 GMServer.py gameconfig=mom.cfg"
    ["3-CharacterServer"]="${ACTIVATE}python3 CharacterServer.py gameconfig=mom.cfg"
    ["4-WorldDaemon"]="${ACTIVATE}python3 WorldDaemon.py gameconfig=mom.cfg -worldname=TestDaemon -publicname=TestWorld -password=mmo"
    ["5-ClientProxy"]="${ACTIVATE}python3 ClientProxy.py gameconfig=mom.cfg"
)

# Find a terminal emulator
launch_terminal() {
    local title="$1"
    local cmd="$2"

    if command -v gnome-terminal &>/dev/null; then
        gnome-terminal --title="$title" -- bash -c "cd '$SCRIPT_DIR' && $cmd; echo '--- Press Enter to close ---'; read"
    elif command -v xfce4-terminal &>/dev/null; then
        xfce4-terminal --title="$title" -e "bash -c \"cd '$SCRIPT_DIR' && $cmd; echo '--- Press Enter to close ---'; read\""
    elif command -v konsole &>/dev/null; then
        konsole --new-tab -p tabtitle="$title" -e bash -c "cd '$SCRIPT_DIR' && $cmd; echo '--- Press Enter to close ---'; read"
    elif command -v xterm &>/dev/null; then
        xterm -T "$title" -e bash -c "cd '$SCRIPT_DIR' && $cmd; echo '--- Press Enter to close ---'; read" &
    else
        echo "No supported terminal emulator found. Run servers manually."
        exit 1
    fi
}

echo "Starting Minions of Mirth servers..."
echo "Working directory: $SCRIPT_DIR"
echo ""

# Launch in order with small delays so they register properly
for key in $(echo "${!SERVERS[@]}" | tr ' ' '\n' | sort); do
    name="${key#*-}"
    cmd="${SERVERS[$key]}"
    echo "Launching $name..."
    launch_terminal "$name" "$cmd"
    sleep 2
done

echo ""
echo "All servers launched!"
echo "  - MasterServer  (port 2010)"
echo "  - GMServer"
echo "  - CharacterServer"
echo "  - WorldDaemon -> WorldServer (port 2008)"
echo "  - ClientProxy (ws://localhost:9000)"
