/* Offline production-TU tests. ALL native Fighter/CpuFighter fields and
 * padding are snapshotted, not just a reduced host surface. Real headers;
 * Read-only native eligibility, extension, adjacency and horizontal intersection
 * helpers extracted by the runner. Player/map queries are stubs; native_scan
 * models the horizontal mpCheckFloor loop with STRICT first-hit ties, not just
 * selection by actual segment X. No full map/physics/live-prevention claim. */
#include "game.h"

static CollLine groundCollLine[6];
static CollVtx groundCollVtx[12];
static MapLine map_lines[6];
static MapCollData map_data;
static MapJoint map_joint, foreign_joint;
static CollJoint coll_joint;
static struct {
    bool allowed, missing_map, missing_joint, missing_lines;
    int map_calls, joint_calls, line_calls;
} certificate;
static CollLine* mpLineGetCollLine(int line);
#include "native_functions.h"

#define CHECK(x) do { if (!(x)) { \
    printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #x); exit(1); \
} } while (0)

static Fighter self, rival, other;
static HSD_GObj objects[3];
static HSD_GObj* primary[6];
static int states[6];
static Gm_PKind kinds[6];
static HSD_GObjList entities;
HSD_GObjList* HSD_GObj_Entities = &entities;
static StKind stage;
static struct FloorGeometry {
    Vec3 left, right, v0, v1;
    bool native_override;
    Vec3 native_v0, native_v1;
} segments[6];
static struct {
    bool hit, native_scan;
    int line, calls, endpoints, hits, ties, native_calls[6];
    u32 flags;
    Vec3 contact, normal, left, right, v0, v1;
} floor_stub;
static unsigned checks;
static int player_queries, stage_queries;

static struct FloorGeometry geometry(int line)
{
    struct FloorGeometry result;
    CHECK(line >= 0 && line < 6);
    result = segments[line];
    if (!floor_stub.native_scan && line == floor_stub.line) {
        result.left = floor_stub.left; result.right = floor_stub.right;
        result.v0 = floor_stub.v0; result.v1 = floor_stub.v1;
    }
    return result;
}

static CollLine* mpLineGetCollLine(int line)
{
    struct FloorGeometry g = geometry(line);
    Vec3 v0 = g.native_override ? g.native_v0 : g.v0;
    Vec3 v1 = g.native_override ? g.native_v1 : g.v1;
    ++floor_stub.native_calls[line];
    groundCollVtx[2 * line].pos = (Vec2) { v0.x, v0.y };
    groundCollVtx[2 * line + 1].pos = (Vec2) { v1.x, v1.y };
    return &groundCollLine[line];
}

s32 Player_GetPlayerState(s32 slot)
{
    CHECK(slot >= 0 && slot < 6);
    ++player_queries;
    return states[slot];
}
HSD_GObj* Player_GetEntity(s32 slot)
{
    CHECK(slot >= 0 && slot < 6);
    ++player_queries;
    return primary[slot];
}
Gm_PKind Player_8003248C(s32 slot, bool secondary)
{
    CHECK(slot >= 0 && slot < 6 && !secondary);
    ++player_queries;
    return kinds[slot];
}
StKind Stage_80225194(void) { ++stage_queries; return stage; }
MapCollData* mpLib_8004D164(void)
{
    CHECK(certificate.allowed); /* EVERY legacy main-floor case forbids this. */
    ++certificate.map_calls;
    return certificate.missing_map ? NULL : &map_data;
}
CollJoint* mpGetGroundCollJoint(void)
{
    CHECK(certificate.allowed);
    ++certificate.joint_calls;
    return certificate.missing_joint ? NULL : &coll_joint;
}
CollLine* mpGetGroundCollLine(void)
{
    CHECK(certificate.allowed);
    ++certificate.line_calls;
    return certificate.missing_lines ? NULL : groundCollLine;
}
bool mpCheckFloor(float ax, float ay, float bx, float by, float offset,
                  Vec3* contact, int* line, u32* flags, Vec3* normal,
                  int skip, int joint_skip, int joint_only,
                  bool (*cb)(Fighter_GObj*, int), Fighter_GObj* gobj)
{
    CHECK(ax == self.cur_pos.x && bx == ax);
    CHECK(ay == self.cur_pos.y + 2 && by == self.cur_pos.y - 2);
    CHECK(offset == 0 && skip == -1 && cb == NULL && gobj == NULL);
    CHECK(joint_skip == self.coll_data.joint_id_skip);
    CHECK(joint_only == self.coll_data.joint_id_only);
    ++floor_stub.calls;
    if (floor_stub.native_scan) {
        int i, last = stage == St_Kind_Battle ? 5 : 2;
        float closest = 1000000.0f;
        bool hit = false;
        /* Vanilla BF order: left strip, center, platforms 2/3/4, right strip.
         * FD has just the three main strips. Platforms have NO adjacency,
         * so the native helper supplies their unextended endpoints.
         * Same native extension and intersection bodies as mpCheckFloor.
         * Its min_dist2 > dist2 is crucial: NEVER replace an equal hit. */
        for (i = 0; i <= last; ++i) {
            float x0, y0, x1, y1, px, py, dist2;
            if (!(groundCollLine[i].flags & CollLine_Floor) ||
                !(groundCollLine[i].flags & LINE_FLAG_ENABLED) ||
                (groundCollLine[i].flags & LINE_FLAG_EMPTY)) continue;
            mpLib_8004ED5C(i, &x0, &y0, &x1, &y1);
            CHECK(y0 == y1); /* This fixture scan covers flat native floors. */
            if (ay >= by && mpLineIntersectionH(&px, &py, x0, y0, x1,
                                                ax, ay, bx, by)) {
                ++floor_stub.hits;
                dist2 = SQ(px - ax) + SQ(py - ay);
                if (dist2 == closest) ++floor_stub.ties;
                if (closest > dist2) {
                    closest = dist2;
                    floor_stub.contact = (Vec3) { px, py, 0 };
                    floor_stub.line = i;
                    floor_stub.flags = map_lines[i].lo_flags;
                    hit = true;
                }
            }
        }
        floor_stub.hit = hit;
    }
    *contact = floor_stub.contact;
    *line = floor_stub.line;
    *flags = floor_stub.flags;
    *normal = floor_stub.normal;
    return floor_stub.hit;
}
#define ENDPOINT(name, field) void name(int line, Vec3* out) { \
    struct FloorGeometry g = geometry(line); ++floor_stub.endpoints; \
    *out = g.field; }
ENDPOINT(mpFloorGetLeft, left)
ENDPOINT(mpFloorGetRight, right)
ENDPOINT(mpLineGetV0Pos, v0)
ENDPOINT(mpLineGetV1Pos, v1)

static void position(float x)
{
    float edge = stage == St_Kind_Battle ? 68.4f : 85.5657f;
    float middle = stage == St_Kind_Battle ? 60.0f : 75.0f;
    int i, last = stage == St_Kind_Battle ? 5 : 2;
    memset(segments, 0, sizeof(segments));
    memset(map_lines, 0, sizeof(map_lines));
    memset(groundCollLine, 0, sizeof(groundCollLine));
    memset(groundCollVtx, 0, sizeof(groundCollVtx));
    for (i = 0; i < 6; ++i) {
        groundCollLine[i].x0 = &map_lines[i];
        groundCollLine[i].flags = CollLine_Floor | LINE_FLAG_ENABLED;
        map_lines[i].hi_flags = CollLine_Floor;
        map_lines[i].v0_idx = 2 * i; map_lines[i].v1_idx = 2 * i + 1;
        map_lines[i].prev_id1 = map_lines[i].next_id1 = -1;
        map_lines[i].prev_id0 = map_lines[i].next_id0 = -1;
        segments[i].left = (Vec3) { -edge, 0, 0 };
        segments[i].right = (Vec3) { edge, 0, 0 };
    }
    segments[0].v0 = segments[0].left;
    segments[0].v1 = segments[1].v0 = (Vec3) { -middle, 0, 0 };
    segments[1].v1 = segments[last].v0 = (Vec3) { middle, 0, 0 };
    segments[last].v1 = segments[last].right;
    /* Outer strips connect to walls too, so BOTH ends can extend. Floor
     * ledge queries still terminate at the last floor vertex, not a wall. */
    map_lines[0].prev_id0 = 3; map_lines[0].next_id0 = 1;
    map_lines[1].prev_id0 = 0; map_lines[1].next_id0 = last;
    map_lines[last].prev_id0 = 1; map_lines[last].next_id0 = 4;
    if (stage == St_Kind_Battle) {
        static const float lefts[] = { -57.6f, -18.8f, 20.0f };
        static const float rights[] = { -20.0f, 18.8f, 57.6f };
        for (i = 2; i <= 4; ++i) {
            float y = i == 3 ? 54.4f : 27.2f;
            segments[i].left = segments[i].v0 =
                (Vec3) { lefts[i - 2], y, 0 };
            segments[i].right = segments[i].v1 =
                (Vec3) { rights[i - 2], y, 0 };
            map_lines[i].lo_flags = LINE_FLAG_PLATFORM;
        }
    }
    self.cur_pos.x = x;
    floor_stub.contact = (Vec3) { x, 0, 0 };
    floor_stub.left = (Vec3) { -edge, 0, 0 };
    floor_stub.right = (Vec3) { edge, 0, 0 };
    /* Native connected outer strips (BF 0/1/5, FD 0/1/2), not a
     * made-up single wide segment. Direction/order of vertices is native. */
    if (x < -middle) {
        floor_stub.line = 0;
        floor_stub.v0 = floor_stub.left;
        floor_stub.v1 = (Vec3) { -middle, 0, 0 };
    } else if (x > middle) {
        floor_stub.line = stage == St_Kind_Battle ? 5 : 2;
        floor_stub.v0 = (Vec3) { middle, 0, 0 };
        floor_stub.v1 = floor_stub.right;
    } else {
        floor_stub.line = 1;
        floor_stub.v0 = (Vec3) { -middle, 0, 0 };
        floor_stub.v1 = (Vec3) { middle, 0, 0 };
    }
    self.coll_data.floor.index = floor_stub.line;
}

static void setup(void)
{
    /* Fill even unrelated motion unions, CPU cache, buffers, timers, pointers,
     * hitboxes and padding with a nonzero sentinel. Initialize only fields
     * the policy/real read-only helpers are allowed to inspect. */
    memset(&self, 0xA5, sizeof(self));
    memset(&rival, 0x5A, sizeof(rival));
    memset(&other, 0x3C, sizeof(other));
    memset(objects, 0, sizeof(objects));
    memset(primary, 0, sizeof(primary));
    memset(states, 0, sizeof(states));
    memset(kinds, 0, sizeof(kinds));
    memset(&entities, 0, sizeof(entities));
    memset(&floor_stub, 0, sizeof(floor_stub));
    memset(&certificate, 0, sizeof(certificate));
    memset(&map_data, 0, sizeof(map_data));
    memset(&map_joint, 0, sizeof(map_joint));
    memset(&foreign_joint, 0, sizeof(foreign_joint));
    memset(&coll_joint, 0, sizeof(coll_joint));
    player_queries = stage_queries = 0;
    objects[0].user_data = &self;
    objects[1].user_data = &rival;
    objects[2].user_data = &other;
    self.gobj = primary[0] = &objects[0];
    rival.gobj = primary[1] = &objects[1];
    self.player_id = 0; rival.player_id = 1;
    self.x8_spawnNum = 8; rival.x8_spawnNum = 11;
    states[0] = states[1] = 2;
    kinds[0] = kinds[1] = Gm_PKind_Cpu;
    self.kind = FTKIND_CAPTAIN; rival.kind = FTKIND_KIRBY;
    self.x221F_b4 = rival.x221F_b4 = 0;
    self.x221F_b3 = rival.x221F_b3 = 0;
    self.item_gobj = rival.item_gobj = NULL;
    self.x221D_b6 = rival.x221D_b6 = 0;
    self.x1988 = self.x198C = rival.x1988 = rival.x198C = 0;
    self.motion_id = ftCo_MS_Wait;
    rival.motion_id = ftCo_MS_DamageFlyTop;
    self.ground_or_air = GA_Ground; rival.ground_or_air = GA_Air;
    self.x221C_b6 = 0; rival.x221C_b6 = 1;
    rival.x2219_b5 = 0;
    self.x2219_b5 = self.x221A_b3 = self.x2224_b2 = self.x221D_b4 = 0;
    self.x2228_b2 = self.x2222_b6 = 0;
    self.dmg.x1948 = 0;
    self.victim_gobj = self.x1A5C = NULL;
    self.x1064_thrownHitbox.owner = NULL;
    self.facing_dir = -1;
    self.x34_scale.y = 1;
    self.co_attrs.model_scaling = 0.97f;
    self.cur_pos = self.self_vel = self.pos_delta = (Vec3) { 0, 0, 0 };
    self.x8c_kb_vel = self.x98_atk_shield_kb = self.x74_anim_vel = self.self_vel;
    self.gr_vel = 0;
    self.cpu.level = 9; self.cpu.xC = 4;
    self.cpu.x18 = 9; self.cpu.xA4 = 0; self.cpu.xF4 = NULL;
    self.cpu.buttons = HSD_PAD_B;
    self.cpu.lstick = (S8Vec2) { -127, 0 };
    self.cpu.cstick = (S8Vec2) { 0, 0 };
    self.cpu.ltrigger = self.cpu.rtrigger = 0;
    self.input.held_buttons[0] = 0;
    self.input.triggers[0] = 0;
    self.input.cstick[0] = (Vec2) { 0, 0 };
    self.cpu.x44 = &rival;
    self.cpu.csP = self.cpu.buffer + 41;
    self.cpu.write_pos = self.cpu.buffer + 97;
    self.cpu.command_duration = 1;
    HSD_GObj_Entities = &entities;
    stage = St_Kind_Battle;
    floor_stub.hit = true;
    floor_stub.normal = (Vec3) { 0, 1, 0 };
    /* Other unrecorded floor/input/scale state above is explicitly stubbed. */
    position(-47.3126f);
}

static void verify(Fighter* fp, Fighter* target, bool expected)
{
    Fighter before, target_before, other_before;
    HSD_GObj objs_before[3];
    HSD_GObjList entities_before;
    memcpy(&before, &self, sizeof(self));
    memcpy(&target_before, &rival, sizeof(rival));
    memcpy(&other_before, &other, sizeof(other));
    memcpy(objs_before, objects, sizeof(objects));
    memcpy(&entities_before, &entities, sizeof(entities));
    CHECK(ShowboatSafety_PostInput(fp, target) == expected);
    if (expected) {
        before.cpu.buttons &= ~HSD_PAD_B;
        before.cpu.lstick.x = 0;
    }
    /* ENTIRE native declarations including every CPU/cache/VM/game byte. */
    CHECK(memcmp(&before, &self, sizeof(self)) == 0);
    CHECK(memcmp(&target_before, &rival, sizeof(rival)) == 0);
    CHECK(memcmp(&other_before, &other, sizeof(other)) == 0);
    CHECK(memcmp(objs_before, objects, sizeof(objects)) == 0);
    CHECK(memcmp(&entities_before, &entities, sizeof(entities)) == 0);
    ++checks;
}
#define VETO() verify(&self, &rival, true)
#define PASS() verify(&self, &rival, false)
#define REJECT(...) do { setup(); __VA_ARGS__; PASS(); } while (0)
#define ACCEPT(...) do { setup(); __VA_ARGS__; VETO(); } while (0)

static void observed_left_hitstun(void)
{
    setup();
    /* Observed fields from playtest_3 f7095, not a full replay. Native enum
     * cross-check prevents silently treating motion 90 as Wait/ordinary Fall.
     * Only rival air+hitstun flags3 were observed; its other state is stubbed.
     * Sparse trace does NOT record scale, facing, sampled input, VM or floor. */
    CHECK(ftCo_MS_DamageFlyTop == 90);
    rival.cur_pos = (Vec3) { -84.22f, 31.17f, 0 };
    self.dmg.x1830_percent = 137.7f;
    VETO();
    CHECK(floor_stub.calls == 1 && floor_stub.endpoints == 10);
    CHECK(floor_stub.native_calls[1] == 2);
}
static void mirrored_right_hitstun(void)
{
    setup(); position(47.3126f);
    self.cpu.lstick.x = 127;
    self.facing_dir = 1;
    rival.cur_pos = (Vec3) { 84.22f, 31.17f, 0 };
    VETO();
}
static void direction_not_facing(void)
{
    ACCEPT(self.facing_dir = 1);
    ACCEPT(position(47.3126f); self.cpu.lstick.x = 127; self.facing_dir = -1);
    ACCEPT(self.cpu.lstick.x = -128);
}
static void center_and_inward(void)
{
    int dir, st;
    for (st = 0; st < 2; ++st) {
        for (dir = -1; dir <= 1; dir += 2) {
            setup(); stage = st ? St_Kind_Last : St_Kind_Battle;
            self.cpu.lstick.x = dir * 127; position(0); PASS();
            position(-dir * 47.3126f); PASS();
            /* Inward B is NOT universally safe: the windup goes backwards. */
            position(-dir * (st ? 80.0f : 65.0f)); VETO();
        }
    }
}
static void connected_outer_strips(void)
{
    ACCEPT(position(-65));
    ACCEPT(position(65); self.cpu.lstick.x = 127);
    ACCEPT(stage = St_Kind_Last; position(-80));
    ACCEPT(stage = St_Kind_Last; position(80); self.cpu.lstick.x = 127);
    /* Native connected bound is 68.4, not the central segment's 60. */
    REJECT(position(0));
}
static void runway_boundaries(void)
{
    int st, dir, backwards, delta;
    for (st = 0; st < 2; ++st) for (dir = -1; dir <= 1; dir += 2)
    for (backwards = 0; backwards < 2; ++backwards)
    for (delta = -1; delta <= 1; ++delta) {
        float threshold, edge, x;
        setup(); stage = st ? St_Kind_Last : St_Kind_Battle;
        self.cpu.lstick.x = dir * 127;
        edge = st ? 85.5657f : 68.4f;
        /* Nearby normal model scale makes the backward threshold exactly
         * representable as a difference at BOTH BF/FD coordinate magnitudes.
         * Default .97's 16.670000076 is between those representable runways. */
        if (backwards) self.co_attrs.model_scaling = 0.9700005f;
        threshold = (backwards ? 11.0f : 61.0f) * self.co_attrs.model_scaling + 6;
        x = backwards ? dir * (threshold - edge) : dir * (edge - threshold);
        /* Place the actual queried ledge at x+threshold; check equality below
         * rather than falsely calling a rounded slightly-short runway exact. */
        position(x);
        if (backwards) {
            if (dir > 0) floor_stub.left.x = x - threshold;
            else floor_stub.right.x = x + threshold;
        } else {
            if (dir > 0) floor_stub.right.x = x + threshold;
            else floor_stub.left.x = x - threshold;
        }
        if (delta == 0) {
            float actual;
            if (backwards) actual = dir > 0 ? x - floor_stub.left.x : floor_stub.right.x - x;
            else actual = dir > 0 ? floor_stub.right.x - x : x - floor_stub.left.x;
            CHECK(actual == threshold);
        }
        /* A milliworld-unit inside/outside the two independent envelopes. */
        self.cur_pos.x += (backwards ? dir : -dir) * delta * 0.001f;
        floor_stub.contact.x = self.cur_pos.x;
        verify(&self, &rival, delta <= 0);
    }
}
static void scale_scope_and_product(void)
{
    float bad[] = { 0, -1, 0.5f, 1.5f, 2, 0.999f, 1.001f };
    unsigned i;
    for (i = 0; i < sizeof(bad) / sizeof(bad[0]); ++i) {
        REJECT(self.x34_scale.y = bad[i]);
    }
    REJECT(self.co_attrs.model_scaling = 1);
    REJECT(self.co_attrs.model_scaling = 0);
    REJECT(self.co_attrs.model_scaling = -0.97f);
    REJECT(self.co_attrs.model_scaling = 0.969f);
    REJECT(self.co_attrs.model_scaling = 0.971f);
    ACCEPT(self.x34_scale.y = 1.00005f; self.co_attrs.model_scaling = 0.97005f);
    ACCEPT(self.x34_scale.y = 0.99995f; self.co_attrs.model_scaling = 0.96995f);
    /* Actual product, not a constant .97 or either scale factor alone. */
    setup(); position(-3.228f); PASS();
    setup(); position(-3.228f);
    self.x34_scale.y = 1.00005f; self.co_attrs.model_scaling = 0.97005f; VETO();
    setup(); position(-3.228f);
    self.x34_scale.y = 0.99995f; self.co_attrs.model_scaling = 0.96995f; PASS();
}
static void walks_and_motion_scope(void)
{
    int motion;
    for (motion = ftCo_MS_Wait; motion <= ftCo_MS_WalkFast; ++motion) {
        ACCEPT(self.motion_id = motion; self.gr_vel = 2.5f;
               self.self_vel.x = -2.5f; self.pos_delta.x = 2.5f);
    }
    /* EVERY other common state and every Captain-specific state yields. */
    for (motion = 0; motion <= ftCa_MS_SpecialAirLwEnd; ++motion) {
        if (motion >= ftCo_MS_Wait && motion <= ftCo_MS_WalkFast) continue;
        REJECT(self.motion_id = motion);
    }
    REJECT(self.ground_or_air = GA_Air);
    REJECT(self.ground_or_air = (GroundOrAir) 2);
}
static void target_location_and_motion_irrelevant(void)
{
    ACCEPT(rival.ground_or_air = GA_Ground; rival.motion_id = ftCo_MS_Wait;
           rival.cur_pos = (Vec3) { -20, 0, 0 });
    ACCEPT(rival.ground_or_air = GA_Ground; rival.motion_id = ftCo_MS_WalkFast;
           rival.cur_pos = (Vec3) { 50, 0, 0 });
    ACCEPT(rival.x2219_b5 = rival.x221A_b3 = 1;
           rival.self_vel = (Vec3) { 9, 20, -8 };
           rival.x8c_kb_vel = (Vec3) { 100, 200, 300 });
    ACCEPT(rival.motion_id = ftCo_MS_FallSpecial);
    /* No reads of target animation displacement, speed, facing or scale. */
    ACCEPT(rival.facing_dir = 0; rival.x34_scale.y = 5);
}
static void native_priority_and_cache(void)
{
    int priority;
    for (priority = -1; priority <= 20; ++priority) {
        if (priority != 9) REJECT(self.cpu.x18 = priority);
    }
    REJECT(self.cpu.xA4 = 1);
    REJECT(self.cpu.xA4 = -1);
    REJECT(self.victim_gobj = rival.gobj);
    ACCEPT(self.cpu.x1C = 4; self.cpu.x44 = &other);
}
static void eligibility_identity(void)
{
    REJECT(self.cpu.level = 8);
    REJECT(self.cpu.xC = 5);
    REJECT(self.cpu.xC = 0);
    REJECT(self.kind = FTKIND_GANON);
    REJECT(kinds[0] = Gm_PKind_Human);
    REJECT(self.player_id = 6);
    REJECT(rival.player_id = 6);
    REJECT(rival.player_id = self.player_id);
    REJECT(self.gobj = NULL);
    REJECT(rival.gobj = NULL);
    REJECT(primary[0] = &objects[2]);
    REJECT(primary[1] = &objects[2]);
    REJECT(objects[0].user_data = &other);
    REJECT(objects[1].user_data = &other);
    REJECT(self.x221F_b4 = 1);
    REJECT(rival.x221F_b4 = 1);
    REJECT(states[0] = 0);
    REJECT(states[1] = 1);
    setup(); verify(NULL, &rival, false);
    setup(); verify(&self, NULL, false);
    setup(); verify(&self, &self, false);
}
static void main_contract_not_reimplemented(void)
{
    /* Direct module calls deliberately know nothing about rules, teams,
     * third players, custom state or readiness. MAIN must not call then.
     * Integration spies belong to test_showboat_ai.py, not this module. */
    ACCEPT(self.team = rival.team = 1);
    ACCEPT(primary[2] = &objects[2]; states[2] = 2);
}
static void unavailable_protection_items(void)
{
    REJECT(self.x221F_b3 = 1);
    REJECT(rival.x221F_b3 = 1);
    REJECT(rival.motion_id = ftCo_MS_DeadDown);
    REJECT(rival.motion_id = ftCo_MS_RebirthWait);
    REJECT(rival.motion_id = ftCo_MS_Entry);
    REJECT(rival.motion_id = ftCo_MS_EntryStart);
    REJECT(rival.motion_id = ftCo_MS_EntryEnd);
    REJECT(self.x221D_b6 = 1);
    REJECT(self.x1988 = 1);
    REJECT(self.x198C = 2);
    REJECT(rival.x221D_b6 = 1);
    REJECT(rival.x1988 = 1);
    REJECT(rival.x198C = 2);
    REJECT(self.item_gobj = &objects[2]);
    REJECT(rival.item_gobj = &objects[2]);
    REJECT(entities.items = &objects[2]);
    REJECT(HSD_GObj_Entities = NULL);
    REJECT(self.cpu.xF4 = (Item*) &other);
}
static void self_forced_state_and_velocity(void)
{
    REJECT(self.x221C_b6 = 1);
    REJECT(self.x2219_b5 = 1);
    REJECT(self.x221A_b3 = 1);
    REJECT(self.x2224_b2 = 1);
    REJECT(self.x221D_b4 = 1);
    REJECT(self.x2228_b2 = 1);
    REJECT(self.x2222_b6 = 1);
    REJECT(self.dmg.x1948 = 1);
    REJECT(self.x1A5C = rival.gobj);
    REJECT(self.x1064_thrownHitbox.owner = rival.gobj);
    REJECT(self.gr_vel = 2.5001f);
    REJECT(self.gr_vel = -2.5001f);
    REJECT(self.self_vel.x = 2.5001f);
    REJECT(self.self_vel.y = -2.5001f);
    REJECT(self.self_vel.z = 2.5001f);
    REJECT(self.pos_delta.x = 2.5001f);
    REJECT(self.pos_delta.y = -2.5001f);
    REJECT(self.pos_delta.z = 2.5001f);
    REJECT(self.x8c_kb_vel.x = 0.001f);
    REJECT(self.x8c_kb_vel.y = -0.001f);
    REJECT(self.x8c_kb_vel.z = 0.001f);
    REJECT(self.x98_atk_shield_kb.x = 0.001f);
    REJECT(self.x98_atk_shield_kb.y = 0.001f);
    REJECT(self.x98_atk_shield_kb.z = 0.001f);
    REJECT(self.x74_anim_vel.x = 0.001f);
    REJECT(self.x74_anim_vel.y = 0.001f);
    REJECT(self.x74_anim_vel.z = 0.001f);
    REJECT(self.facing_dir = 0);
    REJECT(self.facing_dir = 0.999f);
    REJECT(self.cur_pos.z = 1.01f);
}
static void raw_input_narrowness(void)
{
    int x, bit;
    for (x = -128; x <= 127; ++x) {
        if (x != -128 && x != -127 && x != 127)
            REJECT(self.cpu.lstick.x = x);
    }
    for (bit = 0; bit < 16; ++bit) {
        if ((1U << bit) != HSD_PAD_B)
            REJECT(self.cpu.buttons |= 1U << bit);
        REJECT(self.input.held_buttons[0] = 1U << bit);
    }
    REJECT(self.cpu.buttons = 0);
    REJECT(self.cpu.buttons = HSD_PAD_A);
    REJECT(self.cpu.lstick.y = 127);
    REJECT(self.cpu.lstick.y = -128);
    REJECT(self.cpu.lstick.y = 1);
    REJECT(self.cpu.cstick.x = 1);
    REJECT(self.cpu.cstick.y = -1);
    REJECT(self.cpu.ltrigger = 1);
    REJECT(self.cpu.rtrigger = 255);
    REJECT(self.input.triggers[0] = 0.01f);
    REJECT(self.input.cstick[0].x = 0.01f);
    REJECT(self.input.cstick[0].y = -0.01f);
    ACCEPT(self.input.lstick[0] = (Vec2) { -1, 0 });
}
static void opaque_vm_foreign_pointers(void)
{
    s8 foreign[8] = { -7, -6, -5, -4, -3, -2, -1, 0 };
    s8 snapshot[8];
    memcpy(snapshot, foreign, sizeof(foreign));
    ACCEPT(self.cpu.csP = foreign; self.cpu.write_pos = foreign + 8;
           self.cpu.command_duration = 0xFFFFFFFFUL);
    ACCEPT(self.cpu.csP = NULL; self.cpu.write_pos = NULL;
           self.cpu.command_duration = 0);
    ACCEPT(self.cpu.csP = self.cpu.buffer + sizeof(self.cpu.buffer);
           self.cpu.write_pos = self.cpu.buffer; self.cpu.command_duration = 55);
    ACCEPT(self.cpu.csP = (s8*) 1; self.cpu.write_pos = (s8*) 3);
    CHECK(memcmp(snapshot, foreign, sizeof(foreign)) == 0);
}
static void no_restore_and_future_inputs(void)
{
    int wait;
    setup(); VETO(); PASS(); /* Stateless second call cannot restore B. */
    /* Native f42 release/neutral wait55, modeled OUTPUTS only (not a VM
     * emulator). Module must preserve each duration/cursor and idle output. */
    self.cpu.csP = self.cpu.buffer + 48;
    for (wait = 55; wait > 0; --wait) {
        self.cpu.command_duration = wait;
        self.cpu.buttons = 0; self.cpu.lstick.x = 0; PASS();
    }
    self.cpu.csP = self.cpu.buffer + 51;
    self.cpu.command_duration = 1;
    self.cpu.buttons = HSD_PAD_X; PASS(); /* Native f97 jump remains possible. */
    self.cpu.buttons = HSD_PAD_A; PASS(); /* Subsequent followup attack. */
    self.cpu.buttons = HSD_PAD_B; self.cpu.lstick.x = -127;
    position(0); PASS(); /* Future safe B is not blocked by remembered state. */
    position(-47.3126f); VETO(); /* Fresh unsafe sample still independently vetoed. */
    self.cpu.buttons = HSD_PAD_B; self.cpu.lstick.x = -127;
    self.input.held_buttons[0] = HSD_PAD_B; PASS(); /* Never release held B. */
}
static void bad_floor_queries(void)
{
    REJECT(stage = St_Kind_Castle);
    REJECT(floor_stub.hit = false);
    REJECT(floor_stub.line = -1);
    REJECT(floor_stub.line = 3; self.coll_data.floor.index = 3);
    REJECT(floor_stub.line = 2; self.coll_data.floor.index = 2); /* BF platform */
    REJECT(stage = St_Kind_Last; position(-47); floor_stub.line = 5;
           self.coll_data.floor.index = 5);
    /* UNRELATED mismatch: root -47.31 is far outside strip 0's native
     * envelope, unlike the legitimate 0/1 seam overlap near -60. */
    REJECT(self.coll_data.floor.index = 0);
    REJECT(floor_stub.flags = LINE_FLAG_PLATFORM);
    REJECT(floor_stub.normal.x = 0.01f);
    REJECT(floor_stub.normal.y = 0.98f);
    REJECT(floor_stub.normal.y = -1);
    REJECT(floor_stub.normal.z = 0.01f);
    REJECT(floor_stub.left.x = -60);
    REJECT(floor_stub.right.x = 60);
    REJECT(floor_stub.left.x = 68.4f; floor_stub.right.x = -68.4f);
    REJECT(floor_stub.left.y = 1);
    REJECT(floor_stub.right.y = 1);
    REJECT(floor_stub.v0.y = 1);
    REJECT(floor_stub.v1.y = 1);
    REJECT(floor_stub.v0.x = 60; floor_stub.v1.x = -60);
    REJECT(floor_stub.v0.x = -80);
    REJECT(floor_stub.v1.x = 80);
    REJECT(floor_stub.v0.x = -40);
    REJECT(floor_stub.contact.x += 0.2f);
    REJECT(floor_stub.contact.y = 1);
    REJECT(self.cur_pos.y = 0.26f);
    REJECT(floor_stub.contact.z = 0.01f);
    REJECT(floor_stub.left.z = 0.01f);
    REJECT(floor_stub.right.z = 0.01f);
    REJECT(floor_stub.v0.z = 0.01f);
    REJECT(floor_stub.v1.z = 0.01f);
    REJECT(position(-69));
    REJECT(position(69));
    /* Use queried endpoints, not constants: inward windup just fails after
     * a permitted .05 geometry displacement of the connected left ledge. */
    setup(); self.cpu.lstick.x = 127; position(-51.7f); PASS();
    self.cpu.buttons = HSD_PAD_B; self.cpu.lstick.x = 127;
    floor_stub.left.x += 0.05f; VETO();
}
static float special_float(unsigned bits)
{
    float result;
    CHECK(sizeof(bits) == sizeof(result));
    memcpy(&result, &bits, sizeof(result));
    return result;
}
static void nonfinite_self_and_scale(void)
{
    unsigned i;
    float bad[] = { special_float(0x7FC00000U), special_float(0x7F800000U),
                    special_float(0xFF800000U) };
    for (i = 0; i < 3; ++i) {
        REJECT(self.cur_pos.x = bad[i]); REJECT(self.cur_pos.y = bad[i]);
        REJECT(self.cur_pos.z = bad[i]); REJECT(self.gr_vel = bad[i]);
        REJECT(self.facing_dir = bad[i]); REJECT(self.x34_scale.y = bad[i]);
        REJECT(self.co_attrs.model_scaling = bad[i]);
        REJECT(self.self_vel.x = bad[i]); REJECT(self.self_vel.y = bad[i]);
        REJECT(self.self_vel.z = bad[i]); REJECT(self.pos_delta.x = bad[i]);
        REJECT(self.pos_delta.y = bad[i]); REJECT(self.pos_delta.z = bad[i]);
        REJECT(self.x74_anim_vel.x = bad[i]); REJECT(self.x74_anim_vel.y = bad[i]);
        REJECT(self.x74_anim_vel.z = bad[i]); REJECT(self.x8c_kb_vel.x = bad[i]);
        REJECT(self.x8c_kb_vel.y = bad[i]); REJECT(self.x8c_kb_vel.z = bad[i]);
        REJECT(self.x98_atk_shield_kb.x = bad[i]);
        REJECT(self.x98_atk_shield_kb.y = bad[i]);
        REJECT(self.x98_atk_shield_kb.z = bad[i]);
        REJECT(self.input.triggers[0] = bad[i]);
        REJECT(self.input.cstick[0].x = bad[i]);
        REJECT(self.input.cstick[0].y = bad[i]);
        ACCEPT(rival.cur_pos.x = bad[i]; rival.self_vel.y = bad[i]);
    }
}
static void nonfinite_floor(void)
{
    unsigned i, j, k;
    float bad[] = { special_float(0x7FC00000U), special_float(0x7F800000U),
                    special_float(0xFF800000U) };
    for (i = 0; i < 3; ++i) for (j = 0; j < 6; ++j) for (k = 0; k < 3; ++k) {
        Vec3* v[6];
        setup();
        v[0] = &floor_stub.contact; v[1] = &floor_stub.normal;
        v[2] = &floor_stub.left; v[3] = &floor_stub.right;
        v[4] = &floor_stub.v0; v[5] = &floor_stub.v1;
        if (k == 0) v[j]->x = bad[i];
        if (k == 1) v[j]->y = bad[i];
        if (k == 2) v[j]->z = bad[i];
        PASS();
    }
}

/* Native-seam regressions: unlike position()'s legacy direct-X query fixture,
 * these scan ALL main strips with native extended endpoints/intersection and
 * first-equal-distance-wins. Each side tests BOTH directions, BOTH stored
 * indices, and root on/before/after the unextended seam. */
static void native_first_hit_seam(StKind st, int side)
{
    int delta, stored_side, dir;
    for (delta = -1; delta <= 1; ++delta)
    for (stored_side = 0; stored_side < 2; ++stored_side)
    for (dir = -1; dir <= 1; dir += 2) {
        int query, stored;
        float middle;
        setup(); stage = st;
        middle = st == St_Kind_Battle ? 60.0f : 75.0f;
        position(side * middle + delta * 0.5f);
        floor_stub.native_scan = true;
        query = side < 0 ? 0 : 1;
        stored = stored_side ? (side < 0 ? 1 : (st == St_Kind_Battle ? 5 : 2)) : query;
        self.coll_data.floor.index = stored;
        self.cpu.lstick.x = dir * 127;
        VETO();
        CHECK(floor_stub.line == query);
        CHECK(floor_stub.hits == 2 && floor_stub.ties == 1);
        CHECK(floor_stub.native_calls[query] == (stored == query ? 3 : 2));
        if (stored != query) CHECK(floor_stub.native_calls[stored] == 2);
        if (delta > 0) CHECK(self.cur_pos.x > segments[query].v1.x);
    }
}
static void native_first_hit_bf_left(void)
{ native_first_hit_seam(St_Kind_Battle, -1); }
static void native_first_hit_bf_right(void)
{ native_first_hit_seam(St_Kind_Battle, 1); }
static void native_first_hit_fd_left(void)
{ native_first_hit_seam(St_Kind_Last, -1); }
static void native_first_hit_fd_right(void)
{ native_first_hit_seam(St_Kind_Last, 1); }

static void select_query(int line)
{
    floor_stub.line = line;
    floor_stub.left = segments[line].left;
    floor_stub.right = segments[line].right;
    floor_stub.v0 = segments[line].v0;
    floor_stub.v1 = segments[line].v1;
}

static float adjacent_float(float value, int direction)
{
    unsigned bits;
    CHECK(value != 0 && direction != 0);
    memcpy(&bits, &value, sizeof(bits));
    if ((value > 0) == (direction > 0)) ++bits;
    else --bits;
    return special_float(bits);
}

static void native_extended_boundaries(void)
{
    int st, side, end, delta;
    for (st = 0; st < 2; ++st) for (side = -1; side <= 1; side += 2)
    for (end = 0; end < 2; ++end) for (delta = -1; delta <= 1; ++delta) {
        int query, stored;
        float x0, y0, x1, y1, boundary;
        setup(); stage = st ? St_Kind_Last : St_Kind_Battle;
        position(side * (st ? 75.0f : 60.0f));
        floor_stub.native_scan = true;
        query = side < 0 ? 0 : 1;
        stored = side < 0 ? 1 : (st ? 2 : 5);
        self.coll_data.floor.index = end ? query : stored;
        mpLib_8004ED5C(end ? query : stored, &x0, &y0, &x1, &y1);
        boundary = end ? x1 : x0;
        self.cur_pos.x = delta ? adjacent_float(boundary, delta) : boundary;
        /* Exact native closed boundary and one representable float each side.
         * Beyond x1 the vertical native query switches to the next strip, but
         * stored support is now outside its own envelope and must yield. */
        verify(&self, &rival, end ? delta <= 0 : delta >= 0);
        CHECK(floor_stub.line == (end && delta > 0 ? stored : query));
        CHECK(floor_stub.ties == (end ? delta <= 0 : delta >= 0));
        if (end && delta > 0) {
            /* Faulted/stale query at the same root must also fail: don't
             * certify only the stored line or clamp root to returned contact. */
            floor_stub.native_scan = false;
            select_query(query);
            self.coll_data.floor.index = stored;
            floor_stub.contact.x = boundary;
            PASS();
        }
    }
    for (st = 0; st < 2; ++st) for (side = -1; side <= 1; side += 2)
    for (delta = -1; delta <= 1; ++delta) {
        float edge;
        setup(); stage = st ? St_Kind_Last : St_Kind_Battle;
        edge = side * (st ? 85.5657f : 68.4f);
        position(delta ? adjacent_float(edge, delta) : edge);
        floor_stub.native_scan = true;
        /* Even a valid native wall-adjacent extension is NOT actual runway. */
        verify(&self, &rival, delta * side <= 0);
    }
    for (side = -1; side <= 1; side += 2)
    for (delta = -1; delta <= 1; ++delta) {
        float y = side * 0.25f;
        setup(); position(-59.5f); floor_stub.native_scan = true;
        self.cur_pos.y = delta ? adjacent_float(y, delta) : y;
        verify(&self, &rival, delta * side <= 0);
    }
}

static void native_extension_not_one_unit(void)
{
    int st, side, remove;
    for (st = 0; st < 2; ++st) for (side = -1; side <= 1; side += 2)
    for (remove = 0; remove < 3; ++remove) {
        int query;
        float x0, y0, x1, y1, length;
        setup(); stage = st ? St_Kind_Last : St_Kind_Battle;
        position(side * (st ? 75.0f : 60.0f));
        floor_stub.native_scan = true;
        query = side < 0 ? 0 : 1;
        self.coll_data.floor.index = query;
        length = segments[query].v1.x - segments[query].v0.x;
        self.cur_pos.x = segments[query].v1.x + 1.0f + 0.5f / length;
        if (remove == 1) map_lines[query].prev_id0 = -1;
        if (remove == 2) map_lines[query].next_id0 = -1;
        mpLib_8004ED5C(query, &x0, &y0, &x1, &y1);
        CHECK(y0 == 0 && y1 == 0);
        if (!remove) {
            CHECK(x1 > segments[query].v1.x + 1.0f);
            CHECK(self.cur_pos.x <= x1);
        } else if (remove == 1) {
            CHECK(x0 == segments[query].v0.x);
            CHECK(x1 == segments[query].v1.x + 1.0f);
        } else CHECK(x1 == segments[query].v1.x);
        verify(&self, &rival, remove == 0);
    }
}

static void seam_stored_geometry_rejections(void)
{
    int st, side, mutation;
    for (st = 0; st < 2; ++st) for (side = -1; side <= 1; side += 2)
    for (mutation = 0; mutation < 22; ++mutation) {
        int query, stored;
        struct FloorGeometry* g;
        setup(); stage = st ? St_Kind_Last : St_Kind_Battle;
        position(side * (st ? 75.0f : 60.0f) + 0.5f);
        query = side < 0 ? 0 : 1;
        stored = side < 0 ? 1 : (st ? 2 : 5);
        /* Controlled query lets us fault stored geometry independently of the
         * first-hit scan (which deliberately only models flat native maps). */
        select_query(query);
        self.coll_data.floor.index = stored;
        g = &segments[stored];
        switch (mutation) {
        case 0: self.coll_data.floor.index = -1; break;
        case 1: self.coll_data.floor.index = 99; break;
        case 2: self.coll_data.floor.index = st ? 5 : 2; break; /* alien/platform */
        case 3: self.coll_data.floor.index = side < 0 ? (st ? 2 : 5) : 0; break;
        case 4: g->left.x += 0.01f; break; /* Within known extent tolerance,
                                            * but NOT same connected ledges. */
        case 5: g->right.x -= 0.01f; break;
        case 6: g->left.y += 0.01f; break;
        case 7: g->right.y += 0.01f; break;
        case 8: g->left.z = 0.01f; break;
        case 9: g->right.z = 0.01f; break;
        case 10: g->left.x = -200; break;
        case 11: g->right.x = 200; break;
        case 12: g->v0.x = g->v1.x; break;
        case 13: g->v0.x = g->v1.x + 1; break;
        case 14: g->v0.x = g->left.x - 0.01f; break;
        case 15: g->v1.x = g->right.x + 0.01f; break;
        case 16: g->v0.y = 0.001f; break; /* Small slopes also yield. */
        case 17: g->v1.y = 0.001f; break;
        case 18: g->v0.y = g->v1.y = 0.01f; break; /* Flat but noncoplanar. */
        case 19: g->v0.z = 0.01f; break;
        case 20: g->v1.z = 0.01f; break;
        case 21: g->v0.x = 20; g->v1.x = 30; break; /* Far disjoint segment. */
        }
        PASS();
    }
    /* Equivalence is symmetric, not a special case for query < stored.
     * A controlled alternative query in the same overlap also certifies. */
    for (st = 0; st < 2; ++st) for (side = -1; side <= 1; side += 2) {
        int query, stored;
        setup(); stage = st ? St_Kind_Last : St_Kind_Battle;
        position(side * (st ? 75.0f : 60.0f) - 0.5f);
        query = side < 0 ? 1 : (st ? 2 : 5);
        stored = side < 0 ? 0 : 1;
        select_query(query); self.coll_data.floor.index = stored;
        VETO();
    }
}

static void native_helper_return_validation(void)
{
    int st, side, which, mutation;
    for (st = 0; st < 2; ++st) for (side = -1; side <= 1; side += 2)
    for (which = 0; which < 2; ++which)
    for (mutation = 0; mutation < 10; ++mutation) {
        int query, stored;
        struct FloorGeometry* g;
        setup(); stage = st ? St_Kind_Last : St_Kind_Battle;
        position(side * (st ? 75.0f : 60.0f) + 0.5f);
        query = side < 0 ? 0 : 1;
        stored = side < 0 ? 1 : (st ? 2 : 5);
        select_query(query); self.coll_data.floor.index = stored;
        g = &segments[which ? stored : query];
        /* Fault injection: public actual-vertex fixtures remain good while
         * the REAL helper consumes broken/native-inconsistent vertex data.
         * A range-only implementation must not bless its nonflat/nonfinite Y. */
        g->native_override = true;
        g->native_v0 = g->v0; g->native_v1 = g->v1;
        switch (mutation) {
        case 0: g->native_v0.y = 0.001f; break;
        case 1: g->native_v1.y = 0.001f; break;
        case 2: g->native_v0.y = g->native_v1.y = 0.01f; break;
        case 3: g->native_v0.x = special_float(0x7FC00000U); break;
        case 4: g->native_v1.x = special_float(0x7F800000U); break;
        case 5: g->native_v0.y = special_float(0x7FC00000U); break;
        case 6: g->native_v1.y = special_float(0xFF800000U); break;
        case 7: g->native_v0.y = g->native_v1.y = 101; break;
        case 8: g->native_v0.x = g->native_v1.x = 0; break;
        case 9: g->native_v0.x = 99; g->native_v1.x = -99; break;
        }
        PASS();
        CHECK(floor_stub.native_calls[which ? stored : query] >= 1);
    }
}

static void nonfinite_stored_seam_geometry(void)
{
    unsigned i, j, k;
    float bad[] = { special_float(0x7FC00000U), special_float(0x7F800000U),
                    special_float(0xFF800000U) };
    for (i = 0; i < 3; ++i) for (j = 0; j < 4; ++j) for (k = 0; k < 3; ++k) {
        Vec3* v[4];
        setup(); position(-59.5f); select_query(0);
        self.coll_data.floor.index = 1;
        v[0] = &segments[1].left; v[1] = &segments[1].right;
        v[2] = &segments[1].v0; v[3] = &segments[1].v1;
        if (k == 0) v[j]->x = bad[i];
        if (k == 1) v[j]->y = bad[i];
        if (k == 2) v[j]->z = bad[i];
        PASS();
    }
}

static void cheap_gate_ordering(void)
{
    int gate;
    for (gate = 0; gate < 11; ++gate) {
        setup();
        switch (gate) {
        case 0: self.cpu.x18 = 2; break;
        case 1: self.cpu.xA4 = 1; break;
        case 2: self.ground_or_air = GA_Air; break;
        case 3: self.motion_id = ftCo_MS_FallSpecial; break;
        case 4: self.motion_id = ftCo_MS_DeadDown; break;
        case 5: self.cpu.buttons = 0; break;
        case 6: self.cpu.lstick.x = 0; break;
        case 7: self.input.held_buttons[0] = HSD_PAD_B; break;
        case 8: self.cpu.lstick.y = 1; break;
        case 9: self.cpu.cstick.x = 1; break;
        case 10: self.cpu.ltrigger = 1; break;
        }
        verify(&self, (Fighter*) 1, false); /* target must NOT be inspected */
        CHECK(player_queries == 0 && stage_queries == 0);
        CHECK(floor_stub.calls == 0 && floor_stub.endpoints == 0);
    }
    setup(); verify(NULL, (Fighter*) 1, false);
    CHECK(player_queries == 0 && stage_queries == 0 && floor_stub.calls == 0);
    setup(); self.x74_anim_vel.x = 0.01f; PASS();
    CHECK(player_queries > 0 && stage_queries == 0 && floor_stub.calls == 0);
}

/* Static-platform fixtures certify only the CURRENT floor, never a safe drop
 * onto the main chain. All three widths are 37.6: less than 61*.97+6 even
 * before the independent backward reserve. Thus EVERY eligible position and
 * direction yields a veto. These controlled maps are not loaded stage assets. */
static void platform_setup(int line, float fraction, int dir, bool native_scan)
{
    setup();
    CHECK(line >= 2 && line <= 4);
    certificate.allowed = true;
    map_data.lines = map_lines;
    map_data.line_count = 6;
    map_data.floor_count = 6;
    map_data.joints = &map_joint;
    map_data.joint_count = 1;
    map_joint.floor_count = 6;
    coll_joint.inner = &map_joint;
    coll_joint.flags = CollJoint_Enabled;
    select_query(line);
    self.cur_pos.x = segments[line].left.x + fraction *
        (segments[line].right.x - segments[line].left.x);
    self.cur_pos.y = segments[line].left.y;
    floor_stub.contact = self.cur_pos;
    floor_stub.flags = LINE_FLAG_PLATFORM;
    floor_stub.native_scan = native_scan;
    self.coll_data.floor.index = line;
    self.coll_data.joint_id_skip = self.coll_data.joint_id_only = -1;
    self.cpu.lstick.x = dir * 127;
}

static void platform_all_positions_directions(void)
{
    int line, dir, sample, scan;
    for (line = 2; line <= 4; ++line)
    for (dir = -1; dir <= 1; dir += 2)
    for (scan = 0; scan < 2; ++scan)
    for (sample = 0; sample <= 32; ++sample) {
        platform_setup(line, sample / 32.0f, dir, scan);
        /* Both facing choices, including inward requests near each edge. */
        self.facing_dir = sample & 1 ? dir : -dir;
        CHECK(segments[line].right.x - segments[line].left.x < 61*.97f+6);
        VETO();
        CHECK(certificate.map_calls > 0 && certificate.joint_calls > 0 &&
              certificate.line_calls > 0);
        if (scan) {
            CHECK(floor_stub.line == line && floor_stub.hits == 1 &&
                  floor_stub.ties == 0 && floor_stub.flags == LINE_FLAG_PLATFORM);
        }
    }
}

static void platform_exact_edges_no_extension(void)
{
    int line, dir, side, delta, scan;
    for (line = 2; line <= 4; ++line)
    for (dir = -1; dir <= 1; dir += 2)
    for (side = -1; side <= 1; side += 2)
    for (delta = -1; delta <= 1; ++delta)
    for (scan = 0; scan < 2; ++scan) {
        float edge, x0, y0, x1, y1;
        platform_setup(line, side < 0 ? 0 : 1, dir, scan);
        mpLib_8004ED5C(line, &x0, &y0, &x1, &y1);
        CHECK(x0 == segments[line].left.x && x1 == segments[line].right.x);
        CHECK(y0 == segments[line].left.y && y1 == y0);
        edge = self.cur_pos.x;
        self.cur_pos.x = delta ? adjacent_float(edge, delta) : edge;
        floor_stub.contact.x = self.cur_pos.x;
        verify(&self, &rival, delta * side <= 0);
        if (scan) CHECK(floor_stub.hit == (delta * side <= 0));
    }
    /* A stale contact just INSIDE cannot certify a root just OUTSIDE. Native
     * platform lines have no +/-1 extension, even toward a lower safe floor. */
    for (line = 2; line <= 4; ++line)
    for (dir = -1; dir <= 1; dir += 2)
    for (side = -1; side <= 1; side += 2) {
        platform_setup(line, side < 0 ? 0 : 1, dir, false);
        self.cur_pos.x = adjacent_float(self.cur_pos.x, side);
        PASS();
    }
}

static void observed_platform_f5302(void)
{
    /* Exact binary32 source: playtest_4 capture 20260909T185848...,
     * segment3/slot1/f5302. OBSERVED self [spawn4,kind2,Wait14,anim13,
     * x=c2331c81,y=41d999ce,vx=vy=grvel=0,percent=41199999,shield60,flags0];
     * rival [spawn3,kind4,DamageFlyTop90,anim29,x=c2a29e4f,y=4266331f,
     * vx=0,vy=bfcccccd,grvel=0,percent=42d06149,shield=4265a3da,flags3].
     * Native9/cache0/threat0, B512/-127/0, other outputs zero, action0/owns0/events0.
     * Stocks3 and main-owned action/owns are not module inputs.
     * UNKNOWN -> explicit stubs: line2/certificate and all floor query data,
     * rootZ, facing -1, normal physical/model scale 1/.97, sampled input,
     * identity bindings/readiness, unrecorded forced-state/velocity and
     * item/protection details, VM cursor/timer. Not a complete physics replay. */
    platform_setup(2, .5f, -1, true);
    CHECK(ftCo_MS_Wait == 14 && ftCo_MS_DamageFlyTop == 90 && HSD_PAD_B == 512);
    self.player_id = 1; rival.player_id = 0;
    primary[1] = self.gobj; primary[0] = rival.gobj;
    self.cpu.xF8_b12 = 0;
    self.x8_spawnNum = 4; rival.x8_spawnNum = 3;
    self.cur_anim_frame = special_float(0x41500000U);
    self.cur_pos.x = special_float(0xC2331C81U);
    self.cur_pos.y = special_float(0x41D999CEU);
    self.dmg.x1830_percent = special_float(0x41199999U);
    self.shield_health = special_float(0x42700000U);
    rival.cur_anim_frame = special_float(0x41E80000U);
    rival.cur_pos = (Vec3) { special_float(0xC2A29E4FU),
                            special_float(0x4266331FU), 0 };
    rival.self_vel = (Vec3) { 0, special_float(0xBFCCCCCDU), 0 };
    rival.gr_vel = 0;
    rival.dmg.x1830_percent = special_float(0x42D06149U);
    rival.shield_health = special_float(0x4265A3DAU);
    VETO();
    CHECK(floor_stub.line == 2 && floor_stub.hits == 1);
    PASS(); /* No remembered B restoration. */
    self.cpu.x18 = 2; self.cpu.buttons = HSD_PAD_B; self.cpu.lstick.x = -127;
    PASS(); /* Same observed location, ordinary priority2 remains native. */
}

static void platform_scope_and_future_inputs(void)
{
    int line, dir, motion, gate;
    for (line = 2; line <= 4; ++line)
    for (dir = -1; dir <= 1; dir += 2) {
        for (motion = 0; motion <= ftCa_MS_SpecialAirLwEnd; ++motion) {
            platform_setup(line, .5f, dir, true);
            self.motion_id = motion;
            verify(&self, &rival, motion >= ftCo_MS_Wait && motion <= ftCo_MS_WalkFast);
        }
        for (gate = 0; gate < 16; ++gate) {
            platform_setup(line, .5f, dir, true);
            switch (gate) {
            case 0: self.cpu.x18 = 2; break;
            case 1: self.ground_or_air = GA_Air; break;
            case 2: self.cpu.xA4 = 1; break;
            case 3: self.input.held_buttons[0] = HSD_PAD_B; break;
            case 4: self.cpu.buttons |= HSD_PAD_A; break;
            case 5: self.cpu.lstick.y = 1; break;
            case 6: self.cpu.cstick.x = 1; break;
            case 7: self.cpu.ltrigger = 1; break;
            case 8: self.cpu.buttons = 0; self.cpu.lstick.x = 0; break;
            case 9: self.cpu.buttons = HSD_PAD_X; break;
            case 10: self.cpu.buttons = HSD_PAD_A; break;
            case 11: self.x221C_b6 = 1; break;
            case 12: self.x74_anim_vel.x = .01f; break;
            case 13: self.co_attrs.model_scaling = 1; break;
            case 14: self.x34_scale.y = 2; break;
            case 15: self.self_vel.x = 2.5001f; break;
            }
            PASS();
            CHECK(floor_stub.calls == 0 && certificate.map_calls == 0 &&
                  certificate.joint_calls == 0 && certificate.line_calls == 0);
        }
        platform_setup(line, .5f, dir, true);
        self.cpu.lstick.x = dir < 0 ? -128 : 127;
        self.cpu.csP = (s8*) 1; self.cpu.write_pos = (s8*) 3;
        VETO(); PASS();
        self.cpu.buttons = HSD_PAD_X; PASS();
        self.cpu.buttons = HSD_PAD_A; PASS();
        self.cpu.buttons = HSD_PAD_B; self.cpu.lstick.x = dir * 127; VETO();
    }
}

static void platform_query_identity_and_flags(void)
{
    int line, dir, stored, mutation, bit;
    for (line = 2; line <= 4; ++line)
    for (dir = -1; dir <= 1; dir += 2) {
        for (stored = -1; stored <= 6; ++stored) {
            if (stored == line) continue;
            platform_setup(line, .5f, dir, false);
            self.coll_data.floor.index = stored;
            PASS();
        }
        for (mutation = 0; mutation < 8; ++mutation) {
            platform_setup(line, .5f, dir, false);
            switch (mutation) {
            case 0: stage = St_Kind_Last; break;
            case 1: stage = St_Kind_Castle; break;
            case 2: floor_stub.hit = false; break;
            case 3: floor_stub.line = self.coll_data.floor.index = -1; break;
            case 4: floor_stub.line = self.coll_data.floor.index = 6; break;
            case 5: floor_stub.line = self.coll_data.floor.index = 99; break;
            case 6: floor_stub.line = self.coll_data.floor.index = 0; break;
            case 7: floor_stub.flags = 0; break;
            }
            PASS();
        }
        for (bit = 0; bit < 32; ++bit) {
            if ((1U << bit) == LINE_FLAG_PLATFORM) continue;
            platform_setup(line, .5f, dir, false);
            floor_stub.flags |= 1U << bit;
            PASS();
        }
    }
    /* Same known geometry is insufficient: query and stored platform IDs
     * must be identical even if controlled endpoint stubs alias perfectly. */
    for (line = 2; line <= 4; ++line)
    for (stored = 2; stored <= 4; ++stored) {
        if (stored == line) continue;
        platform_setup(line, .5f, -1, false);
        segments[stored] = segments[line];
        self.coll_data.floor.index = stored;
        PASS();
    }
}

static void unexpected_callback(void* data, int joint, CollData* coll, int x50,
                                mpLib_GroundEnum kind, float delta_y)
{
    (void) data; (void) joint; (void) coll; (void) x50; (void) kind; (void) delta_y;
    CHECK(false); /* Certificate checks must NEVER execute these callbacks. */
}

static void platform_static_certificate_rejections(void)
{
    int line, dir, mutation, bit;
    for (line = 2; line <= 4; ++line)
    for (dir = -1; dir <= 1; dir += 2) {
        for (mutation = 0; mutation < 32; ++mutation) {
            platform_setup(line, .5f, dir, false);
            switch (mutation) {
            case 0: certificate.missing_map = true; break;
            case 1: map_data.joint_count = 0; break;
            case 2: map_data.joint_count = 2; break;
            case 3: map_data.joints = NULL; break;
            case 4: map_data.lines = NULL; break;
            case 5: map_data.line_count = 5; break;
            case 6: map_data.line_count = -1; break;
            case 7: map_data.floor_start = 1; break;
            case 8: map_data.floor_count = 5; break;
            case 9: map_data.floor_count = 7; break;
            case 10: map_data.dynamic_count = 1; break;
            case 11: certificate.missing_joint = true; break;
            case 12: coll_joint.inner = NULL; break;
            case 13: foreign_joint = map_joint; coll_joint.inner = &foreign_joint; break;
            case 14: coll_joint.flags = 0; break;
            case 15: coll_joint.x20 = (HSD_JObj*) 1; break;
            case 16: coll_joint.cb_0 = unexpected_callback; break;
            case 17: coll_joint.cb_1 = unexpected_callback; break;
            case 18: map_joint.floor_start = 1; break;
            case 19: map_joint.floor_count = 5; break;
            case 20: map_joint.floor_count = 7; break;
            case 21: map_joint.dynamic_count = 1; break;
            case 22: certificate.missing_lines = true; break;
            case 23: groundCollLine[line].x0 = NULL; break;
            case 24: groundCollLine[line].x0 = &map_lines[line == 2 ? 3 : 2]; break;
            case 25: groundCollLine[line].flags = CollLine_Floor; break;
            case 26: groundCollLine[line].flags = LINE_FLAG_ENABLED; break;
            case 27: map_lines[line].hi_flags = 0; break;
            case 28: map_lines[line].lo_flags = 0; break;
            case 29: map_data.dynamic_count = -1; break;
            case 30: map_joint.dynamic_count = -1; break;
            case 31: map_data.joint_count = -1; break;
            }
            PASS();
        }
        /* Exact equality, not a selected denylist: every alien bit rejected. */
        for (bit = 0; bit < 32; ++bit) {
            if ((1U << bit) != CollJoint_Enabled) {
                platform_setup(line, .5f, dir, false);
                coll_joint.flags |= 1U << bit; PASS();
            }
            if (!((1U << bit) & (CollLine_Floor | LINE_FLAG_ENABLED))) {
                platform_setup(line, .5f, dir, false);
                groundCollLine[line].flags |= 1U << bit; PASS();
            }
            if (bit < 16 && (1U << bit) != CollLine_Floor) {
                platform_setup(line, .5f, dir, false);
                map_lines[line].hi_flags |= 1U << bit; PASS();
            }
            if (bit < 16 && (1U << bit) != LINE_FLAG_PLATFORM) {
                platform_setup(line, .5f, dir, false);
                map_lines[line].lo_flags |= 1U << bit; PASS();
            }
        }
    }
}

static void platform_adjacency_rejections(void)
{
    int line, dir, field, id;
    for (line = 2; line <= 4; ++line)
    for (dir = -1; dir <= 1; dir += 2)
    for (field = 0; field < 4; ++field)
    for (id = -2; id <= 6; ++id) {
        s16* ids[4];
        if (id == -1) continue;
        platform_setup(line, .5f, dir, false);
        ids[0] = &map_lines[line].prev_id0; ids[1] = &map_lines[line].next_id0;
        ids[2] = &map_lines[line].prev_id1; ids[3] = &map_lines[line].next_id1;
        *ids[field] = id;
        PASS();
    }
}

static void platform_geometry_rejections(void)
{
    int line, dir, mutation;
    for (line = 2; line <= 4; ++line)
    for (dir = -1; dir <= 1; dir += 2)
    for (mutation = 0; mutation < 34; ++mutation) {
        platform_setup(line, .5f, dir, false);
        switch (mutation) {
        case 0: floor_stub.left.x -= .101f; break;
        case 1: floor_stub.right.x += .101f; break;
        case 2: floor_stub.left.y += .101f; break;
        case 3: floor_stub.right.y += .001f; break;
        case 4: floor_stub.v0.x = floor_stub.v1.x; break;
        case 5: floor_stub.v0.x = floor_stub.v1.x + 1; break;
        case 6: floor_stub.v0.x -= .001f; break;
        case 7: floor_stub.v1.x += .001f; break;
        case 8: floor_stub.v0.y += .001f; break;
        case 9: floor_stub.v1.y += .001f; break;
        case 10: floor_stub.contact.x += .101f; break;
        case 11: floor_stub.contact.y += .101f; break;
        case 12: self.cur_pos.y += .251f; break;
        case 13: self.cur_pos.y -= .251f; break;
        case 14: self.cur_pos.z = 1.001f; break;
        case 15: floor_stub.contact.z = .001f; break;
        case 16: floor_stub.left.z = .001f; break;
        case 17: floor_stub.right.z = .001f; break;
        case 18: floor_stub.v0.z = .001f; break;
        case 19: floor_stub.v1.z = .001f; break;
        case 20: floor_stub.normal.x = .0011f; break;
        case 21: floor_stub.normal.y = .9989f; break;
        case 22: floor_stub.normal.y = 1.0011f; break;
        case 23: floor_stub.normal.z = .0011f; break;
        case 24: floor_stub.normal.y = -1; break;
        case 25: floor_stub.left.x = -68.4f; floor_stub.right.x = 68.4f; break;
        case 26: floor_stub.left.y = floor_stub.right.y = 0; break;
        case 27: self.cur_pos.y = 0; break;
        /* Coherent modified geometry: all contact/flatness/source checks
         * still agree, leaving only the KNOWN SHAPE tolerance to reject. */
        case 28: case 29:
            floor_stub.left.y += mutation == 28 ? -.101f : .101f;
            floor_stub.right.y = floor_stub.v0.y = floor_stub.v1.y =
                self.cur_pos.y = floor_stub.contact.y = floor_stub.left.y;
            break;
        case 30: case 31:
            floor_stub.left.x += mutation == 30 ? -.101f : .101f;
            floor_stub.v0.x = floor_stub.left.x;
            break;
        case 32: case 33:
            floor_stub.right.x += mutation == 32 ? -.101f : .101f;
            floor_stub.v1.x = floor_stub.right.x;
            break;
        }
        PASS();
    }
}

static void platform_geometry_tolerances(void)
{
    int line, dir, shift, side, delta;
    for (line = 2; line <= 4; ++line)
    for (dir = -1; dir <= 1; dir += 2)
    for (shift = -1; shift <= 1; shift += 2) {
        platform_setup(line, .5f, dir, false);
        floor_stub.left.x += shift * .05f; floor_stub.right.x += shift * .05f;
        floor_stub.v0 = floor_stub.left; floor_stub.v1 = floor_stub.right;
        floor_stub.left.y += shift * .05f; floor_stub.right.y = floor_stub.left.y;
        floor_stub.v0.y = floor_stub.v1.y = floor_stub.left.y;
        self.cur_pos.y = floor_stub.contact.y = floor_stub.left.y;
        VETO(); /* Known-shape tolerance, not hardcoded exact coordinates. */
    }
    for (line = 2; line <= 4; ++line)
    for (dir = -1; dir <= 1; dir += 2)
    for (side = -1; side <= 1; side += 2)
    for (delta = -1; delta <= 1; ++delta) {
        float y;
        platform_setup(line, .5f, dir, true);
        y = self.cur_pos.y + side * .25f;
        self.cur_pos.y = delta ? adjacent_float(y, delta) : y;
        verify(&self, &rival, delta * side <= 0);
    }
}

static void platform_nonfinite_and_stale_source(void)
{
    int line, dir, value, field, component, mutation;
    float bad[] = { special_float(0x7FC00000U), special_float(0x7F800000U),
                    special_float(0xFF800000U) };
    for (line = 2; line <= 4; ++line)
    for (dir = -1; dir <= 1; dir += 2)
    for (value = 0; value < 3; ++value)
    for (field = 0; field < 7; ++field)
    for (component = 0; component < 3; ++component) {
        Vec3* v[7];
        platform_setup(line, .5f, dir, false);
        v[0] = &floor_stub.contact; v[1] = &floor_stub.normal;
        v[2] = &floor_stub.left; v[3] = &floor_stub.right;
        v[4] = &floor_stub.v0; v[5] = &floor_stub.v1; v[6] = &self.cur_pos;
        if (component == 0) v[field]->x = bad[value];
        if (component == 1) v[field]->y = bad[value];
        if (component == 2) v[field]->z = bad[value];
        PASS();
    }
    /* Current vertex query looks good; native helper's source is stale/bad.
     * Exercise the REAL extension body, not a fabricated helper result. */
    for (line = 2; line <= 4; ++line)
    for (dir = -1; dir <= 1; dir += 2)
    for (mutation = 0; mutation < 10; ++mutation) {
        struct FloorGeometry* g;
        platform_setup(line, .5f, dir, false);
        g = &segments[line]; g->native_override = true;
        g->native_v0 = g->v0; g->native_v1 = g->v1;
        switch (mutation) {
        case 0: g->native_v0.y += .001f; break;
        case 1: g->native_v1.y += .001f; break;
        case 2: g->native_v0.y = g->native_v1.y = 0; break;
        case 3: g->native_v0.x = bad[0]; break;
        case 4: g->native_v1.x = bad[1]; break;
        case 5: g->native_v0.y = bad[0]; break;
        case 6: g->native_v1.y = bad[2]; break;
        case 7: g->native_v0.x += .001f; break;
        case 8: g->native_v1.x -= .001f; break;
        case 9: g->native_v0.x = 99; g->native_v1.x = -99; break;
        }
        PASS();
        CHECK(floor_stub.native_calls[line] >= 1);
    }
}

#define CASE(name) { #name, name }
static const struct { const char* name; void (*run)(void); } cases[] = {
    CASE(observed_left_hitstun),
    CASE(mirrored_right_hitstun),
    CASE(direction_not_facing),
    CASE(center_and_inward),
    CASE(connected_outer_strips),
    CASE(runway_boundaries),
    CASE(scale_scope_and_product),
    CASE(walks_and_motion_scope),
    CASE(target_location_and_motion_irrelevant),
    CASE(native_priority_and_cache),
    CASE(eligibility_identity),
    CASE(main_contract_not_reimplemented),
    CASE(unavailable_protection_items),
    CASE(self_forced_state_and_velocity),
    CASE(raw_input_narrowness),
    CASE(opaque_vm_foreign_pointers),
    CASE(no_restore_and_future_inputs),
    CASE(bad_floor_queries),
    CASE(nonfinite_self_and_scale),
    CASE(nonfinite_floor),
    CASE(native_first_hit_bf_left),
    CASE(native_first_hit_bf_right),
    CASE(native_first_hit_fd_left),
    CASE(native_first_hit_fd_right),
    CASE(native_extended_boundaries),
    CASE(native_extension_not_one_unit),
    CASE(seam_stored_geometry_rejections),
    CASE(native_helper_return_validation),
    CASE(nonfinite_stored_seam_geometry),
    CASE(cheap_gate_ordering),
    CASE(platform_all_positions_directions),
    CASE(platform_exact_edges_no_extension),
    CASE(observed_platform_f5302),
    CASE(platform_scope_and_future_inputs),
    CASE(platform_query_identity_and_flags),
    CASE(platform_static_certificate_rejections),
    CASE(platform_adjacency_rejections),
    CASE(platform_geometry_rejections),
    CASE(platform_geometry_tolerances),
    CASE(platform_nonfinite_and_stale_source),
};
int main(int argc, char** argv)
{
    unsigned i;
    CHECK(argc == 2);
    if (!strcmp(argv[1], "footprint")) {
        printf("Fighter=%lu CpuFighter=%lu guarded_bytes=%lu cases=%lu\n",
               (unsigned long) sizeof(Fighter), (unsigned long) sizeof(self.cpu),
               (unsigned long) (3 * sizeof(Fighter) + sizeof(objects) + sizeof(entities)),
               (unsigned long) (sizeof(cases) / sizeof(cases[0])));
        return 0;
    }
    for (i = 0; i < sizeof(cases) / sizeof(cases[0]); ++i) {
        if (!strcmp(argv[1], cases[i].name)) {
            cases[i].run();
            printf("PASS %s %u\n", argv[1], checks);
            return 0;
        }
    }
    printf("Unknown case %s\n", argv[1]);
    return 1;
}
