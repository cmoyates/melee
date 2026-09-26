# Paid cohorts keep their existing spending ledger

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
Native paid checkpoint evidence is pending.
