#ifndef MELEE_MOD_SHOWBOAT_HUD_H
#define MELEE_MOD_SHOWBOAT_HUD_H

#include <melee/ft/forward.h>

#if SHOWBOAT_AI_HUD
/* Display values, NOT motion IDs or CPU scenarios. Map the AI's private enum
 * to these values if that enum changes. Unknown actions display VANILLA. */
enum ShowboatHUD_Action {
    SHOWBOAT_HUD_VANILLA = 0,
    SHOWBOAT_HUD_TAUNT = 1,
    SHOWBOAT_HUD_SWAGGER = 2,
    SHOWBOAT_HUD_PUNCH = 3,
    SHOWBOAT_HUD_DANCE = 4,
    SHOWBOAT_HUD_GRAB = 5,
    SHOWBOAT_HUD_KNEE = 6,
    SHOWBOAT_HUD_UPAIR = 7,
    SHOWBOAT_HUD_JUGGLE = 8
};

/* Call on the game thread, after the normal scene/DevText setup, for a live
 * primary Falcon. Caller decides AI eligibility. ego is clamped to 0..100;
 * serious is the nonnegative remaining frame count (not a boolean).
 * Publish every AI tick, including vanilla/early-return and suspended paths.
 * This copies display data only; it never retains or mutates Fighter*. */
void ShowboatHUD_Update(Fighter* fp, int ego, int action, int serious);

/* Call when a slot loses eligibility, is removed/replaced, or its AI state is
 * reset. Call before the old fighter is freed; do not let a secondary fighter
 * reset its primary's row. Safe with no HUD and with out-of-range slots. */
void ShowboatHUD_ResetSlot(int slot);

/* Update validates its render GObj against live scene lists before reuse;
 * bulk scene heap replacement need not invoke destructors. Slot reset simply
 * clears our static row, and requires neither a live GObj nor a fighter. */
#endif

#endif
