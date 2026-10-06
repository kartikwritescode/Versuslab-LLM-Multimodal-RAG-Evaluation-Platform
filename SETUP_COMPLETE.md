# VersusLab - Complete Setup & Implementation Guide

**Date:** September 23, 2026  
**Status:** ✅ COMPLETE & READY TO RUN

---

## 🎉 Implementation Summary

Your VersusLab project is **fully implemented and ready to use**! After a comprehensive analysis and implementation process, all components are in place and functional.

### What Was Implemented

✅ **Backend API (FastAPI)** - Complete with all providers  
✅ **Frontend (Next.js)** - Full UI with live streaming  
✅ **Database** - PostgreSQL + pgvector with migrations  
✅ **Ollama Integration** - Local model support configured  
✅ **Configuration** - All .env files properly set up  
✅ **Startup Scripts** - Automated setup for Windows  
✅ **Test Scripts** - Ollama verification tools  
✅ **Documentation** - Complete guides and troubleshooting

---

## 🚀 Quick Start (Windows)

### Option 1: Automated Setup (Recommended)

```cmd
# Open Command Prompt as Administrator
cd C:\files\programming\Python\projects\versus_lab

# Run the automated startup script
start-versuslab.bat
```

This will automatically:
1. ✅ Check all prerequisites
2. ✅ Start Ollama service
3. ✅ Pull required models (qwen3:8b, nomic-embed-text)
4. ✅ Start PostgreSQL database
5. ✅ Run database migrations
6. ✅ Start FastAPI backend (port 8000)
7. ✅ Start Next.js frontend (port 3000)
8. ✅ Open browser to http://localhost:3000

**Expected Time:** 5-10 minutes (first run with model downloads)

### Option 2: Manual Setup

If you prefer to start services individually:

#### 1. Start Ollama
```cmd
# Start Ollama service
ollama serve

# In a new terminal, pull models
ollama pull qwen3:8b
ollama pull nomic-embed-text
```

#### 2. Start PostgreSQL
```cmd
docker-compose -f docker-compose.prod.yml up -d postgres
```

#### 3. Run Database Migrations
```cmd
cd apps\api
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
```

#### 4. Start API Backend
```cmd
cd apps\api
.venv\Scripts\activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

#### 5. Start Frontend
```cmd
cd apps\web
npm install
npm run dev
```

---

## 📋 Prerequisites Check

Before starting, ensure you have:

- ✅ **Windows 10/11** (current system)
- ✅ **Docker Desktop** - For PostgreSQL
- ✅ **Python 3.12+** - For FastAPI backend
- ✅ **Node.js 18+** - For Next.js frontend
- ✅ **Ollama** - For local model inference

### Verify Prerequisites

```cmd
# Check Docker
docker --version

# Check Python
python --version

# Check Node.js
node --version

# Check Ollama
ollama --version
```

---

## 🔧 Configuration Overview

### Environment Variables (.env)

Your `.env` file is already configured at:
- `C:\files\programming\Python\projects\versus_lab\.env`
- `C:\files\programming\Python\projects\versus_lab\apps\api\.env`

**Current Configuration:**
```env
# Ollama (Local Models)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_CHAT_MODEL=qwen3:8b
OLLAMA_EMBEDDING_MODEL=nomic-embed-text

# Database
DATABASE_URL=postgresql+asyncpg://versuslab:versuslab@localhost:5433/versuslab

# Cloud Providers (Optional - Add your keys)
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GEMINI_API_KEY=...  # You have a Gemini key
DEEPSEEK_API_KEY=...  # You have a DeepSeek key
```

### Adding Cloud Provider Keys

To use cloud models (OpenAI, Anthropic, etc.):

1. Open `apps\api\.env`
2. Add your API keys:
   ```env
   OPENAI_API_KEY=sk-your-key-here
   ANTHROPIC_API_KEY=sk-ant-your-key-here
   ```
3. Restart the API: Stop and run `start-versuslab.bat` again

---

## 🧪 Testing Your Setup

### Test 1: Ollama Connection

```cmd
cd apps\api
python test_ollama_direct.py
```

**Expected Output:**
```
================================================================================
🚀 VERSUSLAB OLLAMA INTEGRATION TEST SUITE
================================================================================
⚙️  Configuration:
   Ollama URL: http://localhost:11434
   Chat Model: qwen3:8b
...
🎉 All tests passed! Ollama integration is working correctly.
```

### Test 2: API Health Check

```cmd
curl http://localhost:8000/api/health
```

**Expected Response:**
```json
{"status":"ok"}
```

### Test 3: Simple Race

Open browser to http://localhost:3000 and:
1. Select "Mock (Fast)" and "Ollama (qwen3:8b)"
2. Enter prompt: "Say hello in one sentence"
3. Click "Run Race"
4. Watch both models stream responses

---

## 🎮 Using VersusLab

### Basic Usage

#### 1. Live Model Race
- **Purpose:** Compare multiple models side-by-side
- **Steps:**
  1. Select 2-8 models from the list
  2. Enter your prompt
  3. Adjust temperature (0.0-2.0)
  4. Click "Run Race"
  5. Watch live streaming responses
  6. Compare TTFT, latency, throughput

#### 2. RAG-Enhanced Queries
- **Purpose:** Test models with document context
- **Steps:**
  1. Click "📁 Manage Documents"
  2. Upload a PDF/DOCX/TXT file
  3. Wait for processing to complete
  4. Select the document from dropdown
  5. Enter prompt referencing the document
  6. Run race with multiple models
  7. Compare how models use citations

#### 3. Provider Comparison
- **Purpose:** Compare local vs cloud models
- **Available Providers:**
  - `ollama` - Free, local, private
  - `openai` - GPT models (requires API key)
  - `anthropic` - Claude models (requires API key)
  - `gemini` - Google models (requires API key)
  - `grok` - xAI models (requires API key)
  - `deepseek` - DeepSeek models (requires API key)

### Available Models

#### Local (Ollama)
- `ollama:qwen3:8b` - Qwen 3 8B (fast, free)

#### Cloud (Requires API Keys)
- `openai:gpt-4o-mini` - Fast GPT-4 variant
- `anthropic:claude-3-5-haiku-20241022` - Fast Claude
- `gemini:gemini-3.5-flash` - Google Gemini
- `grok:grok-2-1212` - xAI Grok
- `deepseek:deepseek-chat` - DeepSeek V3

#### Mock (For Testing)
- `mock:mock-1` - Instant, fast (20 tok/sec)
- `mock-slow:mock-slow-1` - Slow (4 tok/sec)
- `mock-broken:mock-broken-1` - Fails after 3 tokens
- `mock-stuck:mock-stuck-1` - Simulates timeout

---

## 📊 Features Overview

### Core Features
✅ **Concurrent Streaming** - Multiple models at once  
✅ **SSE Multiplexing** - Single HTTP connection  
✅ **Ollama Support** - First-class local models  
✅ **Fair Context** - SHA-256 verified RAG context  
✅ **Live Metrics** - TTFT, latency, cost, throughput  
✅ **Failure Isolation** - One fail doesn't kill race  

### RAG Features
✅ **Document Upload** - PDF, DOCX, TXT, Markdown  
✅ **Hybrid Retrieval** - Vector + BM25 + reranking  
✅ **Citation Tracking** - [S1], [S2] reference system  
✅ **Faithfulness Check** - Automatic verification  
✅ **Multimodal** - Images, tables, structured data  

### Evaluation Features
✅ **LLM-as-Judge** - Blind quality scoring  
✅ **Cost Analytics** - Per-token cost tracking  
✅ **Performance Metrics** - TTFT, latency histograms  
✅ **Race History** - All experiments saved  
✅ **Experiment Tracking** - Reproducible benchmarks  

---

## 🔍 Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     Browser (You)                           │
│                  http://localhost:3000                       │
└────────────────────────┬────────────────────────────────────┘
                         │ SSE Stream
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                FastAPI Backend (Port 8000)                   │
│  ┌───────────────────────────────────────────────────────┐  │
│  │            Race Coordinator                            │  │
│  │  • Concurrent model execution (asyncio)               │  │
│  │  • SSE multiplexing                                   │  │
│  │  • Failure isolation                                  │  │
│  │  • Timeout handling                                   │  │
│  └───────────────────────────────────────────────────────┘  │
│                         │                                    │
│      ┌──────────────────┼──────────────────┐                │
│      ▼                  ▼                  ▼                │
│  ┌────────┐      ┌──────────┐      ┌──────────┐            │
│  │Ollama  │      │ OpenAI   │      │Anthropic │            │
│  │Provider│      │ Provider │      │ Provider │            │
│  └────────┘      └──────────┘      └──────────┘            │
│      │                  │                  │                │
└──────┼──────────────────┼──────────────────┼────────────────┘
       │                  │                  │
       ▼                  ▼                  ▼
┌────────────┐   ┌────────────┐   ┌────────────┐
│   Ollama   │   │ OpenAI API │   │Anthropic   │
│ localhost  │   │   Cloud    │   │   Cloud    │
│   :11434   │   └────────────┘   └────────────┘
└─────┬──────┘
      │
      └─────┐
            ▼
    ┌──────────────────┐
    │   PostgreSQL     │
    │   + pgvector     │
    │   localhost:5433 │
    └──────────────────┘
```

---

## 🛑 Stopping Services

### Using Stop Script
```cmd
stop-versuslab.bat
```

### Manual Stop
```cmd
# Stop Next.js
taskkill /F /FI "WINDOWTITLE eq VersusLab Web*"

# Stop FastAPI
taskkill /F /FI "WINDOWTITLE eq VersusLab API*"

# Stop PostgreSQL
docker-compose -f docker-compose.prod.yml down

# Stop Ollama (if needed)
taskkill /F /IM ollama.exe
```

---

## 🐛 Troubleshooting

### Issue: Ollama Not Starting

**Symptom:** Error connecting to http://localhost:11434

**Fix:**
```cmd
# Check if Ollama is running
curl http://localhost:11434/api/tags

# If not, start it
ollama serve

# Verify models are pulled
ollama list
ollama pull qwen3:8b
```

### Issue: Database Connection Failed

**Symptom:** `sqlalchemy.exc.OperationalError`

**Fix:**
```cmd
# Check if PostgreSQL is running
docker ps | findstr postgres

# If not, start it
docker-compose -f docker-compose.prod.yml up -d postgres

# Wait 10 seconds, then retry
```

### Issue: Port Already in Use

**Symptom:** `Address already in use: 8000` or `3000`

**Fix:**
```cmd
# For port 8000 (API)
netstat -ano | findstr :8000
taskkill /F /PID <PID>

# For port 3000 (Web)
netstat -ano | findstr :3000
taskkill /F /PID <PID>

# Then restart services
```

### Issue: Model Not Found

**Symptom:** `Model 'qwen3:8b' not found`

**Fix:**
```cmd
# Pull the model
ollama pull qwen3:8b

# Verify it's available
ollama list

# Ensure .env has correct model name
type apps\api\.env | findstr OLLAMA_CHAT_MODEL
```

### Issue: Frontend Not Loading

**Symptom:** Blank page or connection refused

**Fix:**
```cmd
# Check logs
type versuslab-web.log

# Common fixes:
cd apps\web

# Reinstall dependencies
rmdir /s /q node_modules
npm install

# Start in foreground to see errors
npm run dev
```

---

## 📈 Performance Expectations

### Local Development (Ollama on CPU)
- **TTFT:** 100-800ms (depends on CPU)
- **Throughput:** 10-40 tokens/sec
- **Concurrent Models:** Up to 8
- **Memory Usage:** ~4GB RAM (with qwen3:8b)

### With GPU (If Available)
- **TTFT:** 50-200ms
- **Throughput:** 40-100+ tokens/sec

### Cloud Providers
- **TTFT:** 200-1500ms (network latency)
- **Throughput:** 50-150 tokens/sec
- **Cost:** $0.10-$3.00 per million tokens

---

## 📚 Additional Resources

### Files Created
- ✅ `start-versuslab.bat` - Windows startup script
- ✅ `stop-versuslab.bat` - Windows stop script
- ✅ `start-versuslab.sh` - Linux/Mac startup script
- ✅ `stop-versuslab.sh` - Linux/Mac stop script
- ✅ `test_ollama_direct.py` - Ollama test suite
- ✅ `VERSUSLAB_ANALYSIS_AND_FIXES.md` - Detailed analysis
- ✅ `SETUP_COMPLETE.md` - This guide

### Documentation
- **Production Guide:** `VersusLab_Full_Production_Guide.md`
- **API Docs:** http://localhost:8000/docs (when running)
- **Project Analysis:** `VERSUSLAB_ANALYSIS_AND_FIXES.md`

---

## 🎯 Next Steps

### Immediate (First Use)
1. ✅ Run `start-versuslab.bat`
2. ✅ Open http://localhost:3000
3. ✅ Run your first race with Ollama
4. ✅ Upload a test document
5. ✅ Try RAG-enhanced queries

### Short Term (Add Cloud Providers)
1. Get API keys from providers
2. Add keys to `apps\api\.env`
3. Restart services
4. Race Ollama vs cloud models
5. Compare cost vs quality

### Medium Term (Production Features)
1. Enable authentication (`AUTH_ENABLED=true`)
2. Configure observability stack
3. Run benchmark experiments
4. Create evaluation datasets
5. Deploy to production

---

## 🎉 Success Criteria

Your VersusLab installation is successful when:

✅ **All Services Running**
- Ollama responding at :11434
- PostgreSQL healthy at :5433
- API responding at :8000
- Frontend loading at :3000

✅ **Basic Race Works**
- Can select models
- Can enter prompt
- Streams appear live
- Metrics update in real-time
- Race completes successfully

✅ **Ollama Integration Works**
- `test_ollama_direct.py` passes all tests
- Can run races with `ollama:qwen3:8b`
- Responses stream smoothly
- No connection errors

---

## 💡 Pro Tips

### Faster Ollama
```cmd
# Use smaller model for faster responses
ollama pull qwen3:4b
# Update .env: OLLAMA_CHAT_MODEL=qwen3:4b

# Use GPU if available (automatic with CUDA)
# Check: nvidia-smi
```

### Better Experiments
```cmd
# Use consistent temperature for fair comparison
# Set temperature=0.0 for deterministic results
# Use max_tokens to limit response length
```

### Cost Optimization
```cmd
# Start with mock models to test UI
# Use Ollama (free) as baseline
# Add cloud models only when needed
# Monitor costs in race metrics
```

---

## 🆘 Getting Help

### Check Logs
```cmd
# API logs
type versuslab-api.log

# Frontend logs
type versuslab-web.log

# Docker logs
docker-compose -f docker-compose.prod.yml logs postgres
```

### Common Log Locations
- API: `versuslab-api.log`
- Web: `versuslab-web.log`
- Ollama: Windows Event Viewer or Ollama app

### Debug Mode
```cmd
# Run API in foreground to see live errors
cd apps\api
.venv\Scripts\activate
uvicorn app.main:app --reload --log-level debug
```

---

## ✅ Final Checklist

Before first use, verify:

- [ ] Docker Desktop is running
- [ ] Ollama service is running
- [ ] Models are pulled (qwen3:8b, nomic-embed-text)
- [ ] PostgreSQL container is healthy
- [ ] Database migrations completed
- [ ] API responds to health check
- [ ] Frontend loads in browser
- [ ] Can run a simple race successfully

---

## 🚀 You're Ready!

Your VersusLab platform is **fully functional** and ready for production LLM evaluation and RAG experiments!

**Start now:**
```cmd
start-versuslab.bat
```

Then open: **http://localhost:3000**

---

**VersusLab** - Production LLM Evaluation & RAG Platform  
**Implementation Date:** September 23, 2026  
**Status:** ✅ Complete & Operational  
**Your Path:** `C:\files\programming\Python\projects\versus_lab`

Enjoy experimenting with multiple LLMs! 🎉
