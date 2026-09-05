# Limitations

What's genuinely weak, untested, or known-broken. Judges reward honesty here,
and the demo script has a dedicated "what didn't work" section — this file is
the raw material for it.

Keep it current: add things the day you hit them.

---

## Not yet run against the real corpus or real API keys

**The biggest caveat.** Every component has been verified, but with synthetic
test documents and mocked embedding/LLM calls. What *has* been proven is the
plumbing: real HTTP between the real frontend, the real FastAPI server, and the
real Telegram bot handler; real Chroma reads/writes; real graph traversal; real
pickle round-trips.

What has **not** been proven: that Voyage and OpenRouter accept our request
shapes with live keys, and that answer quality on the actual Ashen Era Archive
is any good. Step 5 of `SETUP.md` is where reality will bite first.

## The embedding model may be wrong

The configured default is `voyage-context-4`. Voyage's `*-context-*` models are
contextualized-embedding models served from a **different endpoint**
(`/v1/contextualizedembeddings`) with a different payload shape than the
standard `/v1/embeddings` this code calls. If that model name is wrong or needs
the other endpoint, ingestion fails immediately with an HTTP 400.

Mitigated, not solved: `VOYAGE_MODEL` and `VOYAGE_API_URL` are env-overridable,
so the fix is a `.env` edit rather than a code change.

## The free-tier request budget is the real constraint

A worst-case question costs ~36 OpenRouter requests against a free tier of
roughly 50/day. Graph building costs one call *per chunk*, which on a full
corpus is far beyond a single key's daily allowance.

Practically this means: the graph build has to be spread across keys or days,
and heavy testing needs `CONTRADICTION_MAX_PAIRS` / `MAX_SEARCH_HOPS` turned
down. See `SETUP.md § API budget`.

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
