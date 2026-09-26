# Preserve the verified Sudden Death countdown

The baseline batch stopped on its eleventh attempt after ten completed matches.
`match-76888a9288954c258cda41975e014a5c` verified regulation TIME and the new
Sudden Death GameStart, then recorded frame -123 with one stock and 300% each.
The next adapter event was `UNKNOWN_MENU`. The contest is incomplete. All
28,925 retained frames replay exactly and pass raw integrity; cleanup passed.
The failed attempt remains in the original frozen batch manifest.

The pinned adapter maps scene `0x0202` to IN_GAME but does not map `0x0302`.
The decompilation declares GM_VS=2 in `src/melee/gm/forward.h` and VS Sudden
Death state=3 in `src/melee/gm/gmvsmode.h`. Capture raw menu scene/index metadata
without changing the adapter's parser. Only allow `0x0302` during an already
verified Sudden Death segment's negative countdown, within five seconds of its
start and at most eight distinct events. Record the menu event separately; do
not count a game frame, send a menu-helper command, reset the segment or declare
a result. Other unknown scenes, repeated identities and expired bounds fail.

320 host tests pass, including the actual worker with an interleaved native
scene event and a rejected different scene. The worker fixture uses no emulator.
Native confirmation of the inferred `0x0302` event and completion through Sudden
Death remain pending. No claim of a complete baseline matrix or playing strength.

Original failed recording SHA-256:
`714707d3876f0813aba97d458042f6d1b3b7211f0ae15d80b7bf28f71398e54e`.
