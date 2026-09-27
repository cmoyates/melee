# Retained policy batch reports

The [completed thirty-match cohort](jev-j19-cohort-results.md) now has full
native evidence: all audits pass, with ten losses per policy. The earlier
checkpoints below remain historical snapshots.

Issue #82 adds a read-only report for the checkpointed J19 cohort. It reads
committed audits from a single batch, verifies the retained artifact hashes, and
prints JSON or Markdown without launching Dolphin or contacting OpenRouter:

```sh
uv run --project agent melee-agent batch report BATCH_ID
uv run --project agent melee-agent batch report BATCH_ID --format markdown
```

`--workspace PATH` reads another checkout's private evidence. Reporting does not
require that checkout's controller to match the reporter's current controller.
The original module, local configuration, runtime, provider configuration,
manifest and journal hashes remain in the output. This is historical evidence
inspection; it does not rerun the controller, replace an audit, adopt an unknown
child or authorize resuming a changed experiment. Execution commands retain
their stricter source and exact-ledger checks.

The reader verifies the manifest/journal/audit chain, unique children, schedule,
launch identities, recorded summaries, every retained match artifact, paid
sealed-replay files, and the recorded spending prefixes. It recomputes the
accounting at each prefix; later ledger activity is outside the report. A
changed journal during inspection refuses the report, with no automatic retry.
A pending child is displayed without inspecting its changing files or counting
its requests as audited spending. Unjournaled audits remain pending.

Both formats describe the same snapshot. Markdown includes a short comparison
table and the complete public JSON, including per-match phase and latency
metrics. The output allowlists fields and excludes raw observations, private
paths, prompts, response payloads, provider request IDs and credentials. The
recordings stay local.

## What the numbers mean

- Wins and losses use passed audits only; failed, pending and unattempted slots
  remain visible. A failed match is not silently scored as a loss or retried.
- Wilson 95% intervals describe binomial sampling uncertainty. They do not
  establish independent draws, control selection bias or prove Jev is stronger.
- Per-match submitted attempts, HTTP calls, validated answers, accepted choices
  and raw acknowledgements remain separate. Missing phase or provider evidence
  is unavailable, not zero. Free policies have no provider metrics.
- Phase frames describe the current state; request counters and completions use
  their request source; application counters use the delivery state. These are
  participation counts, not correctness labels or causal attribution.
- Latency percentiles stay per match. Never average those percentiles and call
  the result a pooled latency percentile. Observation-to-queue timing excludes
  later flushing; it is not end-to-end input latency.
- Spending covers committed audits in this cohort, not earlier experiments or
  the pending child. Integer nano-USD preserve exact accounting. Reported charges
  and unknown reservations remain distinct; unknown charges stay reserved.
- Game-start RNG values are observed from each hash-verified Slippi replay's
  big-endian GameStart field at `0x13D`, as specified by the
  [Slippi specification](https://github.com/project-slippi/slippi-wiki/blob/master/SPEC.md#game-start).
  They were not configured or reinjected. Different observed seeds do not make
  these games paired or reproducible. Unsupported old event lengths or an absent
  optional runtime decoder return null; artifact hashes still verify.
- The bot is port 1 in this J19 schedule. This is not the held-out, both-side
  J20 strength tournament. Loss recordings support diagnosis; the report does
  not label a death as a self-destruct or assign damage to an action.

## Validation

Asset-free tests cover valid, failed, empty and pending schedules; unknown paid
charges; later ledger activity; unavailable provider fields; historical source
changes; manifest/audit/frame/ledger tampering; path escape; journal races and
partial writes; JSON/Markdown parity; and execution with network/process creation
blocked. An initial 408-test local run passed; CI then exposed a new test's
unconditional dependency on the optional runtime codec. The corrected tests
mock only the outer codec, exercise real event bytes, and explicitly cover
reporting without that codec installed. Native verification below uses the
installed real decoder.
The corrected full suite passed all 409 tests with `python -S -B`, disabling
site packages to reproduce the dependency-free CI environment. Real native RNG
extraction was rechecked after the fix; all eight retained seeds were available.

The first real inspection used the separate reporting checkout against frozen
batch `batch-17fa1c8b61fb4a2988cc42fb73e62b06`, with network and process creation
blocked. It verified eight committed native matches and displayed slot 8 as
pending. All eight were losses, with no failed audits. This is an interim
snapshot while matches continue, not the final cohort result.

The JSON digest was
`e2caec0678944423e9f51038298b23e5e3ea31c85c0c69f188fc740269d68bf2`;
the Markdown digest was
`740fd6a218f6221e5a067a8cb3b9141154017292a1b3b636917d98bce1dcc0ca`.
Its embedded JSON exactly matched the JSON artifact. The reporting run left the
frozen controller/config identity unchanged. All 578 validated responses across
the three Jev matches recorded `typesafe/jev-1.13-20260917` through TypeSafe,
requested as `~typesafe/jev-latest`. Cohort accounting through slot 7 was
$0.058390050, including $0.012 in unknown reservations; this excludes earlier
experiments and any subsequent calls.
