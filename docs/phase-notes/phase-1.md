# Phase 1: Backend Foundations & Typed Provider Abstraction

Welcome to the Phase 1 documentation notes for **VersusLab**! This document explains what was built, why it was designed this way, which files were touched, how to run and verify everything using PowerShell, and 5 foundational software engineering concepts to help you understand the architecture as a beginner.

---

## 1. What We Built

In Phase 1, we laid the core backend foundation for VersusLab:
1. **Typed Provider Abstraction**: A standardized contract (`ModelProvider`) that allows any AI model provider (local or cloud) to stream token deltas in a unified format (`ModelDelta`).
2. **Deterministic Mock Provider (`MockProvider`)**: A simulated LLM provider with configurable initial token delay, token generation speed, and optional failure injection. It allows testing streaming logic, frontend renderers, and error handling without spending money or needing an internet connection.
3. **Local Ollama Provider (`OllamaProvider`)**: A production-ready adapter for local LLMs running via Ollama. It connects using `httpx.AsyncClient`, streams line-by-line JSON chunks from `/api/chat`, skips empty chunks to support reasoning/thinking models (such as DeepSeek-R1 or Qwen-Thinking), and extracts token usage stats upon completion.
4. **Central Provider Registry (`PROVIDERS` & `DEFAULT_MODELS`)**: A central registry in `app/providers/registry.py` decoupling API endpoints from individual provider implementations.
5. **Configuration System (`Settings`)**: Using `pydantic-settings` to safely read configuration and environment variables from `.env` or system environment variables with sensible defaults (`http://localhost:11434` for Ollama, `qwen3:4b` for the default model).
6. **FastAPI Application & Endpoints**:
   - `GET /api/health`: A simple health check returning `{"status": "ok"}`.
   - `GET /api/stream`: A temporary single-model Server-Sent Events (SSE) streaming endpoint for testing and verifying providers in real-time before Phase 2 introduces the multiplexed race coordinator.
7. **Test Suite**: Automated tests using `pytest` and `pytest-asyncio` covering happy paths and failure paths for all providers and endpoints without touching the real network.

---

## 2. Why We Built It This Way

- **Isolation & Decoupling**: If the rest of the application (race coordinator, evaluators, frontend) had to know how Ollama formats its JSON vs OpenAI vs Anthropic, the code would quickly become a mess of `if/else` checks. By normalizing everything into `ModelDelta` at the provider boundary, the rest of VersusLab only deals with one clean protocol.
- **Accurate Metric Capture**: `ModelDelta` stamps nanosecond-precision timestamps using `Field(default_factory=time.time_ns)`. This enables VersusLab to accurately measure Time To First Token (TTFT) and throughput (tokens/second) down to the microsecond level.
- **Failure Resilience ("Errors are Data")**: In distributed systems and multi-model benchmarking, network timeouts or model errors are normal occurrences. By catching errors and yielding error deltas (or raising typed exceptions in generators), one failing model will never crash the server or break other streaming models.

---

## 3. Files Touched and Created

```text
versus_lab/
├── .gitignore                          # Ignores .venv/, __pycache__/, and .env secrets
├── docs/
│   └── phase-notes/
│       └── phase-1.md                  # This documentation file
└── apps/
    └── api/
        ├── requirements.txt            # Top-level backend dependencies
        ├── .env.example                # Documented template for environment variables
        ├── app/
        │   ├── __init__.py
        │   ├── main.py                 # FastAPI application and /api/health endpoint
        │   ├── api/
        │   │   ├── __init__.py
        │   │   ├── stream.py           # Temporary /api/stream SSE endpoint
        │   │   └── race.py             # (Unmounted placeholder for Phase 2 race logic)
        │   ├── core/
        │   │   ├── __init__.py
        │   │   └── config.py           # Pydantic BaseSettings configuration
        │   ├── providers/
        │   │   ├── __init__.py
        │   │   ├── types.py            # Message, ModelRequest, Usage, ModelDelta
        │   │   ├── base.py             # ModelProvider Protocol definition
        │   │   ├── mock.py             # MockProvider implementation
        │   │   ├── ollama.py           # OllamaProvider implementation
        │   │   └── registry.py         # PROVIDERS and DEFAULT_MODELS maps
        │   └── race/
        │       ├── __init__.py
        │       ├── coordinator.py      # (Phase 2 race coordinator)
        │       └── events.py           # (Phase 2 event definitions)
        └── tests/
            ├── __init__.py
            ├── test_health.py          # Verifies /api/health returns 200
            ├── test_mock_provider.py   # Tests MockProvider generation & failure injection
            ├── test_ollama_provider.py # Tests OllamaProvider with mock network transport
            └── test_stream_endpoint.py # Tests SSE streaming and error responses
```

---

## 4. How to Run and Verify

All commands should be run from PowerShell in the project directory (`c:\files\programming\Python\projects\versus_lab`).

### Step A: Set Up the Virtual Environment and Install Dependencies
```powershell
# Navigate to apps/api
cd apps/api

# Create a virtual environment with Python 3.12 (if not already created)
py -3.12 -m venv .venv

# Activate the virtual environment
.\.venv\Scripts\Activate.ps1

# Install runtime dependencies
pip install -r requirements.txt

# Install test & linting tools
pip install ruff pytest pytest-asyncio
```

### Step B: Run Automated Tests and Linting
Verify that all tests pass and code style complies with `ruff`:
```powershell
# Run the test suite
pytest

# Expected Output:
# ============================== 7 passed in 1.xx s ==============================

# Run the linter
ruff check .

# Expected Output:
# All checks passed!
```

### Step C: Start the Development Server
```powershell
uvicorn app.main:app --reload --port 8000
```
Expected output:
```text
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [...]
INFO:     Application startup complete.
```

### Step D: Test Endpoints with `curl.exe`

Open a second PowerShell window and test the following:

#### 1. Test Health Check
```powershell
curl.exe -i http://localhost:8000/api/health
```
**Expected Output:**
```http
HTTP/1.1 200 OK
content-type: application/json

{"status":"ok"}
```

#### 2. Test Mock Provider Streaming
```powershell
curl.exe -N -i "http://localhost:8000/api/stream?prompt=hello+world&provider=mock"
```
*Note: The `-N` flag disables curl's output buffering so you see the tokens stream live.*

**Expected Output:**
```http
HTTP/1.1 200 OK
cache-control: no-cache
x-accel-buffering: no
content-type: text/event-stream; charset=utf-8

data: {"model_id":"mock-1","sequence":0,"text":"This ","finish_reason":null,"usage":null,"timestamp_ns":1790052621852066100}

data: {"model_id":"mock-1","sequence":1,"text":"is ","finish_reason":null,"usage":null,"timestamp_ns":1790052621932939800}

data: {"model_id":"mock-1","sequence":2,"text":"a ","finish_reason":null,"usage":null,"timestamp_ns":1790052622009247700}

data: {"model_id":"mock-1","sequence":3,"text":"mock ","finish_reason":null,"usage":null,"timestamp_ns":1790052622073061600}

data: {"model_id":"mock-1","sequence":4,"text":"answer ","finish_reason":null,"usage":null,"timestamp_ns":1790052622154375400}

data: {"model_id":"mock-1","sequence":5,"text":"to: ","finish_reason":null,"usage":null,"timestamp_ns":1790052622225657800}

data: {"model_id":"mock-1","sequence":6,"text":"hello ","finish_reason":null,"usage":null,"timestamp_ns":1790052622286317400}

data: {"model_id":"mock-1","sequence":7,"text":"world ","finish_reason":null,"usage":null,"timestamp_ns":1790052622361254100}

data: {"model_id":"mock-1","sequence":8,"text":null,"finish_reason":"stop","usage":{"input_tokens":2,"output_tokens":8},"timestamp_ns":1790052622361254100}
```

#### 3. Test Ollama Provider Streaming
Ensure your local Ollama daemon is running (`ollama serve`) with the default model downloaded (e.g. `ollama pull qwen3:4b`):
```powershell
curl.exe -N -i "http://localhost:8000/api/stream?prompt=why+is+the+sky+blue&provider=ollama"
```
**Expected Output (with Ollama running):**
Live stream of text tokens generated by your local model, followed by a final delta containing `finish_reason: "stop"` and `usage` token counts.

**Expected Output (if Ollama is stopped):**
Instead of crashing or hanging indefinitely, the endpoint times out fast on connection and streams an error delta:
```http
HTTP/1.1 200 OK
content-type: text/event-stream; charset=utf-8

data: {"model_id":"qwen3:4b","sequence":-1,"text":"Error (ConnectError): All connection attempts failed","finish_reason":"error","usage":null,"timestamp_ns":...}
```

---

## 5. Five Concepts You Should Understand

### 1. Asynchronous Generators and Streaming in Python (`AsyncIterator`)
In standard synchronous Python functions, `return` hands back a single value and terminates the function. An **async generator** (`async def` with `yield`) produces a stream of values over time without blocking the execution thread. When you call an async generator, you receive an `AsyncIterator`.
You iterate through it using `async for item in generator:`. While the generator waits for the next token from the LLM or sleeps (`await asyncio.sleep(...)`), the Python event loop is free to handle requests from other users simultaneously.

### 2. Structural Subtyping with `typing.Protocol` (Duck Typing Formalized)
In traditional Object-Oriented Programming (like Java or C++), a class must explicitly inherit from an interface (`class MockProvider implements ModelProvider`).
Python's `typing.Protocol` uses **structural subtyping** (often called static duck typing: "if it walks like a duck and quacks like a duck, it is a duck").
Any class that implements `def stream(self, request: ModelRequest) -> AsyncIterator[ModelDelta]` automatically satisfies `ModelProvider` without needing to inherit from it. This keeps your classes lightweight, loosely coupled, and easy to test.

### 3. Server-Sent Events (SSE) vs WebSockets
When streaming LLM responses to a browser, the communication is strictly **one-way** (server to client): the client asks a question once, and the server pushes partial tokens until complete.
- **WebSockets** provide bidirectional, full-duplex TCP connections. They require special handshake protocols, custom framing, and more complex state handling.
- **Server-Sent Events (SSE)** run over standard HTTP (`media_type="text/event-stream"`). They are simple, native to browser APIs (`EventSource`), work over standard HTTP/2 multiplexing, and automatically handle reconnections. Each message is formatted simply as `data: <content>\n\n`.
The headers `Cache-Control: no-cache` and `X-Accel-Buffering: no` tell intermediate proxies and web servers (like Nginx) not to buffer the bytes, so each token arrives on the user's screen the instant it is generated.

### 4. Network Resilience & Defensive Parsing
Real-world network calls fail in diverse ways: hosts are unreachable, models crash, or JSON responses omit fields.
In `OllamaProvider`, we implement two defensive principles:
- **Differentiated Timeouts**: We configure `httpx.Timeout(connect=5.0, read=120.0, write=10.0, pool=5.0)`. If Ollama is down, we fail within 5 seconds instead of hanging the user for minutes. Conversely, because local LLMs can take seconds to think before producing the first token, the `read` timeout is generous (120s).
- **Defensive Dictionary Access**: We never assume keys exist (e.g. `chunk["message"]["content"]`). We use `.get()` with safe defaults (`chunk.get("message", {}).get("content", "")`) and skip empty tokens so thinking models don't yield blank deltas.

### 5. Type-Safe Configuration with Pydantic v2 `BaseSettings`
Hardcoding configuration values like API URLs and model names directly into application code is an anti-pattern.
`pydantic-settings` provides a type-safe `Settings` class that:
- Reads system environment variables and local `.env` files automatically.
- Validates data types (e.g., converting strings to integers or URLs).
- Provides fallbacks to safe default values (`http://localhost:11434`).
- Ignores extra environment variables via `model_config = SettingsConfigDict(env_file=".env", extra="ignore")`, preventing crashes when other unrelated tools populate environment variables.
