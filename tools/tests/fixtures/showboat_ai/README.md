# Showboat host fixtures — not an emulator test

Run from the repository root:

```sh
python3 -m unittest discover -s tools/tests -p 'test_showboat_ai.py' -v
# A subset:
python3 tools/tests/test_showboat_ai.py -k attack_weight -v
```

Only Python's standard library and clang are needed. `SHOWBOAT_TEST_CC` can name
another clang executable. Each case runs in a fresh process in all four modes:
`SHOWBOAT_RECORDER=0/1` × `SHOWBOAT_AI_DEBUG=0/1`, with ASan/UBSan. Compilation, generated includes, and executables live in a
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
  Update's GetAction must remain unused when **both HUD and recording are disabled**;
  PostInput now legitimately queries it in every mode to exclude custom actions
  from safety. The Update guard checks its per-call delta, not a cumulative zero.
  Its default remains 5, with explicit configurable results for action-precedence
  and safety tests. Combat behavior
  needs its own tests; a spy returning true during danger proves delegation, not safe combat.
- Four `ShowboatMovement` APIs are explicit orchestration spies using its real
  header. They verify reset/suspend ordering, ego-independent starts after combat
  declines, active movement precedence, no duplicate restart on a cancellation
  update, and preservation of the new movement script when a flourish yields.
  The actual wavedash sequence/geometry has a separate module suite; these spies
  do not simulate jump or landing physics.
- Five `ShowboatDefense` APIs are explicit orchestration spies using the real
  header: ResetSlot, Suspend, Update, GetAction (0/10/11), and TakePerfect. They
  default to declining without input writes or rewards. Per-slot owner/action/
  pending state and independent counters leave existing combat/movement event
  traces unchanged. A distinctive `SetLstickY 47; Done` VM identifies ownership;
  it does **not** emulate R, shield timing, collisions, or native defense7.
  Tests inject a verified-contact event explicitly, separately from an attempt
  or a PERFECT indicator. The actual defense module is **not linked** here and
  has its own C suite for contact evidence, release and identity policy.
- All seven `ShowboatRecorder` APIs are explicit, read-only argument/snapshot spies
  in `recording_spies.c`, using the stable real header. Definitions are guarded by
  `#if SHOWBOAT_RECORDER` (disabled APIs are argument-erasing macros). The actual
  recorder implementation is **not linked**; its separate module suite owns
  sampling, schema/segments, flushing, bounds and identity validation. Spies hold
  only per-slot last arguments, counters, CPU snapshots and an opt-in **128-entry**
  trace, independent of legacy `EV_*` events. Setup clears recorder bookkeeping
  after its own ResetSlot calls; focused tests restart the trace between steps.
  Saved owners are comparison tokens, never dereferenced. No recorder spy writes
  game data or reproduces personality/technical policy.
- Script writers follow the corresponding subset of `ftcmdscript.c`: clear all
  controls and reset buffer; append command/argument; append Done and schedule.
  A separate tiny interpreter handles only Done, PressUp, PressB, SetLstickX/Y.
  Unknown opcodes fail loudly. Done intentionally leaves held input untouched.
- Successful updates must produce at most five script bytes. Owned-VM cancellation
  is checked **before** interpreting anything, including both sticks, both triggers,
  buttons and pending script. Fresh vanilla `xA4` selections are always preserved.
  Replacement native VMs must retain their **entire CPU snapshot** instead of being
  blindly neutralized. The old cancellation cases now dirty held channels without
  replacing the owned bytecode; replacement cases test the distinct preservation
  contract. No physical-write masks or original case registrations were removed.
- Every update snapshots all exposed Fighter fields and all fixture player/query
  data. Only the actor's CPU script/input fields and `cpu.xA4` attack-selection
  cache may change. Command weighting must leave all Fighters and archive-table
  bytes unchanged and must not consume personality RNG.

Recorder orchestration (`recording_cases.c`) adds **14 C cases** covering:

- Combat borrowed-input restoration before Begin; Begin before arbitration reasons,
  Decision after arbitration (including verified-contact ego reward), native VM
  consumption before CombatPostInput, and Frame strictly after CombatPostInput.
  `frame()` still means Update + owned VM only; these cases explicitly call
  `ShowboatAI_PostInput` through a full-Fighter-byte read-only guard.
- Decision ego/action/ownership, personality > combat > movement > defense >
  JUGGLE > none action reporting, and both owned and native-fallback samples.
  Frame captures all buttons, both sticks, both triggers and consumed VM state,
  not the queued Decision snapshot. Extra native channel values are explicit test
  inputs; the combat post-input spy remains read-only in these recorder cases.
  Only new safety ordering cases opt into its distinctive x-stick output marker.
- No Decision/Frame after Update loses eligibility or its singles target; no
  CombatPostInput/Frame when PostInput itself loses eligibility/private ownership.
  **Boundary:** if a target disappears only *after* Update, main forwards NULL to
  Frame; if replaced, it forwards the newly reacquired entity. The real recorder,
  not this main suite, owns rejection/segment closure for those late observations.
- ResetSlot bounds, idempotence and slot isolation; Suspend delegation even on
  invalid/non-owning actors, with private spy-owner isolation; owner/rival
  replacement rebaselines and stale identity tokens without dereferencing them.
  Bookkeeping-only lifecycle scenarios compare every Fighter byte.
- Taunt/Punch events only after observed native acknowledgment, never at queued
  or consumed button presses; absent acknowledgments and fresh native selections
  do not emit events, and successful acknowledgment is not repeated next update.
- Ordered reason arguments (including cancellation followed by a more specific
  reason), last-reason overrides for physical/caution/priority/window/cooldown/
  completion/budget paths, and NOT_EVALUATED after an early technical return.
  Mock technical modules emit no fabricated recorder reasons or success events.

Every new scenario also executes with recording disabled; gameplay assertions and
all original physical-write/input-gating assertions remain active in both modes.
Recorder bookkeeping assertions test main's call contract, not the real recorder's
implementation. No HUD rendering, DOL build, emulator or analyzer is tested here.

Safety orchestration (`safety_cases.c`) adds **7 C cases** covering:

- Native VM -> CombatPostInput -> Safety -> debug log / event -> Frame ordering.
  An explicitly enabled combat x-stick marker distinguishes its output from the
  VM output; the safety spy snapshots that exact input, then optionally clears B
  and x. Event and Frame must see the filtered snapshot, including all untouched
  buttons/sticks/triggers and bytecode/cursors. These marker writes are NOT the
  actual safety policy or proof of recovery safety.
- True returns emit exactly one real-header `SBR_EVENT_SIDEB_VETO == 128`, one
  debug log when enabled, and no ego/RNG/state mutation. False returns preserve
  every input byte and emit no event/log, including after a previous true sample.
  Recorder-off builds still call safety and retain exactly the same raw effects.
  Zero/high ego, serious mode and the informational JUGGLE indicator do not gate it.
- Active taunt/dance/swagger/Punch and both offstage styles, combat IDs 5/6/7,
  movement 9, defense 10 and PERFECT 11 never call safety. Queued and consumed
  custom scripts, dirty held channels and pending defense rewards are preserved.
- Missing/replaced target entities, null live user data, invalid saved target slots,
  stale/null owner tokens and target spawn changes block safety. Frame still
  receives the late live target or NULL; recorder validation is tested elsewhere.
- Late self-spawn/owner/primary-entity replacement and every eligibility gate block
  CombatPostInput, safety and Frame. A later Update can rebind live self/target
  identities and allow safety again; no stale pointer is dereferenced.

`safety_spies.c` uses the real `showboat_safety.h` prototype. It has **no permissive
fallback**: every call consumes an explicitly armed expectation from an eight-entry
bounded array, checking exact actor/target, CPU bytes, combat call count and absence
of an early Frame. Unexpected or missing calls fail (also checked before setup
resets and process success). Legacy cases that legitimately reach safety explicitly
arm false results; all other cases default to forbidding calls. The new output
helper compares every Fighter byte against the exact planned CPU change, all
private AI state, fixture world/objects, and script writer/reward counters. Existing
read-only and physical-write guards remain intact.

`test_showboat_ai.py` exports `create_stub_headers(include: Path)` for host/native
hook verifier reuse. It generates only the typed game dependency tree and native
enums; real mod API headers are never replaced by copied/variadic stub headers.
This suite still includes production main verbatim and does not link real safety,
combat, movement, defense or recorder implementations.

Defense orchestration cases cover:

- Fresh defense only after combat declines and before **new** movement, without
  ego/serious gating. Active movement remains first; cancellation gets one
  movement call before combat/defense. Certified KO taunts still precede fresh
  defense. These are delegation tests, not assertions that a mock attempt is safe.
- Existing action 10 serviced before new combat; both true ownership and false
  native handoff return directly. False handoff cannot restart movement or any
  of the six personality contexts, even at low native priorities 1/10 and with
  an idle VM that would otherwise permit takeover. Action 11 alone neither
  blocks new combat nor awards ego.
- Yielding dance/swagger/Punch/offstage styles forget old ownership without
  clearing or changing **any byte of the newly scheduled defense CPU snapshot**.
- Owned attempts and GuardReflect motion grant no confidence. A pending verified
  event produced during an Update returning false is polled afterward, consumed
  once, and grants exactly +8 ego (including zero-ego and upper-clamp cases).
  Rewards are slot/owner private; stale owner tokens are never dereferenced.
- Eligibility loss, lost singles target, rival slot/entity replacement and
  suspension discard pending events before any reward poll. Reset follows
  Suspend where main reinitializes the slot; self spawn/stock loss uses Suspend
  without requiring a defense Reset. Owner replacement resets bookkeeping without
  suspending/dereferencing a stale owner. Reset bounds, isolation and idempotence
  preserve every Fighter byte. The spy does not reproduce physical release or
  the real defense module's own rival-spawn checks.

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
  override (not within the new 30-update actual-hit/stock-loss safety interval). Running winners can settle with bounded neutral input, only proceeding
  after a real free-stance observation. Late death, Rebirth/RebirthWait, unsafe
  court, failure to settle and pre-press budget expiry veto.
- Three-update taunt/punch scripts with explicit native-state acknowledgment and
  cancellation when the press is not acknowledged; unchanged 22-update far-whiff
  swagger pulses. Far-whiff swagger starts only in idle/>=70 contexts; Punch
  requires Furafura with grab_timer >300, not knockdown. All styles now require
  no cached attack and a verified mundane/idle VM at initial takeover.
- DANCE state 4: neutral first update, world-direction sticks, actual Dash frame
  >5/facing confirmation before reversals, delayed initial opposite flick during
  early unturnable Dash, Turn handling, two-turn termination,
  and a hard 24-update bound even without animation progression. Signed floor
  bounds enforce strict >40 starting / >30 active clearance, 24 displacement,
  next-leg runway, no items/platforms, and floor identity. Native priorities and
  real punish opportunities cancel; all exits preserve fresh `xA4`.
- Frequent neutral dance: ego >=30 (was 40), horizontal gap 55–130 (was 55–115),
  vertical gap <24 (was <20), 90% roll (was 75%), 24-update failed retry (was 45),
  successful start cooldown 48 / 36 at ego >=80 (was 90 / 60). Target must now be
  grounded, without hitstun, knockdown, landing lag or protection; no near-ledge
  airborne recovery can sneak through the neutral branch. Technical combat and
  wavedash remain first, independent of ego.
- Deterministic offstage mockery at **any ego**, including zero and residual
  emotional caution: live airborne rival horizontally beyond the main-floor
  ledge by **strictly >30**, separated by **>=100**. FD/BF main floor only, signed
  self runway >30, self grounded/free of capture/hitlag/hitstun, no held/global
  items or projectiles, bounded observed self velocity, and no damage/hitlag/
  hitstun or stock-loss observation within **30 updates**. A four-update closing
  reserve uses the larger inward self-velocity/observed position delta and must
  still satisfy both gap/ledge margins. Below-stage or offscreen alone is NOT
  sufficient. Far target hitstun/hitlag and return invulnerability do not veto a
  geometrically clear window. Return toward stage/pressure cancels immediately.
- Offstage bouts: normal dance mechanics, max **24 updates**, then **18 updates**
  before another qualified bout; no RNG roll or shared-style cooldown suppression.
  If dance admission cannot accept but a slow grounded free/crouch stance can,
  one short crouch uses **12 updates** (8 down, 4 neutral), the same retry, signed
  runway and floor/displacement checks. RunBrake is not faked into a dash/crouch.
  Full D-pad-Up taunts remain certified-KO-only; no guessed 80-frame recoveries.
- Exact personality script ownership: saved bytes/length and only scheduled-start
  or fully consumed cursors allow cleanup; continuation additionally requires a
  consumed sample, original priority and zero `xA4`. Fresh bytecode, malformed or
  alien cursors, duration changes, selected attacks, and even 1->10 priority
  changes preempt. Never restart personality on that preemption update. A bounded
  remaining-bytecode allowlist admits initial native locomotion, scanning past
  waits to reject queued attacks/jumps/taunts, unknown commands and priority writes.
  Tests cover every style, pending/consumed VM, lifecycle/suspend exits, post-press
  taunt/Punch preemption, same-slot rival replacement and opponent spawn changes.
- Selective mercy only at the huge-lead central FD/BF hitstun opportunity: eligible
  air script 6 gets 4x and script 8 gets .35x. Guard failures retain normal Knee/
  Stomp style weighting; common safety vetoes still win, zero stays zero, and
  indicator bookkeeping expires/resets without physical or table writes.

The whiff helper intentionally selects a non-FD/BF stage to isolate crouch
swagger from dance. Death counters and native motion frames never advance
implicitly in a stub; each relevant transition is supplied by the test.

The baseline **123 cases** (88 earlier cases, 14 defense orchestration cases,
7 final regressions and 14 recorder orchestration cases) are all retained. With
7 safety orchestration cases, the suite runs **130 C cases / 520 recorder × debug
matrix executions** with ASan/UBSan.
Case loops also vary styles, sides, priorities, bytecode/cursor mutations, physical
vetoes, defense handoff/reward states and recorder lifecycle/acknowledgment paths.
Existing physical-write guards and combat/movement/defense gating remain intact.

`ego_regressions.c` additionally covers normal VS Time KO certificates without
stocks, elimination/removal/other-mode/final-stock exclusions, pre-press
revalidation, actual native double-Done locomotion padding, character-local
Zelda/Mewtwo/Sheik teleport guards on admission/continuation, and bounded
Run -> observed RunBrake/Wait settling (12 neutral samples, never a forced dash).
The extra game queries default to Title and are reset between setups. Native
GameMode/MatchKind and the three teleport-character enums are extracted, not
invented numeric constants. All new scenarios retain physical-write guards.

Limitations: no full recovery-time, hitbox, knockback/ground-velocity or future
projectile model. The four-update projection is a conservative current-observation
veto, not proof of safety against teleporting/fast-changing specials. Short inputs
remain interruptible only through retail rules; a started taunt/Punch animation
cannot be cancelled by ending ownership. Byte-identical native replacements with
identical cursors/priority are inherently indistinguishable without an engine VM
generation token. These tiny scripts have no autonomous release tail; update or
suspend clears an exactly owned consumed VM. ResetSlot is bookkeeping-only and
relies on the existing native reset lifecycle. No shield-pulse policy is modeled
here, and the spies do not establish real combat/wavedash/defense integration strength.

Native animation progression is supplied explicitly between frames; an emitted
B or D-pad-Up is not evidence that the game actually executed a punch or taunt.
These tests do not validate build opt-in wiring, native collision or frame timing,
PPC layouts, stock/arbitration ordering, or gameplay in Dolphin/hardware.

## Extending and interpreting failures

Add `test_name()` in `harness.c` or an included case file (`recording_cases.c`
for recorder orchestration) and `CASE(name)` in the `harness.c` registry. Python
discovers those entries automatically. Extend `game.h`, query stubs, or the VM explicitly
when the production module gains dependencies; missing APIs remain compile
errors rather than permissive no-ops. Helpers that seed ego/action state isolate
specific branches; contextual tests also enter actions through real Update events.

Regressions remain ordinary failing tests, not silent expected-failure skips.
`spawn_before_stock_charged_once` is explicitly a robustness probe: it supplies
spawn change before stock accounting. Whether that ordering can occur natively
must be checked separately; the normal stock-before-spawn path and a delayed
spawn are tested independently.
