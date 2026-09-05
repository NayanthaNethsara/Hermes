# Decisions

Choices made while building, and why. Add to this as you go — "we tried X, it
didn't work because Y" is much easier to write the day it happens than to
reconstruct from memory in week two.

---

## Frontend lives at `src/frontend/`, not the repo root

The Next.js app was originally scaffolded at `frontend/` in the repo root, but
`docs/architecture.md` section 7 and the required submission structure in
`CLAUDE.md` both put it under `src/`. Moved it to match the documented
structure rather than letting the docs drift from reality.

## Next.js, not Vite

`CLAUDE.md` originally said "React + Vite + Tailwind" while
`docs/architecture.md` 4.7 and Prompt 8 both said Next.js (App Router). The
app was built with Next.js, so `CLAUDE.md` was corrected. Flagging it here
because the two docs genuinely disagreed for a while.

## Graph is pickled with stdlib `pickle`, not `networkx.write_gpickle`

Prompt 2 asked for "networkx's pickle functions", but `write_gpickle` /
`read_gpickle` were **removed in NetworkX 3.0** (we're on 3.6). Those helpers
were always thin wrappers over `pickle.dump`/`pickle.load`, so the graph is
pickled directly. Same file, same format, same `data/graph.gpickle` path.

The alternative — pinning `networkx<3` to get the old helpers back — was
rejected: an older library for a convenience wrapper we don't need is a worse
trade than one extra line of stdlib code.

## Config checks happen before retried calls, not inside them

Every LLM/embedding call is wrapped in tenacity backoff. Early on, the
"is the API key set?" check lived *inside* those retried functions, so a
missing key was retried 5 times with backoff and then surfaced as an opaque
`RetryError` — in one case swallowed entirely by an `except` and downgraded to
a warning.

Config errors aren't transient, so they're now checked once at the top of each
public function, before anything retryable runs. A missing key fails
immediately with a message that names the fix.

## Retries only happen on transient errors, not on 4xx

The same class of problem showed up again once real API calls started
failing for real: the retry decorator on every LLM/embedding call retried
**any** exception, including an HTTP 400 (invalid model, malformed request,
bad auth format) — a deterministic error that will fail identically no
matter how many times it's retried. That meant every call to a
misconfigured endpoint wasted the full ~15s of exponential backoff before
finally surfacing the real error.

Every retried call (`ingest.py`, `build_graph.py`, `trust.py`,
`vector_search.py`, and all three agents) now uses a
`retry_if_exception` predicate: retry on 429, 5xx, connection errors, and
timeouts; fail immediately on anything else. A bad model name or malformed
request now surfaces in under a second instead of ~15.

## `voyage-context-4` doesn't exist — switched to a real model

This project's original spec named `voyage-context-4` as the embedding
model. It isn't real. Confirmed by checking Voyage's own docs: the current
model line is `voyage-4` / `voyage-4-lite` / `voyage-4-large` (plus
`voyage-code-4`, `voyage-context-3`, and the older `voyage-3.x` family).
Nothing named `voyage-context-4` exists at any version. Using it 400s
immediately.

Voyage's actual contextualized-embedding model is `voyage-context-3`, but it
is served from a genuinely different endpoint
(`/v1/contextualizedembeddings`) with a different request shape — a list of
lists (chunks grouped per document), not the flat list of texts
`ingest.py`/`vector_search.py` send to `/v1/embeddings`. Adopting it would
mean restructuring how chunks are batched for embedding in both files.

Given the deadline, the fix was to default `VOYAGE_MODEL` to `voyage-4-lite`
instead — a real, current model on the endpoint this code already calls
correctly, and one of the models Voyage's pricing page lists with the
200M-token free allowance. Zero payload changes needed. `VOYAGE_MODEL` stays
env-overridable in case that model's availability changes before the demo.
Switching to the real contextualized endpoint remains a valid future
enhancement (see `docs/enhancements.md`) if retrieval quality on the real
corpus turns out to need it.

## Sources are assembled in Python, not by the LLM

The Synthesizer gets the answer *text* from the model, but the `sources` list
is built directly from the chunks that were actually retrieved. Asking the
model to emit citations as JSON was considered and rejected — it can
hallucinate or drop citations, and citation accuracy is the core promise of
this project (`CLAUDE.md` rule 5). This way citations can't drift from the
evidence.

## Graph search resolves back to real chunks

`search_graph()` returns *edges* (`from`/`relation`/`to`), which don't have the
text, page, or document title needed to cite them. Every edge carries its
`source_chunk_id` though, so the orchestrator looks those chunks up in Chroma
(`get_chunks_by_ids`) rather than fabricating a stand-in from the triple. Graph
hits are therefore citable exactly like vector hits.

## Graph search is optional, vector search is not

If `data/graph.gpickle` is missing, the orchestrator logs a warning and answers
from vector search alone rather than failing the request. The graph is an
enhancement; being unable to embed a query is fatal, but being unable to walk
relationships is a degraded-but-useful state. This also means the system is
demoable before the (expensive) graph build finishes.

## Unclassifiable sources default to *lowest* trust

Ingestion infers `source_type` from folder/file names. Anything it can't
classify is tagged `ephemera`/`low` and listed in the run summary. Defaulting
to low trust means an unknown source can never be silently presented as
authoritative — the failure mode is "under-trusts a good source", which is
recoverable, rather than "over-trusts an unverified one", which isn't.

## Contradiction verdicts are cached per chunk pair

The Critic runs on every hop over a *growing* chunk list, so without a cache
the same pair of chunks gets sent to the LLM again on every hop. Verdicts are
memoised by chunk-id pair for the life of the process. The corpus is fixed, so
a verdict for a given pair can't change.

## Contradictions accumulate across hops

Originally each hop's Critic result *replaced* the previous one, so a
contradiction found on hop 3 could vanish if hop 4 happened to sample
different pairs. That's a silent resolution of a conflict, which rule 5
forbids outright. They now accumulate, deduplicated by topic + source pair.

## `/api/ask` is a sync endpoint on purpose

It was `async def`, which meant the multi-second blocking agent loop ran on the
event loop and froze the whole server — including `/api/health` — for the
duration. As a plain `def`, FastAPI runs it in a threadpool instead. Same for
the Telegram bot, which now hands its blocking backend call to
`asyncio.to_thread`.

## Budget levers are env-tunable; the hop cap has a hard ceiling

`CONTRADICTION_MAX_PAIRS` and `MAX_SEARCH_HOPS` can be lowered from `.env` to
survive the OpenRouter free tier. `MAX_SEARCH_HOPS` is *clamped* to 5 in code —
it can be turned down but never up, because the 5-hop cap is a hard project
rule and shouldn't be defeatable by an env var.

## Real corpus ingestion findings (first full run, 2026-09-05)

Running ingestion against the actual Ashen Era Archive corpus (341 files)
surfaced three real issues no synthetic test data had exposed:

**Voyage's real free-tier rate limit.** Confirmed directly from their own
429 response body: an account with no payment method attached is capped at
**3 requests/minute, 10K tokens/minute** — not documented anywhere public,
only visible by hitting it. `ingest.py` now self-throttles to respect this
by default (`VOYAGE_EMBED_BATCH_SIZE=10`, 22s between requests), and also
retries only on 429/5xx/network errors, never on a 4xx (see "Retries only
happen on transient errors" above) — a 400 from the wrong model name was
wasting the full backoff window before this. After adding a payment method,
the cap lifted entirely (confirmed empirically: 30 requests in ~23s, zero
429s, ~78 req/min) — the code defaults were then raised accordingly
(`VOYAGE_EMBED_BATCH_SIZE=32`, 1.5s), with the conservative values kept
available as a documented `.env` override for unverified accounts.

**Chunk-id collisions across file formats.** The corpus provides many
documents in more than one format at the same path/name (e.g.
`petition.docx` + `petition.pdf` + `petition.txt`, sometimes all three).
`chunk_id` was built from the file path with the extension stripped, so
every format of the same document produced *identical* chunk_ids. Whichever
file processed first "won"; the others were silently dropped with no error,
no warning, nowhere in the summary — findable only by diffing the walked
file list against what actually made it into Chroma. The resume feature
(see above) made this worse: without it, a later file's upsert would at
least *overwrite* the earlier one (losing one version, keeping one); with
it, the later file's real content was never embedded at all because its
(colliding) chunk_ids already "existed."

Fixed with a pre-pass (`build_slug_map`) that only folds the extension into
the slug for files whose base slug is shared by more than one file — the
~90% of files with a unique name keep the plain scheme untouched, so
already-embedded chunk_ids for the non-colliding majority stay valid and
don't need re-embedding. 32 files across 15 collision groups needed
disambiguating; all now embed distinctly. One accepted side effect: the
"winning" file in each group gets re-embedded once more under its new id,
leaving its old, now-orphaned chunk_id in Chroma as a harmless duplicate —
not worth the added complexity of trying to preserve it.

**`.pdf` files with no embedded text layer.** 17 files named `*.scan.pdf`
(petitions, interrogation records, sermons, ballads, contracts, letters —
the corpus's "ephemera" tier) are image-only PDFs. `pypdf.extract_text()`
returns nothing for a page with no text layer — silently, not an error —
so all 17 produced zero chunks. `architecture.md` 4.1 explicitly requires
OCR support for "simulated scans," so this was a real gap, not a
by-design limitation. Fixed by rendering any page with no extractable text
to an image (PyMuPDF, chosen over `pdf2image` specifically because it
needs no external system binary like poppler — same reasoning as avoiding
a second Tesseract-style install step) and OCR-ing it the same way a
standalone image file already was. New dependency: `pymupdf`.

After both fixes: 6,372 chunks from 271 documents. The only files that still
produce zero chunks are 54 `.png` illustration plates (creature art,
character portraits, landscape paintings) — confirmed by direct OCR test to
genuinely contain no text, which is correct, not a bug.

## The project's default OpenRouter model was already dead

`qwen/qwen3-235b-a22b:free` — this project's originally-specified model,
present in every doc and `.env.example` — is no longer on OpenRouter's free
tier. A real call returns HTTP 404 with `"This model is unavailable for
free. The paid version is available now."` This had never been caught
because every orchestrator/agent test up to this point mocked the LLM call;
`build_graph.py` was the first script actually invoked against a real key.

Free model availability on OpenRouter changes often and isn't something to
hardcode confidence in. Queried `GET /api/v1/models` live rather than
guessing a replacement, filtered to `:free`, and test-called four
candidates with a real extraction prompt: two (`google/gemma-4-31b-it`,
`z-ai/glm-5.2`) hit transient 429s from congested shared upstream pools
(retryable, not a hard failure); two (`minimax/minimax-m2.7`,
`nvidia/nemotron-3-super-120b-a12b`) returned clean, valid, well-formed
JSON immediately. Picked `minimax/minimax-m2.7:free` — slightly tighter
output, no markdown fence, no redundant self-referential relations (the
nvidia model produced one: `"is a major Executioner" -> "Executioner"`).
Updated everywhere the old model was referenced: `.env`, `.env.example`,
`SETUP.md`.

## Graph build scope: highest-trust subset, not the full corpus

`build_graph.py` needs one LLM call per chunk. Against 6,372 real chunks and
OpenRouter's confirmed 50-requests/day free-tier ceiling (no purchase
history), the full corpus would take ~127 days. Raising the daily cap to
1,000 requires an actual $10 purchase — real money, and a direct conflict
with CLAUDE.md rule 3 ("only free-tier tools") — so that decision was left
to the user rather than assumed.

Chosen: build the graph from a capped, highest-trust-tier-first subset
instead of the full corpus. Implemented as `build_graph.py --max-chunks N`,
sorting available chunks by `TRUST_TIER_PRIORITY` (high → medium →
medium-low → low) before truncating, so a capped run gets the most
reliable, best-structured content (codex-tier text tends to be dense
registry/record-style writing that extracts cleanly) rather than an
arbitrary prefix. This is a legitimate reduction, not a hidden one: the
orchestrator already treats a missing/incomplete graph as an optional
enhancement (see "Graph search is optional, vector search is not," above),
so partial graph coverage degrades gracefully rather than breaking
anything — multi-hop answers just won't find relationships for entities
outside the sampled subset.

**Update:** the graph has since been built across the full corpus in a
one-time offline pass — 35,604 entities, 108,588 edges, 6,371/6,372 chunks.
`--max-chunks` therefore isn't needed for the current `data/graph.gpickle`,
but stays in the CLI as the documented way to rebuild a smaller graph on a
constrained request budget. The live agents (Planner/Critic/Synthesizer)
and ingestion run on OpenRouter + Voyage throughout, per CLAUDE.md rule 3.

## Claiming 1B as a secondary sub-track, but not 1A

The challenge doc lets teams address more than one sub-track while warning
that "a strong, working solution to a single sub-track will always beat a
shallow attempt at several." Reviewed all three against what was actually
built:

**1B ("Connecting Facts Across Thousands of Pages") — claimed.** This
needed no new capability. The knowledge graph already spans the whole
corpus (35,604 entities, 108,588 edges) and `search_graph()` already does
multi-hop BFS, which is precisely 1B's ask: answering questions where no
single document holds the answer. Verified directly against the official
1B questions — e.g. `Ederon Fellgard` → (2 hops) → `The Iron-Ring Cartel`
→ `was victor of` → `The Leaden Accord` is a real path in the built graph.
Claiming it is honest rather than opportunistic: the mechanism was already
there and is now explicitly tested against the official 1B question set.

**1A ("Rich Answers, Not Just Text") — deliberately not attempted.** This
one *is* a real capability gap, and the reason is worth recording because
it was measured, not assumed. The 11 official 1A questions ask about
content that exists only as pixels: "what is the central emblem on the
banner of House Morvain?", "in the portrait of X, what object are they
holding?". Tesseract OCR captures the *text* on a figure plate but not the
graphics: on `plate_08_creature_weeping_lurker.png` it extracted
`"Weeping Lurker / THREAT RATING / of 10, per the Vanguard scale"` and
dropped the actual rating, which is drawn as a large numeral inside a
gauge. The answer (3) is simply absent from the index.

A vision model fixes this — confirmed by test, not theory: a free
OpenRouter vision model read the same plate and reported "3 (large numeral
centered inside the gauge arc)". So 1A was *feasible*. It was rejected on
budget, not capability: captioning the corpus's 70 distinct images costs 70
requests against a 50/request/day free tier, before any of the testing,
demo, and eval runs that also compete for that quota — roughly 430-600
requests total across all three sub-tracks versus the ~150 available in the
time remaining. Rather than ship a half-populated image index and a
weakened 1C, 1A was dropped. Recorded in `docs/limitations.md` as a known,
deliberate gap.

## Graph search could pull most of the corpus into a single prompt

Found by measuring what a real question actually retrieves, rather than
trusting that it looked reasonable. Two compounding defects:

1. `_extract_entity_candidates()` treats any capitalized word as a possible
   entity, with a stoplist that didn't include sentence-openers. The
   official 1C question *"**In** which year was the 'Gauntlet of Sorrowfell'
   actually forged?"* yielded `In` as an entity.
2. `find_matching_nodes()` matched node names by bare **substring**, so
   `In` matched every node containing those two letters — `Cinder`,
   `Ring`, `Iron`, `King`, and thousands more.

Together these seeded a graph walk from thousands of nodes. Measured
result for that one question: **79,617 edges returned and 5,615 chunks
fetched — 88% of the entire 6,372-chunk corpus — all fed into the Critic
and Synthesizer prompts**, on every subsequent hop. This silently wrecked
answer quality (real evidence buried in noise) and token cost, and never
surfaced earlier because every prior agent test mocked the LLM and no one
had counted the chunks.

Three fixes, each guarding a different failure mode:
- **Whole-word matching** in `find_matching_nodes()`, with exact name
  matches preferred and returned alone. `Ring` no longer matches
  `Cindering`.
- **A generic-entity guard** (`MAX_NODES_PER_ENTITY`): an entity with no
  exact match that hits more than 50 nodes means nothing useful and is
  skipped rather than allowed to seed a walk.
- **A hard cap on graph-sourced chunks per hop**
  (`MAX_GRAPH_CHUNKS_PER_HOP = 15`), ranked by how many edges reference a
  chunk (density of connection to the query's entities) and tie-broken by
  trust tier — so the cap keeps the *best* chunks rather than an arbitrary
  slice.

Same question after the fix: 2,787 edges, **15 chunks**, and the retrieved
relations are now on-topic — including "Authoritative discussion of the
disputed forging of Gauntlet of Sorrowfell → should consult Annals/Codex",
which is the exact contested fact the question is built around.

## Making a question answer in ~100s instead of ~4 minutes

A real 1B question ("which war was won by the organization that included
Isolde Mournvale?") took over a minute with no output, so the loop was
measured rather than guessed at. One LLM call against a free-tier
reasoning model costs **~4-10s**, and the question spent **41 calls**, so
the wall time was simply the sum of them. Three changes, each aimed at a
different cause:

**Contradiction checks now run concurrently.** Up to 5 pairs per hop were
compared one after another, despite being completely independent
network-bound calls - the single largest block of time in a hop. They now
run in a thread pool (`CONTRADICTION_WORKERS`, default 5), with verdicts
written to the shared cache on the main thread afterwards so no worker
mutates state another can see, and results assembled in ranked order so
output stays deterministic. Measured on the same question: **230s of
summed call time completed in ~112s of wall time.**

**The Planner's circular searches now stop the loop.** The Critic returned
`{"enough": false}` on *every* hop even after the answer was clearly
found on hop 2, so the loop always ran the full 5 hops. The Planner
responded by re-asking the same thing in different words - one run
produced "wars won by The Silent Choir", "Which war did The Silent Choir
win", and "The Silent Choir won which war" across three hops, all
retrieving the same chunks for ~15 wasted calls. Queries are now compared
as a sorted bag of significant words with plurals folded, so cosmetic
rewording is recognised as a repeat and the loop stops and answers with
what it has. (A query of nothing but stopwords falls back to raw text,
otherwise every such query would look identical to every other.)

**The Synthesizer no longer receives everything.** `chunks_so_far`
accumulates across hops - measured at **80 chunks / ~152,000 characters**
(~38k tokens) by hop 5 - and all of it went into one final prompt. It's
now capped (`MAX_SYNTHESIS_CHUNKS`, default 25), preferring higher-trust
sources while preserving retrieval order. This is as much a quality fix as
a speed one: material buried in the middle of a very long prompt tends to
be ignored by small models.

The honest remaining problem is the Critic, which is too reluctant to
declare evidence sufficient. Lowering `MAX_SEARCH_HOPS` and
`CONTRADICTION_MAX_PAIRS` is the reliable lever; a better Critic prompt
would be the real fix and is left as known work in
`docs/limitations.md`.

## A stray `src/backend/.env` silently overrode the real config

The most expensive bug in the project to diagnose, and the most mundane
once found. Symptom: `/api/ask` returned 500 with
`RetryError[<Future at 0x... raised HTTPError>]`, while the *same* question
run from a standalone script worked fine. Swapping in a fresh OpenRouter
key changed nothing.

Cause: a leftover `src/backend/.env`, containing an old API key and
`OPENROUTER_MODEL=qwen/qwen3-235b-a22b:free` — the model that had already
been retired from OpenRouter's free tier (documented above).
`python-dotenv`'s bare `load_dotenv()` searches upward from the *calling
file*, so every module under `src/backend/` found that file before the real
root `.env`. Scripts run from the repo root loaded the correct config;
the backend loaded the stale one. Same code, different config, depending
on which file imported it first.

That also explains an earlier misdiagnosis recorded in this file: the
"model is intermittently unavailable" theory. The orchestrator was never
requesting the working model at all — it was asking for the retired one
every time, which is exactly why the 404 body helpfully said "use this
slug instead: qwen/qwen3-235b-a22b".

Fixes:
- Removed the stray file (it was gitignored and untracked, so no key ever
  reached git history).
- `load_dotenv()` in the backend's config-reading modules is now **pinned
  to the repo root** (`load_dotenv(REPO_ROOT / ".env")`). Config that
  resolves differently depending on which file imported it first isn't
  config.

Lesson worth keeping: when identical code behaves differently in two
contexts, suspect the environment before the code. Two days were spent
theorising about provider flakiness that never existed.

## One shared LLM client instead of four copies

`planner.py`, `critic.py`, `synthesizer.py`, and `trust.py` each carried
their own near-identical copy of the OpenRouter request, retry predicate,
and config check. That duplication had a real cost: the retry-on-4xx bug
had to be found and fixed four separate times, and the opaque-`RetryError`
problem existed in four places at once.

They now all call `src/backend/llm.py::chat()`. Beyond removing the
duplication it fixes three things that were wrong in all four copies:

- **Model failover.** The chain is `OPENROUTER_MODEL` followed by
  `OPENROUTER_FALLBACK_MODELS`. A 404 ("this free model is out of
  capacity") moves to the next model *immediately* rather than burning the
  full ~60s backoff on a model that has nothing to give. Free-tier models
  being withdrawn or briefly unavailable has now bitten this project
  twice, so it's treated as an expected condition, not an outage.
- **Errors say what happened.** `raise_for_status()` throws the response
  body away, which is the only part explaining *why* — "Rate limit
  exceeded: free-models-per-day" and "This model is unavailable for free"
  are both bare 404/429s otherwise. The body is now included, and
  `reraise=True` stops tenacity from burying the real exception inside
  `RetryError[<Future ...>]`, which is what the frontend had been showing
  the user.
- **Empty responses are handled.** Reasoning models can spend their whole
  token budget on the `reasoning` field and return `content: null`. The old
  code passed that `None` straight to callers expecting text. It now
  counts as that model failing, and the chain moves on — observed
  recovering twice in a single real run.

## OpenRouter 404 is sometimes transient, not permanent — retry logic was wrong

> **Later correction — the premise of this entry was wrong.** The
> "same model 200s in isolation but 404s through the orchestrator"
> observation below was real, but the explanation wasn't: the orchestrator
> was loading a stray `src/backend/.env` that pinned the *retired* model,
> so the two paths were never asking for the same model. Kept here rather
> than deleted because the wrong hypothesis cost real time, and the
> reasoning that produced it (and the 400-vs-404 distinction, which is
> genuine and still used) is worth showing. See "A stray `src/backend/.env`
> silently overrode the real config" above.

Live-tested the full agent loop against OpenRouter for the first time
(previously every orchestrator/agent test mocked the LLM call). The exact
same model (`minimax/minimax-m2.7:free`) that returned HTTP 200 ten times in
a row in isolated manual tests returned HTTP 404 consistently when called
through the real orchestrator loop minutes later, with the body `"This
model is unavailable for free."` — the same message text as the already-dead
`qwen/qwen3-235b-a22b:free` model documented above, but this time for a
model confirmed live and working moments before and after.

Checked what a genuinely nonexistent/invalid model ID returns for
comparison: HTTP 400 (`"... is not a valid model ID"`), not 404. That's the
key distinction — 404 on OpenRouter's free tier means "this specific model
has no free capacity available right now" (a transient, provider-side
capacity issue that clears up on retry), while 400 means "this model
doesn't exist" (a real, permanent config error). The existing
`_is_retryable_api_error` predicate (see "Retries only happen on transient
errors," above) treated both as equally permanent and never retried either
— reasonable for 400, wrong for 404.

Fixed by adding 404 to the retryable set (429, 5xx, 404) in all four
OpenRouter call sites (`planner.py`, `critic.py`, `synthesizer.py`,
`trust.py`) — but deliberately *not* in `vector_search.py`, where a 404
against the Voyage embeddings endpoint would mean a genuine URL/config bug,
not model-capacity flakiness, since Voyage doesn't exhibit this pattern.
