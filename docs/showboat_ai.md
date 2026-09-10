# Showboat Falcon AI

Tracking: https://github.com/cmoyates/melee/issues/1
Branch: `mod/showboat-ai`, based on the existing single-player C-stick mod.
Initial working tree was clean; that mod is retained.

**Resuming development? Read the [current handoff](showboat_handoff.md) first.**

## Current gameplay update: platform-origin side-B safeguard

The valid v2 trace exposed an unsafe side-B queued inside a native throw
follow-up. The new `showboat_safety.c/.h` filter examines that actual B output
before controller processing, independently of ego. It is limited to uncached
native priority 9, grounded Wait/Walk and verified normal FD/Battlefield floors.
It checks **both** the backward windup and forward rush runway, using a rounded
animation envelope plus an explicit margin. Central and sufficiently inward
**main-floor** side-B choices remain available; other priorities and
airborne/in-progress specials, recovery, throws, physics and game input timers
are untouched.

The [platform extension](../research/showboat_platform_side_b_safety.md) applies
that same footprint to Battlefield's three verified static platforms. Each is
37.6 units wide versus the required81.84, so **all otherwise eligible priority9
throw-follow-up side-B pulses there are rejected, either direction**. This
intentionally forgoes potentially safe inward drops/lower-floor landings; it does
not model them or ban ordinary priority2 side-B choices. Current native map,
static-joint, source-line and support checks exclude unknown/moving geometry.

Only an unsafe B press and its accompanying horizontal input are suppressed.
**The native VM and its 55-update wait/later follow-up inputs are retained**;
this is not a complete throw-combo planner or guaranteed saved stock. The
recorder emits event128 `side_b_veto` and snapshots the filtered output; the
legacy diagnostic retains the requested direction. No ego reward is added.
See [native research, scope and limitations](../research/showboat_side_b_safety.md).
The [first safeguard live review](../research/showboat_recorder_playtest_4.md)
confirms one actual veto and a retained jump/Knee follow-up that returns to a
platform without recorded damage. It also exposed the platform departure that
motivated this extension: a raised-platform side-B led to a fatal fall at9.6%.
That capture used the preceding main-floor-only binary. The
[first platform live review](../research/showboat_recorder_playtest_5.md) now
confirms one **inward left-platform veto** plus two main-floor vetoes. All three
retained tails land; the platform tail is then punished during up-B landing lag,
while another tail actually catches Kirby. No universal saved-stock or
uniformly useful continuation claim.

**Offline checkpoint:** 461 tests pass (242 retained/main, 43 safety, 56 recorder,
101 analyzer, 16 capture, three config/verifier). This includes **12,122 complete
Fighter write guards** (all2,768 legacy guards retained), all-platform/direction
and static-map rejection matrices, the explicitly stubbed f5302 replay, and
130 main cases across four recorder/debug combinations. Native build/verifier,
28 warning configurations and six disabled-hook comparisons pass. Safety's
object is identical with the recorder off/on. The platform patch changed only
the safety object versus the preceding main-floor live build; this latest
review/label update changes **no gameplay objects**. No jab, shield, recovery
or recorder tuning.
Independent native/asset review found no actionable implementation defects.

Ready DOL: **4,522,912 bytes**, SHA-1
`7384b2f1dadc18b996e324a4c3add40221963290`. The approved platform playtest staged
this same DOL and closed cleanly. Controller mapping is unchanged. No gameplay
changes or rebuild followed the review; only offline Kirby labels/tests/docs
changed. Host/static checks alone do not prove live admission or a saved stock.

## Read-only match recorder

**Recorder v2 replaces the faulty v1 serialization path.** A bounded buffer and
exact float-bit encoding replace the large mixed integer/double formatting call;
only a string is passed to OSReport. See the [repair analysis](../research/showboat_recorder_repair.md).
The [first approved v2 live capture](../research/showboat_recorder_playtest_3.md)
now passes encoding/field checks: 2,760 records, zero rejections, coherent fighter
identities and motions. Coverage gaps still limit statistics; logging overhead
is not measured. Historical v1 data remains quarantined.

Old v1 snapshots remain untrusted, including plausible-looking rows. The
[first](../research/showboat_recorder_playtest_1.md) and
[second](../research/showboat_recorder_playtest_2.md) reviews use only narrow,
separately corroborated events and integer-only accounting. No historical
snapshot fields are repaired by guessing offsets.

The default showboat build now includes structured **SBREC v2** telemetry and an
[offline analyzer](../tools/analyze_showboat.py). This observes the same legal bot;
it does not change its decisions, controls, physics, resources, RNG or timers.
See the [schema and design contract](../research/showboat_recorder.md). On the wire,
float fields are eight-digit IEEE binary32 hex strings; the analyzer converts them
to ordinary numeric values. This preserves bits rather than rounding or changing
game data.

After the tester explicitly approves a launch, the normal launch helper creates
an exclusive directory under `build/showboat/recordings/` containing:

- `runtime.log`: Dolphin output, structured records and existing diagnostics.
- `launch.json`: immutable launch-time DOL hash/size, recorder marker, optional
  controller hash and local Git provenance; written **before** execution.
- `metadata.json`: completion metadata with return code and UTC times. SIGKILL
  can prevent this final file, but launch provenance and written logs remain.

The helper refuses a detected running Dolphin **before copying the virtual DOL**.
No automatic launch/restart, upload, save modification or controller remapping.
Logs use disk, not an ever-growing RAM buffer; disk retention is manual. Process
checking is point-in-time, not a cross-application lock.

### What is observed

At the existing post-VM hook, after the combat L-cancel overlay and before game
input preprocessing, the recorder reads both fighters' native motion/animation,
position/velocity, percent, stocks, shield health and state flags. It also records
native CPU priority/cached attack/threat, ego/HUD intent, VM ownership and raw CPU
buttons/sticks/triggers. These are **CPU outputs**, not human/controller-hardware
input, and not an atomic end-of-frame world snapshot.

Snapshots occur on important state/input/event changes and every 12 observed
frames otherwise, capped at one per player/native frame. Tactic probes run at
actual branches, without rerunning a planner. Per-tactic reason histograms flush
every 60 observed updates and at segment end. Uncalled layers are
`not_evaluated`, not failed attempts. Each snapshot also carries the five local
reason values; these are not extra counts or reasons for unobserved frames.
Flush IDs distinguish batches sharing the same native clock value. Counts mean
observed updates, not unique frames or durations. Compound gates remain honest
branch/group labels, not invented exact predicates.

Separate event bits distinguish taunt/Punch/grab/aerial acknowledgment, wavedash
landing acknowledgment, custom powershield contact and an L-cancel **sample**.
The latter does not prove reduced lag; accepted attacks do not prove connected
hits. Native motion entries are observed transitions, not complete action totals.

### Analyze a capture

```sh
.venv/bin/python tools/analyze_showboat.py build/showboat/recordings/<capture>
.venv/bin/python tools/analyze_showboat.py build/showboat/recordings/<capture> \
  --json build/showboat/report.json --markdown build/showboat/report.md
# Focus on one observed segment:
.venv/bin/python tools/analyze_showboat.py <runtime.log> --segment 1
```

The report includes coverage/gaps, native state/priority intervals, custom events,
rejection counts, sampled ego range, comparable net percent increases, stock changes,
positions and a bounded timeline. It explicitly separates initial sightings,
continuous transitions and unknown intervals. Percent changes are not attributed
hit damage; stock changes are not confirmed KOs/wins. Airborne is not offstage:
the recorder has no complete stage geometry or offstage flag. Sparse positions alone do not
prove useful wavedash displacement or recovery success.

A recording segment is **not necessarily a whole match**. Spawn/identity changes,
clock rollback, context changes and suspension can split it. End is a recording
lifecycle event, not a match result; EOF/open segments and unflushed tails are
reported as incomplete. Old pre-recorder logs remain partial legacy diagnostics;
nothing can reconstruct unrecorded past frames.

### Opt out / baseline

```sh
sh tools/build_showboat.sh --no-showboat-recorder
.venv/bin/python tools/verify_showboat.py --no-recorder
# Restore default recorder-enabled build, without launching:
sh tools/build_showboat.sh
```

Raw configure defaults recording **off**; `--showboat-recorder` requires
`--showboat-ai` but not debug/HUD. Disabled macros do not evaluate arguments.
Recorder opt-out reproduces the entire preceding ego-build DOL byte-for-byte
(SHA-1 `0643071c098d78ab6d3339e3cc931647436b3594`). No new native hooks are added.
Rebuilding does not alter an already-running game or its virtual-disc DOL.
Logging/formatting can still cost runtime; offline tests do not establish emulator
speed or recording overhead. The first live capture exposed the integrity fault
noted above; the following historical checkpoint predates that finding.

### Recorder v2 repair checkpoint (before the ledge safeguard)

- **393 tests pass**: 235 main/retained tests, 52 recorder tests, 87 analyzer
  tests, 16 capture tests and three configuration/verifier tests.
- Raw C-to-CLI tests cover all 16 float positions, integer sentinels, signed zero,
  subnormals, finite extrema, literal `%s` transport, exact-fit/overflow boundaries
  and recovery gaps. Existing game/CPU immutability and recorder/debug matrices
  remain intact.
- Both real v1 captures were reanalyzed without overwriting old reports: invalid
  rows are rejected, remaining plausible v1 samples are quarantined, and each
  retains 7,324 integer-only gate updates per tactic. No trusted v1 sample totals.
- Native build/verifier, 24 module warning compiles, six disabled-hook comparisons
  and exact recorder-off DOL comparison pass. Static inspection of the linked
  PPC call confirms format/buffer pointers only, with the FP-varargs flag clear.
- Repaired DOL: **4,515,936 bytes**, SHA-1
  `27db34f9111d37f01ebf83be4c78d9233fef06bb`.
- The subsequent approved live test staged that v2 DOL and passed record
  encoding/field checks; controller hash remains
  `00dc2b7a5339493fe11fcf93e3adba16e93e0451`. Dolphin then closed cleanly.
  See the [live review](../research/showboat_recorder_playtest_3.md): full taunt,
  actual wavedash displacement, two grab-motion acknowledgments, and a late
  unsafe native side-B into helpless fall. No gameplay tuning followed.
  Further launches require readiness; runtime overhead remains unmeasured.

### Historical v1 recorder offline checkpoint

- **364 tests pass**: 235 retained/main-orchestration tests, 45 recorder tests,
  66 analyzer tests, 16 capture tests and two configuration tests. The 123 main
  AI cases run under recorder 0/1 × debug 0/1 with sanitizers; recorder C has its
  own typed read-only guards and actual-C-to-analyzer CLI seam checks.
- Repeated-clock flushes, sampled reasons, zero-stock Time percent observations,
  live/crash launch metadata, malformed/truncated input and output-source alias
  protection have explicit coverage. Host fixtures are not retail gameplay.
- Native build/verifier pass. Six modules × recorder 0/1 × debug 0/1 pass MWCC
  `-warn all` without module-local diagnostics; six disabled hooks remain
  byte-identical to C-stick. Recorder-off full-DOL comparison passes.
- Recorder-enabled DOL: **4,506,976 bytes**, SHA-1
  `690249dfe765ebdfefff6eb861df691c92cc2aca`. Stock DOLs remain unchanged.
- Existing playtest virtual DOL remains
  `0643071c098d78ab6d3339e3cc931647436b3594`; controller mapping remains
  `00dc2b7a5339493fe11fcf93e3adba16e93e0451`. No new Dolphin launch or live
  SBREC verification was performed for this checkpoint.

## V2 direction: competence before ego

The target is a skilled, infuriating opponent that sometimes prefers keeping a
juggle alive to attempting a finisher. This is a **decision policy**, not special
powers: no modified timings, physics, spacing/ranges, hitboxes, damage, recovery
limits, input timers, or forced motion/hits. Technical execution must work even
at low ego. See [research and primary sources](../research/showboat_v2.md).

V2 adds a separate controller-only combat sidecar, shorter emotional lockouts,
state-confirmed dashdance, conservative KO-reset taunts, and a huge-lead
up-air-over-Knee preference. It is not a trained superhuman model; competitive
strength and the ability to dominate a good human remain to be established.

## More visible ego and precision blocking

The latest policy responds to playtest feedback: frequent short mockery while
an opponent recovers, rather than simply raising an ego number. See
[the native-mechanics audit](../research/showboat_ego_v3.md). Full KO taunts now
also work in normal **Versus Time** matches, including quickstart's fresh default;
the old stock-only restriction prevented them there.

Offstage antics are deterministic, independent of ego/emotional caution, and
short enough to recheck breathing room every update. Known Zelda/Mewtwo/Sheik
teleport phases veto them. Running Falcon may first send at most 12 neutral
samples to observe real RunBrake/Wait; no fabricated dash acceptance. A recovery
window is still a heuristic, not a guarantee against every future special.

`showboat_defense.c` adds a separate controller-only defense sidecar. At a
**fresh, empty native defense-7 melee decision**, it may choose immediate digital
R hardshield instead of the usual roll. It does not replace running native
scripts, delay an existing shield, or pump/release/repress for fresh windows.
Admission requires healthy shield (45–60), ordinary grounded normal-attack
capsules with initialized history, a matching native threat, flat shared support
and >22 clearance on both sides; grabs, specials, projectiles/items, aerials,
forced states and incompatible inputs keep native defense. The native three-frame
body forecast is not precise shield-contact timing.

An attempt holds for at most ten samples, with an abandoned-VM release tail.
Contact/shieldstun and preemption hand back to native processing immediately;
defense-7 handoff preserves held R until the native decision handles it. No
shieldstun, DI/SDI, timer, shield-health or physical-state manipulation. HUD
`BLOCK` (10) means a custom attempt; `PERFECT` (11) requires native fighter
powershield-contact evidence during that owned attempt—not GuardReflect alone.
Such a verified contact adds **8 ego once**; PERFECT expires after at most 30
module updates or leaving guard. Failed attempts retry after 12 updates; success
has no added lockout beyond real actionability and a naturally released sample.
Repeated perfect blocks require legally available opportunities, not guaranteed
success. Logs distinguish queued onset, guard acknowledgment and actual contact.

**Testing protocol:** finish offline checks, then ask here for readiness. Do not
launch or restart Dolphin until the tester explicitly confirms. The previous
quickstart playtest exited cleanly; a new build is not runtime-tested merely
because compilation or host fixtures pass.

### Ego-build checkpoint (before recorder)

- **221 tests pass:** 109 personality/orchestration, 29 combat, 53 movement,
  24 defense, HUD, two unlock and three quickstart tests. Actual-C debug 0/1
  sanitizer coverage where applicable; no inferred native physics from inputs.
- Native build/isolation passes. Five mod modules compile with MWCC `-warn all`
  in debug 0/1 without module-local diagnostics. All six disabled native hooks
  remain byte-identical to the C-stick baseline; original stock DOLs unchanged.
- Current DOL: **4,496,256 bytes**, SHA-1
  `0643071c098d78ab6d3339e3cc931647436b3594`.
- Python compile, shell syntax and whitespace checks pass. Isolated controller
  mapping remains unchanged (`00dc2b7a5339493fe11fcf93e3adba16e93e0451`).
- Logs: `build/showboat-ego-{tests,build,verify,checks}.log`. No new Dolphin
  launch or runtime-strength claim. Await explicit readiness; use FD/Battlefield
  with items off to exercise the advanced mockery/movement/blocking policies.

## Architecture traced so far

Local source, not external AI mods, is the ground truth:

- `Fighter_8006ABA0` calls `ftCo_800B3900` when CPU control is active
  (`ftCo_800A2040`: player is CPU, CPU mode is not 5).
- `ftCo_800B3900` in `ft/kinds/ftCommon/ftCo_0A01.c` updates observations
  (`800B33B0`), environment/behavior transitions (`800B2AFC`), dispatches
  decisions (`800B2790`), interprets commands (`800B3E04`), then performs
  mode-specific postprocessing (`800B0AF4`).
- `CpuFighter.x18` is the current behavior dispatcher ID, not an attack ID.
  Examples: 2 attack, 3 ranged action, 4 recovery, 7 defense, 9 grab/throw.
  `xC` is a separate CPU mode. Unknown fields retain upstream names.
- `800B2790` builds a new script only when `csP == NULL` and
  `command_duration == 0`. It calls `800ADC28` then dispatches on `x18`.
- `ftcmdscript.c` already supplies a bounded 256-byte script buffer, button
  press/release commands, analog axes, waits and `Done`. `800B462C` rewinds
  writing, `800B49F4` commits a script, `800B4A78` clears script AND inputs.
  `Done` alone does **not** release held inputs.
- `800B3E04` writes `CpuFighter.buttons/lstick/cstick/triggers`.
  `Fighter_Spaghetti_8006AD10` consumes these through `ftCo_GetCpu*` getters, scales
  stick values, computes button edges and runs normal fighter input handling.
  No position, damage, velocity or action-state forcing is needed.
- CPU initialization is `800A101C`. It resets scripts, targets, queues and
  observations; `x7C` starts at a random 0–9, so it is not a reliable new-match
  sentinel. Use an explicit mod reset hook instead.

## Integration

`src/melee/mod/showboat_ai.c` owns six sidecars, not padding or unknown game
fields. Eligibility requires normal CPU mode **4**, literal level **9**,
`FTKIND_CAPTAIN`, active CPU control, and the primary entity of a player slot.
The mod additionally requires **exactly one other instantiated player**, not an ally,
and no active secondary opponent entity (Nana). Multi-opponent fights, training
orders, human Falcon, other levels and characters
keep vanilla behavior. Existing C-stick changes on the base branch remain.

Hooks (all behind `SHOWBOAT_AI`):

1. `ftCo_800B3900`: after vanilla mode/priority arbitration, call
   `ShowboatAI_Update`. If false, call the unchanged script builder. Always run
   the original interpreter and partner postprocessing, then
   `ShowboatAI_PostInput` for a narrowly guarded analog-only L-cancel overlay.
   `ShowboatCombat_RestoreInput` runs before update gates/reset/taunt returns.
   Movement flourishes yield to fresh native attacks; combat cleanup compares
   bounded script identity and does not erase a replacement native priority.
   Mod takeover clears stale `xA4` and controls before emitting normal inputs.
2. `ftCo_800B4AB0`: adjust only weights in the **local eligible-candidate copy**
   before summation. All range/level/modulo/allowlist/denylist filters, selection
   RNG calls and shared archive data remain unchanged.
3. `Player_InitOrResetPlayer`: clear that slot's sidecar, preventing cross-match
   pointer reuse. Updates also check owner and `x8_spawnNum`; respawning clears
   antics and penalizes ego instead of restoring initial confidence.
4. `Fighter_8006ABA0`: outside the CPU-control gate, suspend active ownership.
   Control changes to human/mode 5 cannot freeze and later resume a stale action.
   Temporary inactive/death states preserve ego for the subsequent life check.

### Attack selection and verified assets

`ftCo_AttackEntry` is a 0x24-byte record: script ID, prediction horizon, attack
rectangle, weight, modulo divisor and minimum CPU level. The main selector
`800B4AB0` predicts relative positions, rejects ineligible candidates, copies
survivors into a 32-entry stack list and makes a cumulative weighted random
choice. This is not a universal damage/knockback score. `800B52AC` does the
weapon-expanded variant; `800B5AB0` handles items; `800B6208` is a context-free
weighted choice and is deliberately not hooked.

`Fighter_804D64FC` comes from `PlCo.dat`: `x4[kind]` grounded, `x8[kind]` aerial,
`x10[kind]` anti-shield, `x18[kind]` weapon and `x1C[kind]` edgeguard candidates.
The `cmdscripts` pointer table is **shared, indexed by script ID**, despite its
upstream comment. The two eight-entry arrays labelled move queues are used as
candidate allowlist (`xA8`) and denylist (`xCC`) by these selectors.

Decoded the local US v1.02 CISO's `PlCo.dat` in memory, checking DAT relocation
pointers, disc ID/revision and FST. Offsets below include the DAT's 0x20 header:

| Move | Script | Candidate offset | Weight | Modulo / min level |
|---|---|---|---|---|
| Up-air | 6 | 0x155C (air) | 1 | 5 / 0 |
| Knee | 8 | 0x1580 (air) | 1 | 15 / 0 |
| Stomp | 10 | 0x15C8 (air) | 1 | 5 / 0 |
| Punch | 17 | 0x13AC (ground) | 10 | 60 / 3 |

Verified script bytes, for reproducible interpretation (not entire assets):

```
06: 80 00 81 50 86 01 81 00 87 01 7F  # up, A, release
08: 91 50 81 00 86 01 80 00 87 01 7F  # facing +X, A, release
0A: 80 00 81 B0 86 01 81 00 87 01 7F  # down, A, release
11: 80 00 81 00 88 01 89 01 7F        # neutral B, release
```

Script 10 also exists in the ground table as down-A. The hook therefore checks
**aerial table identity**, not just script ID. It never substitutes a move for
an ineligible candidate. Falcon's existing forward-floor exclusions in
`800B77E8` are preserved. No deliberate offstage pursuit is added.

### Movement, targeting, defense and recovery

- `800B2AFC` dispatches CPU mode; normal mode 4 uses `800B24B8`.
- `800ADE48` is high-level priority arbitration. It can flush scripts for
  damage, ledge, grab, recovery, defense and other important state changes.
- `800A4BEC` chooses an eligible non-ally attack target, with cached target
  state; `800A53DC` can choose a different approach target. `cpu.x44` is the
  attack target, `xF0/xF4` are defensive threats. The mod never replaces them.
- `800ABA34` routes locomotion to grounded `800AB224` / airborne `800A9CB4`.
  `800AA42C` handles same-island movement; navigation destination is `cpu.x54`.
- `800BB9B4` scans threats; `800BA9A0` builds defense inputs (behavior 7).
- `800A2C80` detects recovery; `800A8DE4`, `800A9904`, `800A96B8` plan it and
  issue normal jump/up-B inputs. Ordinary airborne locomotion can also recover,
  so preserving only behavior 4 would not be sufficient.

The mod reacquires its sole opponent via live player slots each update. This
allows detecting a KO when vanilla clears `x44`, without retaining a dangling
opponent pointer. Stock loss is approximate credit: self-destructs also count.

### State and ego

Each sidecar owns identity/spawn, opponent slot, ego, percent/stock/death
baselines, event latches, private deterministic RNG, cooldowns and action age.
No heap allocation, game-struct extension or writes to fighter physics.

| Event/condition | Effect |
|---|---|
| Initial ego | 55, clamped to 0–100 |
| Opponent damage increase | +2 + floor(0.4 × damage), capped +12/update |
| Damage during Falcon Knee/Stomp/Punch | additional +8, celebration window 120 |
| Opponent death/stock loss | +22, celebration window 180; KO dedup window 240 |
| Sustained advantage every 90 updates | +4 |
| No sustained advantage, ego >55 | −1 per 90 updates |
| Taking damage | −3 − floor(0.5 × damage), serious for 90 updates |
| Hit within 30 updates of short style / 75 of taunt start | additional −10 |
| Stock loss/new life | −15; serious for 120 updates |
| Entering physical danger (not initial entry/death) | −4; serious at least 30 |

Advantage means stock lead in a stock match, percent lead ≥30, or opponent
≥100% while Falcon <80%. Physical danger includes capture links, forced
entry/rebirth states, hitstun, and airborne with no safe floor below. High percent
alone no longer perpetually suppresses personality. The separate aerial style
weight boost remains conservative at ≥110%; competence is independent of ego.
Damage is approximate attribution, not a combat-event bus; items/hazards can
contribute. Normal damage and velocity remain entirely game-owned.

Accessible observations used: `cur_pos`, `self_vel`, `dmg.x1830_percent`,
`ground_or_air`, `motion_id`, `cur_anim_frame`, `facing_dir`, hitstun `x221C_b6`,
hitlag `x2219_b5`, capture links and `Player_GetStocks`. Whole-fighter protection
comes from `ftColl_8007B868`. `cpu.xFA_b5` is recomputed by vanilla's floor-below
and blast-margin check: it is a veto, not proof of recoverability. Ground
antics additionally require both island-endpoint distances >22, using
`800A2A70` (which returns −1 for missing island/air).

### Independent combat layer

`showboat_combat.c/.h` owns six separate identity/spawn sidecars, bounded script
snapshots, input age and mod-only retry budgets. It runs regardless of ego and
serious mode; physical unavailability, items/capture and native defense/recovery/
grab priorities still veto it. It never calls action-entry or CheckInput helpers.

- **Standing grab:** grounded Wait/walk, facing a rival within 11 units on the
  same floor, slow relative movement, no protection/items/capture. Reactive
  against shield or actual remaining landing lag / compatible grounded hitstun.
  Neutral sample → recheck → one Z → acknowledge Catch and hand back to native
  pummel/throws. The rival can release shield; no guaranteed grab claim.
- **Direct airborne Knee/up-air:** actual free Jump/Fall variants only, not a
  scripted jump-age chain. FD/Battlefield, valid safe floor under both predicted
  paths, compatible rival damage hitstun through startup + reserve. Read-only
  projection includes gravity, friction, knockback decay and both extremes of
  subsequent native drift. Reject predicted floor collision/edge escape before
  the active frame. Choose Knee if its 14-frame intercept fits; otherwise up-air
  at 6 frames. Neutral → recheck → one A/direction → actual AttackAirF/Hi
  acknowledgment → release/yield. Root-relative fit boxes are heuristics, not
  decoded hurtbox/sweetspot guarantees. No forced jump, drift, hit or animation.
- Both use at most two sampled inputs, 45-update mod cooldowns after failed
  attempts (none after acknowledged actions) and bounded 3/5/13-byte native
  scripts with a release tail. Script fingerprinting includes
  actual cursor/resume offset; abort releases only the still-owned script and
  preserves a fresh native cached attack/replacement script.
- **L-cancel overlay:** descending ordinary aerial attack with landing-lag flag,
  no existing effective LR sample, no capture/hitlag/hitstun; read-only ECB sweep
  predicts touchdown in 1–3 frames. Borrow analog L=128 for one sample, preserve
  every button and stick, then restore only that channel if unchanged. The real
  input preprocessor creates LR; the retail landing function decides whether
  it cancels. No digital L/R, airdodge, tech-counter write or landing-lag edit.
  Native DI/SDI/techs and recovery remain intact.

Offensive short-hop chasing, a full punish planner and learned opponent prediction
are not implemented (the separate wavedash uses a hop only for grounded movement). Floor/ECB projections use current geometry and can be wrong;
state acknowledgment proves acceptance, not connection or competitive strength.

### Wavedash movement

`showboat_movement.c/.h` adds an independent six-slot controller sequence; it is
not an ego roll or an animation/physics patch. New starts are considered after
combat declines. An active sequence is serviced before other aerial tactics or
personality, while still yielding to native safety/priority changes. Suspend and
slot/stock/target resets cancel only its own script; fresh native selections and
replacement scripts are retained. The HUD label is `WDASH` (9).

The sequence uses a real sampled neutral → single X → observed KneeBend with
both jump buttons released → first actual Jump → digital shoulder plus diagonal
down → observed EscapeAir or direct LandingFallSpecial. A same-frame landing can
hide EscapeAir between CPU hooks; it must not be mistaken for failure. The
engine's ordinary jumpsquat, airdodge and ten-frame landing lag remain intact.
No input-counter repair, forced facing, position/velocity writes, or mutating
CheckInput/Enter helpers. Missing acknowledgments/timeouts yield to vanilla.

The intent is frequent useful repositioning, not a slower substitute for every
run: approach at 65–110 units and committed-attack retreat at 45–65, initially
on FD/Battlefield static main floors. Entry needs 40 units of edge clearance;
22 must remain after the entire conservative coast/dodge/landing projection.
Bounds use verified flat main-floor chains; the rival may occupy a coplanar outer
strip, but our touchdown stays on its admitted line. Coast is an interval—friction
cannot be assumed to preserve helpful momentum.
Fast retreating rivals and momentum toward the rival during a retreat are vetoed.
The diagonal is X=±90/Y=−64. An 18-update attempt budget and 30-update failed
retry bound attempts; there is no success cooldown beyond engine actionability.
Long-distance running, real punishes, defense, recovery, platforms and unsafe
contexts retain vanilla behavior. No out-of-shield variant yet. Low ego and
serious-mode personality suppression do not disable this technical movement.

See [source/data research](../research/showboat_wavedash.md) for native state
flags, input normalization, floor/landing behavior and verification limits.

### Implemented personality actions / tuning

- **KO-reset taunt:** recent KO, stock match with rival stocks remaining or
  normal Versus Time without elimination/removal routing; primary rival only.
  Grounded on FD/Battlefield's static main floor, no existing items.
  A running winner can send neutral for at most 18 updates to settle through
  real Dash/RunBrake into a free stance (40-unit runway, bounded speed); it never
  forces Wait or spends Up early. Require death countdown + mandatory Rebirth ≥80 frames,
  including 20 frames of reserve beyond retail Falcon's 60-frame taunt. Recheck
  before Up-D-pad. Never count actionable RebirthWait, distance alone, or
  invulnerability as safety. Separate 180-update cooldown; a certified reset
  bypasses low ego/emotional serious mode, never physical danger. Real motion
  state must acknowledge the pulse. No custom final-stock victory pose yet.
- **Offstage mockery:** rival airborne beyond the connected ledge by >30 units,
  with ≥100 horizontal separation after a four-update observed-closing reserve.
  FD/Battlefield main floor, no items, signed runway/velocity/identity guards.
  Deterministic even at ego zero: up to 24 dance updates or a 12-update crouch
  fallback, 18-update retry, 30-update recent-hit veto. Recheck every sample;
  native threats and real conversions win. No full live-recovery taunt gamble.
- **Dashdance:** ego ≥30, idle native priority, no selected attack; an empty VM
  or verified mundane remaining locomotion only. Rival 55–130 units away,
  no immediate knockdown/hitstun/landing punish.
  FD/Battlefield static main floor only, no items, signed endpoint clearance
  ≥40 at start / ≥30 while running, bounded displacement and next-leg runway.
  One neutral sample, then legal full horizontal flicks. Reverse only after
  actual Dash frame 5 and observed facing; hold through Turn. At most two
  reversals and 24 input updates. 90% opportunity roll, 24-update failed-roll
  cooldown, 48 successful (36 at ego ≥80). Yield immediately to real attacks,
  defense, recovery, nearby pressure and lost clearance; no forced dash cancels.
- **Swagger:** two short crouches after a far (70–85), facing-away ordinary
  attack with ego ≥45, 50% opportunity roll. Idle priority only, no native
  script/attack, no pass-through platform, yields to a real punish. A heuristic
  flourish, not a precise whiff-punish detector.
- **Falcon Punch:** ego ≥75, facing a shield-broken `Furafura` opponent with
  `grab_timer >300`, 18–42 units away and within 12 vertically; standing only,
  35% roll. No longer replaces ordinary knockdown/tech-chase opportunities.
  Mash can shorten daze, so this is NOT a guaranteed hit. Actual SpecialN must
  acknowledge the B pulse; animation and startup remain untouched.
- **Knee/Stomp preference:** eligible aerial candidates get multiplier
  `1 + 2 × (ego −45) /55` above ego 45 (maximum 3×), with the original safety
  vetoes. No grounded down-A boost.
- **Selective mercy / JUGGLE:** ego ≥90, stock lead ≥2, own percent ≤40, rival
  ≥80% in hitstun, both central on FD/Battlefield. Already eligible up-air script
  6 gets 4× weight, Knee gets 0.35× instead of its ego boost. This favors keeping
  control over attempting a finisher; it never refuses all attacks or prevents
  a KO. Up-air can still kill and native/direct combat can still choose Knee.
  It is a conservative policy, not proof Falcon can end the match on demand.
- Swagger/Punch share a 90-update cooldown; neutral dance and offstage mockery
  use the shorter budgets above. Opportunity rolls are consumed when actionable,
  not during own lag. Low ego suppresses discretionary neutral antics, **not**
  offstage breathing-room mockery or independent combat/movement/defense.

The short scripts own only CPU controller output. Every frame checks danger,
priority behavior, compatible motion, target presence and floor margin.
Finishing cancels input ownership, **not** an already-started game animation:
Falcon must live with an uncancellable taunt/Punch just like a human. This is
intentional risk, not a state-machine lockup.

### Build and instrumentation

```
sh tools/build_showboat.sh
# Output: build/showboat/GALE01/main.dol
# Only after the tester explicitly confirms readiness:
sh tools/run_showboat.sh /absolute/path/to/original-US-v1.02.ciso
```

Requires the local setup in `LOCAL_SETUP.md`. New configure options:
`--showboat-ai` (explicit opt-in), `--showboat-ai-debug` (event OSReport logs),
`--showboat-ai-hud` (on-screen readout; independent of logging). Without the
base flag all hooks compile out and the new objects are not linked.
The helper enables all three and builds only the modified DOL, not retail hash
verification. `tools/project.py` adds an explicit optional extra-DOL-unit list;
retail split addresses and symbol metadata are unchanged. Stock and C-stick
build directories are not overwritten.

The DOL grows beyond the stock disc allocation (only 32 spare bytes). Do not
use the fixed-allocation C-stick packager. The launch helper extracts the original
disc once to `build/showboat/disc`, copies only the rebuilt executable into that
generated tree, and boots `disc/sys/main.dol` as a Dolphin virtual disc with a
separate user profile. No original assets, original executable or normal save
are overwritten. Stop the prior session before rerunning the helper. Configure
a controller in this isolated profile before manual testing. On first use the
helper copies only `GCPadNew.ini` from the normal macOS Dolphin profile if it
exists; existing test-profile mappings and all normal-profile files are left
untouched. If the selected SDL device differs, choose the connected controller
in Controllers → Port 1 → Configure.

**Boot finding:** standalone DOL + `DefaultISO` reached an early sound-file DVD
bounds panic in this environment. Do not use that route. Virtual-disc boot
runs the retail apploader and successfully reaches Melee initialization. The
C-stick ISO baseline also initializes successfully.

Debug prints include ego deltas/reasons, input action IDs (0 vanilla, 1 taunt,
2 swagger, 3 Punch, 4 dance, 5 grab, 6 Knee, 7 up-air, 9 wavedash), age,
start/acknowledgment/exit/cancellation reasons and throttled eligible
Knee/Stomp weighting messages. These weighting messages do not claim a move
was selected or hit. Logs: `build/showboat/dolphin-user/Logs/dolphin.log`.

The optional HUD (`showboat_hud.c/.h`) shows a shadowed white line such as
`FALCON P2 EGO 62 /100 (VANILLA) SERIOUS 120f` near the upper left. EGO is
confidence, not fighter damage; SERIOUS suppresses personality, not competence,
in CPU updates (normally 60/second). Action labels generally mean **input
ownership**, not animation: a short input can start a long taunt/Punch. `JUGGLE`
means the selective-mercy weighting policy was active within the last 45 updates;
it is not a claim of a connected hit. Analog L-cancel is an overlay, logged
separately rather than hiding the primary action.

It reuses the always-initialized DevText screen camera and built-in stroke font,
with private static character buffers rather than shared text-pool entries.
A single render GObj owns no fighter pointers. Slot resets clear rows; live-list
and callback/userdata validation rejects stale GObjs after scene heap resets.
No repeated font/archive loads, new gameplay cameras or on-screen asset edits.

## Boot directly to the test matchup

The build helper enables `--showboat-quickstart` by default. After normal
save/card initialization it enters **normal Versus character select**, with:

- P1 human, **no character selected**;
- P2 CPU **Captain Falcon, level 9, normal CPU type 4**, default costume;
- other slots disabled and teams off.

Pick a character and press Start normally; the stage is still your choice.
This is a menu preset at each boot/native reboot, **not** an automatic match or a
preset reapplied after results, stage-select cancellation, or Back. Normal CPU
and rule changes remain editable. Unrelated native-initialized player values,
ratios, scale, and saved match-rule preferences are not reset by this hook.

Only `gmboot.c` receives `SHOWBOAT_QUICKSTART`. Its `bootOnLeave()` preserves
Pikmin/card handling and `lbCardGame_DecideGameMode`, seeds the existing VS data,
and requests `GM_VS`; the native mode begins at CSS and loads its own assets.
Save/error and progressive-scan prompts still behave normally. Port 1 must have
an ordinary connected controller; the existing Dolphin mapping is unchanged.
CSS uses external `CKIND_CAPTAIN` (0), **not** internal `FTKIND_CAPTAIN` (2).

Raw `configure.py` defaults off and requires `--showboat-ai` for this option.
To retain the normal title/main-menu sequence:

```sh
sh tools/build_showboat.sh --no-showboat-quickstart
.venv/bin/python tools/verify_showboat.py --no-quickstart
```

Unlocks are independent: add `--no-showboat-unlock-all` to that build and
`--no-unlocks` to verification if desired. Rebuild without opt-outs to restore
the testing defaults. Stop the old Dolphin session before running the usual
launch helper; rebuilding alone does not replace its active virtual-disc DOL.

### Quickstart verification

- **158 tests pass**, including actual extracted boot callbacks under six
  absent/0/1 flag × debug 0/1 ASan/UBSan configurations, native declaration
  extraction, card/trophy/transition ordering, adjacent-state preservation,
  boot-only scope, and parser/helper defaults.
- Native build/isolation passes: **4,473,216 bytes**, SHA-1
  `bce3be8563e0f1d3afb2fd0b10b436d02f177b35`. Six hooked objects plus the four
  mod modules differ from C-stick. `gmboot.c` compiles with MWCC `-warn all`
  in debug 0/1 without local diagnostics; with flags removed its object is
  byte-identical to the C-stick baseline.
- Quickstart opt-out reproduces the entire previous wavedash DOL byte-for-byte:
  `e01be10808e5027b7eb87e6316d8a80f563c63b9`. Logs:
  `build/showboat-quickstart-{tests,build,verify}.log` and
  `build/showboat-quickstart-off-{build,verify}.log`.
- Launched after the previous Dolphin session had exited. The existing Switch
  Pro mapping is unchanged; staged and virtual-disc DOL hashes match. At
  `DbLevel 0`, runtime reports unlocks first, then
  `SHOWBOAT QUICKSTART: VS CSS; P1 choose, P2 Captain CPU9 (ckind=0 type=1 level=9)`.
  A subsequent match logs P2 normal level-9 Falcon initialization in singles.
  Log: `build/showboat/quickstart-stdout.log`. Exact visual layout remains a
  human check, not a claim made by the host tests.

## Automatic test-profile unlocks

`tools/build_showboat.sh` now also passes **`--showboat-unlock-all`**. After
memory-card load/validation, `gmMainLib_8015FA34` executes its existing native
progression-unlock block regardless of debug level: all 11 hidden-character
bits, all 11 hidden-stage bits, option flags, and native unlock-notification
bookkeeping. Starter characters/stages remain available normally. This enables
Final Destination, Battlefield, the full roster and unlock-gated match options
without grinding achievements or importing an external save.

It does **not** enable global developer mode, Action Replay/Gecko, combat cheats,
invulnerability or changed fighter data. It does not fabricate trophies, records
or event-match completions: this is full gameplay access for AI testing, not a
claim of a perfect collector's save. Normal autosaves may persist these progress
flags in the isolated test profile. Original disc/stock DOL/normal Dolphin
profile are not modified.

The additional flag requires `--showboat-ai` and only defines
`SHOWBOAT_UNLOCK_ALL` for `melee/gm/gmmain_lib.c`. Ordinary configure builds still
default off. To test natural progression instead:

```sh
sh tools/build_showboat.sh --no-showboat-unlock-all
.venv/bin/python tools/verify_showboat.py --no-unlocks
```

The default helper build is validated without `--no-unlocks`; it expects the
one additional save-initialization object. Disabling the flag does not relock
progress already autosaved—restore the backed-up test save or use a fresh test
profile. Runtime confirmation prints:
`SHOWBOAT UNLOCK: characters=07ff stages=07ff options=ff` (higher preexisting bits
are preserved). This is a real post-load readback, not a cheat-code assumption.

`tools/tests/test_showboat_unlocks.py` compiles the actual post-load function and
native character/stage mask helpers with the flag absent/0/1 under ASan/UBSan.
It covers loaded/new/invalid-save branches, preserved native debug behavior,
unlock-before-finalization ordering and mask readback. Notification helpers are
explicit spies; it is not a memory-card or UI emulator test.

### Historical unlock-enabled verification

- At the unlock-only V2 checkpoint, **99 tests passed**, including the two unlock
  tests and AI/combat/HUD regressions. Default build/validator: **4,453,984 bytes**,
  SHA-1 `d78122c75886b5a0a09e3698f424b90052cd534e`.
- The explicit opt-out build also passes `verify_showboat.py --no-unlocks` and
  reproduces the previous V2 DOL **byte-for-byte** (SHA-1
  `f63c0cfb49c325e9dacb4f040f042e4464972d66`). The only additional changed source
  object with unlocks enabled is `melee/gm/gmmain_lib.o`.
- With user authorization, stopped V1, backed up isolated `Config` and `GC`
  (including its Melee GCI), and launched the unlocked V2 virtual disc. Backup:
  `build/showboat/profile-backups/20260909-053023-pre-unlocks/`; manifest also at
  `build/showboat/unlock-profile-backup.json`. Normal profile/saves are untouched.
- Dolphin boots through Melee initialization and the **actual game** logs
  `SHOWBOAT UNLOCK: characters=07ff stages=07ff options=ff` after save load.
  CI also confirms `SDL/0/Nintendo Switch Pro Controller`. The controller mapping
  was retained, not replaced. Runtime log: `build/showboat/v2-unlocked-stdout.log`.
- The running virtual-disc DOL matches the verified new build hash. Initial live
  match logs also show P2 Falcon9 initialization and an analog L-cancel pulse at
  low ego; that confirms hook execution, not a successful landing cancel.
  Gameplay strength, hit conversions and visual HUD behavior still require human testing;
  successful boot/unlock readback is not a competitive-strength benchmark.

## Manual test procedure

Start from a fresh match, never a stock/C-stick savestate. Use normal 1v1 stock
Versus, human P1 and CPU P2 Captain Falcon level 9, initially Final Destination.
On CSS, change an unused panel's NONE label to CPU, move its token to Falcon,
and set level 9. Leave other slots NONE.

1. **Baseline:** fight normally; compare movement, defense, recovery and stock
   differential with the C-stick/native level-9 build against the same human.
2. **Execution:** shield close in front of grounded Falcon; look for GRAB
   input and acknowledgment, followed by normal pummels/throws. Observe aerial
   landing-cancel logs and actual landing behavior, including at low ego.
3. **Conversions:** watch for direct KNEE/UPAIR acknowledgment during aerial
   hitstun followups. Inputs/accepted action states do not alone prove hits.
4. **Movement:** leave a medium neutral gap on FD/Battlefield's main floor.
   Look for WDASH, a real short jump/down-diagonal airdodge and landing slide;
   input logs alone do not prove displacement. Test that long gaps still use run
   and real punishes/defense interrupt movement attempts. DANCE remains a separate
   personality flourish with actual direction reversals.
   Test near edges and on platforms: no custom dashdance there.
5. **KO:** let him take a stock while grounded centrally with time left in
   the death reset. Expect the real full TAUNT even at high percent/residual
   serious mode if every physical/reset gate is satisfied. No late respawn taunt.
6. **Toy policy:** give him a two-stock lead, high ego, and ≥80% on your current
   stock while he has ≤40%. Central aerial hitstun can activate JUGGLE weighting;
   look for up-air preference, not guaranteed nonlethal hits or a refused KO.
7. **Punch/punishment:** ordinary knockdowns must not trigger custom Punch.
   A long shield-break daze may. Hit him after a flourish: ego falls, personality
   pauses briefly, but the independent technical assistance remains available.
8. **Isolation/safety:** test grabs, launch/offstage, Battlefield platforms,
   level-8 Falcon, level-9 Fox, human Falcon, FFA and live Ice Climbers. Preserve
   native recovery/defense and never leave stuck controls or cross-slot HUD rows.
9. **Lifecycle:** restart matches and change CPU settings/control. Initial ego
   resets; ordinary stock loss lowers it, and ownership/borrowed analog clears.
10. **Native side-B safeguard:** on FD/Battlefield's main floor, allow native
    throw follow-ups near an edge, then also near center or facing inward.
    Look for `SIDE-B VETO` / event128, not a claimed saved stock. Verify the B
    pulse is actually absent and normal side-B remains available with runway.
    A retained native wait after veto is expected; watch the later follow-up
    rather than assuming the entire native chain has been redesigned. On
    Battlefield, also allow throw follow-ups on each raised platform and check
    both directions: eligible priority9 pulses should be suppressed there.
    Observe the retained jump/attack/up-B tail and subsequent landing, not just
    the veto event. Ordinary priority2/aerial specials should still occur.

Use HUD and logs to distinguish native moves from custom input starts. Play
several fair matches as well as staged observations: deliberately feeding the
CPU proves neither its strength nor its ability to sustain a real lead.

## Remaining limitations / reverse-engineering questions

- Match outcome is not attributed to exact hit sources: hazards/items and
  self-destructs may count as success. Death-animation and confirmed stock
  accounting use a 240-update dedup window; very fast successive KOs can merge.
- Swagger uses motion/range/facing, not exact remaining attack lag. Punch can
  miss if the rival mashes out of daze. Those remain ordinary game consequences.
- Long poses and dashdance support FD/Battlefield main floors with no existing
  items; no prediction of future item spawns. Other stages retain landing-cancel,
  standing-grab and existing conservative personality behavior, but no new
  direct aerial interception, wavedash, dance or KO-reset taunt.
  No intentional offstage style.
- A started taunt/Punch cannot be magically cancelled by input ownership ending.
  Cancellation means vanilla controls resume, not forced escape from animation.
- The candidate data's geometric fields and divisors are followed as implemented;
  not every script, mode, target-cache flag or special-stage case is decoded.
- Vanilla still owns most decisions. Technical assistance at low ego is new,
  but stronger play, hit conversion rates and safe toying need human benchmarks.
  No guaranteed kill evaluation, full opponent model, trained network or complete
  combo/tech-chase planner. Fixed-address third-party cheats and stock/netplay
  savestates are not compatible with this shifted DOL.

## Best next improvements

Main-floor and one inward platform veto are now live-observed. Retained tails
vary in usefulness: one up-B captures Kirby, another gets punished in landing
lag. Investigate context-sensitive continuation without blindly cancelling an
opaque native script. Also research pre-commitment awareness of slow specials:
the latest self-death follows a late dash-grab into Kirby's copied Falcon Punch,
not a side-B departure. The existing fresh7/ordinary-melee shield module does
not admit that situation; relaxing its gates is not a complete fix. Allowing selected inward platform drops would require a
separate supported air-coast/lower-floor landing analysis; it is deliberately
not assumed here. Further controlled tests should check main-floor central/inward
allowances and retained follow-up behavior before script ownership changes. The valid v2 capture also
motivates jab-conversion and defense-admission investigation, not more reckless
flourishes.

1. Benchmark V2 vs native level 9; measure acknowledged inputs, connected
   conversions, failed commitments, stock differential and personality frequency.
2. Add state-confirmed jump/intercept and tech-chase conversions, not guessed
   fixed-age input macros. Preserve native DI/SDI/techs until replacements win tests.
3. Attribute exact hits/KOs and estimate escape/kill options before expanding
   selective mercy. Up-air preference alone is not omniscient control.
4. Extend signed movement/reset safety to more stages and current projectiles;
   add recoverability-scored edgeguards only with validated return plans.
5. Tune frequent, interruptible disrespect from human feedback; a reckless
   flourish or a weak bot's missed punish is not the intended personality.

## Wavedash checkpoint verification and runtime

- **155 tests pass**: 70 personality/orchestration cases, 29 combat groups,
  53 movement cases, HUD and two unlock tests. Actual C, debug 0/1 and
  ASan/UBSan; no synthetic input-age-to-motion or physics simulation.
- Build and isolation validator pass: **4,472,992 bytes**, SHA-1
  `e01be10808e5027b7eb87e6316d8a80f563c63b9`. Exactly five hooked objects plus
  AI/combat/movement/HUD differ from C-stick. All five native hook units compiled
  without showboat defines remain byte-identical to the C-stick baseline.
- Four mod modules compile with MWCC `-warn all`, debug 0/1, without module-local
  diagnostics (existing upstream header warnings remain). Python compilation,
  shell syntax and `git diff --check` pass. Logs:
  `build/showboat-wavedash-{tests,build,verify,checks}.log`.
- Review fixes: bound the whole coast interval instead of crediting beneficial
  momentum; veto interruptible attacks as retreat commitment; clear an exact old
  movement VM after priority-only changes without losing the new priority/A4;
  verify scaled stage geometry and connected coplanar rival supports.
- Launched via the existing isolated virtual-disc helper, with the Switch Pro
  controller detected and `DbLevel 0`. Post-load unlock readback remains
  `characters=07ff stages=07ff options=ff`. Staged and virtual-disc DOLs match.
  Runtime log: `build/showboat/v2-wavedash-stdout.log`.
- **Boot is verified, actual wavedash displacement/frequency is not yet verified
  in a human match.** Look for WDASH and confirm jump/dodge/landing logs, real
  sliding, and useful pressure versus lost neutral frames. No strength claim
  follows from a successful host suite or boot.

## Historical V2 pre-wavedash verification

- `sh tools/build_showboat.sh` succeeds. HUD/debug DOL:
  **4,453,920 bytes**, SHA-1 `f63c0cfb49c325e9dacb4f040f042e4464972d66`.
- `python tools/verify_showboat.py` validates sections, entry point and RAM;
  stock DOLs remain unchanged. Exactly the four existing hook objects and the
  AI/combat/HUD modules differ from the C-stick baseline. All four hooked native
  units compiled with showboat defines removed remain **byte-identical** to that
  baseline. No gameplay assets, game-data tables or binaries are committed.
- **97 host tests pass**: 67 personality cases and 29 combat case groups, each
  with debug off/on and ASan/UBSan, plus the HUD lifetime/formatting test. The
  actual C modules are exercised, with explicit native enum extraction, bounded
  controller interpreters and physical/rules-write guards. Personality/combat
  integration is checked with spies; this is not a full native-engine simulation.
- All three mod modules compile with MWCC `-warn all`, debug off/on, with no
  module-local diagnostics. Existing decomp/SDK header warnings remain. Logs:
  `build/showboat/v2-checks/*-warnings.log`.
- Review/regression fixes include deferring the initial opposite dash flick
  through unturnable frames, bounded neutral settling for KO taunts, restoring
  borrowed analog before every early gate/reset, releasing our old script while
  retaining a fresh native cached attack, and removing artificial retry delay
  after an acknowledged combat action. Missing/failed input still has a bounded
  retry budget; no motion or game input timer is forced.
- `git diff --check`, Python compilation and shell syntax checks pass. Logs:
  `build/showboat-v2-{tests,build,verify}.log`.
- **At the initial V2 checkpoint, V2 had not yet been booted or played.** The user's existing V1 Dolphin
  session/controller profile was deliberately left alone. The running virtual
  disc still contains V1 SHA-1 `f278e0701a97269f929c4386b1344a06c07da402`;
  the new DOL is staged separately until an agreed restart. No V2 win-rate,
  actual hit conversion, visual acknowledgment or superhuman-strength claim is
  made from compilation or host tests.

## Historical V1 verification evidence

The following hashes, test counts and runtime observations describe V1, not V2.


- `sh tools/build_showboat.sh`: full MWCC/WiBo build succeeded; final incremental
  Ninja reported no work. DOL: **4,434,464 bytes**, SHA-1
  `f278e0701a97269f929c4386b1344a06c07da402` (HUD-enabled build).
- `python tools/verify_showboat.py`: all initialized section extents and RAM
  ranges, no initialized overlap, valid text entry, stock DOL hashes unchanged.
  Report: `build/showboat/verification.json`. Original and preserved stock DOL
  SHA-1 remains `08e0bf20134dfcb260699671004527b2d6bb1a45`.
- Compared all compiled objects against preserved C-stick build: only `fighter`,
  `player`, `ftCo_0A01`, `ftcpuattack` and new AI/HUD objects differ. Separately
  compiled all four original-file hooks **without** any showboat defines:
  each is byte-identical to the C-stick baseline.
- Both new modules also compile with `-warn all`. Existing SDK/decomp headers
  emit enum/redeclaration/empty-assert warnings; no module-local diagnostics.
  Logs: `build/showboat/showboat_{ai,hud}-warnings.log`.
- **45 host tests pass**:
  `python -m unittest discover -s tools/tests -p 'test_showboat*.py' -v`.
  44 personality cases compile the actual module, with native enum extraction,
  debug both off/on, ASan/UBSan, scripted-controller and physical-write guards.
  HUD mock test checks bounded formatting, render passes, allocation failure,
  six slots, object reuse and 100 bulk scene resets with sanitizers. These
  mocks do not prove native rendering, fighter animation or PPC behavior.
- Test-driven fixes include clearing stale input on opponent replacement and
  deduplicating stock/spawn observations in either order, without cooldown
  heuristics. Other safety fixes are described above.
- Dolphin 2606a: original C-stick ISO control and **pre-HUD showboat virtual
  disc** boot through the apploader to Melee initialization. Direct-DOL route
  failed early and was replaced, not counted as success.
- During the user's human-vs-Falcon9 match, logs show P2 initialization, ego in
  the 50s, eligible Knee/Stomp weighting at ego 54, loss of ego after damage and
  losing a stock, and a later opponent KO event. No custom taunt/swagger/Punch
  trigger was observed in that first match. Log: `virtual-disc-stdout.log`.
- The latest HUD-enabled DOL was restarted with user permission and boots
  successfully through Melee initialization. The isolated profile's keyboard
  mapping was backed up, the user's saved pad mapping copied in, and Port 1
  explicitly enabled. Dolphin's CI log confirms the exact configured device:
  `Added device: SDL/0/Nintendo Switch Pro Controller`. Original profile and
  saves remain untouched. Log: `hud-controller-stdout.log`.
- HUD legibility and button response still require the user's visual/physical
  confirmation. Screen capture failed (`could not create image from display`)
  and Accessibility automation is off; no automated visual claims are made.
- `git diff --check`, Python syntax checks and shell syntax checks pass. No
  game assets or binary artifacts are tracked or pushed.
