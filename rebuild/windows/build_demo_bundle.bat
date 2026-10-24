@echo off
REM Offline conversion of the two demo SQLite databases + media ZIPs into one validated bundle.
REM Usage (one line, adjust the paths):
REM   rebuild\windows\build_demo_bundle.bat --v5-sqlite D:\in\demo_v5.sqlite3 --v5-media-zip D:\in\demo_v5_media.zip --arch02-sqlite D:\in\demo_arch02.sqlite3 --arch02-media-zip D:\in\demo_arch02_media.zip --out D:\out\rastisi-demo-bundle
REM Needs only Python 3.10+ ("py -3" or "python" on PATH). No server, no database, no admin rights.
setlocal
set PYTHONUTF8=1
cd /d "%~dp0\..\.."
where py >nul 2>nul && (py -3 rebuild\tools\build_bundle_offline.py %* & exit /b %ERRORLEVEL%)
where python >nul 2>nul && (python rebuild\tools\build_bundle_offline.py %* & exit /b %ERRORLEVEL%)
echo Python 3.10 or newer was not found on PATH. Install it from https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^).
exit /b 9
