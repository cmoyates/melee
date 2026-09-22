# Fox short-hop aerial contract

Status: J17 integration with host coverage. Live aerial acceptance is pending.

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
