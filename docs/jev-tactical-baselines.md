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
Historical baseline selections and trace shape are preserved. Live matches for
the two new modes remain pending. This preparation does not satisfy the
ten-full-matches-per-policy acceptance of #21 or claim any playing advantage.
