# Phase 4: Next.js Live Streaming Race Arena, RAF Batching & Two-Sided Cancellation

Welcome to the Phase 4 notes for **VersusLab**! This document explains how we built the first web frontend for VersusLab: a Next.js (App Router) application with TypeScript and Tailwind CSS that orchestrates live multi-LLM races over a single multiplexed SSE connection, renders contenders side-by-side with live latency metrics, batches token rendering with `requestAnimationFrame`, and implements two-sided race cancellation.

---

## 1. What We Built

In Phase 4, we created the `apps/web` project and connected it to our FastAPI backend:

1. **Next.js Project Architecture (`apps/web`)**:
   - Initialized with Next.js App Router, TypeScript, and Tailwind CSS.
   - Clean dark-mode UI with responsive grid columns that dynamically adapt to the number of active contenders (1, 2, 3, or 4+ columns on wide screens, stacking on mobile).
   - Configured proxy rewrite in `apps/web/next.config.ts` (`/api/backend/:path*` -> `http://localhost:8000/api/:path*`) alongside direct backend connectivity via `NEXT_PUBLIC_API_BASE_URL` with `.env.local.example`.
   - Enabled `CORSMiddleware` in `apps/api/app/main.py` allowing requests from `http://localhost:3000`.

2. **Strict Protocol Contract (`apps/web/lib/types.ts`)**:
   - Mirrored the backend's `RaceEvent` and `EventType` union types exactly:
     - `race.started`, `model.started`, `model.delta`, `model.completed`, `model.error`, `model.timeout`, `model.cancelled`, `race.completed`, `race.cancelled`.
   - Added explicit contract comments in both `apps/web/lib/types.ts` and `apps/api/app/race/events.py` requiring both files to stay synchronized.

3. **Fetch-Based SSE Stream Reader (`apps/web/lib/race-client.ts`)**:
   - Built `startRaceStream()` using `fetch()` and `response.body.getReader()`.
   - Solved chunk fragmentation by maintaining an invariant persistent buffer across network reads, splitting on SSE double newlines (`\n\n`), and decoding UTF-8 bytes with `TextDecoder({ stream: true })`.
   - Built `cancelRace(raceId)` to invoke `POST /api/races/{race_id}/cancel`.

4. **Performance: `requestAnimationFrame` (RAF) Token Batching**:
   - When 4+ models stream at 20+ tokens/sec, over 80–160+ events arrive every second. Calling React state setters on every token causes browser stutter and dropped frames.
   - Built a delta accumulator ref (`pendingDeltasRef`) that collects tokens and flushes them to React state once per animation frame (~60–120Hz), delivering buttery smooth rendering.

5. **Interactive UI & Real-Time Metrics (`apps/web/app/page.tsx`)**:
   - **Prompt input** with keyboard shortcut (`Ctrl+Enter` or `Cmd+Enter`).
   - **Contender chips** categorized by type (Mock, Local, Cloud) with multi-select toggle and max-8 validation.
   - **Per-model status badges**: `Queued`, `Streaming` (with pulsing radar indicator), `Done`, `Error`, `Timeout`, and `Cancelled`.
   - **Live Metrics**:
     - **TTFT (Time To First Token)**: Accurately calculated the instant the first non-empty text delta arrives for that model.
     - **Elapsed Timer**: Live-updating timer ticking every 50ms while streaming, which freezes permanently the moment a contender completes, errors out, or cancels.
     - **Token counts & finish reason**: Displayed upon completion.
   - **Isolated Error Rendering**: If one contender fails (e.g. `Mock (Broken)` throws an exception), that column displays a dedicated error banner while other columns continue racing unaffected (Architectural Rule 3: *Errors are data*).
   - **Two-Sided Cancellation**: Clicking "Stop Race" instantly aborts the browser's fetch stream via `AbortController` **and** posts to `POST /api/races/{race_id}/cancel` so the backend coordinator cancels running server tasks.

---

## 2. Why We Built It This Way

### Why not use browser `EventSource`?
The standard browser `EventSource` API is designed only for HTTP `GET` requests. It cannot send an HTTP `POST` body with JSON payloads. Because a race request requires sending a prompt, a list of selected models, temperature, and max tokens, using `EventSource` would require putting everything in query parameters (subject to URL length limits and awkward encoding). Using `fetch()` with `response.body.getReader()` gives full `POST` capability with complete control over streaming and cancellation.

### How SSE Chunk Fragmentation is Handled
Network packets (TCP segments) do not align with application messages. A single read from `response.body.getReader()` may yield:
1. Half of a JSON event.
2. Multiple complete events combined in one chunk.
3. The first half of `\n\n` in one chunk and the second `\n` in the next chunk.

**Our Invariant Parser Algorithm**:
```text
Network Chunk -> TextDecoder({ stream: true }) -> Append to buffer
While buffer contains "\n\n":
  1. Extract substring from index 0 to boundary
  2. Slice buffer: buffer = buffer.slice(boundary + 2)
  3. Parse lines starting with "data: " as JSON
  4. Dispatch RaceEvent to callback
```
Any trailing fragment remains in the buffer until the next read delivers the remainder. This mathematically guarantees events are never split or corrupted.

### Why `requestAnimationFrame` (RAF) Batching is Essential
In React, each `setState` triggers component reconciliation. If 4 models each emit tokens every 50ms, the component receives 80 state updates per second. Most displays only refresh 60 times a second (16.6ms per frame). Updating state 80+ times per second causes React to compute unnecessary intermediate renders.
With RAF batching, incoming tokens are stored in a mutable ref (`pendingDeltasRef[modelId] += token`). The browser schedules exactly one state flush before the next screen repaint, merging all pending tokens into a single state update.

### Why Two-Sided Cancellation Matters
If the user clicks "Stop Race" or navigates away, merely calling `abortController.abort()` disconnects the client. However, on the backend, the FastAPI async tasks would continue calling LLM APIs in the background until completion, wasting tokens and GPU resources.
By sending `POST /api/races/{race_id}/cancel` with the `race_id` received from the initial `race.started` event, the backend coordinator cancels its `asyncio.Task` instances immediately.

---

## 3. Files Touched and Created

```text
versus_lab/
├── apps/
│   ├── api/
│   │   └── app/
│   │       ├── main.py                 # Added CORSMiddleware for localhost:3000
│   │       └── race/
│   │           └── events.py           # Added protocol contract comment
│   └── web/
│       ├── .env.local.example          # Template for NEXT_PUBLIC_API_BASE_URL
│       ├── next.config.ts              # Next.js proxy rewrite for /api/backend/:path*
│       ├── package.json                # Next.js, React, Tailwind dependencies
│       ├── lib/
│       │   ├── types.ts                # TypeScript types mirroring backend RaceEvent
│       │   └── race-client.ts          # Fetch SSE stream parser & cancel client
│       └── app/
│           ├── layout.tsx              # Root layout with dark background & metadata
│           ├── page.tsx                # Main race UI, RAF batching, live timer & grid
│           └── globals.css             # Tailwind CSS imports
├── docs/
│   └── phase-notes/
│       ├── phase-1.md
│       ├── phase-2.md
│       ├── phase-3.md
│       └── phase-4.md                  # This documentation file
```

---

## 4. How to Run and Verify

### Prerequisites
Make sure PowerShell is open and you are in the project root:
```powershell
cd c:\files\programming\Python\projects\versus_lab
```

### Step 1: Start the Backend API Server
In terminal 1:
```powershell
cd apps\api
.\.venv\Scripts\uvicorn app.main:app --port 8000 --reload
```
You should see:
```text
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Application startup complete.
```

### Step 2: Start the Next.js Frontend Dev Server
In terminal 2:
```powershell
cd apps\web
npm run dev -- --port 3000
```
You should see:
```text
▲ Next.js 16.3.5 (Turbopack)
- Local: http://localhost:3000
✓ Ready in ~1s
```

### Step 3: Run the Verification Script

1. **Open the browser**: Navigate to `http://localhost:3000`.
2. **Inspect Initial State**:
   - The prompt textarea contains the default prompt.
   - Three default models are highlighted: `Mock (Fast)`, `Mock (Slow)`, `Mock (Broken)`.
   - The main area displays the empty state placeholder.
3. **Execute a Mixed Race**:
   - Click the purple **Run Race** button (or press `Ctrl+Enter`).
   - Observe the 3 side-by-side columns:
     - `Mock (Fast)` starts immediately, displays TTFT (<50ms), streams answer text, and switches to green `✓ Done`.
     - `Mock (Slow)` waits ~1s before first token (TTFT ~1000ms), streams at 4 tokens/s with an active pulsing cursor, and its elapsed timer updates live.
     - `Mock (Broken)` emits 3 tokens, encounters an error, and displays a red `✕ Error` pill with an isolated error banner (`RuntimeError: mock provider failure`). Notice that `Mock (Fast)` and `Mock (Slow)` continue running without interruption!
4. **Test Mid-Race Cancellation**:
   - In the model chips, click **Mock (Stuck)** to add it (or select `Mock (Stuck)` and `Mock (Slow)`).
   - Click **Run Race**.
   - After 1 to 2 seconds while the timer is ticking, click the red **Stop Race** button in the header.
   - Confirm that:
     - The stream stops immediately.
     - Both columns display `⊘ Cancelled` with message *"Cancelled by user"*.
     - The elapsed timer freezes at the moment of cancellation.
     - The backend terminal displays `POST /api/races/{race_id}/cancel 200 OK`.

---

## 5. Five Concepts a Beginner Should Understand

### 1. ReadableStream & Chunk Fragmentation
When data travels over the internet, it is broken into TCP packets. The operating system and browser deliver these pieces whenever they arrive. A chunk returned by `reader.read()` does **not** equal a single line or a complete JSON object; it is simply a slice of raw bytes. If you try to run `JSON.parse()` on incoming chunks directly, your code will crash on the first chunk that happens to cut off in the middle of a word or quotation mark. Maintaining a persistent string buffer and only slicing out data when the complete delimiter (`\n\n`) appears guarantees your JSON parser only receives complete messages.

### 2. `requestAnimationFrame` (RAF) and Decoupling
Computer screens typically refresh at 60Hz (once every 16.6 milliseconds) or 120Hz (every 8.3ms). If a fast LLM or network stream fires 200 events per second, trying to repaint the browser for every single event creates a bottleneck known as "render thrashing." `requestAnimationFrame` is a browser API that tells you: *"I am about to draw the next frame on the screen; give me your latest changes now."* By buffering incoming text in a JavaScript variable and applying it during the RAF callback, the browser repaints smoothly at its natural refresh rate with zero dropped frames.

### 3. AbortController & Two-Sided Cancellation
When you close a tab or cancel an action, the browser can stop listening to an HTTP connection using an `AbortController`. However, HTTP connections are one-directional requests in client-server architecture: hanging up the phone on the client side doesn't automatically tell the backend server what you want it to do with the work it already scheduled. In distributed systems, cancellation must be **two-sided**:
1. Client-side: Stop reading the stream to release browser memory.
2. Server-side: Send a cancellation command (`POST /api/races/{id}/cancel`) so background server workers terminate their `asyncio` tasks immediately.

### 4. Next.js App Router & Client Components (`"use client"`)
In Next.js App Router, components default to **React Server Components (RSC)**, which run only on the server to render static HTML. However, streaming user interfaces that use browser APIs (`window`, `fetch`, `requestAnimationFrame`, `useEffect`, `useState`, `AbortController`) require code to run dynamically in the user's browser. Adding the `"use client"` directive at the top of `page.tsx` tells Next.js to compile this component for the client-side browser runtime while still rendering the initial frame on the server.

### 5. CORS vs Reverse Proxies
When a web app running on `http://localhost:3000` tries to fetch data from `http://localhost:8000`, the browser's Same-Origin Policy (SOP) blocks the request by default because the port numbers differ. There are two ways to solve this:
1. **CORS (Cross-Origin Resource Sharing)**: The backend sends headers (`Access-Control-Allow-Origin: http://localhost:3000`) telling the browser it is safe to allow the request.
2. **Reverse Proxy Rewrite**: The frontend server forwards `/api/backend/*` requests directly to `http://localhost:8000/*` behind the scenes, so the browser believes it is talking only to `http://localhost:3000`.
In VersusLab, we configured **both**: CORS on the FastAPI backend for direct high-performance browser connections, and Next.js proxy rewrites for flexible deployment environments.
