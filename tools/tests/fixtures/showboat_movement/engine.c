/* Explicit engine answers and a controller-only VM. No motion transitions,
 * clock-to-animation mapping, friction, dodge velocity or AI decisions here. */
#define N 6
static Fighter fighters[N];
static Fighter_GObj objects[N];
static Fighter* const self = &fighters[0];
static Fighter* const target = &fighters[1];
static struct {
    bool cpu[N], floor_enabled, hole_enabled, split_enabled;
    int protection[N], floor_line;
    StKind stage;
    float anim_end[N], floor_y, floor_normal_y, floor_left, floor_right;
    float right_y, hole_left, hole_right, split_x, main_extent;
    bool split_connected;
    u32 floor_flags;
    Fighter_GObj* primary[N];
    HSD_GObjList entities;
    float v0_y, v1_y;
} world;
HSD_GObjList* HSD_GObj_Entities = &world.entities;
HSD_GObj* Player_GetEntity(s32 slot)
{ CHECK(slot >= 0 && slot < N); return world.primary[slot]; }
static struct TestCommonData rules;
struct TestCommonData* p_ftCommonData = &rules;
static struct {
    int clears, scripts, writes, floor, endpoints, anim, triggers, logs;
    int x_ops, l_ops;
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
void OSReport(const char* format, ...) { CHECK(format != NULL); ++calls.logs; }
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
    /* Geometric flat-floor segment query, not a mocked safe-to-wavedash answer.
     * Gaps/line discontinuities are external world observations. */
    int n = calls.floor++;
    CHECK(n < 8192); CHECK(offset == 0); CHECK(!callback && !gobj);
    CHECK(isfinite(ax) && isfinite(ay) && isfinite(bx) && isfinite(by));
    local_output(contact, sizeof(*contact)); local_output(line, sizeof(*line));
    local_output(flags, sizeof(*flags)); local_output(normal, sizeof(*normal));
    calls.sweep[n].ax = ax; calls.sweep[n].ay = ay;
    calls.sweep[n].bx = bx; calls.sweep[n].by = by;
    calls.sweep[n].skip = skip; calls.sweep[n].joint_skip = joint_skip;
    calls.sweep[n].joint_only = joint_only;
    if (!world.floor_enabled || by >= ay || ay < world.floor_y || by > world.floor_y) {
        return false;
    }
    float x = ax + (bx - ax) * (world.floor_y - ay) / (by - ay);
    if (x < world.floor_left || x > world.floor_right ||
        (world.hole_enabled && x >= world.hole_left && x <= world.hole_right)) {
        return false;
    }
    int id = world.floor_line + (world.split_enabled && x >= world.split_x);
    if (skip == id) { return false; }
    *contact = (Vec3) { x, world.floor_y, 0 };
    *line = id; *flags = world.floor_flags;
    *normal = (Vec3) { 0, world.floor_normal_y, 0 };
    return true;
}
StKind Stage_80225194(void) { return world.stage; }
void mpFloorGetLeft(int line, Vec3* out)
{
    CHECK(line == world.floor_line || (world.split_enabled && line == world.floor_line + 1));
    ++calls.endpoints; local_output(out, sizeof(*out));
    *out = (Vec3) { world.floor_left, world.floor_y, 0 };
}
void mpFloorGetRight(int line, Vec3* out)
{
    CHECK(line == world.floor_line || (world.split_enabled && line == world.floor_line + 1));
    ++calls.endpoints; local_output(out, sizeof(*out));
    *out = (Vec3) { world.floor_right, world.right_y, 0 };
    if (line != world.floor_line && !world.split_connected) { out->x += 10; }
}

void mpLineGetV0Pos(int line, Vec3* out)
{
    mpFloorGetLeft(line, out); out->y = world.v0_y;
    if (world.main_extent > 0) {
        out->x = line == world.floor_line ? -world.main_extent : world.main_extent;
    }
}
void mpLineGetV1Pos(int line, Vec3* out)
{
    mpFloorGetRight(line, out); out->y = world.v1_y;
    if (world.main_extent > 0 && line == world.floor_line) { out->x = world.main_extent; }
}

/* Audited subset of ftcmdscript.c. No opcode range fallback; extend explicitly
 * only after reading its native semantics. PressL is DIGITAL ONLY (unlike R).
 * Done retains outputs, so pulses must contain and execute release tails. */
static bool unary(u8 op)
{
    return op == CpuCmd_PressX || op == CpuCmd_ReleaseX || op == CpuCmd_ReleaseY ||
           op == CpuCmd_PressL || op == CpuCmd_ReleaseL ||
           op == CpuCmd_ReleaseAll || op == CpuCmd_Done;
}
static bool binary(u8 op)
{
    return op == CpuCmd_WaitFor || op == CpuCmd_SetLstickX ||
           op == CpuCmd_SetLstickY || op == CpuCmd_SetCstickX ||
           op == CpuCmd_SetCstickY || op == CpuCmd_SetLtrigger ||
           op == CpuCmd_SetRtrigger;
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
    for (int budget = 0; budget < 128; ++budget) {
        CHECK(c->csP >= c->buffer && c->csP < c->write_pos);
        u8 op = (u8) *c->csP++;
        s8 arg = 0;
        if (binary(op)) { CHECK(c->csP < c->write_pos); arg = *c->csP++; }
        switch (op) {
        case CpuCmd_PressX: c->buttons |= HSD_PAD_X; ++calls.x_ops; break;
        case CpuCmd_ReleaseX: c->buttons &= ~HSD_PAD_X; break;
        case CpuCmd_ReleaseY: c->buttons &= ~HSD_PAD_Y; break;
        case CpuCmd_PressL: c->buttons |= HSD_PAD_L; ++calls.l_ops; break;
        case CpuCmd_ReleaseL: c->buttons &= ~HSD_PAD_L; break;
        case CpuCmd_ReleaseAll: c->buttons = 0; break;
        case CpuCmd_SetLstickX: c->lstick.x = arg; break;
        case CpuCmd_SetLstickY: c->lstick.y = arg; break;
        case CpuCmd_SetCstickX: c->cstick.x = arg; break;
        case CpuCmd_SetCstickY: c->cstick.y = arg; break;
        case CpuCmd_SetLtrigger: c->ltrigger = (u8) arg; break;
        case CpuCmd_SetRtrigger: c->rtrigger = (u8) arg; break;
        case CpuCmd_WaitFor:
            CHECK((u8) arg > 0); c->command_duration = (u8) arg; return;
        case CpuCmd_Done:
            CHECK(c->csP == c->write_pos);
            c->csP = NULL; c->command_duration = 0; return;
        default: CHECK(!"unknown input opcode: implement explicitly");
        }
    }
    CHECK(!"input VM exceeded bounded command budget");
}

/* Snapshot EVERY fighter, GObj, query answer, common-data/rule byte around ALL
 * public API calls and VM ticks. Only the actor CPU script/outputs/cached A4
 * may change. Physics, motion, input history/tech counters, native priority,
 * target, and other slots cannot. Query outputs must use local temporaries. */
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
enum Operation { UPDATE, SUSPEND, ACTION, RESET, INTERPRET };
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
    case UPDATE: result = ShowboatMovement_Update(fp, other); break;
    case SUSPEND: ShowboatMovement_Suspend(fp); break;
    case ACTION: result = ShowboatMovement_GetAction(fp); break;
    case RESET: ShowboatMovement_ResetSlot(slot); break;
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
    CHECK(HSD_GObj_Entities == &world.entities);
    if (op == UPDATE && result) {
        CHECK(calls.scripts == scripts + 1);
        CHECK(fp->cpu.xA4 == 0 && fp->cpu.csP == fp->cpu.buffer);
        CHECK(fp->cpu.command_duration == 1);
        CHECK(fp->cpu.write_pos > fp->cpu.buffer);
        CHECK(fp->cpu.write_pos <= fp->cpu.buffer + sizeof(fp->cpu.buffer));
        CHECK(fp->cpu.write_pos[-1] == CpuCmd_Done);
    } else { CHECK(calls.scripts == scripts); }
    if (op == ACTION) { CHECK(result == 0 || result == 9); }
    return result;
}
static bool update(Fighter* fp, Fighter* other) { return invoke(UPDATE, fp, other, 0); }
static void suspend(Fighter* fp) { invoke(SUSPEND, fp, NULL, 0); }
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
static void observe(Fighter* fp, int motion, int air, float anim)
{
    /* Explicit externally supplied state. NEVER called by the VM. */
    fp->motion_id = motion; fp->ground_or_air = air; fp->cur_anim_frame = anim;
}
static void setup(void)
{
    memset(fighters, 0, sizeof(fighters)); memset(objects, 0, sizeof(objects));
    memset(&world, 0, sizeof(world)); memset(&rules, 0, sizeof(rules));
    for (int i = 0; i < N; ++i) {
        Fighter* fp = &fighters[i];
        reset(i); objects[i].user_data = fp; fp->gobj = &objects[i];
        world.primary[i] = &objects[i];
        fp->kind = FTKIND_CAPTAIN; fp->player_id = (u8) i; fp->x8_spawnNum = 100 + i;
        observe(fp, ftCo_MS_Wait, GA_Ground, 2);
        fp->facing_dir = 1; fp->cur_pos = (Vec3) { i * 20, 0, 0 };
        fp->coll_data.cur_pos = fp->cur_pos;
        fp->frame_speed_mul = 1; fp->x2EC = 29;
        fp->cpu.level = 9; fp->cpu.xC = 4; fp->cpu.x18 = 1;
        fp->cpu.xFA_b5 = true; fp->cpu.write_pos = fp->cpu.buffer;
        fp->coll_data.floor.index = 4; fp->coll_data.floor.normal.y = 1;
        fp->coll_data.floor_skip = -1;
        fp->coll_data.joint_id_skip = -1; fp->coll_data.joint_id_only = -1;
        fp->co_attrs.gravity = 0.25f; fp->co_attrs.terminal_velocity = 4;
        fp->co_attrs.fast_fall_velocity = 6; fp->co_attrs.jump_startup_time = 4;
        fp->co_attrs.ground_friction = 0.08f; fp->co_attrs.walk_max_vel = 0.85f;
        fp->co_attrs.normal_landing_lag = 4; fp->co_attrs.hop_v_initial_velocity = 2;
        fp->co_attrs.dash_max_velocity = 2.3f; fp->co_attrs.jump_v_initial_velocity = 3;
        fp->x670_timer_lstick_tilt_x = 111; fp->x671_timer_lstick_tilt_y = 87;
        fp->x67F = 255; fp->x680 = 17; fp->x681 = 21; fp->x682 = 83;
        fp->x683 = 5; fp->x684 = 199; fp->x685 = 231;
        fp->input.lstick[1] = (Vec2) { 0.31f, -0.72f };
        fp->input.cstick[1] = (Vec2) { -0.41f, 0.22f };
        fp->input.prev_held_buttons = HSD_PAD_B; fp->input.ltrigger = 0.11f;
        fp->dmg.x1830_percent = 73.5f;
        world.cpu[i] = true; world.anim_end[i] = 30;
    }
    target->cur_pos.x = target->coll_data.cur_pos.x = 80;
    world.floor_enabled = true; world.floor_line = 4; world.floor_normal_y = 1;
    world.floor_left = -120; world.floor_right = 120;
    world.stage = St_Kind_Last;
    rules.analog_shoulder_deadzone = 0.3f; rules.xE4 = 7;
    rules.escapeair_force = 3.1f; rules.escapeair_decay = 0.9f;
    rules.escapeair_deadzone = (Vec2) { 0.2f, 0.2f };
    rules.x334 = 3; rules.x340 = 1; rules.x344 = 10;
    rules.friction_when_above_walk_speed = 2;
    rules.horizontal_stick_deadzone = rules.vertical_stick_deadzone = 0.2f;
    memset(&calls, 0, sizeof(calls));
}
static void expect_no_start(void)
{
    struct CpuFighter before;
    memcpy(&before, &self->cpu, sizeof(before));
    CHECK(!update(self, target)); CHECK(action(self) == 0);
    CHECK(memcmp(&before, &self->cpu, sizeof(before)) == 0);
}
