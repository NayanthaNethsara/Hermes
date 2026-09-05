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
