# Phase 3: Cloud LLM Providers, Concurrency Limits & Safe Retries

Welcome to the Phase 3 notes for **VersusLab**! This document explains how we integrated four major cloud LLM providers (OpenAI, Anthropic Claude, Google Gemini, and xAI Grok) behind the same unified provider protocol, how global concurrency limits and safe connection retries protect our infrastructure, which files were touched, how to test each provider and a full 6-way race, and 5 key systems concepts written for a beginner.

---

## 1. What We Built

In Phase 3, we extended VersusLab's backend with four production cloud LLM adapters and enhanced coordinator resilience:
1. **OpenAI Provider (`OpenAIProvider`)**:
   - Connects to `https://api.openai.com/v1/chat/completions` using streaming SSE (`stream: true`).
   - Uses `stream_options: {"include_usage": true}` to receive exact token usage figures (`prompt_tokens` and `completion_tokens`) in the final stream chunk before `[DONE]`.
   - Default model: `gpt-4o-mini` (OpenAI's fastest and most cost-efficient general-purpose chat model).
2. **Anthropic Claude Provider (`AnthropicProvider`)**:
   - Connects to `https://api.anthropic.com/v1/messages` with `anthropic-version: 2023-06-01`.
   - Formats requests cleanly: extracts system instructions to top-level `system`, alternates user/assistant messages, and provides `max_tokens` (default 4096).
   - Maps Anthropic's event lifecycle: captures `input_tokens` from `message_start`, streams incremental text from `content_block_delta`, and extracts `output_tokens` and `stop_reason` from `message_delta` upon `message_stop`.
   - Default model: `claude-3-5-haiku-20241022` (near-frontier intelligence with high speed and low cost).
3. **Google Gemini Provider (`GeminiProvider`)**:
   - Connects to Google's REST API: `https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?alt=sse`.
   - Passes authentication via the `x-goog-api-key` header.
   - Formats input messages into Gemini's `contents` structure with `systemInstruction`.
   - Parses SSE chunks, streams text parts, and normalizes `usageMetadata` (`promptTokenCount`, `candidatesTokenCount`) into `ModelDelta`.
   - Default model: `gemini-2.5-flash` (Google's flagship price-performance model for low latency).
4. **xAI Grok Provider (`GrokProvider`)**:
   - **Architectural Reuse**: Confirmed from xAI's official developer documentation that the xAI API at `https://api.x.ai/v1` is fully compatible with OpenAI's Chat Completions REST API.
   - Reuses `OpenAIProvider` pointed to `https://api.x.ai/v1` with `XAI_API_KEY`.
   - Default model: `grok-2-1212` (xAI's production chat and reasoning model).
5. **Secure Configuration & Lazy Validation**:
   - API keys and base URLs are loaded into `Settings` in `app/core/config.py` from `.env`.
   - All API keys are optional strings (`str | None = None`).
   - If an API key is not configured, the application starts up normally with no crash. Only when a race specifically requests an unconfigured provider does it raise a clear `RuntimeError` (`Provider 'X' requires an API key...`), which the race coordinator cleanly isolates into a `model.error` event without breaking other contenders.
6. **Coordinator Concurrency Limiting (`asyncio.Semaphore`)**:
   - A global `asyncio.Semaphore` (configured by `MAX_CONCURRENT_MODEL_CALLS=8`) limits outbound HTTP requests across all running races, preventing socket exhaustion and rate-limit bans when 5+ models race simultaneously.
7. **Safe, Idempotent Connection Retries**:
   - If a transient network connection error occurs (`httpx.ConnectError`, `httpx.ConnectTimeout`) **before any tokens have been streamed**, the coordinator retries up to 2 times with exponential backoff (`0.5s`, `1.0s`).
   - **Crucial Rule**: If any token has already been emitted to the client, the coordinator **never** retries (non-idempotent operation), immediately reporting `model.error` instead of corrupting the client's output stream with repeated tokens.

---

## 2. Why We Built It This Way

- **Zero Coupling Across Providers**: Every provider speaks its own distinct dialect over the wire (OpenAI uses `choices[0].delta.content`, Anthropic uses `content_block_delta`, Gemini uses `candidates[0].content.parts[0].text`). The rest of VersusLab never sees these differences; each adapter translates its native protocol into our clean `ModelDelta`.
- **Why Check Idempotency Before Retrying?**
  In HTTP APIs, retrying an operation that has already produced side effects (or already sent data to an SSE consumer) is a major bug. If model A emits 10 words, then suffers a mid-stream connection drop, restarting the generation would cause the user to see words 1–10 repeated all over again. By checking `not first_token_received`, we only retry operations where no content was ever exposed.
- **Why Global Semaphores Instead of Per-Race Limits?**
  If three users submit races with 8 contenders each at the same moment, 24 simultaneous outbound TLS handshakes would fire at once, potentially exhausting file descriptors or triggering cloud API rate limits (HTTP 429). A global semaphore enforces a hard ceiling across the entire FastAPI process.
- **No Hardcoded Pricing or Limits**: Model prices per 1M tokens and maximum context windows change frequently. Keeping them out of python code prevents brittle refactors later; they will be managed in dedicated configuration files in subsequent phases.

---

## 3. Files Touched and Created

```text
versus_lab/
├── docs/
│   └── phase-notes/
│       ├── phase-1.md
│       ├── phase-2.md
│       └── phase-3.md                  # This documentation file
└── apps/
    └── api/
        ├── .env.example                # Documented API keys, base URLs, concurrency & retries
        ├── app/
        │   ├── core/
        │   │   └── config.py           # Added keys, base URLs, concurrency & retry settings
        │   ├── race/
        │   │   └── coordinator.py      # Added global semaphore and idempotent connection retries
        │   └── providers/
        │       ├── registry.py         # Registered openai, anthropic, gemini, and grok
        │       ├── openai.py           # OpenAI Chat Completions streaming adapter
        │       ├── anthropic.py        # Anthropic Messages streaming adapter
        │       ├── gemini.py           # Google Gemini streamGenerateContent adapter
        │       └── grok.py             # xAI Grok adapter (OpenAI-compatible wrapper)
        └── tests/
            ├── test_cloud_providers.py # Unit tests for all 4 cloud providers with mock transports
            └── test_race.py            # Added concurrency & retry tests
```

---

## 4. How to Run and Verify

All commands should be executed from PowerShell.

### Step A: Run Automated Tests & Linter
In `apps/api`:
```powershell
cd apps/api
.\.venv\Scripts\Activate.ps1
pytest
ruff check .
```
**Expected Output:**
```text
============================= 16 passed in 4.xx s =============================
All checks passed!
```

### Step B: Start the Server
```powershell
uvicorn app.main:app --reload --port 8000
```

### Step C: Test 1 — Unconfigured Providers (Clear Error Verification)
Without setting any keys in `apps/api/.env`, test each cloud provider individually using curl:

```powershell
# 1. Test OpenAI without key
curl.exe -N -s -X POST http://localhost:8000/api/races -H "Content-Type: application/json" -d '{"prompt":"hi","models":["openai"]}'

# 2. Test Anthropic without key
curl.exe -N -s -X POST http://localhost:8000/api/races -H "Content-Type: application/json" -d '{"prompt":"hi","models":["anthropic"]}'

# 3. Test Gemini without key
curl.exe -N -s -X POST http://localhost:8000/api/races -H "Content-Type: application/json" -d '{"prompt":"hi","models":["gemini"]}'

# 4. Test Grok without key
curl.exe -N -s -X POST http://localhost:8000/api/races -H "Content-Type: application/json" -d '{"prompt":"hi","models":["grok"]}'
```

**Expected Output for Each:**
A clean stream that emits `race.started`, `model.started`, and then a descriptive `model.error` telling you exactly which environment variable is missing, followed by `race.completed`:
```http
data: {"type":"race.started","race_id":"...","sequence":0,...}
data: {"type":"model.started","race_id":"...","sequence":1,...,"model_id":"openai:gpt-4o-mini"}
data: {"type":"model.error","race_id":"...","sequence":2,...,"model_id":"openai:gpt-4o-mini","error":"RuntimeError: Provider 'openai' requires an API key. Please configure OPENAI_API_KEY in apps/api/.env."}
data: {"type":"race.completed","race_id":"...","sequence":3,...}
```

### Step D: Test 2 — Configured Providers (Live Stream)
When you add your actual API keys to `apps/api/.env`:
```bash
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=AIza...
XAI_API_KEY=xai-...
```
Run any configured model:
```powershell
curl.exe -N -X POST http://localhost:8000/api/races -H "Content-Type: application/json" -d '{"prompt":"Explain gravity in 5 words","models":["openai:gpt-4o-mini"]}'
```
You will receive real streamed tokens followed by `model.completed` carrying exact input and output token counts from the provider.

### Step E: Test 3 — Full 6-Provider Race
Test all 6 providers racing concurrently over ONE multiplexed SSE stream:
```powershell
$body = '{"prompt":"Explain gravity in 5 words","models":["mock:fast","ollama","openai","anthropic","gemini","grok"]}';
curl.exe -N -s -X POST http://localhost:8000/api/races -H "Content-Type: application/json" -d $body
```

**Expected Behavior:**
- Single `race.started` event with `sequence: 0`.
- 6 `model.started` events.
- Interleaved tokens from `mock:fast` and any configured cloud models.
- Clean `model.error` events for unconfigured providers and stopped Ollama instances without crashing the race.
- Global semaphore limits outbound requests to 8 simultaneous connections.
- Final `race.completed` with strictly monotonic sequence numbers.

---

## 5. Five Concepts You Should Understand

### 1. API Normalization via the Adapter Pattern
Every AI company invents its own JSON structure:
- OpenAI wraps deltas in `{"choices": [{"delta": {"content": "..."}}]}`.
- Anthropic wraps deltas in `{"type": "content_block_delta", "delta": {"text": "..."}}`.
- Google wraps deltas in `{"candidates": [{"content": {"parts": [{"text": "..."}]}}]}`.
The **Adapter Pattern** wraps each incompatible external interface with a class (`OpenAIProvider`, `AnthropicProvider`, `GeminiProvider`) that conforms to a single uniform interface (`ModelProvider.stream -> ModelDelta`). This ensures your core system remains pristine and unaffected by third-party API changes.

### 2. Stream Usage Reporting (The `stream_options` Pattern)
In synchronous non-streaming APIs, token usage is returned in the response footer. But in SSE streaming, how does the caller know how many tokens were processed?
- OpenAI sends a dedicated usage-only chunk at the very end when `stream_options: {"include_usage": true}` is set.
- Anthropic sends cumulative input/output token updates across `message_start` and `message_delta` events.
- Gemini sends a `usageMetadata` object in its candidate chunks.
Our adapters intercept these provider-specific usage events and convert them into our standard `Usage(input_tokens, output_tokens)` object on the final `ModelDelta`.

### 3. Asynchronous Semaphores for Concurrency Control
An **`asyncio.Semaphore`** maintains an internal counter. Every time a coroutine enters `async with semaphore:`, the counter decrements. If the counter hits zero, any subsequent coroutine attempting to enter is paused (without blocking the event loop) until an active coroutine finishes and releases its permit.
This acts as a pressure valve: even if a user asks for 24 models in a race, only 8 concurrent network calls fire at any given millisecond.

### 4. Idempotent vs Non-Idempotent Operations in Retries
An operation is **idempotent** if running it multiple times produces the exact same outcome as running it once.
- *Before* any token is streamed, a connection failure (`httpx.ConnectError`) is completely safe to retry: no data has escaped to the user.
- *After* tokens have started streaming, the operation is **no longer idempotent**: the client has already rendered partial words on the screen. Retrying from scratch would duplicate or scramble the output. Hence, we only retry when `not first_token_received`.

### 5. OpenAI API Compatibility as an Industry Standard
Because OpenAI was the first widely adopted LLM API, many newer AI providers (such as xAI Grok, Together AI, Anyscale, Groq, and DeepSeek) design their HTTP endpoints to be byte-for-byte compatible with OpenAI's Chat Completions schema (`/v1/chat/completions`).
Understanding this pattern allows you to write one robust, well-tested adapter (`OpenAIProvider`) and reuse it across multiple providers simply by changing the `base_url` and API key.
