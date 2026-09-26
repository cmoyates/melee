# Grounded platform boundary recovery

The long recording test exposed a persistent stall in
`match-f5c0d313437a4ffe86f12a4a46b1f5ed`. Fox was natively grounded in Wait
at x=18.80141, y=54.40010, just beyond the top platform's approximate endpoint
x=18.80000. This accounted for 23,337 standing frames with the reflex latched
in conservative failure. An earlier grounded sample at x=57.63696,
y=27.20010 was also outside the right platform's approximate x=57.60000 edge.

Support estimation now permits a declared horizontal tolerance of 0.1 game
units at each static interval. Native grounded status and the existing strict
half-unit height check are both required. Beyond the tolerance, or at an
unsupported height, geometry remains unknown. Airborne fighters never gain
support through this tolerance. This remains an estimate, not an exact native
collision query.

Recognizing the supported position lets the existing reflex landing path clear
its earlier failure and return ownership to ordinary skills. Skill movement
destination bounds and their eight-unit platform margins are unchanged. The
fix does not permit movement off a platform or bypass hitstun, death, resource,
input-neutrality, freshness or commitment checks.

Tests cover both recorded positions and their mirrors, just-inside/outside
boundaries on all surfaces, wrong-height and airborne observations, persistent
failure clearing through AsyncPolicy, damage preemption and unchanged outward
movement refusal. Historical observations can establish the classification
regression; altered control output cannot be called a replay of the original
game's future. Fresh live evidence is required separately.

## Live validation

Fresh run `match-7a9e8d0da0674e38a7d8cbef60c44982`, code `a5a1dfa8b`, captured
nine configured minutes (541.41 seconds including shutdown) without provider
calls. It exercised 270 grounded boundary records that the old interval-only
classifier would call unknown: 179 on top, 88 on left, and three on right.
Of these, 268 had safe reflex state and two remained in appropriate damage
handling. None had a failed reflex. There were zero grounded Wait frames with
latched failure anywhere in the capture.

All 31,460 game frames across two episodes reproduced exact semantic states,
decisions and controller packets in incident
`incident-70d961bc4adc4afcb440cd66b287a30f`, with sockets and subprocess creation
forbidden. Integrity and policy audits passed, with zero gaps, duplicates or
rollbacks. Both replay/rule checks and neutralization/process cleanup passed.
All 31,861 recorder rows were written (345,538,149 bytes), with queue high-water
two. Observed frame rates were 59.83/59.86 FPS. All 285 host tests, agent CI and
native build passed; repository-wide style retains its pre-existing failures.

The simulated backend produced 302 accepted decisions: 282 raw-acknowledged
completions and twenty conservative interruptions. The first match ended in a
0–4 loss, and the second was partial at the deadline with stocks 1–4. Fixing the
stall restored activity; this run does not establish improved playing strength.
The original 31,497-frame stalled trace remains retained and reproduces exactly
on its original recording-capacity checkout. Its future is not relabeled using
the changed controller.

Frame SHA-256:
`949eb74d79f40b21d9e986a97c24370c7e27aaa25a878e96b2342c8eaaf72a31`.
Replayed packet SHA-256:
`aaecf91282fb829a0821d8698ec2e88c78b6b62dceabbf8825be1f3e6864c27e`.
