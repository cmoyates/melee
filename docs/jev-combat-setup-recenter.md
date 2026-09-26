# Combat setup recentering

The J16 120-trial suite had four setup timeouts, all in right-facing trials.
Each included Fox grounded left of x=-35 with Mario still farther left, for
161–208 frames. The first retained failure,
`match-b1af197ec9b9400e983fd199d1970a47`, repeatedly queued slow-left near
x=-62 while Mario stood near -68.4. Walking left could not establish the
required right-facing geometry; the ordinary short-hop crossing was correctly
disabled there by its landing-space bound.

The setup now recenters when the opponent is on the wrong side and Fox is
outside that safe crossing region. It moves toward the interior, stops once
there is room, and waits for a close crossing opportunity instead of chasing
back to the same edge. Both directions share mirrored conditions. A neutral
setup packet still precedes a crossing or measured-skill handoff.

This changes only ordinary controller inputs during scenario setup. The
480-frame setup deadline, legal starting predicate, 180-frame measurement
deadline, native motion acknowledgement and interruption outcomes remain
unchanged. CPU behavior and game RNG remain uncontrolled; recentering is not a
guarantee of a successful setup. Damage still inhibits setup movement.

Regression tests cover both mirrored edge traps, interior waiting, opponent
approach, neutral release before crossing, damage inhibition, the unchanged
timeout, and an already legal attack's measurement boundary. Live validation
is pending; original setup failures and all measured interruptions are retained.
