# Inspect participation by observed opportunity

`melee-agent inspect RUN_ID --policy-evidence` now includes `participation` for
asynchronous policies. It is a read-only report; it does not change candidates,
requests, cadence, packets, game assets or spending.

The report separates three questions:

- `frames`: what was observed on each frame, and whether the provider owned
  that frame's input.
- `request_sources`: the opportunity when a request was made, with backend
  attempts, valid responses, selected labels, frame-loop deliveries, accepted
  choices and raw-verified completed skills. An eventual completion remains
  attributed to its original source even if the game has changed by then.
- `applications`: the opportunity when an accepted choice reached the executor,
  with its eventual completion, interruption or episode cancellation.

The mutually exclusive bins, in priority order, are inactive, own hitstun,
own hitlag, airborne, grounded atomic combat available, grounded option-only,
and other grounded state. The report embeds exact definitions. Availability
uses observed state and the declared profile's local legality checks. These
bins describe opportunities, not tactical correctness, advantage or causality.
For example, an attack's retained hitlag belongs to `own_hitlag`, not a claim
that Fox was hit. Atomic combat includes down tilt and grab, so that bin can
still require walking before a jab.

Backend attempts can be refused before HTTP; HTTP totals remain in the provider
report. Simulated backends without attempt data mark it unavailable, rather than
claiming zero attempts. Deliveries count frame-loop returns, excluding replies
received only during shutdown. Missing source observations receive an explicit
unavailable bin. Counts are evidence only when the encompassing audit passes.

The retained paid match `match-84292a351ef9431a97a99b54bbf78220` passes the
extended audit without additional requests or emulator launches:

| Request source | Attempts | Valid | Accepted | Completed skills | Completed options |
|---|---:|---:|---:|---:|---:|
| Grounded atomic combat available | 29 | 29 | 9 | 9 | 7 |
| Grounded option-only | 28 | 27 | 18 | 13 | 9 |
| Other grounded | 143 | 140 | 94 | 90 | 0 |
| Total | 200 | 196 | 121 | 112 | 16 |

There are 17,357 classified frames and 1,259 provider-owned frames. The original
run, raw audit and exact full replay remain unchanged; the detailed result and
0-4 loss are in `docs/jev-option-live.md`. Nine completed options originated when
no atomic combat action was legal. This is an observed selection-to-execution
path, not a comparison proving the option improves match results.

All 345 host tests pass. Coverage includes the actual delayed option/audit
fixture, candidate-profile-dependent classification, source versus application
attribution, unavailable attempts, repeated reporting without double counting,
and episode cancellation without false completion credit.
