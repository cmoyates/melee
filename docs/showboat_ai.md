# Showboat Falcon AI

Tracking: https://github.com/cmoyates/melee/issues/1
Branch: `mod/showboat-ai`, based on the existing single-player C-stick mod.
Initial working tree was clean; that mod is retained.

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

Short-hop chasing, a full punish planner and learned opponent prediction are
not implemented. Floor/ECB projections use current geometry and can be wrong;
state acknowledgment proves acceptance, not connection or competitive strength.

### Implemented personality actions / tuning

- **KO-reset taunt:** recent KO, normal stock match with rival stocks
  remaining, grounded on FD/Battlefield's static main floor, no existing items.
  A running winner can send neutral for at most 18 updates to settle through
  real Dash/RunBrake into a free stance (40-unit runway, bounded speed); it never
  forces Wait or spends Up early. Require death countdown + mandatory Rebirth ≥80 frames,
  including 20 frames of reserve beyond retail Falcon's 60-frame taunt. Recheck
  before Up-D-pad. Never count actionable RebirthWait, distance alone, or
  invulnerability as safety. Separate 180-update cooldown; a certified reset
  bypasses low ego/emotional serious mode, never physical danger. Real motion
  state must acknowledge the pulse. No custom final-stock victory pose yet.
- **Dashdance:** ego ≥40, idle native priority, no selected attack or running
  native script, rival 55–115 units away, no immediate knockdown/hitstun punish.
  FD/Battlefield static main floor only, no items, signed endpoint clearance
  ≥40 at start / ≥30 while running, bounded displacement and next-leg runway.
  One neutral sample, then legal full horizontal flicks. Reverse only after
  actual Dash frame 5 and observed facing; hold through Turn. At most two
  reversals and 24 input updates. 75% opportunity roll, 45-update failed-roll
  cooldown, 90 successful (60 at ego ≥80). Yield immediately to real attacks,
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
- Short styles share a 90-update cooldown. Opportunity rolls are consumed when
  actionable, not during own lag. Gaining momentum rebuilds confidence; losing
  ego suppresses personality, **not** the independent combat assistance.

The short scripts own only CPU controller output. Every frame checks danger,
priority behavior, compatible motion, target presence and floor margin.
Finishing cancels input ownership, **not** an already-started game animation:
Falcon must live with an uncancellable taunt/Punch just like a human. This is
intentional risk, not a state-machine lockup.

### Build and instrumentation

```
sh tools/build_showboat.sh
# Output: build/showboat/GALE01/main.dol
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
2 swagger, 3 Punch, 4 dance, 5 grab, 6 Knee, 7 up-air), age,
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
4. **Dance:** leave a medium neutral gap on FD/Battlefield's main floor. Look
   for DANCE, real direction reversals, and immediate pressure/punish yielding.
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
  direct aerial interception, dance or KO-reset taunt.
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

## V2 verification and runtime status

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
- **V2 has not yet been booted or played.** The user's existing V1 Dolphin
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
