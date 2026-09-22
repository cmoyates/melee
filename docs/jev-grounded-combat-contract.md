# Fox grounded combat contract

Status: integrated runtime slice. The second
six-case Battlefield pilot completed every primitive in both directions; both
grab cases included actual capture. Full 120-trial acceptance is pending.

## Native actions and measured boundaries

The three initial primitives are jab (`Attack11`, motion 44), down tilt
(`AttackLw3`, 57) and standing grab (`Catch`, 212). Each starts with one fresh
ordinary controller press. The primitive releases attack input on the next
frame and waits for observed motion and a later grounded actionable state with
neutral input. A successful motion is separate from damage or capture evidence.

The pinned libmelee Fox frame table supplies these calibration references:

| Move | Active frames in table | First table IASA | Last table frame |
| --- | --- | --- | --- |
| Jab | 3–5 | 9 | 21 |
| Down tilt | 10–15 | 35 | 35 |
| Standing grab | 6–7 | unavailable | 29 |

Table indexing is libmelee's normalized indexing. Runtime termination must use
observed transitions, rather than assuming those values prove exact native
interruptibility. The native [jab input/animation handlers](../src/melee/ft/kinds/ftCommon/ftCo_Attack1.c)
require a fresh A press and return to wait when animation finishes. Repeated A
can start jab follow-ups; the primitive deliberately sends one press.
[Down tilt](../src/melee/ft/kinds/ftCommon/ftCo_AttackLw3.c) checks A plus a downward
stick angle and allows later interruptions through animation command flags.
[Standing grab](../src/melee/ft/kinds/ftCommon/ftCo_Catch.c) checks held L/R with a
fresh A press; Catch itself has no IASA callback.

## Legality and evidence

The initial conservative ranges are 12 units for jab, 15 for down tilt and 10
for grab, with at most three units of vertical separation. Both fighters must
share a known support surface, the bot must face the target, its input must be
neutral, and its ground motion must permit the declared fresh input. These are
policy restrictions, not geometric hitbox guarantees. Shielded targets refuse
jab/down tilt; grab remains available. Unknown or nonzero hurtbox status refuses
all three actions. An attack already in motion can whiff when the target moves;
motion completion must never manufacture a hit in that case.

An observed move start is acknowledged only by the expected native motion.
Damage evidence requires a rising opponent percent together with paired hitlag
while the bot is in its acknowledged attack motion. Shield contact is recorded
separately. This is a bounded contact observation, not a general attribution
solver for projectiles or multi-fighter games.

Grab motion 212 alone does not establish capture. Capture requires paired
native captor motions 213/216 and victim motions 223–228 in this two-player
match. Neutral input then waits for actual release and return to actionability;
the controller does not invent an automatic throw or combo. Native
[CatchWait](../src/melee/ft/kinds/ftCommon/ftCo_CatchWait.c) and
[CaptureWait](../src/melee/ft/kinds/ftCommon/ftCo_CaptureWait.c) distinguish holding,
mash/timer release and follow-up actions. A bounded timeout can retain genuine
capture evidence without claiming completed endlag.

Hitlag pauses an acknowledged attack commitment; own hitstun interrupts it.
Life changes, observation gaps and lost ground support abort with neutral input.
Start acknowledgement has an eight-frame limit; the entire primitive has a
180-frame limit including pauses. These are agent limits, not native timings.

The heuristic and seeded random selector both consume `combat_candidates` and
the same primitive executor. Their selection preferences do not bypass legality.
The heuristic prefers a legal grab against shield and otherwise a legal jab.

## Runtime and acceptance

`capture --policy heuristic` and `capture --policy random-legal` use the same
combat candidates, SkillArbiter, FoxReflex and FrameExecutor. The random mode
has fixed seed 0, and both select at most once per 60 observed game frames.
Outside a legal combat opportunity both use the same approach/neutral fallback.
These selectors prepare later comparisons; Jev's existing five tactical labels
are unchanged until the full-player integration slice.

Observation schema 4 adds nullable raw hurtbox status (enabled 0, disabled 1,
intangible 2). Unavailable status remains unknown and refuses combat. Historical
schema-3 recordings require their matching PR checkout for replay; they are not
silently reinterpreted by this schema.

`skill-check --suite ground-combat-v1 --repeats 20 --policy offline` schedules
120 fresh Fox versus Mario CPU3 Battlefield matches. Left/right denotes the
attack's facing direction. Setup uses ordinary controller input, including a
short hop to cross the opponent, then waits for observed neutral input before
the measured primitive starts. It never writes game memory or seeds game RNG.

The declared gate requires 20/20 audited motion starts and neutral actionable
completions for every action/direction, plus at least one actual capture in each
grab direction. Setup failures remain in the denominator; motion completion
does not imply damage. Independent raw-state auditing checks press packets,
motion IDs, paired contact/capture evidence and final neutral actionability.

The first pilot retained two down-tilt failures because motion 41 (crouch end)
was initially treated as an interruption, plus one opposite-facing grab setup
failure. The corrected primitive waits through crouch end, and setup releases
the crossing jump promptly. The second pilot passed all six cases. These are
separate recorded experiments, not rewritten outcomes.

The first full schedule (`scenarios-124992a6376745efa4c4993db7b911ba`)
stopped at 41/120 trials: all 41 observed their intended motion, 35 completed
and six were interrupted. One completed jab trial had an unfinished replay
after the emulator exceeded its three-second graceful shutdown limit. Its
independent audit failed, so the schedule stopped and acceptance remains false.
The corrupt replay and original summary remain private and unchanged.

The supervisor now allows eight seconds for its owned emulator to finalize
replays before force-killing it; the worker retains its three-second limit.
Scenario/capture success also requires a parseable replay with verified rules.
A host process test covers a writer that needs more than three seconds to exit;
fresh live validation is still needed to measure whether this prevents recurrence.
