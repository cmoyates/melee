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

J08 is now open as [PR #33](https://github.com/cmoyates/melee/pull/33), stacked
on [PR #32](https://github.com/cmoyates/melee/pull/32). Its 66-test offline CI
passed. The repository style job still reports the same 190 errors in unchanged
Showboat files; this is separate from the dedicated agent CI.

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

## J09 cadence experiment

Run `3058b473279642809ca90f0a6d07cde1` tested 5/10/16 candidates, one/three
questions and 1/2/5 Hz submission rates. It achieved 100 validated responses in
128 attempts. Successful-response latency p50/p95/p99: **435/560/868 ms**.
Failures: **27 invalid distribution sums, one deadline**. The narrow five-choice,
single-question subset validated 22/22 calls. Requests used cold HTTP connections;
provider cache state is unknown, and this is not a gameplay benchmark.

| Target submission rate | Submitted | Validated | Validated responses/second |
| --- | ---: | ---: | ---: |
| 1 Hz | 40 | 32 | 0.803 |
| 2 Hz | 40 | 32 | 1.604 |
| 5 Hz | 40 | 30 | 3.636 |
| 1 Hz follow-up | 8 | 6 | 0.788 |

Three additional diagnostic calls captured a returned distribution totaling
0.99. This conflicts with the documented sum-one response contract; keep strict
rejection and local fallback rather than silently altering the probabilities.
Initial recommendation: **1 Hz, one in-flight request, one question, at most five
choices, maximum accepted age one second**. The local executor still owns reflexes.

The first summary combined the original 1 Hz phase and follow-up interval;
`analysis-v2.json` separates them and retains the original evidence unchanged.
72 local tests now pass, including independent-batch validation and phase accounting.

Cumulative overnight ledger after the benchmark/diagnostics: **133 requests,
$0.005140422 reported, $0.006 reserved for one unknown timed-out batch, and
$0.011140422 total accounted** against the $1 cap. Do not refund the unknown
reservation without verified billing evidence.

## Durable local state

- `build/jev/overnight-20260922/goal.json`: original deadline/authorization.
- `build/jev/overnight-20260922/spend.jsonl`: shared append-only cost ledger.
- `build/jev/overnight-20260922/probes/`: immutable provider probe reports.
- `build/jev/overnight-20260922/battlefield-10.json`: sanitized live-run index.
- `build/jev/overnight-20260922/benchmarks/3058b473279642809ca90f0a6d07cde1/`:
  immutable manifest/attempts/summary plus corrected phase analysis.
- `build/jev/overnight-20260922/distribution-diagnostic.json`: sanitized answers
  demonstrating the probability-sum mismatch.
- Raw replay/frame/runtime assets remain ignored below `build/jev/`.

Resume by reading this report, checking Git status and reading the existing
ledger. Do not reset the budget or repeat paid work merely to reconstruct state.
The two research markdown files remain the user's untracked files.
