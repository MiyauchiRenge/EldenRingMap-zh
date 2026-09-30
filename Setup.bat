@echo off
setlocal
chcp 65001 >nul
title Elden Ring Live Map - setup / 安装

cd /d "%~dp0"

rem ---------------------------------------------------------------------------
rem Your Elden Ring install is found automatically by scanning your Steam
rem libraries. Only fill this in if that fails - it must be the folder that
rem contains eldenring.exe and regulation.bin.
rem
rem   set GAMEDIR=D:\Games\Steam\steamapps\common\ELDEN RING\Game
rem
rem Playing a loose-file mod such as Elden Ring Reforged? Point MODDIR at its
rem mod folder - the one containing the mod's own regulation.bin - and the
rem setup reads the mod's data over the game's archives.
rem
rem   set MODDIR=D:\Games\ELDEN RING Reforged\mod
rem
rem Route descriptions - "how do I actually get to this?" - are not in the game
rem files. They are something people write, so the last step can fetch them from
rem the Fextralife wiki's interactive map and attach them to your markers. It
rem asks first; answer here instead to keep setup unattended.
rem
rem   set TIPS=yes
rem ---------------------------------------------------------------------------
set GAMEDIR=
set MODDIR=
set TIPS=

rem The Python tools pick the mod up from the environment.
if not "%MODDIR%"=="" set "ER_MOD_DIR=%MODDIR%"

echo.
echo   Elden Ring Live Map - setup
echo   Elden Ring 实时地图 - 安装
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

echo   [1/11] Installing Python packages ...
echo         [正在安装 Python 依赖包 / Installing Python packages]
%PY% -m pip install --quiet --disable-pip-version-check zstandard pycryptodome pillow texture2ddecoder numpy
if errorlevel 1 goto :pip_failed

rem The paramdefs (and the event-flag and MFG tables) are community format
rem documents, not game files: they are not shipped in this repository, because
rem they are someone else's writing. They have to be here before anything reads
rem the params, so this runs first - and it is the only step that needs network
rem access besides the optional route descriptions at the end.
echo   [2/11] Fetching the community format documents ...
echo         [正在获取社区格式文档（paramdefs 等）/ Fetching the community format documents]
%PY% tools\fetch_docs.py
if errorlevel 1 goto :docs_failed

echo   [3/11] Extracting map tiles from your game ^(a couple of minutes^) ...
echo         [正在从你的游戏提取地图底图（瓦片），约需几分钟 / Extracting map tiles from your game]
if "%GAMEDIR%"=="" %PY% tools\extract_tiles.py
if not "%GAMEDIR%"=="" %PY% tools\extract_tiles.py --game-dir "%GAMEDIR%"
if errorlevel 1 goto :extract_failed

echo   [4/11] Building the marker dataset ...
echo         [正在生成地图标记数据 / Building the marker dataset]
if "%GAMEDIR%"=="" %PY% tools\build_markers.py
if not "%GAMEDIR%"=="" %PY% tools\build_markers.py "%GAMEDIR%"
if errorlevel 1 goto :markers_failed

echo   [5/11] Indexing the game's map files ...
echo         [正在索引游戏地图文件 / Indexing the game's map files]
%PY% tools\dev\enumerate_maps.py >nul
if errorlevel 1 goto :items_failed

echo   [6/11] Extracting item locations, merchants and one-time drops ^(this reads 864 map files^) ...
echo         [正在提取道具位置、商人与角色掉落 / Extracting item locations, merchants and one-time drops]
if "%GAMEDIR%"=="" %PY% tools\extract_items.py
if not "%GAMEDIR%"=="" %PY% tools\extract_items.py --game-dir "%GAMEDIR%"
if errorlevel 1 goto :items_failed

echo   [7/11] Extracting the game's map and item icons ...
echo         [正在提取游戏地图图标与物品图标 / Extracting the game's map and item icons]
if "%GAMEDIR%"=="" %PY% tools\extract_icons.py
if not "%GAMEDIR%"=="" %PY% tools\extract_icons.py --game-dir "%GAMEDIR%"
if errorlevel 1 goto :icons_failed

rem Rune and Ember Pieces are Reforged collectibles - there are none to find in
rem an unmodded game, so this step only runs when MODDIR is set.
if "%MODDIR%"=="" goto :skip_pieces
echo   [8/11] Extracting Reforged rune/ember pieces ...
echo         [正在提取 Reforged 卢恩/余烬碎片 / Extracting Reforged rune/ember pieces]
if "%GAMEDIR%"=="" %PY% tools\extract_pieces.py --mod-dir "%MODDIR%"
if not "%GAMEDIR%"=="" %PY% tools\extract_pieces.py --game-dir "%GAMEDIR%" --mod-dir "%MODDIR%"
if errorlevel 1 goto :pieces_failed
goto :done_pieces
:skip_pieces
echo   [8/11] Reforged rune/ember pieces - skipped ^(MODDIR not set^)
echo         [已跳过 Reforged 卢恩/余烬碎片，未设置 MODDIR / skipped - MODDIR not set]
:done_pieces

rem Everything above this line was read out of your own copy of the game. This
rem step is the one exception, so it asks before it runs.
if /i "%TIPS%"=="yes" goto :do_tips
if /i "%TIPS%"=="no" goto :skip_tips
echo.
echo   [9/11] One-time drops from the event scripts ^(adds the EMEVD drop layer^) ...
if "%GAMEDIR%"=="" %PY% tools\extract_emevd_drops.py
if not "%GAMEDIR%"=="" %PY% tools\extract_emevd_drops.py --game-dir "%GAMEDIR%"
if errorlevel 1 echo   Note: the EMEVD drop layer was skipped - the map works without it.
echo   [9/11] Marking where farmable enemy drops come from ^(adds the farm-spot layer^) ...
if "%GAMEDIR%"=="" %PY% tools\extract_farm_nodes.py --all-unmarked
if not "%GAMEDIR%"=="" %PY% tools\extract_farm_nodes.py --all-unmarked --game-dir "%GAMEDIR%"
if errorlevel 1 echo   Note: farm spots were skipped - the map works without them.
echo   [11/11] Route descriptions ^(optional^) / 路线说明（可选）
echo.
echo   你的标记现在已经能说明"这是什么"和"它有多高"，但说明不了
echo   "怎么过去"——路线不在游戏文件里，那是别人写的内容。
echo   Fextralife wiki 的互动地图为它的大多数标记写了路线，这一步会
echo   抓取这些文字并附加到你的约 2,000 个标记上。
echo.
echo   Your markers can now say what a thing is and how high up it is. What
echo   they cannot say is how to get to it - that is not in the game files,
echo   it is something people write. The Fextralife wiki's interactive map
echo   has a written route for most of its markers, and this fetches them
echo   and attaches them to about 2,000 of yours.
echo.
echo   那些文字属于他们——既不属于你，也不属于游戏——他们的条款要求
echo   不得自动抓取。它只保存在这台电脑上供你自己使用：请勿转载，
echo   也不要随本工具一起分发。没有它地图依然是完整的。
echo.
echo   That text is theirs - not yours, and not the game's - and their terms
echo   ask that it is not fetched automatically. It stays on this PC for your
echo   own use: do not republish it or ship it with a copy of this tool. The
echo   map is complete without it.
echo.
set "ans="
set /p ans=  抓取路线说明吗？/ Fetch them? [y/N] 
if /i not "%ans%"=="y" goto :skip_tips
:do_tips
echo   Fetching route descriptions ...
echo         [正在抓取路线说明 / Fetching route descriptions]
%PY% tools\fetch_tips.py
if errorlevel 1 goto :tips_failed
goto :done_tips
:skip_tips
echo   [11/11] Route descriptions - skipped
echo         [已跳过路线说明 / Route descriptions - skipped]
:done_tips

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

:tips_failed
echo.
echo   Fetching the route descriptions failed - no internet, or the wiki
echo   changed. Everything else is built and the map works; markers will just
echo   have no "how to get there" text. Re-run this file to try again.
echo   抓取路线说明失败——可能是没有网络，或 wiki 页面结构变了。其他内容都已
echo   生成、地图可正常使用，只是标记不会有"如何抵达"的文字。可重新运行本文件重试。
echo.
pause & goto :eof

:pieces_failed
echo.
echo   Rune/ember piece extraction failed. The map still works - you will just
echo   have no piece markers. Check that MODDIR points at the Reforged mod
echo   folder containing regulation.bin.
echo   卢恩/余烬碎片提取失败。地图仍可使用，只是不会有碎片标记。
echo   请确认 MODDIR 指向包含 regulation.bin 的 Reforged 模组文件夹。
echo.
pause & goto :eof
