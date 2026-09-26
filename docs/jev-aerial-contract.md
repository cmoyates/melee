# Fox short-hop aerial contract

Status: J17 has full live-suite evidence; left-side clean-completion acceptance
remains open. Right-side matched landing-lag calibration passed.

## One measured approach

The first aerial is Fox neutral-air, native common motion 65, after one ground
jump press. The primitive waits for motion 24 (KneeBend), observes released X
while still in jumpsquat, then requires an ordinary rising jump motion 25/26
with one remaining jump. Only then does it send neutral-stick A once. It waits
for motion 65 and drifts in the declared direction, then releases on landing.

[KneeBend](../src/melee/ft/kinds/ftCommon/ftCo_KneeBend.c) sets the native short-hop
flag when the initiating XY input is released during jumpsquat.
[Jump](../src/melee/ft/kinds/ftCommon/ftCo_Jump.c) selects the fighter's separate
hop or full-jump velocity from that flag. We retain observed jumpsquat, release,
takeoff velocity and peak height instead of inferring short hop from one timed
button command. A missing release/takeoff acknowledgement aborts without A.

[AttackAir](../src/melee/ft/kinds/ftCommon/ftCo_AttackAir.c) selects neutral-air
only when both stick axes are within the native neutral thresholds. Horizontal
drift therefore follows the fresh neutral-stick attack press; combining them
could select forward/back-air. Hitlag preserves an acknowledged aerial but
sends neutral input. Own hitstun, life changes, observation gaps, unexpected
motions or unsupported geometry terminate the commitment without follow-ups.

The initial declared setups are settled main ground at x opposite the intended
drift direction, with magnitude 25–45. The primitive supports main-ground
landings only, inside x ±55 and below y 24. Platforms require separate future
setups. Fast-fall is optional in J17 and omitted from this first calibration.

## Landing and L-cancel evidence

`sh_nair` emits at most one L pulse while motion 65 is falling toward the main
floor, outside hitlag and hitstun. `sh_nair_no_lcancel` follows the same path
without that pulse. Both then wait for a known grounded actionable state and
observed neutral input; sending L is never itself called an L-cancel success.

[LandingAir](../src/melee/ft/kinds/ftCommon/ftCo_LandingAir.c) uses the native
recent-shield-input timer to shorten the fighter's configured landing lag. It
changes animation playback rate, so animation-frame increments are not elapsed
game frames. The recorder instead counts consecutive observed native
LandingAirN (70) game frames until actionability. Ordinary landing (42), missing
lag states, interrupted landings and partial traces cannot establish reduced
neutral-air landing lag.

Individual traces always leave `reduced_landing_lag` unknown. The paired suite
reports a reduction only when all 20 clean trials in each direction and mode
have one consistent observed duration, all intended L pulses are verified,
the no-L controls contain no pulse, and the attempted mode's duration is lower.
It publishes both duration distributions. Game RNG is not seeded, so these are
matched declared fresh-match setups, not identical counterfactual physics.

Acceptance command: `skill-check --suite aerial-v1 --repeats 20`. Its 80 trials
cover both directions with and without the L-cancel attempt. Full motion and
neutral-completion acceptance is separate from the landing-lag calibration.

The September 26 full run stopped after 13 scheduled trials: seven completed,
three were interrupted by CPU hitstun, two failed setup, and one hit the
30-second wall-clock limit at approximately 28 observed FPS before setup ended.
The latter saved its replay and shut down cleanly but failed the trial audit;
it is retained as a failure. Scenario launches now allow 60 wall-clock seconds,
inside an 80-second parent deadline. Setup/measurement game-frame limits and
acceptance criteria remain unchanged.

Recorded failed setup also exposed repeated full-stick dash turns across the
settling window. Aerial setup now uses walking input, then observed neutral
release, to reach the same declared predicate without that oscillation.

## September 26 measured result

The corrected pilot completed all four mirrored cases. The full suite
`scenarios-a536d263980b4d969d03864e8b3fb6cd` then completed all eighty scheduled
trials in 1,312.00 seconds, with no setup failures or audit failures:

| Setup | Aerial acknowledged | Clean neutral landing | LandingAirN duration |
| --- | --- | --- | --- |
| L-cancel attempt, left | 20/20 | 17/20 | 7 frames in all 17 completions |
| L-cancel attempt, right | 20/20 | 20/20 | 7 frames in all 20 completions |
| No-L control, left | 20/20 | 11/20 | 15 frames in all 11 completions |
| No-L control, right | 20/20 | 20/20 | 15 frames in all 20 completions |

All twelve interruptions were own hitstun after aerial acknowledgement. They
terminated with neutral input and remain failures of the clean-completion gate;
they were not replaced or omitted. All forty intended L pulses were observed,
and the forty no-L controls contained none. The right-side twenty-versus-twenty
comparison establishes reduced landing lag for that declared setup. The left
comparison remains uncalibrated under the strict suite contract. Overall
acceptance is false, and J17 remains open.

Every replay/rules/raw-state/cleanup audit passed. All 21,361 game records
reproduced identical decisions, controller packets and complete scenario traces
offline. Suite-summary SHA-256:
`3bcd980754aa3e5fefc1430abdfbe61b656afabc75467a15f954f1d9f4895269`.
Private audit: `build/jev/continuation-20260926/j17-final-suite.json`.

The stock DOL, stock disc and pinned emulator fingerprints were reverified, and
tracked native source/config/assets have no diff from the original Showboat
base. The historical forty-two-file manifest under `/tmp` is no longer present;
this continuation does not claim to have rerun that missing full baseline.
The aerial suite made no provider calls. A separate twenty-request J18 frozen
corpus evaluation ran during its final portion and is accounted independently.

Host coverage includes 245 tracked tests. CI exposed a scheduling assumption in
an existing provider test: its fifty-millisecond deadline could expire during
ledger fsync before the mock transport entered. The test now explicitly fires
the deadline callback after observing entry, still asserting that the caller
times out while the occupied transport slot and spend reservation are retained.
Production deadline behavior is unchanged.
