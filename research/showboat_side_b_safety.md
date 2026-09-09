# Native throw-follow-up side-B safety

## Motivation and native path

The [first valid v2 capture](showboat_recorder_playtest_3.md) exposed Falcon's
native Raptor Boost departing Battlefield's left ledge after a down throw.
At f7095 the CPU emits B + left from Wait at x=-47.3126. At f7119 Falcon is in
FallSpecial at x=-69.5556, then DeadDown at f7168 without an intervening sampled
percent increase. This was native priority 9, not a custom wavedash or a fresh
priority-2 attack. No official SD credit or match result is inferred.

Native `ftcpuattack.c::ftCo_800B683C` contains Falcon's grab follow-up: on its
initial decision, level >4 and chance `0.05 * level`, use script 0x39 for victim
percent below 100, otherwise 0x3A. Read-only local US1.02 `PlCo.dat` inspection
locates these scripts at file offsets 0xE578/0xE59C. Both contain:

| Relative update | Native script intent |
|---|---|
| 0 | Down stick / wait 1: initiate down throw |
| 1 | Neutral Y / wait 40 |
| 41 | Stick forward relative to current facing; Y=0; B for 1 |
| 42 | Neutral X / release B / wait 55 |
| 97 | Jump with Y button; later up-B or another jump/forward-A |

The direction is not a current opponent-position query. `ftCo_0A01.c` retains
priority 9 while the script runs; `ftCo_800B2790` builds only when the VM is
finished. Thus weighting attack tables or rejecting only fresh priority-2
choices cannot catch this pulse.

The existing `ShowboatAI_PostInput` hook is after the interpreter and partner
processing, before Fighter's normal controller consumption. Observe that actual
output exactly once there. Never rerun a native planner/interpreter or fake an
input-timer edge to predict it.

## Movement evidence: both directions matter

Grounded side-B is animation-driven, not constant horizontal speed.
`ftCa_SpecialS_Enter` resets ordinary movement velocity. Ground physics calls
`ft_80084FA8`/`ft_80085030`, which use TransN displacement when animation motion
is enabled. `ftAnim_8006E054` supplies scaled TransN differences. All side-B IASA
callbacks are empty: releasing B after entry does not cancel the move. Startup
floor loss with the appropriate command flag enters FallSpecial when miss
landing lag is nonzero; normal Falcon's miss/hit landing lag attributes are
20/40. `specials_gr_vel_x=0.18` is a detection-time velocity multiplier, **not
rush speed**. No runtime attribute is changed.

Read-only local asset inspection: `PlCa.dat` common/special attribute bases are
0x3774/0x38F8; model scaling is 0.97. `PlCaAJ.dat` grounded startup/hit archives
begin at 0x86DA0/0x89200, submotion indices 303/304 (motion states 349/350).
The startup is 80 animation frames, hit animation 25. Startup TransN Z before
scaling:

| Animation time | Z |
|---|---:|
| 0 | 0 |
| 4 | -10 |
| 16 | -9.996094 |
| 20 | 9.998047 |
| 35 | 44.998047 |
| 80 | 59.998047 |

Reconstructing the native FObj interpolation gives a maximum near 60.227 around
time 70.77, not just the final value; minimum is -10. A rounded **whiff-movement
envelope** is 61 raw units forward / 11 backward. The hit animation advances
another five raw units; this is not an exact replay of collision/detection,
recoil, externally changed animations or every possible post-contact path.
At animation time 24 the reconstructed startup displacement is about 22.243
world units, agreeing closely with the observed -47.3126 → -69.5556 departure.

For normal model scale, define `s = x34_scale.y * co_attrs.model_scaling` and
an engineering reserve of six world units:

```
forward requirement  = 61*s + 6  = 65.17 normally
backward requirement = 11*s + 6  = 16.67 normally
```

Require runway strictly greater than both requirements. The six-unit reserve
is a conservative policy choice, not an asset constant or a universal safety
guarantee. An inward side-B initially steps backward; checking only its eventual
rush direction would miss that edge case. Conversely, from the recorded x=-47.31,
a rightward/inward side-B has ample forward runway and about 21.09 backward,
so it remains available. A stage-center side-B on Battlefield also remains
available. Do not add ordinary velocity times all 80 frames: native entry
resets that velocity. Unsupported external displacement/physical scaling is
outside this first feature's scope, not declared safe.

## Narrow initial policy

`showboat_safety.c/.h` supplies a stateless post-input filter. Main orchestration
requires the same live self and opponent spawn identities as Update, and no
active personality/combat/movement/defense input program. The module further
limits itself to:

- Mode-4, level-9 primary Falcon; normal singles policy remains in main.
- **Native priority 9, no cached attack**, no current grabbed victim, observed
  grounded Wait/Walk. Other priorities and in-progress specials/recovery,
  attacks, throws, damage, ledges and unsupported states are untouched.
- Exact fresh B-only, full horizontal, neutral Y/c-stick/shoulders. Do not
  reinterpret mixed buttons, held B, air specials or OOS choices.
- Normal supported physical conditions and finite values. Opponent hitstun is
  allowed: the motivating case is a launched opponent, not a neutral target.
- Verified flat connected main-floor geometry on Battlefield or Final
  Destination, not pass-through platforms, stale floor indices or moving stages.
  Native floor queries extend segment endpoints and can choose an adjacent
  strip on an equal-distance overlap. Validate stored/query support as the same
  connected coplanar floor, with the root inside both native extended segment
  intervals and the actual connected ledges. Do not require equal indices or
  unextended-segment containment at valid seams. `mpLib_8004ED5C` supplies the
  exact native extension; do not substitute a guessed one-unit tolerance.
- Insufficient forward **or** backward runway in the requested direction.

The full horizontal input determines the normal side-special reversal without
writing facing. Ground Wait/Walk check side-B before other specials; native
`ftCo_SpecialS_HasInput` tests B and absolute X >= common x218 (normally 0.60),
not the airborne vertical-special precedence. This implementation deliberately
covers only unambiguous neutral-Y/full-X pulses used by the recorded scripts.

On veto, clear **only B and its accompanying horizontal output**. Keeping B
while neutralizing X could turn the rejected move into Falcon Punch. Never
restore the rejected B later. Do not clear or rewrite the native VM, its
`command_duration`, cache, priority, target, input timers, physics, facing,
motion, shield, jumps or recovery state. Other fighters are read-only. No
sidecars, RNG, ego gate, cooldown or recovery warp is introduced.

**The native 55-update wait and subsequent follow-up inputs remain intact.**
This can leave Falcon idle or produce an unhelpful later follow-up. It is an
explicit limitation of a minimal output filter, not a claim of a full corrected
throw-combo planner or guaranteed saved stock. Investigate it with actual traces
before taking ownership of an existing native program. Helpless fall also
permits normal drift; this patch does not add a drift/recovery policy.

## Recording and validation contract

A true filter result logs the original left/right request and emits v2 event
**128 `side_b_veto`**. The recorder then snapshots the filtered output. This is
an input rejection, **not** a motion acknowledgment, connected hit, confirmed
recovery or saved stock. Existing five tactic histograms remain unchanged;
the veto does not invent another movement-planner decision. `owns` and HUD
intent continue to describe the earlier tactical decision, not every post-input
filter. No ego reward is granted for refusing an input.

The bit is an additive v2 event extension; use the matching analyzer. Old v2
captures remain readable; older strict analyzers may reject event128. Float-bit
transport is unchanged and all historical-v1 quarantine rules remain intact.

Validation must include the observed leftward case and its mirror, central and
inward allowances, backward-runway rejection, threshold/scale/geometry cases,
identity/priority/state/input exclusions, unchanged VM/timers/cache and full
Fighter/CPU write guards allowing only the two output fields. Host replay uses
observed fields plus explicit stubs for unrecorded world/input details; it is
not a claim that a veto has already occurred in Dolphin. Native builds,
recorder/debug variants and disabled-hook isolation must pass before the next
explicitly tester-approved launch. No emulator launch is part of development.

## Completed offline checkpoint

- **442 tests pass**: 242 retained/main, 33 safety, 56 recorder, 92 analyzer,
  16 capture, three configuration/verifier.
- All 123 prior AI cases plus seven new orchestration cases pass in recorder
  0/1 × debug 0/1: 130 cases / 520 sanitizer executions. New tests cover
  post-filter recording order, actual veto events and identity/custom ownership
  exclusions; no ego reward or recorder dependency.
- Safety's real production translation unit uses complete checkout Fighter and
  CpuFighter declarations. Debug 0/1 ASan/UBSan exercise **2,768 full-Fighter
  write guards**, allowing only B/X output differences; native headers also
  pass separate strict PPC syntax checks. Explicit world/input fixtures are
  not retail scheduling or physics emulation.
- An independent review caught the connected-floor seam bypass described above.
  Corrected tests model first-hit overlap on both sides of BF/FD, native asymmetric
  extensions, identical/different support indices and truly stale/alien support.
  The correction retains the actual connected ledge limits and all VM bytes.
- Native build/verifier pass; seven modules × recorder 0/1 × debug 0/1 yield
  **28 MWCC warning checks** without module-local diagnostics. Six disabled
  native hooks remain byte-identical to the C-stick baseline.
- Recorder-off build also verifies: 4,502,496 bytes, SHA-1
  `6c541b96fae7595d39a9033fc6d50dcccd1988d7`; safety's compiled object is identical
  off/on. The default enabled build was restored afterward.
- Rebuilt DOL: **4,522,176 bytes**, SHA-1
  `463a5a435aa5241f943fd21bfc87a4612c9eb2d7`. Versus the last tested v2 build,
  only `showboat_ai.o`, `showboat_recorder.o` (event mask) and the new
  `showboat_safety.o` differ. Other tactical/native objects are unchanged.
- Static linked/DOL check at SR_Emit's new call address **0x803CC31C** confirms
  r4=SP+0x5C, CR6 clear, r3 pointing to `%s` at 0x804EF80C, and the same OSReport
  target. Float/string transport has not reverted to mixed varargs. Local audit:
  `build/showboat/safety-recorder-target-audit.txt`.
- Syntax/whitespace checks pass. Dolphin stayed closed; virtual-disc DOL remains
  `27db34f9111d37f01ebf83be4c78d9233fef06bb` and controller SHA-1 remains
  `00dc2b7a5339493fe11fcf93e3adba16e93e0451`. No active disc, stock assets,
  raw captures, normal profile or prior reports were modified.

An event128 demonstrates rejection only; do not count it as a saved stock.

## First approved live result

The [fourth recorded playtest](showboat_recorder_playtest_4.md) uses this exact
DOL and clean `b52670cc5` source. At f1902 the legacy left-veto diagnostic agrees
with event128 and neutral post-filter output from Wait at x=-49.25. No side-B
starts; the native wait, jumps and Knee continue, followed by landing on the
left platform without a recorded percent increase. This validates one actual
admission/continuation, not a counterfactual saved stock or a generally optimal
throw follow-up.

At f5302 the same native9 B+left pulse occurs on the raised left platform at
y27.2, outside this module's main-floor scope. It proceeds into side-B,
FallSpecial and DeadDown at f5381 with percent unchanged at9.6. Platform-edge
and subsequent air-coast/lower-floor safety is the next evidenced investigation.
The main-floor policy has not become a universal side-B safeguard. Ordinary
priority2 ground/air side-Bs remain observed. The capture parses 2,766 records
without rejected rows; Dolphin exited0 and is closed. No further tuning or
restart followed the review.
