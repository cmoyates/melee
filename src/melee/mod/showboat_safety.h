#ifndef MELEE_MOD_SHOWBOAT_SAFETY_H
#define MELEE_MOD_SHOWBOAT_SAFETY_H

#include <melee/ft/forward.h>

/* Stateless OUTPUT-ONLY veto. Main calls AFTER CPU VM / Combat_PostInput and
 * BEFORE Recorder_Frame/input sampling, only SB_NONE, no active custom tactic,
 * ready singles and unchanged primary/spawn identities. Main owns team policy,
 * linking, orchestration and true-result telemetry.
 * Fighter writes: true ONLY clears cpu.buttons B and sets cpu.lstick.x=0;
 * false changes no Fighter data. The existing native floor query may refresh
 * collision broad-phase flags/cache; the added map getters are read-only.
 * Native priority-9 uncached followup, VM/cursors/buffer/duration/cache/target,
 * 55-update wait and later inputs remain intact (idle tail accepted).
 * No ownership, reset/suspend, borrowed restore or future callback contract. */
bool ShowboatSafety_PostInput(Fighter* fp, Fighter* target);

#endif
