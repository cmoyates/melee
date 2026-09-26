# Observe the controller after a scenario ends

The retained grounded-combat matrix commanded neutral at the end of all 120
trials, but three interrupted trials stopped before observing that release.
The worker previously stopped on the same frame as the terminal command.

The scenario now freezes its original result and end observation, then emits
only neutral while waiting for a subsequent neutral controller observation.
This takes at most eight observations. A frame, episode or life discontinuity
ends the wait without claiming a release. The worker waits for this phase to
finish, and the independent audit checks observed controller packets, frozen
result/skill traces, neutral commands and the bounded release report.

Release-only frames are excluded from measured skill frames and combat/aerial/
option outcome audits. A failed or interrupted skill remains failed. A missing
release, timeout or discontinuity fails the release audit. Older reports without
the added field remain readable and receive no retrospective release claim.
Existing strict skill acceptance gates and all trial denominators stay intact.

355 host tests pass. Coverage includes held input followed by release, bounded
timeout, frame/life/episode changes, forged observed input, changed results,
unreported extra frames and the actual worker recording a post-result release.
Native suite `scenarios-8820e122022c46e281a07782c30f2bfb` ran two trials per
grounded action/direction (twelve total) in 209.95 seconds. All twelve observed
neutral on the first subsequent frame. Eleven skills completed; one right grab
acknowledged at frame 221, aborted to hitstun at 225, then observed release at
226. That interruption remains a failed skill.

All 4,588 game frames replayed exactly, including the extra release frames and
the frozen result reports. Raw audits, source identity and owned cleanup passed.
Suite summary SHA-256:
`c4b103b3410d25287c1765979c0fda4a0a06eea87e8faeed8649bc25a9391c34`.
The twelve-trial pilot does not pass or replace the separate strict twenty-per-
direction combat gate. No provider was contacted.
