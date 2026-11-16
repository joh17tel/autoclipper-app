@echo off
cd /d "%~dp0"
schtasks /create /tn "AutoClipper" /tr "\"%~dp0AutoClipper.bat\" --no-window" /sc onlogon /rl limited /f
echo AutoClipper will start in the background when you log in. Open it any time with the desktop shortcut.
pause
