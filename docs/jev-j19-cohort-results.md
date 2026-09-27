# Frozen J19 development cohort

Batch `batch-17fa1c8b61fb4a2988cc42fb73e62b06` completed all thirty scheduled matches on one unchanged controller implementation. Every match passed retained recording integrity, exact control replay, rules/result and owned-cleanup audits.

Stock Fox played Mario CPU3 on Battlefield, four stocks/eight minutes, with Fox on port 1. Ten round-robin repetitions used the same `fox-aerial-v1` catalog, executor and emergency reflex. Jev had an explicit 200-request cap per match; its fallback tail remains part of each result. Local policies have different inference latency. Game RNG was observed, never configured or paired.

| Policy | Verified | Wins | Losses | Failed | Win fraction, Wilson 95% |
| --- | ---: | ---: | ---: | ---: | --- |
| jev | 10 | 0 | 10 | 0 | 0.000 [0.000, 0.278] |
| random-tactical | 10 | 0 | 10 | 0 | 0.000 [0.000, 0.278] |
| heuristic-tactical | 10 | 0 | 10 | 0 | 0.000 [0.000, 0.278] |

These are development integration results. They do not establish held-out strength, paired policy differences, both-side coverage or equivalence between policies. Existing mechanical clean-completion gaps and full native Sudden Death coverage remain separate. No failed historical cohort was replaced or relabeled.

## Jev participation

1999 backend attempts, 1999 HTTP calls and 1999 reservations; 1945 valid replies and 1176 accepted choices. Provider-owned frames: 21,566/213,178 (10.12%). Ownership is measured across retained game-state observations, including countdown and fallback tails.

| Request-source phase | Attempts | Valid replies | Accepted choices | Completed skills |
| --- | ---: | ---: | ---: | ---: |
| grounded_aerial_only | 587 | 562 | 371 | 347 |
| grounded_atomic_combat | 209 | 206 | 56 | 53 |
| grounded_option_only | 151 | 147 | 72 | 62 |
| grounded_other | 1024 | 1003 | 659 | 626 |
| inactive | 28 | 27 | 18 | 17 |

Phase rows use the original request-source classification; successful application and completion can occur in a later phase. A completed skill is not necessarily a hit. Full reports preserve separate application-phase and ownership tables.

Raw skill audit totals: `aborted` 69, `observed:approach_jab` 39, `observed:dtilt` 26, `observed:grab` 2, `observed:jab` 10, `observed:move` 634, `observed:neutral` 3, `observed:sh_nair` 388, `observed:shield` 3, `timeout` 2.

Resolved response identities: `~typesafe/jev-latest` → `typesafe/jev-1.13-20260917` via `TypeSafe` (1945 valid responses).

Latency is retained per match in the JSON report; no average of per-match percentiles is presented.

## Spending and provenance

This cohort accounted for $0.184776132: $0.154776132 reported charges and $0.030000000 retained uncertain reservations. All five experiment journals total **$0.313272330 of the original $1 cap**, including $0.042000000 uncertain reservations. The four ancestor journal hashes were rechecked unchanged.

Frozen controller implementation: `52233a65a`; original native/Showboat baseline remains separate. Per-module, runtime, prompt/config, frame, packet, replay and observed RNG hashes/identities are retained in the report.

- Manifest SHA-256: `cf9a78c054f1789d440ba7cc1bbf218f29b9ad25879f4f16bf6c25ebb0e4c27e`
- Journal SHA-256: `49acc0ceb4a44afff673afa609a8b32fbdb684273b96611e29b64ebe87adaa26`
- Final paid ledger prefix SHA-256: `4e1e9681416e7c4b49a343852c5a1f627934c81f9ab80d8addb55e2e2d8162c2`
- JSON report SHA-256: `cd888386a66a63cb01ec27863ae1cd14aba6ea1ebad38a6074ed5a0560ce56e6`

Regenerate JSON or full Markdown from retained local artifacts using `melee-agent batch report batch-17fa1c8b61fb4a2988cc42fb73e62b06` and optional `--format markdown`. Historical reporting verifies artifacts without requiring the current controller source; resuming a cohort still requires its original frozen source and configuration.

## Individual matches

| Slot | Policy | Run | Final stocks, Fox–Mario | Wall seconds | Recorded game frames |
| ---: | --- | --- | --- | ---: | ---: |
| 0 | jev | `match-ec61d1621b9e441b8f4c5b0f1a410c10` | 0–3 | 294.91 | 16830 |
| 1 | random-tactical | `match-68c09c66869b481daf9bdc1826906c56` | 0–3 | 369.26 | 21308 |
| 2 | heuristic-tactical | `match-c3f87b6851fd4d46b83017c405eebc97` | 0–3 | 310.63 | 17778 |
| 3 | jev | `match-65d28277bb8f45c09402a9a0c7bdc893` | 0–3 | 382.70 | 22120 |
| 4 | random-tactical | `match-ce64065ba5c7407abcff5ed1bfe4b05e` | 0–3 | 462.24 | 26861 |
| 5 | heuristic-tactical | `match-9bae4e83e5f5411c86de2a9a5244eee4` | 0–3 | 330.19 | 18971 |
| 6 | jev | `match-0f09a695a3914219885e22469bb66580` | 0–3 | 380.38 | 21967 |
| 7 | random-tactical | `match-2b7fe133d16c4ca684aad1a2459e54a6` | 0–3 | 414.40 | 24001 |
| 8 | heuristic-tactical | `match-bdb1a0311c494ca49ae3cfe213cdce26` | 0–3 | 365.56 | 21072 |
| 9 | jev | `match-94a0fa1fd8e940939913739f113cfde9` | 0–3 | 402.38 | 23280 |
| 10 | random-tactical | `match-9e914e041928417e8d20a65c7633aeed` | 0–3 | 421.94 | 24471 |
| 11 | heuristic-tactical | `match-826c7cac0d874583b8da00cca50ad4b8` | 0–3 | 368.17 | 21245 |
| 12 | jev | `match-1297189a7d4b4191a6af665d57bb2aaf` | 0–3 | 344.59 | 19812 |
| 13 | random-tactical | `match-a6d5e5a550254f049aecd5529f55df1c` | 0–3 | 355.13 | 20464 |
| 14 | heuristic-tactical | `match-31d5f30c5f484d68828b529e31c46bf9` | 0–4 | 228.34 | 12852 |
| 15 | jev | `match-3b423a2b064849de93262abb634dd43d` | 0–3 | 347.75 | 20002 |
| 16 | random-tactical | `match-9e5c0135cb96457294dfed5d8fa8e1d6` | 0–3 | 368.81 | 21267 |
| 17 | heuristic-tactical | `match-9a42ba667f414173a84b4d0a069779d3` | 0–3 | 317.23 | 18170 |
| 18 | jev | `match-b8a87f843df044bc99103fd2d093c78d` | 0–3 | 407.69 | 23593 |
| 19 | random-tactical | `match-d7bea949ac944ac0a65354bbda4dcb5d` | 0–4 | 295.85 | 16928 |
| 20 | heuristic-tactical | `match-171694fd819d404db61ce471b70baea8` | 0–4 | 282.22 | 16085 |
| 21 | jev | `match-d4f02343d75a4b7aa72f712a28dfa1dd` | 0–3 | 338.57 | 19428 |
| 22 | random-tactical | `match-1d036da780a74b598045ca9cff1f7cdd` | 0–3 | 399.54 | 23119 |
| 23 | heuristic-tactical | `match-2c12c712311c4e63846d1593976adccd` | 0–3 | 402.36 | 23236 |
| 24 | jev | `match-367d8be092744a918a25a11d5e3e63ca` | 0–3 | 430.92 | 24981 |
| 25 | random-tactical | `match-1f09a77db93f493495a9ee0417db5c22` | 0–3 | 288.23 | 16452 |
| 26 | heuristic-tactical | `match-828aef99fa24469a81cc9909c3b19129` | 0–3 | 388.40 | 22464 |
| 27 | jev | `match-aacd6dc5398348eb8ab4b7ce6f7e418d` | 0–3 | 367.17 | 21165 |
| 28 | random-tactical | `match-e165c31bcbff4a33a5647b5fcdc82998` | 0–4 | 346.87 | 19959 |
| 29 | heuristic-tactical | `match-464eeb32996b414795113311ce7a699a` | 0–4 | 280.39 | 15983 |


