# Explicit approach-jab tactical profile

The experimental `approach-jab-v1` candidate profile adds the bounded option
from #63 to the existing eight atomic labels. It is selected explicitly for
Jev, delayed-fake, heuristic-tactical or random-tactical runs. The default
`grounded-tactical-v1` profile keeps its eight choices. Historical selector
modes and non-tactical diagnostics reject the experimental profile.

All three selectors use the same ordered candidate function and the same
local option/reflex/skill executor. Random selection remains uniform over the
currently legal catalog. The heuristic prefers an immediately legal atomic
attack, otherwise the approach-jab option when available, otherwise its existing
movement/neutral fallback. Jev gets a bounded description of the option and
chooses it through the existing Decisions interface. Its identity, age,
confidence, context and current-legality checks remain intact; an option label
cannot enter the default profile through a forged reply.

Launch, summary, local/async/provider reports, provider configuration hash and
sealed incident provenance record the profile. Local and async replays restore
it and reject mismatched identities. The raw policy audit reports accepted
options separately from their movement acknowledgements, jab acknowledgements,
contacts and completions. A choice that aborts is not a completed attack.
An option selected while farther away may start directly with a freshly legal
jab if the opponent has approached by delivery; the controlled mechanical
scenario still requires a movement before the jab.

The existing frozen corpus compiler/evaluator remains explicitly atomic. It
skips experimental-profile runs and refuses explicit attempts to relabel one
with the atomic catalog. Existing corpora and recordings require their pinned
source checkout for exact replay, as before.

```sh
uv run --project agent melee-agent capture --policy delayed-fake --profile approach-jab-v1 --duration 180
uv run --project agent melee-agent match --policy heuristic-tactical --profile approach-jab-v1 --duration 600
uv run --project agent melee-agent inspect RUN_ID --policy-evidence
```

Paid testing additionally requires the existing `jev` policy, an explicit
remaining-budget ledger and request cap. Selecting a profile does not create
or reset a budget. No new paid call was made to implement or test this slice.

All 331 host tests pass. The deterministic delayed-choice fixture waits 500 ms before accepting the
option, then observes two movement/release commitments and one acknowledged
jab with neutral completion. All 43 frames reproduce exactly from a sealed
incident without network or emulator. Other tests cover shared candidate
sets, rejection under the atomic profile, local option replay, explicit CLI
and provider payload propagation, changed profile identity and forged raw
child evidence. These are host/integration results, not live tactical benefit.
Fresh live option captures and paid validation remain pending.
