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
pending; all earlier failures stay in the evidence.
