@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "HOST=127.0.0.1"
set "PORT=8000"
set "ADMIN_URL=http://%HOST%:%PORT%/admin"
start "" "%ADMIN_URL%"
