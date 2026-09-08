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
V1 additionally requires **exactly one other instantiated player**, not an ally.
Teams/free-for-alls, training orders, human Falcon, other levels and characters
keep vanilla behavior. Existing C-stick changes on the base branch remain.

Hooks (all behind `SHOWBOAT_AI`):

1. `ftCo_800B3900`: after vanilla mode/priority arbitration, call
   `ShowboatAI_Update`. If false, call the unchanged script builder. Always run
   the original interpreter and partner postprocessing. A cancelled or completed
   style clears its script/inputs and resumes vanilla dispatch on this update.
2. `ftCo_800B4AB0`: adjust only weights in the **local eligible-candidate copy**
   before summation. All range/level/modulo/allowlist/denylist filters, selection
   RNG calls and shared archive data remain unchanged.
3. `Player_InitOrResetPlayer`: clear that slot's sidecar, preventing cross-match
   pointer reuse. Updates also check owner and `x8_spawnNum`; respawning clears
   antics and penalizes ego instead of restoring initial confidence.

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
  rising opportunity, 50% roll for two short crouches over 22 updates, then
  vanilla. Not a frame-data-perfect whiff detector or guaranteed punish.
- **Excessive Falcon Punch:** ego ≥75, opponent knocked down/dazed, facing
  toward them, 18–42 units away and within 12 vertically. 35% opportunity-edge
  roll. Neutral/B/neutral; no guaranteed hit and no forced action state.
- **Knee/Stomp preference:** eligible aerial candidates get multiplier
  `1 + 2 × (ego − 45) / 55` above ego 45 (maximum 3×). No boost in danger,
  serious mode, hitlag or without floor below. No grounded down-A boost.
- Other style actions share a 300-update cooldown. Punishment suppresses
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
`--showboat-ai` (explicit opt-in), `--showboat-ai-debug` (event OSReport logs).
Without these flags, all hooks compile out and the new object is not linked.
The helper enables both and builds only the modified DOL, not retail hash
verification. `tools/project.py` adds an explicit optional extra-DOL-unit list;
retail split addresses and symbol metadata are unchanged. Stock and C-stick
build directories are not overwritten.

The DOL grows beyond the stock disc allocation (only 32 spare bytes). Do not
use the fixed-allocation C-stick packager. The launch helper mounts the original
disc via Dolphin DefaultISO and boots the new executable with a separate user
profile. No source assets, original executable or normal save are overwritten.
Configure a controller in this isolated profile before manual testing.

Debug prints include ego deltas/reasons, input action IDs (0 vanilla, 1 taunt,
2 swagger, 3 Punch), age, start/exit/cancellation reasons and throttled eligible
Knee/Stomp weighting messages. These weighting messages do not claim a move
was selected or hit. Logs: `build/showboat/dolphin-user/Logs/dolphin.log`.

Build/runtime evidence and final test results are recorded below when verified.

