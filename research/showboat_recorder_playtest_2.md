# Second recorded manual playtest — limited, corroborated review

Capture: `20260909T142236.722805Z-bd99a2b39c974eb28f7987d33ed183d1`.
Launch repository HEAD: `37d88f548` (documentation-only change since prior run).
**Same gameplay/recorder binary as the first capture:** SHA-1
`690249dfe765ebdfefff6eb861df691c92cc2aca`, 4,506,976 bytes.
User explicitly approved this test with the known telemetry limitation, then
requested analysis and shutdown. Dolphin exited 0; metadata and raw log were
preserved. No relaunch, gameplay changes, builds or recorder repair occurred.

## Reliability

The unresolved mixed-format snapshot defect recurred: **1,660/1,778 snapshots**
have impossible self flag values. Withhold automatic damage/stock totals, rival
state/identity, motion-duration/position/native-priority aggregates, winner and
KO attribution. Do not reconstruct corrupted fields by guessing offsets.

This review uses separate legacy diagnostics and integer-only gate/end records;
selected event-header counts agree with the separate diagnostics. Gate sums were
checked against each segment's end totals for all five tactics. A restricted
`reviewed-summary.json` is saved alongside the raw capture, rather than presenting
automatic mixed-snapshot statistics as authoritative.

There are 2,819 structured records, five segments and 7,324 observed updates per
tactic. The native clock spans 0–7200 on Battlefield in normal VS Time. Repeated
startup clock values mean update totals are not unique frame counts. Segments
are not matches or attributed KOs.

## Confirmed custom behavior and comparison

| Evidence | First capture | Second capture |
|---|---:|---:|
| Custom shield onsets / fighter powershield contacts | 0 / 0 | **1 / 1** |
| Custom grab-motion acknowledgments | 2 | 1 |
| Custom wavedash starts / landing acknowledgments | 3 / 3 | 0 / 0 |
| L-cancel input samples | 5 | 9 |
| Offstage mockery starts | 3 | 1 |
| Neutral dance starts | 3 | 0 |
| Custom KO-taunt starts / acknowledgments | 0 / 0 | 1 / 0 |
| Custom aerial-intercept starts / acknowledgments | 0 / 0 | 0 / 0 |

These are custom-layer observations, not totals for native attacks, grabs,
shielding or movement. Grab acknowledgments are not confirmed hits. L-cancel
samples are not confirmed lag reduction. One powershield does not establish a
success rate, general precision or improved strength.

### Powershield: admitted and confirmed this time

Separate legacy messages at 23:45.770–23:45.788 record:
- `hardshield onset queued`
- `fighter PS contact`
- `guard acknowledged ms=181 (not contact)`
- ego `84 -> 92: verified powershield contact`

Event bit 32 occurs once at native frame 2607; the integer-only defense histogram
contains one STARTED and one SUCCESS. Contact evidence is distinct from merely
entering GuardReflect or displaying a shield animation. The corrupt rival data
cannot reliably identify the blocked opponent move.

This revises the prior run's narrow finding: admission is not impossible and the
contact/reward path can work in live play. Frequency remains selective; more data
is needed before treating it as reliable high-level defensive coverage.

### Personality and ego

- An offstage dance started at ego 66 and completed its 16-update sequence.
- A subsequent opponent death event raised ego 66 -> 88. The bot started its
  certified KO-taunt routine but cancelled with `couldn't settle safely for taunt`.
  No custom taunt acknowledgment occurred. That branch rejects an unready stance
  after its bounded settling allowance or loss of permitted movement; it does
  not force Wait or shorten native animation lag. Do not infer the exact failed
  stance predicate from corrupted snapshots.
- No neutral dance or custom wavedash began this round.
- Legacy ego values span 28–100. Ego reached 100 late in the match, after another
  new-life penalty, rather than around the middle as in the first capture.

## Gate accounting (observed updates, not opportunities)

Defense: 7,164 native-priority rejections (**97.8%** of all logged updates), 134
combined fresh-script/input/stance/shield/items rejections, two target/lifecycle,
one planner/window rejection, 21 not evaluated, one start and one success.
Most gameplay updates are not defensive opportunities; these counts are not
missed-block totals and do not isolate the atomic cause of the combined gate.

Movement: 6,738 broad admission rejections (includes eligibility, priority,
ground/input/VM checks), 563 planner/window rejections, 23 not evaluated. Zero
starts: this was admission declining, not failed wavedash execution.

Combat: 5,132 planner/window rejections, 1,809 physical/state, 360 input/script,
20 not evaluated, one start, one active update and one completion. No custom
aerial-intercept acknowledgment. This cannot quantify missed guaranteed punishes.

Personality: 3,160 geometry/window, 1,487 no candidate, 1,253 physical/state,
1,156 ego/caution, 225 native priority, three cooldown, four not evaluated;
two starts, 32 active updates, one completion and one cancellation. Ego/caution
rejections rose from 803 to 1,156, but were not the only limiting condition.

## Next priorities

Recorder serialization and target-runtime validation still come first. Then
inspect admission frequency and taunt settling using reliable state traces.
Keep the distinction between a functioning but rare shield path and universal
blocking. The unchanged build plus differing encounter conditions do not support
an improvement/regression or win-rate claim from these two matches.
