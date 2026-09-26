# Continuing a bounded Jev experiment

Each experiment retains an immutable deadline, request count, input-token limit
and dollar limit. When further work is authorized under an existing total dollar
allowance, `provider continue-budget` permanently seals one parent and assigns
only its conservatively unspent dollars to one new experiment:

```sh
rtk proxy uv run --project agent --no-sync melee-agent provider continue-budget \
  --from-directory build/jev/PARENT \
  --directory build/jev/CHILD \
  --deadline-utc YYYY-MM-DDTHH:MM:SSZ \
  --max-requests 1100 --max-input-tokens 3000000
```

Stop owned provider workers before this operation. It makes no HTTP calls and
does not accept a new dollar allowance. The operator must explicitly choose the
new experiment's finite request, token and deadline bounds. Those bounds are
local to the new experiment; existing headers and past quotas are not rewritten.
This is an authorized experiment transition, not an automatic retry when a
provider command runs out of budget.

The conservation rule is:

`parent accounted dollars + child maximum dollars = parent maximum dollars`

Accounted dollars include settled charges and the entire reservation for every
unknown response. Sealing prevents both new parent reservations and later
settlements that could refund those unknown charges. Repeating the operation
with identical arguments reuses the same child ledger, including its existing
spend. A different destination or changed limits are refused. Applying the same
rule across a chain preserves its original dollar allowance.

The parent journal's existing bytes remain intact; an appended seal specifies
the sole child destination and limits. Parent reservation and continuation calls
share the existing file lock. Child initialization occurs before that lock is
released, and the child retains a private `funding.json` linking the sealed
parent's hash and accounted cost. An existing destination cannot acquire fresh
funding through this operation.

If initialization stops after sealing but before a child journal exists, the
operation fails closed. It cannot create a replacement child on retry, because
a missing journal could also mean previously spent history was lost. An empty,
corrupt or symlinked child ledger also fails closed. Do not delete or recreate
these artifacts to regain a quota; preserve them for investigation. If the child
journal exists and is valid, an identical retry can finish its provenance file
without resetting spend.

Host tests cover uncertain charges, competing reservations/destinations, repeated
continuations, multiple generations, altered arguments, invalid/occupied paths,
reservation overruns, incomplete initialization and forged journal tails. They
use simulated ledgers and make no provider calls. Existing corruption,
deadline, concurrency and rounding tests remain in place.
