# Movement host fixtures

Run from the repository root:

```sh
python3 tools/tests/test_showboat_movement.py -v
```

Requires clang (or `SHOWBOAT_TEST_CC`), Python standard library, and the actual
`src/melee/mod/showboat_movement.c/.h`. Missing source is an error, not a skip.
No assets, configure step, PPC SDK, emulator, or third-party Python dependencies.

## What executes

- `harness.c` includes the **actual production C in place**. There is no copied
  movement policy. It registers 53 cases, several with independent matrices.
- `game.h` is a small typed host dependency surface, **not** a PPC layout mirror.
  Native fighter, ground/air, common/Falcon motion, jump-input, CPU-command and
  stage enums are extracted from repository headers for every build.
- `engine.c` supplies explicit CPU/primary-entity, protection, animation-length,
  trigger, stage, floor-segment and endpoint queries. Floor queries intersect
  supplied geometry; they do not answer "wavedash safe" on behalf of production.
  Inputs/outputs and query filter arguments are checked; no generic API stubs.
- Its bounded VM implements only explicitly audited stock controller commands.
  Unknown commands fail both at emission and interpretation. Unknown production
  APIs fail compilation/linking (`-Werror`, no fallback definitions).
- `cases.c` covers observed motion/input sequencing and release tails.
  `guards.c` covers geometry, movement/retreat policy and precise eligibility.
  `lifecycle.c` covers native arbitration, cached A4, identity, suspension and
  per-slot independence. `admission.c` covers queued native commands (including
  unknown/malformed bytecode), ordinary pending locomotion and threat guards.
- Both `SHOWBOAT_AI_DEBUG=0/1` builds use **ASan + UBSan**. Each case/mode runs in
  a fresh process. Production/header/fixture edits during compilation invalidate
  the run, preventing two debug modes from silently testing different revisions.

## Observation contract

An 80-unit forward gap on a flat, non-passable main floor is the default positive
control. Retreat is separately exercised at 55 units against an observed,
facing-toward-us, committed normal attack. Long-distance native Run is unchanged.
These are the authored policy's bands, not claims of universally optimal spacing.

The VM changes **CPU controller outputs only**. Test code explicitly supplies:

1. An observed neutral sample, then the single X sample.
2. Actual `KneeBend`, `JumpInput_XY`, held/pressed X; then observed release.
3. First actual `JumpF/B`, short-hop flag, one jump used, `x4 == false` and
   animation/height inside the authored window.
4. The emitted diagonal stick (`+/-90, -64`) and **digital L**, with zero analog
   triggers, followed by actual `EscapeAir` or direct `LandingFallSpecial`.

There is **no input-age-to-motion mapping**, no mocked successful jump/dodge,
and no physics advancement. Missing interpreter samples, consumed tails,
missing/late/unrelated motion observations, full hops, repeated pulses, floor
loss/gaps/platforms/edges/seams, target changes and replacement native commands
are tested separately. Explicit native VM clears at observed transitions are
permitted by the production policy; a consumed release tail is not such a clear.

Every public API call and VM tick snapshots all fixture fighters, objects,
common data and world answers. Only actor CPU script/output fields and cached A4
may differ. Facing, position, velocity, motion/animation, landing interruption,
input history/tech counters, priorities, targets and game rules remain identical.
Fresh A4 and replacement native scripts are preserved. A priority-only change
releases the exact old owned VM immediately while retaining that new decision;
native dispatch need not wait behind the old tail. Owned release tails also clean
up X/L/sticks when Update stops running.

Review regressions cover actionable (`allow_interrupt`) attacks, beneficial-coast
credit erased by friction, and actual-width Battlefield center approach/retreat.
Actual scaled widths distinguish BF's ±60 middle segment/±68.4 chain and FD's
±75/±85.5657. A rival on a verified connected, coplanar outer strip is permitted;
an unrelated support is not. Own touchdown continuity remains strict.

## Native mechanics audited (not emulated)

- `ftcmdscript.c`: `PressL` sets only digital L; unlike `PressR` it does not set an
  analog trigger. `WaitFor` pauses after decrement; `Done` does not clear inputs.
- `ftCo_Jump.c`: X/Y uses pressed buttons; `Jump_Phys_Inner` initially marks `x4`
  without running normal aerial physics. The first Jump window precedes Phys.
- `ftCo_KneeBend.c`: release of both X/Y allows native short-hop observation.
- `ftCo_EscapeAir.c`: native air dodge checks pressed digital L/R, replaces its
  velocity, decays it during Phys, and its collision path enters native
  `LandingFallSpecial` with `p_ftCommonData->x344`.
- `ftCo_Landing.c`: native special landing supplies its own animation speed and
  interruption policy. The test supplies observed landing values and verifies
  movement never rewrites them or bypasses landing lag.
- `ft_084E.c`: native ground friction/movement remain native. The fixture never
  emulates friction or derives slide distance from fake frames.

**These tests do not establish actual wavedash timing/frames, distance, collision
fidelity, or gameplay effectiveness.** They validate controller intent, explicit
observations and noninterference. The core links with no personality/ego module;
main AI arbitration/ego/teams/Nana integration spies belong to the separate main
harness and are not claimed here. No mutable fixtures from other suites are used.
