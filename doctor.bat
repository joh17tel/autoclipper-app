@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (echo Not installed yet - run setup.bat first. & pause & exit /b)
.venv\Scripts\python.exe doctor.py
pause
