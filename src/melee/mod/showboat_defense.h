#ifndef MELEE_MOD_SHOWBOAT_DEFENSE_H
#define MELEE_MOD_SHOWBOAT_DEFENSE_H

#include <melee/ft/forward.h>

/* Sidecars only; never dereferences saved fighters. Suspend a still-live owner
 * BEFORE ResetSlot when immediate release is needed. An abandoned VM has a
 * ten-sample hold / ReleaseR tail, not an unbounded latch. */
void ShowboatDefense_ResetSlot(int slot);
/* Pass the still-live owner, even after its spawn number changes. Cleans an
 * exact old VM BEFORE forgetting by owner pointer, independently of spawn.
 * Only the executed wait phase owns R (including unchanged raw analog 255);
 * pending/completed scripts and replaced VMs do not own later native R.
 * Other controller channels and fresh native priority/A4 survive. Clears credit. */
void ShowboatDefense_Suspend(Fighter* fp);
/* Once per CPU input update AFTER native arbitration/threat refresh and BEFORE
 * native script dispatch/interpreter. true = controller VM ownership, NOT a
 * collision or motion transition. A false return from an ACTIVE action10 must
 * allow native dispatch in the SAME update, notably handoff with R still held.
 * An idle declined start owns nothing and may yield to another tactic. Service
 * action10 before combat; only try a new start after combat declines. Rechecks
 * level9 Captain mode4 and primary live singles identities. Caller must Suspend
 * before raw ResetSlot for immediate cleanup; never dereference saved pointers. */
bool ShowboatDefense_Update(Fighter* fp, Fighter* opponent);
/* 0 none, 10 BLOCK (hardshield intent), 11 PERFECT (observed fighter contact).
 * PERFECT lasts at most 30 calls to Update, or until leaving the guard family;
 * this private display countdown never changes a game timer or awards credit.
 * GuardReflect/window flags alone are only an attempt, never PERFECT. */
int ShowboatDefense_GetAction(Fighter* fp);
/* Consume at most once per owned attempt; native fighter PS contact only.
 * Poll after Update even when it returned false (contact hands back to native).
 * Reset/Suspend/identity or config loss discards pending events. */
bool ShowboatDefense_TakePerfect(Fighter* fp);

#endif
