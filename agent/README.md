# Jev agent workspace

Fox first; build the common foundation for natural-language personality control
and a future Showboat Captain Falcon. Existing Showboat remains a separate
historical implementation and baseline.

The workspace includes supervised Battlefield matches, frame/replay recording,
local recovery and combat skills, and bounded asynchronous Jev choices through
OpenRouter. Grounded tactical integration is experimental; see its
[acceptance contract](../docs/jev-grounded-tactics.md). The complete player and personality control
remain later slices. The scripted policy is a temporary controller test.

## Setup

Use the repository root as the working directory. The tooling is pinned to
Python **3.13.12** and uv/build backend **0.10.9**. There are no third-party runtime
or test dependencies for doctor. The optional `runtime` extra pins libmelee and
its dependencies. The existing decomp `.venv` is not used or changed.

```sh
rtk proxy sh agent/bootstrap.sh
rtk proxy uv sync --project agent --locked
rtk proxy uv run --project agent --no-sync melee-agent doctor --json
rtk proxy uv run --project agent --no-sync melee-agent doctor --json --require offline
rtk proxy uv run --project agent --no-sync python -B -m unittest discover -s agent/tests -v
```

Bootstrap uses the installed interpreter, the lockfile and uv's bundled pinned
build backend **offline**, without downloading Python, game assets or a runtime.
An absent interpreter/tool is an explicit prerequisite. It refuses to replace
an existing environment with a different Python version or a symlinked `.venv`.
No automatic system installation or security-setting change is performed.
uv's bundled-backend behavior is documented at
<https://docs.astral.sh/uv/concepts/build-backend/#bundled-build-backend>.

The isolated environment is `agent/.venv`; when invoked from the repository root,
the uv cache is under `build/jev/uv-cache`. Direct uv commands respect environment
overrides: do not set `UV_PROJECT_ENVIRONMENT` to the decomp environment. The
bootstrap clears that override. Run the installed entry point directly if you
need diagnostics without uv's environment synchronization:

```sh
rtk proxy agent/.venv/bin/melee-agent doctor --json --require offline
```

## Private local configuration

Defaults work for offline development. When needed, copy `config.example.toml`
to ignored `agent/local.toml` and edit private paths there. Input assets/runtime
paths may be external read-only files. Configuration itself must stay inside the
checkout; future run storage must resolve below `build/jev/` without symlink
escapes. Never use `build/showboat` as Jev output storage.

Jev uses **OpenRouter** with `OPENROUTER_MODEL=~typesafe/jev-latest`.
Put your token after `OPENROUTER_API_KEY=` in
`agent/.env`, which is gitignored. A fresh checkout can copy the blank
`agent/.env.example` template to `agent/.env`. Load it explicitly from the
repository root:

```sh
rtk proxy uv run --project agent --no-sync --env-file agent/.env melee-agent doctor --json
```

The doctor checks presence only, never displays or authenticates the token.
Direct CLI invocations do not load `.env` automatically. No API key is accepted
in TOML. Do not put secrets in CLI arguments, issue bodies, reports or committed
files. The J08/J09 adapter and benchmark consume these settings only through
explicit provider commands; adding settings does not make an API request. The
scripted match runner does not consume them.

A one-question live probe on 2026-09-21 verified this alias through
`POST https://openrouter.ai/api/alpha/decisions`. It resolved to
`typesafe/jev-1.13-20260917` on TypeSafe and returned a typed `choice`, a valid
probability distribution and confidence. The synthetic offstage question chose
`recover`; usage was 345 input tokens, 31 output tokens and $0.00001449, with
418 ms observed request latency. This is access proof, not gameplay or latency
certification. The earlier chat-completions probe returned HTTP 400 because Jev
requires the [Decisions API](https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-questions-and-answers-request).
Preserve the leading `~` and record both the requested alias and resolved model
for every experiment, since the alias can move.

The example config validates finite positive duration/request/token/cost/disk
ceilings for future runners. J01 does not spend or enforce a running-session
budget because it has no runner. Changing a config ceiling is not authorization
to purchase credits or silently increase the agreed experiment budget.

Full asset verification currently accepts a raw stock US1.02 ISO/GCM and checks
both its revision header and full SHA-1. Compressed CISO/RVZ/WIA/WBFS inputs are
reported blocked, not corrupt; prepare a separate verified raw image later
without overwriting the original. The existing patched Showboat disc is not a
stock input. Doctor neither extracts nor copies any disc.

## Semantic states and frozen-state evaluation

Live asynchronous policies compile `CompactObservationV1` with named motions,
Battlefield platforms, stocks/stock leader, match time, resources, current skill,
causal history and locally legal candidates. The immutable snapshot is bound to
the provider request and retained in private replay evidence.

```sh
rtk proxy uv run --project agent --no-sync melee-agent corpus build --sources local --split-by episode
rtk proxy uv run --project agent --no-sync melee-agent corpus validate CORPUS_ID
```

These two commands make no provider calls. Evaluation requires an existing
finite ledger, an explicit request bound and the ignored environment file:

```sh
rtk proxy uv run --project agent --no-sync --env-file agent/.env melee-agent corpus evaluate CORPUS_ID --budget EXISTING_BUDGET_DIRECTORY --max-requests 20
```

The paid command evaluates frozen states without launching a game. It reports
model answers and usage, not gameplay success or correct labels. Corpus rows
and raw captures remain ignored. For long semantic captures, see the
[bounded full-match recording profile](../docs/jev-full-match-recordings.md).
See the [semantic-state contract](../docs/jev-semantic-state.md)
for provenance, source hashes, split boundaries and measured acceptance limits.

## Doctor contract

JSON schema version 1 contains `checks`, `capabilities`, `required_capability`,
`status`, `exit_code`, validated `limits` and fixed policy facts. Each check has
an ID, `pass`/`blocked`/`fail`, a public-safe message, remediation and evidence.
User paths, usernames, TOML values and exception details are never interpolated
into public diagnostics. Root/config arguments are local inputs, not outputs.

| Exit | Meaning |
| --- | --- |
| 0 | Selected capability's checks pass. |
| 1 | Invalid configuration, wrong asset/runtime fingerprint, or invalid workspace. |
| 2 | Selected capability needs an external prerequisite or later live validation. |

Default `--require all` reports the most severe check. `--require offline`
permits independent work despite absent live assets, runtime or credentials;
other check failures remain visible in JSON. Other selectors are `host_tests`,
`decomp`, `live` and `provider`.

Pass is scoped to the named probe: tool presence is not a successful build, an
executable checksum is not a successful game, and credential presence is not
account access. The runtime check can validate three retained cold-launch probe
reports for the configured executable; provider access remains blocked until
J09. The port check briefly binds and closes a loopback UDP
socket, sends no packets and reserves nothing. Occupancy can change afterwards;
J04 must own actual port/profile leases.

Doctor performs no application writes, subprocess launches, downloads or HTTP
requests. Python/uv may maintain their own import/install caches; use Python
`-B` or `PYTHONDONTWRITEBYTECODE=1` to suppress import cache writes. Tests use
retained synthetic `/tmp/jev-doctor-test-*` directories, not game assets. If
removing those fixtures, resolve each path and use `/usr/bin/trash` explicitly.

## Agent workflow

1. Read the [roadmap](https://github.com/cmoyates/melee/issues/2), inspect actual
   checkout/status and select an issue whose dependencies are implemented and
   verified. While PRs await review, stack new slices on their dependency branch
   and explicitly name that unmerged dependency; do not claim it has landed.
   Use `gh ... --repo cmoyates/melee`; don't accidentally target upstream.
2. Run doctor. Continue offline work if live prerequisites are missing. A blocked
   live check is not a green skip or proof of gameplay.
3. Use one narrow branch per slice. Record its acceptance command, implementation,
   exact versions/config and evidence. Add a focused regression for actual
   failure paths; don't broaden unrelated Showboat code.
4. Before any later unattended run, use the owned profile, process identity,
   watchdog, explicit budget and launch lease implemented by J03/J04. J01's
   doctor grants no launch lease. Preserve the user's active game and profiles.
   Existing human Showboat testing retains its readiness rules.
5. Preserve immutable evidence under `build/jev/runs/<run-id>/`. Keep original
   assets, DOLs, savestates, private paths, raw captures and secrets out of GitHub.
   After an interruption, inspect owned run identity/completion before restarting;
   never duplicate a game or paid work based on a stale process-name check.
6. Run acceptance checks, inspect their artifacts and open a small reviewable PR.
   Close an issue only with its required evidence; record unresolved prerequisites
   and take another ready issue instead of reporting simulated work as live.
   Do not auto-merge or close unrelated issues.

`work ready`, `run`, `evaluate` and personality
commands in the roadmap are proposed interfaces; `match`, `stop` and `inspect`
are now available as described below. Until the remaining slices land,
use the GitHub dependency UI and existing explicit tools. Never permanently
delete files, reset the worktree, or overwrite historical captures to resume.

## Bounded Jev Decisions adapter

J08 exposes a typed asynchronous `DecisionsClient` and injectable transport.
It preserves observation identity and match context, verifies candidate labels,
finite complete distributions, optional confidence, usage and the currently
verified resolved model. It never writes controller input. The frame-loop
integration and acceptance-age checks remain J10 work.

Initialize an experiment budget once, then explicitly opt into paid probes:

```sh
rtk proxy agent/.venv/bin/melee-agent provider init-budget \
  --directory build/jev/my-experiment --deadline-utc 2026-09-22T10:30:00+00:00 --limit-usd 1
rtk proxy uv run --project agent --no-sync --env-file agent/.env melee-agent provider probe \
  --budget build/jev/my-experiment --timeout 5
rtk proxy agent/.venv/bin/melee-agent provider budget --directory build/jev/my-experiment
```

Choose the actual authorized deadline rather than reusing an expired example.
All runs in one authorized experiment must use the same budget directory;
creating another budget does not authorize additional spending. The append-only
ledger serializes reservations across processes and refuses changed limits,
truncated journals, expired deadlines and exhausted request/token/cost caps.
Costs are integer nano-USD (divide by 1,000,000,000 for dollars). A request
reserves $0.002 and 32,000 input tokens per independent question until validated usage is received;
unknown billing retains the full reservation. A provider exceeding a reservation
blocks subsequent requests. No automatic retries occur. HTTP 429/5xx applies
backoff to future fresh submissions.

Requests use `~typesafe/jev-latest`, TypeSafe-only routing, no provider fallback
and a maximum price of $0.042/M input tokens and $0 output tokens. The known
32k model context costs at most $0.001344 at that rate; identity changes fail
closed pending verification. These routing controls follow the
[Decisions API](https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-questions-and-answers-request)
and [provider routing contract](https://openrouter.ai/docs/guides/routing/provider-selection).

Live HTTP exchanges use an owned short-lived subprocess, stdin credentials,
bounded response size, refused redirects and independent wall-clock deadlines.
Caller deadlines/close invalidate results promptly; in-flight slots remain held
until transport cleanup completes. Submitting/reserving is an off-frame-loop
operation because durable journal writes may block. Offline tests inject a fake
transport and never need a key. Synthetic probe reports establish access and
contract behavior, not latency percentiles or gameplay competence.

### Initial cadence benchmark

```sh
rtk proxy uv run --project agent --no-sync --env-file agent/.env melee-agent provider benchmark \
  --budget build/jev/my-experiment --max-requests 150
```

This submits fresh canned states at 1/2/5 Hz with 5/10/16 choice labels and
one/three independent questions. It records every attempt, refusal, failure,
validated result and actual usage. It uses a new HTTP subprocess/connection per
request; provider cache state is unknown. The choice labels measure request
width and do not imply those controller skills are implemented.

The first 2026-09-22 run produced 100 validated results in 128 attempts:
successful-response p50/p95/p99 were 435/560/868 ms. There were 27 rejected
distribution sums and one timeout, all retained. A diagnostic response totaled
0.99 despite the documented sum-one contract; the adapter continues to reject
it rather than silently normalize reported probabilities. The five-choice,
single-question subset validated 22/22 observations, a small sample.

Initial integration recommendation: one question, at most five choices, 1 Hz,
one in-flight request, maximum accepted action age one second and strict local
fallback on every invalid/late response. This does not certify useful gameplay.
Reports include attempted/submitted/validated rates and age thresholds; latency
percentiles describe successful validated calls only. Post-sweep topups are a
separate phase so their timing cannot distort the original sweep throughput.

## Autonomous local matches

The user has authorized unattended Jev emulator sessions in a separate profile.
Each invocation runs **Fox on port 1 against Mario CPU level 3 on port 2**, on
Battlefield with 4 stocks, 8 minutes and items off. The runtime's stock
Slippi configuration establishes the rules; replay Game Start fields verify them.
No public matchmaking or account login is used. The original Showboat launch
workflow and its profiles remain separate.

Install the optional runtime dependencies once, then use the installed CLI:

```sh
rtk proxy uv sync --project agent --locked --extra runtime
rtk proxy agent/.venv/bin/melee-agent match --policy scripted --duration 600
rtk proxy agent/.venv/bin/melee-agent inspect match-RUN_ID
rtk proxy agent/.venv/bin/melee-agent stop match-RUN_ID
```

`RUN_ID` is the 32-character ID printed at startup (do not duplicate `match-`).
Use `uv run --extra runtime` if invoking through uv; running without that extra
may remove the optional dependencies during environment synchronization.
The local config must pin the runtime executable hash and verified raw disc.
`runtime-lock.json` records the official release URL/checksum and inspected
libmelee commit. The local installation is under `build/jev/runtime/`. The
original compressed disc was verified and converted to a separate raw ISO
with `dtk disc convert`; the original input was preserved. Recreating the local
installation requires the user's game assets and a read-only mount/copy of the
verified official DMG, not a global Dolphin installation.
The prepared local config permits a 600-second wall-clock ceiling; `--duration`
includes setup and is a hard limit, so timeout is reported as incomplete.

The supervisor uses a persistent kernel-lock file to serialize Jev runs and
refuses to start while another Dolphin process is detected. It launches only
owned emulator/controller processes with a new profile for each run. A separate
watchdog process detects CLI disconnection, worker exit, startup/state stalls,
stop requests, time limits and artifact limits. Teardown attempts a neutral
controller packet before bounded termination of the owned emulator. A sent
neutral packet does not prove the game simulated another neutral frame.
Provider credentials are excluded from the emulator and ordinary controller
environments. Explicit `capture --policy jev` passes the key only to its
supervisor/worker; the worker removes it from its environment when constructing
the private HTTP transport. Keys never enter launch manifests or controller packets.

Artifacts live under `build/jev/runs/match-<id>/`:

- `summary.json`: final status, recorded winner, rules, frame continuity and exit reason.
- `replays/*.slp`: native Slippi replay files, with Game Start and Game End events.
- `frames.jsonl`: observations and the next requested controller packet, plus menu transitions.
- `launch.json`, `processes.json`, `worker-result.json`: private run identity and lifecycle evidence.
- `profile/`, `worker.log`, `emulator.log`: retained isolated settings and diagnostics.

Completion is printed as JSON and exits 0 only for verified completion or an
input probe. Timeout, crashes and missing/corrupt result evidence exit nonzero.
Slippi returns directly to character select; the runner requires a recorded
GAME/TIME event before accepting that transition. Unknown placements remain
unknown. `.slp` is replay data, not an MP4 screen recording.

For repeatable infrastructure checks:

```sh
rtk proxy agent/.venv/bin/melee-agent match --policy input-probe --duration 60
rtk proxy agent/.venv/bin/melee-agent match --policy smoke --episodes 10 --duration 600
```

`input-probe` checks observed left/right/neutral input and movement. `smoke`
deliberately walks Fox offstage to exercise real stock loss and end-to-next-game
transitions quickly. Its losses are not a gameplay benchmark. `scripted` is a
basic approach/attack/recovery placeholder that can be replaced through the
shared `TacticalPolicy`/`FrameExecutor` boundary. Jev/OpenRouter calls are not
made by these commands. Frame log schema 4 records the validated observation,
decision, complete requested packet and queue timestamp under `control`.
Controller packets reset every button, both sticks and both analog shoulders.

Observation schema 4 includes each fighter's observed `stocks_remaining` and
`match` context: `time_limit_seconds`, `starting_stocks`,
`elapsed_seconds_derived` and `remaining_seconds_derived`. The configured rules
are eight minutes and four stocks, checked against the completed replay.
Libmelee does not expose the HUD timer: elapsed time is `max(frame, 0) / 60`,
and remaining time is clamped at zero. These are simulation-frame estimates,
not a direct timer read or the supervisor's wall-clock `--duration` limit.
Countdown frames keep elapsed time at zero; episode resets restore the clock
and observed stocks. Policy consumers, including the future Jev adapter, must
retain this context and its derived-time labels. Older observations are rejected
instead of silently assuming four stocks or a fresh clock.

## Asset-free CI slice

```sh
rtk proxy agent/.venv/bin/melee-agent smoke --backend fake
rtk proxy agent/.venv/bin/python -B -m unittest discover -s agent/tests -v
```

The fake source and live libmelee adapter both use the same `FrameExecutor` and
scripted policy. The checked-in synthetic Battlefield fixture covers the main
floor, all three platforms, offstage recovery requests and episode reset. It
asserts complete controller packets against expected outputs, repeats the trace
twice and hashes the canonical result. An intentionally wrong output is tested
to fail the CLI. No emulator, API key, game asset or runtime dependency is needed.
Reports under `build/jev/fake/` explicitly mark live validation **blocked**.

The dedicated `Jev agent offline` GitHub workflow runs on the fork with read-only
permissions and no secrets. Its Linux interpreter loads `agent/src` directly.
Platform surfaces are approximate static geometry from pinned libmelee; derived
support labels are not native collision certification. No new platform tactics
are claimed by this infrastructure change.

Frame logging uses a bounded off-loop writer. Artifact limits are sampled once
per second and can overshoot briefly.
It runs the graphical OpenGL runtime, with background controller input and audio
disabled; headless macOS support has not been established.

## Frame capture and provenance

```sh
rtk proxy agent/.venv/bin/melee-agent capture --policy smoke --duration 600
rtk proxy agent/.venv/bin/melee-agent inspect match-RUN_ID --integrity
```

`capture` continues through completed matches until its configured wall-clock
deadline. A clean, fully drained capture returns `captured` and exits zero. The
last match can be partial, with unknown outcome; this does not count as a win or
a completed match. Normal `match` timeouts still return incomplete. Both modes
use the same supervisor, private profiles, watchdog and configured limits.

Frame schema 4 adds run identity, raw observations, and controller provenance.
The pinned Slippi parser hook retains original post-frame values and availability
flags before libmelee adjusts them. Each fighter has position, action ID/raw
floating-point frame, normalized action frame/adjustment, velocity components,
stocks, percent, hitlag/hitstun, jumps and hurtbox state. A missing or nonfinite
raw optional field is null and marked unavailable; a libmelee default is not
proof that the raw field existed. Unknown animation IDs are preserved.

Fox's internal/native fighter ID is 1 and external selection ID is 2; Mario's
are 0 and 8. Battlefield's Slippi/libmelee ID is 31, while native `GrKind` is
0x24. Mappings are explicit and tested against the decomp headers. Only a small
common motion-state subset has a native mapping; character-specific semantics
remain J18 work. Platform/support geometry and life generations are derived.
The life generation increments on stock loss, including the death/respawn
interval, and resets each episode; it is not a native spawn identifier.

`input_provenance` separates the queued packet from a successfully completed
controller pipe flush and the subsequently observed input values. Value matching
can be ambiguous and never claims a per-packet application receipt. Slippi's
observed analog shoulders contain the game's merged trigger value. The controlled
input probe measures distinct left/right/neutral transition lag separately.

The recorder owns a 256-record queue, serializes/writes on a daemon thread, and
flushes at least every 250 ms while making progress. The producer never waits for
queue space. Queue-full, encoding, short-write, I/O and drain-timeout failures
stop the worker explicitly. Controllers are neutralized before the bounded writer
join. The supervisor still stops a hung worker/emulator. Accepted/written/rejected
counts and remaining unwritten records appear in the final summary; a full disk
can prevent a durable report, in which case stdout reports failure. Flush is an
OS write boundary, not a power-loss durability guarantee.

The read-only integrity command streams the trace, checks record/run/episode
identity and action-frame adjustments, recomputes frame accounting against the
worker summary, and reports stock/grounded transitions and trace SHA-256. A pass
describes trace consistency; consult the separate run status for completion.
The immutable launch manifest records agent source hashes as well as runtime,
disc and dependency identity. Historical frame schemas are not silently upgraded.

## Observed local skills

```sh
rtk proxy agent/.venv/bin/melee-agent skill-check --repeats 20 --duration 600
```

`SkillArbiter` owns one interruptible movement/jump/shield/neutral commitment.
It selects a complete packet through the same frame executor used by fake and
live runs. Movement must show displacement in the requested direction; jumps
must show jumpsquat followed by upward airborne motion; shield must be observed
held for its bounded interval. Success also requires observed input release.
Sending a packet is never sufficient. Missing frames, hitlag/hitstun, death,
respawn, explicit emergency abort and timeouts release input. Noninterruptible
motions and unsafe support edges produce named refusals. Landing is excluded
from start conditions because a jump pressed before the landing window opens
can be ignored and then remain held without a new press edge.

Relative labels (`approach`, `retreat`, `jump_toward`, `jump_away`) resolve the
opponent's side when a skill starts and retain that direction for its commitment.
There is no native CPU fallback for Fox. Waiting/abort behavior is local neutral
input; robust recovery and broader combat are later issues.

The live suite records 20 counted outcomes for each of seven skill/direction
cases, retrying interruptions separately. A counted outcome is observed success
or a specific state-dependent refusal. Every case must have at least one observed
success, and no timeouts may occur for the suite to pass. CPU interruptions are
not counted as successes. The final summary recomputes reported counts from the
trial list; incomplete or failed suites exit nonzero. The replay can be partial
because completing a skill suite is distinct from winning or completing a match.

Observation schema 3 introduced validated fighter details: motion ID/frame, derived
life generation, percent, facing, velocity components, shield strength and
observed input state. Hitlag/hitstun availability is derived from Slippi flags.
RawObservationV2 renames the old `hitstun_raw` field to `misc_as_raw` and records
the state flags: [Slippi's specification](https://github.com/project-slippi/slippi-wiki/blob/master/SPEC.md#post-frame-update)
defines this as a reused motion field that represents hitstun only when its
hitstun flag is set. A still-set flag with zero/fractional remainder conservatively
blocks the skill for the current observation; original values remain in the raw
trace. Earlier v1 captures retain their original field names and source hashes.
Schema 4 additionally retains nullable raw hurtbox state. Unknown availability
refuses grounded combat. Replay older observations on their matching checkout.

Grounded combat commands:

```sh
rtk proxy agent/.venv/bin/melee-agent skill-check --suite ground-combat-v1 --repeats 20
rtk proxy agent/.venv/bin/melee-agent capture --policy heuristic --duration 180
rtk proxy agent/.venv/bin/melee-agent capture --policy random-legal --duration 180
```

These are offline provider modes. Jab, down-tilt and grab share observed skill
commitment and local recovery; both selectors use the same legal candidates.
For comparisons with the grounded Jev catalog, use the separately named
`heuristic-tactical` and `random-tactical` profiles. They share the complete
legal choice set with Jev; local timing and provider latency remain distinct.
See [shared tactical baselines](../docs/jev-tactical-baselines.md) for the
profile, fixed CLI seed, retained historical modes and live validation limits.

See the [grounded combat contract](../docs/jev-grounded-combat-contract.md) for
motion, contact, capture and completion distinctions and current live evidence.

## Delayed decision boundary

```sh
rtk proxy agent/.venv/bin/melee-agent capture --policy delayed-fake --duration 300
rtk proxy agent/.venv/bin/melee-agent inspect RUN_ID --policy-evidence
```

The `ordering-v1` fake backend uses four fixed threads and 0–2000 ms delays,
including duplicate, out-of-order, forged-context and invalid-choice replies.
It never contacts OpenRouter. There is one replaceable state snapshot and a
32-entry reply mailbox; the frame loop skips a busy mailbox without waiting.
Backend calls and any future provider accounting stay off the input thread.

Each reply is bound to its original run, episode, both derived life generations,
frame, monotonic observation time, request sequence, candidate hash, skill
generation and stage/support/opponent-side context. Application rechecks all
bindings, current legality, a one-second age limit and a 60-frame age limit.
Only a newer **applied** decision supersedes an older result. A newer request
submission alone does not invalidate an otherwise useful reply.

The local arbiter preserves active skills, releases them for emergencies and
uses bounded local approach/neutral fallback while waiting. Offstage emergency
input uses the existing temporary scripted recovery, pending the dedicated
recovery slice. No native CPU takes over Fox. The trace records every consumed
reply and its acceptance/rejection reason. The independent audit checks each
accepted choice against both retained source and application observations,
measures observed-to-queued/flushed latency, and checks bounded worker shutdown.
These timing metrics describe input delivery, not proven game application time.

## Real Jev match capture

```sh
rtk proxy uv run --project agent --no-sync --env-file agent/.env melee-agent capture \
  --policy jev --duration 150 --budget build/jev/overnight-20260922 --max-requests 110
rtk proxy agent/.venv/bin/melee-agent inspect RUN_ID --policy-evidence
```

Use an already initialized budget owned by the current experiment. The example
names the overnight experiment; its deadline is immutable, so it will refuse
paid work after that experiment ends. A run cap never resets the shared ledger.
The explicit Jev policy uses the same mailbox, arbiter, fallback, emergency
behavior and one-second/60-frame freshness gates as the delayed fake. Only the
backend changes: one in-flight Decisions request at most, no retries, one
question, at most eight described skills and a one-second response deadline.
The budget reservation and HTTP call run entirely outside the input thread.

The 150-second capture leaves room for setup plus at least two continuous
minutes of play. It retains a partial final replay and does not claim a match
win. Provider reports retain every request outcome, validated probabilities,
requested/resolved model, usage, configuration hash and ledger snapshots.
Replies discarded during shutdown remain explicitly accounted for. Shutdown
checks transport workers/timers and active HTTP exchanges, then reports failure
if any remain. The native CPU never takes over Fox.

`--policy-evidence` independently checks accepted choices and their raw motion
acknowledgements, reports input ownership/fallback participation, and exposes
`live_acceptance.criteria_met` for the two-minute, 20-observed-success,
three-skill-class tracer-bullet criteria. The general audit can pass with fewer
opportunities, so consult that separate field when certifying J11. Confidence
values are retained as model output, not interpreted as win probabilities.

The grounded tactical slice adds locally legal jab, down-tilt and grab choices.
Its `combat_outcomes` audit separates raw native starts, clean completions,
damage-contact indicators and actual captures, including interrupted skills.
For an actual match result rather than a time-bounded capture, `match` also
accepts `--policy jev --budget EXISTING_DIRECTORY --max-requests N`; the same
explicit provider limits apply. Live combat acceptance remains separate from
the historical movement-only pilots and is recorded in the linked contract.

## Runtime failure soak

```sh
rtk proxy agent/.venv/bin/melee-agent soak --budget build/jev/overnight-20260922 --duration 1800
```

`runtime-v1` runs a fixed sequence of terminal fault cases followed by longer
network, missing-frame and rate-cap cases until thirty minutes have elapsed.
Each episode remains bounded by the ordinary supervisor and artifact limits.
It uses the real Decisions adapter with an injected in-process transport and
explicitly simulated ledgers inside each run. It has no OpenRouter key or
external HTTP transport; the named paid ledger is only read before/after to
prove it remained unchanged. Simulated reservations are not real spending.

The schedule covers disconnect, 429/529, malformed/invalid distributions,
low confidence, cancellation, two-second response stalls, circuit recovery,
logger backpressure, frame loss, executor failure, worker death and a blocked
controller write. Three consecutive provider failures open a two-second
circuit; recovery uses the latest observation. Present confidence below 0.15
is rejected conservatively, without treating confidence as win probability.

Terminal cases are expected to produce incomplete matches. Certification checks
the expected failure, bounded teardown and available evidence separately. A
killed worker cannot confirm a final neutral packet; its report explicitly
retains that unknown while requiring the emulator/receiver processes to exit.
The logger-stall case drains accepted records and preserves the last rejected
record in the summary for the policy audit. No failed capture is relabeled as a
complete match.

The pinned libmelee receiver joins its subprocess before closing the read side
of its IPC pipe. A full pipe can therefore prevent shutdown indefinitely. The
adapter closes that owned read end first, then uses bounded join/terminate/kill
steps on the exact multiprocessing process object. It refuses unexpected
emulator or temporary-home ownership. The normal supervisor remains independent
of the controller loop and retains its terminal watchdog.

Soak artifacts live beside the existing experiment ledger under `soaks/`.
Per-phase JSON records audited decisions, input timing, fault counts, cleanup
time, receiver liveness and an unrelated sentinel process. The first failed
phase stops certification; retained failures are investigated before a rerun.

## Explain and replay an incident offline

```sh
rtk proxy agent/.venv/bin/melee-agent explain RUN_ID --episode 1 --frame 600
rtk proxy agent/.venv/bin/melee-agent explain RUN_ID --request-id REQUEST_ID --after-frames 60
rtk proxy agent/.venv/bin/melee-agent replay-incident build/jev/incidents/INCIDENT_ID --verify
```

After a failed acceptance command, inspect the retained run and select the first
relevant frame or consumed request ID. `explain` extracts a private sealed bundle
and prints a shareable summary. It distinguishes the queued decision, latest
completed controller flush and observed skill event; contact and causal match
outcome remain unmeasured. Raw observations, provider answers, candidate bindings,
transitions and packets stay under ignored `build/jev/incidents/`.

Replay feeds the recorded observations and reply deliveries through the same
`AsyncPolicy`, skill arbiter and frame executor. Exact executor/policy/queue clocks
and mailbox-busy observations are recorded at their existing reads; replay never
constructs a provider, emulator, controller or network transport. It verifies the
bundle's checksums, record order, schemas, rules, pinned runtime/disc/dependency,
policy source and provider configuration before executing the prefix. Verification
is mandatory even without the `--verify` spelling. No game assets are read.

The prefix starts at the run's first game observation rather than inventing a
policy checkpoint. Extractions are bounded to 40,000 game records and 128 MiB;
the selected frame may include up to 300 following frames. Historical captures
without exact timing or matching policy source can be explained but explicitly
cannot be certified as exact replays. Restore the matching source checkout to
replay an older contract; never rewrite its declared hashes to make it pass.

Replay stops at the first changed decision, packet, acceptance or skill state.
Subsequent historical observations are not a counterfactual game future. For a
confirmed bug, reduce the relevant observations into an asset-free synthetic
fixture and assert the intended narrow behavior. The included stale-response
regression fails with a deliberately weakened freshness guard and passes with
the real guard; two unchanged replays yield identical decision/packet hashes.
Live gameplay improvements still require new supervised matches.

## Fresh-match mechanical scenarios

```sh
rtk proxy agent/.venv/bin/melee-agent scenario-run --name offstage-left --duration 30
rtk proxy agent/.venv/bin/melee-agent scenarios --suite mechanics-v1 --repeats 10 --duration 2400 --seed 0
```

The fixed `ScenarioV1` suite covers left/right grounded spacing, rising jump and
landing, recoverable offstage positions, actual ledge catch/hang, and a shielding
opponent. Each trial launches a fresh stock Fox versus Mario CPU3 Battlefield
match. The manifest declares its target predicate, setup inputs, resources,
timeouts, rules and outcome. Setup uses ordinary controller packets, then requires
a queued and observed neutral release before the measured policy takes ownership.
No positions, velocities, states or timers are written. Savestate loading is not
implemented; an alternate state/build cannot be passed through this interface.

`--seed` controls trial ordering only. Game/CPU RNG is not seeded, so repeatability
means reaching the declared observed predicates, not identical emulation. Every
run retains its initial observation and hash, source/runtime/disc identity,
setup/measurement boundary, raw frames, replay settings and separate outcome:
`setup_failed`, `skill_failed`, `succeeded`, or `timeout`. A setup failure never
starts the measured skill. The initial offstage probe uses the existing scripted
baseline; it is not the later Fox recovery FSM. Returning to any known Battlefield
platform or the ledge counts as regained stage support.

The suite stores its manifest, per-trial audits and aggregate summary under
`build/jev/scenarios/`. Audits cross-check observations against raw Slippi fields,
setup release and ownership, actual movement/landing/shield evidence, replay rules,
recorder integrity and process cleanup. An audit failure stops the schedule.
`scenario_recorded` and a completed suite mean the outcome was retained and
validated, not that the tested skill succeeded. The suite stops before its wall
deadline or 2 GiB artifact cap; each child has its own thirty-second limit.

The initial pilot reached and passed all six mirrored movement/airborne/offstage
cases. Ledge hanging and a shielding CPU did not reach setup within eight game
seconds. Those remain explicit setup limitations for later mechanical work;
they are not silently replaced with easier predicates.
