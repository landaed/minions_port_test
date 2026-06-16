@echo off
REM ===================================================================
REM  Minions of Mirth (Godot port) - one-time Windows setup.
REM  Creates a Python virtual environment, installs the server
REM  dependencies, and builds the runtime databases from the bundled
REM  MoMReborn baseline. Run this ONCE before run_servers.bat.
REM
REM  Requires: Python 3.11+ on PATH (python.org installer, tick
REM            "Add python.exe to PATH").
REM ===================================================================
setlocal
cd /d "%~dp0"

echo.
echo [1/3] Creating virtual environment (venv)...
python -m venv venv || goto :err

echo.
echo [2/3] Installing server dependencies...
call venv\Scripts\activate.bat || goto :err
python -m pip install --upgrade pip
pip install "Twisted>=22,<24" sqlobject pyopenssl service_identity bcrypt pyasn1 || goto :err
REM autobahn provides the WebSocket bridge the Godot client talks to.
REM --no-deps avoids its optional ubjson/cbor serializers that fail to build.
pip install --no-deps autobahn txaio hyperlink || goto :err
REM Only needed if you want to run the headless tools/ test clients:
pip install websockets

echo.
echo [3/3] Building databases from the bundled MoMReborn baseline...
python setup_databases.py --worldname=TestDaemon || goto :err

echo.
echo ============================================================
echo  Setup complete. Next:
echo    1. run_servers.bat        (starts the 5 servers)
echo    2. Open the 'minions-port' folder in Godot 4.6 and press Play
echo ============================================================
goto :eof

:err
echo.
echo *** Setup FAILED. See the error above. ***
exit /b 1
