# Jev versus Laya: bounded zero-shot evaluation

Recommendation: keep Jev as the current provider. The tested Laya English
checkpoint is faster locally, but its untrained Melee behavior does not justify
adding another runtime or a fine-tuning project now. This is a deployment
recommendation from a small smoke evaluation, not a universal model ranking.

## Method

- Hardware: Apple M3 Max, 36 GiB unified memory; Laya on PyTorch MPS.
- Laya 0.3.20, torch 2.14.0, transformers 5.17.0; isolated temporary environment.
- Checkpoint: `convaiinnovations/laya`, revision
  `55cf4c4ebb4ebe31b2550e8bdf3bd21b99753851`. No task fine-tuning or temperature fitting.
- Select 12 evenly spaced validated requests from each of two retained Jev
  Battlefield captures, for 24 cases. Reconstruct original state, instructions,
  ordered candidates and request envelope; all 24 SHA-256 hashes match the
  original budget reservation records. Jev resolved model:
  `typesafe/jev-1.13-20260917`, provider TypeSafe.
- Run Laya on those states with its default 512-token context/192-token head,
  then with 2,048-token context/384-token head to avoid state truncation.
- Measure synchronized, warmed, sequential inference, excluding model load and
  the initial call for each mode. The retained Jev latency includes its network
  path and was measured while Dolphin ran. Laya ran offline without Dolphin;
  these timings are not a controlled hardware or emulator-load comparison.
- Separately run 12 predeclared simple comprehension checks: six stock-count
  comparisons, four explicit approach/retreat goals and two recovery/shield
  goals. These are authored sanity checks, not a gameplay benchmark. Only Laya
  was run on them; no corresponding Jev accuracy is asserted.
- Reverse candidate order on the first eight full-context cases. Repeat six
  sanity cases on CPU to check whether the observed failures depend on MPS.

## Results

| Measurement | Laya default | Laya full context | Historical Jev |
| --- | --- | --- | --- |
| Cases | 24 | 24 | 24 |
| Median latency | 78 ms | 114 ms | 423 ms |
| 95th-percentile latency | 91 ms | 158 ms | 515 ms |
| Truncated state cases | 24 | 0 | Not measured with Laya tokenizer |
| Neutral choices | 24 | 21 | 5 |
| Approach choices | 0 | 0 | 12 |
| Jump choices | 0 | 2 | 3 |
| Shield choices | 0 | 1 | 4 |

The raw states contain 488–523 Laya tokens. The default configuration retained
as few as 333. Both Laya modes agreed with Jev on five of 24 choices. Agreement
is not accuracy, and frequent neutral choices alone do not establish errors.

Laya answered six of twelve sanity checks correctly. It selected Fox in all
six stock comparisons, including when Mario had more stocks and when stocks
were equal. It approached for both explicit retreat goals. The two recovery
and shield checks passed. CPU repeated exactly the same choices and rounded
probabilities on the six selected cross-checks, including failures.

Reversing candidate order changed seven of eight full-context tactical answers.
This and the simple comprehension failures are stronger reasons to avoid a
provider switch than disagreement with Jev. They also warrant caution about
expecting arbitrary personality instructions to work without domain adaptation.

No live Laya gameplay, win-rate comparison, specialist-checkpoint sweep or
training was attempted. Existing Jev choices are not ground truth. The archived
menu contains five movement/defense skills, so this does not evaluate combat
selection or established personality control for either model.

The loader warned about clamping an invalid temperature for 11+ options. This
experiment uses at most five options and does not attribute its failures to
that unrelated bucket. Rounded output probabilities sometimes differ from a
sum of one by 0.0001; a future adapter would need an explicit rounding-aware
validation contract rather than inheriting the existing Jev tolerance blindly.

## Artifacts and scope

Private reproducible inputs, outputs, checkpoint metadata and scripts are in
`build/jev/laya-comparison-20260926/`: `cases.json`, `model.json`,
`results.jsonl`, `sanity-cases.json`, `summary.json`, `cpu-check.json`, and
`jev-laya-*.py`. Case-file SHA-256:
`d0d17f5fdaa2c62b3b7ecea5dd596f145b838de0be23909eff74582e38d65070`.

No new OpenRouter calls occurred. The existing ledger remains at 312 requests,
$0.013222398 reported and $0.019222398 conservatively accounted, including one
uncertain reservation. Its expired deadline was not changed. Active bot code,
dependencies and provider selection were not modified; model files remain in
ignored experiment storage. Continue the Jev foundation and revisit Laya only
if we choose to invest in domain adaptation or a later checkpoint passes these
same checks without it.

References: [Laya release](https://pypi.org/project/laya/0.3.20/),
[official project](https://github.com/NandhaKishorM/laya),
[model card](https://huggingface.co/convaiinnovations/laya).
