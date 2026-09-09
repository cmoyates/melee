# First side-B safeguard live review (fourth recorded playtest)

## Capture and integrity

The tester approved launch and shutdown. Dolphin exited 0; no restart, build or
new gameplay tuning followed this review.

- Capture: `20260909T185848.011005Z-7e2f413e7e2b43e082e612810f3b427c`.
- Clean launch source: `b52670cc51c0c0bcc2c723d84e4b091cbe8dac8e`.
- DOL: 4,522,176 bytes, SHA-1 `463a5a435aa5241f943fd21bfc87a4612c9eb2d7`.
- Controller SHA-1: `00dc2b7a5339493fe11fcf93e3adba16e93e0451`.
- Final runtime log: 1,058,829 bytes, SHA-256
  `82e26b2be522ec36033d8809347dd7ae07ed60876984e362d9b2e14fa121bc26`.
- 2,766 accepted v2 records, zero rejected: 1,741 samples, 1,017 gates,
  four begin/end pairs. Stable Falcon/Kirby kinds 2/4; valid encoding/flag fields.
  Original log/manifests and generated `report.json`/`report.md` remain archived
  locally. The earlier mixed-varargs defect did not recur.

Battlefield, normal Versus Time. Four recording intervals cover f0–2096,
f2097–4271, f4272–5439 and f5440–7200. Their 2,220/2,175/1,168/1,761
reported updates total **7,324 per tactic**; each interval's gates agree with
its end count. The first split follows Kirby's respawn; the next two follow
Falcon's respawns. These are not four matches or an official score.

The report's overall partial-coverage label reflects startup/tail gaps and
unlocated repeated-clock observations; Kirby-specific numeric motion-name
fallbacks are a separate labeling limitation. Neither is the old corruption.
Stocks stay 3 in Time and do not supply a result. Item/projectile-presence flags
occur in some samples; they do not establish that random item spawning was
enabled (fighter projectiles can also occupy that list).

## The main-floor safeguard actually activates

At **f1902**, event **128 `side_b_veto`** and the independent legacy line
`SIDE-B VETO: left native throw follow-up; VM retained` agree:

- Falcon: Wait, x=-49.2507, y≈0, percent42.96, native priority9/cache0.
- Kirby: DamageFlyTop, x=-86.7707, y32.47, percent117.16.
- Post-filter CPU output: all-zero buttons/sticks/triggers. This is not a
  requested B hidden behind a plausible-looking motion acknowledgment.
- Nominal main-floor left runway is about19.15, below65.17 required by the
  normal-scale forward envelope and reserve.

There is no SpecialSStart after this veto. Falcon remains Wait at the same x
through f1958, with sampled percent42.96 unchanged. The queued jump appears at
f1958, KneeBend at1959, JumpF at1962, double jump at1979, forward-A input at1988
and AttackAirF at1989. Priority9 returns to1 at1991, then native2 at1992. Thus the
retained wait/tail is **observed**, not a speculative claim that the script was
cancelled or that Falcon immediately replanned.

At f2002, Falcon is in Knee's animation frame14 with hitlag; Kirby gains18
percent (117.16→135.16), enters DamageFlyRoll and also has hitlag. That is strong
contact-consistent evidence, but not an explicit attacker/hitbox-ID record.
Falcon lands on the left platform at f2032, still42.96%; Kirby enters DeadLeft
at2038. The preserved tail was useful in this local encounter, not a proven
better general combo planner. No counterfactual saved-stock or winner claim. An independent read-only review
corroborated the veto, native continuation, platform landing and later
platform-origin departure from exact raw binary32 fields.

Falcon then taunts on the platform at f2040. **This is native taunting:** action
and ownership remain0, no custom taunt event/start is logged. Do not credit it
to the custom certified-taunt routine merely because it follows the veto.

## Most important remaining gap: platform side-B

At f5302, a similar priority9 throw follow-up occurs on the **raised left
platform**, not the main floor:

| Frame | Falcon observation |
|---:|---|
| 5289 | Wait, x=-44.78, y27.2, percent9.6 |
| 5302 | B + left, native9/cache0, action0/owns0; no veto event |
| 5303 | SpecialSStart, x=-42.99, y27.2 |
| 5323 | FallSpecial, x=-57.85, y27.2 |
| 5335 | FallSpecial, x=-70.51, y17.06, already beyond the main left ledge |
| 5358 | Native jump input while still FallSpecial, too late to undo entry |
| 5378 | Native up-B input while still FallSpecial |
| 5381 | DeadDown, x=-105.70, y=-110.09 |

Sampled percent remains9.6 with no self hitstun/hitlag flags during this departure.
This strongly supports the same unsafe commitment pattern from a platform,
not a fresh damaging launch. The current implementation explicitly excludes
pass-through platforms and non-main-floor geometry. The recorded location is
therefore a known scope gap sufficient to exclude it; the trace does not expose
every other internal gate field or prove which predicate returned first.

The proper next investigation is **controller-only pre-commitment platform
safety**, not extending main-floor endpoints across a platform or forcing a
recovery after helpless entry. A platform can end before the main stage does;
the subsequent air coast can carry Falcon beyond the lower floor before he
lands. Validating only the main-stage ledge distance would miss this.
The native script still controls the neutral drift/wait after this unfiltered
move. Broader script replanning or recovery changes were not implemented here.

## Other death, preserved native moves, and combat

The earlier Falcon death is different: at f3969 a damaging launch raises percent
137.71→147.76 near the left edge and enters DamageFlyHi. Falcon is later far left
in DamageFall, attempts native aerial up-B at f4100, then FallSpecial and
DeadDown at4213; respawn is4272. Native recovery priority4 and inward inputs are
present. This was not the filtered side-B episode, and the trace alone does not
establish an avoidable recovery error or exact source of every percent increase.

Six ordinary ground side-B starts and two airborne starts remain observed.
Five ground starts are priority2; the sixth is the platform priority9 departure.
Examples include the central start at f407 and an inward start at f2764. These
show that side-B was not globally disabled, **not** live validation of the
priority9 filter's central/inward allowance branches or every floor seam.
All eight request rows have held/global-item bits clear; item presence elsewhere
in the match is not their observed scope distinction. The report's existing
five tactic reasons are not atomic safety-rejection reasons.

Additional custom telemetry:

- One up-air interception acknowledgment, event8 at f476, independently logged.
  At f482 its animation coincides with both-fighter hitlag and Kirby gaining12
  percent (47.07→59.07). Strong contact-consistent evidence, not an explicit
  attributed hit counter or a guaranteed conversion rate.
- **13 L-cancel input samples**. These are not13 proven lag reductions; the
  f2028 pulse, for example, is followed by ordinary Landing rather than a
  LandingAir state, so counting all pulses as successes would overclaim.
- No custom grab acknowledgment, wavedash, powershield contact, Punch, dance or
  certified-taunt start. Native grabs/throws, taunts and specials still occur.
- Sampled ego range0–100, finishing100. Damage/life penalties occurred; this
  varied encounter does not establish an ego-policy improvement/regression.
- Native jab-loop dependence persists:18 Attack11 entries,13 rapid-loop entries,
  with614 continuity-supported native frames in the loop. Entries are not hits.

Comparable net percent increases total approximately158.36 for Falcon and256.35
for Kirby over1,736 comparable pairs. These are sampled percent deltas, not
score-screen damage dealt or attributed hits; resets are excluded and sources
such as magnifying-glass damage can contribute. No match result is inferred.

## Gate totals and next work

All counts below are updates, not unique elapsed frames or missed opportunities:

- Personality: unevaluated2, no_candidate1813, native_priority143,
  physical/state1623, geometry/window2382, ego/caution1361; zero custom starts.
- Combat: active1, started1, input/script428, physical/state1996,
  geometry/window4897, completed1.
- Movement: unevaluated2, physical/state6734, geometry/window588; zero starts.
- Defense: unevaluated2, native_priority7266 (99.2% of all updates),
  compound input/script/state/shield/items55, target1; zero custom starts.
- L-cancel: started13, physical/state7012, geometry/window234, cooldown65.

The main-floor input veto and retained native continuation have now been seen
working in a real encounter. Platform commitments are the next evidenced gap.
Rare defense admission, jab conversions and quiet custom personality still merit
follow-up, without treating all updates as actionable blocking opportunities.
Dolphin is closed; no new patch or launch was performed after this review.
