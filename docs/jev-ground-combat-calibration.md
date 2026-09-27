# Neutral-opponent grounded calibration

Issue [#90](https://github.com/cmoyates/melee/issues/90) adds a separate mechanical
fixture for Fox jab, down-tilt and grab, each facing left and right. The earlier
CPU3 suite remains unchanged: 101 clean completions, 18 interruptions and one
setup failure in 120 attempts. A CPU attack can interrupt a valid setup before
the intended Fox motion starts; this calibration measures execution separately.

`ground-combat-calibration-v1` uses fresh Battlefield matches with Fox on port 1
and a human Mario on port 2 receiving only ordinary released controller input.
Each of the six `calibration-` scenarios preserves the combat vulnerability,
facing, range, input, timing and motion checks, with a narrower starting fixture:
both fighters settled on the right platform. There are no savestates, memory
writes or changes to the measured skill.

The native aerial pilot showed neutral Mario remains at x=38.8, y=27.2001 on
that platform. The CPU3-oriented main-floor setup cannot wait for this stationary
opponent to approach it. The new, explicitly hashed
`right-platform-full-jump-v1` setup moves Fox off the left spawn platform,
walks to a declared position under the right platform, settles, then holds one
jump through jumpsquat until native rising takeoff is acknowledged. It releases
all input in the air, requires a right-platform landing, and settles/faces Mario
before admitting the original attack primitive. Mario receives no setup input.

Missing takeoff after eight frames, a wrong landing, unexpected opponent setup,
route bounds or a 120-frame landing deadline stop this setup without another
jump. The original 480-frame whole-setup deadline and continuity/life guards
still apply. This is one controlled measurement route, not general platform
navigation. Original CPU3 and aerial fixture hashes remain unchanged.

The route allows the existing `LANDING_ORIGIN_FLOOR` corridor (y at least -12)
over the main floor. Recorded aerial pilot
`match-0636f7e0c87149aaa05ab82f0023a7a5`, frame 26, shows an ordinary falling
origin at x=-5.9600, y=-1.9399 just before floor landing. A stricter -1 bound
would reject that valid approach before the calibration jump. The route waits
neutrally while airborne; this allowance does not start an attack or jump below
the floor or permit offstage horizontal coordinates. Frames SHA-256:
`01bb81100fdcc9f9c7048b07bca197dcd12048ccbc3e3507499e91792dbc6a4e`.

The supervisor and raw replay rules require the declared human-opponent fixture.
Every nonnegative gameplay observation, including setup, must show Mario's
buttons, sticks and triggers released. The original CPU3 rules remain strict.
Calibration runs are excluded from normal CPU3 corpus generation. Fixture names,
hashes and result groups keep the two experiments separate.

Run the six-case pilot after the aerial fixture's native wiring is validated:

```sh
uv run --project agent melee-agent scenarios --suite ground-combat-calibration-v1 --repeats 1 --duration 480
```

Audit every attempt's raw motion, exact offline control replay, observed terminal
release, source identity, replay settings and owned cleanup. If the setup and
evidence are sound, run the full matrix:

```sh
uv run --project agent melee-agent skill-check --suite ground-combat-calibration-v1 --repeats 20
```

Each trial retains the 60-second wall-clock limit and starts a fresh match. The
full matrix defaults to a 3,000-second whole-suite limit. No API calls are made.
Strict calibration acceptance requires all twenty native motion starts and
clean neutral actionable completions per action/direction, plus at least one
actual capture in each grab direction. Contact, capture and acknowledgement are
reported separately. Setup failures, interruptions and missing trials remain
visible and cannot be dropped to obtain a pass.

The native pilot and full calibration passed. This establishes this controlled
mechanical fixture, without replacing the original CPU3 integration result or
demonstrating tactical strength. Fourteen focused host tests cover preserved
contracts, bounded mirrored setup and release, interrupted/missing takeoff,
landing and continuity, isolated acceptance groups, failed/missing trials and
the difference between a grab motion and a captured opponent.

## Native evidence, 2026-09-27

Implementation `678a40e55` first passed all six pilot cases, then completed suite
`scenarios-96255f843de34a1b88b67c1da6de0672` with 120/120 audited successes.

| Action / direction | Native acknowledgement | Clean completion | Contact / capture |
| --- | --- | --- | --- |
| Jab left | 20/20 | 20/20 | 20 contact trials |
| Jab right | 20/20 | 20/20 | 20 contact trials |
| Down-tilt left | 20/20 | 20/20 | 20 contact trials |
| Down-tilt right | 20/20 | 20/20 | 20 contact trials |
| Grab left | 20/20 | 20/20 | 20 actual captures |
| Grab right | 20/20 | 20/20 | 20 actual captures |

All trials passed fixture/input, raw-state, rules and owned-cleanup checks.
Independent exact replay reproduced all 44,300 recorded game-frame decisions,
packets, scenario traces and final reports. All launch-recorded source hashes
matched. The suite took 1,890.43 seconds and retained 373,246,324 artifact bytes.
All five spend journals stayed byte-identical; there were no provider calls.

Suite summary SHA-256:
`6178624114b2e2ca678552d1d98df128ce7ddf8d9a4650c0b3a912854fdf3fd5`.
Private recordings and full independent audits remain under
`build/jev/scenarios/` and `build/jev/continuation-20260926/` using the suite ID.
The six-case pilot was `scenarios-54e86e87d2fb4564a0434cf38926acd0` (2,215 exact
records); it was not used to fill the full matrix's denominators.

The original CPU3 suite still records 101 clean completions, 18 interruptions
and one setup failure. This neutral-opponent platform fixture does not reclassify
those trials, prove reliable attacks against an active opponent, or constitute a
general platform-navigation skill.
