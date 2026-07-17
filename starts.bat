@echo off

cd /d "%~dp0"

start "" cmd /k ".venv\Scripts\python.exe app.py"

timeout /t 3 /nobreak > nul

start "" http://127.0.0.1:5000