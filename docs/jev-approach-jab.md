# Bounded approach, then a fresh jab

This is the mechanical tracer bullet for #62, before exposing a new tactical
profile to Jev. Existing atomic candidate profiles remain unchanged. The paid
grounded experiments applied movement but no attacks: short attack openings
often disappeared during the provider response. A longer-lived option can
choose to close distance first and let the local executor validate the attack
when the opportunity actually exists. This is a hypothesis to test, not a
claim that the new option improves play.

`approach_jab` requires known shared support, a vulnerable unshielded opponent
within 34 units, the declared facing, and released actionable ground input.
It uses the existing six-unit movement skill, waits for observed neutral and
actionable state, then rechecks every jab precondition. It emits one fresh jab
press and uses the existing native motion/contact/completion tracker. Both
directions use the same code and the same single frame-to-packet executor.

The direction and support are fixed for the option. Before the jab press,
crossing, unsupported geometry, target invulnerability/shield, damage, stock
or episode changes, frame gaps and a target moving beyond 40 units terminate
with neutral output. There are at most four movement commitments and 180
observed frames. Observing displacement beyond 30 units aborts further setup;
this is an observed-frame cutoff, not a continuous physics constraint.
After the press, the jab tracker owns hitlag and completion rather than
pretending that a changed opponent position can undo a button already sent.

The trace separates the option, every child movement, jab press, native
acknowledgement, contact and terminal release. The raw auditor checks move
displacement/velocity/input, child ordering/preconditions, the jab's existing
contact evidence and terminal completion. Missing or forged motion/input
evidence fails the audit. The measured scenario requires at least one move
before the jab; an immediate jab cannot pass as an approach demonstration.

Two fresh-match ordinary-input scenarios set up a settled shared main-ground
opportunity 18-30 units away. Setup has the existing 480-frame deadline and
measurement has a 180-frame deadline. Setup failures and interruptions remain
in the report. The explicitly limited pilot gate requires at least one audited
completed approach/jab in each direction and valid traces for every requested
trial; it is not a playing-strength or reliability threshold.

```sh
uv run --project agent melee-agent scenarios --suite approach-jab-v1 --repeats 3 --duration 240
uv run --project agent melee-agent inspect RUN_ID --scenario-evidence
```

All 324 host tests pass. Coverage includes mirrored complete packet paths, changed geometry,
facing/input revalidation, hitlag retention, damage/stock/episode/gap aborts,
movement/travel/time bounds, scenario execution and raw evidence tampering.
Live trials and the explicit shared candidate profile are pending. This slice
does not relax provider identity, age, confidence, reflex or legality checks,
and does not contact a provider or change game assets.
