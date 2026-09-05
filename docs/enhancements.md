# Enhancement Roadmap — where the remaining points are

Written after a full audit of the built system. Ordered by
**(judging impact × feasibility)**, not by how interesting they are to build.

Context on what's being optimised for, from the competition material in this
repo: sub-track 1C is *"Searching the Way a Human Does"* — so **multi-hop
search that visibly reasons** is the thing being judged. `CLAUDE.md` names the
trust/contradiction layer as the project's core differentiator, and
`demo_video_script.md` requires **4 minutes of live, unedited** demo. That
means: anything that makes the reasoning *visible on screen, live* is worth
more than backend elegance nobody can see.

---

## Tier 1 — do these first

### 1. Stream the reasoning trace live (SSE)
**Impact: very high · Effort: ~half a day · Also closes a documented gap**

Right now `/api/ask` is one blocking request: the user sees a loading
indicator for 10-30 seconds, then everything appears at once. But
`architecture.md` 4.7 promises the trace panel updates *"live as they come
in"*, and the demo script literally instructs you to *"point at each step as
it appears"*. That moment doesn't currently exist.

This is the single biggest gap between the promised experience and the built
one, and it happens to be the most demo-visible thing in the project.

**How:** add `POST /api/ask/stream` that yields Server-Sent Events. The
orchestrator loop already produces a natural event per hop — turn
`run_archivist` into a generator that yields each reasoning step as it's
recorded, then a final `done` event with answer/sources/contradictions. The
frontend swaps `fetch` for `EventSource` and appends steps to the existing
Reasoning Trace panel as they arrive. Keep the existing blocking endpoint for
the Telegram bot and eval harness.

**Why it wins:** the judge watches the agent *think* — plan, search, find, decide
it needs more, search again. That is the sub-track's entire premise, made
visible. Everything else on this list is smaller than this one.

### 2. Visualise the multi-hop path through the knowledge graph
**Impact: high · Effort: ~half a day**

The knowledge graph is arguably the most technically impressive component and
is currently **completely invisible** — it silently contributes chunks and the
user never learns a graph exists.

**How:** `search_graph()` already returns the exact edges it walked
(`from`/`relation`/`to`/`trust_tier`). Return those in the API response
alongside `reasoning_steps`, and render a small node-link diagram in the
Reasoning Trace panel: *Component Y → affects → Equipment Z → maintained by →
Team A*. No new library strictly needed — a handful of SVG lines and circles
in the existing Tailwind styling is enough for 3-6 nodes.

**Why it wins:** it's the clearest possible proof of *multi-hop* rather than
one-shot lookup, and it's a genuinely novel visual most teams won't have.

### 3. Make the trust layer argue with itself on screen
**Impact: high · Effort: ~2-3 hours**

Trust tiers exist and contradictions are surfaced, but the *reasoning about
trust* is invisible. Currently the banner says "sources disagree on X". It
could say why one side is more credible.

**How:** in `synthesizer.py`, when contradictions exist, pass the trust tiers
of the conflicting sources into the prompt and instruct the model to state the
disagreement **and** which source is more authoritative and why — without
resolving it silently (rule 5 still holds: surface both). Then in the
contradiction banner, render the two sides with their trust badges
side-by-side rather than as a text list.

> *"The Codex (high trust) states Renn Duvel performed the repair. A Tavern
> Ballad (low trust) credits the Grey Hand. Both are recorded here; the Codex
> is the more authoritative source, but the disagreement is unresolved."*

**Why it wins:** this is the differentiator the project is built around, stated
out loud in the one place a judge will definitely look.

---

## Tier 2 — credibility and robustness

### 4. A committed test suite
**Impact: medium-high · Effort: ~2-3 hours**

Every component was verified during the build, but with **scratch scripts that
were never committed** — there is no `pytest` suite in the repo and no CI. A
judge reviewing the repo sees zero tests.

**How:** port the existing smoke tests into `tests/`, using the same mocking
approach (patch `_call_llm` / `embed_query`). The high-value ones already
written: contradiction caching, hop-cap enforcement, chunk deduplication,
planner reply parsing, the graceful-degradation paths. Add a
`pytest` line to `requirements.txt` and a one-line GitHub Action.

**Why it wins:** `CLAUDE.md` says judges score git discipline. Visible tests
signal engineering maturity cheaply, and they protect against a regression
breaking the demo the night before.

### 5. Upgrade the eval harness into a scorecard
**Impact: medium-high · Effort: ~3 hours**

`run_eval.py` logs runs but explicitly doesn't judge correctness. That's fine
as a baseline, but the report will be far stronger with numbers in it.

**How:** add an optional `--expect` field per question in
`sample_questions.json` (keywords that should appear), compute a simple hit
rate, and — key part — have the harness **diff against the previous
`eval_log.json`** so you can say *"answer quality went from 5/8 to 7/8 after
we changed the Planner prompt."*

**Why it wins:** turns "we think it works" into evidence, and gives the
submission report and the video's honesty section real numbers to quote.

### 6. Corpus stats endpoint + status strip in the UI
**Impact: medium · Effort: ~1 hour**

**How:** `GET /api/stats` returning chunk count, per-`source_type` counts, and
graph node/edge counts (all cheap local reads). Render as a thin strip in the
frontend header: *"1,284 chunks · 415 documents · 892 entities · 1,455
relationships"*.

**Why it wins:** instantly communicates scale. A judge sees the system is
loaded with a real corpus, not three demo files — in the first two seconds of
the video, before you've said a word.

### 7. Answer confidence signal
**Impact: medium · Effort: ~1-2 hours**

The orchestrator already knows whether it stopped because the Critic was
satisfied, the Planner said DONE, or it **hit the 5-hop cap** — that last case
is a genuine low-confidence signal that currently only appears as a nudge in
the synthesizer prompt.

**How:** return `stopped_reason` in the API response and render it as a small
badge: *"Confident — evidence sufficient"* vs *"Partial — hit search limit"*.
Also derivable: highest trust tier among cited sources.

**Why it wins:** honest uncertainty is explicitly rewarded by the judging
criteria, and it's nearly free — the information already exists and is being
thrown away.

---

## Tier 3 — polish, only if time remains

### 8. Click a source to read the full chunk
Source cards show a truncated snippet. Make them expand to the full chunk text
with its page and trust tier. Cheap (the text is already in the response),
and it proves answers are grounded in real passages rather than invented.

### 9. Follow-up questions
Every question is currently independent. Passing the previous turn's chunks in
as prior context would enable *"and who else was involved?"* — a very natural
demo beat. Note this raises per-question cost.

### 10. Export an answer as a citation report
"Download as Markdown" containing answer, all sources with trust tiers, the
reasoning trace, and contradictions. Frames the tool as producing auditable
research output. Small effort, nice closing beat in a video.

---

## Explicitly *not* recommended

- **An agent framework** (CrewAI/LangGraph/AutoGen) — banned by `CLAUDE.md`
  and `SKILLS.md`, and three plain functions are easier to explain live when a
  judge asks you to walk the code.
- **A bigger/paid model** — violates the free-tier rule, and the bottleneck is
  request *count*, not model quality.
- **Reranking / hybrid BM25 retrieval** — real quality win, but it adds a
  moving part to explain and the budget can't absorb more calls. Only worth it
  if retrieval turns out to be visibly weak on the real corpus.
- **Deploying to Fly.io** — `architecture.md` 10 already concludes local is
  safer for the recording. Don't add cold-start risk to a graded video.

---

## Suggested order

1. Do a real end-to-end run first (`SETUP.md`). **Nothing on this list matters
   until the pipeline is proven against the real corpus** — and that run will
   likely reshuffle these priorities.
2. Then #1 (streaming) and #3 (trust argument) — biggest visible wins.
3. Then #6 (stats strip) and #7 (confidence) — hours of work, disproportionate
   polish.
4. Then #2 (graph visual) if the graph build actually completed on the real
   corpus.
5. #4 (tests) and #5 (scorecard) in parallel with demo prep — they feed the
   written report.
