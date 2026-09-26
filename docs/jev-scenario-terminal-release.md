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
Native Battlefield confirmation is pending. No provider calls are required.
