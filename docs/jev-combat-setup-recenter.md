# Combat setup recentering

The J16 120-trial suite had four setup timeouts, all in right-facing trials.
Each included Fox grounded left of x=-35 with Mario still farther left, for
161–208 frames. The first retained failure,
`match-b1af197ec9b9400e983fd199d1970a47`, repeatedly queued slow-left near
x=-62 while Mario stood near -68.4. Walking left could not establish the
required right-facing geometry; the ordinary short-hop crossing was correctly
disabled there by its landing-space bound.

The setup now recenters when the opponent is on the wrong side and Fox is
outside that safe crossing region. It moves toward the interior, stops once
there is room, and waits for a close crossing opportunity instead of chasing
back to the same edge. Both directions share mirrored conditions. A neutral
setup packet still precedes a crossing or measured-skill handoff.

This changes only ordinary controller inputs during scenario setup. The
480-frame setup deadline, legal starting predicate, 180-frame measurement
deadline, native motion acknowledgement and interruption outcomes remain
unchanged. CPU behavior and game RNG remain uncontrolled; recentering is not a
guarantee of a successful setup. Damage still inhibits setup movement.

Regression tests cover both mirrored edge traps, interior waiting, opponent
approach, neutral release before crossing, damage inhibition, the unchanged
timeout, and an already legal attack's measurement boundary. All 288 host tests
pass. The six-trial live pilot reached every legal setup and acknowledged all
six attacks; five completed and one correctly aborted in hitstun.

## Full live schedule

`scenarios-8e65d8d2afbc4292b23f8d80824013e1` completed all 120 scheduled trials
in 2,046.87 seconds against Mario CPU 3 on Battlefield. There were 101 clean
completions, eighteen skill interruptions and one setup timeout. All raw audits
passed, and all 42,360 game frames reproduced the exact decisions, packets,
scenario traces and final reports with the launch source hashes unchanged.

| Action/direction | Native starts / 20 | Clean completions / 20 | Captures |
| --- | ---: | ---: | ---: |
| Jab left | 20 | 20 | 0 |
| Jab right | 19 | 18 | 0 |
| Down-tilt left | 20 | 16 | 0 |
| Down-tilt right | 19 | 12 | 0 |
| Grab left | 20 | 20 | 19 |
| Grab right | 18 | 15 | 13 |

Five trials exercised recentering for 628 recorded frames. The remaining setup
timeout, `match-3dabe3908d1a495f9bbdc61b5d8b9d6e`, left the edge region but was
hit during a later crossing attempt; at frame 480 Fox was in damage motion 86
near x=-7.47. It remains a failure. Game RNG is uncontrolled, so the difference
from the earlier four setup timeouts is descriptive rather than a causal success
rate estimate.

Seventeen skill interruptions were own hitstun; one was an unexpected native
motion after acknowledgement. Every terminal packet was neutral. Terminal
observed controller values were neutral in 117/120 trials; three interrupted
trials ended before the recording observed release. Commanded cleanup does not
substitute for that missing observation. The existing strict 20/20 clean gate
still fails overall; neither interruptions nor setup failures were removed.

Private audit: `build/jev/continuation-20260926/scenarios-8e65d8d2afbc4292b23f8d80824013e1-recenter-audit.json`.
Suite summary SHA-256:
`3f420ddc5d168b7d415154cfb4770d99044d62f2bf42846ba1256f76b4561eb2`.
No provider call was made.
