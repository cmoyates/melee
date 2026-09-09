# First platform-safeguard live review (fifth recorded playtest)

## Provenance and integrity

The tester explicitly approved launch and shutdown. Dolphin exited0 and remains
closed. Capture: `20260909T233801.009817Z-d81a4dff4f9c4760a39b3ac8be45e045`.

- Clean launch source: `7f6ee7c6e5f1243c8fe8ab17b0776b447807dcdb`.
- DOL:4,522,912 bytes, SHA-1 `7384b2f1dadc18b996e324a4c3add40221963290`.
- Controller: `00dc2b7a5339493fe11fcf93e3adba16e93e0451`, unchanged.
- Start/end UTC:2026-09-09T23:38:01.010264Z /23:40:56.122952Z.
- Runtime log:1,024,974 bytes, SHA-256
  `16adadec74e88c188fa41cabc120193ae289d559397d097929e21fea30951c75`.
- **2,686 accepted v2 records, zero rejected**:1,671 samples,1,007 gates,
  four begin/end pairs. Stable internal Falcon2/Kirby4 and valid float/flag
  fields. The old serialization defect did not recur.

Battlefield, normal Versus Time. Segment boundaries are0–3553,3554–5442,
5443–6775 and6776–7200; reported updates3677/1889/1333/425 sum to7,324 per
recorded tactic. Each segment's five gate totals agree with its end observation
count. The first two splits follow Kirby's respawns, the third Falcon's.
These are recording lifecycles, not four matches or an official result; stock
fields stay3 in Time.

Coverage still has the initial gap, unlocated repeated-clock observations and
unsampled tails. Original `report.json`/`report.md`, raw log and manifests are
preserved locally. Original reports contain520 Kirby-specific numeric-label
fallback warnings, not corrupt fighter fields. The post-review analyzer adds
native Kirby labels; separate `named-report.json`/`named-report.md` remove all
520 numeric-name warnings while preserving the original analysis. Scan totals
and integrity status are unchanged; remaining warnings concern coverage.
Neither additional names nor completion metadata certify gameplay outcomes.

## Three real vetoes, including a platform admission

Each event128 has an independent direction diagnostic, native[9,0,0], self
Wait/grounded, action0/owns0 and neutral post-filter output:

| Frame | Surface / direction | Self x,y | Self percent | Nominal forward runway |
|---:|---|---|---:|---:|
| 94 | Main floor / left | -17.5153,≈0 | 0 | 50.885 |
| 4323 | **Left platform / right (inward)** | -38.6301,27.2001 | 84.5 | 18.630 |
| 5058 | Main floor / left | -60.5649,≈0 | 102.5 | 7.835 |

All are below the65.17 forward requirement. The platform case confirms actual
admission on one supported platform, **including the intentional sacrifice of
an inward side-B**. It does not demonstrate an outward departure prevented,
all three platforms, or a counterfactual stock saved. Recorded position and
known geometry establish the surface context; exact support IDs are not in the
snapshot. Independent read-only review corroborated all three episodes.

### f94: preserved wait and an unproductive, locally safe up-B

Jump output150 → KneeBend151 → JumpF154 → B+up170 → SpecialAirHi171 →
LandingFallSpecial234 on the top platform → Wait263. Falcon remains0%, Kirby12%
through this tail. The move lands, but does not produce a recorded damage gain;
it spends substantial time without pressure. Do not call it a useful combo merely
because the guard prevented the side-B from starting.

### f4323: platform veto works, but the retained tail gets punished

A native forward throw precedes this pulse (ThrowF4277); it is not correct to
label every observed priority9 side-B a completed down-throw sequence.
Jump output4379 → KneeBend4380 → JumpF4383 → B+up4399 → SpecialAirHi4400 →
FallSpecial4463 → LandingFallSpecial4484 back on the left platform.

At **4501**, while still in the landing-lag sequence, Falcon changes from84.5%
to102.5% and DamageFlyN. Kirby is in **SpecialAirLw (Stone)**. Thus this episode
is not an unqualified safety/strength success: the initial side-B is suppressed
and Falcon lands, but the preserved up-B tail exposes him to a damage event.
The counterfactual without the veto is unknown. No forced landing-lag shortening,
late motion cancellation or invented recovery correction is justified.

### f5058: this retained up-B actually captures the opponent

Jump output5114 → KneeBend5115 → JumpF5118 → B+up5134 → SpecialAirHi5135 →
**SpecialHiCatch5147**, paired with Kirby's **CaptureCaptain** → native throw5165
→ ordinary Landing5230 on the left platform. Rival percent rises81.81→86.81
at5148 and→97.73 at5166; Falcon remains102.5% through landing. A real native
capture state is stronger evidence than a merely queued attack. It still does
not establish an official hit/damage counter or justify suppressing every up-B
follow-up indiscriminately.

All three jump pulses occur exactly56 native frames after the veto, consistent
with the retained release/55-update wait. Inputs and timing are observed; VM
cursor contents are not recorded. The tail is variable in usefulness, not
universally broken or universally successful.

## Other native commitments and the actual self-death

Five ground side-B starts remain, all priority2:
requests1024(right),1562(left),2314(left),3037(right),6071(right). Two airborne
starts also occur. No sampled eligible priority9 ground side-B bypass or
unvetoed platform-origin ground startup appears.

The conservative envelope would also reject some **out-of-scope priority2**
requests:1024 and3037 have insufficient backward reserve,2314 insufficient
forward reserve. Nevertheless those actual attempts return to grounded Wait at
1078/3097/2366. Failing the conservative bound is not proof of inevitable floor
loss and does not justify a blanket priority expansion from this run.

The later native Knee at6158 follows a priority2 side-B, not a veto tail. It
lands on the top platform at6181 with self/rival percent unchanged110.5/19
through the Knee interval. No custom aerial acknowledgment occurs.

The sole sampled self-death follows a different mistake:

- Kirby is **433 = ftKb_MS_CaSpecialN**, copied Falcon Punch.
- Falcon exits rapid jab at6523; Wait6532, then walks toward the charging move.
- At6551 native priority2 produces the dash-grab input; CatchDash begins6552.
- **6557:** DamageFlyLw, percent110.5→137.5, with both-fighter hitlag at Kirby's
  Punch animation frame53.
- **6601:** DeadUpStar at(124.817,201.163); Rebirth6776, new self spawn/zero percent.

This is strong contact-consistent evidence of a late dash-grab into copied Punch,
not another ground side-B→helpless→bottom-death sequence. Explicit hit-source IDs
and official KO/SD/winner attribution remain absent. The native motion name is
source-derived, not inferred merely from the amount of damage.

## Custom behavior and limits

- One custom grab: neutral5008, Z5009, Catch acknowledgment/event4 at5010.
  Actual CatchPull/CapturePulledLw occurs5016, followed by native ThrowLw5018.
  Custom ownership was already released; later native inputs are not additional
  custom starts. The subsequent f5058 veto belongs to this ongoing native chain.
- Nine L-cancel input samples:472,1287,2643,4091,4259,4596,5954,6178,6385.
  Samples are not nine independently verified lag reductions.
- No custom aerial, wavedash, powershield contact, Punch, dance or certified
  taunt starts. Native crouching/dropping/specials are not custom personality.
- Sampled ego55–100 overall (later life61–92); high ego does not override the
  main-floor/runway/action safety gates. No personality improvement is claimed.
- Sampled net percent increases: Falcon152.5, Kirby≈323.96 over1,666 comparable
  pairs. These are unattributed deltas, not score-screen damage or hit counts.

Gate totals, each7,324 updates (not unique time or opportunities):

| Tactic | Recorded reasons |
|---|---|
| Personality | unevaluated2, no_candidate1820, native_priority379, physical/state1311, geometry/window2951, ego/caution861 |
| Combat | active1, started1, input/script356, physical/state2033, geometry/window4932, completed1 |
| Movement | unevaluated2, physical/state6829, geometry/window493 |
| Defense | unevaluated2, native_priority7219, grouped input/script101, target2 |
| L-cancel | started9, physical/state7066, geometry/window204, cooldown45 |

Defense's98.6% native-priority count is a fraction of **all updates**, not a
missed-block rate. No defense geometry/start bin was reached. The current fresh7,
ordinary-melee defense policy did not admit the copied-Punch episode; changing
its collision timing alone would not address this trace.

## Bounded next-defense research

Read-only native/asset research identifies copied ground/air Punch as433/434.
`PlKb.dat` submotion368's script at file0x627C has AsyncTimer52 at0x62C4,
then hitbox creation and five script frames before clearing: conventional
frame53 onset, not a guessed43-frame window. `cur_anim_frame` is not elapsed
capture time, especially across hitlag. Native callbacks in
`ftkirbyspecialcaptain.c` have empty IASA, and ground/air transitions preserve
animation/command progress rather than restart the windup.

At6532 Falcon has a free Wait opportunity with Kirby at animation29 and about
32.23 units away. By CatchDash6552 he has committed; a brief native priority1
at6553 does not make that animation actionable or confer VM ownership. The
current custom defense requires fresh7/empty VM, Wait/Walk, a common grounded
normal attack and initialized capsules. Kirby433 fails that explicit scope.
The native initialized-hitbox scanner does not predict this earlier windup;
merely widening the rival-motion whitelist would not fix the approach error.

A bounded future policy should research early slow-special recognition, reaction
and facing/range/closing-speed bounds, safe spacing or ordinary shield, and a
fresh neutral/before-builder ownership contract. A ten-update shield begun at
animation29 could expire before timer52; timing and duration need revalidation.
Do not erase a live native attack/cache or force a late cancel. Relevant code:
`showboat_defense.c`, native threat scanning in `ftcpuattack.c`, CPU
VM/arbitration in `ftCo_0A01.c`, and Kirby's motion table
in `ftkirby.c`. These are research directions, not new gameplay claims.

## Decision after review

Keep the now-live-tested gameplay binary unchanged. Add bounded offline Kirby
motion labels, preserving numeric fallbacks, kind isolation and v1 quarantine;
this directly removes an interpretation obstacle that hid Stone and copied
Falcon Punch behind numeric IDs. New reports are separate from previous reports.

Next gameplay work should investigate context-sensitive continuation after a
veto and earlier responses to telegraphed specials. The observed up-B capture
argues against blanket tail suppression. A defense expansion requires explicit
reaction/range/hitbox and native-VM ownership analysis; merely bypassing fresh7
or special-motion exclusions is not a safe implementation. Bounded executed-
branch diagnostics would help separate those admissions without rerunning
planners or RNG. No unvalidated balance tuning, rebuild or restart follows this
review; another launch requires fresh readiness.

## Post-review verification

**461 tests pass** in92.965s:242 retained/main,43 safety,56 recorder,
101 analyzer,16 capture,3 config/verifier. Nine new analyzer cases cover native
Kirby IDs/kind isolation, common precedence, missing/malformed/oversized-header
fallback, bounded parsing, v1 quarantine and label-based recovery context. All
452 preceding tests remain, including12,122 full-Fighter safety guards. The
203 native Kirby states are named; only eight actual Kirby up-B phases match
the existing recovery-name heuristic, not copied neutral moves or rollout.

The native verifier passes against the unchanged live DOL; build/staged DOL and
controller hashes remain as above. Runtime raw SHA-256, original reports and
all prior captures are preserved. Logs: `build/showboat-playtest-5-tests.log`
and `build/showboat-playtest-5-verify.log`. No new emulator run or gameplay build.
