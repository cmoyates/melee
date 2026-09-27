# Explicit player-port schedules

Issue [#92](https://github.com/cmoyates/melee/issues/92) extends the audited batch
runner to exercise Fox on either controller port. Individual P2 native matches
already passed the role contract in #84; batch scheduling needs its own pilot.

```sh
# Four free matches: random and heuristic on P1, then both on P2.
uv run --project agent melee-agent batch start --bot-ports 1 2 \
  --policies random-tactical heuristic-tactical --matches-per-policy 1 \
  --profile fox-aerial-v1 --match-seconds 600 --duration 3000 \
  --max-new-matches 4

uv run --project agent melee-agent batch inspect BATCH_ID
uv run --project agent melee-agent batch report BATCH_ID --format markdown
```

The match count is per policy **on each selected port**. The frozen schedule
visits round, port, then policy in the declared order. Ports must be distinct
integers from 1 and 2. Explicit port schedules use manifest version 2. Omitting
the option retains the original version-1 P1 schedule; no old manifest, journal,
recording or public result file is rewritten.

The child command receives its assigned port. Launch, summary, audit and replay
roles must agree before a match can pass. Native winner ports remain native;
reports compare each winner with that match's bot port. Final stocks retain
canonical bot/opponent order. JSON and Markdown include per-port sample counts,
wins, losses and failures. Historical report output is version 2 and continues
to verify both manifest versions without using the current controller source.

Existing source freezes, immutable audit checkpoints, bounded matches, owned
cleanup, storage limits and no-retry handling of uncertain children remain in
force. Free children receive no provider credentials. An explicit Jev schedule
still requires an existing conserved ledger and a per-match request limit;
choosing another port never allocates additional money or extends a deadline.

All 455 dependency-free host tests pass. Coverage checks exact resume order,
P2 scoring, role mismatch rejection, credential isolation, historical
compatibility and paid ledger conservation. Explicit version-2 children must
record their role even when assigned P1; the legacy P1 default cannot fill a
missing role in a new schedule.

The historical thirty-match cohort
`batch-17fa1c8b61fb4a2988cc42fb73e62b06` was read through the new reporter.
Every prior per-match value, policy aggregate, source/runtime/artifact identity
and spending value remained identical; only explicit P1 role and per-port
reporting were added. The old retained result file was not rewritten.

The four-match native pilot is pending. A both-port development cohort is not a
held-out or RNG-paired tournament, and does not complete J20's thirty held-out
episodes per policy requirement. Native evidence for paid P2 cohorts is also
separate from the free scheduling pilot.
