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

Live capacity validation: pending a fresh run that crosses the old 256 MiB
source-reader ceiling and passes complete offline replay.
