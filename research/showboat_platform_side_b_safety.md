# Conservative platform-origin native side-B safeguard

## Motivation and chosen boundary

The [fourth recorded playtest](showboat_recorder_playtest_4.md) validated one
main-floor veto, but exposed another priority9 B+left pulse at f5302:
Falcon stood on Battlefield's left platform at (-44.78,27.2), entered ground
side-B, left that platform into FallSpecial and later entered DeadDown at9.6%,
without an intervening sampled percent increase. This was outside the original
main-floor-only scope, not evidence that its accepted main-floor veto failed.

Extend the existing **current-floor whiff-envelope rule**, not a speculative
lower-floor landing simulator. Ground side-B has no ordinary IASA cancellation;
loss of floor during the relevant startup routes into FallSpecial. A lower main
floor underneath part of the path does not guarantee landing before the outward
air coast crosses its ledge. Native FallSpecial does permit drift; no new drift
or recovery planner is implemented here.

The rule remains: forward runway strictly greater than61 raw model units times
normal scale plus6 world units; backward runway strictly greater than11 times
scale plus6. Both must fit on the **current verified support surface**. At normal
Falcon scale.97, that is65.17 forward plus16.67 backward: **81.84 total**.

Every normal Battlefield platform is only37.6 wide. Consequently this deliberately
vetoes **all otherwise eligible queued priority9 ground side-B pulses on those
three platforms, in either direction**. It sacrifices potentially safe inward
drops, lower-floor landings and contact-shortened paths rather than pretending
to predict them. This is NOT a blanket platform side-B ban: priority2 move
choices, aerial specials, existing specials and recovery remain untouched.

## Native/asset evidence

Verified local `GrNBa.dat`, 452,171 bytes, SHA-256
`5b914b8f28c0dc16b1bafad68704e743d495ead41f0b954cca84479d6868a3b7`.
The asset is not committed. `grGroundParam` at file0x33FC8 supplies stage scale.8
(bits3f4ccccd). `ground.c` loads that scale; `mpLibLoad` in `mplib.c` multiplies
collision vertices by it.

| Surface / line | Raw vertices | World endpoints (approx.) | MapLine file offset |
|---|---|---|---|
| Left /2 | (-72,34) → (-25,34) | (-57.6,27.2) → (-20,27.2) | 0x31F84 |
| Top /3 | (-23.5,68) → (23.5,68) | (-18.8,54.4) → (18.8,54.4) | 0x31F94 |
| Right /4 | (25,34) → (72,34) | (20,27.2) → (57.6,27.2) | 0x31FA4 |

Actual binary32 values include57.6000022888,27.2000007629,18.8000011444 and
54.4000015259. All platforms face left-to-right, are horizontal, and have all
four previous/next adjacency IDs equal−1. Their connected endpoints therefore
terminate on the same platform. The main floor is the separate0→1→5 chain.

Asset `coll_data` is at file0x320FC, vertices0x31E94, 16-byte MapLines0x31F64,
MapJoint0x320D4. There is one collision joint: static floor range0/count6,
dynamic count0. Native Battlefield `StageData.joints/count` is NULL/0 and asset
map-head entries have no collision-joint bindings. Collision APIs synthesize
z0 from 2D vertices; this is not a render-model-depth observation.

`hi_flags=1` describes floor kind; `lo_flags=0x100` is pass-through platform.
`LINE_FLAG_PLATFORM` does **not** mean static or enabled. Native initialization
sets runtime CollLine flags to hi_flags|LINE_FLAG_ENABLED and attaches each
source MapLine pointer. CollJoint initially has only CollJoint_Enabled and no
bound JObj/collision callbacks. Relevant sources:

- `src/melee/mp/{forward.h,types.h}`: flags and Map/Coll structures.
- `src/melee/mp/mplib.c::mpLibLoad`: runtime map/joint/line initialization.
- `mpLib_8004ED5C`/`mpCheckFloor`: actual support intersection/envelopes. Isolated
  platforms have no query extension because they have no neighbors.
- `mpFloorGetLeft/Right`: connected endpoints, not a lower floor projection.
- `src/melee/gr/{ground.c,grbattle.c}`: scale and collision-joint bindings.
- `src/melee/ft/kinds/ftCaptain/ftcaptainspecials.c`: ground-start floor loss.
- `src/melee/ft/kinds/ftCommon/ftCo_FallSpecial.c`: legal helpless drift/landing.

The added map/line/joint getters and endpoint helpers are read-only. The existing
`mpCheckFloor` query can refresh native broad-phase flags/cache through
`mpBoundingCheck`/`mpUncheckBounding`; it is not literally free of all engine
writes. That pre-existing housekeeping is not a fighter-physics change and is
not performed by the recorder. No new joint update, collision mutation, movement
or planner calls are introduced to establish support.

## Implementation contract

Only `src/melee/mod/showboat_safety.c` changes gameplay logic. The existing main
post-VM/pre-recorder hook, ownership checks, API, event128 and float transport
remain unchanged. All existing eligibility restrictions stay in force: primary
CPU9 Falcon mode4, current rival identity, no custom action, priority9/cache0,
fresh unambiguous ground B plus full X from Wait/Walk, normal model/physical
conditions and no unavailable/protected/item state. Target hitstun remains
allowed. No target-offstage condition is introduced.

For a platform query, require Battlefield, query line2/3/4, identical stored
support, exact platform low flags and a native static-map certificate:

- Current map exists, one joint, source lines/joints present, at least six lines,
  static floor range0/count6 and no dynamic lines.
- Runtime joint is the current source joint, exactly enabled, with no bound
  transform JObj or collision callbacks; its inner floor/dynamic ranges agree.
- Runtime line is enabled floor only, points at the matching current MapLine,
  with exact source floor/platform flags and no previous/next neighbors.
- Current connected endpoints match the selected vanilla platform within.1;
  normal, actual vertices, contact, coplanarity, finite fields, root support and
  native query intervals pass the existing checks. Both support IDs are equal
  for isolated platforms; main-floor connected-seam equivalence is retained.

Known endpoints alone are not treated as proof that a moving platform is static.
Bound/transformed/dynamic/callback geometry and unknown layouts are unsupported:
**yield to native**, not label them safe or apply a guessed rejection. These are
current-state checks, not guarantees about arbitrary future map mutations.

On a veto, only B and accompanying CPU left-stick X are cleared. No VM cursor,
buffer, duration, priority, cache, target, timer, physics, shield, animation,
facing, controller-history field, RNG or ego is changed. The55-update native wait
and later jump/attack/up-B inputs remain; they may still idle or act poorly.

Event128 continues to mean input rejection only. The snapshot's support-height
context distinguishes a platform episode from a main-floor episode; the recorder
does not add atomic safety-rejection reasons or certify a stock saved. Existing
capture4 remains evidence from the **preceding** main-floor-only binary, not a
live test of this extension. A replay must explicitly stub its unrecorded native
map/input predicates.

## First approved live result

The [fifth recorded playtest](showboat_recorder_playtest_5.md) uses the exact
platform build below. It records event128 atf4323 on the left platform, pointing
right/inward, with B/X suppressed. The retained jump/up-B lands at4484, but is
punished by a Stone-consistent damage event during landing lag at4501. Two
main-floor vetoes also occur; another retained up-B catches Kirby. This validates
one platform admission, not all directions/platforms, a saved stock, or a
uniformly useful tail. No post-review gameplay changes were made.

## Original offline verification checkpoint

- **452 tests pass** in125.213s:242 retained/main,43 safety,56 recorder,
  92 analyzer,16 capture,3 config/verifier. All442 preceding tests are retained.
- Actual production safety C, native declarations and debug0/1 ASan/UBSan:
  **12,122 full-Fighter write guards**, including all2,768 legacy guards. The
  ten new tests cover all platform positions/directions, exact/adjacent float
  edge boundaries, native platform intersection without extension, priority2
  and future-input preservation, the exact f5302 observed fields with explicit
  unknown-state stubs, map/joint/source/flag/adjacency/geometry exclusions and
  nonfinite/stale data. Host guarded footprint is37,640 bytes per call; it is
  not a retail Fighter layout/performance claim. PPC headers also pass syntax
  checking; dependency/state/write guards remain enabled.
- The130 main AI cases still run all four recorder/debug combinations (520
  sanitizer executions). Native build/verifier,28 module warning configurations
  and six disabled-hook/C-stick comparisons pass.
- Independent read-only review independently checked native initialization,
  map bindings, pointer bounds under native invariants, exact flag meanings and
  retained main-floor seams. No actionable C defects were found. It also
  identified the pre-existing broad-phase query housekeeping clarified above.
- Default DOL: **4,522,912 bytes**, SHA-1
  `7384b2f1dadc18b996e324a4c3add40221963290`.
- Recorder-off verifies:4,503,264 bytes, SHA-1
  `246c8bf41cb1191126c5104747253711d48dda7c`. Safety object SHA-1
  `616447ffefa3b6c3b8ed820641cf44310c5b9d74` is byte-identical off/on;
  default enabled build restored.
- Compared with the last live safety build, **only showboat_safety.o differs**.
  The AI hook, recorder event mask/float codec, other tactics and native hooks
  are unchanged. No physics, timer, shield, jab or recovery tuning.
- Stock files/controller unchanged. Dolphin remains closed, and the virtual
  disc still holds the prior tested463a5... DOL: building did not stage it.

Logs are local under `build/showboat-platform-{tests,checks,final-build,
final-verify,off-build,off-verify}.log`; the preceding tested binaries/object
fingerprints are preserved under `build/showboat/platform-safety-baseline/`.

No live platform admission/prevention or logging-overhead claim follows from
these checks. A fresh tester readiness confirmation is required before launch.
On the next Battlefield test, look for event128 at platform height with B/X
absent, then inspect the retained wait/jump/attack/up-B tail and landing. Verify
ordinary priority2/aerial choices and main-floor central/inward allowances are
still available; a veto is not itself a counterfactual saved stock.
