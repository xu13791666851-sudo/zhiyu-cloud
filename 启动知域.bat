@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ================================
echo   ZhiYu Docker Compose Startup
echo ================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"

echo.
pause
