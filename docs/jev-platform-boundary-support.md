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

Live validation is pending. The original 31,497-frame trace remains retained
and reproduces exactly on its original recording-capacity checkout.
