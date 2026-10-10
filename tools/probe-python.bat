@echo off
rem Find a Python that actually runs, and leave it in the caller's PY.
rem
rem "where python" is not enough: Windows ships a zero-byte App Execution
rem Alias for python.exe that only opens the Microsoft Store, and it satisfies
rem "where" on a machine that has no Python at all. So every candidate is
rem asked to run instead of being looked up.
rem
rem Called once per candidate, in order:
rem     call "%~dp0tools\probe-python.bat" python
rem     if not defined PY call "%~dp0tools\probe-python.bat" py -3
rem
rem What the caller gets, in its own environment:
rem     PY      a Python 3.9 or newer that runs
rem     PYOLD   a Python that runs but is older than 3.9
rem     neither nothing usable - missing, or just the Store stub
rem
rem Deliberately NO setlocal: PY has to survive the return, which is the whole
rem point of splitting this out. Re-calling it once PY is set does nothing, so a
rem caller just tries candidates in order and then looks at PY.
rem
rem No parenthesised if-blocks, for the reason documented in Start Map.bat: cmd
rem expands %* before parsing a block, so a bracket in it ends the block early.
if defined PY goto :eof
%* -c "import sys" >nul 2>nul
if errorlevel 1 goto :eof
%* -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul
if errorlevel 1 goto :too_old
set "PY=%*"
goto :eof
:too_old
set "PYOLD=%*"
goto :eof
