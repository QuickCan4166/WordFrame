@echo off
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo Install Python 3.11 or 3.12 from https://www.python.org/downloads/windows/ first.
  pause
  exit /b 1
)
if not exist .venv\Scripts\python.exe (
  py -3 -m venv .venv
  if errorlevel 1 goto failed
)
.venv\Scripts\python.exe -c "import PySide6, vosk, sounddevice" >nul 2>nul
if errorlevel 1 (
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  if errorlevel 1 goto failed
)
.venv\Scripts\python.exe app.py
if errorlevel 1 goto failed
exit /b 0
:failed
 echo WordFrame could not start. See the error above.
 pause
