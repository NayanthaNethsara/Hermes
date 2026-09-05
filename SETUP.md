# Setup — The Archivist

Everything needed to go from a fresh clone to a working demo, in order.
Each step ends with a **check** — if the check fails, fix it before moving
on, because every later step depends on it.

---

## 0. Prerequisites

| Tool | Version | Needed for | Check |
|---|---|---|---|
| Python | 3.11+ | everything backend | `python --version` |
| Node.js | 20+ | the frontend | `node --version` |
| Tesseract OCR | any recent | scanned/image files in the corpus | `tesseract --version` |

**Tesseract is not a pip package** — `pytesseract` is only a wrapper around a
separate program you must install yourself:

- **Windows:** download the installer from
  https://github.com/UB-Mannheim/tesseract/wiki, then add its install folder
  (usually `C:\Program Files\Tesseract-OCR`) to your `PATH`.
- **macOS:** `brew install tesseract`
- **Linux:** `sudo apt install tesseract-ocr`

If the corpus has no image/scanned files you can skip Tesseract; ingestion
will simply log those files as failed-to-parse and keep going.

---

## 1. Get the three API keys

All free. Nothing here needs a credit card.

### VOYAGE_API_KEY (required — embeddings)
1. Sign up at https://dash.voyageai.com/
2. Create an API key.
3. The default model (`voyage-4-lite`) is on Voyage's 200M-free-token tier,
   so this is not the tight constraint — OpenRouter is (see next).

### OPENROUTER_API_KEY (required — the three agents)
1. Sign up at https://openrouter.ai/
2. Create a key at https://openrouter.ai/keys
3. **This is the tight one.** Without a card attached the free tier is
   **exactly 50 requests/day** (confirmed from OpenRouter's own docs), and
   one question can cost up to ~36. See [API budget](#api-budget) below
   before you start testing.
4. Pick a model whose id ends in `:free`. The default (`minimax/minimax-m2.7:free`)
   was verified working with a real extraction call as of 2026-09-05 — but
   free model availability changes; OpenRouter deprecates and adds `:free`
   models without much notice (the model this project originally shipped
   with, `qwen/qwen3-235b-a22b:free`, was removed from the free tier
   entirely and now 404s). If yours 404s, check current models at
   https://openrouter.ai/models?max_price=0 — a live list is more reliable
   than any name hardcoded here.

### TELEGRAM_BOT_TOKEN (only if demoing the bot)
1. Message **@BotFather** on Telegram, send `/newbot`, follow the prompts.
2. It replies with a token like `123456789:AAE...`.

---

## 2. Backend environment file

From the repo root:

```bash
cp configuration-example/.env.example .env
```

Then open `.env` and fill in `VOYAGE_API_KEY`, `OPENROUTER_API_KEY`, and
(optionally) `TELEGRAM_BOT_TOKEN`. Leave the commented-out overrides alone
unless you hit one of the issues in [Troubleshooting](#troubleshooting).

> `.env` is gitignored. Never commit it — judges read full commit history,
> and a key leaked in an old commit counts against the team even if removed
> later.

**Check:** `cat .env` shows your keys, and `git status` does **not** list `.env`.

---

## 3. Python environment

```bash
# from the repo root
python -m venv .venv

# activate it
.venv\Scripts\Activate.ps1         # Windows PowerShell
.venv\Scripts\activate.bat         # Windows cmd.exe
source .venv/bin/activate          # macOS / Linux

pip install -r requirements.txt
```

**Check:** `python -c "import chromadb, networkx, fastapi, telegram; print('ok')"`
prints `ok`.

> If PowerShell refuses to run the activation script with a execution-policy
> error, run this once per shell session first:
> `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned`
>
> If `python -m venv .venv` fails with `Permission denied` on
> `.venv\Scripts\python.exe`, a previous venv is still active in another
> terminal (or an editor/antivirus has a file open) — close it, or just skip
> recreating the venv if `pip install -r requirements.txt` already succeeds
> against the existing one.

---

## 4. Point at the corpus

The Ashen Era Archive corpus is **read-only** — never write to, rename, or
restructure it (CLAUDE.md rule 2). Put it anywhere outside version control;
if you keep it inside the repo folder for convenience, `.gitignore` already
excludes `/Ashen_Era_Archive/` at the repo root so it won't get committed.
Either way, you pass its path in as a CLI argument — nothing here hardcodes it.

---

## 5. Ingest the corpus (offline, run once)

```bash
python -m src.ingestion.ingest --corpus-path "F:\Ashen_Era_Archive\Ashen_Era_Archive"
```

This walks the folder, extracts text (PDF/DOCX/MD/TXT + OCR for images),
chunks it to ~300-500 words, tags each chunk with a `source_type` and
`trust_tier`, embeds it with Voyage, and writes to `data/chroma/`.

It prints a summary: documents processed, chunks created, per-`source_type`
counts, unclassifiable files, and parse failures. **Read that summary.**

Safe to re-run — chunk ids are stable, so a second run overwrites rather
than duplicating.

### Two things that need attention on the first real run

1. **Source-type classification.** Chunks are classified by matching the
   keywords `codex` / `wiki` / `novel` / `ephemera` (plus `letter`, `ledger`,
   `ballad`, `transcript`) against each file's folder path and filename. Your
   corpus may use different folder names (e.g. `chronicles/` won't match any
   of these). Anything unmatched is listed in the summary and **defaults to
   `ephemera`/`low` trust** — safe, but wrong. Fix by editing
   `SOURCE_TYPE_KEYWORDS` in `src/ingestion/ingest.py` and re-running.

2. **The embedding model.** `VOYAGE_MODEL` defaults to `voyage-4-lite` — a
   real, current, free-tier-eligible model on the standard `/v1/embeddings`
   endpoint this code calls.
   > Earlier drafts of this project specified `voyage-context-4`. That model
   > **does not exist** — it 400s immediately. Voyage's real contextualized
   > embedding model is `voyage-context-3`, but it lives on a different
   > endpoint (`/v1/contextualizedembeddings`) with a different payload shape
   > (nested lists of chunks per document, not a flat list of texts) than
   > what `ingest.py`/`vector_search.py` send. Using a standard model instead
   > of rewriting the pipeline for that endpoint — see `docs/decisions.md`.
   >
   > If embedding still fails with an HTTP 400, double check the model name
   > against https://docs.voyageai.com/docs/embeddings (model names do
   > change), and override in `.env`:
   > ```
   > VOYAGE_MODEL=voyage-3.5-lite
   > ```
   > A 400 now fails in under a second (not ~15s of wasted retries) so you'll
   > find out fast either way.

**Check:** the summary reports a non-zero chunk count, and `data/chroma/`
now exists.

---

## 6. Build the knowledge graph (offline, run once)

```bash
python -m src.ingestion.build_graph
```

Reads every chunk back out of Chroma and asks the LLM to extract
`{from, relation, to}` triples, assembling a NetworkX graph at
`data/graph.gpickle`. Chunks whose response can't be parsed are skipped
with a warning rather than killing the run.

> **This costs one LLM call per chunk.** Against the real 6,372-chunk
> corpus and OpenRouter's confirmed 50-requests/day free tier, the full
> corpus would take **~127 days** on OpenRouter alone — confirmed by
> running it for real, not estimated. Three ways to actually get this
> done, in order of what this project used:
>
> 1. **`--max-chunks N`** caps the run to the N highest-trust-tier chunks
>    first (`TRUST_TIER_PRIORITY`: high → medium → medium-low → low), so a
>    small OpenRouter-budget run still covers the most reliable content
>    first. Good for a demo-sized subset on the free tier.
> 2. **`--resume`** picks a long build back up after an interruption,
>    skipping chunks already in `data/graph.gpickle` — safe to Ctrl+C and
>    restart. Combine with `--workers N` for concurrency, but only raise it
>    against a backend you've confirmed won't rate-limit you at that
>    concurrency — on OpenRouter's free tier, leave it at 1.
> 3. **Spread the build across days or team members' keys** — the free tier
>    resets daily at 00:00 UTC, and `--resume` makes a multi-session build
>    safe.
>
> Whichever path you use, this remains the single most expensive step in
> the project — budget for it deliberately.

Safe to re-run without `--resume` — it always rebuilds fresh, never
appends duplicates.

**Check:** the summary reports non-zero nodes and edges, and
`data/graph.gpickle` exists. (The graph currently committed to this
project's `data/` folder — gitignored, so it travels with the team's local
setup, not with `git clone` — has 35,604 entities and 108,588 edges across
6,371/6,372 chunks.)

> Graph search is treated as an *optional* enhancement: if this file is
> missing, the backend logs a warning and answers using vector search alone.
> So you can demo without it, just with weaker multi-hop behaviour.

---

## 7. Run the backend

```bash
uvicorn src.backend.main:app --reload
```

**Check:** `curl http://localhost:8000/api/health` returns `{"status":"ok"}`.
This must respond instantly even while a question is mid-flight — `/api/ask`
runs in FastAPI's threadpool specifically so it can't block `/api/health`.

Then try a real question end to end (this spends real API calls):

```bash
curl -X POST http://localhost:8000/api/ask ^
  -H "Content-Type: application/json" ^
  -d "{\"question\":\"Who repaired the artifact?\"}"
```

(PowerShell: wrap the whole `-d` value in single quotes instead of `^`-escaping.)

**Check:** the response is JSON with exactly the keys `answer`,
`reasoning_steps`, `sources`, `contradictions`.

If something fails you get a clean `{"error": "..."}` with HTTP 500 rather
than a crashed server — read that message, it names the cause.

---

## 8. Run the frontend

In a second terminal:

```bash
cd src/frontend
copy .env.local.example .env.local     # points at http://localhost:8000
npm install
npm run dev
```

Open http://localhost:3000.

**Check:** ask a question in the UI and confirm the answer, the Sources panel
(with trust badges), and the Reasoning Trace panel all populate. If the
backend is down you'll see "Could not reach the backend…" in the chat rather
than a broken page.

---

## 9. Run the Telegram bot (optional)

Backend must already be running.

```bash
python -m src.bot.telegram_bot
```

**Check:** message your bot on Telegram; it replies with the answer, a
`Sources:` list of up to 3 entries with trust tiers, and a `⚠️ Note:` line
when sources disagree.

---

## 10. Run the eval harness

Backend must already be running.

```bash
python -m src.eval.run_eval --questions-path sample_questions.json
```

Writes `results/eval_log.json` and prints totals, average reasoning steps,
average response time, and how many questions surfaced a contradiction.

`sample_questions.json` at the repo root is the **official 20-question dev
set that ships with the corpus** (`Ashen_Era_Archive/sample_questions.json`
— copied here verbatim). It spans all three sub-tracks (11 questions tagged
`1A`, 7 tagged `1B`, only **2 tagged `1C`** — our track). The final judging
set is different and unpublished, "of the same style" per the challenge
doc. See `TESTING_GUIDE.md` for how to test meaningfully against this —
running all 20 wastes OpenRouter budget on 18 questions from sub-tracks
this project doesn't attempt.

> Re-run this after any meaningful backend change (prompt edit, model swap,
> retrieval tweak) so you can tell whether things improved or regressed.
> It does not judge correctness — that's still a human read.

---

## API budget

This is the most likely thing to ruin a demo day, so plan around it.

Worst case for **one** question, at the default 5 hops:

| Caller | Calls |
|---|---|
| Planner (1 per hop) | 5 |
| Critic "is this enough?" (1 per hop) | 5 |
| Contradiction checks (up to 5 new pairs per hop) | 25 |
| Synthesizer (once at the end) | 1 |
| **Total OpenRouter requests** | **~36** |

Against a ~50/day free tier that's **one question per key per day** in the
worst case. Mitigations, in order of how much they help:

1. **Use several keys.** Each team member makes their own OpenRouter key;
   swap `OPENROUTER_API_KEY` in `.env` between test runs.
2. **Turn the levers down** in `.env` while testing:
   ```
   CONTRADICTION_MAX_PAIRS=2
   MAX_SEARCH_HOPS=3
   ```
   That takes the worst case to roughly 3 + 3 + 6 + 1 = **13 calls**.
   (`MAX_SEARCH_HOPS` can be lowered but never raised above 5 — the 5-hop
   ceiling is a hard project rule and the code clamps it.)
3. **Repeated contradiction comparisons are cached** in-process, so asking
   similar questions back to back costs less than the worst case suggests.
   Restarting the backend clears that cache.
4. **A 4xx error (bad model, bad key format, bad request) fails in under a
   second**, not after 5 retries — only 404/429/5xx/network errors are
   retried with backoff (404 included because OpenRouter's free-tier models
   return it for "temporarily out of capacity", which is transient, not a
   real config error — confirmed empirically; see `docs/decisions.md`). So a
   real misconfiguration (400) won't itself burn your budget while you find
   it, but a 404 will retry for up to ~60s before giving up.
5. **Don't rebuild the graph casually** — Step 6 is one call per chunk.
6. **Don't mix exploratory/manual testing with a real eval run on the same
   key on the same day.** The 50/day cap is shared across everything that
   key does — a handful of manual `curl`/Postman test questions can eat
   most of the budget an 8-question eval run needs. Do exploratory poking
   and the "real" eval run on different days (or different keys) if you can.

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `VOYAGE_API_KEY is not set` | `.env` missing or not at the repo root. It must sit beside `requirements.txt`. |
| Backend behaves differently from the same call in a script; a key/model change seems to have no effect | **A second `.env` somewhere under `src/`.** `load_dotenv()` searches upward from the calling file, so `src/backend/.env` beats the root one for backend code while scripts run from the root use the correct file. Find strays with `find . -name ".env" -not -path "*/node_modules/*"` — there should be exactly one. |
| `RetryError[<Future at 0x... raised HTTPError>]` in the frontend | Old builds swallowed the real error. Errors now name the status and the provider's message. If you still see this, you're running a stale backend process — restart `uvicorn`. |
| `OPENROUTER_API_KEY and OPENROUTER_MODEL must be set` | Both are required, not just the key. Set a `:free` model id. |
| Embedding fails with HTTP 400 (fails in <1s) | Wrong/nonexistent embedding model — see Step 5, note 2. Check the model name is real at https://docs.voyageai.com/docs/embeddings. |
| `data/chroma does not exist` | Run Step 5 first. |
| `data/graph.gpickle does not exist` | Run Step 6 — or ignore it; the backend degrades to vector-only search with a warning. |
| `TesseractNotFoundError` | Tesseract binary isn't installed or isn't on `PATH` (Step 0). |
| HTTP 429 from OpenRouter/Voyage, still failing after retries | Free-tier rate limit tighter than the built-in pacing assumes. Raise `VOYAGE_REQUEST_INTERVAL_SECONDS` / `OPENROUTER_REQUEST_INTERVAL_SECONDS` in `.env` (default 3s / 2s between requests) and re-run — ingestion/graph-building resume cleanly since both are safely re-runnable. If it still persists, you're out of quota for the key — switch keys or wait. |
| A request fails instantly with no retries at all | That's by design for a 4xx (client error, e.g. bad model/bad request) — it would fail identically every time, so it's not worth 15s of backoff. Only 429/5xx/network errors retry. |
| Everything classified as `ephemera` | Folder names don't match the classification keywords — Step 5, note 1. |
| Frontend shows "Could not reach the backend" | Backend isn't running, or `NEXT_PUBLIC_API_URL` in `src/frontend/.env.local` points somewhere else. |
| Answers are nonsense / irrelevant chunks | `VOYAGE_MODEL` was changed after ingesting. Re-run Step 5 with the same model both times. |
| PowerShell: can't run `Activate.ps1` | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned` once per shell. |
| `python -m venv .venv` → `Permission denied` on `python.exe` | The venv is already active in another terminal/process. Close it, or just use the existing venv. |

---

## Fast path for a demo day

```bash
# terminal 1
uvicorn src.backend.main:app --reload
# terminal 2
cd src/frontend && npm run dev
# terminal 3 (optional)
python -m src.bot.telegram_bot
```

Ingestion and graph building are already done by then — they're offline,
one-time steps, not part of the demo.
