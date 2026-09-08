# Combat host tests

Run either:

```sh
python3 tools/tests/test_showboat_combat.py -v
python3 -m unittest discover -s tools/tests -p 'test_showboat_combat.py' -v
```

Requires clang (or `SHOWBOAT_TEST_CC`), but no assets, configure step, target SDK,
network access, or third-party Python packages. Every registered C case runs in
both `SHOWBOAT_AI_DEBUG=0` and `1`, with ASan and UBSan failures fatal.

## What is real / what is mocked

- `harness.c` includes **actual, unmodified** `src/melee/mod/showboat_combat.c` and
  its actual public header. No copied decision helpers or visibility rewrites.
- The runner builds temporary include stubs, following
  `../../test_showboat_ai.py` and `../showboat_ai/`. Motion, fighter, stage and CPU
  command enum declarations are extracted from current native headers, not
  invented numeric motion/opcode IDs. Public HUD IDs 0/5/6/7 are deliberately
  asserted as the API contract.
- `game.h` is a small **host-only** dependency surface, not the full PPC ABI.
  Adding an engine dependency requires an explicit declaration and mock;
  unknown APIs fail compilation/linking. No generic neutral-return fallback.
- The script writer/interpreter subset follows `ftcmdscript.c`: initial duration
  decrement, one sampled `WaitFor`, persistent buttons/sticks, explicit release
  tail, and `Done` without implicit neutralization. Unsupported opcodes fail
  both on emission and interpretation. It never advances motion or animation.
- Queries explicitly model CPU identity, trigger normalization, animation end,
  protection status, stage kind, floor intersections and floor endpoints.
  `mpCheckFloor` intersects supplied segments with a configured flat floor;
  it does **not** return a preselected ETA. It records segments and filters and
  checks collision outputs are temporary, not fighter/world storage.
- Every public API invocation and VM tick snapshots every fixture fighter,
  GObj, query-answer world and common-data/rules byte. Only the current actor's
  CPU inputs, bounded script/cursors/duration, and cached `xA4` are allowed to
  differ. CPU priority/configuration, all targets/other slots, input history,
  LR/tech counters, command variables, damage, animation, position, velocities,
  collision and rules are protected. LC additionally compares the entire CPU
  object except the borrowed left-trigger channel.

## Coverage

| Area | Assertions |
| --- | --- |
| Reactive grab | Neutral then single Z, synchronous ack/capture release, native release tail, failed pulse/cooldown, native priority 9 and replacement script/cached-attack preservation |
| Grab gates | Eligibility/protection, facing, current and predicted distance, floor/height/speed boundaries, guard allowlist, compatible damage union/hitstun, actual remaining landing animation/rate, second-sample recheck |
| Identity | Null/invalid slot/target, slot reset, target/owner/spawn reuse, no writes to former owners or other fighters |
| Analog LC | All aerial motions + command variable, descending-only, ECB rather than root, ETA 1–3 including endpoints, existing LR window, held defense/deadzone, hitlag/hitstun vetoes, terminal speed and positive/negative fastfall/fallthrough |
| LC ownership | Analog 128 only, no digital airdodge/tech or DI-stick changes, native priority/cache preserved, existing tech counters unchanged, idempotent RestoreInput before/after eligibility changes, native replacement channel preserved, no second restore, retry budget |
| Direct air | Knee/up-air IDs, mirrored facing, one A/stick pulse then release/ack, failed/missing sample and cooldown, no artificial cooldown after accepted motion, free-air/jump-physics flag allowlist, no forced jumps/motion changes |
| Interception | Future versus current range, startup/hitstun reserve, protected/unavailable targets, conservative native drift/KB, final reserve frame before landing, floor/runway/stage/sanity vetoes, inclusive intercept boxes, Knee-to-up-air recheck downgrade (not upgrade), target changes/replacement script priority |

A separate development check used six temporary negative controls to verify
rejection of forbidden state writes, unsupported opcodes and unknown engine APIs.
Those injections are not part of the ordinary registered suite; production
source on disk was not edited by them.

## Limits

These are **not emulator or frame-accuracy tests**. Flat floors and synthetic
fighter observations do not prove actual animation timing, collision remapping,
platform topology, hurtbox/hitbox overlap, Knee sweetspots, input sampling order,
stock arbitration, engine integration, build wiring, or PPC layouts. Test code
supplies observed motion/position/hitstun changes explicitly; script age never
stands in for the game transitioning a fighter. Snapshot guards verify exposed
host state, not every byte of the real engine or transient writes later undone.
