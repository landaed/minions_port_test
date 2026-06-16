@echo off
REM ===================================================================
REM  Minions of Mirth (Godot port) - stop the whole server stack on
REM  Windows. Closes the five server windows started by run_servers.bat
REM  AND kills the World server child process the daemon spawned.
REM ===================================================================
setlocal

echo Stopping Minions of Mirth servers...

REM 1) Close each named server window and its process tree (/T kills the
REM    cmd window + the python it runs + anything python spawned).
for %%T in (
    "1-MasterServer"
    "2-GMServer"
    "3-CharacterServer"
    "4-WorldDaemon"
    "5-ClientProxy"
) do (
    taskkill /F /T /FI "WINDOWTITLE eq %%~T*" >nul 2>&1
)

REM 2) Belt-and-suspenders: kill any python still running one of the server
REM    scripts (e.g. the spawned WorldServer.py, which has no window of its
REM    own). Matches on the command line so we never touch unrelated python.
powershell -NoProfile -Command ^
  "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'MasterServer\.py|GMServer\.py|CharacterServer\.py|WorldDaemon\.py|WorldServer\.py|ClientProxy\.py|zoneserver\.py' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1

echo All Minions of Mirth servers stopped.
