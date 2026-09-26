# Neutral-opponent grounded calibration

Issue [#90](https://github.com/cmoyates/melee/issues/90) adds a separate mechanical
fixture for Fox jab, down-tilt and grab, each facing left and right. The earlier
CPU3 suite remains unchanged: 101 clean completions, 18 interruptions and one
setup failure in 120 attempts. A CPU attack can interrupt a valid setup before
the intended Fox motion starts; this calibration measures execution separately.

`ground-combat-calibration-v1` uses fresh Battlefield matches with Fox on port 1
and a human Mario on port 2 receiving only ordinary released controller input.
Each of the six `calibration-` scenarios preserves its original geometry,
vulnerability, facing, range, input, timing and motion predicates. The existing
recenter/setup controller positions Fox through normal input. There are no
savestates, memory writes or changes to the measured skill.

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

Native calibration is pending. Passing it would establish this controlled
mechanical fixture, without replacing the original CPU3 integration result or
demonstrating tactical strength. The six host tests cover preserved scenario
contracts, CLI bounds, isolated acceptance groups, failed/missing trials and the
difference between a grab motion and a captured opponent.
