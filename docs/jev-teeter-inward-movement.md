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
geometry.

Free native match `match-5ac325db19fe4965a50367fae840f879` completed in 364.32
seconds, losing 0-4. All 21,001 game frames replayed exactly; raw integrity,
source identity, rules/result and owned cleanup passed. The recording includes
12 Ottotto and 58 OttottoWait frames. At frame 7556, Fox chose inward movement
from OttottoWait on the left platform's inner edge (x=-20). Raw motion changed
to Turn at 7557 and Dash at 7558; x reached -25.760002 at 7561. Hitlag at 7562
interrupted the skill before its six-unit acknowledgement. This proves native
teeter-to-inward movement, not a clean completed escape. The interruption is
retained, and other endpoints still have host-only coverage.

Frames SHA-256:
`aa0dc5a48fa2bb9dc60a16f58b8bfc93ab5042968ccbe43f19bf825c71785346`.
All four spending journal hashes remained unchanged. This change does not
establish complete platform navigation or playing strength.

Second free match `match-e22d1b6ab4d94680970d12c14b68c256`, using the heuristic,
completed a 0-3 loss in 409.86 seconds. All 23,720 frames replayed exactly with
raw integrity, source, rules/result and cleanup checks passing. Twelve movement
starts came from OttottoWait: eleven completed with independently checked
six-unit native displacement, directional velocity and observed neutral release;
one lost ground support and stayed aborted. Clean completions covered the left
platform's inner/outer edges (2/3), right platform's outer/inner edges (3/1), and
top platform's left edge (2). The top right endpoint and starts from Ottotto
itself remain host-only. The sample contained 156 Ottotto and 263 OttottoWait
frames. It is not a reliability or strength estimate.

Second frames SHA-256:
`2b3ae93ec93ade61a40e8fe0529ec69d52a8bdffceebe8287382dcedcadf712c`.
Again, all four spend journals stayed unchanged. These two runs preceded the
parent integration of the separate Sudden Death menu fix.
