# Phase 2: Concurrent Race Engine & Multiplexed SSE

Welcome to the Phase 2 notes for **VersusLab**! This document explains how the concurrent multi-model race engine works, why it was designed this way, which files were touched, how to run and verify all scenarios with PowerShell and curl, and 5 foundational distributed/concurrent systems concepts explained for a beginner.

---

## 1. What We Built

In Phase 2, we replaced the temporary single-model test endpoint with the core **VersusLab Concurrent Race Engine**:
1. **Multi-Model Event Protocol (`RaceEvent` & `EventType`)**: A unified schema in `app/race/events.py` supporting all 9 lifecycle events:
   - `race.started`, `model.started`, `model.delta`, `model.completed`, `model.error`, `model.timeout`, `model.cancelled`, `race.completed`, `race.cancelled`.
2. **Concurrent Race Coordinator (`app/race/coordinator.py`)**:
   - Spawns independent `asyncio.Task` workers for each contender model.
   - Centralizes event collection using a shared `asyncio.Queue` and stamps strictly monotonic sequence numbers (`0, 1, 2, ...`) in one single place (`run_race`).
   - Guarantees task lifecycle tracking using `task.add_done_callback` to inject `None` sentinels into the queue regardless of whether a task completes normally, errors out, or is cancelled.
3. **Dynamic Per-Model Timeout Scheduling**:
   - Every worker begins with a strict `first_token_timeout_s` deadline (configured in Settings).
   - Upon receiving its first text token, the worker dynamically reschedules its deadline to `model_timeout_s` using `timeout_ctx.reschedule(...)`.
   - Catching `TimeoutError` cleanly emits a `model.timeout` event without crashing other models.
4. **Failure Isolation ("Errors are Data")**:
   - If one model crashes (e.g. `mock-broken` or a network disconnection with Ollama), it emits `model.error` and cleanly completes. Other contenders continue streaming unaffected.
5. **In-Memory Cancellation Registry (`ActiveRace` & `cancel_race`)**:
   - Active races are tracked in a thread-safe in-memory registry: `RACES: dict[str, ActiveRace]`.
   - Calling `POST /api/races/{race_id}/cancel` flags the race as cancelled, cancels all associated worker tasks, causes workers to emit `model.cancelled`, and concludes the stream with `race.cancelled`.
   - Once a race finishes (normally or cancelled), its entry is cleaned up in a `finally` block so subsequent cancel calls immediately return HTTP 404.
6. **Fairness Guarantee**:
   - One `ModelRequest` template is created per race; contenders only differ by `model_copy(update={"model": target.model})`.
7. **Production API Endpoints**:
   - `POST /api/races`: Accepts a validated JSON body (`prompt`, `models` list between 1 and 8 items, `temperature`, `max_tokens`, optional `race_id`), pre-validates providers and duplicate model IDs before streaming starts, and returns an SSE `StreamingResponse` (`data: <json>\n\n`).
   - `POST /api/races/{race_id}/cancel`: Cancels an active race or returns 404 if not found.
   - Deletion of the temporary Phase 1 `/api/stream` endpoint.

---

## 2. Why We Built It This Way

- **Why One Multiplexed SSE Connection Instead of Multiple Connections?**
  Opening 8 or 24 separate HTTP connections from the browser to the backend for every prompt wastes network sockets, increases TLS handshake overhead, and makes client-side synchronization difficult. With ONE multiplexed stream, the frontend receives a single chronological event stream tagged with `model_id`, making state management simple, efficient, and reproducible.
- **Why Central Sequence Stamping?**
  If each worker stamped its own sequence number, sequence numbers would conflict or arrive out of order across contenders. By having workers emit to an `asyncio.Queue` and having `run_race` stamp the sequence number right before yielding the event, we guarantee a single, strictly monotonic timeline: `0, 1, 2, ... N`.
- **Why Dynamic Timeouts with `asyncio.timeout.reschedule`?**
  A fixed global timeout is flawed: if an LLM is hung and fails to respond, you want to fail fast (e.g. 10s `first_token_timeout_s`). But once a model starts generating tokens, complex prompts may take 60+ seconds to finish streaming. Rescheduling the timeout upon the first token provides fast failure detection without cutting off long generations.
- **Why Sentinels via `task.add_done_callback`?**
  In asynchronous concurrent code, relying on `finally` blocks inside worker coroutines can fail if tasks are cancelled abruptly before entering the block. Attaching `task.add_done_callback(lambda _t: queue.put_nowait(None))` guarantees that Python's event loop will push the completion sentinel when the task transitions to the finished state, preventing queue deadlocks.

---

## 3. Files Touched and Created

```text
versus_lab/
├── docs/
│   └── phase-notes/
│       ├── phase-1.md
│       └── phase-2.md                  # This documentation file
└── apps/
    └── api/
        ├── .env.example                # Documented FIRST_TOKEN_TIMEOUT_S and MODEL_TIMEOUT_S
        ├── app/
        │   ├── main.py                 # Mounted race_router, removed stream_router
        │   ├── core/
        │   │   └── config.py           # Added first_token_timeout_s and model_timeout_s
        │   ├── providers/
        │   │   └── registry.py         # Added mock-stuck, mock-broken, and mock-slow personalities
        │   ├── api/
        │   │   ├── race.py             # POST /api/races and POST /api/races/{race_id}/cancel
        │   │   └── stream.py           # (DELETED Phase 1 temporary endpoint)
        │   └── race/
        │       ├── events.py           # Updated EventType with all 9 events & RaceEvent model
        │       └── coordinator.py      # Concurrency, timeout rescheduling, cancellation & sentinels
        └── tests/
            ├── test_stream_endpoint.py # (DELETED Phase 1 test)
            └── test_race.py            # Comprehensive tests for validation, race, errors & cancellation
```

---

## 4. How to Run and Verify

All commands should be executed from PowerShell.

### Step A: Run Automated Tests and Linter
In `apps/api`:
```powershell
cd apps/api
pytest
ruff check .
```
**Expected Output:**
```text
============================== 9 passed in 2.xx s ==============================
All checks passed!
```

### Step B: Start the Server
```powershell
uvicorn app.main:app --reload --port 8000
```

### Step C: Manual Test 1 — Mixed Contender Race (Interleaved Deltas, Error, Timeout, Completion)

In a second PowerShell window, run a race with:
- `mock:fast` (normal fast mock)
- `mock-broken` (emits 3 tokens and crashes with `RuntimeError`)
- `mock-stuck` (hangs on first token, timing out after 10s)
- `ollama:qwen3:4b` (local Ollama contender; fails fast if Ollama daemon is stopped)

```powershell
$body = '{"prompt":"Compare these models","models":["mock:fast","mock-broken","mock-stuck","ollama:qwen3:4b"]}';
curl.exe -N -X POST http://localhost:8000/api/races -H "Content-Type: application/json" -d $body
```

**Expected Event Stream:**
```http
data: {"type":"race.started","race_id":"...","sequence":0,"timestamp_ns":...}

data: {"type":"model.started","race_id":"...","sequence":1,"timestamp_ns":...,"model_id":"mock:fast"}
data: {"type":"model.started","race_id":"...","sequence":2,"timestamp_ns":...,"model_id":"mock-broken:mock-broken-1"}
data: {"type":"model.started","race_id":"...","sequence":3,"timestamp_ns":...,"model_id":"mock-stuck:mock-stuck-1"}
data: {"type":"model.started","race_id":"...","sequence":4,"timestamp_ns":...,"model_id":"ollama:qwen3:4b"}

data: {"type":"model.delta","race_id":"...","sequence":5,"timestamp_ns":...,"model_id":"mock:fast","text":"This "}
data: {"type":"model.delta","race_id":"...","sequence":6,"timestamp_ns":...,"model_id":"mock-broken:mock-broken-1","text":"This "}
data: {"type":"model.delta","race_id":"...","sequence":7,"timestamp_ns":...,"model_id":"mock:fast","text":"is "}
data: {"type":"model.delta","race_id":"...","sequence":8,"timestamp_ns":...,"model_id":"mock-broken:mock-broken-1","text":"is "}
data: {"type":"model.delta","race_id":"...","sequence":9,"timestamp_ns":...,"model_id":"mock-broken:mock-broken-1","text":"a "}

data: {"type":"model.error","race_id":"...","sequence":10,"timestamp_ns":...,"model_id":"mock-broken:mock-broken-1","error":"RuntimeError: mock provider failure"}

data: {"type":"model.delta","race_id":"...","sequence":11,"timestamp_ns":...,"model_id":"mock:fast","text":"a "}
...
data: {"type":"model.completed","race_id":"...","sequence":18,"timestamp_ns":...,"model_id":"mock:fast","finish_reason":"stop","usage":{"input_tokens":3,"output_tokens":9}}

data: {"type":"model.error","race_id":"...","sequence":19,"timestamp_ns":...,"model_id":"ollama:qwen3:4b","error":"ConnectError: All connection attempts failed"}

data: {"type":"model.timeout","race_id":"...","sequence":20,"timestamp_ns":...,"model_id":"mock-stuck:mock-stuck-1","error":"First token timeout exceeded (10.0s)"}

data: {"type":"race.completed","race_id":"...","sequence":21,"timestamp_ns":...}
```

### Step D: Manual Test 2 — Mid-Stream Cancellation & 404 Check

In PowerShell, start a slow race and cancel it mid-generation:

```powershell
# 1. Start a slow race with a known ID in the background
$body = '{"race_id":"cancel-demo-race","prompt":"Stream slowly please","models":["mock-slow:m1","mock-slow:m2"]}';
$job = Start-Job -ScriptBlock {
    param($b)
    curl.exe -N -X POST http://localhost:8000/api/races -H "Content-Type: application/json" -d $b
} -ArgumentList $body;

# 2. Wait 0.5s so streaming starts, then call cancel
Start-Sleep -Milliseconds 500;
curl.exe -i -X POST http://localhost:8000/api/races/cancel-demo-race/cancel;

# 3. View the stream output to verify model.cancelled and race.cancelled
Receive-Job -Job $job -Wait;

# 4. Attempt to cancel again (must return 404)
curl.exe -i -X POST http://localhost:8000/api/races/cancel-demo-race/cancel;
```

**Expected Output:**
- First cancel request:
  ```http
  HTTP/1.1 200 OK
  {"status":"cancelled","race_id":"cancel-demo-race"}
  ```
- Stream receives:
  ```text
  data: {"type":"race.started", ...}
  data: {"type":"model.started", ...}
  data: {"type":"model.cancelled","race_id":"cancel-demo-race", ...,"model_id":"mock-slow:m1"}
  data: {"type":"model.cancelled","race_id":"cancel-demo-race", ...,"model_id":"mock-slow:m2"}
  data: {"type":"race.cancelled","race_id":"cancel-demo-race", ...}
  ```
- Second cancel request:
  ```http
  HTTP/1.1 404 Not Found
  {"detail":"Race not found"}
  ```

---

## 5. Five Concepts You Should Understand

### 1. Concurrency vs Parallelism in Python Asyncio
- **Parallelism** means multiple computations executing literally at the exact same physical instant on multiple CPU cores (multiprocessing).
- **Concurrency** means managing multiple computations at the same time on one thread by interleaving them whenever an operation waits for I/O (like network responses from an LLM API or timers).
In VersusLab, `asyncio.create_task` allows 8 or 24 models to stream simultaneously without needing 24 operating system threads. When model A is waiting for its next token from the network, Python immediately yields CPU time to read the token arriving from model B.

### 2. The Sentinel Pattern
When multiple concurrent tasks push items into a shared queue, how does the receiver know when all tasks are done without busy polling?
A **sentinel** is a special marker value (often `None`) pushed to the queue to signal completion.
By registering a `task.add_done_callback(lambda _t: queue.put_nowait(None))` on each worker task, each finished task pushes one `None` sentinel into the queue. The receiver counts down `remaining = len(tasks)`. When `remaining` reaches 0, the receiver knows with absolute certainty that every single task has terminated.

### 3. Dynamic Timeout Scheduling (`asyncio.timeout` and `.reschedule()`)
In Python 3.11+, `asyncio.timeout(delay)` provides an asynchronous context manager for deadline management.
Standard timeouts are static: if you set a 60-second timeout, a hung server that won't ever answer keeps your connection tied up for 60 seconds.
By using `.reschedule(new_deadline)`, we combine:
- A short **time-to-first-token (TTFT)** deadline (`first_token_timeout_s = 10s`).
- A longer **completion** deadline (`model_timeout_s = 60s`), activated the instant the first token arrives.
This gives the user instant feedback on hung servers while still allowing legitimate, lengthy model outputs.

### 4. Cooperative Cancellation and `asyncio.CancelledError`
Asyncio tasks cannot be forcibly killed like operating system processes; cancellation is **cooperative**.
When `task.cancel()` is called:
1. Python raises an `asyncio.CancelledError` inside the coroutine at the current `await` point.
2. The coroutine catches the exception, performs cleanup (e.g. emitting `model.cancelled`), and **MUST re-raise** `asyncio.CancelledError`.
3. If you accidentally swallow `CancelledError` (`except Exception:` catching it or missing `raise`), Python cannot clean up the task, causing resource leaks ("orphaned tasks").

### 5. Multiplexing & Demultiplexing over Server-Sent Events
- **Multiplexing** is the process of combining multiple independent data streams into a single physical stream. In VersusLab, tokens from 4 different LLMs are packaged as `RaceEvent` objects with a `model_id` tag and sent down one single HTTP SSE pipe.
- **Demultiplexing (Demux)** happens on the frontend: the browser's JavaScript listens to the single SSE event stream, reads `event.model_id`, and routes `event.text` to that specific model's UI column.
This provides the illusion of multiple independent live connections with the performance and simplicity of a single connection.
