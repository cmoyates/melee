#include "showboat_recorder.h"
#include <assert.h>

/* Link with the actual (disabled) C TU and no recorder implementation. */
int main(void)
{
    int calls = 0, i;
    const int tactics[] = { SBR_PERSONALITY, SBR_COMBAT, SBR_MOVEMENT,
        SBR_DEFENSE, SBR_LCANCEL, SBR_TACTICS };
    const int reasons[] = { SBR_NOT_EVALUATED, SBR_NO_CANDIDATE, SBR_ACTIVE,
        SBR_STARTED, SBR_NATIVE_PRIORITY, SBR_INPUT_OR_SCRIPT,
        SBR_PHYSICAL_OR_STATE, SBR_TARGET, SBR_GEOMETRY_OR_WINDOW,
        SBR_COOLDOWN, SBR_EGO_OR_CAUTION, SBR_ITEMS, SBR_COMPLETED,
        SBR_CANCELLED, SBR_BUDGET, SBR_SUCCESS, SBR_REASONS };
    const int events[] = { SBR_EVENT_TAUNT_ACK, SBR_EVENT_PUNCH_ACK,
        SBR_EVENT_GRAB_ACK, SBR_EVENT_AERIAL_ACK, SBR_EVENT_WAVEDASH_LANDING_ACK,
        SBR_EVENT_POWERSHIELD_CONTACT, SBR_EVENT_LCANCEL_SAMPLE,
        SBR_EVENT_SIDEB_VETO };
    for (i = 0; i < 6; ++i) { assert(tactics[i] == i); }
    for (i = 0; i < 17; ++i) { assert(reasons[i] == i); }
    for (i = 0; i < 8; ++i) { assert(events[i] == (1 << i)); }
    ShowboatRecorder_Begin(++calls);
    ShowboatRecorder_Reason(++calls, ++calls, ++calls);
    ShowboatRecorder_Event(++calls, ++calls);
    ShowboatRecorder_Decision(++calls, ++calls, ++calls, ++calls);
    ShowboatRecorder_Frame(++calls, ++calls);
    ShowboatRecorder_ResetSlot(++calls);
    ShowboatRecorder_Suspend(++calls);
    assert(calls == 0);
    return 0;
}
