#!/usr/bin/env bash
# ==============================================================================
# VersusLab Stop Script
# Gracefully stops all running services
# ==============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

echo -e "${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                  Stopping VersusLab Services                   ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Stop Next.js Frontend
echo -e "${YELLOW}Stopping Next.js frontend...${NC}"
pkill -f "next dev" 2>/dev/null && echo -e "${GREEN}✓ Frontend stopped${NC}" || echo -e "${YELLOW}⚠ Frontend not running${NC}"

# Stop FastAPI Backend
echo -e "${YELLOW}Stopping FastAPI backend...${NC}"
pkill -f "uvicorn app.main:app" 2>/dev/null && echo -e "${GREEN}✓ API stopped${NC}" || echo -e "${YELLOW}⚠ API not running${NC}"

# Stop Docker services
echo -e "${YELLOW}Stopping Docker services...${NC}"
docker-compose -f docker-compose.prod.yml down 2>/dev/null && echo -e "${GREEN}✓ Docker services stopped${NC}" || echo -e "${YELLOW}⚠ Docker services not running${NC}"

# Note about Ollama (we don't stop it as it's a system service)
echo ""
echo -e "${BLUE}ℹ Note: Ollama service is still running (system-level service)${NC}"
echo -e "${BLUE}  To stop Ollama manually: ${YELLOW}pkill ollama${NC}"

echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║              All VersusLab services stopped!                   ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""
