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
description.

Real corpus `corpus-6b5b343a287942c39aa5e1eefe4ed195` contains 4,959 states from
three option-profile episodes: 3,303 training states and 1,656 held-out states.
There is no tuning episode. Every state recompiled exactly with network and
process creation blocked. Source selection retained one paid match and two free
delayed-fake sessions; sparse annotations include twenty provider and 99
simulated replies on sampled delivery frames. No new evaluation was run.

- States SHA-256: `2ef5cf8c466025c573460bb331acccb31f3cdddcacbb48bcd94ae4fff0634f12`
- Manifest SHA-256: `19c5f95abfc0a8a9dff3a75de29512a878b0ae0f0cd8ea88b53a84ca509f84d9`

The third source, `match-e015832a18724b7ba302789ba510905c`, completed a free
327.60-second match and lost 0-4. All 18,784 game frames replayed exactly; raw
integrity, decision/option audits, source identity, stock rules, final result
and owned cleanup passed. Six options were accepted: four completed (two after
walking, two immediate), one hitlag interruption and one shared-support change.
There were five walking acknowledgements, four jab acknowledgements and three
contacts. The completed jab without contact remains separate from the three
hits. No provider was contacted and all four spend journal hashes stayed fixed.

Frames SHA-256: `77b97d6d9986ead2b39280c0b64514af6472dbab55d06c299dd0e6387a270424`.
Private exact replay: `incident-c00bf42b90dc4c0fbde249b9730f50eb`.
This adds native delayed-fake walking execution evidence after the earlier paid
probe; it does not retroactively change the order or outcomes of those tests.
Three source episodes do not establish a complete calibration split or playing
strength, and the extraction corpus supplies no optimal-action labels.
