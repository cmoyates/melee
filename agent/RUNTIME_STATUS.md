# Autonomous emulator checkpoint

Verified locally on 2026-09-21. Implementation branch:
`jev/j01-workspace-doctor`; no roadmap issue is closed by this checkpoint.

## Available now

One command launches an isolated Slippi runtime, selects Fox on virtual
controller port 1 versus Mario CPU **level 3** on port 2, plays on
Battlefield, recognizes the recorded match result, retains the replay/frame
data, and shuts down. Multiple episodes return through character select without
manual input. The normal Dolphin and historical Showboat profiles are separate.

```sh
rtk proxy agent/.venv/bin/melee-agent match --policy scripted --duration 600
```

The command prints a run ID at startup and a JSON completion summary when done.
Use `melee-agent inspect RUN_ID` or `melee-agent stop RUN_ID` with that exact ID.
The [runbook](README.md#autonomous-local-matches) describes installation,
limits, artifacts and the three current policies.

## Live evidence

- Match-state regression: `match-c9e2e8991c87477ba5c64459f92c1706`.
  Two completed Battlefield matches with verified eight-minute/four-stock
  replay settings, **1,922 observations**, no gaps/duplicates/rollbacks, neutral
  cleanup and both owned processes stopped. Every schema-3 frame's policy
  observation (schema 2) matched the captured stock counts, including Fox's
  **4 → 3 → 2 → 1 → 0** transitions. Derived elapsed/remaining time followed
  simulation frames and reset at the next episode. This validates the state
  transport; it does not certify exact HUD timer reads or live timeout behavior.
- Current Battlefield regression: `match-3d484f42fb864d96aafa53e6eedbe8ea`.
  Two unattended episodes through the shared live/fake frame executor, two
  valid replays with stage ID **31**, and **1,922 observations** with no gaps,
  duplicates or rollbacks. All three static platforms are included in schema-2
  frame logs. This verifies the new stage and controller path; platform tactics
  themselves are not yet implemented.
- Ten unattended episodes: `match-b70ffb8319b4475788e1ef15195193d1`.
  Ten valid `.slp` replays, ten recorded GAME results, **10,085 observations**,
  zero frame gaps, duplicates or rollbacks. Observed simulation rate ranged
  from **58.78 to 59.99 FPS**, without fast-forward. Replay readback confirmed
  stock mode, 4 stocks, 8 minutes, items off, expected characters/ports/CPU level
  and Final Destination (the previous test stage). The smoke policy intentionally lost stocks; this
  establishes the harness, not bot playing strength.
- Three independent cold-launch input probes:
  `match-6f11f0e93ded42a5953a42a258c3c336`,
  `match-faedf819b66e45fabb9fd3e7645bb2a6`, and
  `match-dd8f1b33eb004411bc1c25cdec4643ba`.
  Right, left and neutral requests were observed at frames 1, 41 and 61 after
  requests on frames 0, 40 and 60. Both movement directions were verified.
  The locally retained certification binds all three summaries to the runtime
  executable hash. These deliberately short probes do not claim a match winner.
- Lifecycle failure injection: hard timeout, competing launch rejection,
  explicit stop, killed CLI, killed worker and a SIGSTOP-stalled worker. All
  owned emulator/controller processes exited, and an unrelated dummy process
  survived. After correcting the stop-exception interaction with multiprocessing,
  explicit stop and killed CLI also produced a successful neutral-input flush.
  Abruptly killed or stalled workers cannot promise neutralization; the
  supervisor terminates the owned emulator and reports that limitation.
- **47 asset-free tests** cover result parsing, malformed/truncated replays,
  unknown outcomes, rule mismatches, input acknowledgement versus movement,
  certificate tampering, process ownership, credentials and existing doctor checks,
  plus strict frame/decision/packet schemas, stale identities, clock rollback and
  an intentionally incorrect controller-output fixture. Match context checks
  cover countdown, stock loss, timer expiry, episode reset and malformed values.
  The deterministic fake
  trace covers the ground and all three Battlefield platforms.
- All **42 protected file fingerprints** remained unchanged: original and
  preserved stock DOLs, root build configuration/environment identity, Showboat
  profile and normal Dolphin controller/settings files.

Evidence is retained under `build/jev/runs/`, with failure-injection reports in
`build/jev/lifecycle-validation.json` and `build/jev/lifecycle-validation-v2.json`.
Private paths, raw captures, runtime binaries and game assets remain ignored.

## Boundaries and next work

The runtime is graphical Slippi Ishiiruka v3.6.4 using OpenGL. Headless macOS
operation and MP4 video capture are not established. `.slp` replays and JSONL
frame/controller data are available now.

The default scripted approach/attack/recovery policy is a placeholder. Jev via
OpenRouter, asynchronous decisions, durable personalities and the full skill
library remain later work. No provider calls were made during these checks.

This implements an initial live path through J03-J05 and part of J06, not every
acceptance condition in those issues. A dedicated asset-free fork CI workflow
now runs the shared executor and contract tests. An off-loop bounded writer,
disk-failure coverage, richer per-packet flush
provenance and wider lifecycle/long-run certification remain outstanding.
Artifact size is sampled once per second; it is not a strict filesystem quota.
The CLI watchdog handles parent disappearance, but a separately killed watchdog
itself cannot guarantee cleanup. Never bypass the existing-process check after
such a failure; inspect exact retained process identities first.

Runtime provenance and primary references are pinned in
[`runtime-lock.json`](runtime-lock.json). The authoritative replay field source
is the [Slippi replay specification](https://github.com/project-slippi/slippi-wiki/blob/master/SPEC.md).
