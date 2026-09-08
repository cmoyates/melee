# V2: strong, rules-legal Falcon with earned disrespect

## Executive summary

The target has changed: competence first, personality second. V1's long emotional
lockouts and ordinary-knockdown Falcon Punches worked against this. The user's
live session logged many ego/KO events but no custom action starts. Increasing
random rolls alone will not fix either problem.

V2 should exploit machine-speed **decisions and normal inputs**, not change game
rules. All timings, hitboxes, damage, physics, collision, movement limits and
input timers remain retail. The bot may observe structured state and execute
legal inputs with unnatural reliability. We must not call action-entry helpers
to bypass the controller, or shorten taunts, jumpsquat, landing lag or recovery.

## Research questions and scope

1. What makes existing strong Melee agents strong?
2. Which high-impact improvements fit a native GameCube C module?
3. How can Falcon be visibly disrespectful without sacrificing conversions?
4. What does local source actually establish about inputs and safety windows?

## Findings

### Strong-agent architecture

SmashBot's README describes strategies → tactics → input chains. It plays Fox,
not Falcon, and runs as an external emulator-connected program; it is not a
native DOL module to import wholesale. Its stated interface is virtual
controller presses, with machine speed and reliability rather than changed
fighter capabilities. The useful lesson is decomposition and bounded actions,
not copying Fox-specific chains or adding its external runtime.

Firoiu et al., *At Human Speed*, explicitly find that imposing human reaction
delay substantially reduces standard learned-agent performance. Their predictive
model compensates for delay. This supports exploiting fast observations and
precise execution for this deliberately inhuman opponent, but does **not** prove
that a few hand-coded Falcon tactics will beat professionals.

A learned superhuman agent needs training, model integration and benchmarking.
That is not a prerequisite for this iteration and is not what this native patch
claims to deliver. No external inference service is being added.

### Best immediate competence investments

Local source and local US v1.02 `PlCo.dat` / `PlCa.dat` establish:

- Landing-cancel input is `x67F < 7` when aerial landing-lag flag `cmd_vars[0]`
  is set. The engine itself halves the normal lag (Falcon fair 19 → 9; dair
  24 → 12). **We press the input; never change those lag values.**
- Analog trigger byte 128 crosses the 0.30 deadzone and creates synthesized
  shoulder input. It can L-cancel without digital L/R's airdodge or tech-lockout
  side effects. Predict near touchdown using the actual ECB bottom and floor
  query, preserve native drift/buttons, and restore only our analog overlay.
- Standing Falcon grab activates at script frame 6; dash grab at 10. Prefer
  close, front-facing reactive grabs from Wait/walk against shield or sufficiently
  committed states; release immediately into vanilla pummel/throw logic.
- Falcon jumpsquat is 4 frames. A sampled X pulse followed by release of both
  jump buttons produces an ordinary short hop. Wait for actual Jump/Fall before
  pressing forward+A for Knee. Knee's strong hit starts at script frame 14,
  not immediately: intercept checks must account for this commitment.
- Digital techs accept an input counter <20 **and** saved prior interval ≥40.
  Blind R spam destroys valid tech windows. Native level-9 tumble already
  predicts floor contact and attempts techs; preserve it initially.
- Native damage behavior already supplies DI. Overwriting either stick during
  hitlag can degrade DI/ASDI. Leave DI/SDI alone in this iteration.

### Disrespect that also serves a purpose

Dashdance is suitable: it advertises control of space and can bait commitment,
while remaining interruptible through ordinary game rules. Falcon's mobility,
Knee and stomp are naturally expressive; continuing a real conversion is more
impressive than replacing it with a slow Punch.

A safe neutral-reset dance should yield to a selected attack, nearby landing
lag/knockdown/hitstun follow-up, defense or recovery. A real taunt should be an
insult **after securing a long reset**, not while the opponent is actionable
but distant. V2 should reserve Punch for exceptional long vulnerabilities such
as a dazed shield-break opponent, not ordinary tech chases.

Local movement constraints:

- Dash needs a fresh ≥0.8 horizontal flick within a 2-frame timer window;
  ±127 works, ±100 does not.
- Fresh forward Dash disallows reversal through animation frame 4. Check actual
  Dash/Turn state and animation frame before reversing, not `age % 3`.
- RunBrake cannot directly horizontal-input dash-cancel. No fake dashdance by
  forcing motion state or timers.
- Island endpoint distance is Euclidean, not signed stage clearance. For the
  first dance, use signed floor endpoints, displacement/travel reserves and
  hazard-free supported main floors; do not equate 'not a platform' with safe.

### Taunt certification, not random courage

Local Falcon left/right taunt animations last 60 frames, with no early IASA.
A three-update controller sequence still commits to that full animation.
Ordinary death has a countdown and normally leads to 60 mandatory Rebirth
frames. Star/screen deaths have multiple phases. Read only the countdown union
member valid for the actual death motion; use a conservative remaining-reset
budget, checked again immediately before D-pad Up.

RebirthWait's maximum duration is **not** guaranteed: the player can leave at
once. Respawn invulnerability is not inability to attack. Outstanding projectiles,
items and stage hazards also invalidate a long-pose safety claim.

### V1 telemetry explains missing antics

In the pre-V2 HUD/controller session: 372 SHOWBOAT log events, 8 opponent
KO/death events, zero custom action starts (source-review snapshot). The exact
rejecting gates were not logged, so attribution is not proven, but V1 had:

- −35 ego for a 20% hit, sometimes another −15 danger penalty;
- 300-frame damage / 600-frame stock-loss personality lockouts;
- high-percent danger perpetually refreshing suppression at ≥110%;
- 120-frame celebration windows expiring before serious mode;
- a shared multi-second cooldown and overly stationary start states.

V2 separates immediate physical safety from ego/emotional recovery and competence.
Fast technical actions should not switch off because Falcon got hit. A certified
post-KO reset can permit celebration despite high percent or residual caution.
Short movement antics need a much shorter cooldown and attribution window.

## Evidence, uncertainty, and implications

Local source is ground truth for this executable:
`fighter.c` input preprocessing; `ftCo_LandingAir.c`, `ftCo_KneeBend.c`,
`ftCo_Catch.c`, `ftCo_Dash.c`, `ftCo_Turn.c`, `ftCo_RunBrake.c`,
`ftCo_0A01.c`, `ft_0D31.c` and `ft_0D4D.c`.

The automated web claim checker returned 'unclear' for a combined architecture
claim. The fetched primary README and paper abstract explicitly support the
individual points above; no stronger win-rate claim is inferred. Search summaries
are not used as frame-data authority. No external code is copied into this patch.

Tests must distinguish issuing correct inputs from the game actually accepting
them. Track state acknowledgments and failed attempts. Successful compilation,
mock tests and a few human matches cannot establish tournament strength.

## Recommendations

1. Add analog-only landing-cancel and bounded reactive grab / aerial-intercept
   tactics, separate from ego. Preserve native defense, DI and recovery.
2. Increase visible styling through state-confirmed neutral dashdance and
   certified post-KO taunts, not more reckless Punches.
3. Display tactical action names alongside ego so the user can judge whether
   inputs produce real conversions; inspect failed-sequence telemetry.
4. Benchmark against the same human and native level-9 baseline before claiming
   substantial strength. Next focus should be punish conversions/tech chasing,
   not changing game data or trying every advanced movement technique at once.

## Sources (accessed 2026-09-08)

- SmashBot README, primary: https://raw.githubusercontent.com/altf4/SmashBot/main/Readme.md
- Firoiu et al., *At Human Speed: Deep Reinforcement Learning with Action Delay*:
  https://arxiv.org/abs/1810.07286
- *Beating the World's Best at Super Smash Bros. with Deep Reinforcement Learning*
  (discovery/context, not a performance claim for this patch):
  https://arxiv.org/abs/1702.06230
- SmashWiki, Captain Falcon (SSBM) (character/play-style context):
  https://www.ssbwiki.com/Captain_Falcon_(SSBM)
- Local assets were inspected in memory from the user's own extracted US v1.02
  disc; neither full assets nor rebuilt binaries are part of the repository.
