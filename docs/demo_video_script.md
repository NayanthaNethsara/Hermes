# Demonstration Video — Step by Step Script

**This file belongs at:** `docs/demo_video_script.md`

**Rules to remember:** max 10 minutes total. At least 3-4 minutes must be a live, unedited screen recording of the real system on real inputs. Upload to YouTube as **unlisted** (not public, not private). Paste the link at the top of `submission_report.pdf`.

---

## Before you record — checklist

- [ ] Real backend is connected (no mock data left in the demo build)
- [ ] Test the exact questions you plan to ask, on the actual running system, at least once beforehand — but the recording itself must show it running live, not a replay
- [ ] Close all other tabs, notifications off, phone on silent
- [ ] Screen recording software ready (OBS Studio is free)
- [ ] Have 2-3 backup questions ready in case your first pick gives a weak answer
- [ ] Do one full dry run with a timer before the real recording

---

## The script (10 minutes total)

### 0:00 – 0:30 — Hook
Say who you are (team name) and the one-sentence problem: enterprise documents are messy, contradictory, and spread across thousands of pages — finding a trustworthy answer is hard.

### 0:30 – 1:30 — The problem, and which sub-track
Explain Sub-track 1C in your own words: some questions need multiple search steps, not one lookup. Mention the corpus (Ashen Era Archive) and the detail that sources disagree with each other sometimes — this is your setup for the differentiator.

### 1:30 – 2:30 — Your idea, briefly
Show the architecture diagram (from `docs/architecture.md`) for about 15-20 seconds while you explain: an agent that searches, checks itself, searches again if needed, and flags when sources contradict instead of hiding it. Keep this short — the demo is more convincing than a slide.

### 2:30 – 2:45 — Transition line
Something like: "Let's see it actually do this, live, right now." Then switch to your screen.

### 2:45 – 6:45 (4 minutes) — LIVE, UNEDITED DEMO
This is the required live segment. Do not cut this part.

1. Open the app, show it's really running (empty chat, real UI)
2. Type a real multi-hop question, live (e.g. "Which other equipment is affected if component Y fails?")
3. While it's thinking, narrate what's happening: "Right now the Planner agent is deciding what to search for..."
4. Show the reasoning trace panel expand — point at each step as it appears
5. Show the final answer with sources and trust badges
6. Ask a **second** question, ideally one where two sources actually disagree, so the contradiction banner shows up on screen — this is your best visual moment, don't skip it
7. If you built the Telegram bot, quickly show the same question asked there too (10-15 seconds is enough)

### 6:45 – 8:15 — What's under the hood
Now that they've seen it work, explain briefly (can be narration over a diagram or the code):
- The 3-agent loop (Planner / Critic / Synthesizer) and why it's not just one prompt
- The trust tier system and why it matters for real enterprise documents (old vs. new manuals, conflicting SOPs)
- Keep this technical but not slow — judges have read your report for full detail, this is a highlight reel

### 8:15 – 9:15 — Honesty section
Say what didn't work, or what's still limited. Judges specifically reward this — it proves you actually built and tested, not just prompted once and got lucky. Example: "Our agent sometimes needs a 4th search round on very obscure questions, which slows it down" or "we chose not to handle images in this version, that's future work."

### 9:15 – 9:45 — AI usage note
One or two sentences: which AI tools you used, for what, and that full chat logs are included in the repo. Keep it matter-of-fact, not defensive — honest disclosure carries no penalty per the rules.

### 9:45 – 10:00 — Close
Thank you + team name again. Stop recording.

---

## After recording

- [ ] Watch the full video back once before uploading — check the live demo segment is actually unedited and actually shows real behavior
- [ ] Upload to YouTube, set visibility to **Unlisted**
- [ ] Copy the link, paste it at the very top of `submission_report.pdf`
- [ ] Double check total run time is under 10:00
