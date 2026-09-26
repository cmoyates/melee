# Grounded Jev tactical tracer bullet

This experimental J19 slice connects the existing grounded primitives to real
asynchronous choices. Its ordered label set is neutral, approach, retreat,
jump, shield, jab, down-tilt and grab. Every request contains only the locally
legal subset and the bound semantic snapshot. Descriptions and the neutral
stock-preserving objective are pinned in the provider configuration hash.
The aerial remains outside this label set.

The same frame executor still writes all controller packets. Responses retain
run/episode/life/generation/candidate/state identity, age, confidence,
commitment and current legality checks. The local primitive owns its one fresh
press, native acknowledgement, release and completion or conservative abort.
No model response may specify a raw controller action, duration or arbitrary
button. No new provider, retry policy or spending allowance is introduced.

The independent raw combat audit is shared with scenario trials. Its
`combat_outcomes` separates `motion_started`, `completed`, `contacts` and
`captures` per skill. An interrupted attack can have a verified native start
without a clean completion. A grab choice or grab motion is not a capture:
both native captor and captured motions must be present. Claimed damage
contacts require paired hitlag, actual percent increase and vulnerability.
Missing acknowledgement frames and duplicate contact claims fail the audit.

Full-match execution is available through the existing bounded supervisor:

```sh
rtk proxy uv run --project agent --no-sync --env-file agent/.env melee-agent match \
  --policy jev --duration 540 --episodes 1 --budget EXISTING_BUDGET_DIRECTORY --max-requests 60
```

The directory must be an existing, unsealed, unexpired ledger with remaining
request/token/dollar allowance. Reaching a request cap leaves the local fallback
in control; it does not create another budget or terminate evidence recording.
A full match is recognized only from the independent result event and replay.
The free delayed backend is also accepted by `match` for transport tests.

## Validation boundary

Host coverage crosses source snapshot, asynchronous reply, application, packet,
raw acknowledgement and exact sealed incident replay for all three attacks.
It checks interrupted starts, fabricated press/motion/release/capture evidence,
malformed primitive reports, apply-time range/invulnerability, unsupported
aerial labels, provider payload binding and full-match CLI budget forwarding.
Existing scenario raw evidence uses the same extracted auditor.

J16 and J17 retain their incomplete strict clean-completion gates. This slice
does not close complete-player issue #21 or satisfy ten full matches per
policy. The historical J18 frozen evaluation and movement-only live pilots
remain separate evidence.

## Initial live pilots

The 180-second free delayed/faulting pilot
`match-7605bdeace63452bb2c6714e7ea6905a` accepted 100 choices. Raw evidence
verified two completed jabs with two contacts, one completed down-tilt with one
contact, and three completed grabs with three paired captures. All 10,184 game
frames replayed exactly, with no gaps and clean recording/shutdown. Fox had
two stocks versus Mario's four at the bounded stop; this was a partial match.
Frames SHA-256: `b71bb3faac41ab5928384cd26ca8d3ce2e24e1457646e97d10042f77104846e0`.

The paid 180-second pilot `match-721bea4e5b0b4090bbcbbf719cad3bb0` made forty
HTTP calls: 39 validated responses and one deadline failure. Seventeen approach
choices were accepted and acknowledged; no attack was applied. Of four source
states offering combat, two responses chose approach but became stale, one
chose grab with confidence 0.13 and was correctly rejected by the unchanged
0.15 threshold, and one timed out. Other rejections were sixteen generation
changes and five context changes across the full run. Median response time was
445.5 ms. The provider owned 1.17% of recorded frames; the finite request cap
left the local fallback in control afterwards.

All 10,178 paid-pilot game frames replayed exactly. Raw integrity, rules/replay
settings, source hashes and cleanup passed, but the tactical participation gate
did not pass. Fox had three stocks versus four at the partial-match stop.
The pilot reported $0.002894220 and retained another $0.002 for the timed-out
request. Total accounted spend immediately after this pilot was $0.103698178
across the inherited $1 budget. Frames SHA-256:
`a9a1382740a262c833d0aeb6058f1210a9347611a763b7239a76006c23f97ae0`.

Private raw/replay reports are in `build/jev/continuation-20260926/` as
`RUN_ID-grounded-tactical-audit.json`. The extracted shared combat auditor also
passes all 120 retained corrected J16 trials; this supplemental check does not
replace that suite's original source-matched control replay.

## Full-match attempt and remaining blockers

`match-5e78a86dd6a64cc193a43cc139a70c26` attempted a full match with sixty
HTTP calls: 58 valid responses and two rejected distributions, all charges
settled for $0.004399164. It accepted and acknowledged 24 approach and twenty
neutral choices. Three attack choices were rejected after generation changes:
two followed damage reactions and one was overtaken by a local fallback move.
No real-latency attack executed.

The run exposed two blockers. Fox stood at the left platform's inner edge for
26,152 grounded Wait frames because both movement directions failed the normal
destination margin (#58). At the regulation timeout with four stocks each,
Melee entered Sudden Death directly in the in-game scene. The unhandled frame
reset to -123 caused the worker to stop cleanly with `status=incomplete` (#60).
The first replay's TIME placements are not a final contest winner.

All 28,924 retained regulation frames replay exactly. Whole-run integrity
correctly fails because the summary counted the rejected boundary observation,
changed its last frame and recorded a rollback. This is not a completed match
or a passing whole-run audit. The retained recording is 313,782,659 bytes;
recording and owned-process cleanup completed. Frames SHA-256:
`0f231aaa8d83018b4171c9b6ea978314793cf439fe38410df32136bc6258c36f`.

Accounted spending after both tactical experiments is $0.108097342, comprising
$0.098097342 reported cost and $0.010 retained for three uncertain older calls.
The active experiment's 1,100-request quota is exhausted; the original $1 global
cap remains in force. Future paid experiments require an explicit ledger
continuation that inherits only the remaining funds.
