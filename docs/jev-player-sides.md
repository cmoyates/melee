# Explicit Fox controller roles

Issue #84 prepares the both-side prerequisite for J20. A single supervised match
can request Fox on port 2 and Mario CPU3 on port 1:

```sh
uv run --project agent melee-agent match --policy heuristic-tactical \
  --profile fox-aerial-v1 --bot-port 2 --duration 600
```

The default remains Fox on port 1. The CLI forwards the explicit side through the
supervisor launch contract. The worker constructs its controlled controller for
that port, binds input tracing and packet output to it, and assigns the other
controller to Mario's menu setup. It checks native characters, CPU levels,
Battlefield, stock count and timer before recording a segment. No tactical
selector, skill, recovery reflex or cloud setting changes with the port.

## Recorded identities

Native player indices remain intact in Slippi and the raw recordings. Canonical
`observation.bot` always describes Fox; `observation.opponent` describes Mario.
Coordinates stay in the original world coordinate system. This does not mirror
coordinates or convert an action's facing direction.

Port-2 launches, summaries, episodes and sealed incident provenance include
`bot_port: 2`. Their gameplay records use frame schema 5 and require an explicit
`bot_port`. Historical frame schema 4 means port 1. A missing, invalid or
conflicting role refuses the relevant audit instead of silently choosing port 1.
The integrity audit additionally checks native fighter IDs, normalized actor
positions/actions/percent, stock/life binding and the controlled player's
observed main stick.

`winner_port` remains the native winner port. Episode `last_stocks` remains in
canonical **[bot, opponent]** order; raw stock maps remain keyed by native port.
For example, Fox on port 2 losing to Mario on port 1 records `bot_port: 2`,
`winner_port: 1` and final stocks such as `[0, 3]`.

Raw movement, attack, grab, approach-jab and aerial acknowledgement checks use
the declared bot's native record. Exact offline control replay still uses
canonical observations and sends no controller input. Corpus cases preserve the
actual side in their source metadata without changing an otherwise identical
canonical semantic state. The role adapter is included in compiler hashes;
historical corpora still require their original compiler checkout. Standalone
replay extraction accepts an explicit `bot_port=2` with matching replay rules.

## Boundaries and validation

Mechanical scenarios, skill-check suites and fault injection remain port-1-only;
port-2 requests for them refuse before provider preflight or process creation.
The existing checkpointed J19 batches also remain port-1-only. This change does
not add mixed-side schedules or reinterpret their historical win counts. A
future evaluation suite must explicitly declare both sides before launch.

The implementation was prepared in a separate checkout while the frozen J19
cohort continued unchanged. All 420 dependency-free host tests passed. The new
coverage exercises asymmetric actors and inputs, actual worker controller
ownership, native winner attribution, supervisor rejection of mismatched roles,
raw combat/aerial acknowledgement, sealed option replay, corpus parity and
missing/conflicting role rejection. The focused role tests also passed after
the final type-validation hardening.

Native port-2 acceptance is **pending**. After the frozen J19 cohort completes or
records a stop, the first tracer match will use the free heuristic selector on
Battlefield. Retain its full recordings, verify raw integrity and exact local
replay, check observed native action acknowledgements and replay extraction
parity, confirm stock rules/result and owned cleanup, and keep failures visible.
Do not count a mock worker or a successful menu launch as native side-swap
acceptance. This slice makes no playing-strength or held-out tournament claim.
