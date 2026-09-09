# Recorder host fixtures

`test_showboat_recorder.py` builds the unmodified production recorder as a
separate C translation unit under debug 0/1 with ASan/UBSan. Native enums, the
complete `CpuFighter`, and read-only helper bodies are extracted from this
checkout; `Fighter` and external game services are explicit typed host stubs.

Every recorder call checks the entire stub Fighter storage and extracted CPU
storage for writes. All records must be schema v2; samples require
`float_encoding:"ieee754-binary32-hex"`. Raw self/rival float positions are strictly
validated as eight lowercase hex digits encoding finite binary32, before any
numeric assertion uses a decoded copy. Independent sentinels verify every field
of both fighters and all integer payloads, with sixteen distinct float bit
patterns including signed zero, minimum subnormals and maximum finite values.
The OSReport stub consumes sample output only through `%s` plus a pointer and
rejects numeric sample formats; a source assertion also forbids extra arguments
that C varargs cannot count at runtime. Begin/gate/end retain integer formatting.

Cases cover schema/finite formatting, post-input values,
events/reasons, periodic/change emission, gaps, flush accounting, all slots,
identity/spawn/context/clock changes, eligibility and freed-token teardown.
Repeated-clock updates verify independent flush batch IDs and the one-sample
cap. Sample reasons reflect the final branch values without extra histogram
counts. A CLI seam test passes unchanged raw C output through the analyzer (no
JSON reserialization or float decoding), including bit sentinels, nonfinite-sample
recovery, repeated-clock batches, lifecycle splits and incomplete coverage.

Overflow tests change only `SR_LINE_CAP` in temporary production-source copies,
compiled under both debug settings with ASan/UBSan. A 64-byte cap emits no samples
or partial records while retaining begin, all gate batches and end. Exact-fit
and one-byte-short caps test newline/NUL boundaries. Controlled integer payload
growth then shrinking in the same segment proves failed emission publishes
nothing and the next unchanged sample recovers with `gap:1`, without production
test hooks. Normal fixture builds still compile unmodified production source.
Disabled builds retain no-argument-evaluation and dependency checks.

Separate PPC clang syntax-only checks include the real native headers and the
actual codec (`ppc_codec.c` checks big-endian types, buffer size, sentinel bit
transfer, integer boundaries and the bool emission interface). They do
not replace an MWCC build or prove retail ABI, native physics, live hook ordering,
logging performance, complete match coverage or runtime action success. These
tests never launch Dolphin or modify its assets, profiles or active virtual DOL.
