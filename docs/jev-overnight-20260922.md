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

## J04 supervisor failure paths

80 offline tests pass. New tests exercise the actual supervisor with real owned
child processes, injected launch/scan/disk failures, corrupt result files and
an unrelated process that must survive. A completed run now also requires the
requested number of verified episodes and successful neutralization.

Two fresh Battlefield smoke matches completed with verified replays and no
frame gaps (`match-ca25892edc9e4e0c9f25968000f7d248`). Five additional live fault
runs verified SIGINT, killed worker, stopped worker/state stall, competing launch
rejection, and killed CLI cleanup. All owned children stopped; the unrelated
dummy survived every case. The killed/stopped workers correctly report unknown
neutralization, while orderly stops report successful neutralization. Subsequent
runs acquired the persistent lock after the previous owner's exit.

PID/PGID/exit status and summary hashes are retained in
`build/jev/overnight-20260922/j04-lifecycle.json`. Physical disk-full reporting is
necessarily limited to stdout if the summary cannot be persisted; the supervisor
returns failure rather than claiming durable completion.

## J06 raw observations and bounded recording

102 offline tests pass, including worker-level full/stalled-disk failures,
bounded queue/drain behavior, short writes, raw event boundaries, explicit native
ID mappings, action-frame normalization, corrupted traces and failed pipe flushes.

The ten-minute Battlefield capture `match-6710ce637a254072855df9cee65007e5`
finished cleanly at its deadline (601.15 seconds including cleanup). Its
independent integrity audit passed: **28,123 game frames, 31,936 total records,
30 episodes, zero gaps/duplicates/rollbacks, 117 observed Fox stock losses**.
There are 29 verified completed replays and one partial final replay with unknown
outcome. All accepted records were written, none rejected, and the sampled queue
high-water mark was one of 256. Trace size: 159,875,009 bytes. Controllers were
neutralized and both owned processes stopped. All 42 protected baseline files
remain unchanged.

Capture trace SHA-256:
`ebca3ba541a445632741a924882a37b007e3be852518fea56b3fa7947751b975`.
Summary SHA-256:
`1b905832760d7a5f559c21ac956413890aa2d2d74500fa69a2cbd33eef9b28cd`.
The launch manifest pins the source hashes used in this run; short-write and
corrupt-recorder-result guards were added afterwards. A fresh final-source match,
`match-1cb7190129044e77ad125e4c86d06b6a`, then completed with 961 game frames,
a verified replay and a passing integrity audit; its recorded source hashes
match the committed module contents. Retained integrity reports are `j06-final-match.json`, `j06-capture-600.json` and
`j06-input-probe.json` in the overnight evidence directory.

The controlled input probe `match-e54ace98f136408281686c26a8e73048` accounts
for all 244 game frames, including 123 countdown frames, and measures one frame
for all four right/neutral/left/neutral transitions. This is a measured transition
lag, not an inferred per-packet application receipt. Two earlier failed probes
exposed NumPy JSON values and the parser's remaining-stream buffer convention;
their artifacts are retained and both shut down cleanly. No provider calls were
made by this slice.

## J07 observed local skills

The first complete 20-repetition suite, `match-8674dfd5f2b74a659bd95c59706c5cbd`,
passed after **303.22 seconds across four Battlefield episodes**. It recorded
123 observed successes, 17 explicit state-dependent refusals and 13 separately
logged/retried interruptions, with zero timeouts. Each of seven skill/direction
groups reached 20 counted outcomes. All successful jumps showed three observed
jumpsquat frames. An independent raw-trace audit confirmed all 123 successes,
including input release; trace integrity passed for all 16,772 game frames.

| Skill | Successes | Refusals | Interruptions |
| --- | ---: | ---: | ---: |
| Neutral | 20 | 0 | 0 |
| Move left | 17 | 3 | 1 |
| Move right | 13 | 7 | 0 |
| Jump left | 19 | 1 | 0 |
| Jump right | 19 | 1 | 4 |
| Jump neutral | 19 | 1 | 2 |
| Shield | 16 | 4 | 6 |

The early runs exposed a real telemetry trap: Slippi's 0x2B field is reused by
other motions and only contains hitstun when its hitstun flag is set. The skill
adapter now gates the derived counter on that flag and preserves the original
value/flags in RawObservationV2. Landing is excluded from skill start conditions
after a trace showed a jump pressed too early being ignored and left held.
Failed runs remain retained, with clean shutdown evidence.

The final observation schema labels derived combat counters explicitly. The
final-source suite `match-013a7d9f350d4720a5d863f2c5282eaf` also passed:
129 observed successes, 11 explicit refusals, nine interruptions and zero
timeouts in 245.54 seconds over three episodes. All 13,570 game frames passed
integrity checks; all 129 successes passed the independent motion/release audit.
All 14,094 records drained, with queue high-water one. Source hashes match the
committed modules, all 42 protected files remain unchanged, and 119 offline
tests pass. Earlier development traces retain their original schema layouts
and exact source hashes.

Final evidence: `j07-final-full-suite.json`. Trace SHA-256:
`5723dd007d3fb5858208a67577d27fa430327bf50f22f96851a7453f90d090f2`.
Summary SHA-256:
`5648d4ae8e433f6c03b2ec496aeaa6ab3d18ce170d97e9f282fcf3e891fbca3d`.

First full-suite evidence: `j07-first-full-suite.json`. Trace SHA-256:
`3cfcb90f74dc70d0cb9dd49d357df6974bb69398273c9ae320e2a3e8784429f1`.
Summary SHA-256:
`e4a76ca0b76377453d7047263aac1d1788e97b672d6bcc7028ae42d8fd6f420b`.
No provider spending occurred in this slice. Movement/defense tests do not
establish recovery or competitive strength; the suite includes three CPU wins
and a partial final replay.

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
