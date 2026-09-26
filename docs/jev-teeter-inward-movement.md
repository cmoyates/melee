# Move inward from native teeter states

The incomplete baseline `match-76888a9288954c258cda41975e014a5c` retained Fox
on the left platform at x=-19.950454711914062, y=27.20009994506836, in native
motion 246 (`OttottoWait`). Geometry permitted an inward destination, but the
motion-start whitelist rejected teeter states, leaving neutral as the only
tactical candidate. This is separate from the previous edge-geometry defect.

`src/melee/ft/kinds/ftCommon/ftCo_Ottotto.c` routes both `Ottotto` (245) and
`OttottoWait` (246) through movement input checks. Permit only the existing
six-unit `move` skill from these states, only when the known support geometry
allows an inward escape that increases clearance. The normal grounding, damage,
commitment and observation checks remain. The states are not added to the
general grounded-action set or made legal for attacks, options, walk, jump or
shield by this change. Outward and unsupported moves remain refused.

358 host tests pass. Added coverage mirrors both states across all six platform
endpoints, rejects outward/unknown/airborne/damaged/interior/unrelated-motion
cases, and checks fallback and heuristic selection against the retained native
geometry. Native teeter-to-movement confirmation is pending. This change does
not establish complete platform navigation or playing strength.
