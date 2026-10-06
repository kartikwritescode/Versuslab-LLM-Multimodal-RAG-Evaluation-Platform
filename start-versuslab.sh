#!/usr/bin/env bash
# ==============================================================================
# VersusLab Quick Start Script
# Starts all services in the correct order with proper health checks
# ==============================================================================

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Project root
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

echo -e "${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                    VersusLab Quick Start                       ║${NC}"
echo -e "${BLUE}║          Production LLM Evaluation & RAG Platform              ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# ==============================================================================
# Step 1: Check Prerequisites
# ==============================================================================
echo -e "${YELLOW}[1/7] Checking prerequisites...${NC}"

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}✗ Docker is not installed. Please install Docker first.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Docker installed${NC}"

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo -e "${RED}✗ Docker Compose is not installed. Please install Docker Compose first.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Docker Compose installed${NC}"

# Check if Ollama is installed
if ! command -v ollama &> /dev/null; then
    echo -e "${YELLOW}⚠ Ollama is not installed. Installing Ollama...${NC}"
    curl -fsSL https://ollama.com/install.sh | sh
fi
echo -e "${GREEN}✓ Ollama installed${NC}"

echo ""

# ==============================================================================
# Step 2: Check and Start Ollama
# ==============================================================================
echo -e "${YELLOW}[2/7] Starting Ollama service...${NC}"

# Check if Ollama is already running
if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Ollama is already running${NC}"
else
    echo -e "${YELLOW}Starting Ollama in background...${NC}"
    nohup ollama serve > /tmp/ollama.log 2>&1 &
    sleep 3

    # Wait for Ollama to be ready (max 30 seconds)
    for i in {1..30}; do
        if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
            echo -e "${GREEN}✓ Ollama started successfully${NC}"
            break
        fi
        if [ $i -eq 30 ]; then
            echo -e "${RED}✗ Ollama failed to start. Check /tmp/ollama.log for details.${NC}"
            exit 1
        fi
        sleep 1
    done
fi

echo ""

# ==============================================================================
# Step 3: Pull Required Ollama Models
# ==============================================================================
echo -e "${YELLOW}[3/7] Checking Ollama models...${NC}"

# Check if qwen3:8b is available
if ollama list | grep -q "qwen3:8b"; then
    echo -e "${GREEN}✓ qwen3:8b already available${NC}"
else
    echo -e "${YELLOW}Pulling qwen3:8b model (this may take a few minutes)...${NC}"
    ollama pull qwen3:8b
    echo -e "${GREEN}✓ qwen3:8b pulled successfully${NC}"
fi

# Check if nomic-embed-text is available
if ollama list | grep -q "nomic-embed-text"; then
    echo -e "${GREEN}✓ nomic-embed-text already available${NC}"
else
    echo -e "${YELLOW}Pulling nomic-embed-text model...${NC}"
    ollama pull nomic-embed-text
    echo -e "${GREEN}✓ nomic-embed-text pulled successfully${NC}"
fi

echo ""

# ==============================================================================
# Step 4: Start PostgreSQL with Docker Compose
# ==============================================================================
echo -e "${YELLOW}[4/7] Starting PostgreSQL database...${NC}"

docker-compose -f docker-compose.prod.yml up -d postgres

# Wait for PostgreSQL to be ready
echo -e "${YELLOW}Waiting for PostgreSQL to be ready...${NC}"
for i in {1..30}; do
    if docker-compose -f docker-compose.prod.yml ps postgres | grep -q "healthy"; then
        echo -e "${GREEN}✓ PostgreSQL is ready${NC}"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e "${RED}✗ PostgreSQL failed to start. Check logs with: docker-compose -f docker-compose.prod.yml logs postgres${NC}"
        exit 1
    fi
    sleep 1
done

echo ""

# ==============================================================================
# Step 5: Run Database Migrations
# ==============================================================================
echo -e "${YELLOW}[5/7] Running database migrations...${NC}"

cd apps/api

# Check if alembic is installed
if [ ! -d ".venv" ]; then
    echo -e "${YELLOW}Creating virtual environment...${NC}"
    python3 -m venv .venv
fi

source .venv/bin/activate 2>/dev/null || source .venv/Scripts/activate 2>/dev/null

# Install dependencies if needed
if ! python -c "import alembic" 2>/dev/null; then
    echo -e "${YELLOW}Installing Python dependencies...${NC}"
    pip install -q -r requirements.txt 2>/dev/null || pip install alembic sqlalchemy asyncpg fastapi
fi

# Run migrations
echo -e "${YELLOW}Applying database migrations...${NC}"
alembic upgrade head

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Database migrations applied successfully${NC}"
else
    echo -e "${RED}✗ Database migration failed${NC}"
    exit 1
fi

cd ../..
echo ""

# ==============================================================================
# Step 6: Start FastAPI Backend
# ==============================================================================
echo -e "${YELLOW}[6/7] Starting FastAPI backend...${NC}"

cd apps/api
source .venv/bin/activate 2>/dev/null || source .venv/Scripts/activate 2>/dev/null

# Kill any existing API process
pkill -f "uvicorn app.main:app" 2>/dev/null || true

# Start API in background
nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload > /tmp/versuslab-api.log 2>&1 &
API_PID=$!

# Wait for API to be ready
echo -e "${YELLOW}Waiting for API to be ready...${NC}"
for i in {1..30}; do
    if curl -s http://localhost:8000/api/health > /dev/null 2>&1; then
        echo -e "${GREEN}✓ API is ready (PID: $API_PID)${NC}"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e "${RED}✗ API failed to start. Check /tmp/versuslab-api.log for details.${NC}"
        exit 1
    fi
    sleep 1
done

cd ../..
echo ""

# ==============================================================================
# Step 7: Start Next.js Frontend
# ==============================================================================
echo -e "${YELLOW}[7/7] Starting Next.js frontend...${NC}"

cd apps/web

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo -e "${YELLOW}Installing Node.js dependencies (this may take a few minutes)...${NC}"
    npm install
fi

# Kill any existing Next.js process
pkill -f "next dev" 2>/dev/null || true

# Start Next.js in background
nohup npm run dev > /tmp/versuslab-web.log 2>&1 &
WEB_PID=$!

# Wait for Next.js to be ready
echo -e "${YELLOW}Waiting for frontend to be ready...${NC}"
for i in {1..60}; do
    if curl -s http://localhost:3000 > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Frontend is ready (PID: $WEB_PID)${NC}"
        break
    fi
    if [ $i -eq 60 ]; then
        echo -e "${RED}✗ Frontend failed to start. Check /tmp/versuslab-web.log for details.${NC}"
        exit 1
    fi
    sleep 1
done

cd ../..
echo ""

# ==============================================================================
# Success Message
# ==============================================================================
echo -e "${GREEN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                    🎉 SUCCESS! 🎉                              ║${NC}"
echo -e "${GREEN}║            VersusLab is now running!                           ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BLUE}📍 Services Running:${NC}"
echo -e "   ${GREEN}✓${NC} Ollama:      ${YELLOW}http://localhost:11434${NC}"
echo -e "   ${GREEN}✓${NC} PostgreSQL:  ${YELLOW}localhost:5433${NC}"
echo -e "   ${GREEN}✓${NC} FastAPI:     ${YELLOW}http://localhost:8000${NC}"
echo -e "   ${GREEN}✓${NC} Next.js Web: ${YELLOW}http://localhost:3000${NC}"
echo ""
echo -e "${BLUE}🚀 Quick Links:${NC}"
echo -e "   • Main UI:        ${YELLOW}http://localhost:3000${NC}"
echo -e "   • API Health:     ${YELLOW}http://localhost:8000/api/health${NC}"
echo -e "   • API Docs:       ${YELLOW}http://localhost:8000/docs${NC}"
echo -e "   • Prometheus:     ${YELLOW}http://localhost:9090${NC}"
echo ""
echo -e "${BLUE}📝 Logs:${NC}"
echo -e "   • Ollama:     ${YELLOW}tail -f /tmp/ollama.log${NC}"
echo -e "   • API:        ${YELLOW}tail -f /tmp/versuslab-api.log${NC}"
echo -e "   • Frontend:   ${YELLOW}tail -f /tmp/versuslab-web.log${NC}"
echo -e "   • PostgreSQL: ${YELLOW}docker-compose -f docker-compose.prod.yml logs -f postgres${NC}"
echo ""
echo -e "${BLUE}🛑 To stop all services:${NC}"
echo -e "   ${YELLOW}./stop-versuslab.sh${NC}"
echo ""
echo -e "${GREEN}Open your browser and visit: http://localhost:3000${NC}"
echo ""
