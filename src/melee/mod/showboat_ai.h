#ifndef MELEE_MOD_SHOWBOAT_AI_H
#define MELEE_MOD_SHOWBOAT_AI_H

#include <melee/ft/forward.h>

/* Only called/linked by builds explicitly configured with --showboat-ai. */
void ShowboatAI_ResetSlot(int slot);
/* Called outside the CPU-control gate; discards ownership on control changes. */
void ShowboatAI_Suspend(Fighter* fp);
/* After vanilla observations/arbitration; true supplies this frame's script. */
bool ShowboatAI_Update(Fighter* fp);
/* Retains vanilla eligibility; only changes relative candidate probability. */
float ShowboatAI_AttackWeight(Fighter* fp, void* table, int command,
                             float weight);

#endif
