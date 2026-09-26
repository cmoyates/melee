# Jev semantic observations and private decision corpus

J18 gives the existing asynchronous Jev policy a bounded snapshot of gameplay
meaning. Fox remains the controlled character, against Mario CPU level 3 on
Battlefield. The deterministic executor still owns input timing, legality,
recovery, interruptions and stale-response rejection. This slice changes the
representation; its original paid pilots used five movement/defense labels.
The later [grounded tactical slice](jev-grounded-tactics.md) adds jab, down-tilt
and grab. Aerial integration and complete-player acceptance remain later work.

## State contract

`CompactObservationV1` contains named native motions, positions and velocities,
relative spacing, facing, stage/platform geometry, stock counts and stock leader,
match duration and elapsed/remaining frame-clock time, jump/shield resources,
mechanical inhibition, the current skill phase, and ordered legal candidates.
The local compiler computes geometry and stock/damage comparisons. It computes
legality before rounding display values to three decimals.

Feature provenance is included in every state. Native IDs, stocks, grounded
flags and available hurtbox state are exact observations. Motion names,
normalized animation indices, comparisons and candidate legality are derived.
Static support surfaces and frame-clock time are estimates. Exact interruptible
frames, punish windows, collision outcomes and opponent intent remain unknown.
Missing replay hurtbox state is nullable, never assumed vulnerable.

History contains at most four earlier samples, spaced fifteen game frames apart.
It clears on a frame gap, episode change or bot life change. Current skill data
is an explicit whitelist, bound to the observed episode/life; no future result,
opponent future input or replay suffix enters the state. A corpus frame after a
gap also discards the previous skill commitment.

The snapshot is canonical JSON, capped at 16 KiB and stored immutably. The
inference worker receives that exact snapshot with its observation and candidate
order. Its SHA-256 joins the existing request context. Forged or mismatched
snapshot/candidate bindings are rejected before HTTP or reply application.
Frame recording retains the semantic state privately; mailbox entries contain
the digest instead of another full payload. Incident replay compares both the
semantic state and the controller decisions.

## Offline source and corpus contract

```sh
rtk proxy uv run --project agent --no-sync melee-agent corpus build --sources local --split-by episode
rtk proxy uv run --project agent --no-sync melee-agent corpus validate CORPUS_ID
```

The builder reads completed, cleaned-up local capture sessions, preferring paid
Jev and delayed-fake captures before local baselines and mechanical scenarios.
It writes only below ignored `build/jev/corpora/`. The default upper bound is
5,000 states from twelve sessions; CLI limits allow 1,000–10,000 states and
three–twenty-four sessions. Short sources may produce fewer states than the
requested maximum, which the report exposes.

Every selected state retains its source run/episode/frame and original record
digest. All frames are processed for history even when only some are sampled.
The deterministic split hashes the source run and episode together; neighboring
frames in an episode cannot cross train/tuning/held-out boundaries. Compiler
files, source frame files, summaries, candidate order and state-file hashes are
pinned in the manifest. Validation recompiles every case and compares the full
result, so updating a file hash alone cannot legitimize an altered state.

Recorded controller actions and delivered replies are separate annotations,
outside policy state. A reply identifies its earlier source frame, delivery
frame, model/request identity, acceptance/rejection and semantic digest when
available. Historical raw-state replies are explicitly marked as such. A reply
delivered on a sampled frame is not a label for that frame's compact state.
Neither a local controller action nor an old Jev choice is a correctness oracle.

Standalone owned Slippi replays use the same pinned raw extraction, observation
normalization and semantic compiler as live captures. That adapter opens the
file stream without creating an emulator, controller, profile or network socket.
It rejects unsupported matchup/rules and noncontiguous episode frames. Capture
schema 3 has an explicit adapter into schema 4; missing optional fields stay
unavailable. Current skill commitment cannot be recovered from a standalone
replay and is marked unknown.

## Evidence and remaining acceptance

The draft passed live-versus-replay comparison on 1,200 supported states from a
retained Battlefield match, with network and subprocess creation forbidden in
the parity harness. Golden tests cover native enum mappings, mirror symmetry,
full-precision range boundaries, hitlag/action indexing, stock/time arithmetic,
unknown fields, history causality and forged request/corpus bindings.

Payload reports include UTF-8 byte sizes and a rough bytes/4 token estimate.
That estimate is not the provider tokenizer or billed usage. Paid validation
must report the actual returned usage separately.

The ordered 1,000-state evaluation is now recorded below: all selected states
were attempted once, with 983 valid answers and seventeen retained refusals.
Sparse historical answers are separate annotations, not validation labels for
the new representation. Live semantic transport and complete incident replay
evidence are reported separately. No win-rate or personality-control claim
follows from these results.

The integrated host suite passes 267 tests. A ninety-second delayed-fake
Battlefield capture (`match-179d2cdf68234d3ebac9540b826135a9`) retained 4,803
game records at 59.59 observed FPS, with no missing, duplicate or rolled-back
frames. All 5,081 recorder rows were written, queue high-water was one, and the
worker/emulator/receiver stopped after neutralization with a valid replay.
Fifty-four simulated decisions were accepted; fifty-one skills completed with
raw acknowledgements and three were interrupted. No provider calls were made.
The policy audit, including source-snapshot hash checks, passed. Every semantic
state, decision and controller packet reproduced identically across the full
4,803-frame incident prefix. Packet SHA-256:
`1bcb3e63b2f6e41d54bd3109de9c5ab78a7b49c47b48303511b8c59169d312d0`.
This is a bounded capture and simulated-inference test, not a completed-match
or paid-policy strength result.

The 120-second paid pilot (`match-604a72e5167b446ba18d1f5f040e16b7`) retained
6,618 game records at 59.71 observed FPS with no gaps/duplicates/rollbacks. It
made forty HTTP calls: thirty-nine valid answers, twenty-five accepted decisions
and twenty-five raw-acknowledged skill completions (sixteen moves, three jumps,
four shields and two neutral releases). Nine replies were rejected after skill
generation changed, two after context changed, three for low confidence, and
one for exceeding its deadline. No invalid or expired decision was applied.
Provider ownership was 3.17% of all recorded gameplay frames; the forty-attempt
cap was reached during the capture, after which local fallback continued.

Successful replies had median source-to-reply latency 434 ms and median 1,751
billed input tokens. The verified model identity remained
`typesafe/jev-1.13-20260917`. Known charges were $0.002869776; one missing response
retains its full $0.002 reservation, for $0.004869776 accounted. Including the
earlier work and the frozen-state pilot, total accounted cost is $0.025554530 of
the original $1 cap. Both ledgers retain their uncertain reservations.

All 6,896 recorder rows were written with queue high-water one. The replay,
neutralization, process cleanup, integrity and policy audits passed. Complete
semantic/control incident replay matched all 6,618 game frames; packet SHA-256:
`1a0d2611f22cef36f1a30b6a20e11c1131e8ebad99a687155b107388be42d09e`.
Fox had three stocks and Mario four at the bounded end. The episode covered
110.83 observed seconds after setup, so the older J11 two-minute live-acceptance
field is correctly false. This is transport/integration evidence, not a full
match, playing-strength result, or satisfied 1,000-state evaluation gate.

## Ordered 1,000-state evaluation

On September 26, evaluation `evaluation-a4001c3a2aca4009aed30c97c4e156b9`
attempted 1,000 unique ordered states from
`corpus-5104654e16d645f28d040422cc73c4be`, once each, without retries. All
3,988 corpus states recompiled exactly before and after evaluation. Independent
checks matched every response to the selected source/frame/state digest and
verified the corpus, evaluation-code and response-file hashes.

There were 983 validated answers and seventeen `invalid_distribution_sum`
refusals. The CLI correctly returned `partial` and exit status 1 because some
answers were invalid, although all 1,000 selected states were attempted. Invalid
distributions were neither normalized nor retried. Every valid answer resolved
to `typesafe/jev-1.13-20260917`.

| Episode split | Attempted | Validated |
| --- | ---: | ---: |
| Train | 662 | 650 |
| Tuning | 209 | 205 |
| Held out | 129 | 128 |

Valid choices were approach 768, jump 102, down-tilt 85, grab sixteen, jab seven
and neutral five. Neither shield nor retreat was selected. These frequencies
describe this corpus and prompt; they are not correctness scores. There were
310 valid answers with confidence below 0.5. The frozen evaluator does not apply
these choices to a controller or claim they would pass live freshness/context
checks.

Valid reply latency was median 446.9 ms, p95 545.6 ms and maximum 1,434.0 ms.
Median billed input was 1,739 tokens; total billed input, including refused
answers, was 1,744,034 tokens. All 1,000 charges settled, totaling $0.073249428.
Across retained experiment ledgers, total accounted spend was $0.098803958 of
the original $1, including $0.008 in two earlier uncertain reservations. Budget
continuation transferred only remaining dollars; see the
[continuation contract](jev-budget-continuation.md).

Replay-only label agreement is unavailable: the corpus's thirteen historical
provider annotations and seventy simulated annotations all refer to an older
raw representation and their own source frames, with no compact-state binding.
There are zero eligible same-representation provider label pairs. Comparing
them to newly generated delivery-frame states would mislabel the evidence.
The live pilot above remains the separate applied-decision result; this frozen
evaluation launches no emulator and sends no controller inputs.

Response-file SHA-256:
`33119813d0bffd1a40887a6137dd113b846172618840ec48c7a3147e84aa25bd`.
Raw states, replies, usage journals and the independent audit remain private
under ignored `build/jev/`.

## Explicit paid frozen-state evaluation

```sh
rtk proxy uv run --project agent --no-sync --env-file agent/.env melee-agent corpus evaluate CORPUS_ID --budget EXISTING_BUDGET_DIRECTORY --max-requests 20
```

This command first validates the entire corpus, then selects evenly spaced
eligible states in source order. It sends each state once, at most one request
per second, with a three-second response deadline and the existing shared
spend/request/token ledger. It stops on budget refusal or provider backoff; it
does not retry failed states. The overall evaluation is bounded to one hour.
It sends the corpus's locally legal movement/defense/grounded-combat candidates;
these offline questions do not expand the live policy's action menu.

The evaluation retains its prompt, ordered candidate descriptions, source/code
hashes, each original state digest, returned model/usage, and response digest.
Source frame/episode stays fixed; the transport timestamp uses a new monotonic
lifetime so a host reboot cannot make old timestamps appear to be in the future.
Selection spans the corpus's existing splits without moving any state between
them. It separately reports reserved requests, actual transport submissions,
validated answers and refusals. Any incomplete evaluation reports `partial`
and exits nonzero. Provider choices remain model outputs, not correct labels;
live participation and match outcomes require a separate emulator run.

The first paid frozen-state pilot used corpus
`corpus-5104654e16d645f28d040422cc73c4be` and evaluation
`evaluation-ce1b9c4b6b9a4865b5487e7c8e87d5d2`. It submitted twenty states once,
validated nineteen answers, and rejected one `invalid_distribution_sum`.
Valid choices were twelve approaches, three jumps and four down-tilts. Successful
responses had median 419 ms latency, maximum 594 ms, and median 1,739 billed
input tokens. The model resolved to `typesafe/jev-1.13-20260917`; all twenty
charges settled for $0.001462356. These measurements were collected while the
independent aerial emulator suite was running, not under isolated latency-test
conditions. Response-file SHA-256:
`d7090ba6a9305e388c224195a606147647d602573c612536eee9c41df70c5faa`.

The corpus has 3,988 states from thirteen episodes, with 2,577 train, 880 tuning
and 531 held-out states. All recompile exactly. State size is 2,556–3,042 bytes
(median 2,916); the rough payload-only estimate of 729 tokens understates the
complete billed request above, which also includes question descriptions and
provider formatting. A 10,000-frame offline compiler profile measured median
0.121 ms, p95 0.156 ms and p99 0.200 ms for compilation/history/canonicalization
and wire decoding. It excludes source parsing, recorder I/O and other control
work, and is not an end-to-end FPS result.
