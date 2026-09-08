#ifndef MELEE_MOD_SHOWBOAT_COMBAT_H
#define MELEE_MOD_SHOWBOAT_COMBAT_H

#include <melee/ft/forward.h>

/* Mod-owned memory only; call alongside native slot/spawn resets. */
void ShowboatCombat_ResetSlot(int slot);
/* Call FIRST in main Update and Suspend, before resets/eligibility/taunt gates.
 * Identity/spawn checked; restores only an unchanged borrowed analog channel. */
void ShowboatCombat_RestoreInput(Fighter* fp);
/* Once per sampled CPU frame, after native arbitration, before script dispatch.
 * Call even when personality owns input: restoration here is idempotent.
 * true supplies a script for the stock interpreter, NOT a fighter transition.
 * Passing NULL target cancels offense but still performs analog cleanup. */
bool ShowboatCombat_Update(Fighter* fp, Fighter* target);
/* After the stock interpreter, before Fighter samples CPU controller output.
 * Never gated on ego/serious or on Update's return value. */
void ShowboatCombat_PostInput(Fighter* fp);
/* HUD IDs: 0 none, 5 GRAB, 6 KNEE, 7 UPAIR. Short-hop chasing deferred. */
int ShowboatCombat_GetAction(Fighter* fp);

#endif
