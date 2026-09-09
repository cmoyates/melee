# First repaired-recorder live review (third recorded playtest)

## Capture and integrity

Tester explicitly approved launch and subsequent shutdown. Dolphin exited 0;
no restart or gameplay tuning followed.

- Capture: `20260909T171817.461429Z-85ac2b55216b4282a22643f59916d482`.
- Launch source: clean `ee3c8bab72da62dc68cd8cd21ff8cf515778c875`.
- DOL: 4,515,936 bytes; SHA-1 `27db34f9111d37f01ebf83be4c78d9233fef06bb`.
- Controller mapping SHA-1: `00dc2b7a5339493fe11fcf93e3adba16e93e0451`.
- Final runtime log: 1,048,398 bytes; SHA-256
  `08e696a69ed898ea4305de472194565b0bdb6a72356064d2b0d29a7f0697a620`.
- 2,760 v2 records accepted, zero rejected: 1,715 samples, 1,041 gates,
  two begin records and two end records. Final launch/completion manifests and
  generated `report.json`/`report.md` remain with the raw local archive.

**The old serialization failure did not reproduce.** All sixteen float positions
have valid finite binary32 encodings; all flags fit the actual eight-bit mask.
Self kind stays 2 (Falcon); rival kind stays 4 (Kirby). There are 73 distinct self
motions and 75 rival motions, not a rival stuck in DeadUpStar. The independently
formatted wavedash diagnostic positions match decoded snapshots to printed
precision. Spawn changes and the observed rival death/respawn are coherent.
This passes this capture's live serialization/integrity checks, not a universal
proof of every future observation or negligible logging overhead.

The analyzer's `partial_or_unreliable` overall label reflects coverage caveats,
not a recurrence of the impossible-field defect: an explicit startup gap,
unsampled segment tails and updates not fully located by sparse samples.
Kirby-specific motions also use numeric fallback names (173 sample warnings);
these are missing labels, not rejected or misdecoded values.

Battlefield (stage 31), normal Versus Time mode, Falcon CPU versus Kirby.
Segments 0–3186 and 3187–7200 report 3,310 and 4,014 updates respectively;
all five tactic histograms agree with each end count, totaling 7,324 each.
These are two recording intervals separated by rival respawn, not two matches.
Repeated startup-clock updates are not extra game duration. Stock fields remain
3 in this Time encounter; unchanged stock values alone are not corruption and
are not a KO/result counter. Neither recorder nor metadata records the winner.

## Personality and controller-only technique

Legacy branch messages independently corroborate these custom events:

| Observation | Evidence |
|---|---|
| Two grab-motion acknowledgments | Events 4 at f380 and f3606; both Catch. Not two proven connected grabs. |
| Four L-cancel input samples | Events 64 at f1865, f2083, f5903, f6658. Not a measured four-success landing-lag rate. |
| One wavedash landing acknowledgment | Event 16 at f2372, LandingFallSpecial. Actual neutral/X/KneeBend/Jump/L sequence also recorded. |
| One certified KO-taunt acknowledgment | Event 1 at f3146, AppealSL, with Kirby in DeadLeft. |
| No custom aerial-intercept, Punch or powershield-contact event | No corresponding custom start/contact diagnostics. Native attacks/shields still operate. |

Three dances started: a neutral dance completed after 16 updates; two offstage
mockery dances yielded for insufficient next-leg runway after six and five
updates. The fourth personality start was the acknowledged KO taunt. No crouch
mockery start in this capture. Sampled ego spans 26–100, ending at 50.

### Actual wavedash displacement, not just input acknowledgment

The neutral dance ends at f2363. A new forward wavedash begins at f2366 with
Falcon x=-9.07 and Kirby x=55.98. Existing leftward momentum carries Falcon to
x=-14.10 at f2371 before the legal down-right L sample. The next sample is
LandingFallSpecial at x=-11.82; sampled Wait at f2381 is x=1.49. Thus this attempt
has about **10.6 units net rightward displacement** from start to sampled Wait,
with recorded percent unchanged at 47.8. Kirby jumps during the slide. This is
useful evidence of actual displacement, not proof that wavedashing beat running
or created a punish. No physics or landing-lag change is inferred.

### Taunt settles and runs through the real animation

At f3144 Falcon is WalkMiddle; f3145 is observed Wait with the Up input; f3146
is AppealSL. The mod releases ownership at f3147 but the native animation
continues. It is still AppealSL at f3199 and returns to Wait at f3205. Kirby is
DeadLeft, then Rebirth from f3187; Falcon's recorded percent stays 73.7 throughout.
This supports a safely completed full taunt in this instance, not merely an
input pulse. It does not establish universal taunt safety. The prior failed
settling encounter used the same gameplay policy: this repair did not tune AI.

## Combat and defensive limitations

Comparable sampled net percent increases sum to approximately **137.7 for
Falcon and 256.2 for Kirby**, across 1,712 comparable pairs. These are observed
percent deltas, not official damage-dealt totals, attributed hit counts or a
match result. Kirby resets from 146.36 to zero on respawn, then reaches 109.85;
that reset is not summed as damage.

Native jab dependence is conspicuous: 28 observed Attack11 entries and 16 rapid
jab-loop entries. The loop alone occupies 745 continuity-supported native clock
frames; the complete jab family accounts for 1,890 known frames. These are
observed entries/durations, not connected-hit or conversion counts. Better
conversion and safer commitments merit investigation, not a strength claim.

Custom defense made zero starts. Its 7,324 gate outcomes were: 7,064
native-priority rejections (96.5% of all updates, **not blocking opportunities**),
245 compound input/script/state/shield/items rejections, one target rejection,
one geometry/window rejection and 13 unevaluated. Five observed native
GuardReflect entries do not by themselves prove contact or custom powershields.
The 74 sampled compound-gate rejections span rolls, jabs, specials, landing lag,
guarding and nine Wait sightings; they do not identify every failed predicate.

## Most actionable failure: late native side-B beyond the ledge

Near the end, after a native down throw sends Kirby leftward:

- f7095: Falcon Wait at x=-47.31, y≈0; native CPU outputs B + left. Mod action=0,
  owns=0. Kirby is already airborne left of the stage at approximately x=-84.22,
  y=31.17.
- f7096 onward: native SpecialSStart (Raptor Boost). Startup initially moves
  inward before the leftward rush; the trajectory is not uniformly outward.
- f7119: FallSpecial at x=-69.56, beyond Battlefield's left ledge (-68.4).
- f7143: still FallSpecial at x=-93.44, y=-38.69.
- f7168: DeadDown at x=-112.19, y=-111.19.

Recorded Falcon percent remains 137.7 across that sequence; no custom tactic owns
it. The trace strongly supports an unsafe native side-B commitment carrying
Falcon offstage into helpless fall, not a failed custom wavedash or a new
recorded damaging launch. Native `ftcaptainspecials.c:345–367` explicitly routes
loss of floor during grounded startup through `ftCo_80096900` into FallSpecial.
An independent raw-data/native-code review corroborated this and the taunt.
It does **not** establish the game's official SD/KO credit or match score.
Sparse snapshots are not an exact contact/motion replay.

The next competence investigation should prioritize rejecting unsafe attack
commitments **before** they start near a ledge, using legal controller decisions
and stage geometry. Once the native special has produced helpless fall, do not
"repair" it by changing physics, motion states, jumps or recovery timers.
Native priority **9** persists through the commitment and sampled fall; sampled
horizontal input stays neutral after startup. Trace this existing grab/throw
follow-up script, not just fresh priority-2 attacks. Also investigate legal
horizontal air drift: native FallSpecial permits drift, so helpless does not
mean all control is impossible or that every such departure is unsalvageable.
This review does not implement a veto/drift policy or weaken recovery fallback.

## Next validation priorities

1. Preserve the repaired transport and historical-v1 quarantine. The live ABI
   corruption blocker is cleared for this capture; measure overhead separately.
2. Investigate the native side-B ledge commitment before increasing showboating.
3. Investigate jab conversions and atomic defense-admission reasons without
   treating all CPU updates as missed punish/block opportunities.
4. Add Kirby-specific motion names if fuller human-readable timelines are needed.
5. Use further controlled, tester-approved encounters before claiming stronger AI,
   winning ability or consistent technique success. Dolphin is now closed.
