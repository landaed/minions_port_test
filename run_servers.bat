@echo off
REM ===================================================================
REM  Minions of Mirth (Godot port) - start the whole server stack on
REM  Windows. Opens one console window per server (Master, GM,
REM  Character, World, Proxy). Close those windows (or stop_servers
REM  via Ctrl+C in each) to shut down.
REM
REM  Run setup_windows.bat ONCE first to create the venv + databases.
REM  The Godot client connects to the ClientProxy at ws://localhost:9000.
REM ===================================================================
setlocal
cd /d "%~dp0"

REM Use the venv's Python if present, else fall back to system python.
set "PY=python"
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"

set "GC=gameconfig=mom.cfg"

REM Show server output in real time (Windows block-buffers console stdout
REM otherwise, which hides what each server is doing when something hangs).
set "PYTHONUNBUFFERED=1"

REM Enable the in-game testing cheats (F8 / backquote cheat window).
REM Set to 0 to disable. Inherited by every server window below.
set "MOM_ENABLE_CHEATS=1"

if not exist "data\master\master.db" (
    echo data\master\master.db not found.
    echo Run setup_windows.bat first to build the databases.
    pause
    exit /b 1
)

echo Starting servers (one window each)...
start "1-MasterServer"    cmd /k "%PY% MasterServer.py %GC%"
timeout /t 2 >nul
start "2-GMServer"        cmd /k "%PY% GMServer.py %GC%"
timeout /t 2 >nul
start "3-CharacterServer" cmd /k "%PY% CharacterServer.py %GC%"
timeout /t 2 >nul
start "4-WorldDaemon"     cmd /k "%PY% WorldDaemon.py %GC% -worldname=TestDaemon -publicname=TestWorld -password=mmo"
timeout /t 3 >nul
start "5-ClientProxy"     cmd /k "%PY% ClientProxy.py %GC%"

echo.
echo All servers launched.
echo   Master 2002 ^| GM 2003 ^| World 2008 ^| Proxy ws://localhost:9000
echo Now open the 'minions-port' folder in Godot 4.6 and press Play (F5).
