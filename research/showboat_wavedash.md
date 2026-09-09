# Controller-only Falcon wavedash research

## Scope

User feedback: V2 is improving and the automatic unlocks work. Add frequent
wavedashing where useful, without replacing faster long-distance running or
sacrificing punishes/defense/recovery. Core movement should not depend on ego.
No rule, position, velocity, facing, jump/dodge timer, ECB or landing-lag writes.

Local native source is the authority; no external input macros or cheat codes.

## The usable timing window

`fighter.c` schedules animation/state update before CPU, then normal input
sampling/IASA, physics, integration and collision. The mod can therefore observe
**the first actual Jump state before upward displacement** and submit the normal
airdodge input in that same frame.

For ordinary Falcon timing, the explanatory sequence is:

1. Sample neutral to release jump/shoulder/attack inputs.
2. One sampled X press from a legal grounded jump state.
3. Observe KneeBend, release both X and Y; remain neutral during jumpsquat.
4. On the first actual JumpF/JumpB, emit digital L + diagonal down main stick.
5. Observe EscapeAir **or directly LandingFallSpecial**, release and yield.

The frame counts explain retail behavior, NOT a timer-driven command chain.
Require accepted states, previous sampled inputs and bounded ownership. If Jump
physics has already run, do not attempt a late downward airdodge.

Relevant Jump-state-only observations:

- `!mv.co.jump.x4`: first Jump physics has not run.
- `mv.co.jump.x0 != 0`: inherited short-hop latch.
- `x1968_jumpsUsed == 1`: ordinary ground jump, not a double jump.
- Previous owned motion was KneeBend; facing remains unchanged.

In KneeBend, `jump_input == JumpInput_XY` and `is_short_hop` identify/release the
intended jump. Read each union member only in its compatible state. The short-hop
latch must be set BEFORE Jump entry; releasing only after observing Jump is late.
`x2227_b0` is not a one-frame marker. The ten-frame ECB lock does not prevent
floor collision.

## Retail values inspected from the local disc

Small numeric facts, not redistributed assets. Common attributes were inspected
in memory at PlCa file base `0x3774`, common data at PlCo file base `0x9FE0`.

| Value | Native field offset | Retail value |
|---|---|---|
| Falcon jumpsquat | attributes +0x38 | 4 frames |
| Full-hop / short-hop velocity | +0x40 / +0x4C | 3.1 / 1.9 |
| Ground-to-jump momentum multiplier | +0x44 | 0.75 |
| Ground friction | +0x18 | 0.08 |
| Controller component deadzones | common +0 / +4 | 0.28 / 0.28 |
| Airdodge component deadzones | +0x32C / +0x330 | 0.25 / 0.25 |
| Airdodge force / decay | +0x338 / +0x33C | 3.1 / 0.9 |
| Airdodge landing lag | +0x344 | 10 frames |

Positive CPU stick bytes normalize by 127; negative by 128. Magnitudes <=35
vanish under normal preprocessing; magnitude 36 survives. A robust starting
choice is world-space X = direction ×80, Y = −80, well beyond those thresholds.
Direction selects the angle; stick magnitude does not scale airdodge speed.
Digital L is sufficient; analog-only L-cancel input is NOT an airdodge input.
Digital L naturally affects native tech counters—never reset/repair them.

At this diagonal, normal first airdodge physics produces approximately 1.97 units
horizontal and −1.97 vertical. An immediate floor collision can transition
Jump → EscapeAir → LandingFallSpecial between two CPU hooks. Requiring a separate
observed EscapeAir update would reject valid wavedashes.

Native LandingFallSpecial retains its ten-frame lag. Its animation rate comes
from `(0.1 + cached landing animation length) / x344`, not a custom countdown.
The ordinary landing-lag flag prevents interruption until the engine allows it.

## Admission and geometry

Wait/walk, Dash, Run and RunBrake have normal jump input paths; RunBrake checks
jump first. Run momentum needs an explicit bound/reserve. Avoid Turn/TurnRun
because facing changes and saved input reinjection complicate the chain.

Out-of-shield is a separate future technique: Guard can release to GuardOff
before checking X, consuming the jump edge; GuardSetOff has no jump IASA.

Initial support should use FD/Battlefield static main floors only, no items,
finite bounded motion, signed endpoint clearance, continuity of the admitted
floor and a read-only predicted dodge sweep using temporary collision outputs.
Do not use unsigned endpoint distance as signed runway. Reserve prejump travel,
dodge travel and the full nominal landing commitment without assuming friction
will rescue an edgeward slide. Recheck at takeoff; near-floor root and ECB
conditions must be much tighter than the old grounded taunt height tolerance.

Use medium-gap approach bursts and selective retreat from committed attacks;
leave very long travel to Falcon's fast run. Avoid idle forward/backward loops,
wave inputs during a real hitstun/knockdown punish, or overriding defense/recovery.
Inputs cannot make the committed jumpsquat/airdodge/landing lag freely cancelable.

## Ownership and integration

Start after combat declines; finish an active movement chain before considering
another aerial tactic. Clear personality ownership without clearing the new
movement script. Restore any borrowed L-cancel analog before all update gates.
Suspend movement before slot/control/opponent resets.

Bounded scripts need waits separating samples and explicit release tails.
`Done` alone releases nothing; `ReleaseAll` releases buttons but not axes/triggers.
Compare script bytes, length/cursors and priority—not just a pointer inside the
shared CPU buffer. Release an old owned script while preserving a fresh native
cached attack. Never restore an old native script snapshot. Unexpected priority
or state transitions must yield rather than erase replacement defense/recovery.

## Verification limits

Host tests can check observations, input sequences, cleanup and forbidden writes;
they do not implement actual fighter state transitions or prove displacement.
Require native build/isolation checks plus Dolphin state-acknowledgment telemetry
and human confirmation of real sliding before claiming the technique works well.

## Local source references

- `src/melee/ft/fighter.c`: process order, controller normalization/edges.
- `ft/kinds/ftCommon/ftCo_KneeBend.c`: jumpsquat and short-hop latch.
- `ft/kinds/ftCommon/ftCo_Jump.c`: accepted jump inputs, first-physics flag.
- `ft/kinds/ftCommon/ftCo_EscapeAir.c`: digital shoulder, angle/force, collision.
- `ft/kinds/ftCommon/ftCo_Landing.c`: landing-lag rate and actionability.
- `ft/kinds/ftCommon/ftCo_{Dash,Run,RunBrake,Guard}.c`: ground admission.
- `ft/ftcmdscript.c`: interpreter samples, release and persistent inputs.
- `mp/mplib.c`, `mp/mpcoll.c`: floor queries/endpoints and ECB locking.
