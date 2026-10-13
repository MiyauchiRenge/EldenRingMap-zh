@echo off
setlocal
chcp 65001 >nul
title Lands Between Map - setup / 安装

cd /d "%~dp0"

rem ---------------------------------------------------------------------------
rem Your Elden Ring install is found automatically by scanning your Steam
rem libraries. Only fill this in if that fails - it must be the folder that
rem contains eldenring.exe and regulation.bin.
rem
rem   set GAMEDIR=D:\Games\Steam\steamapps\common\ELDEN RING\Game
rem ---------------------------------------------------------------------------
set GAMEDIR=

echo.
echo   Lands Between Map - setup
echo   交界地地图 - 安装
echo   ===========================
echo.

rem Node and Python are checked by *running* them, not with "where". Windows
rem ships a zero-byte App Execution Alias at
rem %LOCALAPPDATA%\Microsoft\WindowsApps\python.exe whose only job is to open
rem the Microsoft Store - it satisfies "where python" on a machine that has no
rem Python at all, so the old check passed and pip then failed confusingly.

where node >nul 2>nul
if errorlevel 1 goto :no_node
node -e "process.exit(parseInt(process.versions.node) >= 18 ? 0 : 1)" >nul 2>nul
if errorlevel 1 goto :old_node

set "PY="
set "PYOLD="
call "%~dp0tools\probe-python.bat" python
if not defined PY call "%~dp0tools\probe-python.bat" py -3
if defined PY goto :have_python
if defined PYOLD goto :old_python
goto :no_python

:have_python
%PY% -m pip --version >nul 2>nul
if errorlevel 1 goto :no_pip

echo   [1] Installing Python packages ...
echo         [正在安装 Python 依赖包 / Installing Python packages]
%PY% -m pip install --quiet --disable-pip-version-check zstandard pycryptodome pillow texture2ddecoder numpy
if errorlevel 1 goto :pip_failed

rem The paramdefs (and the event-flag and MFG tables) are community format
rem documents, not game files: they are not shipped in this repository, because
rem they are someone else's writing. They have to be here before anything reads
rem the params, so this runs first - and it is the only step that needs network
rem access besides the optional route descriptions at the end.
echo   [2] Fetching the community format documents ...
echo         [正在获取社区格式文档（paramdefs 等）/ Fetching the community format documents]
%PY% tools\fetch_docs.py
if errorlevel 1 goto :docs_failed

echo   [3] Extracting map tiles from your game ^(a couple of minutes^) ...
echo         [正在从你的游戏提取地图底图（瓦片），约需几分钟 / Extracting map tiles from your game]
if "%GAMEDIR%"=="" %PY% tools\extract_tiles.py
if not "%GAMEDIR%"=="" %PY% tools\extract_tiles.py --game-dir "%GAMEDIR%"
if errorlevel 1 goto :extract_failed

echo   [4] Building the marker dataset ...
echo         [正在生成地图标记数据 / Building the marker dataset]
if "%GAMEDIR%"=="" %PY% tools\build_markers.py
if not "%GAMEDIR%"=="" %PY% tools\build_markers.py "%GAMEDIR%"
if errorlevel 1 goto :markers_failed

echo   [5] Indexing the game's map files ...
echo         [正在索引游戏地图文件 / Indexing the game's map files]
%PY% tools\dev\enumerate_maps.py >nul
if errorlevel 1 goto :items_failed

echo   [6] Extracting item locations, merchants and one-time drops ^(this reads 864 map files^) ...
echo         [正在提取道具位置、商人与角色掉落 / Extracting item locations, merchants and one-time drops]
if "%GAMEDIR%"=="" %PY% tools\extract_items.py
if not "%GAMEDIR%"=="" %PY% tools\extract_items.py --game-dir "%GAMEDIR%"
if errorlevel 1 goto :items_failed

echo   [7] Extracting the game's map and item icons ...
echo         [正在提取游戏地图图标与物品图标 / Extracting the game's map and item icons]
if "%GAMEDIR%"=="" %PY% tools\extract_icons.py
if not "%GAMEDIR%"=="" %PY% tools\extract_icons.py --game-dir "%GAMEDIR%"
if errorlevel 1 goto :icons_failed

echo   [8] One-time drops from the event scripts ^(adds the EMEVD drop layer^) ...
if "%GAMEDIR%"=="" %PY% tools\extract_emevd_drops.py
if not "%GAMEDIR%"=="" %PY% tools\extract_emevd_drops.py --game-dir "%GAMEDIR%"
if errorlevel 1 echo   Note: the EMEVD drop layer was skipped - the map works without it.
echo   [9] Rewards the event scripts grant with no world object ^(adds the EMEVD reward layer^) ...
if "%GAMEDIR%"=="" %PY% tools\extract_emevd_rewards.py
if not "%GAMEDIR%"=="" %PY% tools\extract_emevd_rewards.py --game-dir "%GAMEDIR%"
if errorlevel 1 echo   Note: the EMEVD reward layer was skipped - the map works without it.
echo   [10] Marking where farmable enemy drops come from ^(adds the farm-spot layer^) ...
if "%GAMEDIR%"=="" %PY% tools\extract_farm_nodes.py --all-unmarked
if not "%GAMEDIR%"=="" %PY% tools\extract_farm_nodes.py --all-unmarked --game-dir "%GAMEDIR%"
if errorlevel 1 echo   Note: farm spots were skipped - the map works without them.
echo   [11] Adding the follow-up items of sequential lots ^(the documented lot+1 chain^) ...
if "%GAMEDIR%"=="" %PY% tools\extract_followup_lots.py
if not "%GAMEDIR%"=="" %PY% tools\extract_followup_lots.py --game-dir "%GAMEDIR%"
if errorlevel 1 echo   Note: the follow-up layer was skipped - the map works without it.
echo   [12] Extracting gatherable nodes ^(AEG parts x AssetEnvironmentGeometryParam^) ...
if "%GAMEDIR%"=="" %PY% tools\extract_gather_nodes.py
if not "%GAMEDIR%"=="" %PY% tools\extract_gather_nodes.py --game-dir "%GAMEDIR%"
if errorlevel 1 echo   Note: the gather-node layer was skipped - the map works without it.
echo   [13] Registering the items whose lot nobody references ^(adds the quest-reward layer^) ...
if "%GAMEDIR%"=="" %PY% tools\extract_quest_rewards.py
if not "%GAMEDIR%"=="" %PY% tools\extract_quest_rewards.py --game-dir "%GAMEDIR%"
if errorlevel 1 echo   Note: the quest-reward layer was skipped - the map works without it.
echo   [14] Matching shop shelves to the merchant who sells them ^(adds the shop layer^) ...
if "%GAMEDIR%"=="" %PY% tools\dev\shop_register.py
if not "%GAMEDIR%"=="" %PY% tools\dev\shop_register.py --game-dir "%GAMEDIR%"
if errorlevel 1 echo   Note: the shop layer was skipped - the map works without it.
echo   [15] Counting how many items each lot actually grants ...
if "%GAMEDIR%"=="" %PY% tools\annotate_quantities.py
if not "%GAMEDIR%"=="" %PY% tools\annotate_quantities.py --game-dir "%GAMEDIR%"
if errorlevel 1 echo   Note: the item counts were not annotated - the map works without them.
echo   [16] Placing each merchant's bell bearing on that merchant ...
if "%GAMEDIR%"=="" %PY% tools\dev\fix_bell_positions.py
if not "%GAMEDIR%"=="" %PY% tools\dev\fix_bell_positions.py --game-dir "%GAMEDIR%"
if errorlevel 1 echo   Note: the bell bearings keep their own positions - the map works without the fix.
echo   [17] Recording which bell bearing each merchant drops ...
%PY% tools\dev\link_bell_bearings.py
if errorlevel 1 echo   Note: merchant cards will not name the bearing they drop.
echo   Checking the layer registry against this script ...
%PY% tools\erlib\layers.py check >nul
if errorlevel 1 echo   Note: tools/erlib/layers.py reports a layer this script does not run.

echo.
echo   Done. Start it any time with "Start Map.bat".
echo   完成。随时用 "Start Map.bat" 启动。
echo.
pause
goto :eof

rem The Python probe is tools\probe-python.bat, shared with the other launchers
rem so the "where python finds the Microsoft Store stub" trap is explained and
rem fixed in exactly one place rather than copied into three scripts.

:no_node
echo   Node.js not found. Install it from https://nodejs.org, then run this again.
echo   未找到 Node.js。请从 https://nodejs.org 安装后重新运行本文件。
echo   Make sure you open a NEW window afterwards so PATH is picked up.
echo   安装后请务必打开一个【新】窗口，否则 PATH 不会生效。
echo.
pause & goto :eof

:old_node
echo   Your Node.js is too old - this needs 18 or newer.
echo   你的 Node.js 版本过旧，需要 18 或更高版本。
for /f "delims=" %%v in ('node --version 2^>nul') do echo   当前版本 / Found: %%v
echo   Install the current LTS from https://nodejs.org and open a NEW window.
echo   请从 https://nodejs.org 安装当前 LTS 版本，然后打开一个【新】窗口。
echo.
pause & goto :eof

:no_python
echo   Python not found.
echo   未找到 Python。
echo.
echo   If you think you installed it, this is usually one of two things:
echo   如果你确定已经安装过，通常是以下两种情况之一：
echo     - it was installed without "Add Python to PATH" ticked, or
echo       安装时没有勾选 "Add Python to PATH"，或者
echo     - only the Microsoft Store placeholder is on PATH, which does nothing
echo       except offer to install Python.
echo       PATH 上只有微软商店的占位程序，它除了提示你去装 Python 什么也不做。
echo.
echo   Install it from https://python.org, tick "Add Python to PATH" in the
echo   installer, then open a NEW window and run this again.
echo   请从 https://python.org 安装，在安装程序中勾选 "Add Python to PATH"，
echo   然后打开一个【新】窗口重新运行本文件。
echo.
pause & goto :eof

:old_python
echo   Your Python is too old - this needs 3.9 or newer.
echo   你的 Python 版本过旧，需要 3.9 或更高版本。
for /f "delims=" %%v in ('%PYOLD% --version 2^>^&1') do echo   当前版本 / Found: %%v
echo   Install a current version from https://python.org, tick "Add Python to
echo   PATH", then open a NEW window and run this again.
echo   请从 https://python.org 安装当前版本，勾选 "Add Python to PATH"，
echo   然后打开一个【新】窗口重新运行本文件。
echo.
pause & goto :eof

:no_pip
echo   Python is installed but pip is missing, so the packages cannot be
echo   installed. Try repairing it with:
echo   Python 已安装但缺少 pip，无法安装依赖包。可以尝试用下面的命令修复：
echo     %PY% -m ensurepip --upgrade
echo   then run this again.
echo   然后重新运行本文件。
echo.
pause & goto :eof

:pip_failed
echo.
echo   Installing the Python packages failed. Try it by hand to see the error:
echo   安装 Python 依赖包失败。请手动执行以下命令以查看具体错误：
echo     %PY% -m pip install zstandard pycryptodome pillow texture2ddecoder numpy
echo.
pause & goto :eof

:docs_failed
echo.
echo   Fetching the community format documents failed - this step needs network
echo   access. See the message above for which file could not be fetched.
echo   获取社区格式文档失败——这一步需要联网。上方信息里写明了哪个文件没取到。
echo   You can also download them by hand from
echo   也可以手动下载后放到相同位置：
echo     https://github.com/soulsmods/Paramdex  ^(ER/Defs/*.xml^)
echo     https://github.com/egormagurin/EldenRingMap  ^(data/^)
echo   then run this Setup again.
echo.
pause & goto :eof

:extract_failed
echo.
echo   Tile extraction failed.
echo   地图底图（瓦片）提取失败。
echo   If it could not find your game, set GAMEDIR at the top of this file to the
echo   folder containing eldenring.exe and regulation.bin, then run this again.
echo   如果是找不到游戏，请把本文件顶部的 GAMEDIR 设为包含 eldenring.exe 和
echo   regulation.bin 的文件夹，然后重新运行。
echo.
pause & goto :eof

:markers_failed
echo.
echo   Building the marker dataset failed. See the message above.
echo   生成标记数据失败，请查看上方的报错信息。
echo.
pause & goto :eof

:icons_failed
echo.
echo   Icon extraction failed. The map still works - markers will use coloured
echo   dots instead of the game's own icons.
echo   图标提取失败。地图仍可使用——标记会改用彩色圆点代替游戏图标。
echo.
pause & goto :eof

:items_failed
echo.
echo   Item extraction failed. The map still works without it - you will just
echo   have no item markers. Re-run this file to try again.
echo   道具提取失败。没有它地图仍可使用，只是不会有道具标记。可重新运行本文件重试。
echo.
pause & goto :eof

