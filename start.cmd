@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  py -3.13 -m venv .venv
  if errorlevel 1 (
    echo Please install Python 3.13 first.
    pause
    exit /b 1
  )
)
.venv\Scripts\python.exe -m pip install -r backend\requirements.lock.txt
if errorlevel 1 (
  pause
  exit /b 1
)
where node >nul 2>nul
if errorlevel 1 (
  echo Please install Node.js 24.9 or later first.
  pause
  exit /b 1
)
if not exist node_modules (
  call npm.cmd ci
  if errorlevel 1 (
    pause
    exit /b 1
  )
)
call npm.cmd run build
if errorlevel 1 (
  pause
  exit /b 1
)
echo Open http://127.0.0.1:4317/ in your browser.
echo For a new site, initialize the owner first: npm run owner:init
.venv\Scripts\python.exe -m backend.run
pause
