# First paid live option match

`match-84292a351ef9431a97a99b54bbf78220` completed a stock Fox vs Mario CPU 3
match on Battlefield, losing 0-4 after 303.35 wall-clock seconds. This is a
successful execution experiment and a lost game, not evidence of better play.
The existing Showboat baseline and stock assets were untouched.

The explicit `approach-jab-v1` profile used the same request identity, age,
confidence, legality, reflex and interruption checks as the atomic profile.
At most 200 attempts were allowed; actual request source frames spanned 0-16521.
The remaining match tail used the existing local fallback after the cap.
All 200 HTTP calls are retained: 196 valid distributions, three rejected
distribution sums and one transport timeout. Valid response latency was
424.5 ms median and 537.1 ms p95. All valid answers resolved to
`typesafe/jev-1.13-20260917` through TypeSafe.

| Decision stage | Observed result |
|---|---|
| Valid model choices | 196 |
| Accepted choices | 121: 99 approach, 20 approach-jab, one jab, one shield |
| Selected approach-jab | 40 |
| Accepted approach-jab | 20 |
| Completed approach-jab | 16: six with walking first, ten immediate jabs |
| Interrupted accepted options | One opponent guard/capture transition, three hitlag interruptions |
| Raw walking acknowledgements | Seven across completed/interrupted options |
| Raw option jab acknowledgements and contacts | 16, all completed |
| Separate ordinary jab | One acknowledged/completed jab with one contact |

The full run's provider-owned input fraction was 7.25%. Source-state diagnostics
retained 29 requests from frames offering an atomic combat action (29 valid,
nine accepted) and 171 from other grounded frames (167 valid, 112 accepted).
These are source usability bins, not inferred tactical phases or causal scores;
the latter bin can offer approach-jab. Damage/airborne frames and local recovery
remain in the recording and denominator.

All 17,357 game frames passed raw integrity and policy audits, with zero gaps,
duplicates or rollbacks. Stock rules, final GAME result, Mario winner and owned
cleanup were verified. The recording retained 192,890,609 bytes without recorder
loss. All launch module hashes remained unchanged during the match.

The first sealed replay attempt correctly failed closed at
`provider_config_mismatch`: its verifier accidentally compared the recorded option
profile against the default atomic profile's configuration hash. The audit fix
uses the sealed declared profile when computing that hash, while a mismatched
atomic hash still fails. A network/process-blocked host regression covers both
paths. The controller sources were not changed or reinterpreted. With the fixed
audit tool, the full sealed replay reproduced all 17,357 decisions and packets
exactly without launching an emulator or contacting a provider.

- Frames SHA-256: `586a177ee1e795b6b053f418c7dd7d847092b0fea41f7a81ae05805c94f64666`
- Replayed packets SHA-256: `fb723446449d6bda3075f136c2f701bf5f2f19b2e780c11272417ec421343dd4`
- Private incident: `incident-d86816a029c54fd1ac0b8189a0b60743`
- Provider config SHA-256: `695f4de8a0ff5a8f095ae1223d02f52911d7dfff747ca17ab510cc42a4c15055`

This match reported $0.015288672 and retains a $0.002 reservation for the unknown
timeout charge: $0.017288672 accounted. Across the original conserved ledger
chain, total accounted spend is **$0.125386014 / $1**, including $0.012 in four
uncertain reservations. The active experiment inherited only unspent dollars;
no prior ledger or allowance was reset. It has forty requests remaining.

All 341 host tests pass with the replay correction. This single full game does
not satisfy the ten-match comparison gate or mechanical reliability gates.
The prior delayed-fake native capture completed an immediate option jab, while
the 500 ms host fixture exercised walking then jab; the live paid match now adds
six complete delayed walking sequences. The different evidence layers remain
explicit. Full native Sudden Death transition proof is still pending.
