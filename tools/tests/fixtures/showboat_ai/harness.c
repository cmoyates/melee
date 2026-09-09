/* Deterministic HOST unit tests, NOT an emulator/in-game test.
 * Include production verbatim: no copied personality logic and no #define static.
 * See test_showboat_ai.py for scope, compiler setup, and how to run.
 */
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "showboat_ai.c"

static const char* case_name;
static int variant;
#define CHECK(expr) do { if (!(expr)) { \
    fprintf(stderr, "%s variant=%d, %s:%d: %s\n", \
            case_name, variant, __FILE__, __LINE__, #expr); \
    exit(1); \
} } while (0)

static Fighter fighters[SB_SLOTS];
static Fighter_GObj objects[SB_SLOTS];
static struct {
    Fighter_GObj* entity[SB_SLOTS];
    Fighter_GObj* secondary[SB_SLOTS];
    int player_state[SB_SLOTS], stocks[SB_SLOTS], invincible[SB_SLOTS];
    bool cpu[SB_SLOTS], ally, stock_match;
    float left[SB_SLOTS], right[SB_SLOTS];
    StKind stage;
    Vec3 floor_left[2], floor_right[2];
} world;
static struct TestCommonData common_data;
struct TestCommonData* p_ftCommonData = &common_data;
static struct TestEntities entities;
struct TestEntities* HSD_GObj_Entities = &entities;

enum { EV_RESTORE, EV_RESET, EV_COMBAT, EV_ABORT, EV_POST, EV_ACTION, EV_QUERY, EV_CLEAR,
       EV_MOVE, EV_MOVE_SUSPEND, EV_MOVE_RESET };
static int events[512], event_count;
static bool tracing;
static struct {
    bool owns_input, borrowed, post_overlay;
    Fighter* borrower;
    s8 saved_x;
    int resets[SB_SLOTS], restores, updates, aborts, posts, actions;
    int reported_action; /* configurable HUD/recorder query, not combat policy */
    Fighter* last_actor;
    Fighter* last_target;
} combat;
static struct {
    bool owns_input, active;
    Fighter* owner;
    int owner_slot, updates, suspends, resets[SB_SLOTS];
} movement;
/* Defense uses independent counters: default calls add NO legacy trace events.
 * Saved owners are identity tokens only, never dereferenced on reset/suspend. */
static struct {
    bool owns_input, perfect_on_update;
    int handoff_action; /* 0 native fallback, 11 observed-contact indicator */
    struct {
        Fighter* owner;
        int action;
        bool pending;
    } slots[SB_SLOTS];
    int updates, suspends, actions, takes, rewards, resets[SB_SLOTS];
    int clock, update_order, suspend_order, reset_order, take_order;
    int update_events, update_combat, update_movement;
    Fighter* last_actor;
    Fighter* last_target;
    struct CpuFighter emitted;
} defense;
static void event(int kind)
{
    if (tracing) {
        CHECK(event_count < (int) (sizeof(events) / sizeof(events[0])));
        events[event_count++] = kind;
    }
}
static int first_event(int kind)
{
    for (int i = 0; i < event_count; ++i) {
        if (events[i] == kind) { return i; }
    }
    return -1;
}
static int clears, scripts, writes;
static struct TestFighterData fighter_data;
struct TestFighterData* Fighter_804D64FC = &fighter_data;
static unsigned char air_table[32], ground_table[32];
static Fighter* const self = &fighters[0];
static Fighter* const target = &fighters[1];
static SB_State* const state = &sb_states[0];

#include "recording_spies.c"
#include "safety_spies.c"

static void valid_slot(int slot) { CHECK(slot >= 0 && slot < SB_SLOTS); }
StKind Stage_80225194(void) { event(EV_QUERY); return world.stage; }
void mpFloorGetLeft(int line_id, Vec3* out)
{
    event(EV_QUERY); CHECK(line_id >= 0 && line_id < 2); CHECK(out != NULL);
    *out = world.floor_left[line_id];
}
void mpFloorGetRight(int line_id, Vec3* out)
{
    event(EV_QUERY); CHECK(line_id >= 0 && line_id < 2); CHECK(out != NULL);
    *out = world.floor_right[line_id];
}
Fighter_GObj* Player_GetEntity(int slot)
{ event(EV_QUERY); valid_slot(slot); return world.entity[slot]; }
Fighter_GObj* Player_GetEntityAtIndex(int slot, int index)
{
    valid_slot(slot); CHECK(index == 0 || index == 1);
    return index == 0 ? world.entity[slot] : world.secondary[slot];
}
int Player_GetPlayerState(int slot)
{ valid_slot(slot); return world.player_state[slot]; }
int Player_GetStocks(int slot)
{ valid_slot(slot); return world.stocks[slot]; }
bool gm_8016B094(void) { return world.stock_match; }
bool mpColl_IsOnPlatform(CollData* data) { return data->on_platform; }
bool ftCo_800A2040(Fighter* fp)
{ event(EV_QUERY); valid_slot(fp->player_id); return world.cpu[fp->player_id]; }
bool ftCo_IsAlly(Fighter* fp, Fighter* other)
{ CHECK(fp != other); return world.ally; }
float ftCo_800A2A70(Fighter* fp, bool right)
{
    valid_slot(fp->player_id);
    if (fp->ground_or_air == GA_Air) { return -1.0f; }
    return right ? world.right[fp->player_id] : world.left[fp->player_id];
}
int ftColl_8007B868(Fighter_GObj* gobj)
{
    CHECK(gobj && GET_FIGHTER(gobj));
    valid_slot(GET_FIGHTER(gobj)->player_id);
    return world.invincible[GET_FIGHTER(gobj)->player_id];
}
void OSReport(const char* format, ...)
{
    CHECK(format != NULL);
    if (safety.watching_logs) {
        va_list args;
        va_start(args, format);
        int n = vsnprintf(safety.last_log, sizeof(safety.last_log), format, args);
        va_end(args);
        CHECK(n >= 0 && n < (int) sizeof(safety.last_log));
        ++safety.logs;
        recording_mark(REC_LOG, NULL, 0, 0);
    }
}

/* Faithful subset of ftcmdscript.c writers. Finalizing does NOT execute the VM.
 * In particular Done does not release held buttons/sticks. Cancellation tests
 * inspect input before interpret(), catching a missing synchronous clear. */
void ftCo_800B4A78(Fighter* fp)
{
    struct CpuFighter* cpu = &fp->cpu;
    event(EV_CLEAR);
    ++clears;
    cpu->buttons = 0;
    cpu->lstick.x = cpu->lstick.y = 0;
    cpu->cstick.x = cpu->cstick.y = 0;
    cpu->rtrigger = cpu->ltrigger = 0;
    cpu->csP = NULL;
    cpu->command_duration = 0;
    cpu->write_pos = cpu->buffer;
}
void ftCo_800B463C(Fighter* fp, u8 command)
{
    struct CpuFighter* cpu = &fp->cpu;
    CHECK(cpu->write_pos >= cpu->buffer);
    CHECK(cpu->write_pos < cpu->buffer + sizeof(cpu->buffer));
    *cpu->write_pos++ = command;
    ++writes;
}
void ftCo_800B46B8(Fighter* fp, u8 command, u8 argument)
{ ftCo_800B463C(fp, command); ftCo_800B463C(fp, argument); }
void ftCo_800B49F4(Fighter* fp)
{
    ftCo_800B463C(fp, CpuCmd_Done);
    fp->cpu.csP = fp->cpu.buffer;
    fp->cpu.command_duration = 1;
    ++scripts;
}
static void interpret(Fighter* fp)
{
    struct CpuFighter* cpu = &fp->cpu;
    if (!cpu->csP || !cpu->command_duration) { return; }
    if (--cpu->command_duration) { return; }
    for (;;) {
        CHECK(cpu->csP >= cpu->buffer && cpu->csP < cpu->write_pos);
        switch (*cpu->csP++) {
        case CpuCmd_PressUp: cpu->buttons |= HSD_PAD_DPADUP; break;
        case CpuCmd_PressB: cpu->buttons |= HSD_PAD_B; break;
        case CpuCmd_SetLstickX:
            CHECK(cpu->csP < cpu->write_pos);
            cpu->lstick.x = (s8) *cpu->csP++;
            break;
        case CpuCmd_SetLstickY:
            CHECK(cpu->csP < cpu->write_pos);
            cpu->lstick.y = (s8) *cpu->csP++;
            break;
        case CpuCmd_Done:
            CHECK(cpu->csP == cpu->write_pos);
            cpu->csP = NULL;
            recording_mark(REC_VM, fp, 0, 0);
            return;
        default: CHECK(!"unimplemented input opcode (extend stub explicitly)");
        }
    }
}

/* These spies model only the main/combat handoff, never combat decisions. */
void ShowboatCombat_ResetSlot(int slot)
{
    valid_slot(slot); event(EV_RESET); ++combat.resets[slot];
    if (combat.borrower && combat.borrower->player_id == slot) {
        /* Reset drops bookkeeping: Restore must happen BEFORE this. */
        combat.borrowed = false;
        combat.borrower = NULL;
    }
}
void ShowboatCombat_RestoreInput(Fighter* fp)
{
    CHECK(fp != NULL); event(EV_RESTORE); ++combat.restores;
    if (combat.borrowed && combat.borrower == fp) {
        fp->cpu.lstick.x = combat.saved_x;
        combat.borrowed = false;
    }
    recording_mark(REC_RESTORE, fp, 0, 0);
}
bool ShowboatCombat_Update(Fighter* fp, Fighter* rival)
{
    CHECK(fp && fp != rival);
    if (rival == NULL) {
        /* Explicit abort delegation, not a permissive missing-target combat
         * opportunity. Real fingerprint/release semantics have their own suite. */
        event(EV_ABORT); ++combat.aborts; return false;
    }
    event(EV_COMBAT); ++combat.updates;
    recording_mark(REC_COMBAT, fp, 0, 0);
    combat.last_actor = fp; combat.last_target = rival;
    if (!combat.owns_input) { return false; }
    ftCo_800B4A78(fp);
    fp->cpu.xA4 = 0;
    ftCo_800B463C(fp, CpuCmd_PressB); /* identifiable mock-owned script */
    ftCo_800B49F4(fp);
    return true;
}
void ShowboatCombat_PostInput(Fighter* fp)
{
    CHECK(fp != NULL); event(EV_POST); ++combat.posts; combat.last_actor = fp;
    /* Explicit opt-in output marker to distinguish VM -> combat -> safety. */
    if (combat.post_overlay) { fp->cpu.lstick.x = -91; }
    memcpy(&recording.post_cpu, &fp->cpu, sizeof(fp->cpu));
    recording_mark(REC_POST, fp, 0, 0);
}
int ShowboatCombat_GetAction(Fighter* fp)
{
    CHECK(fp != NULL); event(EV_ACTION); ++combat.actions;
    return combat.reported_action;
}

/* Movement is an explicit orchestration spy here, not a fake wavedash engine.
 * Actual jump/dodge/landing sequences and cleanup have a separate C suite. */
void ShowboatMovement_ResetSlot(int slot)
{
    valid_slot(slot); event(EV_MOVE_RESET); ++movement.resets[slot];
    if (movement.owner_slot == slot) { movement.active = false; movement.owner = NULL; }
}
void ShowboatMovement_Suspend(Fighter* fp)
{
    CHECK(fp); event(EV_MOVE_SUSPEND); ++movement.suspends;
    if (movement.owner == fp) { movement.active = false; }
}
int ShowboatMovement_GetAction(Fighter* fp)
{
    CHECK(fp); return movement.active && movement.owner == fp ? 9 : 0;
}
bool ShowboatMovement_Update(Fighter* fp, Fighter* rival)
{
    CHECK(fp && rival && fp != rival); event(EV_MOVE); ++movement.updates;
    recording_mark(REC_MOVEMENT, fp, 0, 0);
    movement.active = movement.owns_input;
    if (!movement.owns_input) { return false; }
    movement.owner = fp; movement.owner_slot = fp->player_id;
    ftCo_800B4A78(fp); fp->cpu.xA4 = 0;
    ftCo_800B46B8(fp, CpuCmd_SetLstickX, 66); /* distinguish from combat's B */
    ftCo_800B49F4(fp);
    return true;
}

/* Main/defense orchestration ONLY, not a shield/collision/ReleaseR emulator.
 * Tests explicitly inject verified contact; an owned attempt or action 11 alone
 * never creates a reward. Actual fingerprint/release/identity policy is tested
 * in the separate defense module suite. */
void ShowboatDefense_ResetSlot(int slot)
{
    valid_slot(slot); ++defense.resets[slot];
    defense.reset_order = ++defense.clock;
    memset(&defense.slots[slot], 0, sizeof(defense.slots[slot]));
}
void ShowboatDefense_Suspend(Fighter* fp)
{
    CHECK(fp); valid_slot(fp->player_id); ++defense.suspends;
    defense.suspend_order = ++defense.clock;
    if (defense.slots[fp->player_id].owner == fp) {
        memset(&defense.slots[fp->player_id], 0,
               sizeof(defense.slots[fp->player_id]));
    }
}
int ShowboatDefense_GetAction(Fighter* fp)
{
    CHECK(fp); valid_slot(fp->player_id); ++defense.actions;
    return defense.slots[fp->player_id].owner == fp ?
        defense.slots[fp->player_id].action : 0;
}
bool ShowboatDefense_Update(Fighter* fp, Fighter* rival)
{
    CHECK(fp && rival && fp != rival); valid_slot(fp->player_id);
    ++defense.updates; defense.update_order = ++defense.clock;
    recording_mark(REC_DEFENSE, fp, 0, 0);
    defense.update_events = event_count;
    defense.update_combat = combat.updates;
    defense.update_movement = movement.updates;
    defense.last_actor = fp; defense.last_target = rival;
    if (defense.owns_input) {
        defense.slots[fp->player_id].owner = fp;
        defense.slots[fp->player_id].action = 10;
    } else if (defense.slots[fp->player_id].owner == fp &&
               defense.slots[fp->player_id].action == 10) {
        defense.slots[fp->player_id].action = defense.handoff_action;
    }
    if (defense.perfect_on_update) {
        CHECK(defense.slots[fp->player_id].owner == fp);
        defense.slots[fp->player_id].pending = true;
        defense.slots[fp->player_id].action = 11;
        defense.perfect_on_update = false;
    }
    if (!defense.owns_input) { return false; }
    ftCo_800B4A78(fp); fp->cpu.xA4 = 0;
    ftCo_800B46B8(fp, CpuCmd_SetLstickY, 47); /* unique, NOT simulated R */
    ftCo_800B49F4(fp);
    memcpy(&defense.emitted, &fp->cpu, sizeof(defense.emitted));
    return true;
}
bool ShowboatDefense_TakePerfect(Fighter* fp)
{
    CHECK(fp); valid_slot(fp->player_id); ++defense.takes;
    defense.take_order = ++defense.clock;
    if (defense.slots[fp->player_id].owner != fp ||
        !defense.slots[fp->player_id].pending) { return false; }
    defense.slots[fp->player_id].pending = false;
    ++defense.rewards;
    return true;
}

/* Compare EVERY exposed Fighter field, allowing ONLY CPU script/input writes
 * and invalidation of the cached vanilla attack selection (cpu.xA4).
 * This includes motion, position, velocities, facing, damage, animation frame,
 * spawn, ownership, forced flags, CPU scenario and configuration, and target.
 * This is a structural host guard, not an assertion about the real PPC layout. */
static void unchanged_except_input(const Fighter* before, const Fighter* after)
{
    Fighter masked;
    memcpy(&masked, after, sizeof(masked));
#define ALLOW(field) memcpy(&masked.cpu.field, &before->cpu.field, sizeof(masked.cpu.field))
    ALLOW(buttons); ALLOW(lstick); ALLOW(cstick);
    ALLOW(ltrigger); ALLOW(rtrigger); ALLOW(buffer);
    ALLOW(write_pos); ALLOW(csP); ALLOW(command_duration); ALLOW(xA4);
#undef ALLOW
    CHECK(memcmp(before, &masked, sizeof(masked)) == 0);
}
static bool update(Fighter* fp)
{
    Fighter before[SB_SLOTS];
    Fighter_GObj old_objects[SB_SLOTS];
    unsigned char old_world[sizeof(world)];
    int old_scripts = scripts;
#if !SHOWBOAT_RECORDER
    int old_actions = combat.actions;
#endif
    bool result;
    memcpy(before, fighters, sizeof(before));
    memcpy(old_objects, objects, sizeof(objects));
    memcpy(old_world, &world, sizeof(world));
    struct TestCommonData old_common = common_data;
    struct TestEntities old_entities = entities;
    event_count = 0; tracing = true;
    result = ShowboatAI_Update(fp);
    tracing = false;
    CHECK(event_count > 0 && events[0] == EV_RESTORE);
#if !SHOWBOAT_RECORDER
    CHECK(combat.actions == old_actions); /* Update needs no getter; PostInput does */
#endif
    CHECK(memcmp(&old_common, &common_data, sizeof(common_data)) == 0);
    CHECK(memcmp(&old_entities, &entities, sizeof(entities)) == 0);
    for (int i = 0; i < SB_SLOTS; ++i) {
        if (&fighters[i] == fp) {
            unchanged_except_input(&before[i], &fighters[i]);
        } else {
            CHECK(memcmp(&before[i], &fighters[i], sizeof(Fighter)) == 0);
        }
    }
    CHECK(memcmp(old_world, &world, sizeof(world)) == 0);
    CHECK(memcmp(old_objects, objects, sizeof(objects)) == 0);
    if (result) {
        CHECK(scripts == old_scripts + 1);
        CHECK(fp->cpu.csP == fp->cpu.buffer);
        CHECK(fp->cpu.command_duration == 1);
        CHECK(fp->cpu.xA4 == 0);
        CHECK(fp->cpu.write_pos > fp->cpu.buffer);
        CHECK(fp->cpu.write_pos - fp->cpu.buffer <= 5);
        CHECK(fp->cpu.write_pos[-1] == CpuCmd_Done);
    } else {
        CHECK(scripts == old_scripts);
    }
    return result;
}
static bool frame(void)
{
    bool result = update(self);
    if (result) { interpret(self); }
    return result;
}
static void neutral(Fighter* fp)
{
    CHECK(fp->cpu.buttons == 0);
    CHECK(fp->cpu.lstick.x == 0 && fp->cpu.lstick.y == 0);
    CHECK(fp->cpu.cstick.x == 0 && fp->cpu.cstick.y == 0);
    CHECK(fp->cpu.ltrigger == 0 && fp->cpu.rtrigger == 0);
}
static void dirty_controls(Fighter* fp)
{
    fp->cpu.buttons = 0xffff;
    fp->cpu.lstick.x = 77; fp->cpu.lstick.y = -100;
    fp->cpu.cstick.x = -44; fp->cpu.cstick.y = 55;
    fp->cpu.ltrigger = 123; fp->cpu.rtrigger = 234;
}
static void dirty_input(Fighter* fp)
{
    dirty_controls(fp);
    fp->cpu.xA4 = 123;
    fp->cpu.buffer[0] = CpuCmd_PressB;
    fp->cpu.buffer[1] = CpuCmd_Done;
    fp->cpu.write_pos = fp->cpu.buffer + 2;
    fp->cpu.csP = fp->cpu.buffer;
    fp->cpu.command_duration = 1;
}
static void setup(void)
{
    safety_verified();
    memset(&safety, 0, sizeof(safety));
    tracing = false; event_count = 0;
    memset(&recording, 0, sizeof(recording));
    memset(&combat, 0, sizeof(combat));
    combat.reported_action = 5;
    memset(&movement, 0, sizeof(movement));
    memset(&defense, 0, sizeof(defense));
    memset(&test_taunt_rules, 0, sizeof(test_taunt_rules));
    memset(test_taunt_removal, 0, sizeof(test_taunt_removal));
    test_taunt_mode = GM_TITLE; test_taunt_elimination = false;
    memset(&common_data, 0, sizeof(common_data));
    memset(&entities, 0, sizeof(entities));
    memset(fighters, 0, sizeof(fighters));
    memset(objects, 0, sizeof(objects));
    memset(&world, 0, sizeof(world));
    for (int i = 0; i < SB_SLOTS; ++i) {
        Fighter* fp = &fighters[i];
        ShowboatAI_ResetSlot(i);
        objects[i].user_data = fp;
        fp->gobj = &objects[i];
        fp->player_id = (u8) i;
        fp->kind = FTKIND_CAPTAIN;
        fp->x8_spawnNum = 100 + i;
        fp->motion_id = ftCo_MS_Wait;
        fp->ground_or_air = GA_Ground;
        fp->facing_dir = 1.0f;
        fp->cur_pos.x = i * 100.0f;
        fp->cur_pos.z = 2.5f;
        fp->self_vel.z = 0.125f;
        fp->cpu.level = 9; fp->cpu.xC = 4; fp->cpu.x18 = 1;
        fp->cpu.xA4 = 123;
        fp->cpu.xFA_b5 = true;
        fp->cpu.write_pos = fp->cpu.buffer;
        world.entity[i] = &objects[i];
        world.player_state[i] = i < 2 ? 2 : 0;
        world.stocks[i] = 4;
        world.cpu[i] = true;
        world.left[i] = world.right[i] = 100.0f;
    }
    world.stock_match = true;
    world.stage = St_Kind_Last;
    world.floor_left[0] = (Vec3) { -100, 0, 0 };
    world.floor_right[0] = (Vec3) { 100, 0, 0 };
    world.floor_left[1] = (Vec3) { -100, 0, 0 };
    world.floor_right[1] = (Vec3) { 100, 0, 0 };
    common_data.x5D0 = 60;
    memset(&fighter_data, 0, sizeof(fighter_data));
    memset(air_table, 0xA5, sizeof(air_table));
    memset(ground_table, 0x5A, sizeof(ground_table));
    fighter_data.x8[FTKIND_CAPTAIN] = air_table;
    clears = scripts = writes = 0;
    /* Setup's bookkeeping resets must not leak into recorder observations. */
    memset(&recording, 0, sizeof(recording));
}
static void init(void)
{
    setup();
    CHECK(!frame());
    CHECK(state->owner == self && state->ego == SB_BASE_EGO);
}
/* Select a deterministic success/failure independently of SB_Roll. */
static u32 seed_for(int chance, bool success)
{
    for (u32 seed = 0; seed < 10000; ++seed) {
        u32 next = seed * 1664525U + 1013904223U;
        if ((((next >> 16) % 100) < (u32) chance) == success) { return seed; }
    }
    CHECK(!"no suitable RNG seed");
    return 0;
}
static void taunt_context(bool success)
{
    init(); self->cpu.xA4 = 0;
    state->random = seed_for(80, success);
    target->motion_id = ftCo_MS_DeadDown;
    target->mv.co.unk_deadleft.x40 = 20;
    /* The actual KO edge supplies ego +22 and celebration. */
}
static void whiff_context(bool success)
{
    init();
    state->ego = 60;
    state->random = seed_for(50, success);
    self->cpu.xA4 = 0;
    world.stage = St_Kind_Story; /* isolate crouch swagger from FD/BF dance */
    target->cur_pos.x = 70;
    target->motion_id = ftCo_MS_Attack11;
    target->cur_anim_frame = 18;
    target->facing_dir = 1; /* opponent is swinging AWAY from self */
}
static void punch_context(bool success)
{
    init(); self->cpu.xA4 = 0;
    state->ego = 85;
    state->random = seed_for(35, success);
    target->cur_pos.x = 30;
    target->motion_id = ftCo_MS_Furafura;
    target->grab_timer = 301;
}
/* Dirtied held channels still belong to the exact preceding personality VM.
 * Replacement scripts are a different contract: dedicated regressions below
 * require preserving their entire CPU snapshot, not blindly neutralizing it. */
static void dirty_owned_input(void)
{
    if (state->script_size == 0) {
        /* Only manually seeded action tests need an initial owned VM. */
        self->cpu.xA4 = 0;
        ftCo_800B4A78(self);
        ftCo_800B46B8(self, CpuCmd_SetLstickY, (u8) -100);
        SB_FinishInput(self, state);
        interpret(self);
    }
    dirty_controls(self);
}
static void expect_cancel(void)
{
    dirty_owned_input();
    int old_clears = clears;
    int selected = self->cpu.xA4;
    CHECK(!update(self)); /* no interpreter: inputs must already be clear */
    CHECK(state->action == SB_NONE);
    CHECK(clears == old_clears + 1);
    neutral(self);
    CHECK(self->cpu.csP == NULL && self->cpu.command_duration == 0);
    CHECK(self->cpu.write_pos == self->cpu.buffer);
    CHECK(self->cpu.xA4 == selected);
}
static void expect_ignored(void)
{
    struct CpuFighter before;
    dirty_input(self);
    memcpy(&before, &self->cpu, sizeof(before));
    CHECK(!update(self));
    CHECK(state->owner == NULL);
    CHECK(memcmp(&before, &self->cpu, sizeof(before)) == 0);
    CHECK(clears == 0 && writes == 0);
}

static void test_opt_in_exclusions(void)
{
    for (variant = 0; variant <= 10; ++variant) {
        if (variant == 9) { continue; }
        setup(); self->cpu.level = variant; expect_ignored();
    }
    for (variant = 0; variant < FTKIND_MAX; ++variant) {
        if (variant == FTKIND_CAPTAIN) { continue; }
        setup(); self->kind = (FighterKind) variant; expect_ignored();
    }
    for (variant = 0; variant < 20; ++variant) {
        if (variant == 4) { continue; }
        setup(); self->cpu.xC = variant; expect_ignored();
    }
    setup(); world.cpu[0] = false; expect_ignored(); /* human */
    setup(); self->x221F_b3 = true; expect_ignored(); /* secondary fighter */
    setup(); world.entity[0] = &objects[2]; expect_ignored();
    setup(); self->player_id = SB_SLOTS; expect_ignored();
    setup(); self->player_id = 255; expect_ignored();
}
static void test_singles_only(void)
{
    setup(); world.player_state[1] = 0; expect_ignored();
    setup(); world.player_state[2] = 2; expect_ignored();
    setup(); world.entity[1] = NULL; expect_ignored();
    setup(); world.ally = true; expect_ignored();
    setup(); world.secondary[1] = &objects[2]; expect_ignored();
    setup(); world.secondary[1] = &objects[2]; fighters[2].x221F_b3 = true;
    CHECK(!frame()); CHECK(state->owner == self); /* inactive partner */
    setup(); world.secondary[1] = &objects[1]; /* same entity, not a second attacker */
    CHECK(!frame()); CHECK(state->owner == self);
    setup(); world.player_state[2] = 1; /* inactive slot is not an opponent */
    CHECK(!frame()); CHECK(state->owner == self && state->opponent_slot == 1);
}
static void test_initialization_baselines(void)
{
    setup(); self->dmg.x1830_percent = 40; target->dmg.x1830_percent = 70;
    world.stocks[0] = 2; world.stocks[1] = 1;
    target->motion_id = ftCo_MS_DeadDown;
    CHECK(!frame());
    CHECK(state->ego == 55 && state->tick == 1);
    CHECK(state->percent == 40 && state->opponent_percent == 70);
    CHECK(state->stocks == 2 && state->opponent_stocks == 1);
    CHECK(state->opponent_dead && state->celebration == 0);
    CHECK(state->spawn == (u32) self->x8_spawnNum);
    CHECK(state->random == (u32) self->x8_spawnNum * 747796405U + 1);
    CHECK(clears == 0 && writes == 0);
}
static void test_reset_isolated_and_bounds(void)
{
    SB_State saved[SB_SLOTS], zero = { 0 };
    setup();
    for (int i = 0; i < SB_SLOTS; ++i) {
        sb_states[i].ego = 90 + i; sb_states[i].owner = &fighters[i];
        sb_states[i].action = SB_SWAGGER; sb_states[i].random = 123 + i;
    }
    memcpy(saved, sb_states, sizeof(saved));
    ShowboatAI_ResetSlot(-1); ShowboatAI_ResetSlot(SB_SLOTS);
    CHECK(memcmp(saved, sb_states, sizeof(saved)) == 0);
    ShowboatAI_ResetSlot(2);
    CHECK(memcmp(&sb_states[2], &zero, sizeof(zero)) == 0);
    for (int i = 0; i < SB_SLOTS; ++i) {
        if (i != 2) { CHECK(memcmp(&saved[i], &sb_states[i], sizeof(zero)) == 0); }
    }
    ShowboatAI_ResetSlot(2); /* idempotent */
    ShowboatAI_ResetSlot(0); CHECK(!frame()); CHECK(state->ego == 55);
}
static void test_owner_replacement_and_stale_identity(void)
{
    init(); state->ego = 99; state->serious = 100; state->cooldown = 200;
    /* Freed owner identity must not be dereferenced, even during reinitialization. */
    state->owner = (Fighter*) (uintptr_t) 1;
    CHECK(!frame()); CHECK(state->owner == self && state->ego == 55);
    CHECK(state->serious == 0 && state->cooldown == 0);
    fighters[2].player_id = 0; world.entity[0] = &objects[2];
    state->ego = 90;
    CHECK(!update(&fighters[2]));
    CHECK(state->owner == &fighters[2] && state->ego == 55);
    CHECK(state->spawn == (u32) fighters[2].x8_spawnNum);
}
static void test_opponent_slot_rebaseline(void)
{
    init(); state->ego = 99;
    world.player_state[1] = 0; world.player_state[2] = 2;
    fighters[2].dmg.x1830_percent = 85; world.stocks[2] = 1;
    CHECK(!frame());
    CHECK(state->opponent_slot == 2 && state->ego == 55);
    CHECK(state->opponent_percent == 85 && state->opponent_stocks == 1);
    CHECK(state->celebration == 0);
}
static void test_damage_gains_and_clamps(void)
{
    init(); target->dmg.x1830_percent = 10;
    CHECK(!frame()); CHECK(state->ego == 61);
    CHECK(!frame()); CHECK(state->ego == 61); /* delta, not total */
    target->dmg.x1830_percent += 100;
    CHECK(!frame()); CHECK(state->ego == 73); /* per-update cap */
    state->ego = 99; target->dmg.x1830_percent += 1;
    CHECK(!frame()); CHECK(state->ego == 100);
    SB_Ego(self, state, -500, "test clamp"); CHECK(state->ego == 0);
    SB_Ego(self, state, 500, "test clamp"); CHECK(state->ego == 100);
}
static void test_flashy_hit_celebration(void)
{
    const int motions[] = { ftCa_MS_SpecialN, ftCo_MS_AttackAirF, ftCo_MS_AttackAirLw };
    for (variant = 0; variant < 3; ++variant) {
        init(); self->motion_id = motions[variant];
        target->dmg.x1830_percent = 10;
        CHECK(!frame()); CHECK(state->ego == 69 && state->celebration == 120);
        CHECK(!frame()); CHECK(state->ego == 69 && state->celebration == 119);
    }
    init(); target->motion_id = ftCo_MS_DeadDown; state->opponent_dead = true;
    target->dmg.x1830_percent = 20;
    CHECK(!frame()); CHECK(state->ego == 55); /* not a hit on a live opponent */
    init(); self->x221C_b6 = true; target->dmg.x1830_percent = 20;
    CHECK(!frame()); CHECK(state->ego == 51); /* danger only, no gain */
}
static void test_damage_punishment_and_trade_priority(void)
{
    whiff_context(true); CHECK(frame());
    state->ego = 90; self->dmg.x1830_percent = 10;
    target->dmg.x1830_percent = 40; /* trade must not award confidence */
    expect_cancel();
    CHECK(state->ego == 72); /* -(3 + floor(10 * .5)) -10 */
    CHECK(state->serious == SB_SERIOUS_FRAMES && state->recent_style == 0);
    CHECK(state->celebration == 0);
    CHECK(!frame()); CHECK(state->ego == 72 && state->serious == 89);
    self->dmg.x1830_percent += 2;
    CHECK(!frame()); CHECK(state->ego == 68); /* punishment charged only once */
    self->dmg.x1830_percent = 0;
    CHECK(!frame()); CHECK(state->ego == 68 && state->percent == 0);
    self->dmg.x1830_percent = 1;
    CHECK(!frame()); CHECK(state->ego == 65); /* new baseline after healing */
}
static void test_punishment_window_expiry(void)
{
    init(); state->ego = 90; state->recent_style = 1;
    self->dmg.x1830_percent = 10;
    CHECK(!frame()); CHECK(state->ego == 82 && state->recent_style == 0);
}
static void check_new_life_order(bool spawn_first)
{
    whiff_context(true); CHECK(frame()); state->ego = 90;
    self->dmg.x1830_percent = 35;
    if (spawn_first) { ++self->x8_spawnNum; } else { --world.stocks[0]; }
    expect_cancel();
    CHECK(state->ego == 75 && state->serious == 120);
    CHECK(state->percent == 35 && state->celebration == 0);
    self->dmg.x1830_percent = 0;
    if (spawn_first) { --world.stocks[0]; } else { ++self->x8_spawnNum; }
    CHECK(!frame()); CHECK(state->ego == 75 && state->serious == 120);
    CHECK(state->spawn == (u32) self->x8_spawnNum && state->stocks == 3);
    CHECK(!frame()); CHECK(state->ego == 75 && state->serious == 119);
}
static void test_stock_before_spawn_charged_once(void)
{ check_new_life_order(false); }
static void test_spawn_before_stock_charged_once(void)
{
    /* Robustness probe: whether native accounting can arrive in this order
     * must be established separately in game. It is not simulated here. */
    check_new_life_order(true);
}
static void test_timed_mode_ignores_stock_counters(void)
{
    init(); world.stock_match = false; state->ego = 70;
    --world.stocks[0]; --world.stocks[1];
    CHECK(!frame()); CHECK(state->ego == 70 && state->serious == 0);
    CHECK(state->celebration == 0);
    ++self->x8_spawnNum;
    CHECK(!frame()); CHECK(state->ego == 55 && state->serious == 120);
}
static void test_ko_event_deduplication(void)
{
    for (variant = 0; variant < 2; ++variant) {
        init(); state->cooldown = 1000;
        if (variant == 0) { target->motion_id = ftCo_MS_DeadDown; }
        else { --world.stocks[1]; }
        CHECK(!frame()); CHECK(state->ego == 77 && state->ko_lockout == 240);
        CHECK(state->celebration == 180);
        if (variant == 0) { --world.stocks[1]; }
        else { target->motion_id = ftCo_MS_DeadDown; }
        CHECK(!frame()); CHECK(state->ego == 77 && state->ko_lockout == 239);
        target->motion_id = ftCo_MS_Rebirth;
        CHECK(!frame()); CHECK(!state->opponent_dead);
        state->ko_lockout = 1;
        target->motion_id = ftCo_MS_DeadDown;
        CHECK(!frame()); CHECK(state->ego == 99 && state->ko_lockout == 240);
    }
}
static void test_danger_edges_and_serious_recovery(void)
{
    init(); state->ego = 90; state->celebration = 100;
    self->x221C_b6 = true;
    CHECK(!frame()); CHECK(state->ego == 86 && state->serious == 30);
    CHECK(state->danger && state->celebration == 99);
    for (int i = 0; i < 10; ++i) { CHECK(!frame()); }
    CHECK(state->ego == 86 && state->serious == 30);
    self->x221C_b6 = false;
    CHECK(!frame()); CHECK(!state->danger && state->serious == 29);
    state->tick = 0;
    for (int i = 0; i < 29; ++i) { CHECK(!frame()); }
    CHECK(state->serious == 0);
    int old = state->ego;
    self->ground_or_air = GA_Air; self->cpu.xFA_b5 = false;
    CHECK(!frame()); CHECK(state->ego == old - 4 && state->danger);
}
static void test_advantage_and_confidence_settling(void)
{
    for (variant = 0; variant < 3; ++variant) {
        setup();
        if (variant == 0) { world.stocks[1] = 3; }
        if (variant == 1) { target->dmg.x1830_percent = 30; world.stock_match = false; }
        if (variant == 2) { target->dmg.x1830_percent = 100; self->dmg.x1830_percent = 79; }
        for (int i = 0; i < SB_ADVANTAGE_PERIOD - 1; ++i) { CHECK(!frame()); }
        CHECK(state->ego == 55);
        CHECK(!frame()); CHECK(state->ego == 59 && state->tick == 0);
    }
    init(); state->ego = 60; state->tick = SB_ADVANTAGE_PERIOD - 1;
    CHECK(!frame()); CHECK(state->ego == 59);
    state->ego = 20; state->tick = SB_ADVANTAGE_PERIOD - 1;
    CHECK(!frame()); CHECK(state->ego == 20); /* does not settle upward */
    state->ego = 60; state->serious = 10; state->tick = SB_ADVANTAGE_PERIOD - 1;
    world.stocks[1] = 3; state->opponent_stocks = 3;
    CHECK(!frame()); CHECK(state->ego == 59); /* no advantage reward while serious */
}
static void test_taunt_finite_native_script(void)
{
    const int appeals[] = { ftCo_MS_AppealSR, ftCo_MS_AppealSL };
    for (variant = 0; variant < 2; ++variant) {
        taunt_context(true); self->cpu.lstick.x = 77; self->cpu.lstick.y = -100;
        CHECK(frame()); CHECK(state->action == SB_TAUNT && state->age == 1);
        CHECK(state->ego == 77 && state->taunt_cooldown == 180);
        CHECK(state->cooldown == 0);
        CHECK(state->recent_style == 75 && state->celebration == 0);
        CHECK(self->cpu.write_pos - self->cpu.buffer == 1); neutral(self);
        CHECK(frame()); CHECK(state->age == 2);
        CHECK(self->cpu.buffer[0] == CpuCmd_PressUp);
        CHECK(self->cpu.buffer[1] == CpuCmd_Done);
        CHECK(self->cpu.buttons == HSD_PAD_DPADUP && self->cpu.lstick.y == 0);
        self->motion_id = appeals[variant]; /* engine would enter taunt */
        CHECK(frame()); CHECK(state->age == 3); neutral(self);
        expect_cancel(); /* completion returns control, not a perpetual override */
        CHECK(scripts == 3);
    }
}
static void test_taunt_context_requirements(void)
{
    for (variant = 0; variant < 24; ++variant) {
        taunt_context(true);
        state->opponent_dead = true; state->celebration = 100; state->ego = 60;
        switch (variant) {
        case 0: self->motion_id = ftCo_MS_AttackS4S; break;
        case 1: state->celebration = 1; break; /* countdown before decision */
        case 2: target->motion_id = ftCo_MS_Wait; target->x221C_b6 = true; break;
        case 3: target->motion_id = ftCo_MS_Rebirth; break;
        case 4: target->motion_id = ftCo_MS_RebirthWait; break;
        case 5: target->mv.co.unk_deadleft.x40 = 19; break; /* only 79 remaining */
        case 6: target->mv.co.unk_deadleft.x40 = 0; common_data.x5D0 = 100; break;
        case 7: target->mv.co.unk_deadleft.x40 = -1; common_data.x5D0 = 100; break;
        case 8: world.stock_match = false; break;
        case 9: world.stocks[1] = state->opponent_stocks = 0; break;
        case 10: world.stage = St_Kind_Story; break;
        case 11: entities.items = &objects[2]; break;
        case 12: self->coll_data.on_platform = true; break;
        case 13: self->coll_data.floor.index = -1; break;
        case 14: world.floor_right[0].x = -1; break; /* width < 100 */
        case 15: world.floor_right[0].y = 1; break;
        case 16: self->cur_pos.y = 6; break;
        case 17: self->cur_pos.x = 78; break; /* signed 22-margin boundary */
        case 18: self->cur_pos.x = -78; break;
        case 19: self->x221C_b6 = true; break;
        case 20: self->x2219_b5 = true; break;
        case 21: self->ground_or_air = GA_Air; break;
        case 22: self->cpu.x18 = 2; break;
        case 23: state->taunt_cooldown = 2; break;
        }
        u32 random = state->random;
        CHECK(!frame()); CHECK(state->action == SB_NONE && state->random == random);
        CHECK(writes == 0);
    }
    taunt_context(true); state->opponent_dead = true; state->celebration = 100;
    state->ego = 0; target->cur_pos.x = 0; world.invincible[1] = 2;
    CHECK(frame()); CHECK(state->action == SB_TAUNT); /* certified reset, even low ego */
}
static void test_taunt_certified_no_random_roll(void)
{
    for (variant = 0; variant < 2; ++variant) {
        taunt_context(variant != 0);
        u32 random = state->random;
        CHECK(frame()); CHECK(state->action == SB_TAUNT);
        CHECK(state->celebration == 0 && state->taunt_cooldown == 180);
        CHECK(state->random == random);
    }
}
static void test_taunt_cooldown_no_spam(void)
{
    taunt_context(true);
    CHECK(frame()); CHECK(frame()); self->motion_id = ftCo_MS_AppealSR;
    CHECK(frame()); CHECK(!frame());
    u32 random = state->random;
    for (int i = 0; i < SB_TAUNT_COOLDOWN * 2; ++i) { CHECK(!frame()); }
    CHECK(state->taunt_cooldown == 0 && scripts == 3 && state->random == random);
    /* Fresh contextual opportunity is allowed after cooldown, not a periodic taunt. */
    target->motion_id = ftCo_MS_Wait; CHECK(!frame());
    self->motion_id = ftCo_MS_Wait;
    state->ego = 60; state->random = seed_for(80, true);
    target->motion_id = ftCo_MS_DeadDown;
    CHECK(frame()); CHECK(state->action == SB_TAUNT);
}
static void test_swagger_whiff_finite_pulses(void)
{
    whiff_context(true);
    for (int age = 0; age < 22; ++age) {
        CHECK(frame()); CHECK(state->action == SB_SWAGGER && state->age == age + 1);
        bool down = age < 8 || (age >= 14 && age < 21);
        CHECK(self->cpu.buttons == 0 && self->cpu.lstick.x == 0);
        CHECK(self->cpu.lstick.y == (down ? -100 : 0));
        CHECK(self->cpu.write_pos - self->cpu.buffer == (down ? 3 : 1));
        if (down) {
            CHECK(self->cpu.buffer[0] == CpuCmd_SetLstickY);
            CHECK(self->cpu.buffer[1] == (u8) -100);
        }
        self->motion_id = age % 2 ? ftCo_MS_SquatWait : ftCo_MS_Squat;
    }
    expect_cancel(); CHECK(scripts == 22);
    for (int i = 0; i < SB_STYLE_COOLDOWN + 20; ++i) { CHECK(!frame()); }
    CHECK(scripts == 22 && state->cooldown == 0);
}
static void test_whiff_geometry_and_eligibility(void)
{
    for (variant = 0; variant < 10; ++variant) {
        whiff_context(true);
        switch (variant) {
        case 0: target->cur_pos.x = 45; break;
        case 1: target->cur_pos.x = 85; break;
        case 2: target->cur_pos.y = 12; break;
        case 3: target->facing_dir = -1; break;
        case 4: target->cur_anim_frame = 17.9f; break;
        case 5: target->motion_id = ftCo_MS_Wait; break;
        case 6: target->motion_id = ftCo_MS_AttackAirN; break;
        case 7: target->ground_or_air = GA_Air; break;
        case 8: state->ego = 44; break;
        case 9: world.invincible[1] = 1; break;
        }
        u32 random = state->random;
        CHECK(!frame()); CHECK(state->random == random);
    }
    whiff_context(true); target->cur_pos.x = -70; target->facing_dir = -1;
    target->motion_id = ftCo_MS_AttackLw4;
    CHECK(frame()); CHECK(state->action == SB_SWAGGER);
}
static void test_whiff_failed_roll_requires_new_edge(void)
{
    whiff_context(false); CHECK(!frame()); CHECK(state->whiff);
    u32 random = state->random;
    for (int i = 0; i < 360; ++i) { CHECK(!frame()); }
    CHECK(state->random == random && scripts == 0);
    target->motion_id = ftCo_MS_Wait; CHECK(!frame()); CHECK(!state->whiff);
    state->random = seed_for(50, true); target->motion_id = ftCo_MS_Attack11;
    CHECK(frame()); CHECK(state->action == SB_SWAGGER);
}
static void test_cooldown_defers_whiff_roll_without_spam(void)
{
    whiff_context(true); state->cooldown = 3;
    u32 random = state->random;
    CHECK(!frame()); CHECK(state->cooldown == 2 && !state->whiff);
    CHECK(!frame()); CHECK(state->cooldown == 1 && state->random == random);
    /* An observed opportunity is consumed only when an eligible roll occurs. */
    CHECK(frame()); CHECK(state->whiff && state->cooldown == SB_STYLE_COOLDOWN);
    random = state->random;
    for (int i = 1; i < 22; ++i) { CHECK(frame()); }
    CHECK(!frame());
    for (int i = 0; i < SB_STYLE_COOLDOWN * 2; ++i) { CHECK(!frame()); }
    CHECK(state->cooldown == 0 && state->random == random && scripts == 22);
}
static void test_punch_vulnerability_finite_script(void)
{
    punch_context(true);
    CHECK(frame()); CHECK(state->action == SB_PUNCH && state->age == 1);
    CHECK(state->cooldown == SB_STYLE_COOLDOWN); neutral(self);
    CHECK(frame()); CHECK(self->cpu.buttons == HSD_PAD_B);
    CHECK(self->cpu.buffer[0] == CpuCmd_PressB);
    CHECK(self->cpu.buffer[1] == CpuCmd_Done);
    CHECK(self->cpu.lstick.x == 0 && self->cpu.lstick.y == 0);
    self->motion_id = ftCa_MS_SpecialN; /* only the harness changes animation */
    CHECK(frame()); CHECK(state->age == 3); neutral(self);
    expect_cancel(); CHECK(scripts == 3);
}
static void test_punch_geometry_and_invulnerability(void)
{
    for (variant = 0; variant < 8; ++variant) {
        punch_context(true);
        switch (variant) {
        case 0: target->cur_pos.x = 17.9f; break;
        case 1: target->cur_pos.x = 42.1f; break;
        case 2: target->cur_pos.y = -12; break;
        case 3: self->facing_dir = -1; break;
        case 4: target->motion_id = ftCo_MS_Wait; break;
        case 5: state->ego = 74; break;
        case 6: world.invincible[1] = 1; break;
        case 7: world.invincible[1] = 2; break;
        }
        u32 random = state->random;
        CHECK(!frame()); CHECK(state->random == random);
    }
    punch_context(true); target->cur_pos.x = 18; state->ego = 75;
    CHECK(frame()); CHECK(state->action == SB_PUNCH);
    punch_context(true); target->cur_pos.x = -42; self->facing_dir = -1;
    CHECK(frame()); CHECK(state->action == SB_PUNCH);
}
static void test_punch_failed_roll_requires_new_edge(void)
{
    punch_context(false); CHECK(!frame()); CHECK(state->vulnerable);
    u32 random = state->random;
    for (int i = 0; i < 360; ++i) { CHECK(!frame()); }
    CHECK(state->random == random && scripts == 0);
    target->motion_id = ftCo_MS_Wait; CHECK(!frame());
    target->motion_id = ftCo_MS_Furafura; state->random = seed_for(35, true);
    CHECK(frame()); CHECK(state->action == SB_PUNCH);
}
static void test_start_safety_gates(void)
{
    for (variant = 0; variant < 10; ++variant) {
        whiff_context(true);
        switch (variant) {
        case 0: world.left[0] = SB_EDGE_MARGIN; break;
        case 1: world.right[0] = SB_EDGE_MARGIN; break;
        case 2: world.left[0] = -1; break; /* no island */
        case 3: self->ground_or_air = GA_Air; break;
        case 4: self->motion_id = ftCo_MS_Run; break;
        case 5: self->item_gobj = &objects[2]; break;
        case 6: self->self_vel.x = 1.01f; break;
        case 7: self->self_vel.x = -1.01f; break;
        case 8: self->x2219_b5 = true; break;
        case 9: state->serious = 2; break;
        }
        CHECK(!frame()); CHECK(state->action == SB_NONE && writes == 0);
    }
    whiff_context(true); self->self_vel.x = 1; world.left[0] = 22.01f;
    CHECK(frame());
}
static void test_vanilla_scenario_allowlist(void)
{
    for (variant = 0; variant <= 20; ++variant) {
        whiff_context(true); self->cpu.x18 = variant;
        bool allowed = variant == 1 || variant == 10;
        CHECK(frame() == allowed);
        CHECK((state->action == SB_SWAGGER) == allowed);
    }
}
static void test_cancel_forced_priority_and_geometry(void)
{
    for (int action = SB_TAUNT; action <= SB_PUNCH; ++action) {
        for (variant = 0; variant < 14; ++variant) {
            init(); state->ego = 90;
            SB_Start(self, state, (SB_Action) action, "test active cancellation");
            switch (variant) {
            case 0: self->x221C_b6 = true; break;
            case 1: self->victim_gobj = &objects[1]; break;
            case 2: self->x1A5C = &objects[1]; break;
            case 3: self->motion_id = ftCo_MS_Rebirth; break;
            case 4: self->motion_id = ftCo_MS_Entry; break;
            case 5: self->motion_id = ftCo_MS_EntryEnd; break;
            case 6: self->motion_id = ftCo_MS_DamageFlyHi; break;
            case 7: self->ground_or_air = GA_Air; self->cpu.xFA_b5 = false; break;
            case 8: self->cpu.x18 = 4; break;
            case 9: self->x2219_b5 = true; break;
            case 10: world.left[0] = 22; break;
            case 11: self->motion_id = ftCo_MS_Attack11; break;
            case 12: state->serious = 2; break;
            case 13: self->ground_or_air = GA_Air; break; /* floor below isn't safe to pose */
            }
            expect_cancel();
        }
    }
}
static void test_cancel_configuration_and_opponent_loss(void)
{
    for (variant = 0; variant < 9; ++variant) {
        whiff_context(true); CHECK(frame());
        switch (variant) {
        case 0: self->cpu.level = 8; break;
        case 1: world.cpu[0] = false; break;
        case 2: self->cpu.xC = 5; break;
        case 3: self->kind = FTKIND_FOX; break;
        case 4: self->x221F_b3 = true; break;
        case 5: world.entity[1] = NULL; break;
        case 6: world.player_state[1] = 0; break;
        case 7: world.player_state[2] = 2; break;
        case 8: world.ally = true; break;
        }
        expect_cancel(); CHECK(state->owner == NULL);
        CHECK(state->ego == 0 && state->cooldown == 0);
    }
}
static void test_cancel_action_specific_threats(void)
{
    whiff_context(true); CHECK(frame()); target->cur_pos.x = 31.9f;
    expect_cancel();
    taunt_context(true); CHECK(frame()); target->motion_id = ftCo_MS_Wait;
    target->cur_pos.x = 69.9f; expect_cancel();
    punch_context(true); CHECK(frame()); world.invincible[1] = 1;
    expect_cancel();
    /* Unsupported animation before the press must cancel, not inject late input. */
    taunt_context(true); CHECK(frame()); self->motion_id = ftCo_MS_AppealSR;
    expect_cancel();
    punch_context(true); CHECK(frame()); self->motion_id = ftCa_MS_SpecialN;
    expect_cancel();
}
static void test_idle_fallback_preserves_vanilla_input(void)
{
    init(); dirty_input(self);
    struct CpuFighter before;
    memcpy(&before, &self->cpu, sizeof(before));
    CHECK(!update(self)); CHECK(memcmp(&before, &self->cpu, sizeof(before)) == 0);
    CHECK(clears == 0 && writes == 0);
    /* Stop is idempotent and must not wipe a later vanilla frame. */
    SB_Stop(self, state, "already idle");
    CHECK(memcmp(&before, &self->cpu, sizeof(before)) == 0);
}
static void test_rng_deterministic_and_slot_private(void)
{
    SB_State a = { 0 }, b = { 0 };
    a.random = b.random = 0xfffffff0U;
    u32 expected = a.random;
    for (int i = 0; i < 1000; ++i) {
        expected = expected * 1664525U + 1013904223U;
        bool result = ((expected >> 16) % 100) < 35;
        CHECK(SB_Roll(&a, 35) == result);
        CHECK(SB_Roll(&b, 35) == result);
        CHECK(a.random == expected && b.random == expected);
    }
    init(); CHECK(!update(target));
    SB_State other;
    memcpy(&other, &sb_states[1], sizeof(other));
    target->motion_id = ftCo_MS_DeadDown; state->random = seed_for(80, true);
    target->mv.co.unk_deadleft.x40 = 20; self->cpu.xA4 = 0;
    CHECK(frame());
    CHECK(memcmp(&other, &sb_states[1], sizeof(other)) == 0);
}
static void test_stub_done_does_not_release_input(void)
{
    setup(); dirty_input(self);
    self->cpu.write_pos = self->cpu.buffer;
    ftCo_800B49F4(self); interpret(self);
    CHECK(self->cpu.buttons == 0xffff && self->cpu.lstick.y == -100);
    ftCo_800B4A78(self); neutral(self);
    CHECK(self->cpu.csP == NULL && self->cpu.command_duration == 0);
}

static void test_platform_and_crouched_punch_veto(void)
{
    whiff_context(true); self->coll_data.on_platform = true;
    u32 random = state->random;
    CHECK(!frame()); CHECK(state->random == random && !state->whiff);
    self->coll_data.on_platform = false;
    CHECK(frame()); self->coll_data.on_platform = true;
    expect_cancel(); /* crouching must not become a platform drop */
    punch_context(true); self->motion_id = ftCo_MS_SquatWait;
    random = state->random;
    CHECK(!frame()); CHECK(state->random == random && !state->vulnerable);
    self->motion_id = ftCo_MS_Wait;
    CHECK(frame()); self->motion_id = ftCo_MS_Squat;
    expect_cancel(); /* B while crouched could be a different special */
}
static void suspend(Fighter* fp)
{
    Fighter before[SB_SLOTS];
    int old_scripts = scripts;
    memcpy(before, fighters, sizeof(before));
    ShowboatAI_Suspend(fp);
    CHECK(scripts == old_scripts);
    for (int i = 0; i < SB_SLOTS; ++i) {
        if (&fighters[i] == fp) { unchanged_except_input(&before[i], fp); }
        else { CHECK(memcmp(&before[i], &fighters[i], sizeof(Fighter)) == 0); }
    }
}
static void test_suspend_clears_active_input_and_celebration(void)
{
    whiff_context(true); CHECK(frame()); dirty_owned_input();
    state->celebration = 100;
    int ego = state->ego, cooldown = state->cooldown;
    suspend(self); neutral(self);
    CHECK(state->action == SB_NONE && state->celebration == 0);
    CHECK(state->owner == self && state->ego == ego && state->cooldown == cooldown);
    CHECK(self->cpu.csP == NULL && self->cpu.command_duration == 0);
    CHECK(self->cpu.xA4 == 0);
    dirty_input(self); /* repeated idle suspension leaves vanilla input alone */
    struct CpuFighter before;
    memcpy(&before, &self->cpu, sizeof(before));
    suspend(self); CHECK(memcmp(&before, &self->cpu, sizeof(before)) == 0);
}
static void test_suspend_disabled_configuration_resets_slot(void)
{
    for (variant = 0; variant < 4; ++variant) {
        whiff_context(true); CHECK(frame()); dirty_owned_input();
        switch (variant) {
        case 0: world.cpu[0] = false; break;
        case 1: self->kind = FTKIND_FOX; break;
        case 2: self->cpu.level = 8; break;
        case 3: self->cpu.xC = 5; break;
        }
        suspend(self); neutral(self);
        CHECK(state->owner == NULL && state->ego == 0 && state->action == SB_NONE);
    }
}
static void test_suspend_stale_owner_and_invalid_slot_noop(void)
{
    for (variant = 0; variant < 2; ++variant) {
        init(); dirty_input(self);
        if (variant == 0) { state->owner = (Fighter*) (uintptr_t) 1; }
        else { self->player_id = SB_SLOTS; }
        struct CpuFighter before;
        SB_State old_state;
        memcpy(&before, &self->cpu, sizeof(before));
        memcpy(&old_state, state, sizeof(old_state));
        suspend(self);
        CHECK(memcmp(&before, &self->cpu, sizeof(before)) == 0);
        CHECK(memcmp(&old_state, state, sizeof(old_state)) == 0);
    }
}

static float attack_weight(void* table, int command, float weight)
{
    Fighter before[SB_SLOTS];
    struct TestFighterData old_data;
    unsigned char old_air[sizeof(air_table)], old_ground[sizeof(ground_table)];
    u32 random = state->random;
    int old_writes = writes, old_clears = clears;
    memcpy(before, fighters, sizeof(before));
    memcpy(&old_data, &fighter_data, sizeof(old_data));
    memcpy(old_air, air_table, sizeof(old_air));
    memcpy(old_ground, ground_table, sizeof(old_ground));
    float result = ShowboatAI_AttackWeight(self, table, command, weight);
    CHECK(memcmp(before, fighters, sizeof(before)) == 0);
    CHECK(memcmp(&old_data, &fighter_data, sizeof(old_data)) == 0);
    CHECK(memcmp(old_air, air_table, sizeof(old_air)) == 0);
    CHECK(memcmp(old_ground, ground_table, sizeof(old_ground)) == 0);
    CHECK(state->random == random && writes == old_writes && clears == old_clears);
    return result;
}
static void weight_context(void)
{
    init(); self->ground_or_air = GA_Air; state->ego = 100;
}
static void test_attack_weight_verified_air_commands_only(void)
{
    weight_context();
    for (variant = 0; variant < 32; ++variant) {
        CHECK(attack_weight(air_table, variant, 2) ==
              ((variant == 8 || variant == 10) ? 6 : 2));
        CHECK(attack_weight(ground_table, variant, 2) == 2);
    }
    CHECK(attack_weight(NULL, 8, 2) == 2);
    self->ground_or_air = GA_Ground;
    CHECK(attack_weight(air_table, 8, 2) == 2);
    CHECK(attack_weight(ground_table, 10, 2) == 2);
}
static void test_attack_weight_confidence_scaling_and_zero(void)
{
    weight_context();
    state->ego = 45; CHECK(attack_weight(air_table, 8, 10) == 10);
    state->ego = 56;
    float value = attack_weight(air_table, 8, 10);
    CHECK(value > 13.999f && value < 14.001f);
    state->ego = 100; CHECK(attack_weight(air_table, 10, 10) == 30);
    CHECK(attack_weight(air_table, 8, 0) == 0); /* never makes an ineligible candidate eligible */
}
static void test_attack_weight_exclusions_and_safety(void)
{
    for (variant = 0; variant < 23; ++variant) {
        weight_context();
        switch (variant) {
        case 0: self->cpu.level = 8; break;
        case 1: world.cpu[0] = false; break;
        case 2: self->kind = FTKIND_FOX; break;
        case 3: self->cpu.xC = 5; break;
        case 4: self->x221F_b3 = true; break;
        case 5: world.entity[0] = &objects[2]; break;
        case 6: state->owner = NULL; break;
        case 7: ++self->x8_spawnNum; break;
        case 8: state->ego = 44; break;
        case 9: state->serious = 1; break;
        case 10: state->danger = true; break;
        case 11: self->x221C_b6 = true; break;
        case 12: self->x2219_b5 = true; break;
        case 13: self->dmg.x1830_percent = 1; break; /* damage not yet observed by Update */
        case 14: self->dmg.x1830_percent = state->percent = 110; break;
        case 15: self->cpu.xFA_b5 = false; break;
        case 16: self->cpu.x18 = 4; break;
        case 17: self->cpu.x18 = 6; break;
        case 18: self->cpu.x18 = 7; break;
        case 19: self->cpu.x18 = 15; break;
        case 20: self->cpu.x18 = 18; break;
        case 21: self->player_id = SB_SLOTS; break;
        case 22: self->victim_gobj = &objects[1]; break;
        }
        CHECK(attack_weight(air_table, 8, 2.5f) == 2.5f);
        CHECK(attack_weight(air_table, 10, 2.5f) == 2.5f);
    }
}
static void test_stock_before_delayed_spawn_charged_once(void)
{
    init(); state->ego = 90;
    --world.stocks[0]; CHECK(!frame()); CHECK(state->ego == 75);
    /* Death animations can last longer than a short deduplication heuristic. */
    for (int i = 0; i < 150; ++i) { CHECK(!frame()); }
    int ego = state->ego;
    ++self->x8_spawnNum;
    CHECK(!frame()); CHECK(state->ego == ego && state->serious == 120);
    /* A second real life/stock loss is not exempt just because serious is high. */
    --world.stocks[0]; ++self->x8_spawnNum;
    CHECK(!frame()); CHECK(state->ego == (ego > 15 ? ego - 15 : 0));
}

/* Keep regressions strict: do not silently xfail bugs in production. */
static void test_cancel_when_singles_opponent_slot_changes(void)
{
    whiff_context(true); CHECK(frame());
    CHECK(self->cpu.lstick.y == -100); /* actual output of the preceding frame */
    world.player_state[1] = 0; world.player_state[2] = 2;
    CHECK(!update(self));
    CHECK(state->action == SB_NONE);
    neutral(self); /* must clear immediately, not after another VM iteration */
    CHECK(state->opponent_slot == 2 && state->ego == SB_BASE_EGO);
}

static void dance_context(bool success)
{
    init(); self->cpu.xA4 = 0; target->cur_pos.x = 80;
    state->ego = 60; state->random = seed_for(90, success);
}
static void test_v2_policy_constants_and_damage_rounding(void)
{
    CHECK(SB_BASE_EGO == 55 && SB_ADVANTAGE_PERIOD == 90);
    CHECK(SB_SERIOUS_FRAMES == 90 && SB_STYLE_COOLDOWN == 90);
    CHECK(SB_TAUNT_COOLDOWN == 180 && SB_DANCE == 4);
    const float damage[] = { 0.1f, 1.99f, 2, 3.99f, 4, 10.5f };
    const int loss[] = { 3, 3, 4, 4, 5, 8 };
    for (variant = 0; variant < 6; ++variant) {
        init(); self->dmg.x1830_percent = damage[variant];
        CHECK(!frame()); CHECK(state->ego == 55 - loss[variant]);
        CHECK(state->serious == 90);
    }
}
static void test_initial_spawn_no_danger_penalty(void)
{
    const int motions[] = { ftCo_MS_DeadDown, ftCo_MS_Rebirth,
        ftCo_MS_RebirthWait, ftCo_MS_Entry, ftCo_MS_EntryStart, ftCo_MS_EntryEnd };
    for (variant = 0; variant < 6; ++variant) {
        setup(); self->motion_id = motions[variant];
        CHECK(!frame()); CHECK(state->ego == 55 && state->danger);
        CHECK(state->serious == 30);
        CHECK(!frame()); CHECK(state->ego == 55);
    }
    init(); self->dmg.x1830_percent = state->percent = 200;
    CHECK(!frame()); CHECK(!state->danger && state->serious == 0);
    whiff_context(true); self->dmg.x1830_percent = state->percent = 200;
    CHECK(frame()); CHECK(state->action == SB_SWAGGER && !state->danger);
    punch_context(true); self->dmg.x1830_percent = state->percent = 200;
    CHECK(frame()); CHECK(state->action == SB_PUNCH && !state->danger);
}
static void test_taunt_death_enum_and_budget_boundaries(void)
{
    CHECK(ftCo_MS_DeadDown == 0 && ftCo_MS_DeadUpFallHitCameraIce == 10);
    for (variant = 0; variant <= 10; ++variant) {
        taunt_context(false); target->motion_id = variant;
        target->mv.co.unk_deadleft.x40 = 1; common_data.x5D0 = 79;
        CHECK(frame()); CHECK(state->action == SB_TAUNT);
    }
    taunt_context(true); common_data.x5D0 = 0;
    target->mv.co.unk_deadleft.x40 = 80; CHECK(frame());
    taunt_context(true); common_data.x5D0 = 59.99f;
    CHECK(!frame()); CHECK(state->action == SB_NONE);
}
static void test_taunt_safe_overrides_caution_and_style_cooldown(void)
{
    for (variant = 0; variant < 2; ++variant) {
        taunt_context(false); world.stage = variant ? St_Kind_Battle : St_Kind_Last;
        state->serious = 90; state->cooldown = 88;
        self->dmg.x1830_percent = state->percent = 180;
        u32 random = state->random;
        CHECK(frame()); CHECK(state->action == SB_TAUNT && !state->danger);
        CHECK(state->serious == 89 && state->cooldown == 87);
        CHECK(state->taunt_cooldown == 180 && state->random == random);
        CHECK(first_event(EV_RESTORE) == 0 && first_event(EV_COMBAT) == -1);
        CHECK(frame()); CHECK(self->cpu.buttons == HSD_PAD_DPADUP);
        self->motion_id = ftCo_MS_AppealSR;
        CHECK(frame()); CHECK(!frame()); CHECK(scripts == 3);
    }
    dance_context(true); CHECK(frame());
    target->motion_id = ftCo_MS_DeadDown; target->mv.co.unk_deadleft.x40 = 20;
    CHECK(frame()); CHECK(state->action == SB_TAUNT && state->age == 1);
    neutral(self); /* no stale dance stick in the certified reset */
}
static void test_taunt_settles_only_real_ground_movement(void)
{
    const int motions[] = { ftCo_MS_Dash, ftCo_MS_Turn, ftCo_MS_Run, ftCo_MS_RunBrake };
    for (variant = 0; variant < 4; ++variant) {
        taunt_context(true); self->motion_id = motions[variant];
        self->self_vel.x = 2.3f; target->mv.co.unk_deadleft.x40 = 40;
        CHECK(frame()); CHECK(state->action == SB_TAUNT && state->age == 0);
        CHECK(state->taunt_settle == 1); neutral(self);
        self->motion_id = ftCo_MS_RunBrake;
        for (int i = 0; i < 3; ++i) { CHECK(frame()); neutral(self); }
        CHECK(state->age == 0); /* no guessed timer forces Wait or Up */
        self->motion_id = ftCo_MS_Wait; self->self_vel.x = 0;
        CHECK(frame()); CHECK(state->age == 1); neutral(self);
        CHECK(frame()); CHECK(self->cpu.buttons == HSD_PAD_DPADUP);
        self->motion_id = ftCo_MS_AppealSR; CHECK(frame()); neutral(self);
    }
    taunt_context(true); self->motion_id = ftCo_MS_Run;
    for (int i = 0; i < 18; ++i) { CHECK(frame()); neutral(self); }
    CHECK(state->age == 0 && state->taunt_settle == 18);
    expect_cancel(); CHECK(scripts == 18);
    for (variant = 0; variant < 3; ++variant) {
        taunt_context(true); self->motion_id = ftCo_MS_Run; CHECK(frame());
        if (variant == 0) { target->mv.co.unk_deadleft.x40 = 19; }
        if (variant == 1) { self->cur_pos.x = 60; }
        if (variant == 2) { self->self_vel.x = 2.51f; }
        expect_cancel(); CHECK(scripts == 1); /* never spends Up unsafely */
    }
}
static void test_taunt_separate_cooldown_and_prepress_revalidation(void)
{
    taunt_context(true); CHECK(frame()); CHECK(frame());
    self->motion_id = ftCo_MS_AppealSR; CHECK(frame()); CHECK(!frame());
    self->motion_id = ftCo_MS_Wait;
    state->celebration = 180;
    for (int i = 0; i < 176; ++i) {
        CHECK(!frame()); CHECK(state->taunt_cooldown > 0);
    }
    CHECK(state->taunt_cooldown == 1 && scripts == 3);
    CHECK(frame()); CHECK(state->taunt_cooldown == 180 && scripts == 4);
    for (variant = 0; variant < 3; ++variant) {
        taunt_context(true); CHECK(frame());
        if (variant == 0) { target->mv.co.unk_deadleft.x40 = 19; }
        if (variant == 1) { target->motion_id = ftCo_MS_RebirthWait; }
        if (variant == 2) { entities.items = &objects[2]; }
        expect_cancel(); CHECK(scripts == 1); /* never emits Up late */
    }
}
static void test_short_scripts_require_native_state_confirmation(void)
{
    for (variant = 0; variant < 2; ++variant) {
        if (variant) { punch_context(true); } else { taunt_context(true); }
        CHECK(frame()); CHECK(frame());
        CHECK(self->motion_id == ftCo_MS_Wait && state->age == 2);
        CHECK(self->cpu.buttons == (variant ? HSD_PAD_B : HSD_PAD_DPADUP));
        int old_clears = clears;
        CHECK(!update(self)); /* no native acknowledgment: abort, don't repress */
        CHECK(state->action == SB_NONE && scripts == 2 && clears == old_clears + 1);
        neutral(self); CHECK(self->cpu.csP == NULL && self->cpu.command_duration == 0);
        CHECK(!frame()); CHECK(scripts == 2);
    }
}
static void test_punch_only_long_shieldbreak_daze(void)
{
    const int down[] = { ftCo_MS_DownBoundU, ftCo_MS_DownWaitU,
        ftCo_MS_DownBoundD, ftCo_MS_DownWaitD };
    for (variant = 0; variant < 7; ++variant) {
        punch_context(true);
        if (variant < 4) { target->motion_id = down[variant]; target->grab_timer = 1000; }
        else { target->grab_timer = variant == 4 ? 0 : variant == 5 ? 299.99f : 300; }
        u32 random = state->random;
        CHECK(!frame()); CHECK(state->action == SB_NONE && !state->vulnerable);
        CHECK(state->random == random && writes == 0);
    }
    punch_context(true); target->grab_timer = 300.01f; CHECK(frame());
}
static void test_flourish_start_preserves_active_vanilla_script(void)
{
    for (int dance = 0; dance < 2; ++dance) {
        for (variant = 0; variant < 3; ++variant) {
            if (dance) { dance_context(true); } else { whiff_context(true); }
            if (variant == 0) { self->cpu.xA4 = 8; }
            if (variant == 1) {
                self->cpu.buffer[0] = CpuCmd_Done;
                self->cpu.csP = self->cpu.buffer;
                self->cpu.write_pos = self->cpu.buffer + 1;
            }
            if (variant == 2) { self->cpu.command_duration = 3; }
            struct CpuFighter before = self->cpu;
            u32 random = state->random;
            CHECK(!update(self)); CHECK(state->action == SB_NONE);
            CHECK(memcmp(&before, &self->cpu, sizeof(before)) == 0);
            CHECK(state->random == random && writes == 0 && clears == 0);
        }
    }
    whiff_context(true); target->cur_pos.x = 69.99f;
    CHECK(!frame()); CHECK(!state->whiff);
    whiff_context(true); target->cur_pos.x = 70; CHECK(frame());
}
static void test_dance_start_world_direction_and_cooldown(void)
{
    for (variant = 0; variant < 4; ++variant) {
        dance_context(true);
        int side = variant & 1 ? -1 : 1;
        self->facing_dir = variant & 2 ? -1 : 1;
        target->cur_pos.x = side * 80;
        world.stage = variant & 1 ? St_Kind_Battle : St_Kind_Last;
        if (variant & 2) { state->ego = 80; }
        CHECK(frame()); CHECK(state->action == SB_DANCE && state->age == 1);
        CHECK(state->dance_direction == -side && state->dance_turns == 0);
        CHECK(state->dance_origin == 0 && state->dance_floor == 0);
        CHECK(state->cooldown == (variant & 2 ? 36 : 48));
        neutral(self); CHECK(self->cpu.write_pos - self->cpu.buffer == 1);
        CHECK(frame()); CHECK(self->cpu.lstick.x == -side * 127);
        CHECK(self->cpu.buffer[0] == CpuCmd_SetLstickX);
        CHECK(self->cpu.write_pos - self->cpu.buffer == 3);
        CHECK(self->cpu.buttons == 0 && self->cpu.lstick.y == 0);
    }
    dance_context(false); CHECK(!frame()); CHECK(state->cooldown == 24);
    u32 random = state->random;
    for (int i = 0; i < 23; ++i) { CHECK(!frame()); }
    CHECK(state->random == random && state->cooldown == 1);
    state->random = seed_for(90, true); CHECK(frame());
}
static void test_dance_real_dash_confirmation_and_end(void)
{
    dance_context(true); CHECK(frame());
    self->motion_id = ftCo_MS_Dash; self->facing_dir = -1;
    const float early[] = { 0, 3, 4, 5 };
    for (variant = 0; variant < 4; ++variant) {
        self->cur_anim_frame = early[variant];
        CHECK(frame()); CHECK(state->dance_turns == 0 && self->cpu.lstick.x == -127);
    }
    self->cur_anim_frame = 5.01f;
    CHECK(frame()); CHECK(state->dance_turns == 1 && self->cpu.lstick.x == 127);
    CHECK(frame()); CHECK(state->dance_turns == 1); /* old facing: no second flip */
    self->motion_id = ftCo_MS_Turn; self->facing_dir = 1; self->cur_anim_frame = 20;
    CHECK(frame()); CHECK(state->dance_turns == 1 && self->cpu.lstick.x == 127);
    self->motion_id = ftCo_MS_Dash; self->cur_anim_frame = 5;
    CHECK(frame()); CHECK(state->dance_turns == 1);
    self->cur_anim_frame = 6;
    CHECK(frame()); CHECK(state->dance_turns == 2 && self->cpu.lstick.x == -127);
    self->motion_id = ftCo_MS_Turn; self->facing_dir = -1;
    CHECK(frame()); CHECK(state->dance_turns == 2 && self->cpu.lstick.x == -127);
    self->motion_id = ftCo_MS_Dash; self->cur_anim_frame = 2.99f;
    CHECK(frame()); CHECK(state->dance_turns == 2);
    self->cur_anim_frame = 3;
    expect_cancel(); CHECK(state->age < 24);

    /* Taking over a Dash TOWARD the rival must not spend the initial opposite
     * flick during unturnable frames, then hold a stale flick forever. */
    dance_context(true); self->motion_id = ftCo_MS_Dash;
    self->facing_dir = 1; self->cur_anim_frame = 0;
    CHECK(frame()); neutral(self);
    for (int f = 1; f <= 4; ++f) {
        self->cur_anim_frame = f; CHECK(frame()); neutral(self);
        CHECK(state->dance_turns == 0);
    }
    self->cur_anim_frame = 5; CHECK(frame());
    CHECK(self->cpu.lstick.x == -127 && state->dance_turns == 0);
}
static void test_dance_bounded_updates_without_motion_confirmation(void)
{
    dance_context(true);
    for (int i = 0; i < 24; ++i) {
        CHECK(frame()); CHECK(state->age == i + 1 && state->dance_turns == 0);
    }
    expect_cancel(); CHECK(scripts == 24);
    CHECK(!frame()); CHECK(scripts == 24);
}
static void test_dance_start_court_and_context_guards(void)
{
    for (variant = 0; variant < 25; ++variant) {
        dance_context(true);
        switch (variant) {
        case 0: world.stage = St_Kind_Story; break;
        case 1: entities.items = &objects[2]; break;
        case 2: self->coll_data.on_platform = true; break;
        case 3: self->coll_data.floor.index = -1; break;
        case 4: world.floor_right[0].x = -0.01f; break;
        case 5: world.floor_left[0].x = 100; world.floor_right[0].x = -100; break;
        case 6: world.floor_right[0].y = -1; break;
        case 7: self->cur_pos.y = -6; break;
        case 8: self->cur_pos.x = -60; target->cur_pos.x = 20; break;
        case 9: self->cur_pos.x = 60; target->cur_pos.x = -20; break;
        case 10: self->cur_pos.x = 140; target->cur_pos.x = 220; break;
        case 11: self->cur_pos.x = -140; target->cur_pos.x = -220; break;
        case 12: target->cur_pos.x = 54.99f; break;
        case 13: target->cur_pos.x = 130.01f; break;
        case 14: target->cur_pos.y = 24; break;
        case 15: target->x221C_b6 = true; break;
        case 16: target->motion_id = ftCo_MS_DownWaitU; break;
        case 17: world.invincible[1] = 1; break;
        case 18: self->motion_id = ftCo_MS_Run; break;
        case 19: state->ego = 29; break;
        case 20: self->ground_or_air = GA_Air; break;
        case 21: self->x2219_b5 = true; break;
        case 22: state->serious = 2; break;
        case 23: state->cooldown = 2; break;
        case 24: self->cpu.x18 = 3; break;
        }
        u32 random = state->random;
        CHECK(!frame()); CHECK(state->action == SB_NONE && state->random == random);
        CHECK(clears == 0 && writes == 0);
    }
    dance_context(true); state->ego = 40; target->cur_pos.x = 55; CHECK(frame());
    dance_context(true); self->motion_id = ftCo_MS_Dash;
    target->cur_pos.x = 115; CHECK(frame());
    dance_context(true); world.floor_left[0].x = -50; world.floor_right[0].x = 50;
    CHECK(frame()); /* exactly 100-wide floor */
    dance_context(true); self->cur_pos.x = -59.99f; target->cur_pos.x = 20;
    CHECK(frame()); /* just inside the strict 40-unit starting margin */
}
static void test_dance_active_cancellation_and_ground_edges(void)
{
    for (variant = 0; variant < 24; ++variant) {
        dance_context(true); CHECK(frame()); CHECK(frame());
        CHECK(self->cpu.lstick.x == -127);
        switch (variant) {
        case 0: self->motion_id = ftCo_MS_Run; break;
        case 1: self->ground_or_air = GA_Air; break;
        case 2: self->x221C_b6 = true; break;
        case 3: self->x2219_b5 = true; break;
        case 4: self->victim_gobj = &objects[1]; break;
        case 5: state->serious = 2; break;
        case 6: self->dmg.x1830_percent = 1; break;
        case 7: self->coll_data.on_platform = true; break;
        case 8: self->coll_data.floor.index = -1; break;
        case 9: self->coll_data.floor.index = 1; break; /* same bounds, different floor */
        case 10: world.stage = St_Kind_Story; break;
        case 11: entities.items = &objects[2]; break;
        case 12: world.floor_right[0].y = 1; break;
        case 13: self->cur_pos.y = 6; break;
        case 14: world.floor_left[0].x = -30; break;
        case 15: world.floor_right[0].x = 30; break;
        case 16: self->cur_pos.x = -24.01f; break;
        case 17: self->cur_pos.x = 24.01f; break;
        case 18: target->cur_pos.x = 44.99f; break;
        case 19: target->x221C_b6 = true; break;
        case 20: target->motion_id = ftCo_MS_DownBoundD; break;
        case 21: target->motion_id = ftCo_MS_Furafura; break;
        case 22: world.invincible[1] = 2; break;
        case 23: world.floor_left[0].x = 50; world.floor_right[0].x = 200; break;
        }
        expect_cancel();
    }
    dance_context(true); CHECK(frame()); self->cur_pos.x = -24;
    CHECK(frame()); /* exact displacement bound is allowed */
    dance_context(true); CHECK(frame()); target->cur_pos.x = 45;
    CHECK(frame());
    dance_context(true); CHECK(frame());
    world.floor_right[0].x = 30.01f;
    CHECK(frame()); /* 30-unit active margin, not starting margin */
}
static void test_dance_signed_next_leg_runway(void)
{
    for (variant = 0; variant < 2; ++variant) {
        dance_context(true);
        int sign = variant ? 1 : -1;
        self->cur_pos.x = sign * 41; target->cur_pos.x = -sign * 39;
        CHECK(frame()); CHECK(state->dance_direction == sign);
        self->cur_pos.x = sign * 65; /* within 24 displacement, 35 from edge */
        expect_cancel(); /* proposed 22-unit leg would violate 18-unit reserve */
    }
}
static void test_flourish_yields_real_punish_preserves_fresh_selection(void)
{
    const int priority[] = { 0, 2, 3, 4, 6, 7, 8, 15, 18 };
    for (int dance = 0; dance < 2; ++dance) {
        for (variant = 0; variant < 9; ++variant) {
            if (dance) { dance_context(true); } else { whiff_context(true); }
            CHECK(frame());
            dirty_owned_input(); self->cpu.x18 = priority[variant]; self->cpu.xA4 = 8;
            CHECK(!update(self)); CHECK(state->action == SB_NONE);
            neutral(self); CHECK(self->cpu.csP == NULL && self->cpu.command_duration == 0);
            CHECK(self->cpu.xA4 == 8); /* every exit preserves a fresh decision */
        }
    }
    for (variant = 0; variant < 2; ++variant) {
        whiff_context(true); CHECK(frame()); dirty_owned_input(); self->cpu.xA4 = 123;
        if (variant == 0) { target->x221C_b6 = true; }
        else { target->motion_id = ftCo_MS_DownWaitD; }
        CHECK(!update(self)); neutral(self); CHECK(self->cpu.xA4 == 123);
        CHECK(state->action == SB_NONE);
    }
}
static void test_combat_restore_before_early_gates(void)
{
    for (variant = 0; variant < 10; ++variant) {
        init();
        combat.borrowed = true; combat.borrower = self; combat.saved_x = 19;
        self->cpu.lstick.x = 99;
        switch (variant) {
        case 0: self->player_id = 255; break;
        case 1: self->cpu.level = 8; break;
        case 2: world.entity[1] = NULL; break;
        case 3: world.ally = true; break;
        case 4: world.player_state[2] = 2; break;
        case 5: state->owner = (Fighter*) (uintptr_t) 1; break;
        case 6: ++self->x8_spawnNum; break;
        case 7: --world.stocks[0]; break;
        case 8: world.player_state[1] = 0; world.player_state[2] = 2; break;
        case 9: world.secondary[1] = &objects[2]; break;
        }
        int restores = combat.restores;
        CHECK(!update(self)); CHECK(combat.restores == restores + 1);
        CHECK(!combat.borrowed && self->cpu.lstick.x == 19);
        CHECK(first_event(EV_RESTORE) == 0);
        if (variant != 0) { CHECK(first_event(EV_RESET) > 0); }
        if (variant != 0 && variant != 5) {
            CHECK(first_event(EV_ABORT) > first_event(EV_RESTORE));
            CHECK(first_event(EV_ABORT) < first_event(EV_RESET));
        }
        if (variant < 5 || variant == 9) { CHECK(first_event(EV_COMBAT) == -1); }
    }
    taunt_context(true); combat.borrowed = true; combat.borrower = self;
    combat.saved_x = 19; self->cpu.lstick.x = 99;
    CHECK(frame()); CHECK(!combat.borrowed);
    CHECK(first_event(EV_RESTORE) == 0 && first_event(EV_CLEAR) > 0);
    CHECK(first_event(EV_COMBAT) == -1); neutral(self);
}
static void test_combat_independent_of_serious_and_flourish_priority(void)
{
    for (variant = 0; variant < 5; ++variant) {
        if (variant == 1) { dance_context(true); CHECK(frame()); }
        else if (variant == 2) { whiff_context(true); CHECK(frame()); }
        else if (variant == 3) { punch_context(true); CHECK(frame()); }
        else { init(); }
        if (variant == 0) { state->serious = 100; state->ego = 0; }
        if (variant == 4) { state->serious = 100; self->x221C_b6 = true; }
        combat.owns_input = true;
        int old_clears = clears, old_updates = combat.updates;
        CHECK(frame()); CHECK(state->action == SB_NONE);
        CHECK(combat.updates == old_updates + 1);
        CHECK(combat.last_actor == self && combat.last_target == target);
        CHECK(first_event(EV_RESTORE) == 0 && first_event(EV_COMBAT) > 0);
        CHECK(clears == old_clears + 1); /* personality must not SB_Stop the new script */
        CHECK(self->cpu.buttons == HSD_PAD_B && self->cpu.buffer[0] == CpuCmd_PressB);
        if (variant == 0 || variant == 4) { CHECK(state->serious == 99); }
    }
    init(); state->serious = 10;
    CHECK(!frame()); CHECK(first_event(EV_COMBAT) > 0); /* false also reaches caution gate */
}
static void post_input(Fighter* fp)
{
    Fighter before[SB_SLOTS]; memcpy(before, fighters, sizeof(before));
    ShowboatAI_PostInput(fp);
    CHECK(memcmp(before, fighters, sizeof(before)) == 0); /* spy itself writes nothing */
}
static void test_combat_postinput_gating_and_suspend_reset(void)
{
    for (variant = 0; variant < 8; ++variant) {
        init();
        switch (variant) {
        case 0: state->serious = 90; state->ego = 0; break;
        case 1: self->x221C_b6 = true; break;
        case 2: self->cpu.level = 8; break;
        case 3: world.cpu[0] = false; break;
        case 4: state->owner = NULL; break;
        case 5: self->player_id = 255; break;
        case 6: self->kind = FTKIND_FOX; break;
        case 7: self->cpu.xC = 3; break;
        }
        post_input(self); CHECK(combat.posts == (variant < 2 ? 1 : 0));
    }
    taunt_context(true); CHECK(frame()); post_input(self); CHECK(combat.posts == 1);
    init(); combat.owns_input = true; CHECK(frame()); post_input(self);
    CHECK(combat.posts == 1); /* regardless of which module supplied the script */
    init(); combat.borrowed = true; combat.borrower = self; combat.saved_x = 19;
    self->cpu.lstick.x = 99;
    int resets = combat.resets[0];
    event_count = 0; tracing = true; suspend(self); tracing = false;
    CHECK(events[0] == EV_RESTORE && first_event(EV_RESET) > 0);
    CHECK(first_event(EV_ABORT) > 0 && first_event(EV_ABORT) < first_event(EV_RESET));
    CHECK(self->cpu.lstick.x == 19 && combat.resets[0] == resets + 1);
    resets = combat.resets[2]; ShowboatAI_ResetSlot(2);
    CHECK(combat.resets[2] == resets + 1);
    resets = combat.resets[0]; ShowboatAI_ResetSlot(-1); ShowboatAI_ResetSlot(SB_SLOTS);
    CHECK(combat.resets[0] == resets);
}
static void test_movement_starts_after_combat_independent_of_ego(void)
{
    init(); state->ego = 0; state->serious = 100; movement.owns_input = true;
    CHECK(frame()); CHECK(self->cpu.lstick.x == 66 && state->action == SB_NONE);
    CHECK(first_event(EV_COMBAT) >= 0 && first_event(EV_COMBAT) < first_event(EV_MOVE));
    CHECK(state->serious == 99 && movement.active);
    dance_context(true); CHECK(frame()); CHECK(state->action == SB_DANCE);
    movement.owns_input = true; CHECK(frame());
    CHECK(state->action == SB_NONE && self->cpu.lstick.x == 66);
    CHECK(self->cpu.buttons == 0); /* no SB_Stop after movement's new script */
    init(); combat.owns_input = true; movement.owns_input = true;
    int calls = movement.updates;
    CHECK(frame()); CHECK(movement.updates == calls && self->cpu.buttons == HSD_PAD_B);
    taunt_context(true); movement.owns_input = true; CHECK(frame());
    CHECK(state->action == SB_TAUNT && !movement.active);
}
static void test_active_movement_precedes_other_techniques(void)
{
    init(); movement.owns_input = true; CHECK(frame());
    combat.owns_input = true;
    int calls = combat.updates;
    CHECK(frame()); CHECK(combat.updates == calls && self->cpu.lstick.x == 66);
    movement.owns_input = false;
    calls = movement.updates;
    CHECK(frame()); CHECK(movement.updates == calls + 1);
    CHECK(!movement.active && self->cpu.buttons == HSD_PAD_B);
    /* No second movement call/start on the cancellation update. */
}
static void test_movement_suspend_and_reset_orchestration(void)
{
    for (variant = 0; variant < 4; ++variant) {
        init(); movement.owns_input = true; CHECK(frame());
        movement.owns_input = false;
        int suspends = movement.suspends, resets = movement.resets[0];
        if (variant == 0) { world.cpu[0] = false; }
        if (variant == 1) { world.entity[1] = NULL; }
        if (variant == 2) { ++self->x8_spawnNum; }
        if (variant == 3) {
            event_count = 0; tracing = true; suspend(self); tracing = false;
        } else { CHECK(!update(self)); }
        CHECK(!movement.active && movement.suspends == suspends + 1);
        CHECK(first_event(EV_RESTORE) < first_event(EV_MOVE_SUSPEND));
        if (variant != 3) {
            CHECK(movement.resets[0] == resets + 1);
            CHECK(first_event(EV_MOVE_SUSPEND) < first_event(EV_MOVE_RESET));
        }
    }
}
static void mercy_context(void)
{
    weight_context(); state->ego = 90;
    world.stocks[0] = state->stocks = 4;
    world.stocks[1] = state->opponent_stocks = 2;
    self->dmg.x1830_percent = state->percent = 40;
    target->dmg.x1830_percent = state->opponent_percent = 80; target->x221C_b6 = true;
    self->cur_pos.x = -44.99f; target->cur_pos.x = 44.99f;
}
static void test_selective_mercy_commands_and_style_retained(void)
{
    for (variant = 0; variant < 2; ++variant) {
        mercy_context(); world.stage = variant ? St_Kind_Battle : St_Kind_Last;
        float style = 1.0f + 2.0f * 45 / 55;
        CHECK(attack_weight(air_table, 6, 2) == 8);
        CHECK(attack_weight(air_table, 8, 2) == 0.7f);
        CHECK(state->toy_frames == 45);
        CHECK(attack_weight(air_table, 10, 2) == 2 * style);
        for (int command = 0; command < 32; ++command) {
            if (command != 6 && command != 8 && command != 10) {
                CHECK(attack_weight(air_table, command, 2) == 2);
            }
            CHECK(attack_weight(ground_table, command, 2) == 2);
        }
        CHECK(attack_weight(air_table, 6, 0) == 0);
        CHECK(attack_weight(air_table, 8, 0) == 0);
    }
}
static void test_selective_mercy_guard_fallbacks(void)
{
    for (variant = 0; variant < 17; ++variant) {
        mercy_context();
        switch (variant) {
        case 0: state->ego = 89; break;
        case 1: world.stock_match = false; break;
        case 2: self->dmg.x1830_percent = state->percent = 40.01f; break;
        case 3: world.stocks[0] = 3; break;
        case 4: world.stocks[1] = 3; break;
        case 5: state->opponent_slot = -1; break;
        case 6: state->opponent_slot = SB_SLOTS; break;
        case 7: world.entity[1] = NULL; break;
        case 8: world.stage = St_Kind_Story; break;
        case 9: target->dmg.x1830_percent = 79.99f; break;
        case 10: target->x221C_b6 = false; break;
        case 11: self->cur_pos.x = -45; break;
        case 12: self->cur_pos.x = 45; break;
        case 13: target->cur_pos.x = -45; break;
        case 14: target->cur_pos.x = 45; break;
        case 15: state->serious = 1; break;
        case 16: self->ground_or_air = GA_Ground; break;
        }
        float style = variant >= 15 ? 1 : 1.0f + 2.0f * (state->ego - 45) / 55;
        CHECK(attack_weight(air_table, 6, 2) == 2);
        CHECK(attack_weight(air_table, 8, 2) == 2 * style);
        CHECK(attack_weight(air_table, 10, 2) == 2 * style);
        CHECK(state->toy_frames == 0);
    }
}
static void test_selective_mercy_cannot_bypass_common_safety_gates(void)
{
    for (variant = 0; variant < 15; ++variant) {
        mercy_context();
        switch (variant) {
        case 0: self->cpu.level = 8; break;
        case 1: state->owner = (Fighter*) (uintptr_t) 1; break;
        case 2: ++self->x8_spawnNum; break;
        case 3: state->danger = true; break;
        case 4: self->x221C_b6 = true; break;
        case 5: self->x2219_b5 = true; break;
        case 6: self->dmg.x1830_percent = 40.01f; break; /* unobserved damage */
        case 7: self->cpu.xFA_b5 = false; break;
        case 8: self->cpu.x18 = 4; break;
        case 9: self->cpu.x18 = 6; break;
        case 10: self->cpu.x18 = 7; break;
        case 11: self->cpu.x18 = 15; break;
        case 12: self->cpu.x18 = 18; break;
        case 13: self->victim_gobj = target->gobj; break;
        case 14: self->player_id = 255; break;
        }
        CHECK(attack_weight(air_table, 6, 2) == 2);
        CHECK(attack_weight(air_table, 8, 2) == 2);
        CHECK(attack_weight(air_table, 10, 2) == 2);
        CHECK(state->toy_frames == 0);
    }
}
static void test_selective_mercy_indicator_lifecycle(void)
{
    mercy_context(); CHECK(attack_weight(air_table, 6, 1) == 4);
    CHECK(!frame()); CHECK(state->toy_frames == 44);
    self->dmg.x1830_percent += 1; CHECK(!frame()); CHECK(state->toy_frames == 0);
    mercy_context(); CHECK(attack_weight(air_table, 6, 1) == 4);
    ++self->x8_spawnNum; CHECK(!frame()); CHECK(state->toy_frames == 0);
    mercy_context(); CHECK(attack_weight(air_table, 6, 1) == 4);
    self->cpu.xFA_b5 = false; CHECK(!frame()); CHECK(state->toy_frames == 0);
    mercy_context(); CHECK(attack_weight(air_table, 6, 1) == 4);
    target->motion_id = ftCo_MS_DeadDown; CHECK(!frame()); CHECK(state->toy_frames == 0);
}

static void offstage_context(int side, bool crouch)
{
    init(); self->cpu.xA4 = 0;
    state->ego = 0; state->serious = 600; state->cooldown = 900;
    target->ground_or_air = GA_Air; target->motion_id = ftCo_MS_Fall;
    target->cur_pos.x = side * 170; target->cur_pos.y = -30;
    state->opponent_x = target->cur_pos.x; /* preceding observation, not physics */
    if (crouch) { self->motion_id = ftCo_MS_SquatWait; }
}
static void test_offstage_deterministic_repeat_bouts_at_zero_ego(void)
{
    for (variant = 0; variant < 2; ++variant) {
        int side = variant ? -1 : 1;
        offstage_context(side, false);
        world.stage = variant ? St_Kind_Battle : St_Kind_Last;
        u32 random = state->random;
        for (int bout = 0; bout < 3; ++bout) {
            for (int age = 0; age < 24; ++age) {
                CHECK(frame()); CHECK(state->offstage_style && state->action == SB_DANCE);
                CHECK(state->age == age + 1 && state->ego == 0 && state->serious > 0);
                CHECK(self->cpu.buttons == 0 && self->cpu.lstick.y == 0);
                CHECK(self->cpu.lstick.x == (age ? -side * 127 : 0));
                CHECK(state->taunt_cooldown == 0 && state->random == random);
            }
            CHECK(!update(self)); neutral(self);
            CHECK(state->action == SB_NONE && !state->offstage_style);
            CHECK(state->offstage_cooldown == 18);
            for (int i = 0; i < 17; ++i) { CHECK(!frame()); }
            CHECK(state->offstage_cooldown == 1);
        }
        CHECK(scripts == 72); CHECK(frame()); CHECK(scripts == 73);
    }
}
static void test_offstage_crouch_fallback_bounded_and_legal(void)
{
    for (variant = 0; variant < 2; ++variant) {
        offstage_context(1, variant == 0);
        if (variant == 1) { self->cur_pos.x = -65; } /* only 35 signed runway */
        for (int age = 0; age < 12; ++age) {
            CHECK(frame()); CHECK(state->offstage_style && state->action == SB_SWAGGER);
            CHECK(state->age == age + 1 && self->cpu.buttons == 0);
            CHECK(self->cpu.lstick.x == 0 && self->cpu.lstick.y == (age < 8 ? -100 : 0));
            self->motion_id = ftCo_MS_SquatWait; /* real crouch acceptance supplied */
        }
        CHECK(!update(self)); neutral(self); CHECK(scripts == 12);
        for (int i = 0; i < 17; ++i) { CHECK(!frame()); }
        CHECK(frame()); CHECK(state->action == SB_SWAGGER);
    }
}
static void offstage_veto(int which)
{
    switch (which) {
    case 0: world.stage = St_Kind_Story; break;
    case 1: self->coll_data.on_platform = true; break;
    case 2: self->coll_data.floor.index = -1; break;
    case 3: self->ground_or_air = GA_Air; break;
    case 4: self->cur_pos.x = 70; break; /* strict active 30 runway */
    case 5: self->cur_pos.x = -70; break;
    case 6: self->cur_pos.x = 170; break; /* unsigned endpoint distances lie */
    case 7: world.floor_left[0].x = 100; world.floor_right[0].x = -100; break;
    case 8: world.floor_right[0].y = 1; break;
    case 9: self->cur_pos.y = 6; break;
    case 10: entities.items = &objects[2]; break; /* items AND projectiles */
    case 11: self->item_gobj = &objects[2]; break;
    case 12: target->item_gobj = &objects[2]; break;
    case 13: self->x221C_b6 = true; break;
    case 14: self->x2219_b5 = true; break;
    case 15: self->victim_gobj = target->gobj; break;
    case 16: self->x1A5C = target->gobj; break;
    case 17: self->motion_id = ftCo_MS_RunBrake; break; /* can't dash/crouch directly */
    case 18: self->self_vel.x = 2.51f; break;
    case 19: self->self_vel.y = 0.26f; break;
    case 20: state->recent_hit = 2; break;
    case 21: target->cur_pos.x = 130; break; /* exactly ledge+30 */
    case 22: target->cur_pos.x = 100; target->cur_pos.y = -100; break;
    case 23: target->cur_pos.x = 0; target->cur_pos.y = -200; break; /* below != outside */
    case 24: target->ground_or_air = GA_Ground; break;
    case 25: target->motion_id = ftCo_MS_DeadDown; break;
    case 26: target->motion_id = ftCo_MS_RebirthWait; break;
    case 27: target->motion_id = ftCo_MS_Entry; break;
    case 28: target->victim_gobj = self->gobj; break;
    case 29: target->x1A5C = self->gobj; break;
    case 30: target->x221F_b3 = true; break;
    case 31: world.stocks[1] = state->opponent_stocks = 0; break;
    case 32: self->dmg.x1830_percent += 1; break;
    case 33: self->cur_pos.x = 50; target->cur_pos.x = 149.99f; break; /* gap <100 */
    }
}
static void test_offstage_start_signed_court_and_physical_guards(void)
{
    for (variant = 0; variant < 34; ++variant) {
        offstage_context(1, false); offstage_veto(variant);
        state->opponent_x = target->cur_pos.x; /* isolate instantaneous geometry */
        u32 random = state->random;
        CHECK(!frame()); CHECK(state->action == SB_NONE);
        CHECK(writes == 0 && clears == 0 && state->random == random);
    }
    offstage_context(1, false); self->cur_pos.x = 50; target->cur_pos.x = 150;
    state->opponent_x = 150; CHECK(frame()); /* exact 100 gap */
    offstage_context(-1, false); target->cur_pos.x = -130.01f;
    state->opponent_x = target->cur_pos.x; CHECK(frame()); /* signed left boundary */
}
static void test_offstage_active_window_closure_releases_immediately(void)
{
    for (int crouch = 0; crouch < 2; ++crouch) {
        for (variant = 0; variant < 34; ++variant) {
            offstage_context(1, crouch != 0); CHECK(frame()); CHECK(frame());
            offstage_veto(variant);
            int old_clears = clears;
            CHECK(!update(self)); neutral(self);
            CHECK(state->action == SB_NONE && state->offstage_cooldown == 18);
            CHECK(clears == old_clears + 1 && scripts == 2);
        }
        offstage_context(1, crouch != 0); CHECK(frame());
        self->coll_data.floor.index = 1; CHECK(!update(self)); neutral(self);
    }
}
static void test_offstage_far_hitstun_and_return_invulnerability_not_vetoes(void)
{
    for (variant = 0; variant < 4; ++variant) {
        offstage_context(1, false);
        target->x221C_b6 = true; target->motion_id = ftCo_MS_DamageFlyHi;
        if (variant & 1) { world.invincible[1] = 2; }
        if (variant & 2) { target->x2219_b5 = true; }
        CHECK(frame()); CHECK(state->offstage_style);
        self->motion_id = ftCo_MS_Dash; self->facing_dir = -1;
        self->cur_anim_frame = 6; CHECK(frame());
        CHECK(state->dance_turns == 1 && self->cpu.lstick.x == 127);
        target->x221C_b6 = false; target->x2219_b5 = false;
        target->motion_id = ftCo_MS_Fall; world.invincible[1] = 2;
        CHECK(frame()); CHECK(state->offstage_style);
        target->cur_pos.x = 110; CHECK(!update(self)); neutral(self);
    }
    offstage_context(1, false); CHECK(frame());
    target->cur_pos.x = 80; target->cur_pos.y = 0;
    target->ground_or_air = GA_Ground; target->x221C_b6 = true;
    CHECK(!update(self)); neutral(self); /* actual onscreen punish, not far hitstun */
}
static void test_offstage_closing_rate_reserve_uses_live_observations(void)
{
    for (variant = 0; variant < 4; ++variant) {
        int side = variant & 1 ? -1 : 1;
        offstage_context(side, false); CHECK(frame());
        if (variant & 2) {
            target->cur_pos.x = side * 160; /* actual step 10, even with zero self_vel */
        } else { target->self_vel.x = -side * 10; }
        CHECK(!update(self)); neutral(self); /* 4-update projection reaches <=130 */
    }
    offstage_context(1, false); target->self_vel.x = 20; CHECK(frame());
    CHECK(frame()); /* outward motion is not a closing threat */
}
static void test_offstage_recent_hit_caution_and_ego_lifecycle(void)
{
    offstage_context(1, false); CHECK(frame());
    state->ego = 80; self->dmg.x1830_percent = 10;
    CHECK(!update(self)); neutral(self);
    CHECK(state->ego == 62 && state->serious == 90 && state->recent_hit == 30);
    for (int i = 0; i < 29; ++i) { CHECK(!frame()); }
    CHECK(state->recent_hit == 1 && state->serious == 61);
    state->ego = 0; CHECK(frame()); /* physical recovery after 30, emotional 60 remains */
    CHECK(state->offstage_style && state->serious == 60 && state->ego == 0);
    self->x221C_b6 = true; CHECK(!frame()); CHECK(state->recent_hit == 30);
    for (int i = 0; i < 40; ++i) { CHECK(!frame()); CHECK(state->recent_hit == 30); }
    self->x221C_b6 = false;
    for (int i = 0; i < 29; ++i) { CHECK(!frame()); }
    CHECK(frame()); CHECK(state->offstage_style);
    ++self->x8_spawnNum; CHECK(!update(self)); neutral(self);
    CHECK(state->recent_hit == 30 && state->serious == 120);
}
static void test_offstage_technical_competence_and_certified_ko_win(void)
{
    for (int active = 0; active < 2; ++active) {
        for (variant = 0; variant < 2; ++variant) {
            offstage_context(1, false);
            if (active) { CHECK(frame()); }
            if (variant) { movement.owns_input = true; }
            else { combat.owns_input = true; }
            int old_clears = clears;
            CHECK(frame()); CHECK(state->action == SB_NONE && !state->offstage_style);
            CHECK(clears == old_clears + 1);
            CHECK(self->cpu.buttons == (variant ? 0 : HSD_PAD_B));
            CHECK(self->cpu.lstick.x == (variant ? 66 : 0));
            CHECK(first_event(EV_COMBAT) >= 0);
            if (variant) { CHECK(first_event(EV_COMBAT) < first_event(EV_MOVE)); }
            if (active) { CHECK(state->offstage_cooldown == 18); }
        }
    }
    offstage_context(1, false); CHECK(frame());
    target->motion_id = ftCo_MS_DeadDown; target->mv.co.unk_deadleft.x40 = 20;
    CHECK(frame()); CHECK(state->action == SB_TAUNT && !state->offstage_style);
    neutral(self); CHECK(frame()); CHECK(self->cpu.buttons == HSD_PAD_DPADUP);
    CHECK(state->offstage_cooldown == 17); /* ordinary recovery never used Up */
}

static void personality_context(int style)
{
    switch (style) {
    case 0: dance_context(true); break;
    case 1: whiff_context(true); break;
    case 2: taunt_context(true); break;
    case 3: punch_context(true); break;
    case 4: offstage_context(1, false); break;
    case 5: offstage_context(1, true); break;
    default: CHECK(!"unknown style fixture");
    }
}
static void native_vm(const u8* bytes, int size, int cursor, int duration)
{
    CHECK(size > 0 && size <= (int) sizeof(self->cpu.buffer));
    CHECK(cursor >= 0 && cursor < size);
    memcpy(self->cpu.buffer, bytes, (size_t) size);
    self->cpu.write_pos = self->cpu.buffer + size;
    self->cpu.csP = self->cpu.buffer + cursor;
    self->cpu.command_duration = duration;
}
static void test_personality_verified_mundane_initial_takeover(void)
{
    static const u8 locomotion[] = {
        CpuCmd_SetLstickX, 80, CpuCmd_WaitFor, 3,
        CpuCmd_LstickXTowardDestination, 90, CpuCmd_ReleaseAll, CpuCmd_Done
    };
    static const u8 clamped[] = {
        CpuCmd_LstickXTowardDestinationClamped, 5, 80,
        CpuCmd_SetCstickX, 0, CpuCmd_SetLtrigger, 0, CpuCmd_Done
    };
    for (int style = 0; style < 6; ++style) {
        for (variant = 0; variant < 3; ++variant) {
            personality_context(style);
            if (variant == 2) { native_vm(clamped, sizeof(clamped), 0, 1); }
            else { native_vm(locomotion, sizeof(locomotion), variant ? 4 : 0, 3); }
            self->cpu.lstick.x = 80;
            CHECK(frame()); CHECK(state->action != SB_NONE);
            CHECK(clears == 1 && scripts == 1 && self->cpu.lstick.x == 0);
        }
    }
}
static void test_personality_queued_attack_and_malformed_takeover_veto(void)
{
    static const u8 attack[] = {
        CpuCmd_SetLstickX, 80, CpuCmd_WaitFor, 3, CpuCmd_PressB, CpuCmd_Done
    };
    static const u8 mundane[] = { CpuCmd_SetLstickX, 80, CpuCmd_Done };
    for (int style = 0; style < 6; ++style) {
        for (variant = 0; variant < 16; ++variant) {
            personality_context(style);
            native_vm(attack, sizeof(attack), variant == 1 ? 4 : 0, 3);
            switch (variant) {
            case 0: case 1: break; /* don't stop scanning at the wait */
            case 2: self->cpu.buffer[4] = CpuCmd_PressX; break;
            case 3: self->cpu.buffer[4] = CpuCmd_PressA; break;
            case 4: self->cpu.buffer[4] = CpuCmd_PressUp; break;
            case 5: self->cpu.buffer[4] = CpuCmd_Unk0x93; break;
            case 6: self->cpu.buffer[0] = 0xfe; break;
            case 7: self->cpu.write_pos = self->cpu.buffer + 1; break;
            case 8: self->cpu.csP = (void*) (uintptr_t) 1; break;
            case 9: self->cpu.write_pos = (void*) (uintptr_t) 1; break;
            case 10: self->cpu.command_duration = 0; break;
            default:
                native_vm(mundane, sizeof(mundane), 0, 1);
                if (variant == 11) { self->cpu.xA4 = 8; }
                if (variant == 12) { self->cpu.buttons = HSD_PAD_B; }
                if (variant == 13) { self->cpu.ltrigger = 100; }
                if (variant == 14) { self->cpu.cstick.x = 50; }
                if (variant == 15) { self->cpu.buffer[0] = CpuCmd_SetRtrigger; }
            }
            struct CpuFighter before = self->cpu;
            u32 random = state->random;
            CHECK(!update(self)); CHECK(state->action == SB_NONE);
            CHECK(memcmp(&before, &self->cpu, sizeof(before)) == 0);
            CHECK(state->random == random && writes == 0 && clears == 0);
        }
    }
}
static void test_personality_active_replacement_vm_preserved_exactly(void)
{
    static const u8 mundane[] = { CpuCmd_SetLstickX, 80, CpuCmd_Done };
    for (int style = 0; style < 6; ++style) {
        for (variant = 0; variant < 10; ++variant) {
            personality_context(style); CHECK(frame());
            switch (variant) {
            case 0: dirty_input(self); break; /* fresh native attack */
            case 1: native_vm(mundane, sizeof(mundane), 0, 1); break;
            case 2: self->cpu.write_pos++; break; /* same prefix != owned length */
            case 3: self->cpu.csP = self->cpu.buffer + 1;
                    self->cpu.command_duration = 1; break;
            case 4: self->cpu.csP = self->cpu.buffer;
                    self->cpu.command_duration = 2; break;
            case 5: self->cpu.command_duration = 1; break; /* NULL cursor inconsistent */
            case 6: self->cpu.buffer[0] ^= 1; break;
            case 7: self->cpu.csP = (void*) (uintptr_t) 1; break;
            case 8: self->cpu.write_pos = (void*) (uintptr_t) 1; break;
            case 9: self->cpu.csP = self->cpu.buffer;
                    self->cpu.command_duration = 0; break;
            }
            struct CpuFighter before = self->cpu;
            int old_clears = clears;
            CHECK(!update(self)); CHECK(state->action == SB_NONE && state->script_size == 0);
            CHECK(memcmp(&before, &self->cpu, sizeof(before)) == 0);
            CHECK(clears == old_clears && scripts == 1);
        }
    }
}
static void test_personality_cache_and_priority_preemption_release_only_owned_vm(void)
{
    const int priorities[] = { 1, 10, 2, 3, 4, 7, 8, 9, 15, 18 };
    for (int style = 0; style < 6; ++style) {
        for (variant = 0; variant < 10; ++variant) {
            personality_context(style); CHECK(frame());
            self->cpu.x18 = priorities[variant];
            self->cpu.xA4 = variant == 1 ? 0 : 8; /* even low-priority 1 ->10 yields */
            int old_clears = clears;
            CHECK(!update(self)); neutral(self);
            CHECK(self->cpu.csP == NULL && self->cpu.write_pos == self->cpu.buffer);
            CHECK(self->cpu.xA4 == (variant == 1 ? 0 : 8));
            CHECK(self->cpu.x18 == priorities[variant]);
            CHECK(clears == old_clears + 1 && state->script_size == 0);
            CHECK(state->action == SB_NONE && scripts == 1);
        }
    }
}
static void test_personality_unsampled_input_cannot_advance_bout(void)
{
    for (variant = 0; variant < 6; ++variant) {
        personality_context(variant); CHECK(update(self)); /* do not interpret */
        int age = state->age;
        CHECK(!update(self)); neutral(self);
        CHECK(state->action == SB_NONE && state->age == age && scripts == 1);
        CHECK(self->cpu.csP == NULL && self->cpu.command_duration == 0);
    }
}
static void test_personality_replacement_vm_survives_lifecycle_exits(void)
{
    for (int style = 0; style < 6; ++style) {
        for (variant = 0; variant < 10; ++variant) {
            personality_context(style); CHECK(frame()); dirty_input(self);
            switch (variant) {
            case 0: self->cpu.level = 8; break;
            case 1: world.entity[1] = NULL; break;
            case 2: world.ally = true; break;
            case 3: ++self->x8_spawnNum; break;
            case 4: --world.stocks[0]; break;
            case 5: self->dmg.x1830_percent += 1; break;
            case 6: ++target->x8_spawnNum; break;
            case 7: world.player_state[1] = 0; world.player_state[2] = 2; break;
            case 8: fighters[2].player_id = 1; world.entity[1] = &objects[2]; break;
            case 9: break; /* suspension */
            }
            struct CpuFighter before = self->cpu;
            int old_clears = clears;
            if (variant == 9) { suspend(self); } else { CHECK(!update(self)); }
            CHECK(state->action == SB_NONE && state->script_size == 0);
            CHECK(memcmp(&before, &self->cpu, sizeof(before)) == 0);
            CHECK(clears == old_clears && scripts == 1);
        }
    }
}
static void test_offstage_identity_lifecycle_releases_owned_input(void)
{
    for (variant = 0; variant < 4; ++variant) {
        offstage_context(1, false); CHECK(frame()); CHECK(frame());
        if (variant == 0) { ++target->x8_spawnNum; }
        if (variant == 1) { fighters[2].player_id = 1; world.entity[1] = &objects[2]; }
        if (variant == 2) { world.entity[1] = NULL; }
        if (variant == 3) { suspend(self); } else { CHECK(!update(self)); }
        neutral(self); CHECK(state->action == SB_NONE && state->script_size == 0);
        CHECK(self->cpu.csP == NULL && self->cpu.command_duration == 0);
    }
    offstage_context(1, false); CHECK(frame());
    ShowboatAI_ResetSlot(0); /* bookkeeping reset must never dereference old owners */
    CHECK(state->owner == NULL && state->recent_hit == 0 && state->offstage_cooldown == 0);
}
static void test_certified_taunt_still_rejects_recent_hits_and_physical_risk(void)
{
    for (variant = 0; variant < 5; ++variant) {
        taunt_context(true);
        if (variant == 0) { self->dmg.x1830_percent = 1; }
        if (variant == 1) { self->self_vel.x = 2.51f; }
        if (variant == 2) { self->self_vel.y = 0.26f; }
        if (variant == 3) { self->item_gobj = &objects[2]; }
        if (variant == 4) { target->item_gobj = &objects[2]; }
        CHECK(!frame()); CHECK(state->action == SB_NONE && writes == 0);
    }
    taunt_context(true); state->recent_hit = 2; state->serious = 90;
    CHECK(!frame()); CHECK(state->recent_hit == 1);
    CHECK(frame()); CHECK(state->action == SB_TAUNT && state->serious == 88);
}
static void test_long_action_press_preemption_never_forces_animation_exit(void)
{
    for (int punch = 0; punch < 2; ++punch) {
        for (variant = 0; variant < 2; ++variant) {
            if (punch) { punch_context(true); } else { taunt_context(true); }
            CHECK(frame()); CHECK(frame());
            CHECK(self->cpu.buttons == (punch ? HSD_PAD_B : HSD_PAD_DPADUP));
            self->motion_id = punch ? ftCa_MS_SpecialN : ftCo_MS_AppealSR;
            if (variant) {
                dirty_input(self);
                self->cpu.buffer[0] = CpuCmd_PressA; /* distinct from owned Punch B */
            } else { self->cpu.xA4 = 8; }
            struct CpuFighter before = self->cpu;
            CHECK(!update(self)); CHECK(state->action == SB_NONE);
            CHECK(self->motion_id == (punch ? ftCa_MS_SpecialN : ftCo_MS_AppealSR));
            if (variant) { CHECK(memcmp(&before, &self->cpu, sizeof(before)) == 0); }
            else { neutral(self); CHECK(self->cpu.xA4 == 8); }
        }
    }
}
static void test_neutral_frequency_widened_but_recoveries_and_punishes_yield(void)
{
    dance_context(true); state->ego = 30;
    target->cur_pos.x = 125; target->cur_pos.y = 23;
    CHECK(frame()); CHECK(state->cooldown == 48 && !state->offstage_style);
    for (int i = 1; i < 24; ++i) { CHECK(frame()); }
    CHECK(!frame());
    for (int i = 0; i < 23; ++i) { CHECK(!frame()); }
    state->random = seed_for(90, true); CHECK(frame()); /* 48-update start cadence */
    const int motions[] = { ftCo_MS_Landing, ftCo_MS_LandingFallSpecial,
        ftCo_MS_LandingAirN, ftCo_MS_LandingAirLw };
    for (variant = 0; variant < 4; ++variant) {
        dance_context(true); target->motion_id = motions[variant];
        CHECK(!frame()); CHECK(writes == 0);
        dance_context(true); CHECK(frame()); target->motion_id = motions[variant];
        CHECK(!update(self)); neutral(self);
    }
    dance_context(true); target->ground_or_air = GA_Air;
    target->cur_pos.x = 125; target->cur_pos.y = 0; target->motion_id = ftCo_MS_Fall;
    CHECK(!frame()); /* too close to ledge for offstage window; no neutral back door */
}

static void seed_defense(Fighter* fp, int action, bool pending)
{
    valid_slot(fp->player_id);
    defense.slots[fp->player_id].owner = fp;
    defense.slots[fp->player_id].action = action;
    defense.slots[fp->player_id].pending = pending;
}
static void test_defense_default_declines_without_input_or_reward(void)
{
    init(); dirty_input(self);
    struct CpuFighter before = self->cpu;
    int calls = defense.updates, takes = defense.takes;
    int old_writes = writes, old_clears = clears;
    CHECK(!update(self));
    CHECK(defense.updates == calls + 1 && defense.takes == takes + 1);
    CHECK(defense.last_actor == self && defense.last_target == target);
    CHECK(ShowboatDefense_GetAction(self) == 0 && defense.rewards == 0);
    CHECK(state->ego == SB_BASE_EGO);
    CHECK(memcmp(&before, &self->cpu, sizeof(before)) == 0);
    CHECK(writes == old_writes && clears == old_clears);
    CHECK(first_event(EV_COMBAT) < defense.update_events);
    CHECK(defense.update_events <= first_event(EV_MOVE));
    CHECK(defense.take_order > defense.update_order);
}
static void test_defense_new_start_after_combat_before_new_movement(void)
{
    init(); state->ego = 0; state->serious = 100;
    defense.owns_input = movement.owns_input = true;
    int moves = movement.updates, fights = combat.updates;
    CHECK(frame());
    CHECK(defense.update_combat == fights + 1 && combat.updates == fights + 1);
    CHECK(defense.update_movement == moves && movement.updates == moves);
    CHECK(first_event(EV_COMBAT) < defense.update_events);
    CHECK(first_event(EV_MOVE) == -1);
    CHECK(self->cpu.lstick.y == 47 && self->cpu.lstick.x == 0);
    CHECK(state->action == SB_NONE && state->ego == 0 && state->serious == 99);
    CHECK(ShowboatDefense_GetAction(self) == 10 && defense.rewards == 0);

    init(); combat.owns_input = defense.owns_input = movement.owns_input = true;
    int calls = defense.updates; moves = movement.updates;
    CHECK(frame()); CHECK(self->cpu.buttons == HSD_PAD_B);
    CHECK(defense.updates == calls && movement.updates == moves);
    taunt_context(true); defense.owns_input = true; calls = defense.updates;
    CHECK(frame()); CHECK(state->action == SB_TAUNT && defense.updates == calls);
}
static void test_defense_does_not_preempt_existing_movement(void)
{
    init(); movement.owns_input = true; CHECK(frame());
    defense.owns_input = true;
    int calls = defense.updates, fights = combat.updates, moves = movement.updates;
    CHECK(frame()); CHECK(self->cpu.lstick.x == 66);
    CHECK(defense.updates == calls && combat.updates == fights);
    CHECK(movement.updates == moves + 1);
    movement.owns_input = false; moves = movement.updates;
    CHECK(frame()); CHECK(self->cpu.lstick.y == 47 && !movement.active);
    CHECK(defense.updates == calls + 1 && defense.update_combat == fights + 1);
    CHECK(defense.update_movement == moves + 1 && movement.updates == moves + 1);
    CHECK(first_event(EV_MOVE) < first_event(EV_COMBAT));
    CHECK(first_event(EV_COMBAT) < defense.update_events);
}
static void test_defense_existing_block_serviced_before_new_combat(void)
{
    for (variant = 0; variant < 2; ++variant) {
        init(); defense.owns_input = true; CHECK(frame());
        CHECK(ShowboatDefense_GetAction(self) == 10);
        combat.owns_input = movement.owns_input = true;
        defense.owns_input = variant != 0;
        int calls = defense.updates, fights = combat.updates, moves = movement.updates;
        struct CpuFighter before = self->cpu;
        CHECK(update(self) == (variant != 0));
        CHECK(defense.updates == calls + 1 && defense.update_combat == fights);
        CHECK(combat.updates == fights && movement.updates == moves);
        CHECK(first_event(EV_COMBAT) == -1 && first_event(EV_MOVE) == -1);
        CHECK(state->action == SB_NONE && state->script_size == 0);
        if (variant) {
            CHECK(memcmp(&defense.emitted, &self->cpu, sizeof(self->cpu)) == 0);
            interpret(self); CHECK(self->cpu.lstick.y == 47);
        } else { CHECK(memcmp(&before, &self->cpu, sizeof(before)) == 0); }
    }
}
static void test_defense_false_handoff_never_retakes_low_priority_style(void)
{
    /* Every context would start personality without this existing BLOCK. The
     * neutral idle CPU deliberately removes any incidental bytecode veto. */
    for (int style = 0; style < 6; ++style) {
        for (variant = 0; variant < 4; ++variant) {
            personality_context(style);
            self->cpu.x18 = variant & 1 ? 10 : 1;
            CHECK(frame()); CHECK(state->action != SB_NONE); /* prove the opportunity */
            personality_context(style);
            self->cpu.x18 = variant & 1 ? 10 : 1;
            CHECK(SB_Takeover(self));
            seed_defense(self, 10, false);
            defense.handoff_action = variant & 2 ? 11 : 0;
            movement.owns_input = variant < 2; /* also test personality without movement */
            int calls = defense.updates, fights = combat.updates, moves = movement.updates;
            int old_clears = clears, old_writes = writes;
            struct CpuFighter before = self->cpu;
            u32 random = state->random;
            CHECK(!update(self));
            CHECK(defense.updates == calls + 1 && combat.updates == fights);
            CHECK(movement.updates == moves && state->action == SB_NONE);
            CHECK(state->script_size == 0 && state->random == random);
            CHECK(memcmp(&before, &self->cpu, sizeof(before)) == 0);
            CHECK(clears == old_clears && writes == old_writes);
            CHECK(ShowboatDefense_GetAction(self) == defense.handoff_action);
            CHECK(defense.rewards == 0);
        }
    }
}
static void test_defense_yielding_flourish_preserves_entire_new_vm(void)
{
    const int styles[] = { 0, 1, 3, 4, 5 }; /* certified taunt is higher priority */
    for (variant = 0; variant < 5; ++variant) {
        personality_context(styles[variant]); CHECK(frame());
        CHECK(state->action != SB_NONE && state->script_size > 0);
        defense.owns_input = true;
        int old_clears = clears;
        CHECK(update(self)); /* inspect scheduled VM before any interpreter */
        CHECK(state->action == SB_NONE && state->script_size == 0);
        CHECK(clears == old_clears + 1);
        CHECK(memcmp(&defense.emitted, &self->cpu, sizeof(self->cpu)) == 0);
        CHECK(self->cpu.buffer[0] == CpuCmd_SetLstickY && self->cpu.buffer[1] == 47);
        CHECK(self->cpu.buffer[2] == CpuCmd_Done);
        interpret(self); CHECK(self->cpu.lstick.y == 47 && self->cpu.buttons == 0);
        if (styles[variant] >= 4) {
            CHECK(!state->offstage_style && state->offstage_cooldown == 18);
        }
    }
}
static void test_defense_attempt_and_reflect_motion_never_boost_ego(void)
{
    init(); defense.owns_input = true;
    int takes = defense.takes;
    CHECK(frame()); CHECK(state->ego == 55 && defense.rewards == 0);
    self->motion_id = ftCo_MS_GuardReflect; /* attempt, not collision evidence */
    CHECK(frame()); CHECK(state->ego == 55 && defense.rewards == 0);
    CHECK(defense.takes == takes + 2 && !defense.slots[0].pending);
    CHECK(ShowboatDefense_GetAction(self) == 10);
}
static void test_defense_verified_pending_reward_after_false_update_once(void)
{
    for (variant = 0; variant < 3; ++variant) {
        init(); defense.owns_input = true; CHECK(frame());
        state->ego = variant == 0 ? 0 : variant == 1 ? 55 : 97;
        int expected = variant == 0 ? 8 : variant == 1 ? 63 : 100;
        defense.owns_input = false; defense.perfect_on_update = true;
        int takes = defense.takes, calls = defense.updates;
        CHECK(!update(self)); /* verified contact returns native ownership */
        CHECK(defense.updates == calls + 1 && defense.takes == takes + 1);
        CHECK(defense.take_order > defense.update_order);
        CHECK(state->ego == expected && defense.rewards == 1);
        CHECK(!defense.slots[0].pending && ShowboatDefense_GetAction(self) == 11);
        self->cpu.xA4 = 123; /* isolate future ordinary fallback from style */
        for (int i = 0; i < 3; ++i) { CHECK(!frame()); CHECK(state->ego == expected); }
        CHECK(defense.rewards == 1 && !ShowboatDefense_TakePerfect(self));
    }
}
static void test_defense_perfect_indicator_is_not_active_block_or_reward(void)
{
    init(); seed_defense(self, 11, false);
    combat.owns_input = true;
    int calls = defense.updates, fights = combat.updates;
    CHECK(frame()); CHECK(self->cpu.buttons == HSD_PAD_B);
    CHECK(combat.updates == fights + 1 && defense.updates == calls);
    CHECK(state->ego == 55 && defense.rewards == 0);
    CHECK(ShowboatDefense_GetAction(self) == 11);
}
static void test_defense_pending_reward_is_owner_and_slot_private(void)
{
    init(); CHECK(!update(target));
    seed_defense(target, 11, true);
    CHECK(!frame()); CHECK(state->ego == 55 && defense.slots[1].pending);
    CHECK(!update(target)); CHECK(sb_states[1].ego == 63 && state->ego == 55);
    CHECK(defense.rewards == 1 && !defense.slots[1].pending);
    seed_defense(self, 11, true);
    defense.slots[0].owner = (Fighter*) (uintptr_t) 1;
    CHECK(!frame()); CHECK(state->ego == 55 && defense.rewards == 1);
    CHECK(ShowboatDefense_GetAction(self) == 0); /* never dereference stale owner */
}
static void test_defense_lifecycle_cancels_pending_before_reinitialization(void)
{
    for (variant = 0; variant < 12; ++variant) {
        init(); defense.owns_input = true; CHECK(frame());
        defense.owns_input = false; defense.slots[0].pending = true;
        self->cpu.xA4 = 123;
        int suspends = defense.suspends, resets = defense.resets[0];
        int takes = defense.takes;
        switch (variant) {
        case 0: self->cpu.level = 8; break;
        case 1: world.cpu[0] = false; break;
        case 2: self->kind = FTKIND_FOX; break;
        case 3: self->cpu.xC = 5; break;
        case 4: self->x221F_b3 = true; break;
        case 5: world.entity[1] = NULL; break;
        case 6: world.ally = true; break;
        case 7: world.player_state[2] = 2; break;
        case 8: world.player_state[1] = 0; world.player_state[2] = 2; break;
        case 9: fighters[2].player_id = 1; world.entity[1] = &objects[2]; break;
        case 10: ++self->x8_spawnNum; break;
        case 11: --world.stocks[0]; break;
        }
        CHECK(!update(self));
        CHECK(defense.suspends == suspends + 1);
        CHECK(!defense.slots[0].pending && defense.slots[0].owner == NULL);
        CHECK(defense.rewards == 0 && ShowboatDefense_GetAction(self) == 0);
        /* New self life suspends (discarding pending); configuration/identity
         * loss additionally resets the slot. Neither may pay a stale reward. */
        CHECK(defense.resets[0] == resets + (variant < 10 ? 1 : 0));
        if (variant < 10) { CHECK(defense.suspend_order < defense.reset_order); }
        if (variant < 8) {
            CHECK(state->owner == NULL && defense.takes == takes);
        } else {
            CHECK(state->ego == (variant < 10 ? 55 : 40));
            CHECK(defense.take_order > defense.suspend_order);
        }
    }
}
static void test_defense_owner_replacement_resets_without_stale_dereference(void)
{
    for (variant = 0; variant < 2; ++variant) {
        init(); seed_defense(self, 10, true);
        int resets = defense.resets[0], suspends = defense.suspends;
        Fighter* actor = self;
        if (variant == 0) {
            state->owner = (Fighter*) (uintptr_t) 1;
            defense.slots[0].owner = (Fighter*) (uintptr_t) 1;
        } else {
            fighters[2].player_id = 0; world.entity[0] = &objects[2];
            actor = &fighters[2];
        }
        CHECK(!update(actor));
        CHECK(defense.resets[0] == resets + 1 && defense.suspends == suspends);
        CHECK(defense.slots[0].owner == NULL && !defense.slots[0].pending);
        CHECK(state->owner == actor && state->ego == 55 && defense.rewards == 0);
    }
}
static void test_defense_suspend_discards_pending_and_respects_owner_gates(void)
{
    for (variant = 0; variant < 7; ++variant) {
        init(); seed_defense(self, 10, true);
        int suspends = defense.suspends, resets = defense.resets[0];
        switch (variant) {
        case 0: break; /* eligible suspension retains personality identity */
        case 1: self->cpu.level = 8; break;
        case 2: world.cpu[0] = false; break;
        case 3: self->kind = FTKIND_FOX; break;
        case 4: self->cpu.xC = 5; break;
        case 5: state->owner = (Fighter*) (uintptr_t) 1; break;
        case 6: self->player_id = 255; break;
        }
        suspend(self);
        CHECK(defense.suspends == suspends + (variant < 5 ? 1 : 0));
        CHECK(defense.resets[0] == resets + (variant > 0 && variant < 5 ? 1 : 0));
        CHECK(defense.slots[0].pending == (variant >= 5));
        CHECK(defense.rewards == 0);
        if (variant > 0 && variant < 5) {
            CHECK(defense.suspend_order < defense.reset_order && state->owner == NULL);
        }
        if (variant == 0) {
            CHECK(state->owner == self && state->ego == 55);
            suspend(self); CHECK(defense.suspends == suspends + 2);
            CHECK(!ShowboatDefense_TakePerfect(self));
        }
    }
}
static void test_defense_reset_slot_isolated_bounds_and_bookkeeping_only(void)
{
    init(); seed_defense(self, 11, true); seed_defense(&fighters[2], 10, true);
    defense.slots[2].owner = (Fighter*) (uintptr_t) 1;
    unsigned char before[sizeof(defense)];
    Fighter old_fighters[SB_SLOTS]; memcpy(old_fighters, fighters, sizeof(fighters));
    memcpy(before, &defense, sizeof(defense));
    ShowboatAI_ResetSlot(-1); ShowboatAI_ResetSlot(SB_SLOTS);
    CHECK(memcmp(before, &defense, sizeof(defense)) == 0);
    int resets[SB_SLOTS]; memcpy(resets, defense.resets, sizeof(resets));
    ShowboatAI_ResetSlot(2); ShowboatAI_ResetSlot(2);
    CHECK(defense.slots[2].owner == NULL && defense.slots[2].action == 0);
    CHECK(!defense.slots[2].pending);
    CHECK(defense.slots[0].owner == self && defense.slots[0].pending);
    CHECK(defense.slots[0].action == 11);
    for (int i = 0; i < SB_SLOTS; ++i) {
        CHECK(defense.resets[i] == resets[i] + (i == 2 ? 2 : 0));
    }
    CHECK(memcmp(old_fighters, fighters, sizeof(fighters)) == 0);
}

#include "ego_regressions.c"
#include "recording_cases.c"
#include "safety_cases.c"

#define CASE(name) { #name, test_##name }
static const struct { const char* name; void (*run)(void); } cases[] = {
    CASE(safety_native_vm_filter_before_recording),
    CASE(safety_false_preserves_running_native_output),
    CASE(safety_never_cancels_personality_programs),
    CASE(safety_never_cancels_technical_or_perfect_actions),
    CASE(safety_late_target_identity_and_slot_gates),
    CASE(safety_late_self_spawn_owner_and_eligibility_gates),
    CASE(safety_resumes_only_after_update_rebinds_identity),
    CASE(recording_begin_decision_vm_post_frame_order),
    CASE(recording_output_channels_after_native_vm),
    CASE(recording_decision_action_precedence),
    CASE(recording_decision_after_verified_reward),
    CASE(recording_no_frame_after_lost_eligibility),
    CASE(recording_no_frame_after_lost_target),
    CASE(recording_postinput_late_target_resolution),
    CASE(recording_reset_slot_private_and_bounds),
    CASE(recording_suspend_private_owner_lifecycle),
    CASE(recording_owner_replacement_and_rebaseline),
    CASE(recording_taunt_ack_not_queued),
    CASE(recording_punch_ack_not_queued),
    CASE(recording_last_reason_and_not_evaluated),
    CASE(recording_reason_override_paths),
    CASE(normal_time_ko_taunt_without_stocks),
    CASE(time_ko_certificate_excludes_other_routes),
    CASE(time_ko_rechecks_certificate_before_up),
    CASE(native_locomotion_done_padding_takeover),
    CASE(known_teleport_phases_veto_mockery),
    CASE(offstage_run_settles_using_only_neutral_input),
    CASE(offstage_run_settle_timeout_and_threat_preemption),
    CASE(defense_default_declines_without_input_or_reward),
    CASE(defense_new_start_after_combat_before_new_movement),
    CASE(defense_does_not_preempt_existing_movement),
    CASE(defense_existing_block_serviced_before_new_combat),
    CASE(defense_false_handoff_never_retakes_low_priority_style),
    CASE(defense_yielding_flourish_preserves_entire_new_vm),
    CASE(defense_attempt_and_reflect_motion_never_boost_ego),
    CASE(defense_verified_pending_reward_after_false_update_once),
    CASE(defense_perfect_indicator_is_not_active_block_or_reward),
    CASE(defense_pending_reward_is_owner_and_slot_private),
    CASE(defense_lifecycle_cancels_pending_before_reinitialization),
    CASE(defense_owner_replacement_resets_without_stale_dereference),
    CASE(defense_suspend_discards_pending_and_respects_owner_gates),
    CASE(defense_reset_slot_isolated_bounds_and_bookkeeping_only),
    CASE(offstage_deterministic_repeat_bouts_at_zero_ego),
    CASE(offstage_crouch_fallback_bounded_and_legal),
    CASE(offstage_start_signed_court_and_physical_guards),
    CASE(offstage_active_window_closure_releases_immediately),
    CASE(offstage_far_hitstun_and_return_invulnerability_not_vetoes),
    CASE(offstage_closing_rate_reserve_uses_live_observations),
    CASE(offstage_recent_hit_caution_and_ego_lifecycle),
    CASE(offstage_technical_competence_and_certified_ko_win),
    CASE(personality_verified_mundane_initial_takeover),
    CASE(personality_queued_attack_and_malformed_takeover_veto),
    CASE(personality_active_replacement_vm_preserved_exactly),
    CASE(personality_cache_and_priority_preemption_release_only_owned_vm),
    CASE(personality_unsampled_input_cannot_advance_bout),
    CASE(personality_replacement_vm_survives_lifecycle_exits),
    CASE(offstage_identity_lifecycle_releases_owned_input),
    CASE(neutral_frequency_widened_but_recoveries_and_punishes_yield),
    CASE(certified_taunt_still_rejects_recent_hits_and_physical_risk),
    CASE(long_action_press_preemption_never_forces_animation_exit),
    CASE(v2_policy_constants_and_damage_rounding),
    CASE(initial_spawn_no_danger_penalty),
    CASE(taunt_death_enum_and_budget_boundaries),
    CASE(taunt_safe_overrides_caution_and_style_cooldown),
    CASE(taunt_settles_only_real_ground_movement),
    CASE(taunt_separate_cooldown_and_prepress_revalidation),
    CASE(short_scripts_require_native_state_confirmation),
    CASE(punch_only_long_shieldbreak_daze),
    CASE(flourish_start_preserves_active_vanilla_script),
    CASE(dance_start_world_direction_and_cooldown),
    CASE(dance_real_dash_confirmation_and_end),
    CASE(dance_bounded_updates_without_motion_confirmation),
    CASE(dance_start_court_and_context_guards),
    CASE(dance_active_cancellation_and_ground_edges),
    CASE(dance_signed_next_leg_runway),
    CASE(flourish_yields_real_punish_preserves_fresh_selection),
    CASE(combat_restore_before_early_gates),
    CASE(combat_independent_of_serious_and_flourish_priority),
    CASE(combat_postinput_gating_and_suspend_reset),
    CASE(movement_starts_after_combat_independent_of_ego),
    CASE(active_movement_precedes_other_techniques),
    CASE(movement_suspend_and_reset_orchestration),
    CASE(selective_mercy_commands_and_style_retained),
    CASE(selective_mercy_guard_fallbacks),
    CASE(selective_mercy_indicator_lifecycle),
    CASE(selective_mercy_cannot_bypass_common_safety_gates),
    CASE(opt_in_exclusions),
    CASE(singles_only),
    CASE(initialization_baselines),
    CASE(reset_isolated_and_bounds),
    CASE(owner_replacement_and_stale_identity),
    CASE(opponent_slot_rebaseline),
    CASE(damage_gains_and_clamps),
    CASE(flashy_hit_celebration),
    CASE(damage_punishment_and_trade_priority),
    CASE(punishment_window_expiry),
    CASE(stock_before_spawn_charged_once),
    CASE(spawn_before_stock_charged_once),
    CASE(timed_mode_ignores_stock_counters),
    CASE(ko_event_deduplication),
    CASE(danger_edges_and_serious_recovery),
    CASE(advantage_and_confidence_settling),
    CASE(taunt_finite_native_script),
    CASE(taunt_context_requirements),
    CASE(taunt_certified_no_random_roll),
    CASE(taunt_cooldown_no_spam),
    CASE(swagger_whiff_finite_pulses),
    CASE(whiff_geometry_and_eligibility),
    CASE(whiff_failed_roll_requires_new_edge),
    CASE(cooldown_defers_whiff_roll_without_spam),
    CASE(punch_vulnerability_finite_script),
    CASE(punch_geometry_and_invulnerability),
    CASE(punch_failed_roll_requires_new_edge),
    CASE(start_safety_gates),
    CASE(vanilla_scenario_allowlist),
    CASE(cancel_forced_priority_and_geometry),
    CASE(cancel_configuration_and_opponent_loss),
    CASE(cancel_action_specific_threats),
    CASE(idle_fallback_preserves_vanilla_input),
    CASE(rng_deterministic_and_slot_private),
    CASE(stub_done_does_not_release_input),
    CASE(cancel_when_singles_opponent_slot_changes),
    CASE(attack_weight_verified_air_commands_only),
    CASE(attack_weight_confidence_scaling_and_zero),
    CASE(attack_weight_exclusions_and_safety),
    CASE(stock_before_delayed_spawn_charged_once),
    CASE(platform_and_crouched_punch_veto),
    CASE(suspend_clears_active_input_and_celebration),
    CASE(suspend_disabled_configuration_resets_slot),
    CASE(suspend_stale_owner_and_invalid_slot_noop),
};
int main(int argc, char** argv)
{
    if (argc != 2) { fprintf(stderr, "usage: %s CASE\n", argv[0]); return 2; }
    case_name = argv[1];
    for (size_t i = 0; i < sizeof(cases) / sizeof(cases[0]); ++i) {
        if (strcmp(cases[i].name, case_name) == 0) {
            cases[i].run(); safety_verified();
            printf("PASS %s\n", case_name); return 0;
        }
    }
    fprintf(stderr, "unknown case: %s\n", case_name);
    return 2;
}
