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
} world;
static int clears, scripts, writes;
static struct TestFighterData fighter_data;
struct TestFighterData* Fighter_804D64FC = &fighter_data;
static unsigned char air_table[32], ground_table[32];
static Fighter* const self = &fighters[0];
static Fighter* const target = &fighters[1];
static SB_State* const state = &sb_states[0];

static void valid_slot(int slot) { CHECK(slot >= 0 && slot < SB_SLOTS); }
Fighter_GObj* Player_GetEntity(int slot)
{ valid_slot(slot); return world.entity[slot]; }
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
{ valid_slot(fp->player_id); return world.cpu[fp->player_id]; }
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
    result = ShowboatAI_Update(fp);
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
    /* The actual KO edge supplies ego +22 and celebration. */
}
static void whiff_context(bool success)
{
    init();
    state->ego = 60;
    state->random = seed_for(50, success);
    target->cur_pos.x = 60;
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
    target->motion_id = ftCo_MS_DownWaitU;
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
    CHECK(state->ego == 30 && state->tick == 1);
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
    ShowboatAI_ResetSlot(0); CHECK(!frame()); CHECK(state->ego == 30);
}
static void test_owner_replacement_and_stale_identity(void)
{
    init(); state->ego = 99; state->serious = 100; state->cooldown = 200;
    /* Freed owner identity must not be dereferenced, even during reinitialization. */
    state->owner = (Fighter*) (uintptr_t) 1;
    CHECK(!frame()); CHECK(state->owner == self && state->ego == 30);
    CHECK(state->serious == 0 && state->cooldown == 0);
    fighters[2].player_id = 0; world.entity[0] = &objects[2];
    state->ego = 90;
    CHECK(!update(&fighters[2]));
    CHECK(state->owner == &fighters[2] && state->ego == 30);
    CHECK(state->spawn == (u32) fighters[2].x8_spawnNum);
}
static void test_opponent_slot_rebaseline(void)
{
    init(); state->ego = 99;
    world.player_state[1] = 0; world.player_state[2] = 2;
    fighters[2].dmg.x1830_percent = 85; world.stocks[2] = 1;
    CHECK(!frame());
    CHECK(state->opponent_slot == 2 && state->ego == 30);
    CHECK(state->opponent_percent == 85 && state->opponent_stocks == 1);
    CHECK(state->celebration == 0);
}
static void test_damage_gains_and_clamps(void)
{
    init(); target->dmg.x1830_percent = 10;
    CHECK(!frame()); CHECK(state->ego == 36);
    CHECK(!frame()); CHECK(state->ego == 36); /* delta, not total */
    target->dmg.x1830_percent += 100;
    CHECK(!frame()); CHECK(state->ego == 48); /* per-update cap */
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
        CHECK(!frame()); CHECK(state->ego == 44 && state->celebration == 120);
        CHECK(!frame()); CHECK(state->ego == 44 && state->celebration == 119);
    }
    init(); target->motion_id = ftCo_MS_DeadDown; state->opponent_dead = true;
    target->dmg.x1830_percent = 20;
    CHECK(!frame()); CHECK(state->ego == 30); /* not a hit on a live opponent */
    init(); self->x221C_b6 = true; target->dmg.x1830_percent = 20;
    CHECK(!frame()); CHECK(state->ego == 15); /* danger only, no gain */
}
static void test_damage_punishment_and_trade_priority(void)
{
    whiff_context(true); CHECK(frame());
    state->ego = 90; self->dmg.x1830_percent = 10;
    target->dmg.x1830_percent = 40; /* trade must not award confidence */
    expect_cancel();
    CHECK(state->ego == 50); /* -(5 + 15) -20 */
    CHECK(state->serious == SB_SERIOUS_FRAMES && state->recent_style == 0);
    CHECK(state->celebration == 0);
    CHECK(!frame()); CHECK(state->ego == 50 && state->serious == 299);
    self->dmg.x1830_percent += 2;
    CHECK(!frame()); CHECK(state->ego == 42); /* punishment charged only once */
    self->dmg.x1830_percent = 0;
    CHECK(!frame()); CHECK(state->ego == 42 && state->percent == 0);
    self->dmg.x1830_percent = 1;
    CHECK(!frame()); CHECK(state->ego == 36); /* new baseline after healing */
}
static void test_punishment_window_expiry(void)
{
    init(); state->ego = 90; state->recent_style = 1;
    self->dmg.x1830_percent = 10;
    CHECK(!frame()); CHECK(state->ego == 70 && state->recent_style == 0);
}
static void check_new_life_order(bool spawn_first)
{
    whiff_context(true); CHECK(frame()); state->ego = 90;
    self->dmg.x1830_percent = 35;
    if (spawn_first) { ++self->x8_spawnNum; } else { --world.stocks[0]; }
    expect_cancel();
    CHECK(state->ego == 60 && state->serious == 600);
    CHECK(state->percent == 35 && state->celebration == 0);
    self->dmg.x1830_percent = 0;
    if (spawn_first) { --world.stocks[0]; } else { ++self->x8_spawnNum; }
    CHECK(!frame()); CHECK(state->ego == 60 && state->serious == 600);
    CHECK(state->spawn == (u32) self->x8_spawnNum && state->stocks == 3);
    CHECK(!frame()); CHECK(state->ego == 60 && state->serious == 599);
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
    CHECK(!frame()); CHECK(state->ego == 40 && state->serious == 600);
}
static void test_ko_event_deduplication(void)
{
    for (variant = 0; variant < 2; ++variant) {
        init(); state->cooldown = 1000;
        if (variant == 0) { target->motion_id = ftCo_MS_DeadDown; }
        else { --world.stocks[1]; }
        CHECK(!frame()); CHECK(state->ego == 52 && state->ko_lockout == 240);
        CHECK(state->celebration == 120);
        if (variant == 0) { --world.stocks[1]; }
        else { target->motion_id = ftCo_MS_DeadDown; }
        CHECK(!frame()); CHECK(state->ego == 52 && state->ko_lockout == 239);
        target->motion_id = ftCo_MS_Rebirth;
        CHECK(!frame()); CHECK(!state->opponent_dead);
        state->ko_lockout = 1;
        target->motion_id = ftCo_MS_DeadDown;
        CHECK(!frame()); CHECK(state->ego == 74 && state->ko_lockout == 240);
    }
}
static void test_danger_edges_and_serious_recovery(void)
{
    init(); state->ego = 90; state->celebration = 100;
    self->x221C_b6 = true;
    CHECK(!frame()); CHECK(state->ego == 75 && state->serious == 180);
    CHECK(state->danger && state->celebration == 0);
    for (int i = 0; i < 10; ++i) { CHECK(!frame()); }
    CHECK(state->ego == 75 && state->serious == 180);
    self->x221C_b6 = false;
    CHECK(!frame()); CHECK(!state->danger && state->serious == 179);
    state->tick = 0;
    for (int i = 0; i < 179; ++i) { CHECK(!frame()); }
    CHECK(state->serious == 0);
    int old = state->ego;
    self->ground_or_air = GA_Air; self->cpu.xFA_b5 = false;
    CHECK(!frame()); CHECK(state->ego == old - 15 && state->danger);
}
static void test_advantage_and_confidence_settling(void)
{
    for (variant = 0; variant < 3; ++variant) {
        setup();
        if (variant == 0) { world.stocks[1] = 3; }
        if (variant == 1) { target->dmg.x1830_percent = 30; world.stock_match = false; }
        if (variant == 2) { target->dmg.x1830_percent = 100; self->dmg.x1830_percent = 79; }
        for (int i = 0; i < SB_ADVANTAGE_PERIOD - 1; ++i) { CHECK(!frame()); }
        CHECK(state->ego == 30);
        CHECK(!frame()); CHECK(state->ego == 33 && state->tick == 0);
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
        CHECK(state->ego == 52 && state->cooldown == SB_TAUNT_COOLDOWN);
        CHECK(state->recent_style == SB_PUNISH_WINDOW && state->celebration == 0);
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
    for (variant = 0; variant < 6; ++variant) {
        init(); state->ego = 60; state->celebration = 100;
        state->random = seed_for(80, true); target->x221C_b6 = true;
        switch (variant) {
        case 0: state->ego = 44; break;
        case 1: state->celebration = 0; break;
        case 2: target->x221C_b6 = false; break;
        case 3: target->cur_pos.x = 90; break;
        case 4: world.invincible[1] = 1; break;
        case 5: target->cur_pos.x = -90; break;
        }
        u32 random = state->random;
        CHECK(!frame()); CHECK(state->action == SB_NONE && state->random == random);
    }
    init(); state->ego = 45; state->celebration = 100;
    state->random = seed_for(80, true); target->x221C_b6 = true;
    CHECK(frame()); CHECK(state->action == SB_TAUNT);
    taunt_context(true); target->cur_pos.x = 0; world.invincible[1] = 2;
    CHECK(frame()); CHECK(state->action == SB_TAUNT); /* dead target exception */
}
static void test_taunt_failed_roll_is_not_retried(void)
{
    taunt_context(false);
    CHECK(!frame()); CHECK(state->celebration == 0 && state->cooldown == 0);
    u32 random = state->random;
    for (int i = 0; i < SB_TAUNT_COOLDOWN * 2; ++i) { CHECK(!frame()); }
    CHECK(state->random == random && scripts == 0);
}
static void test_taunt_cooldown_no_spam(void)
{
    taunt_context(true);
    CHECK(frame()); CHECK(frame()); CHECK(frame()); CHECK(!frame());
    u32 random = state->random;
    for (int i = 0; i < SB_TAUNT_COOLDOWN * 2; ++i) { CHECK(!frame()); }
    CHECK(state->cooldown == 0 && scripts == 3 && state->random == random);
    /* Fresh contextual opportunity is allowed after cooldown, not a periodic taunt. */
    target->motion_id = ftCo_MS_Wait; CHECK(!frame());
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
    whiff_context(true); target->cur_pos.x = -60; target->facing_dir = -1;
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
    const int down[] = { ftCo_MS_DownBoundU, ftCo_MS_DownWaitU,
        ftCo_MS_DownBoundD, ftCo_MS_DownWaitD, ftCo_MS_Furafura };
    for (variant = 0; variant < 5; ++variant) {
        punch_context(true); target->motion_id = down[variant];
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
    target->motion_id = ftCo_MS_DownWaitD; state->random = seed_for(35, true);
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
        bool allowed = variant == 1 || variant == 2 || variant == 3 ||
                       variant == 8 || variant == 10;
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
            case 6: self->dmg.x1830_percent = state->percent = 110; break;
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
    --world.stocks[0]; CHECK(!frame()); CHECK(state->ego == 60);
    /* Death animations can last longer than a short deduplication heuristic. */
    for (int i = 0; i < 150; ++i) { CHECK(!frame()); }
    int ego = state->ego;
    ++self->x8_spawnNum;
    CHECK(!frame()); CHECK(state->ego == ego && state->serious == 600);
    /* A second real life/stock loss is not exempt just because serious is high. */
    --world.stocks[0]; ++self->x8_spawnNum;
    CHECK(!frame()); CHECK(state->ego == (ego > 30 ? ego - 30 : 0));
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

#define CASE(name) { #name, test_##name }
static const struct { const char* name; void (*run)(void); } cases[] = {
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
    CASE(taunt_failed_roll_is_not_retried),
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
