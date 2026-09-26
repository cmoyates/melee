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
cohort links. Agent-offline and native-build CI pass. Repository-wide
clang-format currently reports existing native/Showboat files outside this
change; this is not a completely green repository-wide CI result.

Native pilot `batch-03c15ea4fa8f49d4a244b032d04cc415` fixed two fresh matches
with `fox-aerial-v1` and 600-second caps. Its first random match,
`match-71f28b4e2dfd4ce793edb633da2e26c5`, completed a 0-3 loss in 286.84 seconds.
The runner audited all 16,320 game frames, exact control packets, raw integrity,
source identity, rules/result and owned cleanup, then stopped at its requested
one-match checkpoint. A separate `batch inspect` reverified the retained hashes.
All four spend journals matched the post-aerial-probe checkpoint. `batch resume`
then completed heuristic match `match-7471080391724c6a93fc481d665532d5`: a 0-3
loss in 436.91 seconds, with all 25,348 game frames replaying exactly. Both raw
audits, source/rules/result and cleanup checks passed. A final independent
`batch inspect` rechecked both results and their artifact hashes, reporting two
verified matches, two losses and zero failed attempts. Spending hashes remained
unchanged. The pilot proves the checkpoint workflow, not the ten-match J19 gate
or comparative strength. Its complete journal SHA-256 is
`2f745a47f189274736b327c6c4cc053346b2f5c40ce47bcd1c1220663d7a2488`.

The completed pilot recording supplied a third compatible session for aerial
corpus `corpus-98380674b9a740be9fe9d47a42960c7f`. All 4,959 states recompiled
exactly with network/process creation blocked: 3,301 training states and 1,658
tuning states, with no held-out episode. Sources include the prior paid capture,
free asynchronous match and this random match. Six provider and 58 simulated
replies are sparse historical annotations, not optimal-action labels. No new
evaluation, tuning or provider call was performed by this extraction.

States SHA-256: `3203508bae3b924830c30112a7073697fa86d546abf40338f4b391b65b929817`.
Manifest SHA-256: `c9e5847d84ed27fdf29eb5b19e830c89b90ffc9b3235b748b14274f0012d0548`.
