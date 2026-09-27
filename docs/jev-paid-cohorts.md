# Paid cohorts keep their existing spending ledger

The [completed thirty-match cohort](jev-j19-cohort-results.md) passed its final
inspection with 1,999 reconciled provider requests. All policies were 0–10;
cumulative accounted spending was $0.313272330 of the original $1 cap. The
checkpoint evidence below is retained as history.

Issue #80 extends the checkpointed runner from #78 with explicit `jev` slots.
Free-only invocations remain credential-free. A mixed or paid cohort requires
both an existing ledger and a 1–200 request cap per Jev match:

```sh
uv run --project agent --env-file agent/.env --no-sync melee-agent batch start \
  --policies jev random-tactical heuristic-tactical --matches-per-policy 10 \
  --profile fox-aerial-v1 --match-seconds 600 --duration 21600 \
  --budget build/jev/EXISTING_CONSERVED_LEDGER --max-requests 200 \
  --max-new-matches 1 --previous-batch PRIOR_BATCH_ID
uv run --project agent --env-file agent/.env --no-sync melee-agent batch resume \
  BATCH_ID --max-new-matches 1
```

These commands never create, reset or continue a dollar allowance. The original
batch deadline must fit the supplied ledger's deadline. Admission requires a
remaining request, token reservation and dollar reservation; the ledger still
enforces every request. A cap is an upper bound, not a promise that the provider
can afford or complete that many calls. Once exhausted, ordinary local fallback
continues the match. Its frames and the actual provider participation remain in
the report; the entire match is not described as continuous model control.

Only the explicit paid supervisor receives the provider environment. Free
supervisors and the ordinary controller/emulator environment remain stripped.
The manifest pins the provider configuration, candidate profile and initial
ledger hash/accounting. Each launch intent records the exact current ledger
checkpoint. Each audit preserves the resulting append and requires its new
reservation IDs to match the child's recorded attempts exactly. Failed replies
now retain their reservation ID, including uncertain transport charges. Those
reservations are never refunded by the cohort runner.

Unexpected ledger writes, changed prefixes, missing attempt identities or
source/config revisions block automatic continuation. A finished paid child
can be adopted after a parent crash using its prior launch intent, recorded
identity and audited ledger append, without another API call. A reused sealed
incident supplies exact control replay; the bundle is hashed and included in
the artifact budget. Resume rechecks its retained files as well as the original
match recording. An ambiguous child remains pending and cannot be retried.

Paid completion additionally requires raw policy evidence, exact sealed replay,
valid stock rules/final result, accepted choices, at least one validated provider
response and observed provider/controller/emulator shutdown. A fallback-only
match cannot count as verified Jev participation. Mixed cohorts share the same
frozen code/profile/rules, but neither game RNG nor player sides are controlled
by this slice. It is J19 participation infrastructure, not the J20 held-out
strength tournament. At most twenty new matches launch per invocation; a
thirty-slot mixed schedule therefore needs a checkpoint/resume.

396 host tests pass. Coverage includes mixed checkpoints, uncertain charges,
crash adoption without re-spending, unexpected ledger appends and edited
prefixes, sealed/exhausted/missing-credential admission, changed provider config,
credential routing, fallback-only failure and reused/tampered sealed replay.
Provider tests also verify reservation identity survives malformed answers and
unknown transport charges. No real API request was made by these tests.
Agent-offline and native-build CI also pass. Repository-wide editorconfig still
reports 190 existing errors outside agent/docs; this is not fully green CI.

Native cohort `batch-17fa1c8b61fb4a2988cc42fb73e62b06` fixes ten rounds ordered
Jev/random/heuristic on `fox-aerial-v1`, with 600-second match caps and a six-hour
batch deadline. It links the prior free pilot and first stops after one paid
match. The existing exhausted request allocation was sealed and only its
$0.871503802 conservatively unspent balance carried forward. This plus the
$0.128496198 previously accounted remains the original $1, with all uncertain
reservations preserved. The child ledger allows at most 2,000 requests and
5,000,000 input tokens until 2026-09-27 10:30 UTC.

First child `match-ec61d1621b9e441b8f4c5b0f1a410c10` completed a 0-3 loss in
294.91 seconds. All 16,830 game frames passed raw integrity, raw policy evidence
and exact sealed replay, alongside stock rules/result and owned shutdown.
Its 199 requests produced 192 valid answers, three invalid distributions,
three deadline failures and one transport timeout. Every reservation matched
its recorded attempt, including the four uncertain charges. A separate
`batch inspect` reverified the checkpoint, source, ledger and replay hashes.

There were 119 accepted choices: 62 approaches, 48 short-hop Nairs, five
approach-jabs, two down tilts, one grab and one neutral. Raw acknowledgements
confirmed 61 completed movements, 43 completed Nairs, four completed options
with contact, two down tilts with contact and one grab capture. Seven accepted
skills were interrupted. Provider ownership was 2,274/16,830 frames (13.51%);
median/p95 source-to-reply latency across all 199 deliveries was 438.26/558.34 ms.
All valid answers resolved to `typesafe/jev-1.13-20260917` through TypeSafe.
These are execution measurements, not evidence that Jev is stronger.

The first match added $0.023237516 in conservative accounting: $0.015237516
reported plus $0.008 reserved for unknown charges. Cumulative accounting became
$0.151733714, including $0.020 uncertain across eight requests. Four ancestor
journals stayed unchanged after the intentional continuation seal. Private
replay: `incident-546722d9df8b455cb1ae7d9d0b954831`. Packet SHA-256:
`0686f0fc00572ebb8e8a8512fec1839e4795a1022283658eafc11c294371c698`.
The subsequent random and heuristic slots both completed 0-3 losses. Their
21,308 and 17,778 game frames replayed exactly, all native audits passed, and
each retained an unchanged before/after ledger checkpoint with zero reservations.
A separate inspection reverified the full first round: 55,916 game frames
across three matches, with all five spend journals unchanged during the free
slots. The cohort then continued under its original bounds. The ten-per-policy
J19 gate and the separate J20 tournament remain incomplete at this checkpoint.
