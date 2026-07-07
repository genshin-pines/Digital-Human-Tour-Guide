@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if errorlevel 1 (
  echo Failed to enter project directory: %~dp0
  pause
  exit /b 1
)

set "HOST=127.0.0.1"
set "PORT=8000"
set "APP_URL=http://%HOST%:%PORT%/visitor"
set "ADMIN_URL=http://%HOST%:%PORT%/admin"
set "BUNDLED_PYTHON=C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
set "LOG_FILE=%~dp0server.log"

if exist "%BUNDLED_PYTHON%" (
  set "PYTHON_EXE=%BUNDLED_PYTHON%"
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo Python was not found.
    echo Please install Python or run this project from Codex bundled runtime.
    pause
    exit /b 1
  )
  set "PYTHON_EXE=python"
)

if not exist "%~dp0app.py" (
  echo app.py was not found in %~dp0
  pause
  exit /b 1
)

netstat -ano | findstr ":%PORT% " | findstr "LISTENING" >nul 2>nul
if not errorlevel 1 (
  echo Port %PORT% is already running. Opening pages only.
  echo If the app does not respond, close the old black server window first.
  start "" "%APP_URL%"
  start "" "%ADMIN_URL%"
  pause
  exit /b 0
)

echo.
echo ==========================================
echo  Lingshan AI Guide - Phase 4 Launcher
echo ==========================================
echo.
echo Project: %~dp0
echo Visitor: %APP_URL%
echo Admin:   %ADMIN_URL%
echo Integrations: http://%HOST%:%PORT%/api/integrations
echo.
echo Keep this window open while using the app.
echo Press Ctrl+C to stop the server.
echo Log file: %LOG_FILE%
echo.

start "open visitor and admin later" powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; $edge=(Get-Command msedge -ErrorAction SilentlyContinue); if ($edge) { Start-Process msedge -ArgumentList '--new-window','%APP_URL%'; Start-Process msedge -ArgumentList '--new-window','%ADMIN_URL%' } else { Start-Process '%APP_URL%'; Start-Process '%ADMIN_URL%' }"
"%PYTHON_EXE%" "%~dp0app.py" --host %HOST% --port %PORT% 1>> "%LOG_FILE%" 2>>&1

echo.
echo Server stopped or failed to start. Exit code: %ERRORLEVEL%
echo If port 8000 is busy, close the old server window and run start.bat again.
pause
