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

Fresh free and paid live integration are pending. J16 and J17 retain their
incomplete strict clean-completion gates. This code is prepared in an isolated
checkout while the corrected combat scenario schedule runs; it does not close
complete-player issue #21, establish attack success under real provider latency,
or satisfy ten full matches per policy. The historical J18 frozen evaluation
and movement-only live pilots remain separate evidence.
