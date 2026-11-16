@echo off
title AutoClipper - keep this window open (it is the engine)
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo AutoClipper isn't installed yet. Double-click setup.bat first.
  pause & exit /b
)
.venv\Scripts\python.exe -c "import flask, yaml, numpy" >nul 2>nul
if errorlevel 1 (
  echo Setup didn't finish properly. Double-click setup.bat again.
  pause & exit /b
)
echo Updating the stream downloader ...
.venv\Scripts\python.exe -m pip install -U yt-dlp -q >nul 2>nul
:run
.venv\Scripts\python.exe app.py %*
if errorlevel 3 if not errorlevel 4 (
  echo Restarting with the new version ...
  goto run
)
echo.
echo AutoClipper stopped. If there is an error above, screenshot this window and send it to Claude.
pause
