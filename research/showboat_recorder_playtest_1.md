# First recorded manual playtest — reviewed findings

Capture: `20260909T135006.037951Z-1cb3c0341dd94eb3b2fe9c82d698d497`.
Build/source: `435836d5e`, DOL SHA-1
`690249dfe765ebdfefff6eb861df691c92cc2aca`.
User approved launch and subsequently requested analysis and emulation shutdown.
Dolphin was terminated gracefully, exited 0, and completion metadata was saved.
No relaunch or gameplay changes were made during analysis.

## Important: live snapshot integrity failure

This is not just sparse coverage. **1,642 of 1,744 snapshots contain self flags
above 255**, impossible under the writer's eight-bit flag construction. All rival
motion values are 4 (`DeadUpStar`) despite active combat and inconsistent rival
identity values. The analyzer accepted 2,799 syntactically valid records, but that
does not establish semantic validity. Its generated damage/state summaries are
**not authoritative for this capture**.

Mixed-varargs serialization/ABI handling is a leading hypothesis: one sample
OSReport call passes 16 promoted doubles alongside many integers, crossing the
native eight-FP-register boundary. Inspection of local OSReport/__va_arg code
supports investigating that boundary, not blaming a particular layer yet.
Caller, retail formatter and Dolphin transport have not been isolated. No fields
were reconstructed by speculative shifting. Host tests passed but did not execute
retail PPC formatting; this live test exposed a gap in validation.

Withhold damage/stock totals, fighter flags/items, rival identity/motions,
continuity/motion-duration/recovery/position and native-priority aggregates from
these mixed-format snapshots. Do not infer the winner or credited KOs.

## Corroborated custom behavior

Separate legacy diagnostics and recorder event counts agree:

| Behavior | Recorded evidence | Interpretation |
|---|---|---|
| Custom grabs | 2 starts, 2 motion acknowledgments | Accepted grab animations, not a total of all native grabs or confirmed hits |
| Wavedashes | 3 starts, 3 landing acknowledgments | Actual legal landing states observed; not proof of optimal displacement/punishes |
| L-cancel overlay | 5 samples | Inputs emitted, not confirmed lag reduction |
| Personality | 6 starts | Three neutral dances; two offstage dances; one offstage crouch sequence |
| Custom aerial interception | 0 starts/acknowledgments | Does not imply no native aerial attacks |
| Precision-shield layer | 0 starts, 0 confirmed custom powershield contacts | Timing quality was not exercised by an admitted attempt |

Situational evidence from legacy logs:
- Two neutral dances yielded to a technical wavedash after 7 and 6 updates.
- The third neutral dance yielded after 4 updates for insufficient next-leg runway.
- Of the two offstage dances, one completed after 16 updates; the other yielded
  after 7 when its window/recent-hit safety gate failed. This does not identify
  which predicate failed or prove that mockery caused damage.
- The offstage crouch input sequence completed after 12 updates; completion of
  an input sequence is not blanket proof of animation acceptance.
- Ego began at 55, fell to 13 following a new-life penalty, then rose to 100.
- No custom full-taunt/Punch acknowledgment was logged. Some raw self snapshots
  show AppealSR with mod action/ownership zero, so do not conclude that Falcon
  never taunted or credit the custom KO-taunt logic from those rows.

## Why layers declined

Integer-only gate/end records agree on **7,324 observed updates per tactic** over
five recording segments. These are neither five matches nor 7,324 unique native
frames; the recorded clock spans 0–7200, including repeated startup clock values.

Defense: native-priority gate 7,238; combined fresh-script/input/stance/shield/items
gate 65; target/lifecycle gate 2; not evaluated 19. Roughly 98.8% of logged updates
were outside required native defense priority 7. The remaining 65 do not identify
one atomic cause. The current admission policy did not engage; this was not a
failed series of powershield timing attempts.

Combat: geometry/window/planner group 5,171; physical/state group 1,737;
input/script group 395; not evaluated 15; two starts, two active updates, two
completions. These groups cannot quantify missed guaranteed punishes.

Movement: physical/state group 6,656; geometry/window group 643; not evaluated 4;
three starts, 15 active updates, three completions.

Personality: geometry/window 2,969; no candidate 1,931; physical/state 1,158;
ego/caution 803; native priority 252; cooldown 134; not evaluated 22; six starts,
46 active updates, two completed and one cancelled outcomes. Technical handoffs
can use other terminal reason paths, so histogram completion/cancellation bins
are not an exhaustive tally of flourish endings.

## Next priorities

1. Fix and live-validate recorder serialization, including target-ABI transport
   and semantic validation, before trusting automatic full-state summaries.
2. Diagnose/broaden legal precision-defense admission using reliable data; merely
   changing powershield timing would not address this run's zero attempts.
3. Review dance-to-wavedash coordination: two quick handoffs show precedence
   working, but may waste motion/interrupt personality. Measure usefulness rather
   than treating a landing acknowledgment as a winning conversion.

Raw log, manifests and generated reports remain under the capture directory in
`build/showboat/recordings/`. No raw runtime data or binaries are committed here.
