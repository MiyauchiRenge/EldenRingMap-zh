@echo off
setlocal
chcp 65001 >nul
title Elden Ring - Live Map / 实时地图

rem ---------------------------------------------------------------------------
rem One launcher, two modes - the mode is selected by the FIRST argument:
rem   "Start Map.bat"          normal mode: the map follows your save file
rem   "Start Map.bat" --live   real-time mode: a read-only reader is attached to
rem                            the running game, so the player dot moves in real
rem                            time instead of jumping once per save.
rem
rem Real-time mode needs administrator rights: Elden Ring runs elevated, so
rem reading its memory requires the same. The reader only ever READS - it cannot
rem modify the game or your save. If it can't attach, the map still works from
rem the save file. Elevation and the Python probe happen in real-time mode ONLY,
rem so normal mode stays launchable without admin rights.
rem
rem Everything after the mode switch is passed straight through to the server,
rem e.g.   "Start Map.bat" --lan                also serve to your local network
rem        "Start Map.bat" --live --lan        real-time mode over the LAN
rem        node server\index.js --help          full list of options
rem
rem Real-time mode is the --live switch above; there is no second launcher file
rem to keep in step any more.
rem
rem Note: `goto` is used instead of parenthesised if-blocks throughout, because
rem cmd expands %~f0 before parsing the block, and any bracket in the install
rem path would terminate the block early.
rem ---------------------------------------------------------------------------

rem Run from this script's own folder, whatever the working directory is.
cd /d "%~dp0"

set PORT=8099

rem The mode switch is consumed here: in real-time mode it is dropped so it never
rem reaches node, and the remaining arguments are kept in PASSTHRU. In normal
rem mode the arguments are passed to node untouched, exactly as before. `shift`
rem is only safe once we know an argument exists, hence the two branches.
set "LIVE="
set "PASSTHRU="
if /i "%~1"=="--live" set "LIVE=1"
if not defined LIVE goto :check_env
shift
if "%~1"=="" goto :check_env
set "PASSTHRU=%~1"
shift
:collect_args
if "%~1"=="" goto :check_env
set "PASSTHRU=%PASSTHRU% %~1"
shift
goto :collect_args

:check_env
rem The window title is the one thing the user sees before anything else, so it
rem says which mode this run is. Set here rather than at the top, because the
rem mode is not known until the first argument has been read - and this label is
rem on the path of both a fresh run and the elevated relaunch.
if defined LIVE title Elden Ring - Live Map (real-time) / 实时地图（实时模式）
where node >nul 2>nul
if errorlevel 1 goto :no_node
node -e "process.exit(parseInt(process.versions.node) >= 18 ? 0 : 1)" >nul 2>nul
if errorlevel 1 goto :old_node

rem --- real-time mode only: elevate, and find a usable Python ----------------
if not defined LIVE goto :after_python

net session >nul 2>&1
if "%errorlevel%"=="0" goto :elevated

echo.
echo   Requesting administrator rights ^(needed to read the game^)...
echo   正在请求管理员权限（读取游戏内存需要）... / Requesting administrator rights...

rem Relaunch elevated, handing ourselves back the arguments we were given with
rem --live forced to the front. -ArgumentList takes an array because a joined
rem string would split any argument that contains a space, and Start-Process
rem takes the path to this script as %~f0 rather than as a bare file name,
rem because the new elevated process does NOT inherit this window's directory:
rem it starts in C:\Windows\system32, where a bare name cannot be found.
powershell -NoProfile -Command "Start-Process -FilePath \"%~f0\" -ArgumentList @(\"--live\",\"%PASSTHRU%\") -Verb RunAs"
goto :eof

:elevated
rem Python has to be probed before the port check, because the port check is the
rem last thing that may send us to an error label - and every error label pauses.
set "PY="
call "%~dp0tools\probe-python.bat" python
if not defined PY call "%~dp0tools\probe-python.bat" py -3
if not defined PY goto :no_python
if not exist "web\tiles\manifest.json" goto :no_tiles

netstat -ano | find ":%PORT% " | find "LISTENING" >nul
if not errorlevel 1 goto :port_busy

tasklist /fi "imagename eq eldenring.exe" 2>nul | find /i "eldenring.exe" >nul
if errorlevel 1 echo   Note: Elden Ring isn't running yet - the reader will wait and attach on its own.
if errorlevel 1 echo   提示：游戏尚未运行——读取器会自动等待并连接。/ Note: Elden Ring isn't running yet.

echo.
echo   Starting in real-time mode on port %PORT% ...
echo   正在以实时模式启动，端口 %PORT% ...
echo   Leave this window open while you play. Close it to stop.
echo   游戏时请保持此窗口打开，关闭窗口即停止服务。
echo.

rem Give the server a moment to bind, then open the browser.
rem ping is the delay here because `timeout` fails when stdin is redirected.
start "" /b cmd /c "ping -n 3 127.0.0.1 >nul & start http://localhost:%PORT%"

if not defined PASSTHRU goto :run_live_plain
node server\index.js --port %PORT% --live-memory --python "%PY%" %PASSTHRU%
set RC=%errorlevel%
goto :live_stopped
:run_live_plain
node server\index.js --port %PORT% --live-memory --python "%PY%"
set RC=%errorlevel%

rem RC is taken straight off each node call rather than after a converging jump:
rem this line exists to report the server's real exit code, so it must not depend
rem on whether an intervening `goto` happened to leave ERRORLEVEL alone.
:live_stopped
echo.
if not "%RC%"=="0" echo   Server exited with code %RC%. / 服务器退出，代码 %RC%。
if "%RC%"=="0" echo   Server stopped. / 服务器已停止。
pause
goto :eof

rem --- normal mode only: nothing above this line ran --------------------------
:after_python
if not exist "web\tiles\manifest.json" goto :no_tiles

netstat -ano | find ":%PORT% " | find "LISTENING" >nul
if not errorlevel 1 goto :port_busy

echo.
echo   Starting the map server on port %PORT% ...
echo   正在端口 %PORT% 上启动地图服务器 ...
echo   Leave this window open while you play. Close it to stop.
echo   游戏时请保持此窗口打开，关闭窗口即停止服务。
echo.

rem Give the server a moment to bind, then open the browser.
rem ping is the delay here because `timeout` fails when stdin is redirected.
start "" /b cmd /c "ping -n 3 127.0.0.1 >nul & start http://localhost:%PORT%"

node server\index.js --port %PORT% %*
set RC=%errorlevel%

echo.
if not "%RC%"=="0" echo   Server exited with code %RC%. / 服务器退出，代码 %RC%。
if "%RC%"=="0" echo   Server stopped. / 服务器已停止。
pause
goto :eof

rem The Python probe lives in tools\probe-python.bat.

:old_node
echo.
echo   Your Node.js is too old - this needs 18 or newer.
echo   你的 Node.js 版本过旧，需要 18 或更高版本。
for /f "delims=" %%v in ('node --version 2^>nul') do echo   当前版本 / Found: %%v
echo   Install the current LTS from https://nodejs.org, then open a NEW window.
echo   请从 https://nodejs.org 安装当前 LTS 版本，然后打开一个【新】窗口。
echo.
pause & goto :eof

:no_node
echo.
echo   Node.js was not found on your PATH.
echo   PATH 上未找到 Node.js。
echo   Install it from https://nodejs.org ^(LTS is fine^), then run this again.
echo   请从 https://nodejs.org 安装（LTS 版即可），然后重新运行。
echo.
pause & goto :eof

:no_tiles
echo.
echo   Map tiles are missing.
echo   缺少地图底图（瓦片）。
echo   Run "Setup.bat" once first - it extracts them from your game install.
echo   请先运行一次 "Setup.bat"，它会从你的游戏安装中提取底图。
echo.
pause & goto :eof

:port_busy
echo.
echo   Port %PORT% is already in use - another copy of the map is probably
echo   still running. Close its window, or end node.exe in Task Manager,
echo   then run this again.
echo   端口 %PORT% 已被占用——很可能还有一个地图副本在运行。请关闭它的窗口，
echo   或在任务管理器中结束 node.exe，然后重新运行。
echo.
echo   Listening process: / 占用端口的进程：
netstat -ano | find ":%PORT% " | find "LISTENING"
echo.
pause & goto :eof

:no_python
echo.
echo   Python not found. Install it from https://python.org and try again.
echo   未找到 Python。请从 https://python.org 安装后重试。
echo.
pause & goto :eof
