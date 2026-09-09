#include "game.h"
#include "showboat_recorder.h"
#include <assert.h>
#include <float.h>
#include <limits.h>
#include <math.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static Fighter fighters[6];
static Fighter_GObj gobjs[6], secondary;
static Fighter_GObj* primary[6];
static Fighter_GObj* second[6];
static int states[6], stocks[6], player_kind[6];
static u32 frame, rng = 0x1937DEADU;
static unsigned rng_calls, report_calls;
static u8 mode;
static bool no_rules;
static struct StartMeleeRules rules;
static struct TestEntities entities;
struct TestEntities* HSD_GObj_Entities = &entities;

u32 gm_GetFrameCount(void) { return frame; }
u8 gm_GetCurrentGameMode(void) { return mode; }
struct StartMeleeRules* gm_GetRules(void) { return no_rules ? NULL : &rules; }
Fighter_GObj* Player_GetEntity(int s) { assert(s >= 0 && s < 6); return primary[s]; }
Fighter_GObj* Player_GetEntityAtIndex(int s, int i)
{ assert(s >= 0 && s < 6 && i == 1); return second[s]; }
int Player_GetPlayerState(int s) { assert(s >= 0 && s < 6); return states[s]; }
int Player_GetStocks(int s) { assert(s >= 0 && s < 6); return stocks[s]; }
int Player_8003248C(int s, bool sub)
{ assert(s >= 0 && s < 6 && !sub); return player_kind[s]; }
/* Actual native read-only protection, CPU eligibility, ally and stage queries. */
#include "native_functions.h"

/* Any accidental native RNG or mutating query is a hard failure, not a benign
 * no-op. The recorder object also has an independent external-symbol allowlist. */
int HSD_Randi(int n) { (void)n; ++rng_calls; ++rng; abort(); }
float HSD_Randf(void) { ++rng_calls; ++rng; abort(); }
void ftCo_800B4A78(Fighter* fp) { (void)fp; abort(); }
void ftCo_800B49F4(Fighter* fp) { (void)fp; abort(); }

void OSReport(const char* format, ...)
{
    char line[1024];
    int n;
    va_list args;
    va_start(args, format);
    if (!strcmp(format, "%s")) {
        /* The sample transport consumes exactly one pointer, never doubles or
         * integer payload varargs. Python also checks the literal call site,
         * since C varargs cannot reveal unused extra arguments at runtime. */
        const char* text = va_arg(args, const char*);
        assert(strncmp(text, "SBREC {\"v\":2,\"type\":\"sample\",", 29) == 0);
        n = (int)strlen(text);
        assert(n > 0 && n < (int)sizeof(line));
        memcpy(line, text, (size_t)n + 1);
    } else {
        const char* p;
        /* Reject any return to a numeric sample OSReport before consuming its
         * varargs. Existing begin/gate/end may use only integer/string args. */
        assert(strstr(format, "\"sample\"") == NULL);
        for (p = format; *p; ++p) {
            if (*p == '%') { ++p; assert(*p && strchr("dus", *p)); }
        }
        n = vsnprintf(line, sizeof(line), format, args);
        assert(strstr(line, "\"type\":\"sample\"") == NULL);
    }
    va_end(args);
    assert(n > 0 && n < (int)sizeof(line));
    assert(strncmp(line, "SBREC {", 7) == 0);
    assert(line[n - 1] == '\n' && strchr(line, '\n') == line + n - 1);
    ++report_calls;
    assert(fwrite(line, 1, (size_t)n, stdout) == (size_t)n);
}

typedef struct {
    unsigned char pool[sizeof(fighters)];
    Fighter* live[6];
    unsigned char fighter[6][sizeof(Fighter)];
    unsigned char cpu[6][sizeof(struct CpuFighter)];
    unsigned char rules_copy[sizeof(rules)];
    unsigned char gobj_copy[sizeof(gobjs)];
    u32 random;
} Snapshot;
static void save(Snapshot* s)
{
    int i;
    memcpy(s->pool, fighters, sizeof(fighters));
    memcpy(s->rules_copy, &rules, sizeof(rules));
    memcpy(s->gobj_copy, gobjs, sizeof(gobjs));
    s->random = rng;
    for (i = 0; i < 6; ++i) {
        s->live[i] = primary[i] ? primary[i]->user_data : NULL;
        if (s->live[i]) {
            memcpy(s->fighter[i], s->live[i], sizeof(Fighter));
            memcpy(s->cpu[i], &s->live[i]->cpu, sizeof(struct CpuFighter));
        }
    }
}
static void unchanged(Snapshot* s)
{
    int i;
    assert(memcmp(s->pool, fighters, sizeof(fighters)) == 0);
    assert(memcmp(s->rules_copy, &rules, sizeof(rules)) == 0);
    assert(memcmp(s->gobj_copy, gobjs, sizeof(gobjs)) == 0);
    assert(s->random == rng && rng_calls == 0);
    for (i = 0; i < 6; ++i) {
        if (s->live[i]) {
            assert(memcmp(s->fighter[i], s->live[i], sizeof(Fighter)) == 0);
            assert(memcmp(s->cpu[i], &s->live[i]->cpu, sizeof(struct CpuFighter)) == 0);
        }
    }
}
#define CHECK(call) do { Snapshot snap; save(&snap); call; unchanged(&snap); } while (0)

static void setup(void)
{
    int i;
    assert(St_Kind_Battle == 31 && St_Kind_Last == 32);
    assert(SBR_TACTICS == 5 && SBR_REASONS == 16);
    memset(fighters, 0, sizeof(fighters));
    memset(&rules, 0, sizeof(rules));
    rules.stkind = St_Kind_Battle;
    rules.match_kind = MatchKind_Stock;
    rules.is_stock = rules.is_vs = 1;
    rules.x30 = rules.game_speed = 1;
    mode = GM_VS;
    frame = 1;
    for (i = 0; i < 6; ++i) {
        Fighter* f = &fighters[i];
        gobjs[i].user_data = f;
        primary[i] = &gobjs[i];
        f->gobj = primary[i];
        f->player_id = (u8)i;
        f->team = (u8)i;
        f->kind = FTKIND_CAPTAIN;
        f->x8_spawnNum = 100 + i;
        f->motion_id = ftCo_MS_Wait;
        f->shield_health = 60;
        /* Populate the ENTIRE native CPU definition, including VM/caches and
         * pointers, before overriding fields actually observed by recorder. */
        memset(&f->cpu, 0xA5, sizeof(f->cpu));
        memset(&f->mv, 0xA5, sizeof(f->mv));
        memset(f->unrelated, 0x5A, sizeof(f->unrelated));
        f->cpu.level = 9;
        f->cpu.xC = 4;
        f->cpu.x18 = 2;
        f->cpu.xA4 = 42;
        f->cpu.xF8_b12 = 2;
        f->cpu.buttons = 0;
        f->cpu.lstick.x = f->cpu.lstick.y = 0;
        f->cpu.cstick.x = f->cpu.cstick.y = 0;
        f->cpu.ltrigger = f->cpu.rtrigger = 0;
        stocks[i] = 4;
        states[i] = i < 2 ? 2 : 0;
        player_kind[i] = i == 0 ? Gm_PKind_Cpu : Gm_PKind_Human;
    }
}
static void begin(Fighter* f)
{ CHECK(ShowboatRecorder_Begin(f)); }
static void decision(Fighter* f, int action)
{ CHECK(ShowboatRecorder_Decision(f, 55, action, false)); }
static void observe(Fighter* f, Fighter* t)
{ CHECK(ShowboatRecorder_Frame(f, t)); }
static void step(u32 n, int action)
{
    frame = n;
    begin(&fighters[0]);
    decision(&fighters[0], action);
    observe(&fighters[0], &fighters[1]);
}
static void finish(void)
{
    int i;
    for (i = 0; i < 6; ++i) { CHECK(ShowboatRecorder_ResetSlot(i)); }
}

static void schema(void)
{
    Fighter* f = &fighters[0];
    Fighter* t = &fighters[1];
    frame = 1000;
    f->motion_id = ftCo_MS_CaptureWaitHi;
    f->cur_anim_frame = 2.5f;
    f->cur_pos.x = -25.25f; f->cur_pos.y = 13.5f;
    f->self_vel.x = -1.25f; f->self_vel.y = 2.75f;
    f->gr_vel = 0.125f; f->dmg.x1830_percent = 23.5f;
    f->shield_health = 51.25f; stocks[0] = 3;
    f->ground_or_air = GA_Air;
    f->x221C_b6 = f->x2219_b5 = f->x221F_b3 = 1;
    f->item_gobj = &secondary; f->x198C = 2;
    entities.items = &secondary;
    t->kind = FTKIND_FOX;
    t->cur_pos.x = 45;
    f->cpu.buttons = HSD_PAD_R | HSD_PAD_A;
    f->cpu.lstick.x = -80; f->cpu.lstick.y = 79;
    f->cpu.cstick.x = 5; f->cpu.cstick.y = -6;
    f->cpu.ltrigger = 11; f->cpu.rtrigger = 255;
    begin(f);
    CHECK(ShowboatRecorder_Reason(f, SBR_PERSONALITY, SBR_STARTED));
    CHECK(ShowboatRecorder_Reason(f, SBR_PERSONALITY, SBR_ACTIVE));
    CHECK(ShowboatRecorder_Reason(f, SBR_LCANCEL, SBR_SUCCESS));
    CHECK(ShowboatRecorder_Reason(f, -1, 2));
    CHECK(ShowboatRecorder_Reason(f, 5, 2));
    CHECK(ShowboatRecorder_Reason(f, 1, -1));
    CHECK(ShowboatRecorder_Reason(f, 1, 16));
    CHECK(ShowboatRecorder_Event(f, SBR_EVENT_TAUNT_ACK));
    CHECK(ShowboatRecorder_Event(f, 0xFFFFFFFEU));
    CHECK(ShowboatRecorder_Decision(f, 73, 11, true));
    observe(f, t);
    observe(f, t); /* No double count, no second sample. */
    finish(); finish();
}
static void sentinels(void)
{
    /* Independent bit patterns: all sixteen fields differ, including -0,
     * both minimum subnormals, both maximum finite values and normal edges.
     * memcpy sets the fixture bits without decimal rounding/aliasing. */
    static const u32 bits[2][8] = {
        { 0x80000000U, 0x00000001U, 0x7f7fffffU, 0x80800000U,
          0x3f123456U, 0xbf654321U, 0x412abcdeU, 0xc2480001U },
        { 0x00000000U, 0x80000001U, 0xff7fffffU, 0x00800000U,
          0x3eaaaaabU, 0xc1234567U, 0x42f6e979U, 0x3f800001U },
    };
    Fighter* f = &fighters[0];
    Fighter* t = &fighters[1];
    int side, i;
    for (side = 0; side < 2; ++side) {
        Fighter* v = &fighters[side];
        float* fields[] = { &v->cur_anim_frame, &v->cur_pos.x, &v->cur_pos.y,
            &v->self_vel.x, &v->self_vel.y, &v->gr_vel,
            &v->dmg.x1830_percent, &v->shield_health };
        for (i = 0; i < 8; ++i) { memcpy(fields[i], &bits[side][i], sizeof(float)); }
    }
    frame = 0xFFFFFFFDU;
    f->x8_spawnNum = INT_MIN; t->x8_spawnNum = INT_MAX;
    f->motion_id = ftCo_MS_Dash; t->motion_id = ftCo_MS_Fall;
    t->kind = FTKIND_FOX;
    stocks[0] = 7; stocks[1] = 13;
    f->ground_or_air = GA_Air; f->x2219_b5 = 1; f->item_gobj = &secondary;
    t->x221C_b6 = t->x221F_b3 = 1; t->x198C = 2;
    f->cpu.x18 = INT_MIN; f->cpu.xA4 = INT_MAX; f->cpu.xF8_b12 = 3;
    f->cpu.buttons = UINT_MAX;
    f->cpu.lstick.x = -128; f->cpu.lstick.y = 127;
    f->cpu.cstick.x = -73; f->cpu.cstick.y = 0;
    f->cpu.ltrigger = 17; f->cpu.rtrigger = 254;
    begin(f);
    for (i = 0; i < SBR_TACTICS; ++i) { CHECK(ShowboatRecorder_Reason(f, i, 1 + i * 3)); }
    CHECK(ShowboatRecorder_Event(f, 85));
    CHECK(ShowboatRecorder_Decision(f, 97, 9, true));
    observe(f, t);
    finish();
}
static void capacity_baseline(void)
{
    step(1, 0);
    finish();
}
static void overflow(void)
{
    u32 n;
    for (n = 1; n <= 61; ++n) { step(n, 0); }
    finish();
    /* Begin, two complete five-tactic flushes, end; NO sample fragments. */
    assert(report_calls == 12);
}
static void overflow_recovery(void)
{
    unsigned before;
    step(1, 0);
    before = report_calls;
    assert(before == 2);
    /* Same identity/context: longer integer payload exceeds exact-fit cap. */
    fighters[0].cpu.x18 = INT_MIN;
    fighters[0].cpu.xA4 = INT_MAX;
    fighters[0].cpu.buttons = UINT_MAX;
    step(2, 0);
    assert(report_calls == before);
    fighters[0].cpu.x18 = 2;
    fighters[0].cpu.xA4 = 42;
    fighters[0].cpu.buttons = 0;
    /* No normal change/interval trigger: only failed SR_Emit's gap recovers. */
    step(3, 0);
    assert(report_calls == before + 1);
    step(4, 0);
    assert(report_calls == before + 1);
    finish();
}
static void phase(void)
{
    Fighter* f = &fighters[0];
    begin(f);
    CHECK(ShowboatRecorder_Reason(f, SBR_COMBAT, SBR_ACTIVE));
    decision(f, 7);
    assert(report_calls == 0); /* Begin/Reason/Decision do not take snapshots. */
    /* Model native VM then post-input output AFTER Decision. These are fixture
     * writes, not recorder writes; the main hook itself is outside this test. */
    f->cpu.buttons = HSD_PAD_A;
    f->cpu.buttons |= HSD_PAD_R;
    f->cpu.rtrigger = 255;
    f->cpu.lstick.x = -40;
    f->cpu.x18 = 7;
    f->cur_anim_frame = 6;
    fighters[1].dmg.x1830_percent = 7;
    /* Prior preprocessed channels must neither leak into input[] nor change. */
    f->input.held_buttons[0] = 0xDEADBEEFU;
    f->input.triggers[0] = 0.375f;
    f->input.lstick.x = 0.75f;
    observe(f, &fighters[1]);
    finish();
}
static void periodic(void)
{
    u32 i;
    for (i = 1; i <= 37; ++i) {
        fighters[0].cpu.lstick.x = (s8)i;
        fighters[1].cur_pos.x = (float)i;
        fighters[0].cur_anim_frame = (float)i;
        fighters[1].shield_health -= 0.01f;
        step(i, 0);
    }
    finish();
}
static void changes(void)
{
    Fighter* f = &fighters[0];
    Fighter* t = &fighters[1];
    step(1, 0);
    f->motion_id = ftCo_MS_Dash; step(2, 0);
    t->motion_id = ftCo_MS_Fall; step(3, 0);
    f->dmg.x1830_percent = 1; step(4, 0);
    t->dmg.x1830_percent = 2; step(5, 0);
    --stocks[0]; step(6, 0);
    --stocks[1]; step(7, 0);
    f->cpu.x18 = 7; step(8, 0);
    step(9, 10);
    f->cpu.buttons = HSD_PAD_R; step(10, 10);
    f->cpu.ltrigger = 1; step(11, 10);
    f->cpu.rtrigger = 255; step(12, 10);
    f->ground_or_air = GA_Air; step(13, 10);
    t->x2219_b5 = 1; step(14, 10);
    frame = 15; begin(f); decision(f, 10);
    CHECK(ShowboatRecorder_Event(f, SBR_EVENT_PUNCH_ACK)); observe(f, t);
    frame = 16; begin(f); CHECK(ShowboatRecorder_Decision(f, 55, 10, true)); observe(f, t);
    finish();
}
static void gaps(void)
{
    step(1, 0); step(2, 0); step(7, 0);
    observe(&fighters[0], &fighters[1]);
    begin(&fighters[0]); decision(&fighters[0], 0);
    CHECK(ShowboatRecorder_Event(&fighters[0], SBR_EVENT_GRAB_ACK));
    observe(&fighters[0], &fighters[1]);
    step(8, 0);
    finish();
}
static void gates(void)
{
    int n, t;
    for (n = 1; n <= 125; ++n) {
        frame = (u32)n;
        begin(&fighters[0]);
        for (t = 0; t < SBR_TACTICS; ++t) {
            if (t == 4 || (t == 1 && n % 2 == 0)) { continue; }
            CHECK(ShowboatRecorder_Reason(&fighters[0], t, SBR_CANCELLED));
            CHECK(ShowboatRecorder_Reason(&fighters[0], t, (n + t) % SBR_REASONS));
        }
        decision(&fighters[0], 0);
        observe(&fighters[0], &fighters[1]);
        observe(&fighters[0], &fighters[1]);
    }
    finish(); finish();
}
static void exact_flush(void)
{
    u32 n;
    for (n = 1; n <= 60; ++n) { step(n, 0); }
    finish(); finish(); /* The 60th observation has already flushed. */
    step(61, 0);
    finish();
}
static void nonfinite(void)
{
    int side, field, bad;
    u32 n = 1;
    step(n++, 0);
    for (side = 0; side < 2; ++side) {
        Fighter* f = &fighters[side];
        float* fields[] = { &f->cur_anim_frame, &f->cur_pos.x, &f->cur_pos.y,
            &f->self_vel.x, &f->self_vel.y, &f->gr_vel,
            &f->dmg.x1830_percent, &f->shield_health };
        for (field = 0; field < 8; ++field) {
            for (bad = 0; bad < 3; ++bad) {
                float old = *fields[field];
                *fields[field] = bad == 0 ? NAN : bad == 1 ? INFINITY : -INFINITY;
                step(n++, 0);
                *fields[field] = old;
                step(n++, 0);
            }
        }
    }
    finish();
}
static void extremes(void)
{
    int i;
    frame = UINT_MAX;
    for (i = 0; i < 2; ++i) {
        Fighter* f = &fighters[i];
        f->x8_spawnNum = INT_MIN;
        f->motion_id = INT_MAX;
        f->cur_anim_frame = f->cur_pos.x = f->self_vel.x = f->gr_vel = FLT_MAX;
        f->cur_pos.y = f->self_vel.y = f->dmg.x1830_percent = f->shield_health = -FLT_MAX;
        stocks[i] = INT_MIN;
    }
    fighters[0].cpu.buttons = UINT_MAX;
    fighters[0].cpu.x18 = fighters[0].cpu.xA4 = INT_MIN;
    begin(&fighters[0]);
    CHECK(ShowboatRecorder_Decision(&fighters[0], INT_MAX, INT_MIN, true));
    observe(&fighters[0], &fighters[1]);
    finish();
}
static void lifecycle(void)
{
    Fighter* f = &fighters[0];
    Fighter* t = &fighters[1];
    step(10, 0);
    ++f->x8_spawnNum; step(11, 0);
    ++t->x8_spawnNum; step(12, 0);
    rules.stkind = St_Kind_Last; step(13, 0);
    rules.match_kind = MatchKind_Time; step(14, 0);
    mode = GM_TRAINING; step(15, 0);
    rules.time_limit = 120; step(16, 0);
    rules.x20 = 0x100000000ULL; step(17, 0);
    rules.game_speed = 0.5f; step(18, 0);
    step(3, 0); /* Native frame rollback, not a complete match. */
    CHECK(ShowboatRecorder_Suspend(f));
    CHECK(ShowboatRecorder_Suspend(f));
    step(4, 0);
    CHECK(ShowboatRecorder_ResetSlot(0));
    step(5, 0);
    finish();
}
static void pending(void)
{
    Fighter* f = &fighters[0];
    begin(f);
    CHECK(ShowboatRecorder_Reason(f, 2, SBR_GEOMETRY_OR_WINDOW));
    CHECK(ShowboatRecorder_Event(f, SBR_EVENT_AERIAL_ACK));
    decision(f, 7);
    observe(f, &fighters[1]); /* Opening the segment must not clear pending. */
    frame = 2;
    begin(f);
    CHECK(ShowboatRecorder_Reason(f, 3, SBR_STARTED));
    CHECK(ShowboatRecorder_Event(f, SBR_EVENT_POWERSHIELD_CONTACT));
    decision(f, 10);
    rules.stkind = St_Kind_Last;
    observe(f, &fighters[1]); /* Nor may a context split clear pending. */
    frame = 3;
    begin(f);
    CHECK(ShowboatRecorder_Reason(f, 0, SBR_STARTED));
    CHECK(ShowboatRecorder_ResetSlot(0)); /* AI first-update reset is allowed. */
    CHECK(ShowboatRecorder_Reason(f, 4, SBR_SUCCESS));
    decision(f, 0);
    observe(f, &fighters[1]);
    frame = 4;
    begin(f);
    CHECK(ShowboatRecorder_Reason(f, 0, SBR_ACTIVE));
    frame = 5; observe(f, &fighters[1]); /* Stale pending cannot cross a frame. */
    frame = 6; observe(f, &fighters[1]); /* No Begin: NOT_EVALUATED and gap. */
    finish();
}
static void same_frame(void)
{
    step(1, 0);
    CHECK(ShowboatRecorder_ResetSlot(0));
    step(1, 1);
    rules.stkind = St_Kind_Last;
    step(1, 2);
    step(2, 2);
    finish();
}
static void repeated_clock(void)
{
    int i;
    for (i = 0; i < 125; ++i) { step(1, i % 2); }
    step(2, 0);
    finish();
}
static void stale(void)
{
    Fighter* old_owner = malloc(sizeof(Fighter));
    Fighter* old_target = malloc(sizeof(Fighter));
    assert(old_owner && old_target);
    memcpy(old_owner, &fighters[0], sizeof(Fighter));
    memcpy(old_target, &fighters[1], sizeof(Fighter));
    gobjs[0].user_data = old_owner;
    gobjs[1].user_data = old_target;
    begin(old_owner); decision(old_owner, 0); observe(old_owner, old_target);
    gobjs[1].user_data = &fighters[1];
    free(old_target);
    frame = 2;
    begin(old_owner); decision(old_owner, 0);
    observe(old_owner, old_target); /* ASan UAF if target argument is inspected. */
    observe(old_owner, &fighters[1]);
    gobjs[0].user_data = &fighters[0];
    free(old_owner);
    frame = 3; step(3, 0); /* ASan UAF if saved owner is inspected. */
    CHECK(ShowboatRecorder_Suspend(old_owner)); /* Must not suspend replacement. */
    CHECK(ShowboatRecorder_Reason(old_owner, 0, 3));
    CHECK(ShowboatRecorder_Event(old_owner, 127));
    CHECK(ShowboatRecorder_Decision(old_owner, 99, 11, true));
    observe(old_owner, &fighters[1]);
    step(4, 0);
    /* Remove current entities entirely, then teardown using only tokens. */
    primary[0] = primary[1] = NULL;
    CHECK(ShowboatRecorder_Suspend(&fighters[0]));
    finish();
}
static void teardown(void)
{
    int pass;
    for (pass = 0; pass < 2; ++pass) {
        Fighter* f = malloc(sizeof(Fighter));
        Fighter* t = malloc(sizeof(Fighter));
        assert(f && t);
        memcpy(f, &fighters[0], sizeof(Fighter));
        memcpy(t, &fighters[1], sizeof(Fighter));
        primary[0] = &gobjs[0]; primary[1] = &gobjs[1];
        gobjs[0].user_data = f; gobjs[1].user_data = t;
        frame = (u32)(pass + 1);
        begin(f); decision(f, 0); observe(f, t);
        primary[0] = primary[1] = NULL;
        gobjs[0].user_data = gobjs[1].user_data = NULL;
        free(f); free(t); /* BOTH saved tokens are now ASan-poisoned. */
        if (pass == 0) { CHECK(ShowboatRecorder_ResetSlot(0)); }
        else { CHECK(ShowboatRecorder_Suspend(f)); }
    }
    finish();
}
static void invalidation(void)
{
    step(1, 0);
    fighters[0].cpu.level = 8; step(2, 0);
    fighters[0].cpu.level = 9; step(3, 0);
    second[1] = &secondary; step(4, 0);
    second[1] = NULL; step(5, 0);
    second[0] = &secondary; step(6, 0);
    second[0] = NULL; step(7, 0);
    no_rules = true; step(8, 0);
    no_rules = false; step(9, 0);
    fighters[1].kind = FTKIND_FOX; step(10, 0);
    rules.stkind = St_Kind_Test; step(11, 0); /* No telemetry stage allowlist. */
    finish();
}
static void replacement(void)
{
    Fighter* t = malloc(sizeof(Fighter));
    assert(t);
    step(1, 0);
    memcpy(t, &fighters[1], sizeof(Fighter));
    gobjs[1].user_data = t;
    frame = 2; begin(&fighters[0]); decision(&fighters[0], 0); observe(&fighters[0], t);
    gobjs[1].user_data = &fighters[1]; free(t);
    step(3, 0);
    finish();
}
static void flags(void)
{
    Fighter* f = &fighters[0];
    /* Stale unrelated pointers/unions cannot mark standing as captured. */
    f->victim_gobj = f->x1A5C = &secondary;
    f->x1064_thrownHitbox.owner = &secondary;
    step(1, 0);
    f->motion_id = ftCo_MS_CapturePulledHi; step(2, 0);
    f->motion_id = ftCo_MS_ThrownF; step(3, 0);
    f->motion_id = ftCo_MS_ShoulderedWait; step(4, 0);
    f->motion_id = ftCo_MS_CaptureMewtwo; step(5, 0);
    f->motion_id = ftCo_MS_CaptureMasterHand; step(6, 0);
    f->motion_id = ftCo_MS_CaptureCrazyHand; step(7, 0);
    f->motion_id = ftCo_MS_Wait; step(8, 0);
    f->x221D_b6 = 1; step(9, 0);
    f->x221D_b6 = 0; f->x1988 = 1; step(10, 0); /* Same protection flag. */
    f->x1988 = 0; step(11, 0);
    entities.items = &secondary; step(12, 0);
    finish();
}
static void slots(void)
{
    int i;
    for (i = 0; i < 6; ++i) {
        int target = (i + 1) % 6, j;
        frame = (u32)(i + 1);
        for (j = 0; j < 6; ++j) { states[j] = j == i || j == target ? 2 : 0; }
        player_kind[i] = Gm_PKind_Cpu;
        begin(&fighters[i]); decision(&fighters[i], i); observe(&fighters[i], &fighters[target]);
        CHECK(ShowboatRecorder_ResetSlot(i));
    }
    /* Two CPU primaries observed in the same native frame are independent. */
    for (i = 0; i < 6; ++i) { states[i] = i < 2 ? 2 : 0; }
    frame = 7;
    begin(&fighters[0]); begin(&fighters[1]);
    CHECK(ShowboatRecorder_Reason(&fighters[0], 0, 3));
    CHECK(ShowboatRecorder_Reason(&fighters[1], 4, 15));
    decision(&fighters[0], 1); decision(&fighters[1], 2);
    observe(&fighters[0], &fighters[1]); observe(&fighters[1], &fighters[0]);
    CHECK(ShowboatRecorder_ResetSlot(-1)); CHECK(ShowboatRecorder_ResetSlot(6));
    finish();
}
static void invalid(const char* which)
{
    Fighter* f = &fighters[0];
    Fighter* t = &fighters[1];
    if (!strcmp(which, "level")) { f->cpu.level = 8; }
    else if (!strcmp(which, "mode")) { f->cpu.xC = 3; }
    else if (!strcmp(which, "kind")) { f->kind = FTKIND_FOX; }
    else if (!strcmp(which, "human")) { player_kind[0] = Gm_PKind_Human; }
    else if (!strcmp(which, "owner_secondary")) { second[0] = &secondary; }
    else if (!strcmp(which, "target_secondary")) { second[1] = &secondary; }
    else if (!strcmp(which, "owner_subflag")) { f->x221F_b4 = 1; }
    else if (!strcmp(which, "target_subflag")) { t->x221F_b4 = 1; }
    else if (!strcmp(which, "ally")) { rules.is_teams = 1; t->team = f->team; }
    else if (!strcmp(which, "third")) { states[2] = 2; }
    else if (!strcmp(which, "owner_slot")) { f->player_id = 255; }
    else if (!strcmp(which, "target_slot")) { t->player_id = 6; }
    else if (!strcmp(which, "owner_gobj")) { f->gobj = NULL; }
    else if (!strcmp(which, "target_gobj")) { t->gobj = &secondary; }
    else if (!strcmp(which, "missing")) { primary[1] = NULL; }
    else if (!strcmp(which, "inactive_slot")) { states[1] = 0; }
    else if (!strcmp(which, "null")) { t = NULL; }
    else if (!strcmp(which, "self")) { t = f; }
    else if (!strcmp(which, "bad_target")) { t = (Fighter*)(uintptr_t)1; }
    else if (!strcmp(which, "bad_owner")) { f = (Fighter*)(uintptr_t)1; }
    else if (!strcmp(which, "no_rules")) { no_rules = true; }
    else if (!strcmp(which, "bad_rules")) { rules.game_speed = NAN; }
    else { abort(); }
    begin(f); decision(f, 0); observe(f, t);
    CHECK(ShowboatRecorder_Suspend(f));
    finish();
    assert(report_calls == 0);
}
#define CASE(name) { #name, name }
int main(int argc, char** argv)
{
    unsigned i;
    static const struct { const char* name; void (*run)(void); } cases[] = {
        CASE(schema),
        CASE(sentinels),
        CASE(capacity_baseline),
        CASE(overflow),
        CASE(overflow_recovery),
        CASE(phase),
        CASE(periodic),
        CASE(changes),
        CASE(gaps),
        CASE(gates),
        CASE(exact_flush),
        CASE(nonfinite),
        CASE(extremes),
        CASE(lifecycle),
        CASE(pending),
        CASE(same_frame),
        CASE(repeated_clock),
        CASE(stale),
        CASE(teardown),
        CASE(invalidation),
        CASE(replacement),
        CASE(flags),
        CASE(slots),
    };
    assert(argc == 2);
    setup();
    if (!strncmp(argv[1], "invalid_", 8)) { invalid(argv[1] + 8); return 0; }
    for (i = 0; i < sizeof(cases) / sizeof(cases[0]); ++i) {
        if (!strcmp(argv[1], cases[i].name)) { cases[i].run(); return 0; }
    }
    abort();
}
