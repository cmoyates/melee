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

## J10: delayed decisions and apply-time freshness

The five-minute `ordering-v1` Battlefield soak
`match-1e0d0239aa324bb08a0bda297a6a0544` passed both frame integrity and the
independent policy audit. It retained 17,121 game frames across two episodes,
five Fox stock losses, 417 submitted requests and 452 delivered replies.
All 131 accepted decisions were independently checked against source/current
observations; zero invalid applications were found. There were 154 out-of-order
deliveries and explicit forged-context, stale, invalid-choice and duplicate
rejections. Accepted labels: approach 23, retreat 22, jump 20, shield 35,
neutral 31. The local arbiter recorded 218 motion/release successes and ten
hitlag aborts across policy and fallback skills.

The four-worker limit held, peak mailbox depth was two, and all workers stopped
with zero remaining in-flight calls or replies. All 17,522 records drained,
with no gaps, duplicates, rollbacks or dropped records. Input was neutralized
and both owned processes exited. One CPU win and one partial replay were
retained; this is control-boundary evidence, not competitive strength.

| Timing | Delayed fake, 300 s | Scripted baseline, 60 s |
| --- | ---: | ---: |
| Simulation FPS | 59.78 / 59.93 by episode | 59.54 |
| Observed-to-queued p95 | 0.0909 ms | 0.0519 ms |
| Observed-to-flushed p95 | 12.3666 ms | 12.3386 ms |
| Observed-to-flushed p99 | 12.4950 ms | 12.5787 ms |

The baseline is `match-63aa8bfc671d4ebb9c7a06fc1216c658`. These are separate
game trajectories on the same runtime, not a controlled performance experiment.
Flush timing does not prove the exact game frame in which input was applied.

Evidence: `j10-fault-soak.json`, `j10-scripted-baseline.json`. Fault trace
SHA-256: `8bfd23eb0e883a800b5fd25a9aa9e6f757fb0aaccfa82e97360f11e5a9a6215a`.
Baseline trace SHA-256:
`30269ca3d3279faae246e77ef2b0983f533a5d79bb9bcd6af6a8f327e09c84b3`.
No provider calls occurred; the shared ledger remains at $0.011140422 accounted,
including its existing $0.006 uncertain reservation.

The final-source 60-second check `match-40dddd55d8194d5c91fa2e4dc4417577`
also passed: 3,012 game frames, 21 accepted choices, 28 reordered deliveries,
one observed commitment rejection and zero invalid applications. Its source
hashes match the final modules, both audits pass, all workers stop, and 133
offline tests pass. Evidence: `j10-final-fault-check.json`; trace SHA-256:
`a671fbf958654413fcb0220cfa7af2e2acc7053e6d05c4da06ceea37065ad651`.

## J11: real Jev choices in live Battlefield play

Two 150-second captures passed frame integrity, decision accounting and the
independent raw acknowledgement audit. Both had over 140 continuous seconds
in one episode, at least 20 observed policy completions and all four available
skill classes. No invalid choice was applied. Their final replay is partial;
neither capture establishes a completed match win or competitive strength.

| Evidence | First run | Repeat |
| --- | ---: | ---: |
| Game frames | 8,399 | 8,421 |
| HTTP returns / validated | 88 / 87 | 91 / 90 |
| Accepted decisions | 58 | 59 |
| Observed move / neutral / jump / shield | 46 / 4 / 3 / 1 | 40 / 4 / 2 / 8 |
| Interrupted accepted skills | 4 | 5 |
| Simulation FPS | 59.77 | 59.76 |
| Source-to-reply p95 | 485.06 ms | 518.77 ms |
| Observed-to-flushed p95 | 12.38 ms | 12.38 ms |

The other returns were rejected for changed skill generation/context or an
invalid probability sum (one per run). Every provider attempt has one recorded
outcome; no pending accepted skills remain. One HTTP request was in flight at
most. All inference workers, timers and HTTP exchanges stopped; both owned
processes exited and inputs were neutralized. All records drained with zero
gaps, duplicates, rollbacks or recording errors. 141 offline tests pass.

The repeat records input ownership explicitly: 471 provider-owned frames,
137 local-fallback frames, 5,831 idle/neutral frames and 1,982 emergency frames
(including countdown). Provider ownership is 5.59% of all game observations,
or 5.68% after countdown. Local behavior still accounts for most of play; this
slice proves useful live choices without claiming sustained tactical control.

Requested model: `~typesafe/jev-latest`; resolved model:
`typesafe/jev-1.13-20260917`, provider TypeSafe. Configuration SHA-256:
`ba493eef644befac9ce765395800fd89e89971b05aedf6a01c4ea7c85b55ed1e`.
The repeat's actuating/provider module hashes match its launch manifest; the
read-only audit was extended afterwards. All 42 protected baseline files remain
unchanged. No game assets, credentials or raw captures were published.

First run: `match-174cf2be0aac46a6a10e5db01310c189`, evidence
`j11-first-live.json`. Trace SHA-256:
`dde3c4275f1059090fae3a81f7eeb7c80853040c721bb4b265eeab631edf468c`.
Summary SHA-256:
`50f50eb4c79ef71132eab9f2d51fee0b77afaeed50805fe0fcfeeae8f7f89f67`.

Repeat: `match-a0bfc93878194bf1b39f2ccca20b3af4`, evidence
`j11-second-live.json`. Trace SHA-256:
`f3705e746ff8b888251a0b1a8b842d6f2aecc30ef458eaeba92a76c7fd961a9c`.
Summary SHA-256:
`1dc1be1cdb6ee3774e77f6eecc37608c6c20bc1db6cf9d4f1aa85e6169050733`.

The shared ledger now accounts for $0.019222398 against the $1 limit:
$0.013222398 reported plus the original $0.006 uncertain reservation. It records
312 requests and 410,819 accounted input tokens, leaving the original global
limits unchanged. The two J11 runs added no uncertain reservations.

## J12: runtime fault soak (validation in progress)

The first short network probe `match-181fbe552ea04d368e879cced61dcdb9`
passed with eight audited simulated choices while exercising disconnect,
429/529, invalid JSON/distributions, low confidence, cancellation, delayed
responses, circuit opening and recovery. No external HTTP transport or key was
available. Simulated ledgers are separate from the unchanged paid ledger.

The first full schedule `soak-0662d97a964446388b3d53da59449c27` stopped after
99.56 seconds at the controller-stall phase. Logger failure, executor failure
and worker death had passed, but blocked controller input exposed an unbounded
join in libmelee's receiver shutdown. The watchdog stopped the owned processes;
neutralization and the worker shutdown report were unavailable. This remains a
failed run and is not counted as certification.

The adapter now closes the owned receiver pipe before bounded joins and, if
necessary, termination/kill of the exact receiver process object. An actual
backpressured-pipe regression and an unresponsive-child regression pass. The
fixed Battlefield retest `match-2ac95779ff5a48e98ee3a2c154194df1` retained a
clean neutralization report and stopped the receiver without force, 16.19
seconds after the blocked write. Evidence: `j12-controller-fixed.json`.
The logger probe `match-43a1f8e4889c470cadb7e9fc8eb7d2fc` retained all 856
accepted records plus its rejected final record, neutralized input, and cleaned
up in 5.29 seconds. Evidence: `j12-logger-probe.json`.

155 offline tests pass. The restarted thirty-minute schedule
`soak-e2e03533731e428c99a20633dc9a5d4e` has passed all five terminal cases
and is running its longer network/frame-gap/rate-cap phases. Certification is
pending the complete schedule and aggregate evidence; do not infer a pass from
these intermediate results.

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
