# EloJudge — UI Specification

Single-page flow, three states: **Input → Processing → Results**. Matches the pipeline and frontend-flow sections of the build plan.

---

## 1. Input screen

- Header: "EloJudge — turn messy feedback into a prioritized, explainable backlog"
- **Product context** textarea — helper text: "at least 20 characters"
- **Feedback** textarea, one item per line — helper text: "up to 20 items"
- **"Load demo data"** button (secondary) — pre-fills both fields with the QuickNote dataset
- **"Prioritize feedback"** button (primary) — triggers `POST /rank`
- Inline validation: context too short, fewer than 2 feedback items, more than 20 items

---

## 2. Processing screen

Shown while the request is in flight. Step list with checkmarks as each completes, spinner on the active step:

```
1/6 Filtering and cleaning feedback locally
2/6 Building your product rubric
3/6 Selecting top candidates
4/6 Running Swiss comparison — round 2 of 4
5/6 Updating Elo ratings
6/6 Building explainable roadmap
```

If the backend can't stream live progress, estimate step timing instead of leaving the screen static — a demo audience should never see a blank loading spinner with no context.

---

## 3. Results screen

- Title: **"Your prioritized backlog"**
- **Metrics bar:** submitted items, removed items, merged duplicates, clean items, tournament candidates, comparisons run, API requests used
- **Ranked cards**, grouped into three visually distinct tiers:
  - 🟢 **Now** (top rank)
  - 🟡 **Next** (mid rank)
  - ⚪ **Later** (remaining tournament candidates)
- Each card shows: rank #, feedback text, Elo score, win/loss record, one-line reason, and an expandable "why" section with match history
- **Source badge** on every judgment: `AI judgment` / `Local fallback` / `Demo dataset result` — never hide which one produced a given ranking
- **Cleaning summary panel** (collapsible) — what was filtered or merged, with example merged pairs (e.g. "app crashes on login" ← merged with "login screen keeps crashing")
- **Rubric panel** (collapsible) — dimensions and weights used
- **Lower-priority section** — items that didn't enter the tournament, clearly labeled "not fully compared," never mixed in with ranked results
- **"Run again"** button (secondary) — returns to Input screen with prior inputs preserved

---

## Component list

| Component | Notes |
|---|---|
| Textarea × 2 | Product context, feedback items |
| Button (primary/secondary) | Prioritize / Load demo / Run again |
| Progress step list | 6 steps, checkmark + active spinner |
| Metric badge row | Small stat chips across the top of results |
| Ranked card | Rank, text, Elo, W/L, reason, expandable history |
| Source-label badge | AI judgment / Local fallback / Demo dataset result |
| Tier header | Now / Next / Later — visually distinct at a glance |
| Collapsible panel | Cleaning summary, rubric |

---

## States to handle

- Empty input / validation error
- Loading (multi-step progress)
- Success (full ranked results)
- Partial failure — some judgments came from local fallback (must be visibly labeled, never hidden)
- Full failure — demo dataset result shown, clearly labeled as such
- "Load demo data" pre-fill state

---

## Visual priorities

Readable hierarchy and proof-of-computation over decoration. **Now / Next / Later** must be scannable in under 2 seconds — that's the first thing a judge's eyes will land on.

---

## Open question before implementation

The build plan's tech stack specifies plain HTML/CSS/JS served by FastAPI. An earlier Streamlit skeleton was also drafted for this project — confirm which one this UI should actually be built in, since the two require different implementations (Streamlit manages state for you; vanilla JS needs manual fetch calls and DOM updates against this spec).
