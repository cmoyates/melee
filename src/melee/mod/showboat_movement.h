#ifndef MELEE_MOD_SHOWBOAT_MOVEMENT_H
#define MELEE_MOD_SHOWBOAT_MOVEMENT_H

#include <melee/ft/forward.h>

/* Sidecar only. Suspend the live fighter BEFORE resetting an occupied slot. */
void ShowboatMovement_ResetSlot(int slot);
/* Abort only a still-owned VM; preserve replacement native scripts and A4. */
void ShowboatMovement_Suspend(Fighter* fp);
/* Once per CPU sample, AFTER arbitration and BEFORE native script dispatch.
 * Service an active action before combat/taunts; try new starts only after
 * combat declines. Main grants normal-mode level-9 primary Falcon singles
 * eligibility (no Nana). No personality/ego gate. true supplies controller
 * commands, false permits native fallback THIS frame. NULL target aborts. */
bool ShowboatMovement_Update(Fighter* fp, Fighter* target);
/* HUD ID: 0 none, 9 WDASH. Identity/spawn checked, no state creation. */
int ShowboatMovement_GetAction(Fighter* fp);

#endif
