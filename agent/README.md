# Jev agent workspace

Fox first; build the common foundation for natural-language personality control
and a future Showboat Captain Falcon. Existing Showboat remains a separate
historical implementation and baseline.

The workspace includes bootstrap, doctor, and a first supervised local match
runner. Paid inference and personality control are not implemented yet. The
scripted policy is a temporary controller test; it is not a Jev-powered bot.

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
files. The production inference adapter and broader provider checks belong to
J08/J09; adding these settings does not make an API request. The model setting
is reserved for that adapter; the scripted match runner does not consume it.

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
   checkout/status and select an open issue whose native blockers are closed.
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

`work ready`, `match`, `run`, `stop`, `evaluate`, incident replay and personality
commands in the roadmap are proposed interfaces; `match`, `stop` and `inspect`
are now available as described below. Until the remaining slices land,
use the GitHub dependency UI and existing explicit tools. Never permanently
delete files, reset the worktree, or overwrite historical captures to resume.

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
Provider credentials are excluded from emulator and controller environments.

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
made by these commands. Frame log schema 3 records the validated observation,
decision, complete requested packet and queue timestamp under `control`.
Controller packets reset every button, both sticks and both analog shoulders.

Observation schema 2 includes each fighter's observed `stocks_remaining` and
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

This first runner uses buffered synchronous frame logging with watchdog shutdown
on stalls; an off-loop logger and richer per-packet flush provenance remain J06
work. Artifact limits are sampled once per second and can overshoot briefly.
It runs the graphical OpenGL runtime, with background controller input and audio
disabled; headless macOS support has not been established.
