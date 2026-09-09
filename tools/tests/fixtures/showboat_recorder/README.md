# Recorder host fixtures

`test_showboat_recorder.py` builds the unmodified production recorder as a
separate C translation unit under debug 0/1 with ASan/UBSan. Native enums, the
complete `CpuFighter`, and read-only helper bodies are extracted from this
checkout; `Fighter` and external game services are explicit typed host stubs.

Every recorder call checks the entire stub Fighter storage and extracted CPU
storage for writes. Cases cover schema/finite formatting, post-input values,
events/reasons, periodic/change emission, gaps, flush accounting, all slots,
identity/spawn/context/clock changes, eligibility and freed-token teardown.
Repeated-clock updates verify independent flush batch IDs and the one-sample
cap. Sample reasons reflect the final branch values without extra histogram
counts. A CLI seam test passes actual C-produced records through the analyzer,
including repeated-clock batches, lifecycle splits and incomplete coverage.

A separate PPC clang syntax-only check includes the real native headers. It does
not replace an MWCC build or prove retail ABI, native physics, live hook ordering,
logging performance, complete match coverage or runtime action success. These
tests never launch Dolphin or modify its assets, profiles or active virtual DOL.
