# Read-only behavior recorder (schema v2 contract)

Goal: explain observed custom AND native behavior after a playtest, including
why tactics declined. No gameplay/controller writes, timers repaired, native RNG,
allocations, network, model runtime, or claims that observed inputs guarantee hits.
Recorder work does not launch Dolphin; launch/restart requires tester readiness.

## Transport and ownership

Optional `SHOWBOAT_RECORDER=1` (raw configure off, showboat helper default on).
Only mod sources change; existing native hooks remain the same. Disabled macros
must not evaluate arguments. Native C emits one-line JSON prefixed `SBREC ` via
OSReport. V2 snapshots use a checked 1,024-byte local string builder and one
`OSReport("%s", line)` call, with no floating-point variadic arguments. Overflow
publishes nothing and marks a coverage gap. Integer-only lifecycle/gate records
retain their existing transport. Dolphin timestamps/prefixes are transport, not
game-frame timestamps.
The launch helper archives each approved launch under an exclusive directory in
`build/showboat/recordings/`, preserving `runtime.log`, an immutable `launch.json`
written before execution, and final `metadata.json` with exit information. A
crash/SIGKILL can prevent final metadata but not erase launch provenance. No saves,
controller changes or original-disc writes. Log capture also preserves legacy
human-readable SHOWBOAT diagnostics.

Game-thread APIs (`showboat_recorder.h`, compile-out macros when disabled):
- `ShowboatRecorder_Begin(Fighter*)`: clear this update's tactic outcomes/events.
- `ShowboatRecorder_Reason(Fighter*, int tactic, int reason)`: last actual outcome
  for a tactic this update. Uncalled tactics stay NOT_EVALUATED.
- `ShowboatRecorder_Event(Fighter*, unsigned mask)`: OR explicit event bits.
- `ShowboatRecorder_Decision(Fighter*, int ego, int action, bool owns)`.
- `ShowboatRecorder_Frame(Fighter*, Fighter* live_target)`: after native VM and
  combat post-input overlay, before game input preprocessing; validates identities.
- `ShowboatRecorder_ResetSlot(int)`, `ShowboatRecorder_Suspend(Fighter*)`: end/
  flush observed segments without dereferencing saved owner/target pointers.

Tactic IDs: 0 personality, 1 combat, 2 movement, 3 defense, 4 lcancel.
Reason IDs: 0 not_evaluated, 1 no_candidate, 2 active, 3 started,
4 native_priority, 5 input_or_script, 6 physical_or_state, 7 target,
8 geometry_or_window, 9 cooldown, 10 ego_or_caution, 11 items,
12 completed, 13 cancelled, 14 budget, 15 success.
A reason is the actual instrumented branch/group, not necessarily one atomic
predicate. Report NOT_EVALUATED separately: another layer may own this update.
Never rerun a mutating planner just to explain its rejection.
Event bit masks: 1 taunt_ack, 2 punch_ack, 4 grab_ack, 8 aerial_ack,
16 wavedash_landing_ack, 32 custom_powershield_contact, 64 lcancel_sample,
128 side_b_veto (added with the native ledge safeguard; current allowed mask255).
Acknowledgment is not a hit; lcancel_sample is not successful lag reduction.
`side_b_veto` is only a controller-input rejection, not acknowledgment, recovery
or saved-stock proof. Snapshot input is after that filter; `owns`/intent retain
the earlier tactical meaning. The native follow-up VM is not rewritten.
This additive v2 bit requires the matching analyzer; older strict readers may
reject new safety-event rows. Existing v2 captures and float encoding are unchanged.

## JSON records

All new records: `v:2`, `type`, `segment` (monotonically increasing capture-local ID),
`slot` (0-based CPU player), `frame` (native gm_GetFrameCount).
Segments are observed intervals, NOT guaranteed complete matches. Identity,
spawn, frame rollback, stage/rules change or suspension can split them. EOF
without end is explicitly incomplete, not a loss/victory. No raw addresses.

`begin`: additionally `stage`, `mode`, `match_kind`, `target` (0-based),
`interval:12` (periodic snapshot maximum interval during observed continuity).

`sample`: additionally `ego`, `action` (HUD controller intent code 0..11),
`owns` (mod claimed VM for this update), `events` (mask), `gap` (0/1),
`float_encoding:"ieee754-binary32-hex"`, and `self`/`rival` arrays with exactly
these 13 logical fields:
`[spawn,kind,motion,anim,x,y,vx,vy,ground_v,percent,stocks,shield,flags]`.
The eight float fields at indices **3,4,5,6,7,8,9,11** are transmitted as exactly
eight lowercase hexadecimal characters in JSON strings, containing the native
IEEE binary32 bits (`"3f800000"` = 1, `"80000000"` = negative zero). Other fields
are JSON integers. `memcpy` into u32 plus numeric nibble extraction avoids aliasing
and host byte-order dependence. The analyzer decodes these to numeric values;
NaN/infinity encodings are rejected. No quantization, floating varargs, numeric
formatter or pointer values are used to encode these fields.
Flags bits: 1 airborne, 2 hitstun, 4 hitlag, 8 inactive, 16 held_item,
32 captured_or_thrown, 64 protected (read-only native protection query),
128 global_items_present.
`native`: `[priority,cached_attack,threat]`.
`input`: `[raw_buttons,lstick_x,lstick_y,cstick_x,cstick_y,ltrigger,rtrigger]`.
`reasons`: five final reason IDs at this sample, in tactic order. These values
provide local context, not extra histogram counts or reasons for unlogged frames.
These are CPU output channels BEFORE game preprocessing, not controller hardware
or opponent inputs. Both fighter observations are taken at the CPU hook, not an
atomic end-of-frame world snapshot.

Emit samples initially, at most 12 observed game frames apart, and on changes to
either fighter's motion/spawn/stocks/percent, native priority, mod action, raw
buttons/triggers, flags or explicit events. At most one sample per observed game
frame. No need to log every analog stick drift or passive shield drain. Frame
gaps are explicit and not interpolated as known behavior. Non-finite observations
must be rejected/marked rather than emitting invalid JSON.

`gate`: additionally `from` (first included native frame), `tactic`, `reason`,
`count` (observed CPU updates in this bin), `batch` (positive flush ID). Flush
nonempty bins at least every 60 observed updates and at segment end. Exactly one
reason per tactic per recorded update; last actual outcome wins. Unflushed EOF
tails are unknown. `batch` starts at 1 per segment and advances per nonempty
flush. Multiple CPU updates/flushes may share a native frame counter: counts are
observed updates, **not** unique frames or durations. Batch identity disambiguates
these flushes. The analyzer also accepts older v1 integer records without `batch`,
retaining ambiguity warnings. All v1 sample-derived metrics are quarantined,
including plausible-looking rows; they cannot become trusted by filtering out
obviously invalid samples.

`end`: additionally `reason` (fixed token), `observations` (segment total).
Flush gates first. An end is a recording lifecycle event, NOT match result.

## Offline reports

Stream parse prefixed records; validate bounded shapes/types/finite numbers,
versions and ordering; reject mixed versions within a segment, invalid encoding,
nonfinite float words and impossible fighter fields (including flags above 255).
Warn on malformed/truncated/missing rows and unfinished segments. For v1 or a
corrupt capture, Markdown withholds sample summaries and JSON trusted metric
fields are empty/null; bounded raw diagnostics are separate. Validated integer
gate/end accounting is retained with its own coverage caveats. Plain older SHOWBOAT logs have no structured coverage: say so rather
than inventing statistics. Never execute text from a log.

Report per-segment context/coverage, observed motion entries and native-priority
intervals (not guaranteed actual action totals), custom intents/acknowledgments,
known rejection counts, unknown/not-evaluated intervals, observed net percent
increases and stock changes, ego range, position/recovery context and a bounded
timeline. Damage/stock changes are not automatically attributed hits, kills,
combos or player wins. Do not count percent resets as healing/damage. Sparse
position snapshots do not prove useful wavedash displacement. Emit Markdown
and machine-readable JSON on request. No gameplay or emulator actions in analysis.

## Historical v1 offline checkpoint — superseded by live findings

364 host tests passed, including main hook ordering across recorder/debug variants,
actual C writer output through the analyzer, repeated-clock batches, Time matches
with zero stocks, and archive/source-file safety. Review found and corrected the
update-count versus unique-frame mismatch and finite-f32 parser-domain mismatch.
The reader retains explicit uncertainty rather than inventing temporal placement
for multiple updates sharing one native clock value.

The enabled MWCC build and isolation verifier pass; 24 module warning builds and
six disabled-hook byte comparisons pass. Recorder-off reproduces the preceding
DOL exactly; the enabled DOL is 4,506,976 bytes / SHA-1
`690249dfe765ebdfefff6eb861df691c92cc2aca`. Existing virtual-disc DOL and controller
hashes remained unchanged at that offline checkpoint. Subsequent
[first](showboat_recorder_playtest_1.md) and [second](showboat_recorder_playtest_2.md)
live tests exposed mixed-format corruption despite those tests. The v2 repair
replaces that serialization path rather than attempting to reinterpret damaged
v1 samples. The [first approved v2 live capture](showboat_recorder_playtest_3.md)
passes encoding/field checks with no recurrence of the defect; it does not make
historical v1 samples trustworthy. OSReport formatting/I/O may cost runtime: host tests do not establish
emulator speed, logging overhead or actual retail capture completeness.
