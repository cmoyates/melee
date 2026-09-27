# Neutral-opponent aerial timing fixture

Issue [#86](https://github.com/cmoyates/melee/issues/86) adds a separate mechanical
calibration for J17. The native pilot and full eighty-trial calibration passed. This fixture
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
exclusion. The following native evidence separately verifies setup and timing.

## Native calibration evidence

Implementation `7ae36d6be` was exercised first in four fresh matches, then in
suite `scenarios-9ca179a7a21e457fb7cd33012de5ca4b` on 2026-09-27. All eighty
trials acknowledged the aerial, returned to neutral grounded state, and passed
the independent scenario audit. Exact replay reproduced all 21,600 recorded
game-frame decisions, controller packets, scenario traces and final reports.
All launch-recorded source hashes matched the tested checkout.

| Direction | L-cancel attempt | No-L-cancel control |
| --- | --- | --- |
| Left | 20/20 completions, all 7 landing frames | 20/20 completions, all 15 landing frames |
| Right | 20/20 completions, all 7 landing frames | 20/20 completions, all 15 landing frames |

Every nonnegative gameplay frame passed the observed neutral-opponent input
check. The suite took 1,118.13 seconds and retained 188,790,006 artifact bytes.
All five existing spend journals remained byte-identical; no provider was used.

Suite summary SHA-256:
`8d11ad60ede17c4b0503a99af54909c1762c782b07cce1afc227580051307b55`.
Full private evidence is retained under `build/jev/scenarios/` and
`build/jev/continuation-20260926/` using that suite identifier.

This establishes the declared mechanical timing calibration in both directions.
The older CPU3 suite still records 68 clean completions and 12 interruptions;
its strict left-side clean-completion gate remains unmet. These results do not
establish tactical strength, paired RNG, or aerial success against an attacking
opponent.
