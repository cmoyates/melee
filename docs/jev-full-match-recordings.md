# Bounded full-match recordings

Semantic traces contain both raw observations and the compact state that the
provider saw. A measured 6,618-frame capture occupied 71,813,831 bytes. At that
rate an eight-minute match requires roughly 312 MB of frame records before
replay and diagnostic files. The original 256 MiB artifact budget can stop such
a capture before its configured time limit.

The short-run default stays 256 MiB. Full-match testing can explicitly set these
values in ignored `agent/local.toml`:

```toml
[limits]
max_run_seconds = 600
max_artifact_bytes = 536870912
```

The supervisor rejects artifact budgets above 512 MiB before opening runtime
assets or starting processes. Seven eighths of the artifact allowance belongs
to frame recording; the rest accommodates replay and diagnostics. The existing
watchdog, elapsed-time limit, bounded writer queue, recorder failure handling
and aggregate artifact stop remain active. This is a finite capacity ceiling,
not a guarantee that arbitrarily verbose or multi-episode captures fit.

Incident extraction, source hashing, corpus building and frozen evaluation use
the same 512 MiB source-file ceiling. Compact incident prefixes allow 256 MiB,
with the existing 40,000-game-record and 64 KiB single-record limits. Symlinks,
non-regular files, oversized files and malformed/truncated records still fail
closed. Slippi replay limits are unchanged. Corpus compiler provenance includes
the shared limit module; old corpora retain their original compiler identity
and should be validated on the matching checkout rather than resealed.

For a free integration run with semantic states and simulated delayed replies:

```sh
rtk proxy uv run --project agent --no-sync melee-agent capture --policy delayed-fake --duration 540
```

Inspect the resulting summary and integrity/policy evidence, then export and
replay its complete gameplay prefix. A bounded capture can end mid-match or
contain multiple episodes. A completed match still requires the independent
observed result event and finalized replay winner; increasing storage does not
turn a capture into a match result.

## Live capacity validation

On September 26, run `match-f5c0d313437a4ffe86f12a4a46b1f5ed` captured 540
configured wall seconds (541.27 including shutdown) using code `4af11ac2b`,
512 MiB total artifacts and 448 MiB frame allowance. All 31,900 recorder rows
were written: 340,664,880 bytes, exceeding the previous 256 MiB source ceiling.
The queue high-water was one. There were 31,497 game frames across two episodes,
with zero gaps, duplicates or rollbacks, at 59.87/59.97 observed FPS.

The first episode reached the stock eight-minute timer; both the observed
result and finalized replay identify Mario as winner, with stocks three to
four. The second episode was stopped by the capture deadline and has no winner.
Both replay rule checks passed, and controller neutralization plus worker,
emulator and receiver shutdown completed. No provider was contacted; the paid
ledger remained at 1,000 requests and $0.073249428 for that experiment.

With sockets and subprocess creation forbidden, incident
`incident-9790198f619740c89f4e556befa11799` reproduced every semantic state,
decision and controller packet across all 31,497 game records. Its compact
prefix occupied 177,696,909 bytes, also exceeding the previous 128 MiB prefix
ceiling. All 88 accepted simulated decisions had observed skill acknowledgements;
invalid, reordered and expired replies remained rejected. Raw integrity and
policy audits passed.

The same long source was included through normal corpus source selection in
`corpus-4dac380db62c43a2920b0703616df64a`. All 4,684 compiled states across
sixteen source episodes recompiled exactly. About 58 GiB disk space remained
after recording and analysis. Agent CI and native build passed; the existing
repository-wide formatting check retained 190 baseline errors, cancelling the
other style jobs through fail-fast.

Frame SHA-256:
`7d3764d04df1ad0338449cc6b585bf4b0e67d04668577e3f248c062578e3cd08`.
Replayed packet SHA-256:
`631adb20c834e4159f5bbcca751a54e4753ffb9bb6c2c820a9ffdff08c14cd80`.

This passes recording capacity and exact replay, not tactical strength. The
long run exposed a separate platform-edge problem: native grounded Fox can
stand slightly beyond the static platform interval, producing unknown support
and a persistent conservative reflex failure. That gameplay defect needs its
own regression and live validation before full-player acceptance.
