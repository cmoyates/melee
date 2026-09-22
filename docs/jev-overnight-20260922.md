# Jev overnight work: September 21–22, 2026

Status: in progress. Deadline: **September 22, 8 AM Newfoundland time**
(`2026-09-22T10:30:00Z`). Authorized OpenRouter cap: **$1 total**.
PRs stay open for review; no merges are authorized by this goal.

## Starting point and order

Foundation PR #32 contains J01/J02 implementation and substantial J03–J05
runtime evidence. All issue statuses remain open pending acceptance/review.
New review slices stack on verified dependency branches instead of merging them.
The initial checkout was `ea74132b3425f3d18aefae39435e20c54af29982`.

The next independent slice is J08 (depends on J02), followed by the J09
latency experiment. In the runtime track, finish J04/J05 acceptance and J06
recording before J07 skills and J10 live asynchronous decisions.

## Evidence so far

- Refreshed J05 Battlefield run: `match-7a696e5de9794ea0b2721bf989fbf686`.
  Ten unattended matches, ten verified stage-31 replays, 9,610 observations,
  zero gaps/duplicates/rollbacks, 58.60–60.00 observed simulation FPS, successful
  neutralization and both owned processes stopped. This is the intentional
  stock-loss smoke policy, not Jev gameplay or a strength benchmark.
- J08: 66 local asset-free tests pass, including durable/concurrent spend
  reservations, corrupted journals, deadline/cancellation, HTTP failures,
  malformed distributions, candidate mutation and actual owned-child timeout.
- Two synthetic live adapter probes resolved to `typesafe/jev-1.13-20260917`
  through TypeSafe and selected `recover`; full stock/time state was included.
  Request times were 560.6 and 588.3 ms. Two samples are not a latency benchmark.
  Reported usage totals 1,058 input tokens, 62 output tokens and **$0.000044436**.
  No unknown charges remain for these probes.

## Durable local state

- `build/jev/overnight-20260922/goal.json`: original deadline/authorization.
- `build/jev/overnight-20260922/spend.jsonl`: shared append-only cost ledger.
- `build/jev/overnight-20260922/probes/`: immutable provider probe reports.
- `build/jev/overnight-20260922/battlefield-10.json`: sanitized live-run index.
- Raw replay/frame/runtime assets remain ignored below `build/jev/`.

Resume by reading this report, checking Git status and reading the existing
ledger. Do not reset the budget or repeat paid work merely to reconstruct state.
The two research markdown files remain the user's untracked files.
