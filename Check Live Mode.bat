@echo off
setlocal
chcp 65001 >nul
title Elden Ring - live mode diagnostic / 实时模式诊断

rem ---------------------------------------------------------------------------
rem One-shot check that the live reader can attach to your game and that the
rem byte signatures still match this game version. Reads only; changes nothing.
rem Writes cache\live-probe.log.
rem
rem Run this with Elden Ring running and a character loaded (not the title
rem screen) for a meaningful result.
rem ---------------------------------------------------------------------------

net session >nul 2>&1
if "%errorlevel%"=="0" goto :elevated

echo   Requesting administrator rights...
echo   正在请求管理员权限... / Requesting administrator rights...
powershell -NoProfile -Command "Start-Process -FilePath \"%~f0\" -Verb RunAs"
goto :eof

:elevated
cd /d "%~dp0"

set "PY="
call "%~dp0tools\probe-python.bat" python
if not defined PY call "%~dp0tools\probe-python.bat" py -3
if not defined PY goto :no_python

tasklist /fi "imagename eq eldenring.exe" 2>nul | find /i "eldenring.exe" >nul
if errorlevel 1 goto :not_running

echo.
%PY% tools\live_memory.py --probe
echo.
pause
goto :eof

:not_running
echo.
echo   Elden Ring is not running. Start it, load your character, then run this again.
echo   游戏未运行。请先启动游戏并载入角色，然后重新运行本文件。
echo.
pause & goto :eof

rem The Python probe is tools\probe-python.bat, shared with the other launchers.

:no_python
echo.
echo   Python not found. Install it from https://python.org and try again.
echo   未找到 Python。请从 https://python.org 安装后重试。
echo.
pause & goto :eof
