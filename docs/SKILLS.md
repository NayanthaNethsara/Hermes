# Skills to Use for This Project

**This file belongs at:** `ai_usage/skills.md` (or keep a copy in `docs/`)

"Skills" here means the built-in Claude skills (used through Claude Code, Claude Desktop, or claude.ai) that add pre-built know-how for specific file types. You don't need to build these — just enable/use them when the moment calls for it.

---

## Skills worth using

| Skill | When to use it | Why |
|---|---|---|
| **pdf** | Writing `submission_report.pdf` | The report is a required PDF (max 5 pages). This skill knows how to build a clean, properly formatted PDF instead of a messy print-out of a Word doc. |
| **frontend-design** | While building the React UI | Gives design guidance (spacing, type, color choices) so the frontend doesn't look like a generic AI-generated template. Worth using early, not just at the end for polish. |
| **pptx** | Only if you choose to present with slides in the video | Not required — you can also just narrate over a screen recording. Use this only if the team decides slides are the better format for the pitch section. |

That's it. Don't go looking for more skills than this — the project doesn't need spreadsheet or Word-document skills, and adding tools you don't need just adds confusion.

---

## What NOT to add

- **No multi-agent frameworks** (CrewAI, AutoGen, LangGraph, etc.) as dependencies or skills. Three agents as plain Python functions is easier to build in two weeks, easier to debug, and easier to explain when judges ask you to walk through the code live.
- **No paid skills, plugins, or connectors.** Everything in this project must run on free tiers.

---

## Optional: a custom skill, if you have spare time

If the team finishes core features early (nice problem to have), one small custom skill worth building is a **submission-checklist skill** — something that, when run, checks:
- is `.env` missing from git (i.e., correctly ignored)?
- does the repo folder structure match section "Required repository structure" in `CLAUDE.md`?
- have chat logs been exported recently?

This isn't required and shouldn't be built before the core product works. Treat it as a stretch goal for days 12-13, not day 1.
