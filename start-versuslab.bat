@echo off
REM ==============================================================================
REM VersusLab Quick Start Script for Windows
REM Starts all services in the correct order with proper health checks
REM ==============================================================================

setlocal enabledelayedexpansion

echo ========================================================================
echo                     VersusLab Quick Start
echo          Production LLM Evaluation ^& RAG Platform
echo ========================================================================
echo.

REM ==============================================================================
REM Step 1: Check Prerequisites
REM ==============================================================================
echo [1/7] Checking prerequisites...

REM Check if Docker is installed
where docker >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Docker is not installed. Please install Docker Desktop first.
    pause
    exit /b 1
)
echo [OK] Docker installed

REM Check if Python is installed
where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python is not installed. Please install Python 3.12+ first.
    pause
    exit /b 1
)
echo [OK] Python installed

REM Check if Node.js is installed
where node >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Node.js is not installed. Please install Node.js 18+ first.
    pause
    exit /b 1
)
echo [OK] Node.js installed

REM Check if Ollama is installed
where ollama >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [WARNING] Ollama is not installed.
    echo Please install Ollama from: https://ollama.com/download
    pause
    exit /b 1
)
echo [OK] Ollama installed
echo.

REM ==============================================================================
REM Step 2: Check and Start Ollama
REM ==============================================================================
echo [2/7] Starting Ollama service...

curl -s http://localhost:11434/api/tags >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [OK] Ollama is already running
) else (
    echo Starting Ollama in background...
    start /B ollama serve
    timeout /t 3 /nobreak >nul

    REM Wait for Ollama to be ready
    set "OLLAMA_READY=0"
    for /L %%i in (1,1,30) do (
        curl -s http://localhost:11434/api/tags >nul 2>&1
        if !ERRORLEVEL! EQU 0 (
            echo [OK] Ollama started successfully
            set "OLLAMA_READY=1"
            goto :ollama_ready
        )
        timeout /t 1 /nobreak >nul
    )

    :ollama_ready
    if !OLLAMA_READY! EQU 0 (
        echo [ERROR] Ollama failed to start
        pause
        exit /b 1
    )
)
echo.

REM ==============================================================================
REM Step 3: Pull Required Ollama Models
REM ==============================================================================
echo [3/7] Checking Ollama models...

echo Checking for qwen3:8b...
ollama list > "%TEMP%\ollama_list.txt" 2>&1
type "%TEMP%\ollama_list.txt" | findstr /C:"qwen3:8b" >nul
if errorlevel 1 (
    echo Pulling qwen3:8b model - this may take several minutes...
    ollama pull qwen3:8b
    echo Model qwen3:8b pulled successfully
) else (
    echo [OK] qwen3:8b already available
)

echo Checking for nomic-embed-text...
ollama list > "%TEMP%\ollama_list.txt" 2>&1
type "%TEMP%\ollama_list.txt" | findstr /C:"nomic-embed-text" >nul
if errorlevel 1 (
    echo Pulling nomic-embed-text model...
    ollama pull nomic-embed-text
    echo Model nomic-embed-text pulled successfully
) else (
    echo [OK] nomic-embed-text already available
)

if exist "%TEMP%\ollama_list.txt" del "%TEMP%\ollama_list.txt"
echo.

REM ==============================================================================
REM Step 4: Start PostgreSQL with Docker Compose
REM ==============================================================================
echo [4/7] Starting PostgreSQL database...

docker-compose -f docker-compose.prod.yml up -d postgres

echo Waiting for PostgreSQL to be ready...
timeout /t 5 /nobreak >nul

docker-compose -f docker-compose.prod.yml ps postgres | findstr /C:"healthy" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [OK] PostgreSQL is ready
) else (
    echo [WARNING] PostgreSQL may still be starting up. Continuing anyway...
)
echo.

REM ==============================================================================
REM Step 5: Run Database Migrations
REM ==============================================================================
echo [5/7] Running database migrations...

cd apps\api

REM Create virtual environment if it doesn't exist
if not exist .venv (
    echo Creating virtual environment...
    python -m venv .venv
)

REM Activate virtual environment
call .venv\Scripts\activate.bat

REM Install dependencies
echo Installing Python dependencies...
pip install -q -r requirements.txt 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo Installing core dependencies...
    pip install alembic sqlalchemy asyncpg fastapi uvicorn
)

REM Run migrations
echo Applying database migrations...
alembic upgrade head

if %ERRORLEVEL% EQU 0 (
    echo [OK] Database migrations applied successfully
) else (
    echo [ERROR] Database migration failed
    cd ..\..
    pause
    exit /b 1
)

cd ..\..
echo.

REM ==============================================================================
REM Step 6: Start FastAPI Backend
REM ==============================================================================
echo [6/7] Starting FastAPI backend...

cd apps\api
call .venv\Scripts\activate.bat

REM Kill any existing API process
taskkill /F /IM python.exe /FI "WINDOWTITLE eq *uvicorn*" >nul 2>&1

REM Start API in new window
start "VersusLab API" /MIN cmd /c "uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload > ..\..\versuslab-api.log 2>&1"

echo Waiting for API to be ready...
timeout /t 3 /nobreak >nul

REM Wait for API to be ready
set "API_READY=0"
for /L %%i in (1,1,30) do (
    curl -s http://localhost:8000/api/health >nul 2>&1
    if !ERRORLEVEL! EQU 0 (
        echo [OK] API is ready
        set "API_READY=1"
        goto :api_ready
    )
    timeout /t 1 /nobreak >nul
)

:api_ready
if !API_READY! EQU 0 (
    echo [ERROR] API failed to start. Check versuslab-api.log for details.
    cd ..\..
    pause
    exit /b 1
)

cd ..\..
echo.

REM ==============================================================================
REM Step 7: Start Next.js Frontend
REM ==============================================================================
echo [7/7] Starting Next.js frontend...

cd apps\web

REM Install node_modules if missing
if not exist node_modules (
    echo Installing Node.js dependencies (this may take a few minutes)...
    npm install
)

REM Start Next.js in new window
start "VersusLab Web" /MIN cmd /c "npm run dev > ..\..\versuslab-web.log 2>&1"

echo Waiting for frontend to be ready...
timeout /t 5 /nobreak >nul

REM Wait for Next.js to be ready
set "WEB_READY=0"
for /L %%i in (1,1,60) do (
    curl -s http://localhost:3000 >nul 2>&1
    if !ERRORLEVEL! EQU 0 (
        echo [OK] Frontend is ready
        set "WEB_READY=1"
        goto :web_ready
    )
    timeout /t 1 /nobreak >nul
)

:web_ready
if !WEB_READY! EQU 0 (
    echo [ERROR] Frontend failed to start. Check versuslab-web.log for details.
    cd ..\..
    pause
    exit /b 1
)

cd ..\..
echo.

REM ==============================================================================
REM Success Message
REM ==============================================================================
echo ========================================================================
echo                         SUCCESS!
echo                 VersusLab is now running!
echo ========================================================================
echo.
echo Services Running:
echo   [OK] Ollama:      http://localhost:11434
echo   [OK] PostgreSQL:  localhost:5433
echo   [OK] FastAPI:     http://localhost:8000
echo   [OK] Next.js Web: http://localhost:3000
echo.
echo Quick Links:
echo   * Main UI:        http://localhost:3000
echo   * API Health:     http://localhost:8000/api/health
echo   * API Docs:       http://localhost:8000/docs
echo.
echo Logs:
echo   * API:        versuslab-api.log
echo   * Frontend:   versuslab-web.log
echo.
echo To stop all services: run stop-versuslab.bat
echo.
echo Opening browser...
timeout /t 2 /nobreak >nul
start http://localhost:3000
echo.
pause
