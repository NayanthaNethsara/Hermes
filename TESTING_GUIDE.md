# Testing Guide — is it good enough to submit?

For when the coding is done and the only thing left is to verify the system
actually answers questions well, before the 9 Sep 2026, 11:30 PM deadline.
Grounded in `docs/AI_Competition_Challenge_Final.pdf`'s actual rubric
(section 6) and deliverables (section 5), not guesswork.

Read this once end to end before you start — the quota section especially,
since it constrains how you should test, not just when.

---

## 0. Two things to know before you test anything

**1. `sample_questions.json` is the real official dev set — read it
carefully.** It ships with the corpus (`Ashen_Era_Archive/sample_questions.json`,
copied verbatim to the repo root) and has exactly 20 questions, tagged by
sub-track: **11 for 1A, 7 for 1B, 2 for 1C**.

This project targets **1C (primary) + 1B (secondary)**, so 9 of the 20 are
in scope. The 11 `1A` questions are about figure plates and portraits and
are **deliberately out of scope** — the system has no visual understanding
(see `docs/limitations.md`), so testing them produces guaranteed failures
and burns budget for no signal.

Use **`sample_questions_1b_1c.json`** (repo root): the 9 official in-scope
questions plus 2 supplementary ones written for this project. Not the full
20.

The 2 real 1C questions are both about **a contested fact** ("the *true*
founding", "*actually* forged") — that's not a coincidence. Sub-track 1C is
about multi-step reasoning, and this corpus's version of that is largely
"sources disagree, dig until you can say which one is right (or that they
genuinely conflict)." These two questions are the best test of whether the
trust/contradiction layer is actually earning its keep, not just present in
the code.

**2. The competition rules require teams of exactly 4** (section 4:
"Teams consist of exactly 4 members"), and the rubric's Human–AI
collaboration criterion (15%) plus the report's required "team member
names, roles, and contributions" section both assume a team, not a single
person. The commit history in this repo currently shows one author. If
this is genuinely a solo build, that's worth resolving (adding real
teammates' contributions, or documenting the situation honestly) before
submission — it's not something a testing pass can fix, but it's more
consequential than any answer-quality issue below, so flagging it here
first.

---

## 1. Respect the OpenRouter budget while testing

This is the tightest constraint in the whole project — see `SETUP.md §
API budget`. The free tier (no card) is **50 requests/day**, and one
question through the full agent loop costs up to **~36 requests** in the
worst case (5 hops × (planner + critic + up to 5 contradiction checks) + 1
synthesizer call). That means:

- **You can realistically fully-test 1-2 questions per key per day** at
  default settings. Plan test sessions around this — don't discover it
  mid-session the way this project did (see `docs/limitations.md` "Eval
  run blocked by OpenRouter's daily quota").
- **Set the budget levers before you test anything.** At stock settings a
  measured question cost **41 API calls and ~110 seconds** — that is
  *fewer than two questions per key per day*, which is not enough to run a
  demo, let alone test one. Put these in `.env`:
  ```
  MAX_SEARCH_HOPS=3
  CONTRADICTION_MAX_PAIRS=3
  ```
  That's ~16 calls and ~45-60s per question (3 questions/day/key), with no
  observed quality loss — the answer was already settled by hop 2 on every
  question tested. Raise them back only for a final representative run.
- **Expect 45-110 seconds per question, with no progress indicator.** The
  UI shows a spinner the whole time (`/api/ask` doesn't stream). This is
  documented, not a hang. If you're demoing live, ask the question and
  narrate while it works.
- **Don't mix manual poking (curl, Postman, the frontend) with a real eval
  run on the same key on the same day.** A handful of manual test questions
  can eat the budget an eval run needs. If you have multiple team members'
  keys, use different ones for exploratory testing vs. the "real" pass.
- Check remaining quota before a serious test session:
  ```bash
  curl -s https://openrouter.ai/api/v1/chat/completions -X POST \
    -H "Authorization: Bearer $OPENROUTER_API_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"model\":\"minimax/minimax-m2.7:free\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}],\"max_tokens\":1}"
  ```
  A `429` with `"free-models-per-day"` in the body means today's quota is
  gone — the response includes `X-RateLimit-Reset`, a Unix ms timestamp for
  when it clears (daily, at 00:00 UTC).

---

## 2. Smoke test (5 minutes, ~1-2 questions, do this first)

Confirms nothing is actually broken before spending a full test pass.

```bash
# terminal 1
uvicorn src.backend.main:app --reload
```

```bash
# terminal 2 - health check first, costs nothing
curl http://localhost:8000/api/health
# expect: {"status":"ok"}

# one real question
curl -X POST http://localhost:8000/api/ask -H "Content-Type: application/json" \
  -d "{\"question\":\"In which year was the 'Gauntlet of Sorrowfell' actually forged?\"}"
```

**Pass criteria:**
- Response is JSON with exactly the keys `answer`, `reasoning_steps`,
  `sources`, `contradictions` (the frozen contract, `docs/architecture.md`
  section 6) — no extra keys, no missing ones.
- HTTP 200, not a 500. If you get a clean `{"error": "..."}` at 500, read
  the message — it names the cause (this is by design, not a crash).
- Took somewhere under ~90 seconds. Much longer suggests hop count or
  retries are misbehaving.

If this fails, stop and fix it before doing anything below — there's no
point evaluating answer *quality* on a system that isn't answering at all.

---

## 3. What "good" looks like, panel by panel

Test through the actual frontend (`npm run dev` in `src/frontend`) for
this part — panel behavior is easier to judge visually than in raw JSON.

### Answer text
- Actually answers the question asked, not a generic restatement of it.
- If the evidence was incomplete (hop cap hit), the answer should say so
  honestly rather than presenting a partial picture as complete — this is
  literally instructed in the synthesis prompt when `hit_hop_cap` is true
  (`orchestrator.py`). If you see a confident answer that turns out to be
  based on 1 weak source, that's the failure mode to watch for.

### Left panel — Sources
- Each source shows a **trust badge**: green=high, yellow=medium,
  orange=medium-low, red=low. Spot-check a few against
  `src/ingestion/ingest.py`'s `SOURCE_TYPE_KEYWORDS` classification logic —
  a codex citation should be green, a tavern ballad should be red.
- **Every claim in the answer should trace back to something in this list.**
  Sources are assembled from the actual retrieved chunks in Python, not
  generated by the LLM (`docs/decisions.md` "Sources are assembled in
  Python, not by the LLM") specifically so this can't drift — if you find
  an unsourced claim, that's a real bug, not expected behavior.
- Pick one source and open the actual file it names in the corpus. Confirm
  the snippet is really in there, on the page cited. This is the single
  best trust-building check you can do before a demo.

### Center panel — Chat
- An amber **contradiction banner** appears above any answer where
  `contradictions` is non-empty. Ask one of the two real 1C questions
  (both are framed around a contested fact) specifically to try to trigger
  this — it's the project's core differentiator, so confirm it actually
  fires on a real question, not just in a scripted test.
- If it never fires on any question you try, that's worth investigating
  before the demo — either the corpus questions you're using don't
  actually have conflicting sources, or contradiction detection has
  regressed. Check `docs/limitations.md` "Contradiction detection only
  sees a sample of pairs" for a known reason it might miss a real one.

### Right panel — Reasoning Trace
- Each step should read like a genuine, specific search ("Searched:
  'Gloamreach founding year'"), not a generic filler query. A trace that's
  the same 1-2 words reworded every hop suggests the Planner isn't
  actually using what's been retrieved so far.
- Step count should usually be well under the 5-hop cap for a question with
  a real answer in the corpus. Hitting the cap on every single question is
  a sign something's wrong (over-cautious Critic, or retrieval not
  actually finding relevant chunks) — see `docs/limitations.md` for
  Critic/retrieval known limitations before assuming it's fine.
- **Note (documented, not a bug to chase):** the panel is meant to update
  live per `docs/architecture.md` 4.7, but `/api/ask` is currently a single
  blocking call, so it populates all at once after a loading delay. This
  is the largest known gap between the documented and built experience —
  worth mentioning honestly in the report/demo, not worth "fixing" this
  close to the deadline unless there's real time left.

---

## 4. Running the eval harness for a repeatable pass

```bash
python -m src.eval.run_eval --questions-path sample_questions_1b_1c.json
```

Writes `results/eval_log.json`: per-question answer, reasoning step count,
whether a contradiction fired, and response time. It does **not** judge
correctness automatically — that's still a human read, by design
(`src/eval/run_eval.py`'s own docstring is explicit about this).

After it finishes, open `results/eval_log.json` and for each question ask:
1. Is the answer actually right (or honestly uncertain), based on what you
   know of the corpus / can verify by checking the source file?
2. Does `reasoning_steps` show real, specific search queries?
3. If two sources plausibly disagree on this topic, did `contradictions`
   catch it?

This costs real budget (11 questions × up to ~36 calls worst case — far
more than one day's free quota). Budget levers (§1) matter more here than
anywhere else. Practical approach: run a **subset** first
(`--questions-path` accepts any JSON file, so make a 2-3 question file),
with the levers turned down, and only do a full-settings run over the
whole set once you're confident nothing else needs fixing.

**For 1B specifically**, check the reasoning trace shows the answer being
*assembled across documents* rather than found in one place — that's the
whole point of the sub-track. E.g. for "which accord was won by the faction
Ederon Fellgard is a member of?", the trace should show it establishing his
faction first, then that faction's accord. If it answers correctly but the
trace shows one lookup, say so honestly in the report rather than claiming
multi-hop reasoning it didn't do.

---

## 5. Test the other two front doors

**Telegram bot** (`python -m src.bot.telegram_bot`, backend must be
running): message it one question. Confirm the reply includes a `Sources:`
list (up to 3, with trust tiers) and a `⚠️ Note:` line specifically when
sources disagree — don't just confirm it replies at all.

**Frontend down / backend down handling:** stop the backend, refresh the
frontend, ask a question. Confirm you see "Could not reach the backend…"
rather than a broken page or an unhandled error in the browser console.
Small thing, but a crash here during a live demo is a bad look and costs
nothing to check now.

---

## 6. Submission-readiness checklist

Tied to the actual rubric (challenge doc section 6) and deliverables
(section 5) — not everything here is testable by running the app, but all
of it is checkable without more coding.

| Item | Status check |
|---|---|
| **Technical execution (25%)** — works end-to-end on unscripted input | Ask a question *not* in any sample/supplementary set, live. Does it still work? |
| **Human-AI collaboration (15%)** — evidence of directing, not one-shotting | `docs/decisions.md` and `docs/limitations.md` already read as a real debugging log (kept honest as you go) — confirm they're still current with today's findings. Chat logs exported (see below). |
| **Engineering best practices (15%)** — git discipline, reproducibility | `git log --oneline` reads as real incremental work, not one giant dump. A judge can `git clone` + follow `SETUP.md` alone — try this yourself on a clean checkout if you have time. |
| **Technical judgment (10%)** — trade-offs and failures documented | `docs/decisions.md` and `docs/limitations.md` cover the real trade-offs (model dead-ends, rate limits, chunk-id collisions, OCR gaps) — this is in good shape already. |
| **Impact & relevance (10%)** — convincingly addresses 1C + 1B | The demo should show one contested-fact question (1C) *and* one cross-document chain question (1B), not two of the same kind. |
| **Presentation (10%)** — video, docs, diagrams | `docs/diagrams/architecture.md` exists now. Confirm the video covers both claimed sub-tracks. |
| Mandatory: `ai_usage/ai-usage-disclosure.md` | Exists now — re-read it and make sure it's still accurate/complete as of your last work session. |
| Mandatory: exported AI chat logs as `.txt` in `ai_usage/` | **Not yet done as of this writing** — export before submission, and ideally after each significant session, not only once at the end. |
| `ai_usage/claude.md` | Copy the root `CLAUDE.md` here **right before zipping** for submission (not permanently — Claude Code needs it at the root to keep reading it during development). |
| `submission_report.pdf` (5 pages max) | Not yet written. Needs: YouTube link at the top, problem statement + sub-track, architecture diagram, key decisions, honest limitations, AI usage disclosure, team names/roles/contributions. |
| Demo video (10 min max, YouTube unlisted) | Not yet recorded. See `docs/demo_video_script.md` — already updated to use a real 1C question instead of a generic placeholder. |

---

## 7. If you only have time for one thing

Ask the system the two real 1C questions from `sample_questions.json`,
through the actual frontend, and read the Sources panel against the real
corpus files. That single check exercises the multi-hop loop, the trust
tiers, the contradiction layer, and citation accuracy all at once — it's
the closest thing to "will this hold up in front of judges" that a few
minutes of testing can tell you.
