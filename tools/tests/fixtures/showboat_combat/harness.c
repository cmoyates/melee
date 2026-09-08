/* Actual production C, included verbatim. Host observations, not game physics.
 * All motion/animation/hitstun changes are explicit test stimuli; the tiny VM
 * only processes controller commands. No mocked fighter transition function. */
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "showboat_combat.c"

static const char* case_name;
static int variant;
#define CHECK(e) do { if (!(e)) { \
    fprintf(stderr, "%s variant=%d %s:%d: %s\n", \
            case_name, variant, __FILE__, __LINE__, #e); exit(1); \
} } while (0)
#define CLOSE(a, b) CHECK(fabsf((a) - (b)) < 0.0001f)
#define N 6
static Fighter fighters[N];
static Fighter_GObj objects[N];
static Fighter* const self = &fighters[0];
static Fighter* const target = &fighters[1];
static struct {
    bool cpu[N], floor_enabled;
    int protection[N], floor_line;
    StKind stage;
    float anim_end[N], floor_y, floor_normal_y, floor_left, floor_right;
} world;
static struct TestCommonData rules;
struct TestCommonData* p_ftCommonData = &rules;
static struct {
    int clears, scripts, writes, floor, anim, triggers;
    struct { float ax, ay, bx, by; int skip, joint_skip, joint_only; } sweep[8192];
} calls;
static Fighter* allowed_actor;
static int index_of(Fighter* fp)
{
    for (int i = 0; i < N; ++i) { if (fp == &fighters[i]) { return i; } }
    CHECK(!"unknown fighter in engine query"); return -1;
}
bool ftCo_800A2040(Fighter* fp) { return world.cpu[index_of(fp)]; }
int ftColl_8007B868(Fighter_GObj* gobj)
{ CHECK(gobj); return world.protection[index_of(GET_FIGHTER(gobj))]; }
float ftAnim_8006F484(Fighter_GObj* gobj)
{ CHECK(gobj); ++calls.anim; return world.anim_end[index_of(GET_FIGHTER(gobj))]; }
float ftCo_GetCpuLTrigger(Fighter* fp)
{ index_of(fp); ++calls.triggers; return fp->cpu.ltrigger / 255.0f; }
float ftCo_GetCpuRTrigger(Fighter* fp)
{ index_of(fp); ++calls.triggers; return fp->cpu.rtrigger / 255.0f; }
void OSReport(const char* format, ...) { CHECK(format != NULL); }
static void local_output(void* p, size_t size)
{
    uintptr_t a = (uintptr_t) p, b = (uintptr_t) fighters;
    CHECK(p != NULL && (a + size <= b || a >= b + sizeof(fighters)));
    b = (uintptr_t) &world;
    CHECK(a + size <= b || a >= b + sizeof(world));
}
bool mpCheckFloor(float ax, float ay, float bx, float by, float offset,
                  Vec3* contact, int* line, u32* flags, Vec3* normal,
                  int skip, int joint_skip, int joint_only,
                  bool (*callback)(Fighter_GObj*, int), Fighter_GObj* gobj)
{
    /* Explicit flat-floor query, NOT a stubbed ETA or collision engine.
     * Captures every segment and checks production uses temporary outputs. */
    int n = calls.floor++;
    CHECK(n < 8192); CHECK(offset == 0); CHECK(!callback && !gobj);
    CHECK(isfinite(ax) && isfinite(ay) && isfinite(bx) && isfinite(by));
    local_output(contact, sizeof(*contact)); local_output(line, sizeof(*line));
    local_output(flags, sizeof(*flags)); local_output(normal, sizeof(*normal));
    calls.sweep[n].ax = ax; calls.sweep[n].ay = ay;
    calls.sweep[n].bx = bx; calls.sweep[n].by = by;
    calls.sweep[n].skip = skip; calls.sweep[n].joint_skip = joint_skip;
    calls.sweep[n].joint_only = joint_only;
    if (!world.floor_enabled || skip == world.floor_line ||
        by >= ay || ay < world.floor_y || by > world.floor_y) { return false; }
    float x = ax + (bx - ax) * (world.floor_y - ay) / (by - ay);
    if (x < world.floor_left || x > world.floor_right) { return false; }
    *contact = (Vec3) { x, world.floor_y, 0 };
    *line = world.floor_line; *flags = 0x1234;
    *normal = (Vec3) { 0, world.floor_normal_y, 0 };
    return true;
}

StKind Stage_80225194(void) { return world.stage; }
void mpFloorGetLeft(int line, Vec3* out)
{
    CHECK(line == world.floor_line); local_output(out, sizeof(*out));
    *out = (Vec3) { world.floor_left, world.floor_y, 0 };
}
void mpFloorGetRight(int line, Vec3* out)
{
    CHECK(line == world.floor_line); local_output(out, sizeof(*out));
    *out = (Vec3) { world.floor_right, world.floor_y, 0 };
}

/* Audited subset of ftcmdscript.c. Unknown opcodes fail at emission AND VM.
 * WaitFor pauses after decrementing the native command_duration. Done doesn't
 * clear persistent inputs; release tails must really execute. */
static bool unary(u8 op)
{
    return op == CpuCmd_PressZ || op == CpuCmd_ReleaseZ ||
           op == CpuCmd_PressA || op == CpuCmd_ReleaseA || op == CpuCmd_Done;
}
static bool binary(u8 op)
{
    return op == CpuCmd_WaitFor || op == CpuCmd_SetLstickX ||
           op == CpuCmd_SetLstickY || op == CpuCmd_SetCstickX ||
           op == CpuCmd_SetCstickY;
}
static void byte(Fighter* fp, u8 value)
{
    CHECK(fp == allowed_actor);
    CHECK(fp->cpu.write_pos >= fp->cpu.buffer);
    CHECK(fp->cpu.write_pos < fp->cpu.buffer + sizeof(fp->cpu.buffer));
    *fp->cpu.write_pos++ = (s8) value; ++calls.writes;
}
void ftCo_800B4A78(Fighter* fp)
{
    CHECK(fp == allowed_actor); ++calls.clears;
    fp->cpu.buttons = 0;
    fp->cpu.lstick = fp->cpu.cstick = (TestStick) { 0, 0 };
    fp->cpu.ltrigger = fp->cpu.rtrigger = 0;
    fp->cpu.csP = NULL; fp->cpu.command_duration = 0;
    fp->cpu.write_pos = fp->cpu.buffer;
}
void ftCo_800B463C(Fighter* fp, u8 op)
{ CHECK(unary(op)); byte(fp, op); }
void ftCo_800B46B8(Fighter* fp, u8 op, u8 arg)
{ CHECK(binary(op)); byte(fp, op); byte(fp, arg); }
void ftCo_800B49F4(Fighter* fp)
{
    ftCo_800B463C(fp, CpuCmd_Done); ++calls.scripts;
    fp->cpu.csP = fp->cpu.buffer; fp->cpu.command_duration = 1;
}
static void interpret(Fighter* fp)
{
    struct CpuFighter* c = &fp->cpu;
    if (!c->csP || !c->command_duration || --c->command_duration) { return; }
    for (int budget = 0; budget < 32; ++budget) {
        CHECK(c->csP >= c->buffer && c->csP < c->write_pos);
        u8 op = (u8) *c->csP++;
        s8 arg = 0;
        if (binary(op)) { CHECK(c->csP < c->write_pos); arg = *c->csP++; }
        switch (op) {
        case CpuCmd_PressZ: c->buttons |= HSD_PAD_Z; break;
        case CpuCmd_ReleaseZ: c->buttons &= ~HSD_PAD_Z; break;
        case CpuCmd_PressA: c->buttons |= HSD_PAD_A; break;
        case CpuCmd_ReleaseA: c->buttons &= ~HSD_PAD_A; break;
        case CpuCmd_SetLstickX: c->lstick.x = arg; break;
        case CpuCmd_SetLstickY: c->lstick.y = arg; break;
        case CpuCmd_SetCstickX: c->cstick.x = arg; break;
        case CpuCmd_SetCstickY: c->cstick.y = arg; break;
        case CpuCmd_WaitFor:
            CHECK(arg == 1); c->command_duration = (u8) arg; return;
        case CpuCmd_Done:
            CHECK(c->csP == c->write_pos); c->csP = NULL; return;
        default: CHECK(!"unknown input opcode: implement explicitly");
        }
    }
    CHECK(!"input VM exceeded bounded command budget");
}

/* Every public API call snapshots every fixture fighter, GObj, query answer,
 * and common-data/rules byte. Only ACTOR cpu inputs/script/cached A4 may change;
 * scenario, CPU config, frame input, tech/LR counters, physics, damage, animation,
 * collisions, target and other slots remain byte-identical. */
static void input_only(const Fighter* before, const Fighter* after)
{
    Fighter masked;
    memcpy(&masked, after, sizeof(masked));
#define ALLOW(f) memcpy(&masked.cpu.f, &before->cpu.f, sizeof(masked.cpu.f))
    ALLOW(buttons); ALLOW(lstick); ALLOW(cstick); ALLOW(ltrigger); ALLOW(rtrigger);
    ALLOW(buffer); ALLOW(write_pos); ALLOW(csP); ALLOW(command_duration); ALLOW(xA4);
#undef ALLOW
    CHECK(memcmp(before, &masked, sizeof(masked)) == 0);
}
enum Operation { UPDATE, POST, RESTORE, ACTION, RESET, INTERPRET };
static int invoke(enum Operation op, Fighter* fp, Fighter* other, int slot)
{
    Fighter before[N]; Fighter_GObj old_objects[N];
    unsigned char old_world[sizeof(world)], old_rules[sizeof(rules)];
    memcpy(before, fighters, sizeof(before));
    memcpy(old_objects, objects, sizeof(objects));
    memcpy(old_world, &world, sizeof(world)); memcpy(old_rules, &rules, sizeof(rules));
    int result = 0, scripts = calls.scripts;
    allowed_actor = fp;
    switch (op) {
    case UPDATE: result = ShowboatCombat_Update(fp, other); break;
    case POST: ShowboatCombat_PostInput(fp); break;
    case RESTORE: ShowboatCombat_RestoreInput(fp); break;
    case ACTION: result = ShowboatCombat_GetAction(fp); break;
    case RESET: ShowboatCombat_ResetSlot(slot); break;
    case INTERPRET: interpret(fp); break;
    }
    allowed_actor = NULL;
    for (int i = 0; i < N; ++i) {
        if (&fighters[i] == fp && op != ACTION && op != RESET) {
            input_only(&before[i], &fighters[i]);
        } else { CHECK(memcmp(&before[i], &fighters[i], sizeof(Fighter)) == 0); }
    }
    CHECK(memcmp(old_objects, objects, sizeof(objects)) == 0);
    CHECK(memcmp(old_world, &world, sizeof(world)) == 0);
    CHECK(memcmp(old_rules, &rules, sizeof(rules)) == 0);
    CHECK(p_ftCommonData == &rules);
    if (op == UPDATE && result) {
        CHECK(calls.scripts == scripts + 1);
        CHECK(fp->cpu.xA4 == 0 && fp->cpu.csP == fp->cpu.buffer);
        CHECK(fp->cpu.command_duration == 1);
        CHECK(fp->cpu.write_pos > fp->cpu.buffer);
        CHECK(fp->cpu.write_pos <= fp->cpu.buffer + 13);
        CHECK(fp->cpu.write_pos[-1] == CpuCmd_Done);
    } else { CHECK(calls.scripts == scripts); }
    return result;
}
static bool update(Fighter* fp, Fighter* other) { return invoke(UPDATE, fp, other, 0); }
static void post(Fighter* fp) { invoke(POST, fp, NULL, 0); }
static void restore(Fighter* fp) { invoke(RESTORE, fp, NULL, 0); }
static int action(Fighter* fp) { return invoke(ACTION, fp, NULL, 0); }
static void vm(Fighter* fp) { invoke(INTERPRET, fp, NULL, 0); }
static void reset(int slot) { invoke(RESET, NULL, NULL, slot); }
static bool frame(void) { bool r = update(self, target); vm(self); return r; }
static void neutral(void)
{
    CHECK(self->cpu.buttons == 0);
    CHECK(self->cpu.lstick.x == 0 && self->cpu.lstick.y == 0);
    CHECK(self->cpu.cstick.x == 0 && self->cpu.cstick.y == 0);
    CHECK(self->cpu.ltrigger == 0 && self->cpu.rtrigger == 0);
}
static void setup(void)
{
    memset(fighters, 0, sizeof(fighters)); memset(objects, 0, sizeof(objects));
    memset(&world, 0, sizeof(world)); memset(&rules, 0, sizeof(rules));
    for (int i = 0; i < N; ++i) {
        Fighter* fp = &fighters[i];
        reset(i); objects[i].user_data = fp; fp->gobj = &objects[i];
        fp->kind = FTKIND_CAPTAIN; fp->player_id = (u8) i; fp->x8_spawnNum = 100 + i;
        fp->motion_id = ftCo_MS_Wait; fp->ground_or_air = GA_Ground;
        fp->facing_dir = 1; fp->cur_pos.x = i * 100; fp->cur_pos.z = 3;
        fp->frame_speed_mul = 1; fp->cur_anim_frame = 2;
        fp->cpu.level = 9; fp->cpu.xC = 4; fp->cpu.x18 = 1; fp->cpu.xA4 = 0;
        fp->cpu.xFA_b5 = true; fp->cpu.write_pos = fp->cpu.buffer;
        fp->coll_data.floor.index = 4; fp->coll_data.floor_skip = -1;
        fp->coll_data.joint_id_skip = -7; fp->coll_data.joint_id_only = -9;
        fp->co_attrs.gravity = 0.25f; fp->co_attrs.terminal_velocity = 4;
        fp->co_attrs.fast_fall_velocity = 6;
        fp->co_attrs.air_drift_max = 1;
        fp->co_attrs.air_max_horizontal_velocity = 2;
        fp->x67F = 255; fp->x680 = 17; fp->x681 = 21; fp->x682 = 83;
        fp->x683 = 5; fp->x684 = 199; fp->x685 = 231;
        fp->input.lstick[1] = (Vec2) { 0.31f, -0.72f };
        fp->input.cstick[1] = (Vec2) { -0.41f, 0.22f };
        fp->input.pressed_buttons = HSD_PAD_B; fp->input.ltrigger = 0.11f;
        fp->dmg.x1830_percent = 73.5f;
        world.cpu[i] = true; world.anim_end[i] = 30;
    }
    target->cur_pos.x = 8; target->motion_id = ftCo_MS_Guard;
    world.floor_enabled = true; world.floor_line = 4; world.floor_normal_y = 1;
    world.floor_left = -1000; world.floor_right = 1000;
    rules.analog_shoulder_deadzone = 0.3f; rules.xE4 = 7;
    rules.x204_knockbackFrameDecay = 0.051f;
    world.stage = St_Kind_Last;
    memset(&calls, 0, sizeof(calls));
}
static void lc_setup(void)
{
    setup();
    self->ground_or_air = GA_Air; self->motion_id = ftCo_MS_AttackAirF;
    self->cmd_vars[0] = 1; self->self_vel.y = -1; self->pos_delta.y = -1;
    self->coll_data.cur_pos = (Vec3) { 20, 3, 0 };
    self->coll_data.ecb.bottom = (Vec2) { 2, -2 };
    /* Distinct from ECB coordinates: catches using fighter origin for sweep. */
    self->cur_pos = (Vec3) { 500, 90, 3 };
    self->pos_delta.x = 0.5f;
    self->input.lstick[0] = (Vec2) { 0.31f, -0.72f };
    self->input.cstick[0] = (Vec2) { -0.41f, 0.22f };
    self->cpu.ltrigger = 23; self->cpu.rtrigger = 29;
    self->cpu.buttons = HSD_PAD_A | HSD_PAD_B;
    self->cpu.lstick = (TestStick) { -57, -88 };
    self->cpu.cstick = (TestStick) { 41, 33 };
}
static void expect_no_start(void)
{
    struct CpuFighter before;
    memcpy(&before, &self->cpu, sizeof(before));
    CHECK(!update(self, target)); CHECK(action(self) == 0);
    CHECK(memcmp(&before, &self->cpu, sizeof(before)) == 0);
}
static void expect_no_lc(void)
{
    struct CpuFighter before;
    memcpy(&before, &self->cpu, sizeof(before)); post(self);
    CHECK(memcmp(&before, &self->cpu, sizeof(before)) == 0);
}
static void expect_lc(void)
{
    struct CpuFighter before, masked;
    memcpy(&before, &self->cpu, sizeof(before)); post(self);
    CHECK(self->cpu.ltrigger == 128);
    memcpy(&masked, &self->cpu, sizeof(masked)); masked.ltrigger = before.ltrigger;
    CHECK(memcmp(&before, &masked, sizeof(before)) == 0);
    CHECK(!(self->cpu.buttons & (HSD_PAD_L | HSD_PAD_R | HSD_PAD_Z | HSD_PAD_LR)));
}

static void grab_neutral_pulse_ack_release(void)
{
    int ack[] = { ftCo_MS_Catch, ftCo_MS_CatchDash };
    for (variant = 0; variant < 2; ++variant) {
        setup();
        self->cpu.lstick = (TestStick) { 40, -10 };
        CHECK(frame()); CHECK(action(self) == 5); neutral();
        CHECK(frame()); CHECK(self->cpu.buttons == HSD_PAD_Z);
        CHECK(action(self) == 5);
        self->motion_id = ack[variant]; /* External engine acknowledgement. */
        CHECK(!update(self, target)); CHECK(action(self) == 0); neutral();
        CHECK(sc_states[self->player_id].cooldown == 0);
    }
}
static void grab_release_tail_without_update(void)
{
    setup(); CHECK(frame()); CHECK(frame()); CHECK(self->cpu.buttons == HSD_PAD_Z);
    vm(self); neutral(); CHECK(!self->cpu.csP && !self->cpu.command_duration);
    CHECK(!update(self, target)); CHECK(action(self) == 0);
}
static void grab_failed_press_cooldown(void)
{
    setup(); CHECK(frame()); CHECK(frame());
    /* Same native Wait forever: script age is NOT an animation transition. */
    CHECK(!update(self, target)); neutral(); CHECK(action(self) == 0);
    for (int i = 0; i < 44; ++i) { CHECK(!frame()); }
    CHECK(frame()); CHECK(action(self) == 5); neutral();
}
static void grab_native_capture_priority(void)
{
    for (variant = 0; variant < 2; ++variant) {
        setup(); CHECK(frame()); CHECK(frame());
        self->motion_id = ftCo_MS_Catch; self->victim_gobj = target->gobj;
        if (variant) { self->cpu.x18 = 9; self->cpu.xA4 = 71; }
        struct CpuFighter before; memcpy(&before, &self->cpu, sizeof(before));
        CHECK(!update(self, target)); CHECK(action(self) == 0);
        if (variant) { CHECK(memcmp(&before, &self->cpu, sizeof(before)) == 0); }
        else { neutral(); }
        CHECK(sc_states[self->player_id].cooldown == 0);
    }
}
static void grab_replaced_script_not_clobbered(void)
{
    for (variant = 0; variant < 7; ++variant) {
        setup(); CHECK(frame());
        switch (variant) {
        case 0: self->cpu.x18 = 9; break;
        case 1: self->cpu.buffer[0] = CpuCmd_PressA; break;
        case 2: self->cpu.write_pos = self->cpu.buffer; self->cpu.csP = NULL; break;
        case 3: self->cpu.csP = self->cpu.buffer + 1; break;
        case 4: self->cpu.command_duration = 4; break;
        case 5: self->cpu.xA4 = 71; break;
        case 6: self->cpu.csP = target->cpu.buffer; break;
        }
        struct CpuFighter before; memcpy(&before, &self->cpu, sizeof(before));
        CHECK(!update(self, target)); CHECK(action(self) == 0);
        if (variant == 5) {
            /* Cache-only selection isn't a replacement SCRIPT. Release our
             * old input now, but preserve the fresh native attack selection. */
            CHECK(self->cpu.xA4 == 71); neutral();
            CHECK(self->cpu.csP == NULL && self->cpu.write_pos == self->cpu.buffer);
        } else { CHECK(memcmp(&before, &self->cpu, sizeof(before)) == 0); }
    }
}
static void grab_eligibility_and_priority(void)
{
    for (variant = 0; variant < 23; ++variant) {
        setup();
        switch (variant) {
        case 0: self->kind = FTKIND_FOX; break;
        case 1: self->cpu.level = 8; break;
        case 2: self->cpu.xC = 3; break;
        case 3: world.cpu[0] = false; break;
        case 4: self->x221F_b3 = true; break;
        case 5: self->x2219_b5 = true; break;
        case 6: self->x221A_b3 = true; break;
        case 7: self->x2224_b2 = true; break;
        case 8: self->x221D_b4 = true; break;
        case 9: self->victim_gobj = target->gobj; break;
        case 10: self->x1A5C = target->gobj; break;
        case 11: self->motion_id = ftCo_MS_DeadDown; break;
        case 12: self->motion_id = ftCo_MS_Entry; break;
        case 13: self->x221C_b6 = true; break;
        case 14: self->ground_or_air = GA_Air; break;
        case 15: self->motion_id = ftCo_MS_Dash; break;
        case 16: self->item_gobj = target->gobj; break;
        case 17: target->item_gobj = self->gobj; break;
        case 18: world.protection[0] = 1; break;
        case 19: world.protection[1] = 2; break;
        case 20: target->ground_or_air = GA_Air; break;
        case 21: target->x2219_b5 = true; break;
        case 22: target->motion_id = ftCo_MS_EntryEnd; break;
        }
        expect_no_start();
    }
    for (variant = -1; variant <= 20; ++variant) {
        setup(); self->cpu.x18 = variant;
        bool allowed = variant == 1 || variant == 2 || variant == 3 ||
                       variant == 8 || variant == 10;
        CHECK(update(self, target) == allowed);
    }
}
static void grab_distance_facing_prediction(void)
{
    const float dx[] = { -1, 0, 0.001f, 11, 11.001f };
    for (variant = 0; variant < 10; ++variant) {
        setup(); self->facing_dir = variant < 5 ? 1 : -1;
        target->cur_pos.x = dx[variant % 5] * self->facing_dir;
        CHECK(update(self, target) == (variant % 5 == 2 || variant % 5 == 3));
    }
    for (variant = 0; variant < 12; ++variant) {
        setup(); bool ok = variant % 2 == 0;
        switch (variant / 2) {
        case 0: target->cur_pos.y = ok ? 3 : 3.001f; break;
        case 1: self->self_vel.x = ok ? -0.5f : -0.501f; break;
        case 2: target->cur_pos.x = 4; target->pos_delta.x = ok ? 0.5f : 0.501f; break;
        case 3: target->cur_pos.x = 7; target->pos_delta.x = ok ? 0.5f : 0.50001f; break;
        case 4: self->coll_data.floor.index = ok ? 4 : -1; break;
        case 5: target->coll_data.floor.index = ok ? 4 : 5; break;
        }
        CHECK(update(self, target) == ok);
    }
    setup(); target->cur_pos.x = 1; self->pos_delta.x = 0.125f; expect_no_start();
    setup(); target->cur_pos.x = 7; self->pos_delta.x = -0.501f; expect_no_start();
}
static void grab_guard_damage_and_lag_boundaries(void)
{
    const int guard[] = { ftCo_MS_GuardOn, ftCo_MS_Guard, ftCo_MS_GuardSetOff,
                          ftCo_MS_GuardReflect, ftCo_MS_GuardOff, ftCo_MS_Wait };
    for (variant = 0; variant < 6; ++variant) {
        setup(); target->motion_id = guard[variant];
        CHECK(update(self, target) == (variant < 4)); CHECK(calls.anim == 0);
    }
    for (variant = 0; variant < 4; ++variant) {
        setup(); target->motion_id = ftCo_MS_DamageHi1;
        target->x221C_b6 = variant != 0;
        target->mv.co.damage.x0 = variant == 1 ? 7.99f : 8;
        if (variant == 3) { target->motion_id = ftCo_MS_DamageLw3; }
        CHECK(update(self, target) == (variant >= 2)); CHECK(calls.anim == 0);
    }
    for (variant = 0; variant < 9; ++variant) {
        setup(); target->motion_id = ftCo_MS_LandingAirN;
        world.anim_end[1] = 18; target->cur_anim_frame = 2; target->frame_speed_mul = 2;
        bool ok = variant == 0 || variant == 7;
        switch (variant) {
        case 1: target->cur_anim_frame = 2.01f; break;
        case 2: target->frame_speed_mul = 0; break;
        case 3: target->frame_speed_mul = -1; break;
        case 4: target->x8A4_animBlendFrames = 0.01f; break;
        case 5: target->frame_speed_mul = 4; break; /* Already L-cancelled lag. */
        case 6: target->motion_id = ftCo_MS_Landing; break;
        case 7: target->motion_id = ftCo_MS_LandingFallSpecial; break;
        case 8: target->motion_id = ftCo_MS_LandingFallSpecial;
                target->mv.co.landing.allow_interrupt = true; break;
        }
        CHECK(update(self, target) == ok);
    }
    setup(); target->motion_id = ftCo_MS_LandingAirLw;
    world.anim_end[1] = 10; CHECK(frame());
    target->cur_anim_frame = 3; CHECK(frame()); /* Recheck permits exactly 7. */
    setup(); target->motion_id = ftCo_MS_LandingAirF;
    world.anim_end[1] = 10; CHECK(frame());
    target->cur_anim_frame = 3.001f; CHECK(!frame()); neutral();
}
static void grab_held_defense_and_second_sample(void)
{
    const u32 masks[] = { HSD_PAD_L, HSD_PAD_R, HSD_PAD_Z, HSD_PAD_LR };
    for (variant = 0; variant < 8; ++variant) {
        setup(); if (variant < 4) { self->cpu.buttons = masks[variant]; }
        else { self->input.held_buttons[0] = masks[variant - 4]; }
        expect_no_start();
    }
    setup(); self->cpu.ltrigger = 77; expect_no_start();
    setup(); self->cpu.rtrigger = 77; expect_no_start();
    setup(); self->cpu.ltrigger = 76; CHECK(frame());
    for (variant = 0; variant < 5; ++variant) {
        setup(); CHECK(frame());
        self->input.held_buttons[0] = variant == 4 ? HSD_PAD_A : masks[variant];
        CHECK(!frame()); neutral(); CHECK(action(self) == 0);
    }
}
static Fighter* replacement_target(void)
{
    /* A DIFFERENT identity with the SAME viable opportunity: cancellation
     * must be due to identity, not an accidentally distant/unavailable target. */
    Fighter* fp = &fighters[2];
    memcpy(fp, target, sizeof(*fp));
    fp->gobj = &objects[2]; fp->player_id = 2; ++fp->x8_spawnNum;
    fp->cpu.write_pos = fp->cpu.buffer; fp->cpu.csP = NULL;
    fp->cpu.command_duration = 0;
    return fp;
}
static void identity_reset_and_invalid_slots(void)
{
    setup(); CHECK(!update(NULL, target)); post(NULL); restore(NULL); CHECK(action(NULL) == 0);
    reset(-1); reset(N); reset(1000);
    self->player_id = 255; CHECK(!update(self, target)); post(self); restore(self);
    CHECK(action(self) == 0);
    setup(); CHECK(!update(self, NULL)); CHECK(!update(self, self));
    for (variant = 0; variant < 4; ++variant) {
        setup(); CHECK(frame());
        if (variant == 0) { ++target->x8_spawnNum; }
        if (variant == 2) { ++self->x8_spawnNum; }
        if (variant == 3) { reset(0); }
        if (variant < 2) {
            CHECK(!update(self, variant == 1 ? replacement_target() : target));
            neutral(); CHECK(action(self) == 0);
        } else {
            CHECK(action(self) == 0); CHECK(update(self, target));
            CHECK(action(self) == 5); /* New identity starts with neutral, not Z. */
            vm(self); neutral();
        }
    }
    setup(); CHECK(frame());
    Fighter* replacement = &fighters[2]; replacement->player_id = 0;
    replacement->cur_pos.x = 0;
    CHECK(action(replacement) == 0); CHECK(update(replacement, target));
    CHECK(action(self) == 0 && action(replacement) == 5);
}

static void lc_ecb_eta_and_sweep_filters(void)
{
    const float heights[] = { 1.25f, 2.75f, 4.5f, 4.501f };
    for (variant = 0; variant < 4; ++variant) {
        lc_setup(); self->coll_data.cur_pos.y = heights[variant] + 2;
        if (variant < 3) { expect_lc(); } else { expect_no_lc(); }
        CHECK(calls.floor == (variant < 3 ? variant + 1 : 3));
        CLOSE(calls.sweep[0].ax, 22); CLOSE(calls.sweep[0].ay, heights[variant]);
        for (int i = 0; i < calls.floor; ++i) {
            CLOSE(calls.sweep[i].bx - calls.sweep[i].ax, 0.5f);
            CLOSE(calls.sweep[i].by - calls.sweep[i].ay, -1.25f - 0.25f * i);
            CHECK(calls.sweep[i].skip == -1 && calls.sweep[i].joint_skip == -7);
            CHECK(calls.sweep[i].joint_only == -9);
            if (i) { CLOSE(calls.sweep[i].ax, calls.sweep[i-1].bx);
                     CLOSE(calls.sweep[i].ay, calls.sweep[i-1].by); }
        }
    }
}
static void lc_descending_aerial_cmdvars_and_eligibility(void)
{
    for (variant = 0; variant < 5; ++variant) {
        lc_setup(); self->motion_id = ftCo_MS_AttackAirN + variant; expect_lc();
    }
    for (variant = 0; variant < 20; ++variant) {
        lc_setup();
        switch (variant) {
        case 0: self->self_vel.y = 0; break;
        case 1: self->self_vel.y = 0.01f; break;
        case 2: self->pos_delta.y = 0; break;
        case 3: self->pos_delta.y = 0.01f; break;
        case 4: self->cmd_vars[0] = 0; break;
        case 5: self->ground_or_air = GA_Ground; break;
        case 6: self->motion_id = ftCo_MS_AttackAirN - 1; break;
        case 7: self->motion_id = ftCo_MS_AttackAirLw + 1; break;
        case 8: self->x221F_b3 = true; break;
        case 9: self->x221C_b6 = true; break;
        case 10: self->x2219_b5 = true; break;
        case 11: self->x221A_b3 = true; break;
        case 12: self->x2224_b2 = true; break;
        case 13: self->x221D_b4 = true; break;
        case 14: self->victim_gobj = target->gobj; break;
        case 15: self->kind = FTKIND_FOX; break;
        case 16: self->cpu.level = 8; break;
        case 17: self->cpu.xC = 0; break;
        case 18: world.cpu[0] = false; break;
        case 19: rules.analog_shoulder_deadzone = 128.0f / 255.0f; break;
        }
        expect_no_lc(); CHECK(calls.floor == 0);
    }
}
static void lc_existing_lr_window_and_defense(void)
{
    for (variant = 0; variant < 6; ++variant) {
        lc_setup(); int eta = variant / 2 + 1;
        self->coll_data.cur_pos.y = 2 + (eta == 1 ? 1 : eta == 2 ? 2 : 4);
        self->x67F = (u8) (rules.xE4 - eta - 1 - (variant % 2 == 0));
        if (variant % 2) { expect_lc(); } else { expect_no_lc(); }
    }
    const u32 masks[] = { HSD_PAD_L, HSD_PAD_R, HSD_PAD_Z, HSD_PAD_LR };
    for (variant = 0; variant < 10; ++variant) {
        lc_setup();
        if (variant < 4) { self->cpu.buttons |= masks[variant]; }
        else if (variant < 8) { self->input.held_buttons[0] = masks[variant - 4]; }
        else if (variant == 8) { self->cpu.ltrigger = 77; }
        else { self->cpu.rtrigger = 77; }
        expect_no_lc(); CHECK(calls.floor == 0);
    }
}
static void lc_fastfall_terminal_and_fallthrough(void)
{
    for (variant = 0; variant < 2; ++variant) {
        lc_setup(); self->fall_fast = true; self->self_vel.y = -6;
        self->coll_data.cur_pos.y = variant ? 20.001f : 20;
        if (variant) { expect_no_lc(); } else { expect_lc(); }
        CHECK(calls.floor == 3);
        for (int i = 0; i < 3; ++i) {
            CLOSE(calls.sweep[i].by - calls.sweep[i].ay, -6);
        }
    }
    lc_setup(); self->self_vel.y = -3.9f; self->coll_data.cur_pos.y = 10;
    expect_lc(); CHECK(calls.floor == 2);
    CLOSE(calls.sweep[0].by - calls.sweep[0].ay, -4);
    CLOSE(calls.sweep[1].by - calls.sweep[1].ay, -4);
    for (variant = 0; variant < 6; ++variant) {
        lc_setup();
        switch (variant) {
        case 0: self->coll_data.floor_skip = world.floor_line; break;
        case 1: world.floor_enabled = false; break;
        case 2: world.floor_line = -2; break;
        case 3: world.floor_normal_y = 0; break;
        case 4: world.floor_normal_y = -1; break;
        case 5: world.floor_right = 21; break;
        }
        expect_no_lc(); CHECK(calls.floor > 0);
    }
    lc_setup(); self->coll_data.floor_skip = 10; expect_lc();
}
static void lc_restore_only_borrowed_channel_and_idempotence(void)
{
    for (variant = 0; variant < 5; ++variant) {
        lc_setup(); expect_lc();
        struct CpuFighter before;
        if (variant == 1) { self->cpu.ltrigger = 91; }
        if (variant == 2) { self->cpu.ltrigger = 0; }
        self->cpu.rtrigger = 173; self->cpu.buttons = HSD_PAD_B;
        self->cpu.lstick = (TestStick) { 92, -114 };
        self->cpu.xA4 = 71; self->cpu.x18 = 15;
        memcpy(&before, &self->cpu, sizeof(before));
        if (variant == 3) { CHECK(!update(self, NULL)); }
        else { restore(self); }
        CHECK(self->cpu.ltrigger == (variant == 1 ? 91 : variant == 2 ? 0 : 23));
        before.ltrigger = self->cpu.ltrigger;
        CHECK(memcmp(&before, &self->cpu, sizeof(before)) == 0);
        /* It must relinquish ownership, not keep restoring on later calls. */
        self->cpu.ltrigger = 128; restore(self); restore(self);
        CHECK(self->cpu.ltrigger == 128);
    }
}
static void lc_restore_before_eligibility_changes(void)
{
    for (variant = 0; variant < 10; ++variant) {
        lc_setup(); expect_lc();
        switch (variant) {
        case 0: self->kind = FTKIND_FOX; break;
        case 1: self->cpu.level = 1; break;
        case 2: self->cpu.xC = 0; break;
        case 3: world.cpu[0] = false; break;
        case 4: self->x221F_b3 = true; break;
        case 5: self->x221C_b6 = true; break;
        case 6: self->ground_or_air = GA_Ground; break;
        case 7: self->victim_gobj = target->gobj; break;
        case 8: self->cpu.x18 = 9; break;
        case 9: self->motion_id = ftCo_MS_Entry; break;
        }
        if (variant % 2) { CHECK(!update(self, NULL)); }
        else { restore(self); }
        CHECK(self->cpu.ltrigger == 23); restore(self); CHECK(self->cpu.ltrigger == 23);
    }
    /* Restore is independently callable before personality/serious gating. */
    lc_setup(); expect_lc(); restore(self); expect_no_lc();
}
static void lc_retry_budget_and_identity(void)
{
    lc_setup(); expect_lc(); post(self); CHECK(self->cpu.ltrigger == 128);
    restore(self); CHECK(self->cpu.ltrigger == 23); expect_no_lc();
    for (int i = 0; i < 5; ++i) { CHECK(!update(self, NULL)); expect_no_lc(); }
    CHECK(!update(self, NULL)); expect_lc(); restore(self);
    lc_setup(); expect_lc(); ++self->x8_spawnNum;
    self->cpu.ltrigger = 41; restore(self); CHECK(self->cpu.ltrigger == 41);
    CHECK(!update(self, NULL)); restore(self); CHECK(self->cpu.ltrigger == 41);
    lc_setup(); expect_lc();
    fighters[2].player_id = 0; fighters[2].cpu.ltrigger = 128;
    restore(&fighters[2]); CHECK(fighters[2].cpu.ltrigger == 128);
    CHECK(!update(&fighters[2], NULL)); restore(self); CHECK(self->cpu.ltrigger == 128);
}

/* Air scenarios are synthetic observations in a flat-floor world. Neither
 * frame() nor the VM integrates physics or sets motion_id from script age. */
static void air_setup(int requested)
{
    setup();
    for (int i = 0; i < 2; ++i) {
        Fighter* fp = &fighters[i];
        fp->ground_or_air = GA_Air;
        fp->cur_pos = (Vec3) { 0, 60, 0 };
        fp->co_attrs.gravity = 0.125f;
        fp->co_attrs.aerial_friction = 0.01f;
        fp->co_attrs.air_drift_stick_mul = 0.015f;
        fp->co_attrs.aerial_drift_base = 0.005f;
        fp->coll_data.ecb.bottom.y = -2;
    }
    self->motion_id = ftCo_MS_Fall;
    target->motion_id = ftCo_MS_DamageFlyN; target->x221C_b6 = true;
    target->mv.co.damage.x0 = 40;
    target->cur_pos.x = requested == 6 ? 12 : 0;
    target->cur_pos.y += requested == 6 ? 4 : 12;
    self->coll_data.cur_pos = self->cur_pos;
    target->coll_data.cur_pos = target->cur_pos;
    world.floor_left = -100; world.floor_right = 100;
}
static void observed_position(Fighter* fp, float x, float y)
{
    fp->cur_pos.x = x; fp->cur_pos.y = y;
    fp->coll_data.cur_pos = fp->cur_pos;
}
static void air_pulse(int id)
{
    CHECK(frame()); CHECK(action(self) == id);
    CHECK(self->cpu.buttons == HSD_PAD_A);
    CHECK(self->cpu.lstick.x == (id == 6 ? (int) (self->facing_dir * 80) : 0));
    CHECK(self->cpu.lstick.y == (id == 7 ? 80 : 0));
    CHECK(self->cpu.cstick.x == 0 && self->cpu.cstick.y == 0);
    CHECK(self->cpu.ltrigger == 0 && self->cpu.rtrigger == 0);
    CHECK(self->cpu.write_pos - self->cpu.buffer == 13);
}
static void air_neutral_direct_pulse_and_ack(void)
{
    for (variant = 0; variant < 4; ++variant) {
        int id = variant % 2 + 6; air_setup(id);
        if (variant >= 2) {
            self->facing_dir = -1; target->cur_pos.x *= -1;
            target->coll_data.cur_pos = target->cur_pos;
            world.stage = St_Kind_Battle;
        }
        self->cur_anim_frame = 119.75f; /* NOT an animation-age trigger. */
        CHECK(frame()); CHECK(action(self) == id); neutral();
        CHECK(self->motion_id == ftCo_MS_Fall);
        self->cur_anim_frame = 0.25f; air_pulse(id);
        CHECK(self->motion_id == ftCo_MS_Fall);
        /* Only the game/test observation supplies acknowledgement. */
        self->motion_id = id == 6 ? ftCo_MS_AttackAirF : ftCo_MS_AttackAirHi;
        self->input.held_buttons[0] = HSD_PAD_A;
        CHECK(!update(self, target)); CHECK(action(self) == 0); neutral();
        CHECK(self->cpu.csP == NULL);
        CHECK(sc_states[self->player_id].cooldown == 0);
        /* A later real free-air observation can convert immediately; do not
         * burn 45 updates of artificial 'reaction time' after acceptance. */
        self->motion_id = ftCo_MS_Fall;
        self->input.held_buttons[0] = 0;
        CHECK(frame()); CHECK(action(self) == id);
    }
}
static void air_release_tail_failed_press_and_cooldown(void)
{
    for (variant = 0; variant < 4; ++variant) {
        int id = variant % 2 + 6; air_setup(id);
        CHECK(frame()); air_pulse(id);
        if (variant >= 2) { vm(self); neutral(); }
        /* No engine acknowledgement: never retry A, drift, jump, or force motion. */
        CHECK(!update(self, target)); CHECK(action(self) == 0); neutral();
        CHECK(self->motion_id == ftCo_MS_Fall);
        for (int i = 0; i < 44; ++i) { CHECK(!frame()); }
        CHECK(frame()); CHECK(action(self) == id); neutral();
    }
}
static void offense_requires_real_neutral_sample(void)
{
    for (variant = 0; variant < 3; ++variant) {
        if (variant == 0) { setup(); } else { air_setup(variant + 5); }
        CHECK(update(self, target)); /* Not interpreted: no controller sample. */
        CHECK(!update(self, target)); CHECK(action(self) == 0); neutral();
    }
    for (variant = 0; variant < 12; ++variant) {
        air_setup(variant % 2 + 6); CHECK(frame());
        switch (variant / 2) {
        case 0: self->input.lstick[0].x = 0.001f; break;
        case 1: self->input.lstick[0].y = -0.001f; break;
        case 2: self->input.cstick[0].x = 0.001f; break;
        case 3: self->input.cstick[0].y = -0.001f; break;
        case 4: self->input.held_buttons[0] = HSD_PAD_B; break;
        case 5: self->cpu.rtrigger = 77; break;
        }
        CHECK(!update(self, target)); CHECK(action(self) == 0); neutral();
    }
}
static void air_predicts_intercept_not_current_distance(void)
{
    air_setup(6);
    observed_position(target, 24, 64); /* Outside Knee box NOW, entering at hit. */
    target->self_vel.x = target->pos_delta.x = -0.6f;
    CHECK(frame()); CHECK(action(self) == 6); air_pulse(6);
    air_setup(7);
    observed_position(target, 0, 57); /* Below us now, rising into up-air. */
    target->self_vel.y = target->pos_delta.y = 2;
    CHECK(frame()); CHECK(action(self) == 7); air_pulse(7);
    air_setup(6); target->self_vel.x = target->pos_delta.x = 1;
    expect_no_start(); /* In range now, moving out before startup. */
    air_setup(7); target->self_vel.y = target->pos_delta.y = 3;
    expect_no_start();
    air_setup(6); CHECK(frame());
    observed_position(target, 35, 64);
    CHECK(!frame()); CHECK(action(self) == 0); neutral();
}
static void air_recheck_downgrade_not_upgrade(void)
{
    air_setup(6); CHECK(frame()); CHECK(action(self) == 6);
    observed_position(target, 0, 72); target->mv.co.damage.x0 = 10;
    air_pulse(7); /* The faster, now-vertical intercept is still legal. */
    self->motion_id = ftCo_MS_AttackAirHi;
    CHECK(!update(self, target)); neutral(); CHECK(action(self) == 0);
    air_setup(7); CHECK(frame()); CHECK(action(self) == 7);
    observed_position(target, 12, 64);
    CHECK(!frame()); CHECK(action(self) == 0); neutral();
}
static void air_hitstun_startup_and_reserve_boundaries(void)
{
    for (variant = 0; variant < 4; ++variant) {
        int id = variant / 2 + 6; air_setup(id);
        target->mv.co.damage.x0 = (id == 6 ? 17 : 9) - (variant % 2 ? 0.001f : 0);
        CHECK(update(self, target) == (variant % 2 == 0));
    }
    for (variant = 0; variant < 4; ++variant) {
        int id = variant / 2 + 6; air_setup(id); CHECK(frame());
        target->mv.co.damage.x0 = (id == 6 ? 16 : 8) - (variant % 2 ? 0.001f : 0);
        if (variant % 2) { CHECK(!frame()); neutral(); CHECK(action(self) == 0); }
        else { air_pulse(id); }
    }
    const int states[] = { ftCo_MS_DamageHi1, ftCo_MS_DamageFlyRoll,
        ftCo_MS_DamageHi1 - 1, ftCo_MS_DamageFlyRoll + 1, ftCo_MS_DamageFall,
        ftCo_MS_Fall, ftCo_MS_AttackAirF, ftCo_MS_Guard };
    for (variant = 0; variant < 8; ++variant) {
        air_setup(6); target->motion_id = states[variant];
        CHECK(update(self, target) == (variant < 2));
    }
    air_setup(6); target->x221C_b6 = false; expect_no_start();
    air_setup(7); target->mv.co.damage.x0 = NAN; expect_no_start();
}
static void air_free_motion_protection_and_conflicts(void)
{
    for (variant = ftCo_MS_JumpF; variant <= ftCo_MS_FallAerialB; ++variant) {
        air_setup(6); self->motion_id = variant; self->mv.co.jump.x4 = true;
        CHECK(frame()); CHECK(action(self) == 6);
    }
    const int motions[] = { ftCo_MS_KneeBend, ftCo_MS_DamageFall, ftCo_MS_FallSpecial,
        ftCo_MS_AttackAirN, ftCo_MS_Landing, ftCo_MS_EscapeAir, ftCo_MS_JumpF,
        ftCo_MS_JumpB };
    for (variant = 0; variant < 8; ++variant) {
        air_setup(6); self->motion_id = motions[variant]; expect_no_start();
    }
    for (variant = 0; variant < 22; ++variant) {
        air_setup(variant % 2 + 6);
        switch (variant) {
        case 0: world.protection[0] = 1; break;
        case 1: world.protection[1] = 2; break;
        case 2: self->x221F_b3 = true; break;
        case 3: target->x221F_b3 = true; break;
        case 4: target->x2219_b5 = true; break;
        case 5: target->x221A_b3 = true; break;
        case 6: target->x2224_b2 = true; break;
        case 7: target->x221D_b4 = true; break;
        case 8: target->victim_gobj = self->gobj; break;
        case 9: target->x1A5C = self->gobj; break;
        case 10: self->x221C_b6 = true; break;
        case 11: self->item_gobj = target->gobj; break;
        case 12: target->item_gobj = self->gobj; break;
        case 13: self->cpu.xFA_b5 = false; break;
        case 14: self->facing_dir = 0; break;
        case 15: self->facing_dir = NAN; break;
        case 16: self->ground_or_air = GA_Ground; break;
        case 17: target->ground_or_air = GA_Ground; break;
        case 18: world.stage = St_Kind_Izumi; break;
        case 19: self->cpu.x18 = 4; break;
        case 20: self->cpu.xA4 = 71; break;
        case 21: world.protection[1] = -1; break;
        }
        expect_no_start();
    }
    const u32 masks[] = { HSD_PAD_A, HSD_PAD_B, HSD_PAD_X, HSD_PAD_Y,
                         HSD_PAD_L, HSD_PAD_R, HSD_PAD_Z, HSD_PAD_LR };
    for (variant = 0; variant < 16; ++variant) {
        air_setup(variant % 2 + 6);
        if (variant < 8) { self->cpu.buttons = masks[variant]; }
        else { self->input.held_buttons[0] = masks[variant - 8]; }
        expect_no_start();
    }
}
static void air_before_landing_and_runway_vetoes(void)
{
    for (variant = 0; variant < 10; ++variant) {
        air_setup(6);
        switch (variant) {
        case 0: observed_position(self, 0, 12); observed_position(target, 12, 16); break;
        case 1: world.floor_enabled = false; break;
        case 2: world.floor_line = -2; break;
        case 3: world.floor_normal_y = 0.99f; break;
        case 4: world.floor_left = -12; break; /* Strict runway margin. */
        case 5: world.floor_right = 24; break;
        case 6: observed_position(self, 0, 91); observed_position(target, 12, 95); break;
        case 7: self->coll_data.ecb.bottom.y = -13; break;
        case 8: self->fall_fast = true; break; /* Existing fastfall lands too soon. */
        case 9: self->co_attrs.gravity = 0.5f; break;
        }
        expect_no_start();
    }
    air_setup(7); CHECK(frame());
    observed_position(self, 0, 5); observed_position(target, 0, 17);
    CHECK(!frame()); CHECK(action(self) == 0); neutral();
    air_setup(7); CHECK(frame());
    world.protection[1] = 1; CHECK(!frame()); CHECK(action(self) == 0); neutral();
    /* Landing on either prediction invalidates, not only our attack's ECB. */
    air_setup(6); target->self_vel.y = target->pos_delta.y = -4; expect_no_start();
    air_setup(7); self->coll_data.floor.index = -1;
    CHECK(frame()); /* Stale airborne floor index is not the floor query. */
}
static void air_prediction_sanity_and_native_drift(void)
{
    for (variant = 0; variant < 24; ++variant) {
        air_setup(variant % 2 + 6);
        Fighter* fp = variant % 2 ? target : self;
        switch (variant / 2) {
        case 0: fp->x2228_b2 = true; break;
        case 1: fp->x2222_b6 = true; break;
        case 2: fp->dmg.x1948 = 1; break;
        case 3: fp->x1064_thrownHitbox.owner = target->gobj; break;
        case 4: fp->x98_atk_shield_kb.x = 0.01f; break;
        case 5: fp->x74_anim_vel.y = 0.01f; break;
        case 6: fp->cur_pos.x = NAN; break;
        case 7: fp->pos_delta.x = 2.01f; break;
        case 8: fp->co_attrs.gravity = 0; break;
        case 9: fp->co_attrs.air_drift_max = 0; break;
        case 10: fp->co_attrs.terminal_velocity = INFINITY; break;
        case 11: fp->x8c_kb_vel.y = 12.01f; break;
        }
        expect_no_start();
    }
    air_setup(6); rules.x204_knockbackFrameDecay = -0.1f; expect_no_start();
    air_setup(6); self->co_attrs.air_drift_stick_mul = 0.5f;
    self->co_attrs.aerial_drift_base = 0.1f; self->co_attrs.air_drift_max = 3;
    self->co_attrs.air_max_horizontal_velocity = 3;
    expect_no_start(); /* Native opposite drift can spoil the hit: no forced chase. */
    air_setup(6); target->x8c_kb_vel.x = target->pos_delta.x = 0.1f;
    CHECK(frame()); /* Small decaying KB remains a usable intercept. */
    air_setup(7); target->fall_fast = true;
    CHECK(frame()); /* Damage physics use ordinary gravity, NOT fastfall speed. */
}
static void air_intercept_box_and_final_reserve_frame(void)
{
    /* Zero horizontal acceleration isolates inclusive root-box boundaries;
     * normal air_setup cases above separately exercise uncertain native drift. */
    const struct { int id; float x, y; bool ok; } points[] = {
        { 6, 5, 4, true }, { 6, 4.999f, 4, false },
        { 6, 20, 4, true }, { 6, 20.001f, 4, false },
        { 6, 12, 0, true }, { 6, 12, -0.001f, false },
        { 6, 12, 9, true }, { 6, 12, 9.001f, false },
        { 7, -8, 12, true }, { 7, -8.001f, 12, false },
        { 7, 8, 12, true }, { 7, 8.001f, 12, false },
        { 7, 0, 7, true }, { 7, 0, 6.999f, false },
        { 7, 0, 22, true }, { 7, 0, 22.001f, false },
    };
    for (variant = 0; variant < 32; ++variant) {
        int n = variant % 16; air_setup(points[n].id);
        self->co_attrs.air_drift_stick_mul = self->co_attrs.aerial_drift_base = 0;
        self->facing_dir = variant < 16 ? 1 : -1;
        observed_position(target, points[n].x * self->facing_dir, 60 + points[n].y);
        CHECK(frame() == points[n].ok);
        CHECK(action(self) == (points[n].ok ? points[n].id : 0));
    }
    for (variant = 0; variant < 4; ++variant) {
        int id = variant / 2 + 6; air_setup(id);
        float y = (id == 6 ? 21 : 8.5f) + (variant % 2 ? 0.001f : 0);
        observed_position(self, 0, y);
        observed_position(target, id == 6 ? 12 : 0, y + (id == 6 ? 4 : 12));
        CHECK(frame() == (variant % 2 != 0));
        /* Root is safe at startup, but exactly four units on the later reserve
         * frame must still veto. This is not a fixed-age landing transition. */
    }
}
static void lc_tech_counters_di_and_native_priority_untouched(void)
{
    for (variant = 0; variant < 4; ++variant) {
        lc_setup();
        self->x680 = variant == 0 ? 0 : variant == 1 ? 255 : 1;
        self->x685 = variant == 2 ? 0 : 255;
        self->cpu.x18 = variant == 0 ? 9 : variant == 1 ? 15 : variant == 2 ? 18 : 4;
        self->cpu.xA4 = 71;
        /* LC is independent of offense priority and does not overwrite DI,
         * tech cooldowns, native script bytes/cursors or cached native attack. */
        expect_lc(); restore(self); CHECK(self->cpu.ltrigger == 23);
    }
    for (variant = 0; variant < 2; ++variant) {
        lc_setup(); self->fall_fast = true;
        self->self_vel.y = variant ? 1 : 0;
        expect_no_lc(); CHECK(calls.floor == 0);
    }
}
static void air_replaced_script_and_identity_yield(void)
{
    for (variant = 0; variant < 16; ++variant) {
        int id = variant % 2 + 6; air_setup(id); CHECK(frame()); air_pulse(id);
        switch (variant / 2) {
        case 0: self->cpu.x18 = 9; break;
        case 1: self->cpu.xA4 = 71; break;
        case 2: self->cpu.buffer[0] = (s8) CpuCmd_SetLstickY; break;
        case 3: self->cpu.write_pos = self->cpu.buffer; self->cpu.csP = NULL; break;
        case 4: self->cpu.csP = self->cpu.buffer + 3; break;
        case 5: self->cpu.command_duration = 2; break;
        case 6: self->cpu.csP = target->cpu.buffer; break;
        case 7: self->cpu.write_pos = self->cpu.buffer + 12; break;
        }
        self->motion_id = id == 6 ? ftCo_MS_AttackAirF : ftCo_MS_AttackAirHi;
        struct CpuFighter before; memcpy(&before, &self->cpu, sizeof(before));
        CHECK(!update(self, target)); CHECK(action(self) == 0);
        if (variant / 2 == 1) {
            CHECK(self->cpu.xA4 == 71); neutral();
            CHECK(self->cpu.csP == NULL && self->cpu.write_pos == self->cpu.buffer);
        } else { CHECK(memcmp(&before, &self->cpu, sizeof(before)) == 0); }
    }
    for (variant = 0; variant < 6; ++variant) {
        air_setup(variant % 2 + 6); CHECK(frame());
        if (variant < 2) { ++target->x8_spawnNum; }
        else if (variant < 4) { target->x221F_b3 = true; }
        CHECK(!update(self, variant >= 4 ? replacement_target() : target));
        CHECK(action(self) == 0); neutral();
    }
    air_setup(6); CHECK(frame()); ++self->x8_spawnNum;
    CHECK(action(self) == 0); CHECK(frame()); neutral(); CHECK(action(self) == 6);
}

#define CASE(name) { #name, name }
static const struct { const char* name; void (*run)(void); } cases[] = {
    CASE(grab_neutral_pulse_ack_release),
    CASE(grab_release_tail_without_update),
    CASE(grab_failed_press_cooldown),
    CASE(grab_native_capture_priority),
    CASE(grab_replaced_script_not_clobbered),
    CASE(grab_eligibility_and_priority),
    CASE(grab_distance_facing_prediction),
    CASE(grab_guard_damage_and_lag_boundaries),
    CASE(grab_held_defense_and_second_sample),
    CASE(identity_reset_and_invalid_slots),
    CASE(lc_ecb_eta_and_sweep_filters),
    CASE(lc_descending_aerial_cmdvars_and_eligibility),
    CASE(lc_existing_lr_window_and_defense),
    CASE(lc_fastfall_terminal_and_fallthrough),
    CASE(lc_restore_only_borrowed_channel_and_idempotence),
    CASE(lc_restore_before_eligibility_changes),
    CASE(lc_retry_budget_and_identity),
    CASE(air_neutral_direct_pulse_and_ack),
    CASE(air_release_tail_failed_press_and_cooldown),
    CASE(offense_requires_real_neutral_sample),
    CASE(air_predicts_intercept_not_current_distance),
    CASE(air_recheck_downgrade_not_upgrade),
    CASE(air_hitstun_startup_and_reserve_boundaries),
    CASE(air_free_motion_protection_and_conflicts),
    CASE(air_before_landing_and_runway_vetoes),
    CASE(air_prediction_sanity_and_native_drift),
    CASE(air_replaced_script_and_identity_yield),
    CASE(air_intercept_box_and_final_reserve_frame),
    CASE(lc_tech_counters_di_and_native_priority_untouched),
};
int main(int argc, char** argv)
{
    CHECK(argc == 2); case_name = argv[1];
    for (size_t i = 0; i < sizeof(cases) / sizeof(cases[0]); ++i) {
        if (strcmp(case_name, cases[i].name) == 0) {
            cases[i].run(); printf("PASS %s\n", case_name); return 0;
        }
    }
    CHECK(!"unknown case name"); return 1;
}
