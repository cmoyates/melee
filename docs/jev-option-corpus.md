# Keep option and atomic corpora separate

The private semantic corpus now accepts an explicit candidate profile:

```sh
uv run --project agent melee-agent corpus build --profile approach-jab-v1 --source-limit 12 --maximum-states 5000
uv run --project agent melee-agent corpus validate CORPUS_ID
```

The default remains `grounded-tactical-v1`. Source selection requires the same
declared profile, and direct generation rejects a mismatched source. At least
three compatible completed sessions are required; an insufficient option corpus
cannot be filled with atomic recordings. Each case, manifest and report carries
the profile, and the manifest binds its ordered candidate catalog. Compiler and
source hashes, episode-level splits, prior-frame history and source recompilation
checks remain required. Historical corpora retain their files and matching
checkout requirement; a changed compiler cannot silently validate them.

The explicit paid evaluation command takes its profile from the validated
corpus and uses that profile's live candidate descriptions. It checks profile and
candidate compatibility before creating a client or reserving spending. Its
manifest/summary identify the profile and preserve the exact criteria. This
change makes no provider call on build or validation and does not trigger an
evaluation automatically. Recorded model replies still refer to their own source
frames and representation; they are annotations, not labels proving an optimal
decision or a successful application.

All 349 host tests pass. Tests cover separate source selection, exact option
recompilation, insufficient compatible sessions, forged/rehashed profile data,
CLI propagation and a simulated provider payload containing the option's live
description. Real option corpus validation is pending the third complete source
session. Report actual episode/split counts; three sessions alone do not imply
that every split is populated or that the corpus is a strength benchmark.
