# Checkpointed free policy batches

Issue #78 adds `melee-agent batch start`, `resume` and `inspect`. A batch fixes
one candidate profile, source/config/runtime identity and a round-robin schedule
of `random-tactical` and `heuristic-tactical`. It uses the existing stock Fox
versus Mario CPU 3 setup on Battlefield, including its observed match lifecycle.
Game RNG is not seeded. This is baseline infrastructure, not a strength claim.

For a two-match checkpoint pilot:

```sh
uv run --project agent --no-sync melee-agent batch start \
  --matches-per-policy 1 --profile fox-aerial-v1 \
  --match-seconds 600 --duration 1800 --max-new-matches 1
uv run --project agent --no-sync melee-agent batch inspect batch-<printed-id>
uv run --project agent --no-sync melee-agent batch resume batch-<printed-id> \
  --max-new-matches 1
```

Each child receives an environment without API credentials and a parent-EOF
watchdog pipe. The batch accepts only free local selectors. Match time is bounded
at 30–600 seconds, with up to 30 additional seconds reserved for supervisor
cleanup. No new match starts unless that reservation fits the original batch
deadline; resuming never resets it. Final local artifact verification may finish
after the gameplay deadline. There are at most ten matches per policy, an 8 GiB
free-space floor and a 12 GiB cumulative recording budget, checked before each
launch alongside the existing per-match artifact limit.

An immutable manifest and append-only journal live under ignored
`build/jev/batches/<id>`. Launch intent is synced before spawning. Each retained
audit includes raw stream integrity, exact local control replay, stock rules,
final result, source identity and owned cleanup. Earlier recordings and audits
are hashed and rechecked before resuming. Wins/losses include only verified
complete matches; failures remain attempts and stop further launches.

A finished child can be adopted after a parent crash only from its single
recorded run identity, a free match lease and fresh artifact inspection. Missing,
ambiguous or still-owned evidence blocks automatic retry. A crash between audit
write and journal append is recoverable only if a fresh audit matches exactly.
Source changes require a separate cohort. `start --previous-batch <id>` links
the prior manifest without importing its results or changing it.

The old private cohort in `build/jev/baselines-20260926` remains separate: ten
completed losses plus one incomplete Sudden Death attempt. It is not resumed
with the later lifecycle, teeter and aerial changes. Its failure is preserved.

383 asset-free host tests pass, including 15 batch tests for ordered checkpoints,
crash recovery, failed-slot retention, changed source/artifacts, immutable
deadlines, metadata ambiguity, credential stripping, watchdog EOF and separate
cohort links. Native checkpoint/resume evidence is pending.
