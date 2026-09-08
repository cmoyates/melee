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
- The runner extracts native fighter-kind, motion-state, and CPU-command enums
  from current headers. It does not invent enum ordering or copy the AI logic.
- `game.h` defines a deliberately small **non-ABI-compatible** Fighter layout.
  Player, collision, ground-edge, team, CPU-control, and match-mode queries read
  explicit fixture data. They do not infer game behavior.
- Script writers follow the corresponding subset of `ftcmdscript.c`: clear all
  controls and reset buffer; append command/argument; append Done and schedule.
  A separate tiny interpreter handles only Done, PressUp, PressB, SetLstickY.
  Unknown opcodes fail loudly. Done intentionally leaves held input untouched.
- Successful updates must produce at most five script bytes. Cancellation is
  checked **before** interpreting anything, including both sticks, both triggers,
  buttons, pending script, and vanilla attack-selection cache invalidation.
- Every update snapshots all exposed Fighter fields and all fixture player/query
  data. Only the actor's CPU script/input fields and `cpu.xA4` attack-selection
  cache may change. Command weighting must leave all Fighters and archive-table
  bytes unchanged and must not consume personality RNG.

Coverage includes configuration opt-in exclusions, singles/partner exclusions,
identity/reset/suspend lifecycle, damage and advantage ego accounting, stock/death
deduplication, deterministic rolls, contextual taunt and punch three-frame scripts,
22-frame swagger pulses, cooldown/failed-roll spam prevention, platform/crouch
vetoes, forced-state cancellation, fallback, and air-command weight/table guards.

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
