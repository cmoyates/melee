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

Fresh live escape validation is pending. This slice does not implement dropping
through platforms, directed platform jumps or complete navigation between
support surfaces, and it does not establish improved playing strength.
