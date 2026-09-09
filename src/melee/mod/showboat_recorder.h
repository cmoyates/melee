#ifndef MELEE_MOD_SHOWBOAT_RECORDER_H
#define MELEE_MOD_SHOWBOAT_RECORDER_H

#include <melee/ft/forward.h>

/* Stable schema-v1 IDs. A reason describes the executed branch/group, not
 * necessarily one atomic predicate. Uncalled layers remain NOT_EVALUATED. */
enum {
    SBR_PERSONALITY, SBR_COMBAT, SBR_MOVEMENT, SBR_DEFENSE, SBR_LCANCEL,
    SBR_TACTICS
};
enum {
    SBR_NOT_EVALUATED, SBR_NO_CANDIDATE, SBR_ACTIVE, SBR_STARTED,
    SBR_NATIVE_PRIORITY, SBR_INPUT_OR_SCRIPT, SBR_PHYSICAL_OR_STATE,
    SBR_TARGET, SBR_GEOMETRY_OR_WINDOW, SBR_COOLDOWN, SBR_EGO_OR_CAUTION,
    SBR_ITEMS, SBR_COMPLETED, SBR_CANCELLED, SBR_BUDGET, SBR_SUCCESS,
    SBR_REASONS
};
/* Additive v2 event bit: no protocol version bump or format/float-encoding
 * change. Older strict readers with mask 127 reject bit 128, not reinterpret it.
 * SIDEB_VETO records an actual controller safety veto, not an acknowledgment,
 * hit, success or proof of a saved recovery. Existing bits 1-64 are unchanged. */
enum {
    SBR_EVENT_TAUNT_ACK = 1, SBR_EVENT_PUNCH_ACK = 2,
    SBR_EVENT_GRAB_ACK = 4, SBR_EVENT_AERIAL_ACK = 8,
    SBR_EVENT_WAVEDASH_LANDING_ACK = 16, SBR_EVENT_POWERSHIELD_CONTACT = 32,
    SBR_EVENT_LCANCEL_SAMPLE = 64, SBR_EVENT_SIDEB_VETO = 128
};

#if SHOWBOAT_RECORDER
/* Call Begin before AI arbitration overlay, Decision after it, and Frame after
 * native VM + mod post-input overlay. All game observations are read-only.
 * Reset/Suspend flush private records, never dereference saved fighter tokens. */
void ShowboatRecorder_Begin(Fighter* fp);
void ShowboatRecorder_Reason(Fighter* fp, int tactic, int reason);
void ShowboatRecorder_Event(Fighter* fp, unsigned mask);
void ShowboatRecorder_Decision(Fighter* fp, int ego, int action, bool owns);
void ShowboatRecorder_Frame(Fighter* fp, Fighter* target);
void ShowboatRecorder_ResetSlot(int slot);
void ShowboatRecorder_Suspend(Fighter* fp);
#else
/* Do not even evaluate arguments in non-recording builds. */
#define ShowboatRecorder_Begin(fp) ((void) 0)
#define ShowboatRecorder_Reason(fp, tactic, reason) ((void) 0)
#define ShowboatRecorder_Event(fp, mask) ((void) 0)
#define ShowboatRecorder_Decision(fp, ego, action, owns) ((void) 0)
#define ShowboatRecorder_Frame(fp, target) ((void) 0)
#define ShowboatRecorder_ResetSlot(slot) ((void) 0)
#define ShowboatRecorder_Suspend(fp) ((void) 0)
#endif

#endif
