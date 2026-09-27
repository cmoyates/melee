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

## Native port-2 results

After the frozen thirty-match J19 cohort completed, two free full matches
validated the local and asynchronous paths on source `de8f2a09e`:

| Policy | Run | Wall seconds | Exact game records | Result, Fox–Mario |
| --- | --- | ---: | ---: | --- |
| heuristic-tactical | `match-b75d5fbb23e647ecbf3a2841cb2366ec` | 302.85 | 17,308 | 0–4 |
| delayed-fake | `match-ce46421919d44ea7844390e05fd023d9` | 332.65 | 19,088 | 0–4 |

Both replay headers identify human Fox on port 2 and Mario CPU3 on port 1, with
the expected Battlefield stock/timer rules. Both native winners are port 1,
while canonical final stocks are `[0, 4]`. Raw integrity, source identity,
complete results and owned cleanup passed. All 36,396 canonical observations
and legal-candidate sets matched standalone Slippi extraction exactly, with
zero unmatched states. Standalone files do not recover historical skill
commitment; the complete controller traces were checked separately.

The local controller replay matched all 17,308 records. The asynchronous sealed
replay matched all 19,088 records and 192 accepted choices, with zero raw policy
audit errors. Native acknowledgements included fifteen completed Nairs, two
approach-jabs, two down tilts, one jab and one grab. The Nair landing durations
were fourteen seven-frame landings and one fifteen-frame landing; an attempted
L-cancel is not automatically a reduced-lag success. Thirteen skills aborted
and remain in the result. The fault backend supplied stale, duplicate, invalid
and misbound responses; none bypassed the apply-time guards.

Sealed incident: `incident-2ed7be433e914a579cdcace57942dc98`.
Asynchronous packet SHA-256:
`883ff5c2a577f9f493d2e168a4650f88190dbc295045fd6ba58a9a9f4b19a220`.
Local packet SHA-256:
`1866c86038676ca01808b886f4481afc79cf2abbb618335505510ea32df794bb`.

The audits ran with network and subprocess creation blocked. All five spending
journal hashes remained unchanged across both matches and their audits.
These results establish the explicit controller-role contract, without claiming
playing strength, paid-model port-2 performance or a held-out tournament.
