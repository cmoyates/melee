# Showboat Falcon AI

Tracking: https://github.com/cmoyates/melee/issues/1
Branch: `mod/showboat-ai`, based on the existing single-player C-stick mod.
Initial working tree was clean; that mod is retained.

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

## V1 integration

`src/melee/mod/showboat_ai.c` owns six sidecars, not padding or unknown game
fields. Eligibility requires normal CPU mode **4**, literal level **9**,
`FTKIND_CAPTAIN`, active CPU control, and the primary entity of a player slot.
V1 additionally requires **exactly one other instantiated player**, not an ally,
and no active secondary opponent entity (Nana). Multi-opponent fights, training
orders, human Falcon, other levels and characters
keep vanilla behavior. Existing C-stick changes on the base branch remain.

Hooks (all behind `SHOWBOAT_AI`):

1. `ftCo_800B3900`: after vanilla mode/priority arbitration, call
   `ShowboatAI_Update`. If false, call the unchanged script builder. Always run
   the original interpreter and partner postprocessing. A cancelled or completed
   style clears its script/inputs and cached attack `xA4`, then resumes vanilla
   dispatch on this update. Cached selections made during antics are discarded.
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
| Knee | 8 | 0x1580 (air) | 1 | 15 / 0 |
| Stomp | 10 | 0x15C8 (air) | 1 | 5 / 0 |
| Punch | 17 | 0x13AC (ground) | 10 | 60 / 3 |

Verified script bytes, for reproducible interpretation (not entire assets):

```
08: 91 50 81 00 86 01 80 00 87 01 7F  # facing +X, A, release
0A: 80 00 81 B0 86 01 81 00 87 01 7F  # down, A, release
11: 80 00 81 00 88 01 89 01 7F        # neutral B, release
```

Script 10 also exists in the ground table as down-A. The hook therefore checks
**aerial table identity**, not just script ID. It never substitutes a move for
an ineligible candidate. Falcon's existing forward-floor exclusions in
`800B77E8` are preserved. No deliberate offstage pursuit is added in V1.

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
| Initial ego | 30, clamped to 0–100 |
| Opponent damage increase | +2 + floor(0.4 × damage), capped +12/update |
| Damage during Falcon Knee/Stomp/Punch | additional +8, celebration window 120 |
| Opponent death/stock loss | +22, celebration window 120; KO dedup window 240 |
| Sustained advantage every 120 updates | +3 |
| No sustained advantage, ego >30 | −1 per 120 updates |
| Taking damage | −5 − floor(1.5 × damage), serious for 300 updates |
| Hit within 180 updates of style start | additional −20 |
| Stock loss/new life | −30; serious for 600 updates |
| Entering hitstun/offstage/high-percent danger | −15; serious at least 180 |

Advantage means stock lead in a stock match, percent lead ≥30, or opponent
≥100% while Falcon <80%. Danger includes ≥110% self damage, capture links,
forced entry/rebirth states, hitstun, and airborne with no safe floor below.
Damage is approximate attribution, not a combat-event bus; items/hazards can
contribute. Normal damage and velocity remain entirely game-owned.

Accessible observations used: `cur_pos`, `self_vel`, `dmg.x1830_percent`,
`ground_or_air`, `motion_id`, `cur_anim_frame`, `facing_dir`, hitstun `x221C_b6`,
hitlag `x2219_b5`, capture links and `Player_GetStocks`. Whole-fighter protection
comes from `ftColl_8007B868`. `cpu.xFA_b5` is recomputed by vanilla's floor-below
and blast-margin check: it is a veto, not proof of recoverability. Ground
antics additionally require both island-endpoint distances >22, using
`800A2A70` (which returns −1 for missing island/air).

### Implemented personality actions / tuning

- **Contextual taunt:** ego ≥45, recent KO or flashy launch, safe interior,
  stationary neutral/crouch, opponent dead or >90 units away in hitstun. One
  80% roll per safe event; 600-update cooldown. Neutral/up-D-pad/neutral over
  three updates. This starts the real taunt; it does not shorten its animation.
- **Swagger:** ego ≥45, opponent's ordinary grounded attack ≥18 animation
  frames old, facing away, 45–85 units away and within 12 vertically. On the
  first actionable opportunity, 50% roll for two short crouches over 22 updates,
  then vanilla. Forbidden on pass-through platforms (down-flick could drop
  through). Not a frame-data-perfect whiff detector or guaranteed punish.
- **Excessive Falcon Punch:** ego ≥75, opponent knocked down/dazed, facing
  toward them, 18–42 units away and within 12 vertically. Standing Wait/walk
  only: crouch reversal cannot accept neutral-B. One 35% roll per actionable
  opportunity. Neutral/B/neutral; no guaranteed hit and no forced action state.
- **Knee/Stomp preference:** eligible aerial candidates get multiplier
  `1 + 2 × (ego − 45) / 55` above ego 45 (maximum 3×). No boost in danger,
  serious mode, hitlag or without floor below. No grounded down-A boost.
- Whiff/knockdown opportunities are consumed only when an eligible roll occurs,
  not when Falcon is still in his own lag. The condition must end before another
  roll. Other style actions share a 300-update cooldown. Punishment suppresses
  antics and candidate boosts; gaining momentum can rebuild confidence.

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
2 swagger, 3 Punch), age, start/exit/cancellation reasons and throttled eligible
Knee/Stomp weighting messages. These weighting messages do not claim a move
was selected or hit. Logs: `build/showboat/dolphin-user/Logs/dolphin.log`.

The optional HUD (`showboat_hud.c/.h`) shows a shadowed white line such as
`FALCON P2 EGO 62 /100 (VANILLA) SERIOUS 120f` near the upper left. EGO is
confidence, not fighter damage; SERIOUS is remaining custom-behavior suppression
in CPU updates (normally 60/second). The action label is **input ownership**, not
the animation: a three-frame input can start a much longer taunt/Punch.

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

1. **Baseline:** fight normally for a minute. Falcon should retain ordinary
   movement, attacks, defense, ledge options and recovery.
2. **Build ego:** let Falcon land hits without hitting him back for a while.
   At ego >45, eligible aerial Knee/Stomp weights increase, not all attacks.
3. **KO:** let him take a stock while safely grounded away from the edge, with
   no recent damage. Look for a TAUNT start and normal full taunt animation.
   A roll can fail; do not expect every KO to taunt, especially while serious.
4. **Swagger:** with ego ≥45, commit an attack facing away about 45–85 game
   units from grounded stationary Falcon. Two quick crouches may occur. Try
   again after the shared cooldown, not by holding the identical opportunity.
5. **Punch:** at ego ≥75, suffer knockdown/daze in front of him, roughly 18–42
   units away. Occasionally he should attempt a real, punishable Falcon Punch.
6. **Punish:** hit him during/right after an antic. Expect extra ego loss,
   cancelled input ownership and several seconds without custom antics.
7. **Safety:** launch him offstage, approach during swagger, grab him, and
   play on Battlefield platforms. No custom downward flick on pass platforms,
   no custom input during recovery/defense/grab priorities, no permanent wedge.
8. **Isolation:** repeat with level 8 Falcon, level 9 Fox, human Falcon,
   three-player FFA, and live Ice Climbers opponent. No mod-owned behavior/HUD.
9. **Lifecycle:** restart matches and switch CPU settings/control. Initial ego
   starts fresh; ordinary stock loss lowers it instead of refreshing it.

For quick observation, a several-stock match where you initially leave Falcon
unhit is more revealing than exchanging hits constantly. The prototype is
intentionally conservative after punishment. Do not confuse original CPU
taunts or Punches with custom triggers: use the HUD/logs.

## Remaining limitations / reverse-engineering questions

- Match outcome is not attributed to exact hit sources: hazards/items and
  self-destructs may count as success. Death-animation and confirmed stock
  accounting use a 240-update dedup window; very fast successive KOs can merge.
- Whiffs use motion/range/facing, not hitbox activation or actual remaining lag.
  Punch can miss or be too slow. Those are ordinary game consequences.
- Local connected-floor clearance does not predict moving-stage hazards or
  projectiles. Start testing on standard stages. No intentional offstage style.
- A started taunt/Punch cannot be magically cancelled by input ownership ending.
  Cancellation means vanilla controls resume, not forced escape from animation.
- The candidate data's geometric fields and divisors are followed as implemented;
  not every script, mode, target-cache flag or special-stage case is decoded.
- Normal CPU scripts/priority machinery still run; low-confidence Falcon is not
  stronger than vanilla. Probabilities and conservative danger rules need human
  tuning across more matches. Third-party cheat codes using fixed executable
  addresses and stock/netplay savestates are not compatible with this shifted DOL.

## Best next improvements

1. Tune ego/safety thresholds from HUD-visible human matches so contextual
   taunts and excessive punishes are noticeable without dominating play.
2. Attribute real hit/KO events, recording which move landed and whether style
   actually connected; replace percent-delta credit approximations.
3. Give whiffs/knockdowns short contextual opportunity windows based on actual
   attack commitment, improving plausible Punch timing without forced hits.
4. Add recoverability-scored edgeguard candidates, still retaining vanilla
   recovery and stock floor checks rather than unconditional offstage dives.
5. Extract character-specific style tables once Falcon's loop feels right.

## Verification evidence

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
