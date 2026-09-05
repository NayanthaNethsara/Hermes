# Limitations

What's genuinely weak, untested, or known-broken. Judges reward honesty here,
and the demo script has a dedicated "what didn't work" section — this file is
the raw material for it.

Keep it current: add things the day you hit them.

---

## Update: full corpus ingestion completed successfully

Ingestion has now run end to end against the real 341-file corpus with a
real `VOYAGE_API_KEY`. Final state: 6,372 chunks from 271 documents; the
only files producing zero chunks are 54 confirmed-textless illustration
PNGs (verified by direct OCR test, not assumed). A real query
(`search_chunks("Who is Gareth Ironmere?")`) returns correct, well-ranked,
correctly-trust-tiered results with accurate page numbers — the embedding
pipeline genuinely works, not just "doesn't crash."

Three real bugs surfaced by this run and are fixed — see `docs/decisions.md`
"Real corpus ingestion findings": Voyage's actual (undocumented) free-tier
rate limit, a chunk-id collision across same-named files in different
formats that was silently dropping content, and image-only `.scan.pdf`
files that needed OCR `pypdf` alone can't provide.

**Update:** graph building is also now complete against the full real corpus
(6,371/6,372 chunks, 35,604 entities, 108,588 edges) — see `docs/decisions.md`
"Graph build scope" and its resolution below. A real multi-hop graph query
returns correct, trust-tagged, multi-source facts.

Still not proven: **answer quality end-to-end through the orchestrator/agents
on real questions**, blocked today by the OpenRouter free-tier daily cap —
see "Eval run blocked by OpenRouter's daily quota" below.

## ~~The embedding model may be wrong~~ — confirmed and fixed

**Update:** ran against the real corpus and hit this immediately, as
predicted. `voyage-context-4` (this project's originally-specified model)
**does not exist** — it's not a real Voyage model, hence the instant HTTP 400.
Voyage's real contextualized-embedding model is `voyage-context-3`, and it
lives on a genuinely different endpoint (`/v1/contextualizedembeddings`) with
a different payload shape (nested lists of chunks per document) than the flat
list this code sends to `/v1/embeddings`.

Fixed by defaulting `VOYAGE_MODEL` to `voyage-4-lite` — a real, current,
free-tier model on the endpoint this code already correctly calls. No
rewrite of the ingestion/retrieval payload shape needed. Still
env-overridable via `VOYAGE_MODEL`/`VOYAGE_API_URL` if that model's
availability changes. See `docs/decisions.md`.

Also fixed as part of chasing this down: the retry decorator on every
LLM/embedding call was retrying **any** exception, including a 400 (which is
deterministic and can never succeed on retry) — wasting ~15s of backoff
before failing. It now only retries on 429/5xx/network errors; a 4xx fails
in under a second.

## ~~Free-tier rate limits~~ — hit immediately, mitigated

**Update:** with the model fixed, the very next attempt hit HTTP 429 on the
first embedding call and exhausted all 5 retries (~15s of backoff) without
clearing it. Voyage doesn't publish a requests-per-minute number for accounts
with no payment method attached, so there was no number to target — but
whatever it is, it's low enough to trip on the first request of a fresh run.

Three changes, in order of impact:
1. `EMBED_BATCH_SIZE` raised from 32 to 128 texts per request (`voyage-4-lite`
   allows up to 1,000/request) — fewer, larger requests means far less
   pressure on a per-minute ceiling for the same amount of text.
2. Ingestion and graph-building now enforce a minimum delay between
   consecutive requests (`VOYAGE_REQUEST_INTERVAL_SECONDS`,
   `OPENROUTER_REQUEST_INTERVAL_SECONDS`) *before* hitting the limit, not just
   backoff after. Backoff alone doesn't help a tight bulk loop: the instant
   one retry succeeds, the next batch's request fires immediately and can
   retrigger the same 429.
3. The retry schedule itself was extended (2s/4s/8s/16s/30s, ~60s total, up
   from ~15s) as a safety net, since 5 short retries genuinely weren't enough.

All three are `.env`-tunable (see `configuration-example/.env.example`) since
the real limit for any given account is unknown.

## The free-tier request budget is still the real constraint

A worst-case question costs ~36 OpenRouter requests against a free tier of
roughly 50/day. Graph building costs one call *per chunk*, which on a full
corpus is far beyond a single key's daily allowance.

Practically this means: the graph build has to be spread across keys or days,
and heavy testing needs `CONTRADICTION_MAX_PAIRS` / `MAX_SEARCH_HOPS` turned
down. See `SETUP.md § API budget`.

## Eval run blocked by OpenRouter's daily quota (2026-09-05)

Tried to run `src/eval/run_eval.py` against the real 8-question
`sample_questions.json` set through the full orchestrator with real API
keys, for the first time. Two things came out of this:

**Real bug found and fixed:** every LLM call site (`planner.py`, `critic.py`,
`synthesizer.py`, `trust.py`) treated HTTP 404 as a permanent, non-retryable
error. Live testing showed OpenRouter actually returns 404 — not 429 — for
"this free-tier model is temporarily out of capacity", while a genuinely
invalid/unknown model ID returns 400 instead (confirmed by direct API call).
So 404 was being treated as fatal when it's really transient. Fixed: 404 is
now retried alongside 429/5xx, since it's empirically distinguishable from a
real config error.

**Real constraint hit:** after that fix, every question in the 8-question
eval set still failed — this time because the account's OpenRouter free-tier
quota (50 requests/day, unverified/no card) was fully exhausted
(`X-RateLimit-Remaining: 0`, confirmed via direct API response headers) by
the same day's diagnostic testing (model discovery, retry-bug reproduction,
several manual test calls) plus the agent loop's own per-question cost
(~2-10+ OpenRouter calls per question across up to 5 hops of
planner+critic, plus one synthesizer call). Quota resets at 00:00 UTC daily
(confirmed from the `X-RateLimit-Reset` header). CLAUDE.md rule 3 says to
rotate to a different team member's key rather than pay for more — that
decision belongs to the team, not something to assume. Practical
consequence: **a full 8-question eval run needs a fresh day's quota (or a
different key) done in one sitting**, since exploratory testing on the same
key eats directly into the same 50/day budget the eval needs.

## Reasoning steps don't stream

`docs/architecture.md` 4.7 describes the Reasoning Trace panel as "updating
live as they come in", and the demo script asks you to point at each step "as
it appears". In reality `/api/ask` is a single blocking request that returns
everything at once, so the panel populates in one go after several seconds of a
loading indicator.

This is the largest gap between the documented experience and the built one.
Closing it needs streaming (SSE) from the backend.

## Source-type classification is keyword matching

`source_type` is inferred by matching `codex` / `wiki` / `novel` / `ephemera`
(plus `letter`, `ledger`, `ballad`, `transcript`) against folder and file names.
If the real corpus uses different names, everything lands in the
`ephemera`/`low` fallback and trust tiers become meaningless. The ingestion
summary lists every unclassified file so this is visible rather than silent,
but the fix is manual.

## Entity extraction for graph search is a regex, not NER

The orchestrator decides whether to walk the knowledge graph by looking for
capitalized word sequences in the search query, with a stoplist for question
words. It will miss lowercase entity names, and `search_graph` matches node
names by case-insensitive *substring*, so short entity names can pull in
unrelated nodes.

## Contradiction detection only sees a sample of pairs

Pairs are ranked by keyword overlap and only the top few per hop are actually
compared by the LLM, to control cost. A genuine contradiction between two
chunks that don't share obvious vocabulary will be missed. It also can't detect
a contradiction *within* a single document — same-`source_doc` pairs are
skipped by design, since "sources disagree" implies two sources.

## Chunking splits per page, not across pages

For PDFs, each page is chunked independently so the `page` number stays
accurate for citations. A paragraph spanning a page break gets split, which can
cut a fact in half.

## Chunk ids can collide in theory

Chunk ids come from slugifying the file's relative path. Two different files
that slugify identically (`a-b.txt` and `a_b.txt`) would collide, and the
second would overwrite the first on upsert. Not observed, but not guarded
against.

## In-process caches reset on restart

The contradiction-verdict cache and the loaded knowledge graph live in process
memory. Restarting the backend clears both — the first question after a restart
is slower and costs more API calls. They also grow unbounded in a long-running
process, which is fine for a demo and wrong for production.

## No tests in the repo

Every component was verified with smoke tests during development, but those
were scratch scripts, not committed test files. There is no `pytest` suite to
run, and no CI. A regression would only be caught by re-running things by hand
or via the eval harness.

## Not addressed at all

- No authentication or rate limiting on the API (deliberate — hackathon demo).
- CORS is wide open to all origins.
- No conversation memory: every question is independent, no follow-ups.
- Images are OCR'd to text only; no visual understanding.
- The eval harness logs results but doesn't judge correctness.
