# Follow a match through Sudden Death

Issue #60 follows the failure in `match-5e78a86dd6a64cc193a43cc139a70c26`.
Regulation reached frame 28800 with four stocks each. Melee emitted TIME,
then started Sudden Death while the scene still reported IN_GAME. The game
frame reset to -123, stocks became one each and damage became 300%. The old
worker treated that reset as a frame rollback and stopped; it also counted
the rejected frame before the controller accepted it. The regulation replay's
placement was not the eventual contest winner.

The worker now requires a new native GameStart, a completed regulation TIME
replay, tied positive stocks at the time limit, the expected Battlefield
Fox/Mario CPU 3 settings, and the native one-stock/300% Sudden Death start.
Only that verified boundary starts another recorded episode under the same
match number. New episode identity resets frame, life, skill, semantic history
and delayed-response validity. Other backward frames still stop the run.
Observation counters advance only after the controller accepts the observation.

Each recording episode has a phase, parent match number, starting rules and
native GameStart index. The regulation segment is marked continued, with no
final winner. Only the final verified result increments completed matches.
The supervisor verifies one replay per segment and the same parent match
through the transition. A requested match cannot finish merely because a
regulation replay has a TIME placement. The final Sudden Death replay must
contain GAME. Partial captures remain explicitly partial.

Observation schema 5 permits an untimed segment: time limit and remaining
time are null, starting stocks are one, and frame-derived elapsed time starts
again within that segment. CompactObservationV2 exposes timer enabled, phase
and `elapsed_scope: current_segment`; it does not invent an eight-minute
Sudden Death countdown. Historical schema 4 recordings remain readable, but
exact policy/corpus replay still requires its original source checkout.
Compiler identity also pins the live/raw/replay adapter modules.

Native rule evidence is in `gm_SetupSuddenDeath` (`src/melee/gm/gm_1B03.c`),
the versus lifecycle (`src/melee/gm/gmvsmelee.c`) and `StartMeleeRules`
(`src/melee/mn/types.h`). The recorded GameStart rule byte is 0x32 in regulation
and 0x30 in Sudden Death: timer enabled is mask 0x02. The original retained
Sudden Death replay's first three frames were independently decoded through
the replay adapter as untimed, one-stock, life-generation-one observations.

All 316 asset-free host tests pass. Coverage includes valid and invalid transitions, wrong rules/start
identity, parent-result accounting, untimed semantics, stale response refusal,
and the actual worker across both a verified transition and an unexplained
rollback. The worker fixture verifies five retained observations across two
segments and one completed match, and that the rejected reset does not alter
the earlier segment's counts. This is integration evidence with a simulated
stream, not a live emulator transition.

`--policy neutral-probe` is a diagnostic ordinary-input policy that always
releases the controller. It can exercise natural timeouts without changing
CPU level, match rules, game memory, assets or saves. It is not a playing
strength baseline and does not guarantee that the CPU will leave Fox alive
until time expires. The usual owned-process, deadline and recording limits
apply.

The first live neutral probe, `match-5b8b45a66daa457b9aec9c051a8ab3c0`,
completed an ordinary regulation match: Fox lost 0-4 before time expired.
All 9,386 gameplay observations passed raw integrity and exact packet replay;
the new native GameStart settings, final result, completion count and cleanup
were verified. It did not exercise Sudden Death. Frame SHA-256:
`23ee4e936de0094520d465731b400c7bd33391f4657d816a56a4bdc971799ff3`;
packet SHA-256: `12f1d5bef97a96388677c4483c90b2e9c9ff24aaf94ada8e6aff2a58eafc82fe`.
No provider was contacted. Live full-transition validation remains pending.

Agent-offline and native-build CI pass. Repository editorconfig checking still
reports 190 existing errors outside agent/docs; clang-format was cancelled by
that job failure, rather than reporting a new formatting error in this slice.
