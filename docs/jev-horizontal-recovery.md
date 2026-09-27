# High horizontal recovery experiment

Issue [#88](https://github.com/cmoyates/melee/issues/88) covers one additional
Fox recovery situation. One native left-side acknowledgement and stage return
passed the pilot audit; broader directional coverage remains pending.
The frozen J19 comparison and its historical losses remain unchanged.

In a hash-verified snapshot of sixteen development matches, 44 of 64 Fox stock
losses ended in DamageFall (native motion 38) with the reflex latched failed.
Those encounters first failed outside the declared horizontal recovery boundary,
with one jump still available. This observation identifies an unattempted
recovery opportunity; it does not establish that all those positions were
recoverable. The earlier 80-trial recovery suite covered narrower setups.

The new admission requires all of the following observed conditions:

- Airborne, active Fox in DamageFall, with exactly one jump remaining.
- No hitlag or hitstun, released jump input, and nonpositive self vertical speed.
- Horizontal magnitude greater than 130 and at most 180; height from 0 to 140.
- No earlier jump/special attempt or consumed admission in this damage episode.

Admission emits one inward jump through the same executor and shared reflex
used by local and Jev policies. Native
[DamageFall](../src/melee/ft/kinds/ftCommon/ftCo_DamageFall.c) checks aerial-jump
input through `ftCo_800CB870`; the
[jump handler](../src/melee/ft/kinds/ftCommon/ftCo_JumpAerial.c) requires an available
jump and fresh XY/tap input. These source checks motivate the input; live motion
and resource observations must still acknowledge its execution.

The existing recovery state machine then handles the admitted trajectory inside
an outer horizontal bound of 180 and the original lower bound of -85. Its
180-frame deadline is not extended. A missing jump acknowledgement ends this
experiment after eight frames without another jump or special press. New damage
clears admission; fresh observed resources govern any later attempt. A frame gap
releases input and cannot readmit the same knockback. Stage return and life reset
clear the admission. Other unsupported positions retain their earlier behavior.

## Native protocol and evidence

Use a separately identified free heuristic-tactical Fox versus Mario CPU3 match
on Battlefield after the frozen comparison finishes. Count naturally occurring
eligible knockback encounters, preserving their side, source position, resource,
and frame identity. Ordinary setup cannot be assumed to place a fighter at an
arbitrary high horizontal coordinate with a jump remaining. This protocol does
not use savestates, memory writes, or altered CPU behavior.

```sh
uv run --project agent melee-agent match --policy heuristic-tactical --profile fox-aerial-v1 --duration 600
uv run --project agent melee-agent inspect RUN_ID --horizontal-recovery-evidence
uv run --project agent melee-agent inspect RUN_ID --integrity
uv run --project agent melee-agent inspect RUN_ID --policy-evidence
```

The recovery report independently checks native motion, position, jump resource,
combat flags, released observed jump input and the source jump packet. It counts
raw jump acknowledgements and known stage/ledge returns separately from reported
controller failures, damage/frame interruptions and pending encounters. Run it
with the companion rules/result, integrity, exact control replay and cleanup
audits. A report with zero encounters is not coverage or a recovery success.

Begin with a bounded pilot. Twenty eligible encounters on each side is a later
coverage target; retain every failed or partial encounter and every match loss.
The existing narrow recovery suite also needs a fresh native regression pass.
This is a development experiment with uncontrolled game RNG, not a paired or
held-out strength comparison.

## Native pilot, 2026-09-27

Run `match-ce5f11a06cbc44eb8bf128528b313a09` used free heuristic-tactical
`fox-aerial-v1`, Fox P1 versus Mario CPU3, on stock Battlefield. It completed in
369.85 seconds with a verified 0–3 loss. One eligible natural encounter occurred:

| Side | Source frame / life | Position | Jump acknowledged | Known stage return |
| --- | --- | --- | --- | --- |
| Left | 9,844 / 2 | x −141.1066, y 56.1003 | Frame 9,845 | Frame 9,995 |

The independent raw-state recovery audit verified admission, resource/motion
acknowledgement and return with no errors. Full recording integrity, rules,
native result and owned cleanup passed. Exact local control replay and complete
standalone SLP semantic/legal-candidate parity covered all 21,160 game records,
with no unmatched states or differences. All source hashes and all five spend
journals were unchanged; no provider was contacted.

Frames SHA-256:
`482195a7a6502cc4e4aed5e2920725fea230ff726d5471faecc2d8994c43a709`.
Replayed controller packets SHA-256:
`83d4b97e83368782272be6a83640c7fc9d7ef12d566a4a3f3b4a384f13dea894`.
Full private audit: `build/jev/horizontal-recovery-20260927/pilot-audit.json`.

This is one observed left-side success and zero right-side encounters. It does
not meet the twenty-encounters-per-side target or establish better match
performance. The fresh eighty-trial narrow recovery regression is running;
the earlier suite's success is not substituted for that check.

## Offline boundary evidence

The host tests cover mirrored admission, both policy integrations, raw player
roles, missing acknowledgements, input repetition, unsupported positions,
interruptions and original bounds. A read-only probe examined 166,725 recorded
observations across the sixteen development matches, stopping at the first
changed reflex trace in each match. Fourteen first changes were exactly the
declared admission: the former neutral failure became one inward jump. The
other two traces remained identical throughout. The probe does not continue
through changed inputs or predict subsequent game physics.

Private probe SHA-256:
`aa086442bd3eded39062390c22878bf99e791a791fe9ba7fbdff13432da038f3`.
