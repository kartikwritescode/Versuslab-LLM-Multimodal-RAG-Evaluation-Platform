# Phase 11: Ollama Stream Diagnostics, Modern UI Redesign & Enhanced Knowledge Base

Welcome to the Phase 11 notes for **VersusLab**! This phase resolved a critical local model streaming issue with Ollama, modernized the user interface into a sleek, high-energy evaluation arena, and completely overhauled the RAG file attachment workflow with an interactive drag-and-drop document hub.

---

## 1. What We Built

### 1. Ollama Streaming Diagnosis & Solution
- **The Mystery**: When running races with local Ollama (`qwen3:8b`), VersusLab failed to stream content and produced `First token timeout exceeded (10.0s)`.
- **The Investigation**:
  - Direct terminal testing against Ollama (`curl http://127.0.0.1:11434/api/chat`) revealed that `qwen3:8b` in Ollama 0.32+ is a thinking/reasoning model by default.
  - During the thinking phase, Ollama outputs deltas where `chunk["message"]["content"]` is `""` (empty) while internal reasoning is placed in `chunk["message"]["thinking"]`.
  - In `apps/api/app/providers/ollama.py`, `stream()` had `if text: yield ModelDelta(...)` on `content` only. Because `content` was empty for over 30–70 seconds, **zero tokens were yielded**.
  - In `coordinator.py`, `asyncio.timeout(10.0)` enforced `settings.first_token_timeout_s`. Because 0 deltas arrived within 10 seconds, the coordinator aborted the stream with `model.timeout`.
- **The Solution**:
  - We passed `"think": False` by default to Ollama's `/api/chat`. This commands `qwen3:8b` to bypass internal monologue and generate direct chat responses immediately. TTFT dropped from **>30,000ms (timeout)** to **~430ms**, with responses completing in **~2–5 seconds**.
  - We updated `OllamaProvider.stream()` to defensively check both `content` and `thinking` (`text = content or thinking`). If reasoning models are ever used with thinking enabled, tokens are never dropped and keep the stream active.
  - Added `ollama_think: bool = False` to `Settings` and increased `first_token_timeout_s` from 10.0s to 15.0s in `.env` and `config.py` to give local models breathing room during cold-start weight loading.

### 2. High-Polish Modern UI Redesign
- **Glassmorphism & Ambient Glow**: Added custom CSS utility classes (`glass-panel`, `glass-panel-interactive`, `bg-ambient-radial`, custom dark scrollbars, and `cursor-blink`) in `apps/web/app/globals.css`.
- **Live Status Header**: Created a sticky header displaying the platform brand, active tabs (Race, Benchmarks, History), and a real-time pulsing green indicator (`● FastAPI Engine Online`).
- **High-Energy Action CTA**: Redesigned the "Run Race" button with a vivid gradient (`from-violet-600 via-indigo-600 to-cyan-500`), hover glow shadow, and keyboard shortcut pill (`Ctrl + ↵`).
- **Contender Selector Chips**: Enhanced model selector chips with distinct provider logos/icons (Ollama 🦙, OpenAI, Claude, Gemini, Grok, DeepSeek, Mock) and colored category badges (`MOCK`, `LOCAL`, `CLOUD`).
- **Quick Preset Prompts**: Added 4 one-click experiment chips (`⚡ Sync vs Async`, `🧠 Hybrid RAG Search`, `🚀 Python Retry Pattern`, `📄 Document Summary`) to test model responses instantly.
- **Redesigned Contender Stream Cards**:
  - Prominent provider icons and model tags.
  - Live metrics bar displaying TTFT (ms), Total Latency (s), Throughput Speed (tokens/sec), and Output Token counts.
  - Automatic `⚡ FASTEST TTFT` winner highlight badge when races complete.
  - Smooth typing cursor animation (`cursor-blink`) during live streaming.

### 3. Enhanced Knowledge Base & File Attachment Section
- **Created `DocumentManager.tsx`**:
  - **Interactive Drag & Drop Zone**: Visual dashed upload dropzone with hover/drag-over animations, supporting `.txt` and `.md` files up to 5MB.
  - **Active Attached Document Card**: Displays the attached document with file icon, filename, chunk count badge (e.g. `2 chunks`), SHA-256 hash preview, and 1-click Detach button.
  - **Document Library Modal**: Allows browsing and searching through previously ingested documents with 1-click attach.
  - **Chunk Preview Drawer**: Allows inspecting the ordered paragraph chunks stored in pgvector to see exactly what RAG context will be injected into LLM prompts.
  - **Backend Support**: Added `GET /api/documents/{document_id}` in `apps/api/app/api/documents.py` to serve ordered chunk snippets.

---

## 2. Why We Built It This Way

- **`think: false` for Competitive LLM Races**: When evaluating models side-by-side on TTFT and response latency against GPT-4o-mini or Claude Haiku, a local model spending 60 seconds generating unconstrained chain-of-thought monologue would always lose on latency benchmarks. Passing `think: false` allows fair, direct chat comparison.
- **Defensive Chunker Fallback**: Even though `think: false` is default, checking `text = content or thinking` ensures that if a user intentionally configures a thinking model, the stream will still flow smoothly without premature timeouts.
- **Dedicated `DocumentManager` Component**: Rather than cluttering `page.tsx` with modal dialogs and file drag events, encapsulating document management in a separate reusable component keeps code modular and maintainable.
- **`getNow()` Helper for React 19 Compiler Purity**: React 19's strict compiler flags `performance.now()` if called directly in component bodies. Defining an external helper `getNow()` satisfies strict React purity rules while preserving sub-millisecond precision.

---

## 3. Files Touched and Created

```text
apps/api/
├── app/
│   ├── api/documents.py                   # Added GET /api/documents/{document_id} endpoint
│   ├── core/config.py                     # Added ollama_think setting; updated timeout to 15.0s
│   ├── providers/ollama.py                # Supported think option and defensive thinking extraction
│   └── providers/registry.py              # Passed think=settings.ollama_think to OllamaProvider
├── .env.example                           # Added OLLAMA_THINK=false, FIRST_TOKEN_TIMEOUT_S=15.0
├── .env                                   # Updated local environment configuration
└── tests/
    ├── test_ollama_provider.py            # Added unit tests for think option and thinking chunks
    └── test_rag.py                        # Added test for GET /api/documents/{id}

apps/web/
├── app/
│   ├── components/
│   │   └── DocumentManager.tsx            # [NEW] Drag & drop, document library, and chunk preview
│   ├── globals.css                        # Glassmorphism, ambient gradients, custom dark scrollbars
│   ├── history/page.tsx                   # Fixed useEffect cascading render for React 19
│   └── page.tsx                           # Modernized arena UI, preset chips, provider icons, metrics
├── lib/
│   ├── race-client.ts                     # Added fetchDocumentDetail client API
│   └── types.ts                           # Added DocumentDetail and DocumentChunkItem types
```

---

## 4. How to Run and Verify It

### 1. Run Automated Unit Tests (Backend)
```powershell
cd c:\files\programming\Python\projects\versus_lab\apps\api
.venv\Scripts\pytest tests/test_ollama_provider.py tests/test_rag.py -v
```
**Expected Output**:
```text
tests/test_ollama_provider.py::test_ollama_provider_happy_path PASSED
tests/test_ollama_provider.py::test_ollama_provider_thinking_chunk_streaming PASSED
tests/test_ollama_provider.py::test_ollama_provider_server_error PASSED
tests/test_ollama_provider.py::test_ollama_provider_model_not_found PASSED
tests/test_ollama_provider.py::test_ollama_embedding_provider_mock_transport PASSED
tests/test_rag.py::test_get_document_detail PASSED
10 passed in 1.43s
```

### 2. Verify Frontend Typecheck and Lint
```powershell
cd c:\files\programming\Python\projects\versus_lab\apps\web
npx tsc --noEmit
npx eslint app/
```
**Expected Output**: Clean exit with 0 errors.

### 3. Verify Live Race with Ollama
With the FastAPI server running (`uvicorn app.main:app --reload`):
```powershell
curl -N -s -X POST http://localhost:8000/api/races -H "Content-Type: application/json" -d '{"prompt": "Say hi in 2 words", "models": ["ollama:qwen3:8b"]}'
```
**Expected Output**:
```text
data: {"type":"race.started","race_id":"...","sequence":0}
data: {"type":"model.started","model_id":"ollama:qwen3:8b","sequence":1}
data: {"type":"model.delta","model_id":"ollama:qwen3:8b","sequence":2,"text":"Hello"}
data: {"type":"model.delta","model_id":"ollama:qwen3:8b","sequence":3,"text":"!"}
data: {"type":"model.completed","model_id":"ollama:qwen3:8b","sequence":4,"finish_reason":"stop"}
data: {"type":"race.completed","sequence":5}
```

### 4. Interactive Browser Verification
1. Open `http://localhost:3000` in your browser.
2. Click the preset prompt chip `⚡ Sync vs Async`.
3. Check the `Ollama (qwen3:8b)` and `Mock (Fast)` chips.
4. Click **Run Race** (or press `Ctrl+Enter`).
5. Observe live text streaming in both columns simultaneously, with sub-second TTFT and live throughput metrics!

---

## 5. Five Concepts a Beginner Should Understand

1. **Reasoning / Thinking Models in Ollama**:
   Models like DeepSeek-R1, Qwen 2.5/3 with thinking, and OpenAI o1 output two different streams of text: internal reasoning (`thinking`) and the final answer (`content`). If an API consumer only listens for `content`, it will appear silent while the model thinks. Providing `"think": false` disables the reasoning phase for fast, low-latency chat.

2. **Time to First Token (TTFT)**:
   TTFT measures the time elapsed from when an HTTP request is dispatched until the very first token byte is received by the client. It measures prompt processing speed and server latency. For local models on GPUs, cold-start model weight loading can add several seconds to TTFT on the first run.

3. **Multiplexed Server-Sent Events (SSE)**:
   Rather than opening 5 separate HTTP connections to stream 5 different models, VersusLab uses **one** single SSE connection. Events from all contenders are interleaved and tagged with `model_id` and a monotonically increasing `sequence` number, dramatically reducing network socket overhead.

4. **Glassmorphism in Web Design**:
   A modern UI aesthetic achieved using translucent backgrounds (`rgba(24, 24, 27, 0.65)`), background blur filters (`backdrop-filter: blur(16px)`), and subtle glowing borders (`rgba(255, 255, 255, 0.08)`). It creates depth and visual hierarchy without heavy opaque panels.

5. **Drag-and-Drop File API (HTML5)**:
   The browser provides `onDragOver`, `onDragLeave`, and `onDrop` events. Calling `e.preventDefault()` on `onDragOver` tells the browser that the element is a valid drop target. The dropped files are accessed via `e.dataTransfer.files` and can be sent to a backend using standard `FormData` and `multipart/form-data`.
