# Shared grounded tactical baselines

`heuristic-tactical` and `random-tactical` use the same ordered legal candidate
function as the grounded Jev policy and frozen corpus compiler. The profile is
`grounded-tactical-v1`: neutral, approach, retreat, jump, shield, jab, down-tilt
and grab. Aerials remain outside this slice. The historical `heuristic` and
`random-legal` modes retain their existing attack-focused selection behavior
and trace format; their old results are not relabeled as this profile.

The new random selector samples uniformly from every currently legal choice.
The deterministic heuristic prefers a legal grab against shield, otherwise a
legal jab or down-tilt, then a legal approach or neutral. All modes use the same
skill arbiter, emergency reflex and controller executor. Local choices occur
at most once per 60 simulation frames and apply on that frame; Jev requests
are wall-clock rate limited and incur actual provider latency. This difference
is explicit and is not presented as a latency-matched experiment.

Selections record the complete candidate set, chosen label, refusal, episode,
source and application frame, profile and seed. CLI runs use reproducible seed
zero; the policy constructor also accepts an explicit seed. Source hashes pin
the shared catalog in live manifests, sealed incidents and corpus compilation.
The new local modes never receive credentials or contact a provider.

```sh
rtk proxy uv run --project agent --no-sync melee-agent match --policy heuristic-tactical --duration 540
rtk proxy uv run --project agent --no-sync melee-agent match --policy random-tactical --duration 540
```

The configured per-run limit and artifact cap must cover the requested run.
Normal result-event and replay checks determine whether a full match completed;
a wall-clock stop with a partial match is not a completed comparison trial.

`melee-agent inspect RUN_ID --policy-evidence` replays local policy recordings
without network, emulator or controller writes. It requires the launch control
sources, recreates the recorded seed, and checks every decision, packet,
selection/reflex trace and final selector summary. It stops at the first
divergence; altered source identities fail before replay. Use the separate
`--integrity` audit for raw input, rules and result evidence. Exact replay on
historical observations is not a counterfactual simulation.

Host tests cover candidate parity for both directions, spacing, shielding and
invulnerability; the random selector can choose every legal tactic and retains
its seed; commitment/hitlag and damage preemption still use the shared executor.
Historical baseline selections and trace shape are preserved. All 305 host
tests pass, including local replay and corruption/source-identity checks.

## First complete live matches

Both profiles completed one unattended Fox versus Mario CPU 3 match on
Battlefield with four stocks and the eight-minute timer. Actual result events
and replay winners agreed; input/frame integrity, rules and owned-process
cleanup passed. Both runs used seed zero and made no provider calls.

| Profile | Run | Final stocks (Fox/Mario) | Replayed frames | Selections |
| --- | --- | ---: | ---: | ---: |
| Random tactical | `match-7f4fbf4e2a29477eaa574c96ff359daa` | 0 / 3 | 18,097 | 259 |
| Heuristic tactical | `match-d699d1c9360e467ea66a97687217b724` | 0 / 4 | 16,712 | 242 |

The reusable policy audit reproduced every recorded decision, packet,
selection/reflex trace and final summary with the launch sources unchanged.
Random frame SHA-256:
`b645b5d1b45f9600e9afba2dbc41b753c4299b6accafcedde24bce2bc81569d4`.
Heuristic frame SHA-256:
`4980ecba750c03e989332bb3143f9563775f1741ef62adaf4d92e14fed995a89`.
Private reports are retained as `RUN_ID-full-local-audit.json` in
`build/jev/continuation-20260926/`; the CLI can reproduce the policy and raw
integrity checks from each run directory on its matching checkout.

One match per profile is a tracer bullet, not a win-rate comparison or the
ten-full-matches-per-policy acceptance of #21. These runs did not exercise
Sudden Death; the separately reproduced lifecycle gap remains tracked in #60.
