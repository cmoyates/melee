# Showboat Falcon AI (work in progress)

Tracking: https://github.com/cmoyates/melee/issues/1
Branch: `mod/showboat-ai`, based on the existing single-player C-stick mod.
Initial working tree was clean; that mod is retained.

## Architecture traced so far

Local source, not external AI mods, is the ground truth:

- `Fighter_8006ABA0` calls `ftCo_800B3900` when CPU control is active
  (`ftCo_800A2040`: player is CPU, CPU mode is not 5).
- `ftCo_800B3900` in `ft/kinds/ftCommon/ftCo_0A01.c` updates observations
  (`800B33B0`), environment/behavior transitions (`800B2AFC`), dispatches
  decisions (`800B2790`), interprets commands (`800B3E04`), then performs
  mode-specific postprocessing (`800B0AF4`).
- `CpuFighter.x18` is the current behavior dispatcher ID, not an attack ID.
  Examples: 2 attack, 3 defense, 4 recovery, 9 grab/throw handling.
  `xC` is a separate CPU mode. Unknown fields retain upstream names.
- `800B2790` builds a new script only when `csP == NULL` and
  `command_duration == 0`. It calls `800ADC28` then dispatches on `x18`.
- `ftcmdscript.c` already supplies a bounded 256-byte script buffer, button
  press/release commands, analog axes, waits and `Done`. `800B462C` rewinds
  writing, `800B49F4` commits a script, `800B4A78` clears script AND inputs.
  `Done` alone does **not** release held inputs.
- `800B3E04` writes `CpuFighter.buttons/lstick/cstick/triggers`.
  `Fighter_8006B0B0` consumes these through `ftCo_GetCpu*` getters, scales
  stick values, computes button edges and runs normal fighter input handling.
  No position, damage, velocity or action-state forcing is needed.
- CPU initialization is `800A101C`. It resets scripts, targets, queues and
  observations; `x7C` starts at a random 0–9, so it is not a reliable new-match
  sentinel. Use an explicit mod reset hook instead.

## Intended V1 integration

Separate mod-owned state, explicit build opt-in, only normal Level 9 CPU
Captain Falcon. Observe match events each CPU update, then optionally supply
short native input scripts ahead of the normal decision dispatcher. Recovery
and targeting remain vanilla. Interrupt/finish must clear pending style input
and return to the vanilla dispatcher on the same update.

Further findings, implemented behavior, tuning, build evidence and test steps
will be recorded here as implementation proceeds. This document is not a claim
of completed implementation or runtime validation.
