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
retained; other endpoints had host-only coverage at that checkpoint.

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
top platform's left edge (2). At that checkpoint the top right endpoint and
starts from Ottotto itself remained host-only. The sample contained 156 Ottotto and 263 OttottoWait
frames. It is not a reliability or strength estimate.

Second frames SHA-256:
`2b3ae93ec93ade61a40e8fe0529ec69d52a8bdffceebe8287382dcedcadf712c`.
Again, all four spend journals stayed unchanged. These two runs preceded the
parent integration of the separate Sudden Death menu fix.

The first four audited matches in later mixed cohort
`batch-17fa1c8b61fb4a2988cc42fb73e62b06` supplied 21 independently checked
successful OttottoWait escapes across all six platform endpoints. Left outer /
inner counts were 3/2, right inner / outer 1/5, and top left / right 8/2. One
interrupted random-policy attempt remained separate. Raw checks require the
source motion 246, actual directional input, native movement with at least six
units inward on the same platform, positive directional ground velocity and
observed neutral release. Each recording matched its passing cohort audit hash.

Both new top-right cases came from heuristic match
`match-c3f87b6851fd4d46b83017c405eebc97`. At source frame 2458, x=18.800001;
native Dash at frame 2463 reached x=12.440001, with neutral observed at 2464.
At source frame 10893, the same starting x led to Dash at 10899/x=11.140001
and neutral at 10900. This fills the top-right native endpoint gap. Starts
from Ottotto (245) itself still have host-only coverage.

Private extracted evidence SHA-256:
`9d551b7461aa5f9a04156d818038f81200d13f798adbf59a150cfce80bf89286`.
This read-only extraction uses existing paid/free recordings; it makes no new
provider or emulator call and does not claim full platform navigation.
