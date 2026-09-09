# Recorder v2 repair: avoid the mixed-varargs boundary

The two v1 playtests produced syntactically valid but semantically corrupted
snapshots. A successful host libc printf test was insufficient validation for
the retail PPC formatter/ABI. This repair changes only mod-owned serialization,
analyzer validation and supporting checks/docs; not gameplay policy or inputs.

## Native evidence

Read-only inspection compared relevant old ELF instruction ranges with the
preserved virtual DOL (`690249dfe765ebdfefff6eb861df691c92cc2aca`). In the old
inlined sample call in `ShowboatRecorder_Frame`, the caller placed self stocks
at SP+0x18, passed self shield (the eighth double) in f8, left SP+0x1c unused,
and placed self flags at SP+0x20 (store at 0x803c999c). Rival spawn/kind/motion
followed at SP+0x24/+0x28/+0x2c.

The native OSReport overflow cursor starts at caller SP+8. Its `__va_arg` path
consumes register-resident doubles without advancing/alignment-adjusting that
cursor. After stocks it therefore expects flags at SP+0x1c and rival
spawn/kind/motion at SP+0x20/+0x24/+0x28. This is a concrete caller/native-reader
layout disagreement consistent with the observed flag garbage and rival motion
reading a kind value. It does not prove which formatting path Dolphin executed
or authorize reconstructing old rows by shifting fields.

Relevant sources: `src/Runtime/__va_arg.c`, `src/MSL/printf.c` (floating conversion
va_arg), and `extern/dolphin/src/dolphin/os/OSError.c`. Do not patch these retail
runtime files: that would expand risk beyond the observer and violate isolation.

## New wire format

All new records declare `v:2`. Integer-only begin/gate/end records retain their
fields. Samples add `float_encoding:"ieee754-binary32-hex"`. In both 13-field
fighter arrays, indices 3–9 and 11 use eight lowercase hexadecimal digits in
JSON strings representing the exact observed IEEE binary32 word. Other fields
remain JSON integers. The analyzer normalizes these words back to numeric floats.

The sample writer:
- Uses a private 1,024-byte stack buffer and checked appends, reserving NUL.
- Converts integers manually, including unsigned-wrap handling of INT_MIN.
- Uses memcpy from float storage into u32, then numeric nibble extraction; no
  aliasing cast, host-byte-order string dump, quantization or floating varargs.
- Sends only `OSReport("%s", buffer)` after the complete record is constructed.
- Publishes no partial line on overflow and leaves a gap for the next valid row.
- Keeps finite filtering, identity validation, timing, probes and input placement.

A conservative field-width bound is 751 bytes including newline/NUL, below the
fixed capacity. The bound does not replace executable overflow/canary tests.
Native printf's conversion scratch size is not a plain-string length limit.

## Validation requirements

- Every integer and all 16 float positions round-trip distinct sentinels.
- Exact bit patterns for signed zero, subnormal, minimum normal and maximum
  finite values; reject NaN/infinity on observation and decoding.
- Sample OSReport calls must use literal `%s`, never numeric or float varargs.
- Forced buffer exhaustion publishes nothing; exact-fit/one-short handling and
  later coverage-gap behavior are tested without production test-only hooks.
- Existing whole-Fighter/native-CPU immutability and lifecycle tests stay intact.
- Actual C wire output passes through the updated CLI, not a relabeled v1 fixture.
- Old captures remain preserved; invalid v1 fields are rejected and v1 sample
  statistics must not become trusted merely by filtering implausible rows.
- MWCC build, real-header syntax, warning matrix, disabled native hooks and exact
  recorder-off DOL comparison remain required. The verifier requires the v2
  encoding marker, so an old recorder-enabled DOL no longer passes as repaired.

## Static audit of the rebuilt target

The inspected v2 DOL is 4,515,936 bytes, SHA-1
`27db34f9111d37f01ebf83be4c78d9233fef06bb`. Linked ELF SHA-1 is
`a33387ef4f1c6cf33eb643c95625791f35e3bab2`; mapped file-backed sections match
the DOL. Actual CodeWarrior target instructions, not just host C, show:

- At `SR_Emit` call VA **0x803CABD4** (DOL offset 0x3C77B4), r3 addresses the
  literal `%s` at 0x804EE02C and r4 addresses local text at SP+0x5C.
- CR bit 6 is cleared before the branch to `OSReport` at 0x80345708. There are
  no floating/mixed sample varargs or sample overflow-area arguments.
- SR_Emit allocates 0x480 stack bytes, tests its overflow latch before printing,
  and contains no FP instructions. SR_FighterText copies each of eight float
  fields as four bytes and extracts nibbles with integer instructions.
- Begin/gate/end remain integer/pointer layouts; their formats only change v1
  to v2. No generic runtime, native AI hook or controller code was repaired.

Local detailed evidence/reproduction commands:
`build/showboat/recorder-v2-target-audit.txt`. This is a static target audit, not
an executed retail printf round trip or performance measurement.

## Completed offline verification

**393 tests pass** (235 retained/main, 52 recorder, 87 analyzer, 16 capture,
three configuration/verifier). The 52 recorder tests include thirteen raw-C-output
CLI scenarios, every float/integer sentinel, literal-string sample transport,
nonfinite rejection, exact-capacity/overflow and subsequent gap recovery. The
analyzer rejects malformed v2 encodings/mixed versions/impossible fields and
quarantines all v1 sample metrics, even after invalid rows are filtered.

Both existing real captures were reanalyzed into new `quarantined-report.*`
files, leaving previous artifacts intact. The 1,642/1,660 invalid rows are rejected
and the remaining 102/118 plausible v1 sample-shaped rows stay quarantined. No
trusted v1 sample metrics remain; 7,324 integer-only gate updates per tactic are
retained in each capture with coverage caveats.

MWCC build/verifier and 24 module warning configurations pass. Six disabled
native hooks remain byte-identical to C-stick; recorder-off reproduces the prior
ego DOL exactly (`0643071c098d78ab6d3339e3cc931647436b3594`). The v2 build was
restored afterward and its decisive linked/DOL instructions rechecked. Stock
DOLs, the existing virtual-disc v1 DOL and controller mapping remain unchanged.
Dolphin stayed closed throughout repair work. No gameplay tuning was included.

Offline validation and target code inspection do not substitute for the retail
execution path or measure runtime overhead. No emulator launch was part of the
offline repair work.

## Subsequent approved live validation

The tester then explicitly approved a new launch and shutdown. The
[first v2 live review](showboat_recorder_playtest_3.md) accepted 2,760 records with
zero rejected rows: exact finite float encodings, valid flag masks, stable
Falcon/Kirby identities and coherent changing motions. Independent legacy
wavedash positions agree with decoded v2 values. The old corruption did not
reproduce in this capture. Sparse startup/tail coverage and missing Kirby-specific
motion names remain distinct limitations, not evidence of the former ABI fault.
Dolphin exited 0 and is closed; any further launch requires fresh readiness.
This is a live integrity pass for this capture, not an overhead benchmark or
universal proof of every future snapshot. Historical v1 samples remain quarantined.
