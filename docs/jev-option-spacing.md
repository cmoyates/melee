# Reach the unchanged option starting predicate

The first two approach-jab suites retained five right-side setup timeouts in
six attempts. In `match-0acae8fb2e7b4af58ff3c22468367009`, the bot slowly backed
away while Mario followed. At frames 90, 120 and 150 their separations were
9.02, 16.51 and 19.09 units; Fox was still turning or walking away, so the
required released, correctly facing 18-30-unit state was never reached. By
frame 180 Fox was at x=-58.17. Setup eventually expired at the original frame
480 deadline. This is a setup failure, not an attempted option execution.

For this option's setup only, a close grounded opponent in the interior now
uses the existing ordinary-input short hop away to make room. It releases jump
after the initial press, steers for 24 units of separation, and queues neutral
on landing before the starting predicate can admit measurement. Existing
wrong-side crossing and atomic combat scenarios keep their old behavior.

The main-ground, facing, neutral-input, vulnerable-opponent and 18-30-unit
requirements remain unchanged, as do the 480-frame setup deadline, damage/life
abort paths, raw option evidence and pilot gate. No savestate, CPU patch,
teleport, timer change or provider call is used. Mirrored host tests cover
spacing, jump release, landing/measurement separation, edge and airborne-target
exclusions, old atomic setup, damage and timeout. Fresh live validation is
pending for the follow-up below; all earlier failures stay in the evidence.

The first twenty-trial spacing suite on `c492fb722`,
`scenarios-8b357939cc5d474fbfbf595629d03e5e`, completed six left and two right
approach/jab sequences, with four left damage interruptions and eight right
setup timeouts. All twenty raw audits passed and all 9,386 game frames replayed
exactly through the controller with unchanged launch sources. The declared
pilot gate passed in both directions, but the 8/10 right setup failures prevent
a reliability claim. Summary SHA-256:
`03f2507f22c589ad3064dc82e7b0e3d1241c70f1a774280e86b9fb33dfcfc0b9`.

One completed right trial, `match-335f8cce61a740c0a444d4bb1492bc04`, measured
from frame 427, acknowledged two walking children and jab, observed one contact,
and completed after 58 measured frames. Setup used 426 frames of its 480-frame
limit. That is measured execution, not a discarded setup failure or scripted hit.

The remaining timeouts exposed another setup issue: Fox was chasing Mario's
horizontal position while Mario was above him on a platform or in the air.
The follow-up waits on main ground until Mario shares that support before
attempting spacing. It preserves the landing, recovery and already-started hop
paths. All 340 host tests pass. Fresh six-trial probe
`scenarios-bf75c3b27faa42d0ac2505762d9b5de7` reached every setup, completed two
approach/jab sequences per direction, and retained two interrupted attempts.
All 2,148 game frames replayed exactly, every raw audit passed, and launch
sources remained unchanged. Summary SHA-256:
`91baf557b36c8f99074a1ceb9c5339ab67362d9c7da60652933892e728794ed4`.
The limited pilot gate passes again. Six fresh trials do not establish a setup
reliability rate or isolate the effect from CPU/game variability.
