# Neutral-opponent aerial timing fixture

Issue [#86](https://github.com/cmoyates/melee/issues/86) adds a separate mechanical
calibration for J17. Native pilot and full calibration are pending. This fixture
does not replace the existing CPU3 suite or turn its interruptions into passes.

The earlier CPU3 suite acknowledged all eighty aerials. Twelve own-hitstun
interruptions prevented strict left-side clean-completion calibration. A neutral
human-controller Mario removes opponent attacks from this timing experiment.
Fox remains Player 1 on stock Battlefield, four stocks and eight-minute rules.
No game-memory or native-code change is involved. Mario can still be hit or
displaced; neutral input does not imply an immobile fighter or identical RNG.

```sh
# Four fresh-match trials; inspect all audits before running the full schedule.
uv run --project agent melee-agent scenarios --suite aerial-calibration-v1 --repeats 1 --duration 360

# Eighty trials, twenty in each direction and L-attempt/control group.
uv run --project agent melee-agent skill-check --suite aerial-calibration-v1 --repeats 20
```

The four names have a `calibration-` prefix. Their setup predicates, short-hop
primitive, landing measurement and strict twenty-trial duration gate are the
same as the CPU3 aerial suite. Existing suite manifests retain their hashes.
The new suite is explicitly identified in its own manifest and result report.
Launches, episode records and summaries declare `neutral-human-v1`; replay
settings must prove that Mario is human controlled. Normal matches continue to
require Mario CPU3. Calibration trials have a sixty-second wall-clock ceiling,
one fresh match, ordinary controller packets and no provider access.

Every gameplay row records the neutral command and Mario's observed controller
values. The independent scenario audit requires complete, released input on
every nonnegative frame, including setup. Countdown input remains recorded;
menu input can still be visible when countdown begins. Missing fixture identity,
the wrong replay role, an incomplete input packet or non-neutral observed input
fails the audit. Commanding release alone is insufficient.

Acceptance groups keep calibration and CPU3 rows separate. Failed trials remain
in their original denominators. The compiler excludes calibration runs and
refuses explicitly selected calibration frames from ordinary CPU3 decision
corpora. Standalone replay extraction still requires the original CPU3 rules.

Host coverage exercises the real worker and supervisor boundaries with synthetic
states/replays, the scenario audit, input tampering, grouping, and corpus
exclusion. These checks do not establish native timing or menu-setup success.
Run the live pilot only after the frozen J19 cohort releases its emulator lease.
