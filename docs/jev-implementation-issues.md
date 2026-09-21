# Jev implementation issue specifications

GitHub roadmap: https://github.com/cmoyates/melee/issues/2

See [the plan](jev-implementation-plan.md) and [machine-readable manifest](jev-implementation-issues.json).

Parent roadmap: #2

# J01: Bootstrap an isolated agent workspace and machine-readable doctor

**Track:** Foundation — core

**Blocked by:** None — ready to implement.

## Outcome

One command tells a fresh coding-agent session exactly what it can run and what external prerequisite is missing.

## Scope

- Create agent/ with its own pinned Python/uv environment and console entry point `melee-agent`; preserve the decomp .venv and existing Showboat behavior. Prefer Python 3.12/3.13 subject to resolved dependency compatibility.
- Add ignored local configuration for asset/runtime paths and provider credentials; configure run duration, request/token/spend ceilings and offline-only environment. Doctor must not launch, install, or spend.
- Implement capability checks for matching stock DOL/full game assets, architecture, WiBo/toolchain, runtime, compiler, ports and credential presence (never values). Bootstrap downloads tooling only with pinned provenance; never downloads game assets.
- Write a scoped agent runbook: ready-issue selection, exact commands, expected artifacts, recovery from interruption, and staged implementation PRs. Existing interactive Showboat launch restrictions stay intact; new unattended runs use a separate owned profile.

## Acceptance

- [ ] Doctor JSON has schema version, pass/blocked/fail per capability, remediation, exit status; missing live dependencies do not prevent offline work.
- [ ] Reject wrong game version and config escaping the owned workspace; report no secret or machine username in public summaries.
- [ ] Run doctor twice without changing original DOL, Showboat profile, root build configuration or controller mappings.

## Acceptance commands to implement

```sh
uv sync --project agent --locked
uv run --project agent melee-agent doctor --json
```

## Execution contract

This is a small vertical slice in the Jev Melee plan. Commands below are proposed acceptance interfaces to implement. Use the parent tracker for shared architecture and the full dependency graph.

Keep original assets, existing Showboat behavior/profiles and source history intact. Measured play changes only ordinary controller input. Use owned runtime profiles/processes and explicit run/request/token/spend limits. No game assets, rebuilt binaries, keys or raw captures in GitHub artifacts. Removed local paths go to macOS Trash.

Close only with the stated checks, commit/config/runtime/model identity where relevant, sanitized artifact summary and any remaining limits. Mocks/host tests do not establish live gameplay success. Record blocked prerequisites explicitly; do independent ready work. Experimental improvements may be rejected based on valid measurements.

## Starting references

- [Checkout and Showboat handoff](https://github.com/cmoyates/melee/blob/b2195989e5c080fb37d4fb76471e2f5b40da257d/docs/showboat_handoff.md)

---

Parent roadmap: #2

# J02: Run a complete fake frame-to-controller slice in asset-free CI

**Track:** Foundation — core

**Blocked by:** [J01 #3](https://github.com/cmoyates/melee/issues/3)

## Outcome

A fresh checkout can execute and verify the same runtime orchestration without Dolphin, game assets or an API key.

## Scope

- Introduce only contracts needed by this slice: StateSource, ControllerSink, TacticalPolicy, monotonic clock and RunManifest; use typed versions and deterministic fake inputs.
- Drive observed state through a scripted decision and complete controller packet, archive the trace, and make one failure demonstrably fail the command.
- Add a dedicated fork CI workflow for this suite and relevant existing host tests; do not mistake upstream-only build jobs for this project's acceptance checks. Use synthetic fixtures and minimal permissions.

## Acceptance

- [ ] CI passes on cmoyates/melee without assets/secrets; an intentionally wrong controller output fails its assertion.
- [ ] Replay the same synthetic sequence twice and obtain identical decisions and packet hashes.
- [ ] Unexpected fields, NaN/Inf and wrong schema versions fail with useful diagnostics; missing live checks are marked blocked/skipped and never presented as passed.

## Acceptance commands to implement

```sh
uv run --project agent --no-sync melee-agent smoke --backend fake
uv run --project agent --no-sync python -B -m unittest discover -s agent/tests -v
```

## Execution contract

This is a small vertical slice in the Jev Melee plan. Commands below are proposed acceptance interfaces to implement. Use the parent tracker for shared architecture and the full dependency graph.

Keep original assets, existing Showboat behavior/profiles and source history intact. Measured play changes only ordinary controller input. Use owned runtime profiles/processes and explicit run/request/token/spend limits. No game assets, rebuilt binaries, keys or raw captures in GitHub artifacts. Removed local paths go to macOS Trash.

Close only with the stated checks, commit/config/runtime/model identity where relevant, sanitized artifact summary and any remaining limits. Mocks/host tests do not establish live gameplay success. Record blocked prerequisites explicitly; do independent ready work. Experimental improvements may be rejected based on valid measurements.

## Starting references

- [Checkout and Showboat handoff](https://github.com/cmoyates/melee/blob/b2195989e5c080fb37d4fb76471e2f5b40da257d/docs/showboat_handoff.md)

---

Parent roadmap: #2

# J03: Prove and pin a macOS Slippi/libmelee runtime with one input round trip

**Track:** First autonomous match — core

**Blocked by:** [J01 #3](https://github.com/cmoyates/melee/issues/3)

## Outcome

A reproducible runtime probe observes a live match frame and confirms a neutral/left/right input through the actual controller transport.

## Scope

- Probe the documented macOS-compatible Slippi candidates with the current libmelee fork; existing stock /Applications/Dolphin.app is not proof of compatibility. Start from stock US1.02 assets, not the shifted Showboat DOL.
- Pin runtime source/release, checksum, architecture, libmelee commit/package and adapter settings. Try Ishiiruka first per current upstream guidance; use a source-built nogui candidate if needed. Keep a bounded candidate log rather than silently changing platforms.
- Record actual Console.step/flush ordering, stick normalization, menu/in-game frame semantics, input acknowledgement and blocking-input behavior. Retain a diagnostic screenshot/frame dump where supported.
- Use a uniquely owned profile and bounded child process for the probe. No global installs/profile changes or existing-process termination. If all local candidates fail, leave a concrete compatibility blocker and continue independent offline/provider work.

## Acceptance

- [ ] Live state and changed movement/input are observed, not merely successful pipe writes; repeat three cold launches.
- [ ] Measure simulation-frame progress against monotonic time at real-time speed and document input application delay; no fast-forward results labeled real-time.
- [ ] Probe exits within its timeout and leaves no owned child; fingerprint normal Dolphin and Showboat settings before/after.
- [ ] Record supported graphical/headless modes rather than assuming Null graphics implies headless operation.

## Acceptance commands to implement

```sh
uv run --project agent melee-agent runtime probe --profile local-v1 --duration 30 --json
```

## Execution contract

This is a small vertical slice in the Jev Melee plan. Commands below are proposed acceptance interfaces to implement. Use the parent tracker for shared architecture and the full dependency graph.

Keep original assets, existing Showboat behavior/profiles and source history intact. Measured play changes only ordinary controller input. Use owned runtime profiles/processes and explicit run/request/token/spend limits. No game assets, rebuilt binaries, keys or raw captures in GitHub artifacts. Removed local paths go to macOS Trash.

Close only with the stated checks, commit/config/runtime/model identity where relevant, sanitized artifact summary and any remaining limits. Mocks/host tests do not establish live gameplay success. Record blocked prerequisites explicitly; do independent ready work. Experimental improvements may be rejected based on valid measurements.

## Starting references

- [Current libmelee setup and macOS caveat](https://github.com/vladfi1/libmelee/blob/bce21f09984b286e6d36bfd2939e4cd4691f94c2/README.md)
- [Inspected libmelee frame/transport implementation](https://github.com/vladfi1/libmelee/blob/bce21f09984b286e6d36bfd2939e4cd4691f94c2/melee/console.py)

---

Parent roadmap: #2

# J04: Supervise owned emulator runs with locks, watchdog and recoverable cleanup

**Track:** First autonomous match — core

**Blocked by:** [J03 #5](https://github.com/cmoyates/melee/issues/5), [J02 #4](https://github.com/cmoyates/melee/issues/4)

## Outcome

An agent can launch, interrupt, inspect and resume a test run without harming an unrelated game or leaving stuck input.

## Scope

- Promote the probe launcher into a RunSession with unique run ID, exclusive profile/port lease, process identity and external watchdog. Verify identity before signaling; don't kill by process name.
- On normal stop release all inputs and flush before bounded teardown; on a hung/killed controller worker the supervisor ends only the owned emulator. Record why neutralization was impossible if the pipe is gone.
- Retain launch/completion manifests, hashes, stderr, exit and timeout reasons. Audit libmelee cleanup: disable its temporary-home deletion path and use owned persistent run profiles; removed paths go to absolute-path /usr/bin/trash.
- Reject concurrent profile use and symlink/path escapes; never stage a DOL into an active run. Enforce per-run runtime and local artifact-size budgets.

## Acceptance

- [ ] SIGINT, startup failure, stalled state, abrupt worker death and two competing launches all terminate/reject predictably.
- [ ] An unrelated dummy process/profile survives all shutdown cases; exact owned PID/process group and final input status appear in evidence.
- [ ] A stale lock is recovered only after proving its owner has exited; a live owner cannot be stolen.
- [ ] No permanent deletion by our runner or library cleanup; disk-cap exhaustion preserves failure evidence.

## Acceptance commands to implement

```sh
uv run --project agent melee-agent run --policy scripted --duration 30
uv run --project agent melee-agent stop --run-id RUN_ID
uv run --project agent pytest -m lifecycle
```

## Execution contract

This is a small vertical slice in the Jev Melee plan. Commands below are proposed acceptance interfaces to implement. Use the parent tracker for shared architecture and the full dependency graph.

Keep original assets, existing Showboat behavior/profiles and source history intact. Measured play changes only ordinary controller input. Use owned runtime profiles/processes and explicit run/request/token/spend limits. No game assets, rebuilt binaries, keys or raw captures in GitHub artifacts. Removed local paths go to macOS Trash.

Close only with the stated checks, commit/config/runtime/model identity where relevant, sanitized artifact summary and any remaining limits. Mocks/host tests do not establish live gameplay success. Record blocked prerequisites explicitly; do independent ready work. Experimental improvements may be rejected based on valid measurements.

## Starting references

- [Checkout and Showboat handoff](https://github.com/cmoyates/melee/blob/b2195989e5c080fb37d4fb76471e2f5b40da257d/docs/showboat_handoff.md)
- [Inspected libmelee frame/transport implementation](https://github.com/vladfi1/libmelee/blob/bce21f09984b286e6d36bfd2939e4cd4691f94c2/melee/console.py)

---

Parent roadmap: #2

# J05: Automate local match setup, result detection and the next match

**Track:** First autonomous match — core

**Blocked by:** [J04 #6](https://github.com/cmoyates/melee/issues/6)

## Outcome

One command starts the chosen local matchup, finishes it, and starts the next episode without human menu input.

## Scope

- Use libmelee menu-state helpers and explicit controller roles to choose character, CPU opponent, stage, items-off stock rules and start; verify every setting from observations or a documented config readback.
- Use Fox versus Mario CPU level 3 on Battlefield, as selected by the user. Bot port is human/virtual-controller controlled; CPU opponent is a different port. Showboat Falcon remains a separate baseline.
- Handle boot, CSS, stage select, game, results, reset and errors with state-based timeouts; never navigate public matchmaking.
- Assign new episode/session generations across starts/resets. Persist exact settings and unknown/timeout/aborted outcomes. Prefer fresh starts over savestates initially.

## Acceptance

- [ ] Ten unattended episodes complete setup, gameplay and results-to-next-match transitions with zero manual clicks.
- [ ] Wrong character/port/stage/rules, menu stalls and premature exit are detected and fail the run.
- [ ] Artificially late previous-episode work cannot affect the next match; outcome reporting distinguishes actual result, timeout and unknown.
- [ ] Normal user and Showboat controller profiles remain unchanged.

## Acceptance commands to implement

```sh
uv run --project agent melee-agent match --policy scripted --episodes 10 --profile local-v1
```

## Execution contract

This is a small vertical slice in the Jev Melee plan. Commands below are proposed acceptance interfaces to implement. Use the parent tracker for shared architecture and the full dependency graph.

Keep original assets, existing Showboat behavior/profiles and source history intact. Measured play changes only ordinary controller input. Use owned runtime profiles/processes and explicit run/request/token/spend limits. No game assets, rebuilt binaries, keys or raw captures in GitHub artifacts. Removed local paths go to macOS Trash.

Close only with the stated checks, commit/config/runtime/model identity where relevant, sanitized artifact summary and any remaining limits. Mocks/host tests do not establish live gameplay success. Record blocked prerequisites explicitly; do independent ready work. Experimental improvements may be rejected based on valid measurements.

## Starting references

- [libmelee menu automation](https://github.com/vladfi1/libmelee/blob/bce21f09984b286e6d36bfd2939e4cd4691f94c2/melee/menuhelper.py)
- [Checkout and Showboat handoff](https://github.com/cmoyates/melee/blob/b2195989e5c080fb37d4fb76471e2f5b40da257d/docs/showboat_handoff.md)

---

Parent roadmap: #2

# J06: Capture trustworthy per-frame observations and applied controller provenance

**Track:** First autonomous match — core

**Blocked by:** [J05 #7](https://github.com/cmoyates/melee/issues/7)

## Outcome

Every runtime decision can be traced back to an identified observation and the packet actually sent.

## Scope

- Implement RawObservationV1 from live libmelee with run/episode/frame/monotonic time, port and spawn/life identity; preserve raw IDs plus explicit enum mappings and availability flags.
- Include positions, grounded state, action/frame, velocities, stocks/percent, hitlag/hitstun, jumps and stage geometry where available. Declare exact, derived and unknown fields; don't silently equate native IDs to libmelee IDs.
- Record attempted packet, flush time, observed input acknowledgement where available and known application lag. Count duplicate/gapped/rolled-back frames explicitly.
- Use bounded off-loop JSONL writing and immutable run manifests. Reuse Showboat provenance concepts; its interval-12 samples are not a 60-Hz state source and v1 samples remain quarantined.

## Acceptance

- [ ] Ten-minute capture has every expected frame accounted for as observed or an explicit gap; resets and negative menu/countdown frames are handled.
- [ ] Cross-check controlled grounded/airborne, movement and stock transitions against game observations.
- [ ] Golden fixtures catch native/libmelee character/stage/action mapping and off-by-one action frames.
- [ ] Disk stall/full and slow logger cannot silently back up state or block control; run degrades or stops with a recorded reason.

## Acceptance commands to implement

```sh
uv run --project agent melee-agent capture --duration 600 --profile local-v1
uv run --project agent melee-agent inspect RUN_ID --integrity
```

## Execution contract

This is a small vertical slice in the Jev Melee plan. Commands below are proposed acceptance interfaces to implement. Use the parent tracker for shared architecture and the full dependency graph.

Keep original assets, existing Showboat behavior/profiles and source history intact. Measured play changes only ordinary controller input. Use owned runtime profiles/processes and explicit run/request/token/spend limits. No game assets, rebuilt binaries, keys or raw captures in GitHub artifacts. Removed local paths go to macOS Trash.

Close only with the stated checks, commit/config/runtime/model identity where relevant, sanitized artifact summary and any remaining limits. Mocks/host tests do not establish live gameplay success. Record blocked prerequisites explicitly; do independent ready work. Experimental improvements may be rejected based on valid measurements.

## Starting references

- [Checkout and Showboat handoff](https://github.com/cmoyates/melee/blob/b2195989e5c080fb37d4fb76471e2f5b40da257d/docs/showboat_handoff.md)
- [Inspected libmelee frame/transport implementation](https://github.com/vladfi1/libmelee/blob/bce21f09984b286e6d36bfd2939e4cd4691f94c2/melee/console.py)

---

Parent roadmap: #2

# J07: Execute observed movement, jump and shield skills through one controller owner

**Track:** First autonomous match — core

**Blocked by:** [J06 #8](https://github.com/cmoyates/melee/issues/8)

## Outcome

The bot reliably moves, jumps, shields and returns to neutral using state-aware local skills.

## Scope

- Implement neutral, move/dash toward/away, jump and bounded shield as small interruptible state machines with can_start/step/continue/abort/timeout contracts.
- One arbiter owns a complete controller packet each frame, including released buttons and centered unused sticks/triggers. Current skill commitment is explicit; network code cannot write input.
- Use observed motion transitions instead of blind frame recordings. Verify Fox-specific movement and jumpsquat timings; local emergency/termination priority precedes tactical replacement.
- An externally controlled player has no native CPU fallback. Its fallback is local safe behavior and eventual run termination on lost observation; do not claim Showboat's native recovery is inherited.

## Acceptance

- [ ] Each skill succeeds in 20 controlled repetitions in both directions where applicable, or records a specific state-dependent refusal.
- [ ] Hitlag/hitstun, death/respawn and skill timeout abort/transition without latched inputs or two writers.
- [ ] Expected motion is acknowledged before success; sending a packet alone is not success.
- [ ] Injected missing frames cannot advance a blind sequence as though all frames were observed.

## Acceptance commands to implement

```sh
uv run --project agent melee-agent skill-check --suite movement-v1 --repeats 20
```

## Execution contract

This is a small vertical slice in the Jev Melee plan. Commands below are proposed acceptance interfaces to implement. Use the parent tracker for shared architecture and the full dependency graph.

Keep original assets, existing Showboat behavior/profiles and source history intact. Measured play changes only ordinary controller input. Use owned runtime profiles/processes and explicit run/request/token/spend limits. No game assets, rebuilt binaries, keys or raw captures in GitHub artifacts. Removed local paths go to macOS Trash.

Close only with the stated checks, commit/config/runtime/model identity where relevant, sanitized artifact summary and any remaining limits. Mocks/host tests do not establish live gameplay success. Record blocked prerequisites explicitly; do independent ready work. Experimental improvements may be rejected based on valid measurements.

## Starting references

- [Checkout and Showboat handoff](https://github.com/cmoyates/melee/blob/b2195989e5c080fb37d4fb76471e2f5b40da257d/docs/showboat_handoff.md)
- [Inspected libmelee frame/transport implementation](https://github.com/vladfi1/libmelee/blob/bce21f09984b286e6d36bfd2939e4cd4691f94c2/melee/console.py)

---

Parent roadmap: #2

# J08: Integrate Jev behind a deadline-aware typed adapter and mock transport

**Track:** Jev connection — core

**Blocked by:** [J02 #4](https://github.com/cmoyates/melee/issues/4)

## Outcome

A canned observation yields a validated tactical decision through the same API boundary used live.

## Scope

- Use OpenRouter as requested by the user, with OPENROUTER_API_KEY loaded privately from agent/.env. Put a bounded asynchronous OpenRouter transport behind the provider-neutral tactical contract. Verify which structured-output and probability fields the selected route actually supports; never assume native TypeSafe Choice/confidence fields survive this transport.
- Set explicit transport and end-to-end deadlines and disable automatic retries/fallback replay for stale tactical requests. Apply Retry-After/backoff to future fresh submissions, not the expired snapshot.
- Bound request size/in-flight count and reserve token/request/spend budget before submission. Track uncertain billing for timed-out calls conservatively. No keys in arguments/logs/manifests.
- Require an explicit verified OpenRouter model ID and record resolved model/provider identity. The public OpenRouter catalog checked on 2026-09-21 had no Jev/TypeSafe entry; obtain the intended private model ID or resolve this live prerequisite before claiming Jev access. Keep provider-specific types out of the game executor.
- Represent unavailable probabilities/confidence as unavailable. Do not fabricate a Choice distribution from generated text or treat token log probabilities as calibrated tactical probabilities. Downstream calibration/personality sampling must explicitly handle the actual route capabilities.

## Acceptance

- [ ] Mock transport covers valid Choice, wrong answer type, unknown/missing labels, malformed/nonfinite probabilities, missing model, 401/403/429/529, timeout and cancellation.
- [ ] Wrong responses never reach ControllerSink; cancellation releases resources without unbounded workers.
- [ ] Rate/cost caps hold under concurrent calls and errors; default retry cannot secretly double requests.
- [ ] Offline adapter tests need no key. Missing credentials produce actionable blocked live status. Secure credential provisioning and the live smoke belong to J09 and do not block closing this offline adapter slice.

## Acceptance commands to implement

```sh
uv run --project agent pytest -m jev_adapter
```

## Execution contract

This is a small vertical slice in the Jev Melee plan. Commands below are proposed acceptance interfaces to implement. Use the parent tracker for shared architecture and the full dependency graph.

Keep original assets, existing Showboat behavior/profiles and source history intact. Measured play changes only ordinary controller input. Use owned runtime profiles/processes and explicit run/request/token/spend limits. No game assets, rebuilt binaries, keys or raw captures in GitHub artifacts. Removed local paths go to macOS Trash.

Close only with the stated checks, commit/config/runtime/model identity where relevant, sanitized artifact summary and any remaining limits. Mocks/host tests do not establish live gameplay success. Record blocked prerequisites explicitly; do independent ready work. Experimental improvements may be rejected based on valid measurements.

## Starting references

- [TypeSafe HTTP API](https://docs.typesafe.ai/api)
- [TypeSafe async Python client](https://docs.typesafe.ai/sdk/python/api/clients/async)
- [TypeSafe retry controls](https://docs.typesafe.ai/sdk/python/api/retries)
- [TypeSafe model versions and limits](https://docs.typesafe.ai/models)

---

Parent roadmap: #2

# J09: Benchmark Jev from this machine and select an honest initial cadence

**Track:** Jev connection — core

**Blocked by:** [J08 #10](https://github.com/cmoyates/melee/issues/10)

## Outcome

A budgeted benchmark establishes actual response-age expectations before gameplay claims.

## Scope

- First verify the intended Jev model is available through the configured OpenRouter route. A present token or a generic OpenRouter model is not proof of Jev access. Record a concrete compatibility blocker if the route is unavailable.
- Run canned compact states with 5/10/16 action alternatives and single versus small independent-question batches, bounded by a hard token/request/cost limit.
- Collect p50/p95/p99 end-to-end latency, failures, token use, resolved model and confidence; record warm/cold connection status and geographic host context without exposing private details.
- Select initial cadence, maximum concurrent requests and semantic decision horizons from measurements. Report submitted/completed/accepted rates separately; don't promise 10 useful decisions/s from marketing latency.
- Offline mocks remain usable if the account is unavailable; live acceptance remains blocked until measured. Do not infer successful account access from public docs.

## Acceptance

- [ ] At least 100 successful calls plus all failed attempts appear in a reproducible report within the declared cap.
- [ ] Run a small 1/2/5 Hz sweep subject to service limits; explain sustainable cadence and freshness budget.
- [ ] Spend ledger reconciles reported usage, reservations and unknown timed-out usage.
- [ ] Record a concrete proceed/reduce-cadence/block decision; slow service is an experimental finding, not a fake passing gameplay test.

## Acceptance commands to implement

```sh
uv run --project agent melee-agent jev benchmark --suite initial --max-requests 150 --max-input-tokens 300000
```

## Execution contract

This is a small vertical slice in the Jev Melee plan. Commands below are proposed acceptance interfaces to implement. Use the parent tracker for shared architecture and the full dependency graph.

Keep original assets, existing Showboat behavior/profiles and source history intact. Measured play changes only ordinary controller input. Use owned runtime profiles/processes and explicit run/request/token/spend limits. No game assets, rebuilt binaries, keys or raw captures in GitHub artifacts. Removed local paths go to macOS Trash.

Close only with the stated checks, commit/config/runtime/model identity where relevant, sanitized artifact summary and any remaining limits. Mocks/host tests do not establish live gameplay success. Record blocked prerequisites explicitly; do independent ready work. Experimental improvements may be rejected based on valid measurements.

## Starting references

- [TypeSafe model versions and limits](https://docs.typesafe.ai/models)
- [TypeSafe HTTP API](https://docs.typesafe.ai/api)
- [TypeSafe retry controls](https://docs.typesafe.ai/sdk/python/api/retries)

---

Parent roadmap: #2

# J10: Keep the live frame loop running under delayed and reordered policy results

**Track:** Jev connection — core

**Blocked by:** [J07 #9](https://github.com/cmoyates/melee/issues/9), [J08 #10](https://github.com/cmoyates/melee/issues/10)

## Outcome

The actual game continues on local skills while fake inference stalls, returns out of order or describes an obsolete situation.

## Scope

- Isolate synchronous libmelee stepping and controller writes from async HTTP work; choose a thread/process boundary that preserves a single controller owner and bounded shutdown.
- Maintain latest observation with no backlog and a configurable in-flight cap. Bind results to run/episode/life/context, source frame, request sequence, candidate-set hash and skill generation.
- Validate current legality plus both monotonic age and frame age at apply time. Newer request submission alone must not starve otherwise valid results; stale queue items are never played back to catch up.
- Preserve useful skill commitments with hysteresis; emit a reason for every acceptance/rejection. Use a watchdog for blocked pipe/state calls, not merely an async timer in the blocked loop.

## Acceptance

- [ ] In a five-minute live run with mocked 0–2000 ms delays, duplicate/reordered replies and respawns, zero invalid/stale/wrong-generation decisions are applied.
- [ ] Local frame progress continues during HTTP stalls; measure game-speed and observed-to-flushed latency against the scripted baseline.
- [ ] At most the configured in-flight tasks exist, no unbounded pending-state queue, no leaked tasks after shutdown.
- [ ] Noninterruptible skill boundaries and emergency override are covered by deterministic tests and observed trace evidence.

## Acceptance commands to implement

```sh
uv run --project agent melee-agent match --policy delayed-fake --fault-suite ordering-v1 --duration 300
uv run --project agent pytest -m scheduler
```

## Execution contract

This is a small vertical slice in the Jev Melee plan. Commands below are proposed acceptance interfaces to implement. Use the parent tracker for shared architecture and the full dependency graph.

Keep original assets, existing Showboat behavior/profiles and source history intact. Measured play changes only ordinary controller input. Use owned runtime profiles/processes and explicit run/request/token/spend limits. No game assets, rebuilt binaries, keys or raw captures in GitHub artifacts. Removed local paths go to macOS Trash.

Close only with the stated checks, commit/config/runtime/model identity where relevant, sanitized artifact summary and any remaining limits. Mocks/host tests do not establish live gameplay success. Record blocked prerequisites explicitly; do independent ready work. Experimental improvements may be rejected based on valid measurements.

## Starting references

- [Inspected libmelee frame/transport implementation](https://github.com/vladfi1/libmelee/blob/bce21f09984b286e6d36bfd2939e4cd4691f94c2/melee/console.py)
- [TypeSafe async Python client](https://docs.typesafe.ai/sdk/python/api/clients/async)

---

Parent roadmap: #2

# J11: Complete the first live Jev-controlled two-minute CPU match

**Track:** Jev connection — core

**Blocked by:** [J09 #11](https://github.com/cmoyates/melee/issues/11), [J10 #12](https://github.com/cmoyates/melee/issues/12)

## Outcome

Real match state reaches Jev and valid Jev choices visibly control the player while the game continues at normal speed.

## Scope

- Use only neutral, move toward/away, jump and shield from the proven executor. Feed compact exact/derived fields sufficient for these choices, with meaningful action descriptions.
- Retain the same scheduler and fallback as the delayed-fake run; enable real HTTP as a policy replacement, not a new runtime.
- Archive bounded replay/video evidence, full decision trace, resolved model/config hashes, applied age, rejection reasons, fallback fraction and spend.

## Acceptance

- [ ] Run at least two continuous minutes against CPU without manual menu action or inference-driven game freezes.
- [ ] Obtain at least 20 accepted real decisions with observed execution acknowledgements across at least three available skill classes; use controlled opportunities if needed rather than forcing fake choices.
- [ ] Every returned decision is accounted for; unavailable opportunities and low model participation are visible.
- [ ] Repeat the run once; report actual strength as unmeasured. A loop that only falls back does not pass this slice.

## Acceptance commands to implement

```sh
uv run --project agent melee-agent match --policy jev --duration 120 --profile local-v1 --max-requests 700
```

## Execution contract

This is a small vertical slice in the Jev Melee plan. Commands below are proposed acceptance interfaces to implement. Use the parent tracker for shared architecture and the full dependency graph.

Keep original assets, existing Showboat behavior/profiles and source history intact. Measured play changes only ordinary controller input. Use owned runtime profiles/processes and explicit run/request/token/spend limits. No game assets, rebuilt binaries, keys or raw captures in GitHub artifacts. Removed local paths go to macOS Trash.

Close only with the stated checks, commit/config/runtime/model identity where relevant, sanitized artifact summary and any remaining limits. Mocks/host tests do not establish live gameplay success. Record blocked prerequisites explicitly; do independent ready work. Experimental improvements may be rejected based on valid measurements.

## Starting references

- [TypeSafe HTTP API](https://docs.typesafe.ai/api)

---

Parent roadmap: #2

# J12: Prove failure recovery and watchdog behavior in a bounded live soak

**Track:** Reliable experimentation — core

**Blocked by:** [J11 #13](https://github.com/cmoyates/melee/issues/13)

## Outcome

The bot survives API failures and shuts down cleanly when control or observation is lost.

## Scope

- Exercise API disconnect, 429/529, malformed reply, low confidence, rate cap, cancellation, logger stall, frame loss, executor exception, worker death and provider recovery.
- Implement health/circuit-breaker behavior that recovers with current state only; ordinary confidence gates use conservative policy defaults without claiming confidence means win probability.
- Separate gameplay fallback from terminal disconnect policy. The external bot cannot hand off to native CPU without a separately proven control mechanism.

## Acceptance

- [ ] Thirty-minute deterministic fault schedule has zero stale/wrong-episode applications, no unbounded tasks/queues and no latched inputs after stop.
- [ ] API failure leaves local control running; unrecoverable observation/controller failure triggers owned-process teardown within the configured bound.
- [ ] Recovery never replays an old request; request/spend limits remain enforced through faults.
- [ ] Attach machine-readable fault counts, worst observed age/control gap, cleanup proof and unresolved failures.

## Acceptance commands to implement

```sh
uv run --project agent melee-agent soak --policy jev --fault-suite runtime-v1 --duration 1800 --budget-profile soak
```

## Execution contract

This is a small vertical slice in the Jev Melee plan. Commands below are proposed acceptance interfaces to implement. Use the parent tracker for shared architecture and the full dependency graph.

Keep original assets, existing Showboat behavior/profiles and source history intact. Measured play changes only ordinary controller input. Use owned runtime profiles/processes and explicit run/request/token/spend limits. No game assets, rebuilt binaries, keys or raw captures in GitHub artifacts. Removed local paths go to macOS Trash.

Close only with the stated checks, commit/config/runtime/model identity where relevant, sanitized artifact summary and any remaining limits. Mocks/host tests do not establish live gameplay success. Record blocked prerequisites explicitly; do independent ready work. Experimental improvements may be rejected based on valid measurements.

## Starting references

- [TypeSafe retry controls](https://docs.typesafe.ai/sdk/python/api/retries)
- [Inspected libmelee frame/transport implementation](https://github.com/vladfi1/libmelee/blob/bce21f09984b286e6d36bfd2939e4cd4691f94c2/melee/console.py)

---

Parent roadmap: #2

# J13: Turn a run trace into a deterministic incident report and offline regression

**Track:** Reliable experimentation — core

**Blocked by:** [J06 #8](https://github.com/cmoyates/melee/issues/8), [J10 #12](https://github.com/cmoyates/melee/issues/12)

## Outcome

The coding agent can locate a bad action, reproduce its decision path offline, and keep a regression without replaying cloud calls.

## Scope

- Implement inspect/explain and incident extraction by run/episode/frame/request ID. Bundle relevant observations, actual provider response, candidate set, skill transitions and applied packets.
- Replay recorded responses against the exact runtime policy/executor contract using a fake clock; reject mismatched schema/config/binary provenance.
- Create shareable summaries with explicit queued/started/acknowledged/contact/outcome distinctions. Raw captures, savestates and assets remain private; synthetic reduced fixtures may be committed.
- Teach the runbook to inspect this report after a failed acceptance command and convert a confirmed bug into a narrow regression.

## Acceptance

- [ ] A seeded stale-response or input-latch bug fails offline before a fix and passes after it without API/network/assets.
- [ ] Tampered, truncated, wrong-episode and mismatched-schema bundles fail integrity validation.
- [ ] Two offline replays produce identical accepted decisions and controller outputs.
- [ ] A historical match trace is not treated as the counterfactual future after a different policy action.

## Acceptance commands to implement

```sh
uv run --project agent melee-agent explain RUN_ID --frame FRAME
uv run --project agent melee-agent replay-incident INCIDENT_PATH --verify
```

## Execution contract

This is a small vertical slice in the Jev Melee plan. Commands below are proposed acceptance interfaces to implement. Use the parent tracker for shared architecture and the full dependency graph.

Keep original assets, existing Showboat behavior/profiles and source history intact. Measured play changes only ordinary controller input. Use owned runtime profiles/processes and explicit run/request/token/spend limits. No game assets, rebuilt binaries, keys or raw captures in GitHub artifacts. Removed local paths go to macOS Trash.

Close only with the stated checks, commit/config/runtime/model identity where relevant, sanitized artifact summary and any remaining limits. Mocks/host tests do not establish live gameplay success. Record blocked prerequisites explicitly; do independent ready work. Experimental improvements may be rejected based on valid measurements.

## Starting references

- [Checkout and Showboat handoff](https://github.com/cmoyates/melee/blob/b2195989e5c080fb37d4fb76471e2f5b40da257d/docs/showboat_handoff.md)

---

Parent roadmap: #2

# J14: Create repeatable mechanical scenarios with declared setup and outcome oracles

**Track:** Playable mechanics — core

**Blocked by:** [J07 #9](https://github.com/cmoyates/melee/issues/9), [J13 #15](https://github.com/cmoyates/melee/issues/15)

## Outcome

Skills can be evaluated in controlled game situations automatically instead of through arbitrary matches.

## Scope

- Define ScenarioV1 with setup inputs, stage/character, target state predicates, seed/initial-state provenance, timeout and measured outcome.
- Begin with fresh-match scripted setup: grounded spacing, jump/landing, shielded opponent, ledge and recoverable offstage situations; pin private savestates only if required and validate runtime/DOL/settings hashes before loading.
- Scenario setup may establish initial conditions but must stop before measured play; measured execution uses ordinary controller input. Keep setup privilege separate and report it.
- Record repeatability limits honestly; do not claim cloud responses or emulation are deterministic without evidence.

## Acceptance

- [ ] At least six scenarios run ten times each unattended and reach declared starting predicates, or fail setup explicitly.
- [ ] Mirrored left/right cases are covered; incorrect build-bound savestates cannot be loaded.
- [ ] Output identifies setup failure, skill failure, success and timeout separately with artifact links.
- [ ] Provide a fixed suite and seed/config manifest for subsequent skill issues.

## Acceptance commands to implement

```sh
uv run --project agent melee-agent scenarios --suite mechanics-v1 --repeats 10
```

## Execution contract

This is a small vertical slice in the Jev Melee plan. Commands below are proposed acceptance interfaces to implement. Use the parent tracker for shared architecture and the full dependency graph.

Keep original assets, existing Showboat behavior/profiles and source history intact. Measured play changes only ordinary controller input. Use owned runtime profiles/processes and explicit run/request/token/spend limits. No game assets, rebuilt binaries, keys or raw captures in GitHub artifacts. Removed local paths go to macOS Trash.

Close only with the stated checks, commit/config/runtime/model identity where relevant, sanitized artifact summary and any remaining limits. Mocks/host tests do not establish live gameplay success. Record blocked prerequisites explicitly; do independent ready work. Experimental improvements may be rejected based on valid measurements.

## Starting references

- [libmelee menu automation](https://github.com/vladfi1/libmelee/blob/bce21f09984b286e6d36bfd2939e4cd4691f94c2/melee/menuhelper.py)
- [Checkout and Showboat handoff](https://github.com/cmoyates/melee/blob/b2195989e5c080fb37d4fb76471e2f5b40da257d/docs/showboat_handoff.md)

---

Parent roadmap: #2

# J15: Recover and defend locally without cloud decisions

**Track:** Playable mechanics — core

**Blocked by:** [J14 #16](https://github.com/cmoyates/melee/issues/16)

## Outcome

The externally controlled character can survive representative offstage and defensive situations while Jev is unavailable.

## Scope

- Implement Fox-specific drift/jump/up-B recovery and ledge-return FSMs for initial stage geometry, with resource/state confirmation.
- Add conservative local hitstun DI/tech policies where current observations support them; unknown geometry/resources use a documented bounded fallback.
- Emergency reflexes preempt tactical intentions through the same arbiter. Do not copy native CPU recovery assumptions into a human-controlled port.
- Use the Fox decomp source and verified Fox frame data for mechanics. Reuse Showboat's architecture and testing lessons only; Falcon timings and internal Fighter/native VM ownership are not Fox skills or a callable external skill API.

## Acceptance

- [ ] On mirrored recoverable-offstage scenarios, at least 18/20 trials per declared scenario regain stage/ledge with the API disconnected.
- [ ] Explicitly unrecoverable states do not loop indefinitely or report success.
- [ ] Hitlag, hitstun, consumed jump, ledge occupancy, death and respawn reset ownership/resources correctly.
- [ ] Only controller packets change gameplay; no position, velocity, state or timer writes during measured play.

## Acceptance commands to implement

```sh
uv run --project agent melee-agent skill-check --suite recovery-v1 --repeats 20 --policy offline
```

## Execution contract

This is a small vertical slice in the Jev Melee plan. Commands below are proposed acceptance interfaces to implement. Use the parent tracker for shared architecture and the full dependency graph.

Keep original assets, existing Showboat behavior/profiles and source history intact. Measured play changes only ordinary controller input. Use owned runtime profiles/processes and explicit run/request/token/spend limits. No game assets, rebuilt binaries, keys or raw captures in GitHub artifacts. Removed local paths go to macOS Trash.

Close only with the stated checks, commit/config/runtime/model identity where relevant, sanitized artifact summary and any remaining limits. Mocks/host tests do not establish live gameplay success. Record blocked prerequisites explicitly; do independent ready work. Experimental improvements may be rejected based on valid measurements.

## Starting references

- [Checkout and Showboat handoff](https://github.com/cmoyates/melee/blob/b2195989e5c080fb37d4fb76471e2f5b40da257d/docs/showboat_handoff.md)

---

Parent roadmap: #2

# J16: Execute grounded attacks and grabs with observed completion

**Track:** Playable mechanics — core

**Blocked by:** [J14 #16](https://github.com/cmoyates/melee/issues/16)

## Outcome

The bot can convert a known grounded opportunity into an acknowledged attack or grab.

## Scope

- Add Fox jab, one simple grounded punish and grab with verified Fox timings, facing/range checks and bounded termination.
- Confirm action start, interruption, endlag/return to actionability; record capture/contact separately where available.
- Add simple local heuristic and random-legal selectors using precisely the same candidates/executor to prepare fair comparisons.
- Do not implement large combo trees, raw charge control or native VM transplantation in this slice.

## Acceptance

- [ ] 20 trials per supported action and direction execute the expected motion from legal setup.
- [ ] Shield, invulnerability, opponent moving out of range and own hitstun cause correct refusal/interruption rather than false hits.
- [ ] Grab acknowledgement and actual capture are separately asserted in suitable controlled cases.
- [ ] All baselines share the same legal candidate set and reflex/skill code.

## Acceptance commands to implement

```sh
uv run --project agent melee-agent skill-check --suite ground-combat-v1 --repeats 20
```

## Execution contract

This is a small vertical slice in the Jev Melee plan. Commands below are proposed acceptance interfaces to implement. Use the parent tracker for shared architecture and the full dependency graph.

Keep original assets, existing Showboat behavior/profiles and source history intact. Measured play changes only ordinary controller input. Use owned runtime profiles/processes and explicit run/request/token/spend limits. No game assets, rebuilt binaries, keys or raw captures in GitHub artifacts. Removed local paths go to macOS Trash.

Close only with the stated checks, commit/config/runtime/model identity where relevant, sanitized artifact summary and any remaining limits. Mocks/host tests do not establish live gameplay success. Record blocked prerequisites explicitly; do independent ready work. Experimental improvements may be rejected based on valid measurements.

## Starting references

- [Checkout and Showboat handoff](https://github.com/cmoyates/melee/blob/b2195989e5c080fb37d4fb76471e2f5b40da257d/docs/showboat_handoff.md)

---

Parent roadmap: #2

# J17: Execute one short-hop aerial with landing and interruption handling

**Track:** Playable mechanics — core

**Blocked by:** [J14 #16](https://github.com/cmoyates/melee/issues/16)

## Outcome

One complete aerial approach works reliably before expanding the aerial library.

## Scope

- Implement Fox short hop plus one aerial, drift, optional fast-fall and L-cancel attempt with observed jumpsquat/airborne/landing transitions.
- Keep hitlag and early/late landing behavior explicit; any platform variant is a separately declared supported scenario.
- Confirm exact input timing against the live adapter; no universal frame constants across characters or animation indexing schemes.

## Acceptance

- [ ] 20 trials from each supported direction/setup acknowledge the intended aerial and terminate in a known controller state.
- [ ] Early/late landing, hitlag, failed jumpsquat and interruption do not issue stale follow-up inputs.
- [ ] L-cancel input attempt is distinguished from observed reduced landing lag; success requires the latter when claimed.
- [ ] Unsupported geometry/action states fall back with a reason.

## Acceptance commands to implement

```sh
uv run --project agent melee-agent skill-check --suite aerial-v1 --repeats 20
```

## Execution contract

This is a small vertical slice in the Jev Melee plan. Commands below are proposed acceptance interfaces to implement. Use the parent tracker for shared architecture and the full dependency graph.

Keep original assets, existing Showboat behavior/profiles and source history intact. Measured play changes only ordinary controller input. Use owned runtime profiles/processes and explicit run/request/token/spend limits. No game assets, rebuilt binaries, keys or raw captures in GitHub artifacts. Removed local paths go to macOS Trash.

Close only with the stated checks, commit/config/runtime/model identity where relevant, sanitized artifact summary and any remaining limits. Mocks/host tests do not establish live gameplay success. Record blocked prerequisites explicitly; do independent ready work. Experimental improvements may be rejected based on valid measurements.

## Starting references

- [Checkout and Showboat handoff](https://github.com/cmoyates/melee/blob/b2195989e5c080fb37d4fb76471e2f5b40da257d/docs/showboat_handoff.md)
- [Inspected libmelee frame/transport implementation](https://github.com/vladfi1/libmelee/blob/bce21f09984b286e6d36bfd2939e4cd4691f94c2/melee/console.py)

---

Parent roadmap: #2

# J18: Compile semantic observations and build a leakage-resistant decision corpus

**Track:** Playable mechanics — core

**Blocked by:** [J14 #16](https://github.com/cmoyates/melee/issues/16)

## Outcome

Jev receives relevant gameplay meaning, and representation changes can be evaluated on fixed cases.

## Scope

- Compile CompactObservationV1 with named actions, relative and absolute stage geometry, mechanical availability, current skill, short history and legal candidates.
- Compute arithmetic, timing comparisons and candidate legality locally. Label exact/derived/estimated/unknown features; don't invent exact punish windows from incomplete frame data.
- Use locally supplied replays and captured scenarios through the same extractor; establish field/enum/frame parity for the installed libmelee version before combining them.
- Split train/tuning/held-out by match/session, not neighboring frames. Exclude future outcomes, opponent future input and full replay suffixes from policy state. Pin prompt/candidate ordering/versions.

## Acceptance

- [ ] Live and offline extraction agree for common supported fields on fixtures; missing replay fields are represented as unavailable.
- [ ] Mirror, boundary spacing, hitlag, action-frame indexing and resource cases have golden assertions.
- [ ] Evaluate at least 1000 ordered states with budgeted provider calls or recorded responses; separately report replay-only label agreement and live outcomes.
- [ ] Document payload tokens and feature provenance, and preserve raw observations privately for debugging.

## Acceptance commands to implement

```sh
uv run --project agent melee-agent corpus build --sources local --split-by episode
uv run --project agent melee-agent corpus validate CORPUS_ID
```

## Execution contract

This is a small vertical slice in the Jev Melee plan. Commands below are proposed acceptance interfaces to implement. Use the parent tracker for shared architecture and the full dependency graph.

Keep original assets, existing Showboat behavior/profiles and source history intact. Measured play changes only ordinary controller input. Use owned runtime profiles/processes and explicit run/request/token/spend limits. No game assets, rebuilt binaries, keys or raw captures in GitHub artifacts. Removed local paths go to macOS Trash.

Close only with the stated checks, commit/config/runtime/model identity where relevant, sanitized artifact summary and any remaining limits. Mocks/host tests do not establish live gameplay success. Record blocked prerequisites explicitly; do independent ready work. Experimental improvements may be rejected based on valid measurements.

## Starting references

- [Jev 1.13 known limitations](https://docs.typesafe.ai/model-jaggedness/jev-1.13)
- [Inspected libmelee frame/transport implementation](https://github.com/vladfi1/libmelee/blob/bce21f09984b286e6d36bfd2939e4cd4691f94c2/melee/console.py)

---

Parent roadmap: #2

# J19: Assemble a complete Jev tactical player on one character and stage

**Track:** Playable mechanics — core

**Blocked by:** [J12 #14](https://github.com/cmoyates/melee/issues/14), [J15 #17](https://github.com/cmoyates/melee/issues/17), [J16 #18](https://github.com/cmoyates/melee/issues/18), [J17 #19](https://github.com/cmoyates/melee/issues/19), [J18 #20](https://github.com/cmoyates/melee/issues/20)

## Outcome

Jev can choose meaningful neutral and punish skills while a complete local controller handles survival.

## Scope

- Expand Choice to the proven skill library with context-specific candidates, durations, preconditions and interruption rules.
- Add compact domain descriptions and a neutral default macro directive. Prevent thrashing with explicit commitment and apply-time validation.
- Provide random-legal, scripted and Jev policy modes all playing Fox and sharing observation limits, executor, emergency reflexes and starting conditions.
- Keep core Fox gameplay stock for comparable measurement. Preserve Showboat Falcon as a separate native-mod baseline; compatibility work does not merge it into the Fox executor.

## Acceptance

- [ ] Ten unattended full matches per policy complete with valid input and trace integrity, including recovery/death/results transitions.
- [ ] Jev has measurable tactical participation by game phase; report submitted, valid, accepted and acknowledged decisions separately.
- [ ] Zero forbidden/unknown action IDs or expired decisions applied.
- [ ] Every loss/timeout can be explained using retained evidence; playing strength remains a measured result rather than an acceptance assumption.

## Acceptance commands to implement

```sh
uv run --project agent melee-agent match --policies random,scripted,jev --episodes-per-policy 10 --profile local-v1
```

## Execution contract

This is a small vertical slice in the Jev Melee plan. Commands below are proposed acceptance interfaces to implement. Use the parent tracker for shared architecture and the full dependency graph.

Keep original assets, existing Showboat behavior/profiles and source history intact. Measured play changes only ordinary controller input. Use owned runtime profiles/processes and explicit run/request/token/spend limits. No game assets, rebuilt binaries, keys or raw captures in GitHub artifacts. Removed local paths go to macOS Trash.

Close only with the stated checks, commit/config/runtime/model identity where relevant, sanitized artifact summary and any remaining limits. Mocks/host tests do not establish live gameplay success. Record blocked prerequisites explicitly; do independent ready work. Experimental improvements may be rejected based on valid measurements.

## Starting references

- [TypeSafe HTTP API](https://docs.typesafe.ai/api)
- [Checkout and Showboat handoff](https://github.com/cmoyates/melee/blob/b2195989e5c080fb37d4fb76471e2f5b40da257d/docs/showboat_handoff.md)

---

Parent roadmap: #2

# J20: Run reproducible policy tournaments and produce an honest strength report

**Track:** Measured improvement — core

**Blocked by:** [J19 #21](https://github.com/cmoyates/melee/issues/21), [J13 #15](https://github.com/cmoyates/melee/issues/15)

## Outcome

A single bounded command compares bot policies against the same CPU/scenario schedule.

## Scope

- Create a versioned EvaluationSuite with Fox as the controlled character, fixed opponent/stage/rules, held-out seed/setup schedule, both player sides, warmup policy and per-policy budgets.
- Score actual match results, stocks/damage where reliable, deaths (not unsupported self-destruct attribution), survival, stage occupancy, action acknowledgement, fallback fraction, decision age and input latency.
- Report sample sizes, uncertainty intervals, paired setup differences and invalid/aborted episode reasons. Keep Showboat Falcon as a separately labeled baseline with character, binary and controller differences disclosed; it is not a same-character policy ablation or a prerequisite for the Fox comparison. Publish sanitized summaries only.
- Support real-time evaluation by default; fast-forward/EXI is a separate proven runtime profile and is never used to claim cloud real-time performance.

## Acceptance

- [ ] Execute at least 30 valid held-out episodes per random/scripted/Jev policy; retain all failures and report exclusion rules.
- [ ] One command generates JSON and Markdown comparison with code/runtime/model/prompt/schema/config hashes.
- [ ] Repeat a subset to quantify environment/model variability.
- [ ] State whether Jev improves over the scripted baseline; a negative result closes the measurement issue with evidence and does not justify a stronger-than-CPU claim.

## Acceptance commands to implement

```sh
uv run --project agent melee-agent evaluate --suite cpu-v1 --episodes-per-policy 30 --policies random,scripted,jev
```

## Execution contract

This is a small vertical slice in the Jev Melee plan. Commands below are proposed acceptance interfaces to implement. Use the parent tracker for shared architecture and the full dependency graph.

Keep original assets, existing Showboat behavior/profiles and source history intact. Measured play changes only ordinary controller input. Use owned runtime profiles/processes and explicit run/request/token/spend limits. No game assets, rebuilt binaries, keys or raw captures in GitHub artifacts. Removed local paths go to macOS Trash.

Close only with the stated checks, commit/config/runtime/model identity where relevant, sanitized artifact summary and any remaining limits. Mocks/host tests do not establish live gameplay success. Record blocked prerequisites explicitly; do independent ready work. Experimental improvements may be rejected based on valid measurements.

## Starting references

- [Current libmelee setup and macOS caveat](https://github.com/vladfi1/libmelee/blob/bce21f09984b286e6d36bfd2939e4cd4691f94c2/README.md)
- [TypeSafe model versions and limits](https://docs.typesafe.ai/models)

---

Parent roadmap: #2

# J21: Calibrate Jev action selection, confidence gates and delay tolerance

**Track:** Measured improvement — core

**Blocked by:** [J20 #22](https://github.com/cmoyates/melee/issues/22), [J09 #11](https://github.com/cmoyates/melee/issues/11)

## Outcome

Choose a measured tactical configuration and know when the provider is too slow or unhelpful.

## Scope

- Predeclare a bounded tuning grid over cadence, action lifetime, compact feature variants, commitment and confidence thresholds; freeze the held-out set.
- Treat Choice probabilities as judgments over candidates and confidence as a distribution statistic, not action success or win probability. Measure selectivity versus labeled correctness and live return separately.
- Measure useful decision age, provider tail latency, fallback share, cost per accepted decision and local overhead; choose longer-lived intents if instantaneous choices expire.
- Keep best-known scripted configuration available. If no Jev configuration improves, report that boundary and open a precise follow-up rather than expand models blindly.

## Acceptance

- [ ] A/B result uses identical executor/observation capabilities and declared seeds/scenarios, with at least 30 held-out episodes per shortlisted config.
- [ ] No held-out tuning; confidence buckets show counts and defined labels, not unsupported calibration claims.
- [ ] Chosen config has a rationale, measured latency envelope, fallback/participation rate and reproducible budget.
- [ ] Local overhead target p95 <=2 ms excluding frame wait/provider call is measured; misses are explained and addressed or explicitly block a real-time claim.

## Acceptance commands to implement

```sh
uv run --project agent melee-agent tune --experiment tactical-v1 --budget-profile tuning
uv run --project agent melee-agent evaluate --suite heldout-v1 --config SELECTED
```

## Execution contract

This is a small vertical slice in the Jev Melee plan. Commands below are proposed acceptance interfaces to implement. Use the parent tracker for shared architecture and the full dependency graph.

Keep original assets, existing Showboat behavior/profiles and source history intact. Measured play changes only ordinary controller input. Use owned runtime profiles/processes and explicit run/request/token/spend limits. No game assets, rebuilt binaries, keys or raw captures in GitHub artifacts. Removed local paths go to macOS Trash.

Close only with the stated checks, commit/config/runtime/model identity where relevant, sanitized artifact summary and any remaining limits. Mocks/host tests do not establish live gameplay success. Record blocked prerequisites explicitly; do independent ready work. Experimental improvements may be rejected based on valid measurements.

## Starting references

- [TypeSafe confidence semantics](https://docs.typesafe.ai/confidence)
- [TypeSafe model versions and limits](https://docs.typesafe.ai/models)
- [Jev 1.13 known limitations](https://docs.typesafe.ai/model-jaggedness/jev-1.13)

---

Parent roadmap: #2

# J22: Track opponent tendencies and prove a time-limited macro directive

**Track:** Strategy and style — core

**Blocked by:** [J20 #22](https://github.com/cmoyates/melee/issues/22), [J18 #20](https://github.com/cmoyates/melee/issues/20)

## Outcome

A deterministic strategic directive changes measured tactical behavior without taking over controller execution.

## Scope

- Maintain event-based opponent statistics with denominators, opportunities, continuity and missing-data handling; begin with approach/retreat and shield responses that telemetry supports.
- Define MacroDirectiveV1: goal, risk, spacing, preferred/avoided skill families, run/episode/generation and TTL.
- Implement two mock planners (patient center control and pressure) using the same tactical interface. Bound probability reweighting and preserve legality/reflex priority.
- Expire/reset directives on TTL, episode and target changes; no model is needed for this slice.
- Keep durable personality configuration separate from short-lived MacroDirective state. Tactical directive expiry or a new stock must not silently erase the selected personality; default directives are derived from the active personality. Character mechanics remain in the skill layer.

## Acceptance

- [ ] Fixture histories produce exact counts including interrupted and missing intervals.
- [ ] Two directives produce a predeclared measurable difference such as approach frequency/center occupancy over matched scenarios.
- [ ] Impossible preferences and all-zero reweighting fall back deterministically.
- [ ] Expired or old-episode directives cannot affect input.

## Acceptance commands to implement

```sh
uv run --project agent melee-agent macro-check --planners patient,pressure --suite style-v1
```

## Execution contract

This is a small vertical slice in the Jev Melee plan. Commands below are proposed acceptance interfaces to implement. Use the parent tracker for shared architecture and the full dependency graph.

Keep original assets, existing Showboat behavior/profiles and source history intact. Measured play changes only ordinary controller input. Use owned runtime profiles/processes and explicit run/request/token/spend limits. No game assets, rebuilt binaries, keys or raw captures in GitHub artifacts. Removed local paths go to macOS Trash.

Close only with the stated checks, commit/config/runtime/model identity where relevant, sanitized artifact summary and any remaining limits. Mocks/host tests do not establish live gameplay success. Record blocked prerequisites explicitly; do independent ready work. Experimental improvements may be rejected based on valid measurements.

## Starting references

- [TypeSafe confidence semantics](https://docs.typesafe.ai/confidence)
- [Checkout and Showboat handoff](https://github.com/cmoyates/melee/blob/b2195989e5c080fb37d4fb76471e2f5b40da257d/docs/showboat_handoff.md)

---

Parent roadmap: #2

# J23: Add a replaceable LLM strategist with measured incremental value

**Track:** Strategy and style — core

**Blocked by:** [J22 #24](https://github.com/cmoyates/melee/issues/24), [J21 #23](https://github.com/cmoyates/melee/issues/23)

## Outcome

A slow LLM can adapt strategy from summaries while the Jev/local loop remains independent.

## Scope

- Implement vendor-neutral MacroPlanner with strict structured output, bounded summaries, minimum update interval/event triggers, model ID, token/spend cap and finite deadline.
- Validate instructions against the directive schema and allowed skill families; model has no controller, shell or game-memory access.
- Use current summaries and deterministic opponent stats; retain a directive until TTL then return to default on timeout or malformed output.
- Choose the concrete provider/model at implementation using existing access and a small benchmark; add secure credentials as an external prerequisite only if absent.
- Condition strategic summaries and directives on the active validated personality, balancing its preferences with the current matchup and available skills. Bind async plans to personality revision so an old response cannot overwrite a newer user request.

## Acceptance

- [ ] Malformed output, unsupported goals, long delay, cancellation, stale summaries and provider loss leave the tactical loop unaffected.
- [ ] Run at least 30 matched episodes per Jev-only/Jev+macro configuration with the same executor and total evaluation settings.
- [ ] Report behavior/strength/cost differences, even if the LLM adds no value.
- [ ] Removing/disabling the LLM adapter still leaves a complete playable Jev-only bot.
- [ ] Changing the personality revision invalidates old in-flight plans; timeout retains the last valid personality and uses its default directive after tactical TTL expiry.

## Acceptance commands to implement

```sh
uv run --project agent melee-agent evaluate --suite macro-v1 --policies jev,jev-macro --episodes-per-policy 30
```

## Execution contract

This is a small vertical slice in the Jev Melee plan. Commands below are proposed acceptance interfaces to implement. Use the parent tracker for shared architecture and the full dependency graph.

Keep original assets, existing Showboat behavior/profiles and source history intact. Measured play changes only ordinary controller input. Use owned runtime profiles/processes and explicit run/request/token/spend limits. No game assets, rebuilt binaries, keys or raw captures in GitHub artifacts. Removed local paths go to macOS Trash.

Close only with the stated checks, commit/config/runtime/model identity where relevant, sanitized artifact summary and any remaining limits. Mocks/host tests do not establish live gameplay success. Record blocked prerequisites explicitly; do independent ready work. Experimental improvements may be rejected based on valid measurements.

## Starting references

- [Checkout and Showboat handoff](https://github.com/cmoyates/melee/blob/b2195989e5c080fb37d4fb76471e2f5b40da257d/docs/showboat_handoff.md)

---

Parent roadmap: #2

# J24: Expose reproducible playing styles and an explanation of adaptation

**Track:** Strategy and style — core

**Blocked by:** [J22 #24](https://github.com/cmoyates/melee/issues/24), [J23 #25](https://github.com/cmoyates/melee/issues/25)

## Outcome

The user describes how the bot should play in ordinary language and can revise that personality during a match, with observable behavior changes through the same Jev foundation.

## Scope

- Add a natural-language personality command, such as 'confident and flashy, bait mistakes, take stylish risks when ahead, celebrate only when safe.' Use the LLM adapter to compile it into a validated PersonaSpecV1 with named presets as reproducible examples.
- PersonaSpecV1 stores the requested description, revision, strategic preferences, risk/style weights and supported skill families. Keep it durable across stocks and tactical directive expiry. It influences macro planning and bounded seeded sampling/reweighting of legal Jev choices.
- Apply a new personality atomically at a valid tactical boundary without restarting the match or editing skill code. Reject obsolete compilation/strategy responses by revision; timeout or invalid output retains the previous valid personality.
- Report which requested traits are supported by the current skill library and which need new skills. A personality description cannot manufacture a taunt, combo, recovery route or character mechanic that the executor cannot perform.
- Log raw versus reweighted distributions, personality revisions, sampled selections and strategy changes. Keep local legality, emergency reflexes, recovery and commitment rules authoritative.
- Use Fox to prove creative control now. Preserve the old Showboat Falcon as a historical baseline; the intended later Showboat Falcon is a character skill adapter plus expressive skills and personality on this shared foundation, rather than an extension of the old native CPU overlays.

## Acceptance

- [ ] Two distinct natural-language personality descriptions produce predeclared differences in approach, retreat or risk metrics on matched scenarios; test paraphrases without adding code branches for exact wording.
- [ ] Change personality during a live match with no restart; record request time, compilation latency, accepted revision and first legal application. Do not claim instantaneous behavior or promise a fixed cloud response time.
- [ ] Rapid successive edits, out-of-order compilation/strategy replies, invalid output and provider timeout cannot restore an older persona or disrupt frame execution.
- [ ] Fixed recorded responses, compiled personality and sampling seed reproduce choices. Stock transitions and tactical TTL expiry retain the active personality.
- [ ] Unsupported requested moves/traits are reported explicitly; style cannot bypass action legality, recovery, deadline, commitment or budget checks.
- [ ] The run report links observed behavior to the active personality and adaptation evidence; a changed label or generated explanation alone does not prove a changed playing style.

## Acceptance commands to implement

```sh
uv run --project agent melee-agent evaluate --suite style-v1 --styles patient,aggressive --episodes-per-style 20
uv run --project agent melee-agent persona set --run-id RUN_ID --description 'Patient and evasive; punish mistakes and protect the lead'
```

## Execution contract

This is a small vertical slice in the Jev Melee plan. Commands below are proposed acceptance interfaces to implement. Use the parent tracker for shared architecture and the full dependency graph.

Keep original assets, existing Showboat behavior/profiles and source history intact. Measured play changes only ordinary controller input. Use owned runtime profiles/processes and explicit run/request/token/spend limits. No game assets, rebuilt binaries, keys or raw captures in GitHub artifacts. Removed local paths go to macOS Trash.

Close only with the stated checks, commit/config/runtime/model identity where relevant, sanitized artifact summary and any remaining limits. Mocks/host tests do not establish live gameplay success. Record blocked prerequisites explicitly; do independent ready work. Experimental improvements may be rejected based on valid measurements.

## Starting references

- [TypeSafe confidence semantics](https://docs.typesafe.ai/confidence)

---

Parent roadmap: #2

# J25: Test shifted-DOL compatibility and export one useful decomp field

**Track:** Optional research — optional experiment

**Blocked by:** [J06 #8](https://github.com/cmoyates/melee/issues/8), [J14 #16](https://github.com/cmoyates/melee/issues/16)

## Outcome

Resolve whether custom telemetry can enrich this bot without breaking the stock Slippi/control path.

## Scope

- First audit Slippi/Gecko patch addresses against this fork's shifted DOL and source hooks. Do not assume a retail-address patch works on a rebuilt binary.
- Choose one documented missing field from current failure evidence, such as exact transition eligibility, with a specific consumer and controlled oracle.
- Build a separate feature-flagged Jev instrumentation target without changing active Showboat build/config/profile. Use named source symbols and mapped build addresses.
- Prove a minimal frame-tagged read-only export via a validated transport. No game-thread networking, unsafe OSReport float varargs or writing gameplay state. If compatibility fails, document the minimal relocation/transport requirement and leave core bot usable.

## Acceptance

- [ ] Telemetry-off target matches its declared baseline behavior/hook footprint; original stock hash remains unchanged.
- [ ] Validate the field and frame/life identity against a controlled live scenario.
- [ ] Show the exact runtime/DOL/patch combination used; corrupted/unsupported combinations fail closed.
- [ ] Bounded probe yields either working compatibility or a concrete failed hypothesis. Before closing a negative result, add a concrete compatibility-remediation issue as a native blocker of J26, or explicitly close J26 as not planned; never leave enrichment falsely ready.

## Acceptance commands to implement

```sh
uv run --project agent melee-agent decomp probe --field SELECTED --profile instrumented-v1
```

## Execution contract

This is a small vertical slice in the Jev Melee plan. Commands below are proposed acceptance interfaces to implement. Use the parent tracker for shared architecture and the full dependency graph.

Keep original assets, existing Showboat behavior/profiles and source history intact. Measured play changes only ordinary controller input. Use owned runtime profiles/processes and explicit run/request/token/spend limits. No game assets, rebuilt binaries, keys or raw captures in GitHub artifacts. Removed local paths go to macOS Trash.

Close only with the stated checks, commit/config/runtime/model identity where relevant, sanitized artifact summary and any remaining limits. Mocks/host tests do not establish live gameplay success. Record blocked prerequisites explicitly; do independent ready work. Experimental improvements may be rejected based on valid measurements.

## Starting references

- [Checkout and Showboat handoff](https://github.com/cmoyates/melee/blob/b2195989e5c080fb37d4fb76471e2f5b40da257d/docs/showboat_handoff.md)
- [Inspected libmelee frame/transport implementation](https://github.com/vladfi1/libmelee/blob/bce21f09984b286e6d36bfd2939e4cd4691f94c2/melee/console.py)

---

Parent roadmap: #2

# J26: Consume versioned enriched telemetry and measure its value

**Track:** Optional research — optional experiment

**Blocked by:** [J25 #27](https://github.com/cmoyates/melee/issues/27), [J20 #22](https://github.com/cmoyates/melee/issues/22)

## Outcome

An enriched state source can be swapped in without changing the policy/executor contracts, and its value is quantified.

## Scope

- Define a minimal versioned BotTelemetry envelope with source build, frame, episode/life identity, sequence and integrity check; specify byte order and float encoding.
- Handle torn reads, stale/missing packets, version mismatch and telemetry source dropout. Downgrade optional fields to unknown/core state rather than fabricate continuity.
- Compare core-only and enriched policies on the same missing-information scenarios and held-out match suite.
- Measure export/transport overhead and missing-frame rates; retain only features that justify their cost.

## Acceptance

- [ ] Thirty-minute enabled capture has all malformed/missing records rejected or accounted for and no invalid cross-frame joins.
- [ ] Fault injection covers partial packets, wrong build/version, reused sequence and late previous-life telemetry.
- [ ] Consumer works with core-only state after enrichment disappears.
- [ ] A/B report separates information benefit from changing runtime/game binary; record residual confounds.

## Acceptance commands to implement

```sh
uv run --project agent melee-agent evaluate --suite telemetry-v1 --sources core,enriched
```

## Execution contract

This is a small vertical slice in the Jev Melee plan. Commands below are proposed acceptance interfaces to implement. Use the parent tracker for shared architecture and the full dependency graph.

Keep original assets, existing Showboat behavior/profiles and source history intact. Measured play changes only ordinary controller input. Use owned runtime profiles/processes and explicit run/request/token/spend limits. No game assets, rebuilt binaries, keys or raw captures in GitHub artifacts. Removed local paths go to macOS Trash.

Close only with the stated checks, commit/config/runtime/model identity where relevant, sanitized artifact summary and any remaining limits. Mocks/host tests do not establish live gameplay success. Record blocked prerequisites explicitly; do independent ready work. Experimental improvements may be rejected based on valid measurements.

## Starting references

- [Checkout and Showboat handoff](https://github.com/cmoyates/melee/blob/b2195989e5c080fb37d4fb76471e2f5b40da257d/docs/showboat_handoff.md)

---

Parent roadmap: #2

# J27: Measure speculative branch decisions under real latency

**Track:** Optional research — optional experiment

**Blocked by:** [J21 #23](https://github.com/cmoyates/melee/issues/23)

## Outcome

Test whether precomputed responses to opponent behavior increase useful tactical decisions.

## Scope

- Ask a small bounded set of independent branch Choices, each with explicit hypothetical conditions and the same factual snapshot.
- Bind branch answers to context, source frame, candidate set and TTL; select at most one branch after an observed trigger and revalidate live legality.
- Handle ambiguous/multiple/no triggers explicitly; branches cannot use each other's answers. Count extra question tokens and service latency.
- Keep simple single-choice mode as the default unless held-out evidence favors fan-out.

## Acceptance

- [ ] Synthetic tests cover mutually conflicting triggers, aged branches and context changes with no illegal application.
- [ ] Matched live evaluation reports action age, valid branch utilization, gameplay outcomes and cost per useful decision.
- [ ] No regression in stale rejection, reflex priority or request caps.
- [ ] Commit measured enable/disable decision; benefit is not presumed.

## Acceptance commands to implement

```sh
uv run --project agent melee-agent evaluate --suite fanout-v1 --policy-variants single,fanout
```

## Execution contract

This is a small vertical slice in the Jev Melee plan. Commands below are proposed acceptance interfaces to implement. Use the parent tracker for shared architecture and the full dependency graph.

Keep original assets, existing Showboat behavior/profiles and source history intact. Measured play changes only ordinary controller input. Use owned runtime profiles/processes and explicit run/request/token/spend limits. No game assets, rebuilt binaries, keys or raw captures in GitHub artifacts. Removed local paths go to macOS Trash.

Close only with the stated checks, commit/config/runtime/model identity where relevant, sanitized artifact summary and any remaining limits. Mocks/host tests do not establish live gameplay success. Record blocked prerequisites explicitly; do independent ready work. Experimental improvements may be rejected based on valid measurements.

## Starting references

- [TypeSafe speculative fan-out](https://docs.typesafe.ai/patterns/fan-out)

---

Parent roadmap: #2

# J28: Evaluate bounded response-time state prediction

**Track:** Optional research — optional experiment

**Blocked by:** [J21 #23](https://github.com/cmoyates/melee/issues/23)

## Outcome

Test whether a short prediction horizon improves tactical choices despite cloud delay.

## Scope

- Predict only well-supported motion/action evolution using measured latency distribution; mark horizon and uncertainty separately from observed state.
- Clamp near collisions, hitlag, ledges, unknown actions and opponent commitments; do not invent an exact future.
- Log prediction error at the target frame and use identical apply-time legality checks.
- Keep prediction disabled unless measured benefit survives held-out tests.

## Acceptance

- [ ] Prediction error is reported by horizon/situation on unseen episodes; unsupported states explicitly abstain.
- [ ] Matched live A/B evaluates useful decision age and outcomes with the same local skill execution.
- [ ] No predicted feature overrides observed recovery/reflex/legality checks.
- [ ] Archive a keep/reject conclusion and measured limits rather than requiring an improvement to close the experiment.

## Acceptance commands to implement

```sh
uv run --project agent melee-agent evaluate --suite prediction-v1 --policy-variants observed,predicted
```

## Execution contract

This is a small vertical slice in the Jev Melee plan. Commands below are proposed acceptance interfaces to implement. Use the parent tracker for shared architecture and the full dependency graph.

Keep original assets, existing Showboat behavior/profiles and source history intact. Measured play changes only ordinary controller input. Use owned runtime profiles/processes and explicit run/request/token/spend limits. No game assets, rebuilt binaries, keys or raw captures in GitHub artifacts. Removed local paths go to macOS Trash.

Close only with the stated checks, commit/config/runtime/model identity where relevant, sanitized artifact summary and any remaining limits. Mocks/host tests do not establish live gameplay success. Record blocked prerequisites explicitly; do independent ready work. Experimental improvements may be rejected based on valid measurements.

## Starting references

- [Checkout and Showboat handoff](https://github.com/cmoyates/melee/blob/b2195989e5c080fb37d4fb76471e2f5b40da257d/docs/showboat_handoff.md)

---

Parent roadmap: #2

# J29: Certify a one-command autonomous demo and resumable development workflow

**Track:** Autonomous handoff — core

**Blocked by:** [J12 #14](https://github.com/cmoyates/melee/issues/14), [J13 #15](https://github.com/cmoyates/melee/issues/15), [J21 #23](https://github.com/cmoyates/melee/issues/23), [J24 #26](https://github.com/cmoyates/melee/issues/26)

## Outcome

A fresh agent session can select a ready issue, run its checks, diagnose failures and demonstrate the player from documented commands.

## Scope

- Finalize bootstrap/doctor/run/evaluate/explain/stop interfaces and a machine-readable ready-work view from GitHub dependencies.
- Exercise clean agent-environment setup against existing user-owned assets; add capability-gated local live checks alongside asset-free CI. Don't install a privileged persistent self-hosted runner for public PRs.
- Document session launch leases, owned profiles, credential bootstrap, model/cost limits, exact closure evidence and restart recovery. Reserve interactive Showboat testing for its existing user-ready workflow.
- Package source/configs and sanitized reports only; preserve builds/captures locally and Trash for removal. Defer multi-character expansion, trained local policy and all-stage generalization to evidence-driven future issues.
- Carry forward the intended product direction: after Fox certifies the shared foundation, implement Captain Falcon-specific skills and expressive actions on that foundation, then recreate Showboat through high-level personality control. Preserve the old Showboat as comparison evidence, not the starting controller.

## Acceptance

- [ ] From a fresh shell, doctor -> automated demo -> report -> stop completes without manual menus; test missing key/runtime/assets with actionable blocked status.
- [ ] Run a final 100-episode selected-policy suite within a declared budget; report competence and uncertainty honestly against the existing baselines.
- [ ] Resume after an interrupted run and continue the next ready issue without duplicating games, API spend or GitHub issues.
- [ ] Core milestone closes only with live proof and resolved mandatory acceptance; optional research outcomes are tracked separately and cannot hold the first usable bot hostage.
- [ ] The autonomous demo accepts a natural-language personality and changes it during play; its report shows capability limits, personality revisions and observed behavioral differences.

## Acceptance commands to implement

```sh
uv run --project agent melee-agent demo --profile local-v1 --budget-profile demo
uv run --project agent melee-agent evaluate --suite certification-v1 --episodes 100
uv run --project agent melee-agent work ready --repo cmoyates/melee
```

## Execution contract

This is a small vertical slice in the Jev Melee plan. Commands below are proposed acceptance interfaces to implement. Use the parent tracker for shared architecture and the full dependency graph.

Keep original assets, existing Showboat behavior/profiles and source history intact. Measured play changes only ordinary controller input. Use owned runtime profiles/processes and explicit run/request/token/spend limits. No game assets, rebuilt binaries, keys or raw captures in GitHub artifacts. Removed local paths go to macOS Trash.

Close only with the stated checks, commit/config/runtime/model identity where relevant, sanitized artifact summary and any remaining limits. Mocks/host tests do not establish live gameplay success. Record blocked prerequisites explicitly; do independent ready work. Experimental improvements may be rejected based on valid measurements.

## Starting references

- [Checkout and Showboat handoff](https://github.com/cmoyates/melee/blob/b2195989e5c080fb37d4fb76471e2f5b40da257d/docs/showboat_handoff.md)
