@echo off
setlocal
cd /d "%~dp0"
title AutoClipper setup
echo ==================================================
echo   AutoClipper setup  (takes 5-15 minutes)
echo ==================================================
echo.

rem ---- 1. Find a supported Python (3.10 - 3.12). Ignores the fake Microsoft Store "python".
set "PY="
for %%v in (3.12 3.11 3.10) do (
  if not defined PY (
    py -%%v -c "import sys" >nul 2>nul && set "PY=py -%%v"
  )
)
if not defined PY (
  python -c "import sys; sys.exit(0 if (3,10)<=sys.version_info[:2]<=(3,12) else 1)" >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo [1/4] Installing Python 3.12 ...
  winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
  for %%p in ("%LocalAppData%\Programs\Python\Python312\python.exe" "%ProgramFiles%\Python312\python.exe") do (
    if not defined PY if exist %%p set PY="%%~p"
  )
  if not defined PY (
    py -3.12 -c "import sys" >nul 2>nul && set "PY=py -3.12"
  )
)
if not defined PY (
  echo.
  echo  !! Could not find or install Python 3.12.
  echo     Install it from https://www.python.org/downloads/release/python-3129/
  echo     ^(tick "Add python.exe to PATH"^), then run setup.bat again.
  pause & exit /b 1
)
echo [1/4] Python found: %PY%

rem ---- 2. FFmpeg (video engine)
where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo [2/4] Installing FFmpeg ...
  winget install -e --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
) else (
  echo [2/4] FFmpeg found
)

rem ---- 3. Private Python environment (rebuilt if it's broken or the wrong version)
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe -c "import sys; sys.exit(0 if (3,10)<=sys.version_info[:2]<=(3,12) else 1)" >nul 2>nul
  if errorlevel 1 (
    echo     Old environment is the wrong version - rebuilding
    rmdir /s /q .venv
  )
)
if not exist .venv\Scripts\python.exe (
  echo [3/4] Creating environment ...
  %PY% -m venv .venv
)
if not exist .venv\Scripts\python.exe (
  echo  !! Could not create the environment. Send a screenshot of this window to Claude.
  pause & exit /b 1
)

rem ---- 4. Libraries: core first (must work), extras after (nice to have)
echo [4/4] Installing libraries ...
.venv\Scripts\python.exe -m pip install --upgrade pip -q
.venv\Scripts\python.exe -m pip install flask pyyaml numpy yt-dlp pypdf "opencv-python-headless<5"
if errorlevel 1 (
  echo  !! Core libraries failed to install. Check your internet, then run setup.bat again.
  pause & exit /b 1
)
.venv\Scripts\python.exe -m pip install faster-whisper || echo  (captions library failed - clips will be made without captions)
.venv\Scripts\python.exe -m pip install chat-downloader || echo  (chat library failed - moments found by audio only)

echo.
echo Checking everything ...
.venv\Scripts\python.exe doctor.py
echo.
echo Next: double-click create_desktop_shortcut.bat, then open AutoClipper from your desktop.
pause
