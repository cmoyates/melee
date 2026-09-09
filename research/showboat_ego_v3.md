# More visible ego: native constraints and implementation direction

The user confirms quickstart works and the bot feels better, and asks for much
more obvious toying: dance while the rival recovers, taunt when there is room,
and show off precise blocking. This is gameplay feedback, not a controlled
win-rate measurement or proof the bot can win on demand.

## Breathing-room antics

Previous dance admission required vertical separation <20 and horizontal gap
55–115, an empty native VM and a random roll. Those conditions exclude most
far-offstage recoveries and much ordinary native locomotion. Raising ego alone
cannot fix that. New antics should exploit visible geometric separation, not
camera/offscreen flags, and recheck every update.

- Static FD/Battlefield main-floor support and signed runway bounds remain.
- Native attack/recovery/defense decisions and fresh cached attacks must survive
  flourish cancellation. Exact VM ownership is required before clearing inputs.
- Short dance/crouch sequences use legal transitions. They are not arbitrarily
  cancelable during native dash restrictions, and cannot guarantee avoiding an
  opponent's future input or a projectile not yet spawned.
- Current rival speed is an observation, not a universal future recovery cap.
  Teleports, fast specials, ledge transitions, projectiles and unknown reach
  require conservative vetoes, not invented frame-perfect safety certificates.
- A 60-frame Falcon D-pad taunt remains a real commitment. Merely releasing its
  input cannot cancel it. Keep full taunts on the existing certified KO-reset
  window; use frequent shorter mockery for ordinary live recoveries.

Source: `showboat_ai.c`, `ftCo_Dash.c`, `ftCo_Squat.c`, `ftCo_AppealS.c`,
`ftCo_CliffWait.c`, `ft_0D4D.c`, `mplib.c`, and prior wavedash/stage research.

## Shield inputs and actual powershields

`fighter.c` input preprocessing synthesizes LR and full trigger pressure from
digital L/R. A naturally fresh digital edge with trigger threshold timer <2
can enter GuardReflect. Holding, switching shoulders under continuing pressure,
or releasing/repressing inside a single VM execution cannot repeatedly reset
that opportunity.

Local `PlCo.dat` common data (loaded from `ftLoadCommonData[0]`, file offset
0x9FE0) and `ftCo_Guard.c` establish:

| Field | Value | Meaning |
| --- | ---: | --- |
| analog shoulder deadzone | .30 | Analog preprocessing |
| shield press threshold | .25 | Input threshold timer |
| powershield_input_window | 2 | Digital onset eligibility, timer 0/1 |
| x2A4 | 1 | Projectile window, expires below zero |
| x2B4 | 3 | Fighter-hit window, expires below zero |
| x268 | 8 | Ordinary minimum shield-hold counter |
| maximum shield health | 60 | Native resource, never modified |

The normal uninterrupted windows include two projectile collision opportunities
and four fighter-hit opportunities. Hitlag/callback scheduling must not be
replaced with an unconditional wall-clock countdown.

GuardReflect by itself proves an **attempt**, not contact. In
`ftcoll.c:ftColl_80076CBC`, successful fighter powershield collision checks
`x221C_b2`, skips ordinary shield damage, calls `ftCo_80094138`, and generates
feedback. `ftCo_80094138` sets `mv.co.guard.x1C` (the cancel opportunity) and clears
`x10` (minimum hold). It does **not** set `x20`. These fields must only be read in
compatible guard states and deduplicated per fresh guard attempt; stale flags
from an earlier success are not another powershield. Ordinary projectile shield
contact is not equivalent to that fighter-hit success path.

`ftCo_80092BCC` latches shield release in `mv.co.guard.xC`; reholding does not
simply undo it. GuardSetOff has no ordinary IASA. A one-frame shoulder pulse
followed by blind release can therefore harm defense. No timer repair, forced
Guard state, shield-health change, or mandatory pumping to refresh the window.

## Native threat and defensive choices

CPU arbitration precedes the mod, and collision geometry finalization follows
it. `ftCo_800BB9B4` is a **mutating** native scanner; do not call it as a read-only
query. Its freshly cached threat fields are `xF8_b12`, `xF0` and `xF4`. Native
fighter prediction extrapolates initialized hit-capsule history three frames;
that is not exact contact ETA. Newly enabled or discontinuous hit geometry is
not reliable. Victim-history membership and grab/unblockable paths matter.

Scenario 7 includes several defenses, not merely shielding. For a fighter
threat, native `ftCo_800BA9A0` frequently chooses a directional roll; for other
threats it may shield, spotdodge or use a character-specific response. Native
level 9 already uses digital R when it chooses a shield.

The intended precision change is deliberately narrow: favor a healthy, grounded
hard shield at a **fresh, empty, verified melee-defense decision**, rather than
its default roll. This changes the choice of defense, not native priorities or
rules. Do not overwrite an already queued/running native defense, remove an
existing shield to chase a later perfect window, or substitute shields for
known grabs/projectiles/unsafe states. Holding and handoff must preserve native
shieldstun/SDI and allow native decisions to handle R without a manufactured
release. Repeated successes require naturally separate, legally available
onsets; no claim of perfect blocking of every attack.

Source: `fighter.c` input preprocessing; `ftCo_Guard.c`; `ftcoll.c`;
`ftcpuattack.c:ftCo_800B9F90`, `ftCo_800BA9A0`, `ftCo_800BB104`,
`ftCo_800BB9B4`; `ftCo_0A01.c` arbitration/dispatch; `ftcmdscript.c`.

## Evidence needed

Actual-C sanitizer tests can validate inputs, ownership, resets and observation
logic, not simulate the native collisions. Distinguish flourish starts, shield
onsets, accepted GuardReflect, actual powershield contacts, and gameplay value.
Watch style punishment, shield breaks, recovery failures and lost punishes—not
just increased activity counts. Preserve quickstart, unlocks and controller
mapping; coordinate any restart of an active playtest.
