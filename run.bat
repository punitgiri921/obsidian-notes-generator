@echo off
cd /d %~dp0
echo Launching Obsidian Study Notes Generator...
.venv\Scripts\python.exe main.py
if errorlevel 1 pause
