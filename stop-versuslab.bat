@echo off
REM ==============================================================================
REM VersusLab Stop Script for Windows
REM Gracefully stops all running services
REM ==============================================================================

echo ========================================================================
echo                  Stopping VersusLab Services
echo ========================================================================
echo.

REM Stop Next.js Frontend
echo Stopping Next.js frontend...
taskkill /F /FI "WINDOWTITLE eq VersusLab Web*" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [OK] Frontend stopped
) else (
    echo [WARNING] Frontend not running
)

REM Stop FastAPI Backend
echo Stopping FastAPI backend...
taskkill /F /FI "WINDOWTITLE eq VersusLab API*" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [OK] API stopped
) else (
    echo [WARNING] API not running
)

REM Stop Docker services
echo Stopping Docker services...
docker-compose -f docker-compose.prod.yml down >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [OK] Docker services stopped
) else (
    echo [WARNING] Docker services not running
)

echo.
echo ========================================================================
echo              All VersusLab services stopped!
echo ========================================================================
echo.
echo Note: Ollama service is still running (system-level service)
echo   To stop Ollama manually: taskkill /F /IM ollama.exe
echo.
pause
