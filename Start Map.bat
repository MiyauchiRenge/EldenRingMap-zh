@echo off
setlocal
chcp 65001 >nul
title Lands Between Map / 交界地地图

rem ---------------------------------------------------------------------------
rem Starts the map server and opens the page. The map follows your save file:
rem the player marker is the position the game last wrote, refreshed when the
rem save changes. Nothing here reads the running game.
rem
rem Anything you pass is handed straight to the server, e.g.
rem   "Start Map.bat" --lan            also serve to your local network
rem   node server\index.js --help      full list of options
rem
rem Note: `goto` is used instead of parenthesised if-blocks throughout, because
rem cmd expands %~f0 before parsing the block, and any bracket in the install
rem path would terminate the block early.
rem ---------------------------------------------------------------------------

rem Run from this script's own folder, whatever the working directory is.
cd /d "%~dp0"

set PORT=8099

where node >nul 2>nul
if errorlevel 1 goto :no_node
node -e "process.exit(parseInt(process.versions.node) >= 18 ? 0 : 1)" >nul 2>nul
if errorlevel 1 goto :old_node

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
