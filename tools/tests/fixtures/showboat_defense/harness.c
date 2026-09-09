#include "game.h"
#include "showboat_defense.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static Fighter f[6];
static HSD_GObj obj[6], secondary;
static int player_state[6];
static HSD_GObj *primary[6], *sub[6];
static bool is_cpu;
static float edges[2];
static struct TestEntities entities;
struct TestEntities* HSD_GObj_Entities = &entities;
static struct { int x2B8, powershield_input_window; }
    common = { 32, 2 }, *p_ftCommonData = &common;
static int native_attempts;
static void ftCo_80093850(Fighter_GObj* gobj) { (void) gobj; ++native_attempts; }
static void ftCo_80092450_inline(Fighter_GObj* gobj) { (void) gobj; }
/* Typed dependencies for extracted native C. Effects and victim registration
 * are inert; guard transitions and frame scheduling remain explicit fixtures. */
#define PAD_STACK(n)
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define HSD_ASSERTREPORT(line, cond, msg) assert(cond)
static float lb_8000D008(float y, float x) { return atan2f(y, x); }
static float HSD_Randf(void) { return 0.5f; }
static bool ftCo_800A2998(Fighter* fp, float distance)
{ (void) fp; (void) distance; assert(!"item heuristic outside these cases"); return false; }
static void ftColl_80076808(Fighter* fp, HitCapsule* hit, int kind, void* victim, bool b)
{ (void) fp; (void) hit; (void) victim; assert(kind == 1 && !b); }
static bool ftCo_800BFFD0(Fighter* fp, int id, bool b)
{ (void) fp; assert(id == 118 && !b); return true; }
static void ft_PlaySFX(Fighter* fp, int id, int volume, int pan)
{ (void) fp; assert(id == 104 && volume == 127 && pan == 64); }
static void pl_8003E150(int slot, int secondary_player)
{ assert(slot >= 0 && slot < 6 && !secondary_player); }
static void efSync_Spawn(int id, HSD_GObj* gobj, Vec3* pos)
{ (void) pos; assert((id == 27 || id == 1052) && gobj == NULL); }
/* Native decomp has unused stack/register declarations. Suppress only here,
 * never for the separately compiled production module or handwritten tests. */
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wunused-variable"
#include "native_functions.h"
#pragma GCC diagnostic pop
#define FP (&f[0])
#define TARGET (&f[1])

bool ftCo_800A2040(Fighter* fp) { assert(fp == FP || fp == &f[2]); return is_cpu; }
float ftCo_800A2A70(Fighter* fp, bool side) { (void) fp; return edges[side]; }
s32 Player_GetPlayerState(s32 i) { assert(i >= 0 && i < 6); return player_state[i]; }
HSD_GObj* Player_GetEntity(s32 i) { assert(i >= 0 && i < 6); return primary[i]; }
HSD_GObj* Player_GetEntityAtIndex(int i, int index)
{ assert(index == 1 && i >= 0 && i < 6); return sub[i]; }
void OSReport(const char* fmt, ...) { (void) fmt; }
/* Segment vs stationary body sphere, the restricted arguments of BB104. This
 * mock is geometry, not future shield collision; module computes all endpoints. */
bool lbColl_80006094(Vec3* a, Vec3* b, Vec3* c, Vec3* d,
                     Vec3* out0, Vec3* out1, float r0, float r1)
{
    float x = b->x-a->x, y = b->y-a->y, z = b->z-a->z;
    float len = x*x+y*y+z*z, t = 0, dx, dy, dz;
    assert(c->x == d->x && c->y == d->y && c->z == d->z);
    if (len > 0) { t = ((c->x-a->x)*x+(c->y-a->y)*y+(c->z-a->z)*z)/len; }
    if (t < 0) { t = 0; } if (t > 1) { t = 1; }
    *out0 = (Vec3) { a->x+t*x, a->y+t*y, a->z+t*z }; *out1 = *c;
    dx = out0->x-c->x; dy = out0->y-c->y; dz = out0->z-c->z;
    return dx*dx+dy*dy+dz*dz <= (r0+r1)*(r0+r1);
}

static void setup(void)
{
    int i;
    memset(f, 0, sizeof(f)); memset(primary, 0, sizeof(primary));
    memset(sub, 0, sizeof(sub)); memset(player_state, 0, sizeof(player_state));
    entities.items = NULL; is_cpu = true; edges[0] = edges[1] = 100;
    for (i = 0; i < 6; ++i) {
        ShowboatDefense_ResetSlot(i);
        obj[i].user_data = &f[i]; f[i].gobj = &obj[i]; f[i].player_id = i;
        f[i].x8_spawnNum = 100+i; f[i].kind = FTKIND_CAPTAIN;
        f[i].motion_id = ftCo_MS_Wait; f[i].ground_or_air = GA_Ground;
        f[i].shield_health = 60; f[i].coll_data.floor.index = 3;
        f[i].coll_data.floor.normal.y = 1;
        f[i].cpu.level = 9; f[i].cpu.xC = 4; f[i].cpu.x18 = 7;
        f[i].cpu.x1C = 2; f[i].cpu.x568 = 20;
        f[i].cpu.write_pos = f[i].cpu.buffer;
        f[i].trigger_analog_timer = 254;
        /* Canary bytes in all non-controller CPU fields we don't use. */
        memset(f[i].cpu.unrelated_native_cpu_bytes, 0xA7, 64);
    }
    primary[0] = &obj[0]; primary[1] = &obj[1];
    player_state[0] = player_state[1] = 2;
    TARGET->motion_id = ftCo_MS_Attack11; TARGET->cur_pos.x = 20;
    FP->cpu.xF0 = TARGET; FP->cpu.xF8_b12 = 1;
    TARGET->x914[0].state = HitCapsule_Unk2;
    TARGET->x914[0].damage = 8; TARGET->x914[0].scale = 3;
    TARGET->x914[0].x40_b3 = TARGET->x914[0].x42_b5 = 1;
    TARGET->x914[0].x4C = (Vec3) { 10, 10, 0 };
    TARGET->x914[0].x58 = TARGET->x914[0].x4C;
}

/* ALL game fields, including motion union, inputs, timers, health, positions,
 * flags and every hit capsule must stay bit-identical. Only VM/controller
 * fields are permitted to differ. This also catches priority/A4/cache writes. */
static void write_guard(Fighter* before, Fighter* after)
{
    Fighter masked = *after;
    masked.cpu.buttons = before->cpu.buttons;
    masked.cpu.lstick = before->cpu.lstick; masked.cpu.cstick = before->cpu.cstick;
    masked.cpu.ltrigger = before->cpu.ltrigger; masked.cpu.rtrigger = before->cpu.rtrigger;
    masked.cpu.csP = before->cpu.csP; masked.cpu.write_pos = before->cpu.write_pos;
    masked.cpu.command_duration = before->cpu.command_duration;
    memcpy(masked.cpu.buffer, before->cpu.buffer, sizeof(masked.cpu.buffer));
    assert(memcmp(before, &masked, sizeof(masked)) == 0);
}
static bool update_target(Fighter* target)
{
    Fighter before[6]; bool result; int i;
    memcpy(before, f, sizeof(f)); result = ShowboatDefense_Update(FP, target);
    write_guard(&before[0], FP);
    for (i = 1; i < 6; ++i) { assert(memcmp(&before[i], &f[i], sizeof(Fighter)) == 0); }
    return result;
}
static bool update(void) { return update_target(TARGET); }
static void suspend(void)
{
    Fighter before = *FP; ShowboatDefense_Suspend(FP); write_guard(&before, FP);
}
static void reject(void)
{
    Fighter before = *FP; assert(!update()); assert(memcmp(&before, FP, sizeof(before)) == 0);
    assert(ShowboatDefense_GetAction(FP) == 0); assert(!ShowboatDefense_TakePerfect(FP));
}

static void vm(void) { ftCo_800B3E04(FP); }
/* fighter.c digital-L/R normalization, separate from VM and game transitions. */
static void sample(void)
{
    u32 old = FP->input.held_buttons[0], now = FP->cpu.buttons;
    float trigger = fmaxf(FP->cpu.ltrigger, FP->cpu.rtrigger)/255.0f;
    if (now & (HSD_PAD_L | HSD_PAD_R)) { now |= HSD_PAD_LR; trigger = 1; }
    else if (trigger) { now |= HSD_PAD_LR; }
    FP->input.held_buttons[1] = old;
    FP->input.triggers[1] = FP->input.triggers[0];
    FP->input.held_buttons[0] = now; FP->input.triggers[0] = trigger;
    Fighter_Spaghetti_8006AD10_Inner1(FP); /* native edge accumulation in hitlag */
}
static void begin(void)
{
    assert(update()); assert(ShowboatDefense_GetAction(FP) == 10);
    vm(); sample(); assert(FP->cpu.rtrigger == 255);
    assert(FP->input.pressed_buttons & HSD_PAD_R);
}
static void shield(void) { FP->motion_id = ftCo_MS_GuardReflect; FP->x221C_b2 = 1; }
static void contact(void)
{
    FP->motion_id = ftCo_MS_GuardSetOff; FP->x221C_b2 = 1;
    FP->mv.co.guard.x10 = 8; FP->mv.co.guard.x20 = 73;
    ftColl_80076CBC(TARGET, &TARGET->x914[0], FP);
    assert(FP->mv.co.guard.x1C == 32 && FP->mv.co.guard.x10 == 0);
    assert(FP->mv.co.guard.x20 == 73);
    /* Fighter_ProcessHit consumes then clears these, before the next CPU hook. */
    FP->x19A4 = 0; FP->x19A8 = NULL;
    FP->x2219_b5 = 1; FP->allow_sdi = 1;
}

static void fresh_press_and_bounded_hold(void)
{
    int i;
    setup(); FP->cpu.lstick.x = 80; FP->cpu.cstick.y = -127;
    begin(); shield();
    assert(FP->input.triggers[0] == 1 && (FP->input.held_buttons[0] & HSD_PAD_LR));
    assert(FP->cpu.lstick.x == 0 && FP->cpu.cstick.y == 0);
    for (i = 1; i < 10; ++i) {
        assert(update()); vm(); sample();
        assert(FP->input.held_buttons[0] & HSD_PAD_R);
        assert(!(FP->input.pressed_buttons & HSD_PAD_R));
        assert(!(FP->input.released_buttons & HSD_PAD_R));
        assert(!ShowboatDefense_TakePerfect(FP));
    }
    assert(!update()); assert(FP->cpu.csP == NULL);
    assert(FP->cpu.write_pos == FP->cpu.buffer && FP->cpu.x18 == 7);
    assert(FP->cpu.buttons & HSD_PAD_R); assert(FP->cpu.rtrigger == 255);
}
#define DENY(change) do { setup(); change; reject(); } while (0)
static void fresh_empty_only(void)
{
    int i;
    for (i = 0; i <= 20; ++i) { if (i != 7) { DENY(FP->cpu.x18 = i); } }
    DENY(FP->cpu.xA4 = 14);
    DENY(FP->cpu.csP = FP->cpu.buffer; FP->cpu.command_duration = 1);
    DENY(FP->cpu.command_duration = 1);
    DENY(FP->cpu.csP = FP->cpu.buffer);
    DENY(FP->cpu.write_pos++);
    /* Completed native7 buffer is NOT fresh empty. */
    DENY(FP->cpu.buffer[0] = CpuCmd_PressR; FP->cpu.write_pos += 2);
    for (i = ftCo_MS_Wait; i <= ftCo_MS_WalkFast; ++i) {
        setup(); FP->motion_id = i; assert(update());
    }
}
static void released_sample_and_no_retap(void)
{
    u32 masks[] = { HSD_PAD_R, HSD_PAD_L, HSD_PAD_LR, HSD_PAD_Z,
                    HSD_PAD_A, HSD_PAD_B, HSD_PAD_X, HSD_PAD_Y };
    size_t i;
    for (i = 0; i < sizeof(masks)/sizeof(*masks); ++i) {
        DENY(FP->cpu.buttons = masks[i]);
        DENY(FP->input.held_buttons[0] = masks[i]);
    }
    DENY(FP->cpu.rtrigger = 1); DENY(FP->cpu.ltrigger = 1);
    DENY(FP->input.triggers[0] = 0.01f); DENY(FP->input.triggers[0] = NAN);
    setup(); FP->cpu.buttons = HSD_PAD_L; sample();
    assert(FP->input.triggers[0] == 1 && (FP->input.held_buttons[0] & HSD_PAD_LR));
    FP->cpu.buttons = 0; reject(); /* cpu released, Fighter sample still held */
    sample(); assert(update()); /* natural release, not a module neutral frame */
    setup(); begin(); shield();
    assert(update()); vm(); sample(); assert(!(FP->input.pressed_buttons & HSD_PAD_R));
    assert(!ShowboatDefense_TakePerfect(FP));
}
static void eligibility_and_live_identity(void)
{
    DENY(FP->cpu.level = 8); DENY(FP->cpu.xC = 3); DENY(is_cpu = false);
    DENY(FP->kind = FTKIND_FOX); DENY(FP->x221F_b3 = 1);
    DENY(FP->x221F_b4 = 1); DENY(TARGET->x221F_b3 = 1);
    DENY(TARGET->x221F_b4 = 1); DENY(primary[0] = NULL);
    DENY(primary[1] = NULL); DENY(player_state[0] = 0);
    DENY(player_state[2] = 2); DENY(sub[0] = &secondary); DENY(sub[1] = &secondary);
    DENY(TARGET->gobj = &secondary); DENY(TARGET->player_id = 4);
    setup(); assert(!update_target(NULL));
    setup(); assert(!update_target(FP));
    setup(); assert(!update_target((Fighter*) (uintptr_t) 1)); /* never deref token */
    setup(); FP->player_id = 6; reject();
}
static void exclusions(void)
{
    int motions[] = { ftCo_MS_GuardOn, ftCo_MS_Guard, ftCo_MS_GuardReflect,
        ftCo_MS_GuardSetOff, ftCo_MS_GuardOff, ftCo_MS_EscapeF, ftCo_MS_EscapeB,
        ftCo_MS_EscapeN, ftCo_MS_EscapeAir, ftCo_MS_DamageHi1, ftCo_MS_Fall,
        ftCo_MS_Entry, ftCo_MS_DeadDown, ftCo_MS_Attack11, ftCo_MS_Landing,
        ftCo_MS_Squat, ftCo_MS_Dash, ftCo_MS_Catch, ftCo_MS_CliffWait };
    size_t i;
    for (i = 0; i < sizeof(motions)/sizeof(*motions); ++i) { DENY(FP->motion_id = motions[i]); }
    DENY(FP->ground_or_air = GA_Air); DENY(TARGET->ground_or_air = GA_Air);
    DENY(FP->x221C_b6 = 1); DENY(FP->x2224_b2 = 1); DENY(FP->x221D_b4 = 1);
    DENY(FP->x2219_b5 = 1); DENY(FP->x221A_b3 = 1);
    DENY(FP->victim_gobj = &obj[1]); DENY(FP->x1A5C = &obj[1]);
    DENY(TARGET->x1064_thrownHitbox.owner = FP);
    DENY(FP->item_gobj = &secondary); DENY(TARGET->item_gobj = &secondary);
    DENY(entities.items = &secondary); DENY(FP->cpu.xF4 = &secondary);
    DENY(FP->cpu.xF8_b12 = 0); DENY(FP->cpu.xF8_b12 = 2); DENY(FP->cpu.xF8_b12 = 3);
    DENY(FP->cpu.xF0 = FP); DENY(FP->cpu.xF0 = NULL);
    DENY(TARGET->motion_id = ftCo_MS_Catch);
    DENY(TARGET->motion_id = ftCo_MS_AttackAirN);
    DENY(TARGET->motion_id = ftCa_MS_SpecialLw);
    DENY(TARGET->motion_id = ftCo_MS_Wait); /* active stale capsule */
    DENY(TARGET->x2219_b5 = 1); DENY(TARGET->x221A_b3 = 1);
}
static void geometry_and_capsules(void)
{
    int i;
    DENY(FP->shield_health = 44.99f); DENY(FP->shield_health = NAN);
    setup(); FP->shield_health = 45; assert(update());
    DENY(edges[0] = 22); DENY(edges[1] = -1); DENY(edges[0] = NAN);
    DENY(FP->coll_data.floor.index = -1); DENY(TARGET->coll_data.floor.index = 4);
    DENY(FP->coll_data.floor.normal.y = 0.8f);
    DENY(TARGET->cur_pos.y = 4); DENY(TARGET->cur_pos.z = 3);
    DENY(FP->pos_delta.x = 3); DENY(TARGET->pos_delta.x = 4);
    for (i = 0; i <= 1; ++i) { DENY(TARGET->x914[0].state = i); }
    DENY(TARGET->x914[0].state = 5);
    DENY(TARGET->x914[0].x43_b2 = 1); DENY(TARGET->x914[0].x42_b5 = 0);
    DENY(TARGET->x914[0].x40_b3 = 0); DENY(TARGET->x914[0].hit_grabbed_victim_only = 1);
    DENY(TARGET->x914[0].element = HitElement_Catch);
    DENY(TARGET->x914[0].element = HitElement_Inert);
    DENY(TARGET->x914[0].victims_1[11].victim = FP);
    DENY(TARGET->x914[0].scale = NAN); DENY(TARGET->x914[0].damage = 0);
    DENY(TARGET->x914[0].x58.x = NAN); DENY(TARGET->x914[0].x4C.y = INFINITY);
    DENY(TARGET->x914[1] = TARGET->x914[0]; TARGET->x914[1].element = HitElement_Catch);
    DENY(TARGET->x914[1].state = HitCapsule_Enabled);
    setup(); TARGET->x914[0].x4C.x = 20; TARGET->x914[0].x58.x = 24;
    assert(update()); /* now out of range, native 3-frame sweep reaches x=8 */
    DENY(TARGET->x914[0].x4C.x = 20; TARGET->x914[0].x58.x = 16); /* receding */
    DENY(TARGET->x914[0].x4C.x = 30; TARGET->x914[0].x58.x = 34); /* still misses */
}

/* Caller dispatch contract restricted to priority7: native B2790 checks idle
 * VM, resets write_pos, runs BA9A0, then B49F4. ADC28 is a no-op for Captain.
 * Actual BA9A0/builders/interpreter are extracted, not a hand-written roll. */
static void native_defense(int threat)
{
    struct CpuFighter* c = &FP->cpu;
    assert(c->x18 == 7 && c->csP == NULL && c->command_duration == 0);
    c->xF8_b12 = threat;
    ftCo_800B462C(FP); ftCo_800BA9A0(FP); ftCo_800B49F4(FP);
    vm(); sample();
}
static void handoff_no_manufactured_drop(void)
{
    setup(); begin(); shield(); FP->cpu.xF8_b12 = 0;
    assert(!update()); assert(FP->cpu.rtrigger == 255 && (FP->cpu.buttons & HSD_PAD_R));
    assert(FP->cpu.x18 == 7); native_defense(0);
    assert(FP->cpu.rtrigger == 0 && !(FP->cpu.buttons & HSD_PAD_R));
    assert(FP->cpu.x18 == 2);
    setup(); begin(); shield(); TARGET->x914[0].state = HitCapsule_Disabled;
    assert(!update()); assert(FP->cpu.rtrigger == 255);
    native_defense(1); assert(FP->cpu.rtrigger == 0);
    vm(); sample(); assert(FP->cpu.rtrigger == 255 && FP->cpu.lstick.x == 127);
    /* No timeout-generated GuardOff, no release/repress by this module. */
    assert(FP->motion_id == ftCo_MS_GuardReflect);
}
static void acknowledge_and_forced_handoff(void)
{
    int i;
    setup(); begin();
    for (i = 1; i < 3; ++i) { assert(update()); vm(); sample(); }
    assert(!update()); assert(FP->cpu.rtrigger == 255); /* input not acknowledged */
    setup(); begin(); shield(); assert(update()); vm(); sample();
    FP->motion_id = ftCo_MS_Wait; assert(!update()); /* lost acknowledged shield */
    setup(); begin(); shield(); FP->motion_id = ftCo_MS_GuardOff;
    assert(!update()); assert(FP->motion_id == ftCo_MS_GuardOff);
    setup(); begin(); shield(); FP->x221A_b3 = 1;
    assert(!update()); assert(FP->cpu.rtrigger == 255); /* hitlag is not PS */
    assert(!ShowboatDefense_TakePerfect(FP));
    setup(); begin(); shield(); FP->shield_health = 44;
    assert(!update()); assert(FP->cpu.rtrigger == 255);
}
static void contact_marker_and_dedup(void)
{
    int i;
    setup(); begin(); shield(); assert(update()); assert(!ShowboatDefense_TakePerfect(FP));
    contact(); assert(!update()); assert(ShowboatDefense_GetAction(FP) == 11);
    assert(FP->cpu.csP == NULL && FP->cpu.rtrigger == 255);
    assert(FP->allow_sdi && FP->x2219_b5); /* native shield hitlag, not forced away */
    assert(ShowboatDefense_TakePerfect(FP)); assert(!ShowboatDefense_TakePerfect(FP));
    for (i = 0; i < 15; ++i) { assert(!update()); assert(!ShowboatDefense_TakePerfect(FP)); }
    FP->motion_id = ftCo_MS_Wait; assert(!update()); assert(ShowboatDefense_GetAction(FP) == 0);
    /* Real marker alone in GuardReflect is NOT contact state. */
    setup(); begin(); shield(); ftCo_80094138(FP); assert(update());
    assert(!ShowboatDefense_TakePerfect(FP));
    setup(); begin(); FP->motion_id = ftCo_MS_GuardSetOff;
    FP->mv.co.guard.x10 = 8; /* ordinary native branch never sets the marker */
    ftColl_80076CBC(TARGET, &TARGET->x914[0], FP);
    assert(FP->mv.co.guard.x1C == 0 && FP->mv.co.guard.x10 == 8);
    assert(!update()); assert(!ShowboatDefense_TakePerfect(FP));
    setup(); begin(); contact(); FP->mv.co.guard.x1C = 0; FP->mv.co.guard.x20 = 32;
    assert(!update()); assert(!ShowboatDefense_TakePerfect(FP));
    setup(); begin(); contact(); FP->mv.co.guard.x10 = 1;
    assert(!update()); assert(!ShowboatDefense_TakePerfect(FP));
    setup(); begin(); contact(); entities.items = &secondary;
    assert(!update()); assert(!ShowboatDefense_TakePerfect(FP));
    setup(); assert(update()); contact(); /* script never sampled */
    assert(!update()); assert(!ShowboatDefense_TakePerfect(FP));
    setup(); contact(); reject(); /* unrelated native PS not ours */
}
static void native_windows_are_not_contact(void)
{
    int i;
    setup(); begin(); FP->mv.co.guard.x0 = 0; FP->trigger_analog_timer = 0;
    native_attempts = 0;
    assert(ftCo_80093694(FP->gobj)); assert(native_attempts == 1);
    assert(!ShowboatDefense_TakePerfect(FP)); /* entry is only an attempt */
    FP->mv.co.guard.x0 = 2;
    assert(!ftCo_80093694(FP->gobj));
    FP->mv.co.guard.x0 = 1; FP->trigger_analog_timer = 2;
    assert(!ftCo_80093694(FP->gobj));
    FP->trigger_analog_timer = 1;
    assert(ftCo_80093694(FP->gobj));
    sample(); /* held R, not freshly pressed: never retap to extend window */
    assert(!ftCo_80093694(FP->gobj));
    shield(); FP->mv.co.guard.x18 = 3; FP->x221C_b1 = 1;
    FP->mv.co.guard.x14 = 1; FP->reflecting = 1;
    for (i = 0; i < 4; ++i) {
        assert(FP->x221C_b2); /* initial 3,2,1,0: FOUR collision samples */
        ftCo_80093BC0(FP->gobj);
        assert(FP->x221C_b1 == (i == 0)); /* initial 1,0: two projectile samples */
    }
    assert(!FP->x221C_b2 && !FP->reflecting);
    assert(!ShowboatDefense_TakePerfect(FP));
}

static void ordinary_block_and_hitlag(void)
{
    setup(); begin(); FP->motion_id = ftCo_MS_GuardSetOff;
    FP->x2219_b5 = 1; FP->mv.co.guard.x1C = 0; FP->mv.co.guard.x10 = 8;
    assert(!update()); assert(!ShowboatDefense_TakePerfect(FP));
    assert(FP->cpu.rtrigger == 255); /* native SDI/OOS handback also on normal block */
    setup(); begin(); shield(); FP->x2219_b5 = 1;
    assert(!update()); assert(!ShowboatDefense_TakePerfect(FP));
    setup(); begin(); contact(); assert(!update()); assert(ShowboatDefense_TakePerfect(FP));
}
static void old_vm_priority_and_A4(void)
{
    int priorities[] = { 1, 4, 9, 15, 18 }; size_t i;
    setup(); begin(); shield(); FP->cpu.xA4 = 99;
    assert(!update()); assert(FP->cpu.xA4 == 99 && FP->cpu.x18 == 7);
    assert(FP->cpu.csP == NULL && FP->cpu.rtrigger == 255);
    for (i = 0; i < sizeof(priorities)/sizeof(*priorities); ++i) {
        setup(); begin(); shield(); FP->cpu.x18 = priorities[i]; FP->cpu.xA4 = 42;
        FP->cpu.buttons |= HSD_PAD_A; FP->cpu.lstick.x = 99;
        assert(!update()); assert(FP->cpu.x18 == priorities[i] && FP->cpu.xA4 == 42);
        assert(FP->cpu.csP == NULL && FP->cpu.write_pos == FP->cpu.buffer);
        assert(FP->cpu.rtrigger == 0 && FP->cpu.buttons == HSD_PAD_A);
        assert(FP->cpu.lstick.x == 99); /* do not zero native punish controller */
    }
}
static void replacement_and_cursor_ownership(void)
{
    int i;
    for (i = 0; i < 13; ++i) {
        Fighter before;
        setup(); begin(); shield(); FP->cpu.buffer[i] ^= 1; before = *FP;
        assert(!update()); assert(memcmp(&before, FP, sizeof(before)) == 0);
        suspend(); assert(memcmp(&before, FP, sizeof(before)) == 0);
    }
    for (i = 0; i < 5; ++i) {
        Fighter before;
        setup(); begin(); shield();
        switch (i) {
        case 0: FP->cpu.csP = FP->cpu.buffer + 10; break;
        case 1: FP->cpu.command_duration = 11; break;
        case 2: FP->cpu.command_duration = 0; break;
        case 3: FP->cpu.write_pos--; break;
        case 4: FP->cpu.csP = NULL; break;
        }
        before = *FP; assert(!update()); assert(memcmp(&before, FP, sizeof(before)) == 0);
    }
    setup(); begin(); contact(); FP->cpu.buffer[0] = CpuCmd_PressA;
    FP->cpu.csP = FP->cpu.buffer; FP->cpu.command_duration = 1;
    { Fighter before = *FP; assert(!update()); assert(memcmp(&before, FP, sizeof(before)) == 0); }
    assert(!ShowboatDefense_TakePerfect(FP)); /* replacement ends attribution */
}
static void suspension_reset_and_abandoned_tail(void)
{
    int i; Fighter before;
    setup(); begin(); shield(); FP->cpu.xA4 = 23; FP->cpu.ltrigger = 128;
    suspend(); assert(FP->cpu.rtrigger == 0 && !(FP->cpu.buttons & HSD_PAD_R));
    assert(FP->cpu.ltrigger == 128 && FP->cpu.xA4 == 23);
    assert(ShowboatDefense_GetAction(FP) == 0); suspend();
    setup(); begin(); FP->cpu.rtrigger = 127; suspend(); assert(FP->cpu.rtrigger == 127);
    setup(); begin(); before = *FP; ShowboatDefense_ResetSlot(0);
    assert(memcmp(&before, FP, sizeof(before)) == 0); /* memory-only reset */
    for (i = 1; i < 10; ++i) { vm(); sample(); assert(FP->cpu.rtrigger == 255); }
    vm(); sample(); assert(FP->cpu.csP == NULL && FP->cpu.rtrigger == 0);
    assert(!(FP->cpu.buttons & HSD_PAD_R)); /* abandoned bounded tail really executes */
    setup(); begin(); FP->x8_spawnNum++; suspend();
    assert(FP->cpu.csP == NULL && FP->cpu.write_pos == FP->cpu.buffer);
    assert(FP->cpu.rtrigger == 0 && !(FP->cpu.buttons & HSD_PAD_R));
    assert(!ShowboatDefense_TakePerfect(FP));
    ShowboatDefense_ResetSlot(-1); ShowboatDefense_ResetSlot(6);
    ShowboatDefense_Suspend(NULL); assert(!ShowboatDefense_Update(NULL, NULL));
    assert(ShowboatDefense_GetAction(NULL) == 0 && !ShowboatDefense_TakePerfect(NULL));
}
static void config_opponent_and_pending_reset(void)
{
    setup(); begin(); TARGET->x8_spawnNum++;
    assert(!update()); assert(FP->cpu.rtrigger == 0);
    setup(); begin(); FP->cpu.xC = 3;
    assert(!update()); assert(FP->cpu.rtrigger == 0);
    setup(); begin(); contact(); assert(!update()); suspend(); assert(!ShowboatDefense_TakePerfect(FP));
    setup(); begin(); contact(); assert(!update()); ShowboatDefense_ResetSlot(0);
    assert(!ShowboatDefense_TakePerfect(FP));
    setup(); begin(); contact(); assert(!update()); TARGET->x8_spawnNum++;
    assert(!ShowboatDefense_TakePerfect(FP));
    setup(); begin(); contact(); assert(!update()); FP->cpu.level = 8;
    assert(ShowboatDefense_GetAction(FP) == 0 && !ShowboatDefense_TakePerfect(FP));
    setup(); begin(); primary[1] = &obj[2]; player_state[1] = 0;
    player_state[2] = 2; primary[2] = &obj[2];
    assert(!update_target(&f[2])); assert(FP->cpu.rtrigger == 0);
}
static void all_six_slots_and_retries(void)
{
    int slot, i;
    setup(); begin(); contact(); assert(!update());
    /* Resetting another slot does not erase our pending event. */
    for (slot = 1; slot < 6; ++slot) { ShowboatDefense_ResetSlot(slot); }
    assert(ShowboatDefense_TakePerfect(FP));
    FP->x2219_b5 = 0; FP->x221C_b2 = 0; FP->motion_id = ftCo_MS_Wait;
    FP->cpu.buttons = 0; FP->cpu.rtrigger = 0; sample();
    assert(update()); vm(); sample(); contact(); assert(!update());
    assert(ShowboatDefense_TakePerfect(FP)); assert(!ShowboatDefense_TakePerfect(FP));
    /* A failed/no-contact attempt DOES retain its bounded retry. */
    setup(); begin(); shield(); FP->cpu.xF8_b12 = 0; assert(!update());
    FP->motion_id = ftCo_MS_Wait; FP->cpu.xF8_b12 = 1;
    FP->cpu.buttons = 0; FP->cpu.rtrigger = 0; sample();
    for (i = 0; i < 12; ++i) { assert(!update()); }
    assert(update());
    /* Same pointer, different spawn cannot consume old event. */
    setup(); begin(); contact(); assert(!update()); FP->x8_spawnNum++;
    assert(!ShowboatDefense_TakePerfect(FP));
    for (slot = 0; slot < 6; ++slot) {
        setup();
        if (slot == 1) { TARGET->player_id = 0; primary[0] = &obj[1]; }
        if (slot != 0) { player_state[0] = slot == 1 ? 2 : 0; }
        FP->player_id = slot; player_state[slot] = 2; primary[slot] = &obj[0];
        assert(update()); suspend(); assert(FP->cpu.rtrigger == 0);
    }
}

static void same_pointer_respawn_cleanup(void)
{
    int how, replaced;
    for (how = 0; how < 2; ++how) {
        for (replaced = 0; replaced < 2; ++replaced) {
            Fighter before;
            setup(); begin(); FP->x8_spawnNum++;
            FP->cpu.x18 = 4; FP->cpu.xA4 = 17;
            FP->cpu.buttons |= HSD_PAD_A | HSD_PAD_L;
            FP->cpu.ltrigger = 87; FP->cpu.lstick.x = 73;
            if (replaced) { FP->cpu.buffer[0] = CpuCmd_PressA; }
            before = *FP;
            assert(ShowboatDefense_GetAction(FP) == 0);
            if (how) { assert(!update()); } else { suspend(); }
            if (replaced) { assert(memcmp(&before, FP, sizeof(before)) == 0); }
            else {
                assert(FP->cpu.csP == NULL && FP->cpu.write_pos == FP->cpu.buffer);
                assert(FP->cpu.buttons == (HSD_PAD_A | HSD_PAD_L));
                assert(FP->cpu.rtrigger == 0 && FP->cpu.ltrigger == 87);
                assert(FP->cpu.x18 == 4 && FP->cpu.xA4 == 17 && FP->cpu.lstick.x == 73);
            }
            assert(!ShowboatDefense_TakePerfect(FP));
        }
    }
    /* A different live allocation must never authorize cleanup of this one,
     * even if its VM is a byte-for-byte copy. Saved owner is only a token. */
    setup(); begin();
    f[2] = *FP; f[2].gobj = &obj[2]; primary[0] = &obj[2];
    f[2].cpu.csP = f[2].cpu.buffer + 11;
    f[2].cpu.write_pos = f[2].cpu.buffer + 13;
    { Fighter before = f[2];
      ShowboatDefense_Suspend(&f[2]);
      assert(!ShowboatDefense_Update(&f[2], TARGET));
      assert(memcmp(&before, &f[2], sizeof(before)) == 0); }
}
static void unexecuted_and_completed_vm_do_not_own_R(void)
{
    int completed, how, i;
    for (completed = 0; completed < 2; ++completed) {
        for (how = 0; how < 3; ++how) {
            setup(); assert(update());
            if (completed) { for (i = 0; i <= 10; ++i) { vm(); sample(); } }
            /* R belongs to a later writer, not the unexecuted PressR or the
             * completed ReleaseR. Old exact buffer may still be discarded. */
            FP->cpu.buttons = HSD_PAD_R | HSD_PAD_A; FP->cpu.rtrigger = 255;
            FP->cpu.x18 = 4; FP->cpu.xA4 = 42;
            if (how == 2) { FP->x8_spawnNum++; }
            if (how == 0) { suspend(); } else { assert(!update()); }
            assert(FP->cpu.buttons == (HSD_PAD_R | HSD_PAD_A));
            assert(FP->cpu.rtrigger == 255 && FP->cpu.x18 == 4 && FP->cpu.xA4 == 42);
            assert(FP->cpu.csP == NULL && FP->cpu.write_pos == FP->cpu.buffer);
        }
    }
}
static void perfect_toast_expires_without_recredit(void)
{
    int i;
    setup(); begin(); contact(); assert(!update());
    assert(ShowboatDefense_TakePerfect(FP));
    for (i = 1; i < 30; ++i) {
        assert(!update()); assert(ShowboatDefense_GetAction(FP) == 11);
        assert(!ShowboatDefense_TakePerfect(FP));
    }
    for (i = 0; i < 60; ++i) {
        assert(!update()); assert(ShowboatDefense_GetAction(FP) == 0);
        assert(!ShowboatDefense_TakePerfect(FP));
    }
}
static void expired_window_contact_marker(void)
{
    setup(); begin(); shield(); FP->mv.co.guard.x18 = 0;
    contact();
    /* Exercise observation after animation resumes (proc1 precedes CPU proc2).
     * This is callback ordering, not a simulated hitlag-duration proof. */
    FP->x2219_b5 = 0;
    ftCo_80093BC0(FP->gobj); /* native expiry does NOT erase contact */
    assert(!FP->x221C_b2 && FP->mv.co.guard.x1C == 32);
    assert(!update()); assert(ShowboatDefense_TakePerfect(FP));
    setup(); begin(); shield(); FP->mv.co.guard.x18 = 0;
    ftCo_80093BC0(FP->gobj); FP->motion_id = ftCo_MS_GuardSetOff;
    FP->mv.co.guard.x10 = 0; /* expiry/ordinary contact alone has no marker */
    ftColl_80076CBC(TARGET, &TARGET->x914[0], FP);
    assert(FP->mv.co.guard.x1C == 0);
    assert(!update()); assert(!ShowboatDefense_TakePerfect(FP));
}

static void lost_controller_hold_yields_without_retap(void)
{
    int change, marker;
    for (change = 0; change < 4; ++change) {
        for (marker = 0; marker < 2; ++marker) {
            u32 buttons; u8 trigger;
            setup(); begin(); shield();
            if (marker) { contact(); }
            switch (change) {
            case 0: FP->cpu.buttons &= ~HSD_PAD_R; break;
            case 1: FP->cpu.rtrigger = 127; break;
            case 2: FP->input.held_buttons[0] = 0; break;
            case 3: FP->input.triggers[0] = 0; break;
            }
            buttons = FP->cpu.buttons; trigger = FP->cpu.rtrigger;
            assert(!update()); assert(!ShowboatDefense_TakePerfect(FP));
            assert(FP->cpu.buttons == buttons && FP->cpu.rtrigger == trigger);
            assert(FP->cpu.csP == NULL && FP->cpu.write_pos == FP->cpu.buffer);
        }
    }
}
static void native_new_selection_keeps_R(void)
{
    Fighter before;
    setup(); begin(); shield();
    ftCo_800B4A78(FP); /* native arbitration ends old VM, not old Fighter sample */
    FP->cpu.x18 = 7;
    before = *FP; assert(!update());
    assert(memcmp(&before, FP, sizeof(before)) == 0);
    FP->cpu.xF0 = NULL; native_defense(1); /* real native block, not roll */
    assert(FP->cpu.rtrigger == 255 && (FP->cpu.buttons & HSD_PAD_R));
    assert(!(FP->input.released_buttons & HSD_PAD_R));
    before = *FP; suspend(); assert(memcmp(&before, FP, sizeof(before)) == 0);
    /* Even if a native builder restores exactly the old R value, a replaced
     * byte/cursor stream is native-owned. Update AND Suspend leave it alone. */
    setup(); begin(); shield();
    ftCo_800B4A78(FP); FP->cpu.x18 = 7; FP->cpu.xF0 = NULL;
    native_defense(1); before = *FP;
    assert(!update()); suspend(); assert(memcmp(&before, FP, sizeof(before)) == 0);
    /* No sidecar yet: fresh-empty selection while native R remains held. */
    setup(); FP->cpu.buttons = HSD_PAD_R; FP->cpu.rtrigger = 255;
    reject(); assert(FP->cpu.rtrigger == 255);
}
static void new_attempt_discards_unconsumed_old_credit(void)
{
    setup(); begin(); contact(); assert(!update()); /* deliberately do not consume */
    assert(!update()); /* still shieldstunned: zero success retry is NOT a retap */
    FP->motion_id = ftCo_MS_Wait; FP->x2219_b5 = 0; FP->x221C_b2 = 0;
    assert(!update()); /* even actionable Wait cannot refresh while holding R */
    FP->cpu.buttons = 0; FP->cpu.rtrigger = 0; sample();
    /* Explicit naturally released/actionable observations suffice: no extra
     * successful-attempt timer. New onset discards unconsumed old credit. */
    assert(update()); assert(!ShowboatDefense_TakePerfect(FP));
    vm(); sample(); contact(); assert(!update());
    assert(ShowboatDefense_TakePerfect(FP)); assert(!ShowboatDefense_TakePerfect(FP));
}
static void forecast_matches_native_BB104(void)
{
    int x, y, dx;
    for (x = -45; x <= 45; x += 5) {
        for (y = 0; y <= 30; y += 5) {
            for (dx = -8; dx <= 8; dx += 2) {
                Vec3 body = { 0, 10, 0 }; bool native;
                setup();
                TARGET->x914[0].x4C = (Vec3) { x, y, 0 };
                TARGET->x914[0].x58 = (Vec3) { x-dx, y, 0 };
                native = ftCo_800BB104(FP, TARGET, &body, 10);
                assert(update() == native);
            }
        }
    }
}

#define CASE(name) { #name, name }
static const struct { const char* name; void (*run)(void); } cases[] = {
    CASE(fresh_press_and_bounded_hold),
    CASE(fresh_empty_only),
    CASE(released_sample_and_no_retap),
    CASE(eligibility_and_live_identity),
    CASE(exclusions),
    CASE(geometry_and_capsules),
    CASE(handoff_no_manufactured_drop),
    CASE(acknowledge_and_forced_handoff),
    CASE(contact_marker_and_dedup),
    CASE(ordinary_block_and_hitlag),
    CASE(native_windows_are_not_contact),
    CASE(old_vm_priority_and_A4),
    CASE(replacement_and_cursor_ownership),
    CASE(suspension_reset_and_abandoned_tail),
    CASE(config_opponent_and_pending_reset),
    CASE(all_six_slots_and_retries),
    CASE(same_pointer_respawn_cleanup),
    CASE(unexecuted_and_completed_vm_do_not_own_R),
    CASE(perfect_toast_expires_without_recredit),
    CASE(expired_window_contact_marker),
    CASE(lost_controller_hold_yields_without_retap),
    CASE(native_new_selection_keeps_R),
    CASE(new_attempt_discards_unconsumed_old_credit),
    CASE(forecast_matches_native_BB104),
};
int main(int argc, char** argv)
{
    size_t i; assert(argc == 2);
    for (i = 0; i < sizeof(cases)/sizeof(*cases); ++i) {
        if (!strcmp(argv[1], cases[i].name)) {
            cases[i].run(); printf("PASS %s\n", argv[1]); return 0;
        }
    }
    return 2;
}
