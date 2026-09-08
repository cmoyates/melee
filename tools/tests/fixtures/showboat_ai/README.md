# Showboat host fixtures — not an emulator test

Run from the repository root:

```sh
python3 -m unittest discover -s tools/tests -p 'test_showboat_ai.py' -v
# A subset:
python3 tools/tests/test_showboat_ai.py -k attack_weight -v
```

Only Python's standard library and clang are needed. `SHOWBOAT_TEST_CC` can name
another clang executable. Each case runs in a fresh process in both debug modes,
with ASan/UBSan. Compilation, generated includes, and executables live in a
`TemporaryDirectory` that is cleaned up even after failure. No configure step,
assets, emulator, production edits, or target build are involved.

## What is real and what is stubbed

- `harness.c` includes **the actual `src/melee/mod/showboat_ai.c`**, including its
  actual public header, static `SB_State`, RNG, action selection, and helpers.
- The runner extracts native fighter-kind, motion-state, CPU-command, and stage
  enums from current headers. It does not invent enum ordering or copy AI logic.
  HUD is explicitly disabled; this suite does not own or exercise HUD tests.
- `game.h` defines a deliberately small **non-ABI-compatible** Fighter layout.
  Player, collision, ground-edge, team, CPU-control, and match-mode queries read
  explicit fixture data. Signed floor endpoints, floor IDs, stage kind, global
  item presence, death counter, mandatory rebirth duration (`x5D0`), and shield-
  break `grab_timer` are explicit inputs. They do not infer game behavior.
- All five `ShowboatCombat` APIs are explicit spies, using the real combat header:
  ResetSlot, RestoreInput, Update, PostInput, GetAction. The real combat module is
  **not linked**. Update can decline or supply a distinctive tiny B script; it
  does not reproduce combat policy. A borrowed-stick fixture and call trace test
  restoration before early gates/reset/taunt, serious-mode-independent delegation,
  flourish handoff without clearing the new combat script, and PostInput gating.
  GetAction must remain unused with HUD disabled. Combat behavior needs its own
  tests; a spy returning true during danger proves delegation, not safe combat.
- Script writers follow the corresponding subset of `ftcmdscript.c`: clear all
  controls and reset buffer; append command/argument; append Done and schedule.
  A separate tiny interpreter handles only Done, PressUp, PressB, SetLstickX/Y.
  Unknown opcodes fail loudly. Done intentionally leaves held input untouched.
- Successful updates must produce at most five script bytes. Cancellation is
  checked **before** interpreting anything, including both sticks, both triggers,
  buttons, pending script, and vanilla attack-selection cache invalidation.
- Every update snapshots all exposed Fighter fields and all fixture player/query
  data. Only the actor's CPU script/input fields and `cpu.xA4` attack-selection
  cache may change. Command weighting must leave all Fighters and archive-table
  bytes unchanged and must not consume personality RNG.

Coverage retains configuration/singles/partner exclusions, identity/reset/suspend
lifecycle, stock/death deduplication (including delayed/reversed observation order),
stale-input cancellation, deterministic private RNG, and archive-table guards.
V2-specific cases cover:

- Base ego 55, 90-update advantage +4, fractional damage rounding, -15 stock loss
  with 120 serious updates, 90-update damage caution, and -4 physical-danger entry
  without an initial-spawn or blanket high-percent penalty.
- Certified taunts: actual death states 0–10, positive death counter plus mandatory
  rebirth budget >=80, stock mode/live rival stocks, FD/BF main floor/no items,
  separate 180-update cooldown, no RNG roll, and safe high-percent/low-ego/serious
  override. Running winners can settle with bounded neutral input, only proceeding
  after a real free-stance observation. Late death, Rebirth/RebirthWait, unsafe
  court, failure to settle and pre-press budget expiry veto.
- Three-update taunt/punch scripts with explicit native-state acknowledgment and
  cancellation when the press is not acknowledged; unchanged 22-update swagger
  pulses. Swagger starts only in idle/far-whiff (>=70) contexts without an active
  vanilla script; Punch requires Furafura with grab_timer >300, not knockdown.
- DANCE state 4: neutral first update, world-direction sticks, actual Dash frame
  >5/facing confirmation before reversals, delayed initial opposite flick during
  early unturnable Dash, Turn handling, two-turn termination,
  and a hard 24-update bound even without animation progression. Signed floor
  bounds enforce strict >40 starting / >30 active clearance, 24 displacement,
  next-leg runway, no items/platforms, and floor identity. Native priorities and
  real punish opportunities cancel; priority yields preserve fresh `xA4`.
- Selective mercy only at the huge-lead central FD/BF hitstun opportunity: eligible
  air script 6 gets 4x and script 8 gets .35x. Guard failures retain normal Knee/
  Stomp style weighting; common safety vetoes still win, zero stays zero, and
  indicator bookkeeping expires/resets without physical or table writes.

The whiff helper intentionally selects a non-FD/BF stage to isolate crouch
swagger from dance. Death counters and native motion frames never advance
implicitly in a stub; each relevant transition is supplied by the test.

Native animation progression is supplied explicitly between frames; an emitted
B or D-pad-Up is not evidence that the game actually executed a punch or taunt.
These tests do not validate build opt-in wiring, native collision or frame timing,
PPC layouts, stock/arbitration ordering, or gameplay in Dolphin/hardware.

## Extending and interpreting failures

Add `test_name()` in `harness.c` and `CASE(name)` in the registry. Python discovers
those entries automatically. Extend `game.h`, query stubs, or the VM explicitly
when the production module gains dependencies; missing APIs remain compile
errors rather than permissive no-ops. Helpers that seed ego/action state isolate
specific branches; contextual tests also enter actions through real Update events.

Regressions remain ordinary failing tests, not silent expected-failure skips.
`spawn_before_stock_charged_once` is explicitly a robustness probe: it supplies
spawn change before stock accounting. Whether that ordering can occur natively
must be checked separately; the normal stock-before-spawn path and a delayed
spawn are tested independently.
