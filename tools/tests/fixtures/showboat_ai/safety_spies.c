/* Typed orchestration spy, NOT the actual ledge/Side-B safety policy.
 * No default permission: every call must consume an explicitly armed, bounded
 * expectation. Saved actors are comparison tokens, never dereferenced on reset.
 * The optional B/x edit is a distinctive output filter, not a recovery model. */
typedef struct {
    Fighter *actor, *target;
    struct CpuFighter input;
    bool veto;
    int combat_posts, recorder_frames;
} SafetyExpectation;
static struct {
    SafetyExpectation expected[8];
    int count, calls, logs;
    bool watching_logs;
    char last_log[256];
} safety;

static void safety_expect(Fighter* fp, Fighter* rival, bool veto,
                          const struct CpuFighter* input)
{
    CHECK(fp && rival && fp != rival && input);
    CHECK(safety.count < (int) (sizeof(safety.expected) / sizeof(safety.expected[0])));
    SafetyExpectation* next = &safety.expected[safety.count++];
    next->actor = fp; next->target = rival; next->veto = veto;
    memcpy(&next->input, input, sizeof(*input));
    next->combat_posts = combat.posts + 1;
    next->recorder_frames = recording.frames;
}
static void safety_verified(void) { CHECK(safety.calls == safety.count); }

bool ShowboatSafety_PostInput(Fighter* fp, Fighter* rival)
{
    CHECK(safety.calls < safety.count); /* unexpected call fails, even if false */
    SafetyExpectation* next = &safety.expected[safety.calls++];
    CHECK(fp == next->actor && rival == next->target);
    CHECK(combat.posts == next->combat_posts); /* CombatPostInput already ran */
    CHECK(recording.frames == next->recorder_frames); /* Frame has NOT run */
    CHECK(memcmp(&fp->cpu, &next->input, sizeof(fp->cpu)) == 0);
    recording_mark(REC_SAFETY, fp, next->veto, 0);
    if (next->veto) {
        fp->cpu.buttons &= ~HSD_PAD_B;
        fp->cpu.lstick.x = 0;
    }
    return next->veto;
}
