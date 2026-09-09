# Precision-defense actual-C fixtures

Run `python3 tools/tests/test_showboat_defense.py -v`.

24 cases run with debug 0 and 1 under ASan/UBSan. The production module is
compiled as its own unmodified C translation unit. Native enums, pad masks,
input preprocessing, VM, relevant defense builders/body forecast and fighter
shield-contact functions are extracted from this checkout. Typed engine query,
geometry/effect stubs are explicit; unsupported calls are not silent successes.

Coverage:

- Fresh empty defense-7 acquisition, released sampled/raw shoulders, grounded
  common normals, initialized blockable capsules, native threat identity,
  shield health, floor/runway and live-singles guards.
- Actual script PressR/WaitFor/ReleaseR processing; bounded hold and abandoned
  release tail; no retapping when the raw or sampled hold is lost.
- Native defense handoff retains held R on priority 7 until native processing
  decides release/roll/block; changed priorities and replacements survive.
- Every exposed Fighter byte is compared across mod operations, permitting
  only owned CPU script/controller fields—not physical state, shield resources,
  game timers, priorities, cached decisions or opponent changes.
- GuardReflect is only an attempt. Extracted fighter-contact code produces the
  persistent cancel/minimum-hold evidence. Contact is recognized even if the
  short window flag expired before observation, and credited at most once.
- Ordinary blocks, bare/stale window flags, items, replacement VM/identity,
  configuration loss and reset do not fabricate powershield events.
- Same-pointer/new-spawn cleanup happens before forgetting. A pending PressR
  or completed ReleaseR does not own a later native R. No stale pointer is
  dereferenced. Raw ResetSlot alone retains the documented bounded-tail policy.
- PERFECT display is limited to 30 module updates/the current guard family.
  A new attempt discards unconsumed old credit. Successful contact has no extra
  retry timer, but a real released sample/actionable stance remains mandatory;
  failed attempts retain the 12-update retry. No shield pumping is introduced.

These tests do not simulate fighter physics, collision scheduling or complete
native action transitions. The native three-frame body forecast is not a shield
contact oracle; direct fixture motion/contact observations are not in-game
successes. Gameplay frequency, useful blocking, shield breaks and strength need
an explicitly approved Dolphin playtest. Main-AI delegation/rewards have separate
spies in `showboat_ai/`, not a second imitation of this policy.
