/* Deterministic HOST unit tests, NOT an emulator/in-game test.
 * Include production verbatim: no copied personality logic and no #define static.
 * See test_showboat_ai.py for scope, compiler setup, and how to run.
 */
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
    bool owns_input, borrowed;
    Fighter* borrower;
    s8 saved_x;
    int resets[SB_SLOTS], restores, updates, aborts, posts, actions;
    Fighter* last_actor;
    Fighter* last_target;
} combat;
static struct {
    bool owns_input, active;
    Fighter* owner;
    int owner_slot, updates, suspends, resets[SB_SLOTS];
} movement;
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
void OSReport(const char* format, ...) { CHECK(format != NULL); }

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
}
int ShowboatCombat_GetAction(Fighter* fp)
{
    CHECK(fp != NULL); event(EV_ACTION); ++combat.actions; return 5;
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
    movement.active = movement.owns_input;
    if (!movement.owns_input) { return false; }
    movement.owner = fp; movement.owner_slot = fp->player_id;
    ftCo_800B4A78(fp); fp->cpu.xA4 = 0;
    ftCo_800B46B8(fp, CpuCmd_SetLstickX, 66); /* distinguish from combat's B */
    ftCo_800B49F4(fp);
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
    CHECK(combat.actions == 0); /* personality suite explicitly disables HUD */
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
static void dirty_input(Fighter* fp)
{
    fp->cpu.xA4 = 123;
    fp->cpu.buttons = 0xffff;
    fp->cpu.lstick.x = 77; fp->cpu.lstick.y = -100;
    fp->cpu.cstick.x = -44; fp->cpu.cstick.y = 55;
    fp->cpu.ltrigger = 123; fp->cpu.rtrigger = 234;
    fp->cpu.buffer[0] = CpuCmd_PressB;
    fp->cpu.buffer[1] = CpuCmd_Done;
    fp->cpu.write_pos = fp->cpu.buffer + 2;
    fp->cpu.csP = fp->cpu.buffer;
    fp->cpu.command_duration = 1;
}
static void setup(void)
{
    tracing = false; event_count = 0;
    memset(&combat, 0, sizeof(combat));
    memset(&movement, 0, sizeof(movement));
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
    init();
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
    init();
    state->ego = 85;
    state->random = seed_for(35, success);
    target->cur_pos.x = 30;
    target->motion_id = ftCo_MS_Furafura;
    target->grab_timer = 301;
}
static void expect_cancel(void)
{
    int old_clears = clears;
    dirty_input(self);
    CHECK(!update(self)); /* no interpreter: inputs must already be clear */
    CHECK(state->action == SB_NONE);
    CHECK(clears == old_clears + 1);
    neutral(self);
    CHECK(self->cpu.csP == NULL && self->cpu.command_duration == 0);
    CHECK(self->cpu.write_pos == self->cpu.buffer);
    CHECK(self->cpu.xA4 == 0);
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
        taunt_context(true); dirty_input(self);
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
    target->mv.co.unk_deadleft.x40 = 20;
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
    whiff_context(true); CHECK(frame()); dirty_input(self);
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
        whiff_context(true); CHECK(frame()); dirty_input(self);
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
    state->ego = 60; state->random = seed_for(75, success);
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
        CHECK(state->cooldown == (variant & 2 ? 60 : 90));
        neutral(self); CHECK(self->cpu.write_pos - self->cpu.buffer == 1);
        CHECK(frame()); CHECK(self->cpu.lstick.x == -side * 127);
        CHECK(self->cpu.buffer[0] == CpuCmd_SetLstickX);
        CHECK(self->cpu.write_pos - self->cpu.buffer == 3);
        CHECK(self->cpu.buttons == 0 && self->cpu.lstick.y == 0);
    }
    dance_context(false); CHECK(!frame()); CHECK(state->cooldown == 45);
    u32 random = state->random;
    for (int i = 0; i < 44; ++i) { CHECK(!frame()); }
    CHECK(state->random == random && state->cooldown == 1);
    state->random = seed_for(75, true); CHECK(frame());
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
        case 13: target->cur_pos.x = 115.01f; break;
        case 14: target->cur_pos.y = 20; break;
        case 15: target->x221C_b6 = true; break;
        case 16: target->motion_id = ftCo_MS_DownWaitU; break;
        case 17: world.invincible[1] = 1; break;
        case 18: self->motion_id = ftCo_MS_Run; break;
        case 19: state->ego = 39; break;
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
            dirty_input(self); self->cpu.x18 = priority[variant]; self->cpu.xA4 = 8;
            CHECK(!update(self)); CHECK(state->action == SB_NONE);
            neutral(self); CHECK(self->cpu.csP == NULL && self->cpu.command_duration == 0);
            /* Dance preserves fresh selection on EVERY native-priority yield;
             * swagger does so inside its 1/2/3/8/10 input path. */
            bool preserve = dance || priority[variant] == 2 || priority[variant] == 3 ||
                            priority[variant] == 8;
            CHECK(self->cpu.xA4 == (preserve ? 8 : 0));
        }
    }
    for (variant = 0; variant < 2; ++variant) {
        whiff_context(true); CHECK(frame()); dirty_input(self);
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

#define CASE(name) { #name, test_##name }
static const struct { const char* name; void (*run)(void); } cases[] = {
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
            cases[i].run(); printf("PASS %s\n", case_name); return 0;
        }
    }
    fprintf(stderr, "unknown case: %s\n", case_name);
    return 2;
}
