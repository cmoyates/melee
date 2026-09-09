/* Main orchestration only: do NOT link/copy showboat_recorder.c. These spies
 * retain call arguments and snapshots, not segments, sampling or schema logic.
 * Saved owners are comparison tokens only. No spy writes any game field.
 * The opt-in, bounded trace is independent of the legacy EV_* trace and never
 * accumulates across the long personality loops. setup() clears all counters. */
enum {
    REC_RESTORE, REC_BEGIN, REC_REASON, REC_DECISION, REC_VM, REC_POST,
    REC_FRAME, REC_RESET, REC_SUSPEND, REC_EVENT, REC_COMBAT,
    REC_MOVEMENT, REC_DEFENSE, REC_SAFETY, REC_LOG
};
typedef struct {
    Fighter* owner;
    int reasons[SBR_TACTICS];
    unsigned mask;
    int ego, action;
    bool owns;
} RecordingSlot;
static struct {
    RecordingSlot slots[SB_SLOTS];
    int begins, decisions, frames, reasons, events, suspends, resets[SB_SLOTS];
    Fighter *begin_actor, *decision_actor, *frame_actor, *frame_target,
            *suspend_actor;
    struct CpuFighter begin_cpu, decision_cpu, post_cpu, frame_cpu, event_cpu;
    int begin_tick, decision_tick;
    bool watching;
    int count;
    struct { int kind, a, b; Fighter* actor; } trace[128];
} recording;

static void recording_mark(int kind, Fighter* fp, int a, int b)
{
    if (!recording.watching) { return; }
    CHECK(recording.count < (int) (sizeof(recording.trace) / sizeof(recording.trace[0])));
    recording.trace[recording.count].kind = kind;
    recording.trace[recording.count].actor = fp;
    recording.trace[recording.count].a = a;
    recording.trace[recording.count++].b = b;
}

/* Guard DEFINITIONS too: the disabled header APIs are argument-erasing macros. */
#if SHOWBOAT_RECORDER
static RecordingSlot* recording_slot(Fighter* fp)
{
    CHECK(fp != NULL);
    if (fp->player_id >= SB_SLOTS) { return NULL; }
    return &recording.slots[fp->player_id];
}
void ShowboatRecorder_Begin(Fighter* fp)
{
    RecordingSlot* slot = recording_slot(fp);
    ++recording.begins; recording.begin_actor = fp;
    memcpy(&recording.begin_cpu, &fp->cpu, sizeof(fp->cpu));
    recording.begin_tick = slot ? sb_states[fp->player_id].tick : -1;
    recording_mark(REC_BEGIN, fp, 0, 0);
    if (slot) {
        memset(slot, 0, sizeof(*slot));
        slot->owner = fp;
    }
}
void ShowboatRecorder_Reason(Fighter* fp, int tactic, int reason)
{
    RecordingSlot* slot = recording_slot(fp);
    CHECK(tactic >= 0 && tactic < SBR_TACTICS);
    CHECK(reason >= 0 && reason < SBR_REASONS);
    ++recording.reasons;
    recording_mark(REC_REASON, fp, tactic, reason);
    if (slot) { slot->owner = fp; slot->reasons[tactic] = reason; }
}
void ShowboatRecorder_Event(Fighter* fp, unsigned mask)
{
    RecordingSlot* slot = recording_slot(fp);
    ++recording.events;
    memcpy(&recording.event_cpu, &fp->cpu, sizeof(fp->cpu));
    recording_mark(REC_EVENT, fp, (int) mask, 0);
    if (slot) { slot->owner = fp; slot->mask |= mask; }
}
void ShowboatRecorder_Decision(Fighter* fp, int ego, int action, bool owns)
{
    RecordingSlot* slot = recording_slot(fp);
    CHECK(slot);
    ++recording.decisions; recording.decision_actor = fp;
    recording.decision_tick = sb_states[fp->player_id].tick;
    memcpy(&recording.decision_cpu, &fp->cpu, sizeof(fp->cpu));
    recording_mark(REC_DECISION, fp, action, owns);
    slot->owner = fp; slot->ego = ego; slot->action = action; slot->owns = owns;
}
void ShowboatRecorder_Frame(Fighter* fp, Fighter* rival)
{
    CHECK(fp);
    ++recording.frames;
    recording.frame_actor = fp; recording.frame_target = rival;
    memcpy(&recording.frame_cpu, &fp->cpu, sizeof(fp->cpu));
    recording_mark(REC_FRAME, fp, 0, 0);
}
void ShowboatRecorder_ResetSlot(int slot)
{
    CHECK(slot >= 0 && slot < SB_SLOTS);
    ++recording.resets[slot];
    recording_mark(REC_RESET, NULL, slot, 0);
    memset(&recording.slots[slot], 0, sizeof(recording.slots[slot]));
}
void ShowboatRecorder_Suspend(Fighter* fp)
{
    RecordingSlot* slot = recording_slot(fp);
    ++recording.suspends; recording.suspend_actor = fp;
    recording_mark(REC_SUSPEND, fp, 0, 0);
    if (slot && slot->owner == fp) { memset(slot, 0, sizeof(*slot)); }
}
#endif
