# Phase 6: Basic RAG with pgvector, Ollama Embeddings, Deduplication & Race Context Injection

Welcome to the Phase 6 notes for **VersusLab**! This document explains how we built the foundation for Retrieval-Augmented Generation (RAG) in VersusLab: vector storage with PostgreSQL's `pgvector` extension, an embedding provider abstraction targeting Ollama (`nomic-embed-text`), content-hash deduplication, deterministic paragraph chunking, and canonical context injection into the shared race template.

---

## 1. What We Built

In Phase 6, we introduced basic RAG capabilities into the VersusLab stack:

1. **Vector-Enabled Infrastructure (`infra/docker-compose.yml`)**:
   - Updated PostgreSQL service image from `postgres:17-alpine` to `pgvector/pgvector:pg17`, providing native vector operations (`<->`, `<=>`, `<#>`) inside PostgreSQL 17.
   - Preserved persistent storage volume (`versuslab_pgdata`).

2. **Alembic Vector Migration (`apps/api/migrations/versions/002_add_pgvector_and_documents.py`)**:
   - Creates the PostgreSQL `vector` extension (`CREATE EXTENSION IF NOT EXISTS vector`).
   - Creates `documents` table:
     - `id`: UUID string primary key.
     - `filename`: original uploaded file name.
     - `content_hash`: SHA-256 hex digest of file bytes (indexed for fast duplicate lookups).
     - `mime_type`: detected or fallback MIME type.
     - `created_at`: UTC timestamp with timezone.
   - Creates `document_chunks` table:
     - `id`: UUID string primary key.
     - `document_id`: foreign key to `documents.id` with `CASCADE` delete and index.
     - `chunk_index`: 0-indexed position within the document.
     - `text`: chunk text payload.
     - `embedding`: `Vector(768)` pgvector column matching Ollama's embedding dimension.

3. **Embedding Provider Protocol (`app/providers/embeddings.py`)**:
   - `EmbeddingProvider` Protocol:
     - `embed_documents(texts: list[str]) -> list[list[float]]`
     - `embed_query(text: str) -> list[float]`
   - `OllamaEmbeddingProvider`: Async client calling Ollama's modern `POST /api/embed` endpoint using `OLLAMA_EMBEDDING_MODEL` (default `"nomic-embed-text"` with 768 dimensions).
   - `MockEmbeddingProvider`: Deterministic pseudo-embedding generator using SHA-256 unit vectors for fast, offline unit testing without requiring Ollama or GPU models.

4. **Deterministic Paragraph Chunking (`app/retrieval/chunking.py`)**:
   - Normalizes line breaks and splits text on paragraph boundaries (`\n\n+`).
   - Greedily merges small consecutive paragraphs up to **800 characters** (approx. 120–160 words) to maintain coherent context without fragmentation.
   - Splits oversized paragraphs (>800 characters) on sentence endings (`. `, `? `, `! `) to avoid truncating thoughts mid-sentence.

5. **Document Ingestion & Idempotent Deduplication (`app/api/documents.py`)**:
   - `POST /api/documents`: Accepts file uploads (`.txt`, `.md`). Computes the SHA-256 content hash of the raw bytes.
     - **Idempotency**: If a document with the same content hash already exists in PostgreSQL, the API immediately returns the existing record (`deduplicated: true`) without re-chunking or re-embedding.
     - If new, chunks text, batch embeds chunks via `EmbeddingProvider`, and saves to PostgreSQL in a single transaction.
   - `GET /api/documents`: Returns a list of all uploaded documents with chunk counts.

6. **Basic Vector Retrieval & Context Injection (`app/retrieval/basic.py`, `app/api/race.py`)**:
   - `retrieve_top_k`: Embeds the user's prompt query and executes a pgvector cosine distance search (`DocumentChunk.embedding.cosine_distance(query_vector)`), returning the top-K chunks (default K=5).
   - `format_rag_context`: Formats retrieved chunks into a single, canonical system prompt.
   - **Fairness Guarantee (Rule 6)**: The canonical context string is prepended as a system message to the shared `ModelRequest` template **ONCE** before the race begins. Every contender model receives the exact same retrieved context.

7. **Frontend Attachment UI (`apps/web/app/page.tsx`)**:
   - Document selector dropdown allowing the user to pick from existing uploaded documents or "None".
   - File upload button supporting `.txt` and `.md` files.
   - Active attachment badge displaying document name and chunk count, with a one-click detach button.

---

## 2. Why We Built It This Way

### The Chunking Strategy: Paragraph-First Greedy Merging
Naive chunking (e.g. splitting every 500 characters) frequently splits words in half, cuts sentences mid-thought, and destroys code blocks or lists.
Our paragraph-based approach:
1. Treats paragraphs as natural units of human thought.
2. Merges small consecutive paragraphs so short bullet points or dialogue lines stay together.
3. Enforces an 800-character ceiling to prevent chunks from exceeding embedding model context windows or diluting vector search relevance.

### Why Idempotent Content-Hash Deduplication?
Generating embeddings for documents requires compute (or paid API tokens in later phases). If a user uploads `readme.txt` three times, calculating embeddings three times wastes compute and litters the vector database with duplicate vectors that distort similarity search results. By hashing the raw bytes with SHA-256 before doing any work, the server recognizes identical documents in under 1ms.

### Canonical Context Injection & Fairness (Rule 6)
In evaluation systems, comparison validity is paramount. If Model A receives context formatted differently than Model B, or if retrieval is executed separately per model, the race is invalid.
By querying PostgreSQL once per race and formatting the retrieved chunks into a single canonical system prompt before dispatching contenders, we ensure that:
- Every model sees the exact same chunks in the exact same order.
- TTFT and latency measurements reflect pure model generation performance, not varying database retrieval latencies.

---

## 3. Files Touched and Created

```text
versus_lab/
├── infra/
│   └── docker-compose.yml              # Updated image to pgvector/pgvector:pg17
├── apps/
│   ├── api/
│   │   ├── requirements.txt            # Added pgvector, python-multipart
│   │   ├── .env.example                # Documented OLLAMA_EMBEDDING_MODEL, EMBEDDING_DIMENSIONS, RAG_TOP_K
│   │   ├── app/
│   │   │   ├── core/config.py          # Added RAG settings to Settings
│   │   │   ├── main.py                 # Mounted documents_router
│   │   │   ├── db/models.py            # Added Document and DocumentChunk declarative models
│   │   │   ├── providers/
│   │   │   │   └── embeddings.py       # EmbeddingProvider protocol, Ollama & Mock providers
│   │   │   ├── retrieval/
│   │   │   │   ├── __init__.py         # Retrieval exports
│   │   │   │   ├── chunking.py         # Paragraph-based text chunker
│   │   │   │   └── basic.py            # Vector cosine distance search & context formatter
│   │   │   └── api/
│   │   │       ├── documents.py        # POST/GET /api/documents router with deduplication
│   │   │       └── race.py             # Added document_id to RaceRequest & canonical RAG injection
│   │   ├── migrations/versions/
│   │   │   └── 002_add_pgvector_and_documents.py  # Alembic migration for pgvector & documents
│   │   └── tests/
│   │       └── test_rag.py             # 9 unit tests for chunking, embeddings, deduplication, and RAG
│   └── web/
│       ├── lib/
│       │   ├── types.ts                # Added document_id to RaceRequest, DocumentItem type
│       │   └── race-client.ts          # Added fetchDocuments and uploadDocument
│       └── app/
│           └── page.tsx                # Added document attachment dropdown & upload controls
└── docs/
    └── phase-notes/
        └── phase-6.md                  # This documentation file
```

---

## 4. How to Run and Verify

### Prerequisites
Make sure PowerShell is open and you are in the project root:
```powershell
cd c:\files\programming\Python\projects\versus_lab
```

### Step 1: Pull Ollama Embedding Model (If testing real local embeddings)
```powershell
ollama pull nomic-embed-text
```

### Step 2: Start PostgreSQL with pgvector via Docker Compose
Ensure Docker Desktop is running, then recreate the container with the pgvector image:
```powershell
docker compose -f infra/docker-compose.yml up -d
```

### Step 3: Apply the New Alembic Migration
```powershell
cd apps\api
.\.venv\Scripts\alembic upgrade head
```
*(Output will indicate `Running upgrade 001_initial -> 002_pgvector_and_documents`)*

### Step 4: Start Backend and Frontend
Terminal 1 (Backend):
```powershell
cd apps\api
.\.venv\Scripts\uvicorn app.main:app --port 8000 --reload
```
Terminal 2 (Frontend):
```powershell
cd apps\web
npm run dev -- --port 3000
```

---

### Step 5: Manual End-to-End Test Script

1. **Create a Test Document**:
   Create a small text file `versus_lore.txt`:
   ```text
   # Project VersusLab Secret Lore

   Project VersusLab was founded in the year 2026 on Planet Kepler-442b by robotic astronomers.

   The primary energy source for VersusLab is a miniature captured blue hypergiant star known as Stella-9.

   All experiments are evaluated using the ancient Galactic Protocol of Monotonic Stamping.
   ```

2. **Test Idempotent Deduplication**:
   - In the web UI at [http://localhost:3000](http://localhost:3000), click **Upload .txt / .md** and select `versus_lore.txt`.
   - Observe message: *"Uploaded 'versus_lore.txt' successfully (3 chunks created)."*
   - Upload the exact same file a second time.
   - Observe message: *"Existing document 'versus_lore.txt' matched & attached (3 chunks)."* (Deduplication confirmed!)

3. **Run a Race WITH the Document Attached**:
   - Select `Mock (Fast)` and `Mock (Slow)` (or cloud models if configured).
   - Verify `versus_lore.txt` is selected in the **Attach Document (RAG)** dropdown.
   - Enter prompt: *"Where was VersusLab founded and what powers it?"*
   - Click **Run Race**.
   - Observe the models answer referencing *Planet Kepler-442b* and *Stella-9* directly from the retrieved document context!

4. **Run a Race WITHOUT the Document Attached**:
   - Change the dropdown to **None (No document attached)**.
   - Enter the same prompt: *"Where was VersusLab founded and what powers it?"*
   - Click **Run Race**.
   - Observe that without the document, the models have no knowledge of Kepler-442b or Stella-9.

---

## 5. Five Concepts a Beginner Should Understand

### 1. Vector Embeddings
A **vector embedding** is an array of floating-point numbers (e.g. 768 numbers) that represents the semantic meaning of a text. Words or sentences with similar meanings produce vectors that point in nearly the same direction in high-dimensional mathematical space. For example, the vector for *"dog"* will be much closer to *"puppy"* than to *"refrigerator"*.

### 2. Cosine Distance (`<=>`)
In high-dimensional vector spaces, comparing how similar two texts are is measured by the angle between their embedding vectors. **Cosine similarity** measures the cosine of this angle:
- 1.0 means identical direction (maximum semantic similarity).
- 0.0 means orthogonal (unrelated).
In `pgvector`, the `<=>` operator computes **cosine distance** (`1 - cosine_similarity`), where 0.0 means identical and smaller numbers mean closer matches.

### 3. Chunking & Context Window Economy
Language models and embedding models have finite context windows. You cannot feed an entire 200-page book into a single embedding vector without losing all fine-grained details. **Chunking** breaks long texts into smaller, focused segments (paragraphs) so each chunk gets its own distinct vector. During search, only the 3–5 most relevant chunks are retrieved and sent to the LLM.

### 4. Content-Hash Deduplication (SHA-256)
A cryptographic hash function like SHA-256 converts any amount of data into a fixed 64-character fingerprint. Even changing a single comma completely changes the hash. By storing `content_hash` in PostgreSQL with a unique or indexed constraint, the system can instantly check whether a file has already been ingested without re-reading or re-computing expensive embeddings.

### 5. RAG System Prompts & Injection Seams
In Retrieval-Augmented Generation, the LLM does not search the database itself. Instead, the backend search engine finds the relevant information first, pastes it into a **system prompt**, and then prompts the LLM: *"Here are the reference facts: [...]. Answer the user's question using only these facts."* This grounds the model's answer in your private data, eliminating hallucinations.
