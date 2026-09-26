# Walk before the approach-jab attack

The first six-trial live option suite failed its pilot gate. Suite
`scenarios-68d7d3590a294954bfd2c89480bf5f7c` retained three left skill failures
and three right setup timeouts. All 2,709 game frames replayed exactly through
the scenario controller, all six raw audits passed, and launch sources remained
unchanged. No provider was contacted. Summary SHA-256:
`4a95607943ef005164720b98b4ae60ff8fd6775a2e5a31b39fa3f16a2fd22cae`.

Two left trials crossed the opponent without a jab; the third was interrupted
by damage. In `match-ea09338a99a74fcdb05fd353569432b3`, movement began at frame
161, acknowledged six units at 165, and observed released input at 166. Fox
remained in Dash and slid past Mario by frame 176: x=7.39 versus Mario x=7.74,
still moving left at 1.32 units/frame. Releasing input was not evidence that Fox
could jab. The option correctly aborted rather than issuing an invalid attack.

`ftCo_Walk_IASA` in `src/melee/ft/kinds/ftCommon/ftCo_Walk.c` checks jab input;
`ftCo_Dash_IASA` has a separate transition path. The option now uses a six-unit
walk child with existing 0.35/0.65 stick packets. It starts only from released
standing/walking in the intended direction, requires native WalkSlow/Middle/Fast
motion and velocity for acknowledgement, and aborts an unexpected dash. It still
waits for observed release and revalidates the jab. The existing full-stick move
skill and atomic baseline profile retain their behavior.

Raw option evidence now requires walking packets and native walking motion;
full-stick or dash substitutions fail. Host coverage includes mirrored packets,
dash refusal/abort, waiting for an existing dash to settle, old movement behavior,
exact delayed/local option replay, cancellation and raw evidence tampering.
All 336 host tests pass. Fresh six-trial walking suite
`scenarios-6431388d85ba438ba16e3297a80e694d` retained one complete left trial,
two left damage interruptions, one right guard interruption and two right setup
timeouts. All 2,780 game frames replayed exactly; every raw audit and source
identity check passed. No provider was contacted. Summary SHA-256:
`f105bbda7a2f350b435892f169190032b495d95c26978cc36bc5dce8c95871a6`.

The complete trial `match-d2ad0fed0dc74f1abd475b8170cc5c28` pressed jab at frame
208, observed native jab at 209, paired hitlag/damage contact at 210, and completed
with actionable neutral release at 229. Another left trial acknowledged jab
before damage aborted it. The pilot gate still fails for the right side. These
twelve total trials are retained across both implementations; the result is
evidence of one working live sequence, not a reliability or strength claim.
