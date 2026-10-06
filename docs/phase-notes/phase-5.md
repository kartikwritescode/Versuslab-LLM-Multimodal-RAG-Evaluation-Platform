# Phase 5: PostgreSQL Persistence, Alembic Migrations, Non-Blocking SSE DB Writes & History UI

Welcome to the Phase 5 notes for **VersusLab**! This document explains how we added database persistence to VersusLab: storing races, contender model runs, token counts, server-side TTFT and latency metrics, and complete generated responses in PostgreSQL via asynchronous SQLAlchemy 2.0 and Alembic, without adding any latency to the live SSE stream, and surfacing past experiments in Next.js `/history` views.

---

## 1. What We Built

In Phase 5, we integrated PostgreSQL database persistence into the VersusLab stack:

1. **Local Infrastructure (`infra/docker-compose.yml`)**:
   - Single container service running `postgres:17-alpine` exposing port `5432`.
   - Credentials configured via environment variables (`POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`).
   - Named persistent volume (`versuslab_pgdata`) so experimental data survives `docker compose down`.

2. **Async SQLAlchemy 2.0 Data Layer (`app/db/`)**:
   - `app/db/base.py`: Singleton `create_async_engine` configured with connection pooling (`pool_pre_ping=True`) and `async_sessionmaker`. Includes a FastAPI dependency `get_session()` providing scoped sessions per request with guaranteed cleanup.
   - `app/db/models.py`: Declarative SQLAlchemy 2.0 models using type-safe `Mapped[...]`:
     - `races`: `id` (uuid hex matching `race_id`), `prompt`, `temperature`, `max_tokens`, `status` (`running`, `completed`, `cancelled`), `created_at` (timestamptz), and `finished_at` (timestamptz).
     - `model_runs`: `id` (uuid hex), `race_id` (foreign key to `races.id` with `CASCADE` delete and index), `model_id` (e.g. `mock:mock-1`), `status` (`queued`, `streaming`, `done`, `error`, `timeout`, `cancelled`), `ttft_ms`, `latency_ms`, `input_tokens`, `output_tokens`, `finish_reason`, `error_message`, and `response_text`.
   - `app/db/service.py`: Encapsulated database operations for inserting races, marking model status transitions, updating timing metrics and response text, and fetching paginated histories.

3. **Alembic Database Migrations (`apps/api/`)**:
   - Configured `alembic.ini` and `migrations/env.py` for asynchronous schema management with `asyncpg` and `Base.metadata`.
   - Created initial migration `001_initial_races_and_model_runs.py` creating the `races` and `model_runs` tables with indexes and foreign keys.

4. **Non-Blocking SSE Persistence Architecture (`app/db/tracker.py`)**:
   - Zero added stream latency: The SSE event is formatted and yielded to the client **FIRST** (`yield f"data: ...\n\n"`).
   - In-memory accumulation: High-frequency `model.delta` tokens do **not** write to the database on every token; text is buffered in memory, and the first token's arrival timestamp is recorded for server-side `ttft_ms` calculation.
   - Isolated short transactions: Database writes only occur on major lifecycle milestones (`model.started`, terminal model states `done`/`error`/`timeout`/`cancelled`, and `race.completed`/`race.cancelled`). Each write uses a short-lived session that commits and closes immediately.
   - Error isolation: Any database glitch is logged as a warning and caught, guaranteeing database issues never disrupt or terminate an ongoing live race (Rule 3: *Errors are data*).

5. **History REST Endpoints (`app/api/race.py`)**:
   - `GET /api/races?limit=20&offset=0`: Paginated list of past races ordered newest first, returning race ID, prompt, model count, status, created at, and finished at.
   - `GET /api/races/{race_id}`: Detailed view returning the race metadata and all associated child `model_runs`.

6. **Frontend History Pages (`apps/web`)**:
   - `/history` (`apps/web/app/history/page.tsx`): Displays a responsive table of historical races with status badges, timestamps, model counts, and direct links to detail views.
   - `/history/[race_id]` (`apps/web/app/history/[race_id]/page.tsx`): Read-only detail view showing the full prompt, parameter cards, and a grid of all contenders showing TTFT, latency, token counts, status badges, and complete response texts.
   - Header navigation: Added direct navigation links between the live streaming Arena (`/`) and past History (`/history`).

---

## 2. Why We Built It This Way

### How DB Writes are Interleaved with the SSE Stream Without Adding Latency
If an application writes to a database during a live streaming connection, it risks adding 5–50ms of network/disk I/O wait to every single word emitted.
We eliminated this bottleneck through a four-part design:
1. **Never Write on Tokens (`model.delta`)**: In a race with 4 models generating 20 tokens/sec, there are 80 deltas per second. Writing every delta to Postgres would flood the database with 80 `UPDATE` queries per second. Instead, we accumulate tokens in an in-memory dictionary.
2. **Yield Before Writing**: In `sse_race()`, we execute `yield f"data: {event.model_dump_json(exclude_none=True)}\n\n"` **before** calling `await tracker.record_event(event)`. The client receives the token packet instantly.
3. **Short-Lived Transactions**: We never hold a database transaction open across the duration of a race. Each milestone update creates an isolated session, executes an indexed `UPDATE`, commits, and closes immediately.
4. **Server-Side Timestamp Truth**: Timing metrics (`ttft_ms` and `latency_ms`) are calculated directly from the nanosecond timestamps stamped on the `RaceEvent` instances centrally by the coordinator (`timestamp_ns`). This ensures exact consistency between what the client saw and what the database records.

---

## 3. Files Touched and Created

```text
versus_lab/
├── infra/
│   └── docker-compose.yml              # Single PostgreSQL 17 service with persistent volume
├── apps/
│   ├── api/
│   │   ├── alembic.ini                 # Alembic configuration
│   │   ├── requirements.txt            # Added sqlalchemy, asyncpg, alembic
│   │   ├── .env.example                # Documented POSTGRES_* and DATABASE_URL
│   │   ├── app/
│   │   │   ├── core/config.py          # Added database_url to Settings
│   │   │   ├── db/
│   │   │   │   ├── __init__.py         # DB package exports
│   │   │   │   ├── base.py             # Async engine, sessionmaker, and get_session dependency
│   │   │   │   ├── models.py           # Declarative Race and ModelRun models
│   │   │   │   ├── service.py          # Database queries and updates
│   │   │   │   └── tracker.py          # Non-blocking streaming event persistence tracker
│   │   │   └── api/race.py             # Pre-seeded race creation, tracker wiring, and GET endpoints
│   │   ├── migrations/
│   │   │   ├── env.py                  # Async Alembic runner
│   │   │   ├── script.py.mako          # Migration template
│   │   │   └── versions/
│   │   │       └── 001_initial_races_and_model_runs.py  # Initial schema migration
│   │   └── tests/
│   │       └── test_persistence.py     # 5 new tests for endpoints, metrics, and error isolation
│   └── web/
│       ├── lib/
│       │   ├── types.ts                # Added RaceListItem, ModelRunDetail, response types
│       │   └── race-client.ts          # Added fetchRaces and fetchRaceDetail
│       └── app/
│           ├── page.tsx                # Added History navigation link
│           └── history/
│               ├── page.tsx            # /history list view
│               └── [race_id]/page.tsx  # /history/[race_id] detail view
└── docs/
    └── phase-notes/
        └── phase-5.md                  # This documentation file
```

---

## 4. How to Run and Verify

### Prerequisites
Make sure PowerShell is open and you are in the project root:
```powershell
cd c:\files\programming\Python\projects\versus_lab
```

### Step 1: Start PostgreSQL via Docker Compose
Ensure Docker Desktop is running on your machine, then run:
```powershell
docker compose -f infra/docker-compose.yml up -d
```
Verify the container is healthy:
```powershell
docker compose -f infra/docker-compose.yml ps
```

### Step 2: Apply Database Migrations
In `apps/api`:
```powershell
cd apps\api
.\.venv\Scripts\alembic upgrade head
```
Expected output:
```text
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> 001_initial, initial races and model_runs tables
```

### Step 3: Start the Backend API Server
```powershell
cd apps\api
.\.venv\Scripts\uvicorn app.main:app --port 8000 --reload
```

### Step 4: Start the Next.js Frontend Dev Server
In a second terminal:
```powershell
cd apps\web
npm run dev -- --port 3000
```

---

### Step 5: Manual End-to-End Test Script

1. **Run a Normal & Mixed Race**:
   - Open [http://localhost:3000](http://localhost:3000).
   - Select 3 models: `Mock (Fast)`, `Mock (Slow)`, and `Mock (Broken)`.
   - Click **Run Race**.
   - Observe the live race finish: `Mock (Fast)` completes, `Mock (Slow)` finishes after ~1s, and `Mock (Broken)` displays `✕ Error`.
2. **Run a Cancelled Race**:
   - Select `Mock (Stuck)` and `Mock (Slow)`.
   - Click **Run Race**.
   - After 1.5 seconds, click **Stop Race**.
   - Both contenders show `⊘ Cancelled`.
3. **Verify Historical Persistence via Web UI**:
   - Click the **History** button in the header (or navigate to [http://localhost:3000/history](http://localhost:3000/history)).
   - Observe both races listed:
     - The first race shows status `✓ Completed` with 3 contenders.
     - The second race shows status `⊘ Cancelled` with 2 contenders.
   - Click **View Detail →** on the first race:
     - Verify `Mock (Fast)` shows status `done`, TTFT ~35ms, and full response text.
     - Verify `Mock (Broken)` shows status `error`, error message `RuntimeError: mock provider failure`, and 3 generated tokens.
   - Click **View Detail →** on the second race:
     - Verify the race status is `cancelled` with appropriate timestamps.
4. **Verify via API**:
   Open a browser tab or run in PowerShell:
   ```powershell
   Invoke-RestMethod http://localhost:8000/api/races
   ```
   Confirm the JSON payload returns the stored race records and total count.

---

## 5. Five Concepts a Beginner Should Understand

### 1. Declarative ORM & Modern SQLAlchemy 2.0 (`Mapped[...]`)
In traditional database programming, developers wrote raw SQL strings like `"SELECT * FROM races"`. An **Object-Relational Mapper (ORM)** lets you define database tables as standard Python classes (`class Race(Base)`). In SQLAlchemy 2.0, `Mapped[str]` and `mapped_column()` use Python's modern type system, so your IDE automatically autocompletes column names, detects type mismatches, and prevents runtime bugs before code even runs.

### 2. Database Migrations with Alembic
As an application grows, its database schema must change (adding columns, creating tables, modifying indexes). If you manually edit a database with `CREATE TABLE`, other developers or production servers will be out of sync. **Alembic** manages schema version control: each migration file (e.g. `001_initial.py`) records the exact `upgrade()` instructions to create or alter tables, and the `downgrade()` instructions to roll back changes, stamped with a unique revision ID in an `alembic_version` table.

### 3. Connection Pooling & `pool_pre_ping`
Opening a new TCP connection and performing a TLS handshake to PostgreSQL takes time (10–50ms). A **connection pool** keeps a collection of open database connections ready in memory. When a request needs to query the database, it borrows a connection from the pool and returns it when finished. The `pool_pre_ping=True` option tests the connection with a lightweight ping before handing it to a request, ensuring that if PostgreSQL was restarted or a connection timed out, stale connections are automatically discarded without throwing errors.

### 4. Non-Blocking I/O & Event Stream Decoupling
In asynchronous web servers, the event loop handles multiple requests simultaneously. If a background database write blocks the event loop or takes 200ms, every other request on that server pauses. Furthermore, in streaming protocols (like SSE), the consumer expects real-time token delivery. Decoupling means:
- Emitting the token to the network stream **immediately**.
- Accumulating tokens in fast local RAM.
- Writing to PostgreSQL only at critical lifecycle milestones using short, dedicated async transactions.

### 5. Foreign Keys with `ON DELETE CASCADE`
When tables relate to one another (each `ModelRun` belongs to a parent `Race`), a **Foreign Key** enforces data integrity by ensuring a model run cannot reference a non-existent race ID. Setting `ondelete="CASCADE"` on the foreign key tells PostgreSQL: *"If a race record is deleted, automatically delete all associated model_runs records in the same transaction."* This prevents orphaned records from cluttering the database.
