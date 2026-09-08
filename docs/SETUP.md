# Setup — The Archivist (Hermes)

Everything needed to go from a fresh clone to a working demo, in order.
Each step ends with a **check** — if the check fails, fix it before moving
on, because every later step depends on it.

---

## 0. Prerequisites

| Tool | Version | Needed for | Check |
|---|---|---|---|
| Python | 3.11+ | Backend | `python --version` |
| Node.js | 20+ | Frontend | `node --version` |
| Docker | any recent | PostgreSQL + Redis | `docker --version` |

---

## 1. Get API keys

### GCP_PROJECT_ID + Application Default Credentials (primary path)

1. Create or select a GCP project with Vertex AI API enabled.
2. Run `gcloud auth application-default login` to set up ADC.
3. Set `GCP_PROJECT_ID` and `GCP_LOCATION` in `.env`.

### GEMINI_API_KEY (alternative path)

1. Get a key from [Google AI Studio](https://aistudio.google.com/apikey).
2. Set `GEMINI_API_KEY` in `.env`.

### VOYAGE_API_KEY (required — embeddings)

1. Sign up at https://dash.voyageai.com/
2. Create an API key.
3. The default model (`voyage-3.5-lite`) is on Voyage's free tier.

---

## 2. Environment file

From the repo root:

```bash
cp configuration-example/.env.example .env
```

Open `.env` and fill in your API keys. The required variables:

```env
# LLM (one of these two approaches)
GCP_PROJECT_ID=your-project-id
GCP_LOCATION=us-central1
GEMINI_MODEL=gemini-2.5-flash
# OR
GEMINI_API_KEY=your-key-here

# Embeddings
VOYAGE_API_KEY=your-voyage-key

# Database (defaults work with docker-compose)
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=archivist
POSTGRES_USER=archivist
POSTGRES_PASSWORD=archivist

# Redis (defaults work with docker-compose)
REDIS_URL=redis://localhost:6379/0
```

> `.env` is gitignored. Never commit it.

**Check:** `cat .env` shows your keys, and `git status` does **not** list `.env`.

---

## 3. Start infrastructure

```bash
# PostgreSQL + Redis via docker-compose
make db

# Or manually:
docker compose up -d postgres redis
```

**Check:** `docker ps` shows both containers running and healthy.

---

## 4. Python environment

### Option A: Using `uv` (Recommended)

```bash
uv sync --project src/backend
```

### Option B: Using pip

```bash
python -m venv .venv
source .venv/bin/activate    # macOS / Linux
pip install -e src/backend
```

**Check:** `python -c "import fastapi, langchain_google_genai, asyncpg; print('ok')"` prints `ok`.

---

## 5. Ingest the corpus (offline, run once)

```bash
make ingest
# Or:
python -m src.backend.ingestion.ingest --corpus-path /path/to/Ashen_Era_Archive
```

This walks the corpus folder, extracts text (PDF/DOCX/MD/TXT), chunks it,
embeds with Voyage AI, and writes to PostgreSQL (pgvector).

**Check:** the summary reports a non-zero chunk count, and the
`document_chunks` table in PostgreSQL has rows.

---

## 6. Run the backend

```bash
make backend
# Or:
uvicorn src.backend.main:app --reload
```

**Check:** `curl http://localhost:8000/api/health` returns `{"status":"ok"}`.

Then try a real question:

```bash
curl -X POST http://localhost:8000/api/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Who is Gareth Ironmere?"}'
```

**Check:** the response is JSON with keys `answer`, `reasoning_steps`,
`sources`, `contradictions`.

---

## 7. Run the frontend

In a separate terminal:

```bash
make frontend
# Or:
cd src/frontend && npm install && npm run dev
```

Open http://localhost:3000/chat.

**Check:** ask a question in the UI and confirm the answer streams in,
source cards with trust badges appear, and the reasoning trace populates.

---

## 8. Docker (full stack)

```bash
docker compose up -d
```

- Backend API: `http://localhost:8000`
- Frontend UI: `http://localhost:3000`

---

## Troubleshooting

| Symptom | Cause / Fix |
|---|---|
| `GEMINI_API_KEY is not set` and no GCP project | Set either `GCP_PROJECT_ID` or `GEMINI_API_KEY` in `.env` |
| Backend logs `AFC is enabled with max remote calls` | Update to latest code — AFC is now disabled in `llm.py` |
| `ChatVertexAI` deprecation warning | Update to latest code — migrated to `ChatGoogleGenerativeAI` |
| Frontend shows "Could not reach the backend" | Backend isn't running, or `NEXT_PUBLIC_API_URL` in `.env.local` is wrong |
| Embedding fails with HTTP 400 | Check `VOYAGE_MODEL` name against https://docs.voyageai.com/docs/embeddings |
| `connection refused` on PostgreSQL | Run `make db` or `docker compose up -d postgres` first |
| Redis connection warning in logs | Redis is optional (fail-open). Run `docker compose up -d redis` to enable caching |
| 429 Too Many Requests | Rate limit hit (30/min per IP). Wait 60 seconds |
| Session loads empty on `/chat/<id>` | Expected for new session IDs — session persists after first question |

---

## Fast path for demo day

```bash
# Terminal 1
make db         # starts PostgreSQL + Redis

# Terminal 2
make backend    # starts FastAPI

# Terminal 3
make frontend   # starts Next.js
```

Ingestion is a one-time offline step — already done by demo day.
