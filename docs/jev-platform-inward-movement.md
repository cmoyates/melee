# Inward movement from known platform edges

The full grounded Jev experiment `match-5e78a86dd6a64cc193a43cc139a70c26`
found Fox standing on the left platform at x=-19.99574, y=27.20010. Support
recognition was correct, but the catalog offered only neutral, jump and shield.
A six-unit move left would end near x=-26, outside the ordinary eight-unit
interior margin ending at x=-28, while moving right would approach open air.
Both directions were refused. The fallback repeatedly chose neutral.

The ordinary destination margin remains eight units. A move starting outside
that interior region may additionally proceed toward the support center when
its six-unit destination lies strictly inside the physical support interval and
is closer to the center. Outward moves and moves from unknown support still
fail. Native grounded/actionable state and all other primitive checks remain
required. This uses the existing bounded movement primitive and ordinary inputs.

When approach is unavailable, the asynchronous fallback and new tactical
heuristic may select a legal retreat before neutral. Since both use the shared
candidate checks, this allows an inward edge escape without permitting an
outward step. Historical attack-focused selector mode preferences stay intact;
the common mechanical legality improvement is pinned by source hashes.

All 309 host tests pass. New coverage includes inner and outer endpoints of
both side platforms, both top-platform endpoints, the retained native sample,
the unchanged normal interior margin, outward refusal, unknown/airborne/damage
refusal, and actual inward fallback/heuristic selection.

Live capture `match-bc351343464341e1a829d6c94b8cd54e` ran for 300 seconds
on Battlefield against Mario CPU 3 using the free delayed-provider fixture.
All 17,394 gameplay frames passed raw integrity and exact semantic/controller
replay with unchanged launch sources. Seven moves used the newly allowed
inward path: five on the right platform and two on the left. Six observed the
required six-unit displacement, native ground movement, directional input and
neutral release; one was interrupted by hitlag before acknowledgement.
The exact previously trapped left-platform position, x=-19.995738983154297,
escaped to x=-26.35573959350586 at frame 15423 and completed release at 15424.
The mirrored right inner edge and right outer edge also completed. The top
platform and left outer edge have host coverage but were not exercised live.

The partial match ended at Fox 1 stock, Mario 4; no final result is claimed.
There were zero observation gaps, recorder losses or replay errors; controllers
neutralized and owned processes stopped. No paid provider was contacted.
Frame SHA-256: `54593c50c4b48c45a8cfcb50b8d82f1da664f76657be65d3a8654dca87be2ab1`.
Packet SHA-256: `6175d3dd4a847d75a2600eba4399b7b14d557b73561bf201693f3bb52b9de4f6`.
Private raw motion diagnostics are retained alongside the full replay audit.

This slice does not implement dropping
through platforms, directed platform jumps or complete navigation between
support surfaces, and it does not establish improved playing strength.
