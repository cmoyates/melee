# Fox local recovery and defense contract

Status: integrated through the shared executor and tactical arbiter. The first
four live Battlefield probes succeeded; the full 20-per-scenario acceptance run
is pending. This document distinguishes native mechanics from agent heuristics.

## Native mechanics used

| Observed native motion | Local action and acknowledgement |
| --- | --- |
| Ordinary airborne motions 25–34 or tumble 38 | Drift or request a fresh double jump when observed resources permit it. |
| Aerial jump 27/28 | Confirm a resource decrement and upward velocity, then release jump. |
| Firefox charge 353/354 | Aim while charge is observed; release B after the initial up-B packet. |
| Firefox travel 355/356 | Record launch, treat jump as consumed, and await an observed end state. |
| Special fall 35–37, 358/359 | Drift only; do not repeatedly request jump or up-B. |
| CliffCatch 252 | Release inputs while the catch animation completes. |
| CliffWait 253 | Observe neutral in the hanging state before pressing inward for get-up. |
| Cliff get-up/roll/jump 254–263 | Await observed completion; do not replace the animation with another tactical skill. |

These are Fox/native IDs, not the generic names returned by libmelee's enum.
For example, the same numeric values can print sword-dance names for another
character. The runtime separately validates that the controlled fighter is Fox.

The Fox [motion enum](../src/melee/ft/kinds/ftFox/forward.h) and
[Firefox implementation](../src/melee/ft/kinds/ftFox/ftfoxspecialhi.c) show that
air charge zeroes vertical self velocity, and launch samples the current stick,
sets the travel velocity and consumes the jump resource. Charge IASA callbacks
do not accept arbitrary interruptions. Aim therefore belongs to the charge state,
not to a guessed delay after pressing B.

[Aerial jump entry](../src/melee/ft/kinds/ftCommon/ftCo_JumpAerial.c) checks jump
resources and a new jump input, selects the forward/backward aerial motion and
increments jumps used. The pinned libmelee character table supplies Fox's basic
gravity/air-speed data; no Falcon movement timings or native CPU VM routines are
treated as callable external skills.

[Cliff catch](../src/melee/ft/ftcliffcommon.c) checks the ledge collision flags,
down input and occupancy before entering motion 252. [CliffWait](../src/melee/ft/kinds/ftCommon/ftCo_CliffWait.c)
initializes its input gate to false. [CliffClimb](../src/melee/ft/kinds/ftCommon/ftCo_CliffClimb.c)
arms that gate on neutral input before a directional get-up. Neutral during the
catch animation alone does not establish that the hanging-state gate is armed.

[Damage input](../src/melee/ft/kinds/ftCommon/ftCo_Damage.c) applies stick-based
knockback rotation when leaving hitlag. [Fighter input timers](../src/melee/ft/fighter.c)
track new L/R presses, and the [tech gate](../src/melee/ft/kinds/ftCommon/ftCo_DownAttack.c)
checks current and previous press timing. Those internal timers are not exposed
by this observation schema, so the external policy must not claim exact native
tech eligibility.

## Deliberately limited policy

The local reflex uses observed position, velocity, jump count, motion, life,
hitlag/hitstun and input release. A new life clears commitments. A frame gap
releases input and invalidates pending resource acknowledgements without extending
the existing recovery deadline. Damage interrupts the old special commitment;
fresh observations govern a later attempt.

The recovery sequence has a 180-frame deadline. Jump and up-B requests get eight
frames for acknowledgement. Unacknowledged actions are not continually pressed.
An unsupported recovery envelope (`abs(x) > 130` or `y < -85`) and unknown grounded
geometry use a bounded neutral failure. These are conservative experiment limits,
not a proof that every excluded position is physically unrecoverable.

Battlefield surfaces are approximate pinned static geometry, not native collision
queries. Coarse up/steep/diagonal/shallow/inward aim bins target known stage space.
Close below the lip, the policy rises outside the side wall before drifting after
travel; a naive diagonal can cross the wall below floor height. An opponent in a
same-side cliff motion is treated as a conservative occupancy proxy, causing a
higher, more interior target. The stream does not expose the exact native ledge
occupancy flag or ECB collision query.

During hitlag/hitstun, observed nonzero knockback permits a conservative inward/up
stick heuristic. Unknown vectors use neutral input. This is not an optimized DI
solver or a calibrated survival claim. A one-frame L pulse is attempted only in
positive hitstun, outside hitlag, with released shield input and a descending
trajectory approaching a known floor. The three-frame projection and forty-frame
press cooldown are agent heuristics, not asserted native windows. Tech success is
counted only when a native tech motion is observed.

The state machine emits action intents through the same complete-packet frame
executor and aborts tactical commitments through the existing arbiter.
It observes safe frames too, so returning to stage clears
recovery ownership before an ordinary later jump. It never writes fighter state,
position, velocity, resources, timers or CPU ownership, and never needs Jev or an
API credential.

## Live scenario contract

`skill-check --suite recovery-v1 --repeats 20 --policy offline` runs 80 fresh
matches within a default 2,400-second wall-clock limit. It exits successfully
only after every scenario has 20 audited trials and at least 18 stage/ledge
returns. A setup failure counts against that threshold. `scenarios --suite
recovery-v1 --repeats 1` is an exploratory four-trial probe; completion alone
does not certify the 20-trial acceptance threshold.

High left/right starts require signed x in (68.4,82], y in [-12,8], a descending
airborne fighter and at least one jump. Low left/right starts require signed x
in [88,112], y in [-40,-20], descending air and zero jumps. Ordinary setup inputs
run off the edge; the low setup spends the double jump outward before drifting
to its starting region. Both queued neutral and observed neutral input separate
setup from measurement. No savestates or fighter-state writes are used.

The pilot `scenarios-5b2dc9dc03b44b04abf01a1f0d4343d0` completed four audited
returns in 62.75 seconds with no API calls. High trials took 33 measured frames
each and showed native aerial jump 28 with a resource decrement. Low trials
took 85 frames each and showed charge 354 (42 frames), travel 356 (30 frames),
fall 358 and grounded landing 357 on the side platform. This confirms the
actual Fox motions even where libmelee prints another character's enum names.
