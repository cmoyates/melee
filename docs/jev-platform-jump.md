# Bounded side-platform transfer

Issue [#94](https://github.com/cmoyates/melee/issues/94) turns the native grounded
fixture's platform access into a reusable local skill. It is not available in
any Jev, random or heuristic candidate profile in this slice.

The grounded pilot observed Fox leave the main floor after four held-jump
frames, reach a peak y=31.2801 and land on Battlefield's right platform. The
existing short-hop Nair calibration peaks below that platform. Those recordings
motivate this primitive; its separate left/right suite must validate it.

`SkillSpec('platform_jump', side)` fixes the target to the left (-1) or right
(1) platform. Admission requires standing, released, settled main ground below
that platform, an eight-unit horizontal inset and two jumps. The skill requests
one ordinary neutral-direction jump from the existing shared arbiter. It
observes jumpsquat, held jump input, rising native takeoff and one remaining
jump, then releases all input. Completion requires the declared platform,
restored ground-jump resources and a standing neutral observation after landing.
Moving the opponent never changes the target.

Missing takeoff stops after eight frames; the whole transfer stops after ninety.
Damage, hitlag, death, life/frame changes, unexpected motion/resources, the wrong
landing surface or more than two units of horizontal drift abort neutrally.
The primitive emits intents through the existing executor; it owns no controller
writer and does not call the provider. There is no second jump or attack.

```sh
uv run --project agent melee-agent scenarios \
  --suite platform-jump-calibration-v1 --repeats 1 --duration 240

uv run --project agent melee-agent skill-check \
  --suite platform-jump-calibration-v1 --repeats 20
```

The new neutral-human Mario fixture uses fresh stock Battlefield matches. Fox
leaves its spawn platform using ordinary input, reaches the main floor and
settles around x=-45 or x=45. The right launch point stays clear of Mario's
neutral spawn at x=38.8. Setup input ends before measurement and the existing
terminal observed-release contract remains required. All older scenario
manifest hashes, profiles and original CPU3 results remain unchanged.

Independent raw evidence checks the source geometry, actual held jump through
jumpsquat, rising takeoff/resource change, neutral airborne packets, target
landing, final observed input and reported peak. Failed, missing, wrong-fixture
and unknown trials cannot satisfy the twenty-per-side gate. The suite requires
exact replay of recorded decisions and traces, source/rules/cleanup checks and
unchanged spending in addition to raw acknowledgement. Neutral fixture records
remain excluded from CPU3 decision corpora.

All 471 dependency-free host tests pass, including twelve focused checks for
the primitive, scenario and independent evidence boundary. All seven existing
scenario manifest hashes remain identical. New fixture SHA-256:
`13ee2f98121fe08ea70bdab3746c2444e2fe517004c7d3caada8a27b082335b9`.

Native pilot and forty-trial acceptance are pending. No general navigation,
platform-to-platform movement, CPU3 tactical success or strength improvement is
claimed. Any provider/profile integration requires a separately measured slice.
