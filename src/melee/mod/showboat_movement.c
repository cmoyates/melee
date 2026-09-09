/* Controller-only Falcon wavedash. No Enter/CheckInput calls, input-timer
 * writes, or gameplay-state writes. Native KneeBend/Jump/EscapeAir/Landing
 * own all motion and the unmodified p_ftCommonData->x344 landing lag (10).
 * Geometry/threat predictions are conservative vetoes, NOT hit guarantees. */
#include "showboat_movement.h"

#include <melee/ft/fighter.h>
#include <melee/ft/ftanim.h>
#include <melee/ft/ftcoll.h>
#include <melee/ft/ftcmdscript.h>
#include <melee/ft/kinds/ftCommon/ftCo_0A01.h>
#include <melee/ft/types.h>
#include <melee/gr/stage.h>
#include <melee/mp/mplib.h>
#include <melee/pl/player.h>
#include <sysdolphin/baselib/gobj.h>
#include <dolphin/os.h>
#include <math.h>
#include <string.h>

#define SM_SLOTS 6
#define SM_WDASH 9
#define SM_SCRIPT_MAX 24
#define SM_BUDGET 18
#define SM_RETRY 30
#define SM_SWEEP 3
#define SM_ENTRY_RESERVE 40.0f
#define SM_RESERVE 22.0f
#define SM_DEFENSE (HSD_PAD_L | HSD_PAD_R | HSD_PAD_Z | HSD_PAD_LR)
#define SM_CONFLICT (SM_DEFENSE | HSD_PAD_A | HSD_PAD_B | HSD_PAD_XY | HSD_PAD_DPADUP)

typedef enum {
    SM_IDLE, SM_NEUTRAL, SM_X, SM_SQUAT, SM_L, SM_AIRDODGE
} SM_Phase;

typedef struct {
    Fighter* owner; /* Identity tokens only: never dereference saved pointers. */
    Fighter* target;
    s32 spawn, target_spawn;
    SM_Phase phase;
    int age, phase_age, cooldown, direction, toward;
    int floor, stage, squat_limit;
    float left, right, floor_y, facing;
    int priority, script_size, resume_offset;
    s8 script[SM_SCRIPT_MAX];
} SM_State;

static SM_State sm_states[SM_SLOTS];

static float SM_Abs(float x) { return x < 0.0f ? -x : x; }
static bool SM_Range(float x, float lo, float hi)
{
    return x >= lo && x <= hi; /* Also reject NaN. */
}

static void SM_Log(Fighter* fp, char* reason)
{
#if SHOWBOAT_AI_DEBUG
    OSReport("SHOWBOAT MOVEMENT P%d WDASH: %s ms=%d x=%.2f y=%.2f "
             "ground-v=%.2f air-vx=%.2f\n", fp->player_id + 1, reason,
             fp->motion_id, fp->cur_pos.x, fp->cur_pos.y, fp->gr_vel,
             fp->self_vel.x);
#else
    (void) fp;
    (void) reason;
#endif
}

void ShowboatMovement_ResetSlot(int slot)
{
    if (slot >= 0 && slot < SM_SLOTS) {
        memset(&sm_states[slot], 0, sizeof(SM_State));
    }
}

static SM_State* SM_StateFor(Fighter* fp)
{
    SM_State* s;
    if (fp == NULL || fp->player_id >= SM_SLOTS) { return NULL; }
    s = &sm_states[fp->player_id];
    if (s->owner != fp || s->spawn != fp->x8_spawnNum) {
        ShowboatMovement_ResetSlot(fp->player_id);
        s->owner = fp;
        s->spawn = fp->x8_spawnNum;
    }
    return s;
}

static bool SM_ScriptMatches(Fighter* fp, SM_State* s)
{
    /* A fresh attack OR priority can coexist with our OLD VM. Cleanup owns
     * these exact bytes/cursors, not the new decision; preserve A4 and x18.
     * Continuation separately requires the original priority. */
    return s->script_size > 0 && s->script_size <= SM_SCRIPT_MAX &&
           s->script_size <= (int) sizeof(fp->cpu.buffer) &&
           s->resume_offset > 0 && s->resume_offset < s->script_size &&
           fp->cpu.write_pos == fp->cpu.buffer + s->script_size &&
           memcmp(fp->cpu.buffer, s->script, (size_t) s->script_size) == 0 &&
           ((fp->cpu.csP == fp->cpu.buffer && fp->cpu.command_duration == 1) ||
            (fp->cpu.csP == fp->cpu.buffer + s->resume_offset &&
             fp->cpu.command_duration == 1) ||
            (fp->cpu.csP == NULL && fp->cpu.command_duration == 0));
}

static bool SM_Sampled(Fighter* fp, SM_State* s)
{
    return fp->cpu.xA4 == 0 && fp->cpu.x18 == s->priority &&
           SM_ScriptMatches(fp, s) &&
           fp->cpu.csP == fp->cpu.buffer + s->resume_offset &&
           fp->cpu.command_duration == 1;
}

static void SM_Stop(Fighter* fp, SM_State* s, bool success, char* reason)
{
    if (s->phase == SM_IDLE) { return; }
    if (SM_ScriptMatches(fp, s)) {
        int selected = fp->cpu.xA4;
        ftCo_800B4A78(fp);
        fp->cpu.xA4 = selected;
    }
    SM_Log(fp, reason);
    s->phase = SM_IDLE;
    s->script_size = s->resume_offset = 0;
    s->cooldown = success ? 0 : SM_RETRY;
}

void ShowboatMovement_Suspend(Fighter* fp)
{
    SM_State* s;
    if (fp == NULL || fp->player_id >= SM_SLOTS) { return; }
    s = &sm_states[fp->player_id];
    if (s->owner == fp && s->spawn == fp->x8_spawnNum) {
        SM_Stop(fp, s, false, "suspend");
    }
}

static bool SM_LowPriority(Fighter* fp)
{
    /* Strict allowlist, including retakes. Defense 7, recovery 4, grab 9,
     * attack 2/3/8, damage, ledges and unknown priorities ALWAYS win. */
    return (fp->cpu.x18 == 1 || fp->cpu.x18 == 10) && fp->cpu.xA4 == 0;
}

static bool SM_ClearedVM(Fighter* fp)
{
    /* Native arbitration can clear locomotion at a jump transition. Retake
     * ONLY an empty/reset VM, never a replacement (even at priority 1/10).
     * A consumed release tail has write_pos at its end, NOT at buffer. */
    return SM_LowPriority(fp) && fp->cpu.csP == NULL &&
           fp->cpu.command_duration == 0 && fp->cpu.write_pos == fp->cpu.buffer &&
           fp->cpu.buttons == 0 && fp->cpu.lstick.x == 0 &&
           fp->cpu.lstick.y == 0 && fp->cpu.cstick.x == 0 &&
           fp->cpu.cstick.y == 0 && fp->cpu.ltrigger == 0 && fp->cpu.rtrigger == 0;
}

static bool SM_MundaneVM(Fighter* fp)
{
    int i, cursor = -1, end = -1, op, args;
    if (fp->cpu.csP == NULL && fp->cpu.command_duration == 0) { return true; }
    if (fp->cpu.command_duration == 0) { return false; }
    /* Admit active locomotion, not a queued attack whose button has not yet
     * been sampled. Find cursors by equality (no subtraction of alien pointers)
     * and decode only the bounded REMAINING bytecode. Never execute it here. */
    for (i = 0; i <= (int) sizeof(fp->cpu.buffer); ++i) {
        if (fp->cpu.csP == fp->cpu.buffer + i) { cursor = i; }
        if (fp->cpu.write_pos == fp->cpu.buffer + i) { end = i; }
    }
    if (cursor < 0 || cursor >= end) { return false; }
    while (cursor < end) {
        op = (u8) fp->cpu.buffer[cursor++];
        if (op == CpuCmd_Done) { return true; }
        switch (op) {
        case CpuCmd_ReleaseA: case CpuCmd_ReleaseB:
        case CpuCmd_ReleaseX: case CpuCmd_ReleaseY:
        case CpuCmd_ReleaseR: case CpuCmd_ReleaseL:
        case CpuCmd_ReleaseZ: case CpuCmd_ReleaseUp:
        case CpuCmd_ReleaseAll:
            args = 0;
            break;
        case CpuCmd_SetLstickX: case CpuCmd_SetLstickY:
        case CpuCmd_WaitFor: case CpuCmd_WaitIfMotionId:
        case CpuCmd_LstickTowardDestination:
        case CpuCmd_LstickXTowardDestination: case CpuCmd_LstickXForward:
        case CpuCmd_LstickTowardFighter: case CpuCmd_LstickXTowardFighter:
            args = 1;
            break;
        case CpuCmd_LstickTowardDestinationClamped:
        case CpuCmd_LstickXTowardDestinationClamped:
        case CpuCmd_LstickForwardClamped:
            args = 2;
            break;
        case CpuCmd_SetCstickX: case CpuCmd_SetCstickY:
        case CpuCmd_SetRtrigger: case CpuCmd_SetLtrigger:
            if (cursor >= end || fp->cpu.buffer[cursor] != 0) { return false; }
            args = 1;
            break;
        default:
            return false; /* Presses, repeats, priority writes, unknown opcodes. */
        }
        if (cursor + args > end) { return false; }
        cursor += args;
    }
    return false;
}

static bool SM_Unavailable(Fighter* fp)
{
    return fp->gobj == NULL || fp->x221F_b3 || fp->x2219_b5 || fp->x221A_b3 ||
           fp->x2224_b2 || fp->x221D_b4 || fp->x221C_b6 ||
           fp->victim_gobj != NULL || fp->x1A5C != NULL ||
           fp->item_gobj != NULL || fp->motion_id < ftCo_MS_Wait ||
           (fp->motion_id >= ftCo_MS_Entry && fp->motion_id <= ftCo_MS_EntryEnd);
}

static bool SM_Eligible(Fighter* fp, Fighter* target)
{
    /* Main owns singles/team policy. Recheck live primary identities here;
     * reject a partner BEFORE sidecar use by callers, never dereference owner. */
    return fp->kind == FTKIND_CAPTAIN && fp->cpu.level == 9 && fp->cpu.xC == 4 &&
           ftCo_800A2040(fp) && Player_GetEntity(fp->player_id) == fp->gobj &&
           target != NULL && target != fp && target->player_id < SM_SLOTS &&
           target->player_id != fp->player_id &&
           Player_GetEntity(target->player_id) == target->gobj &&
           !SM_Unavailable(fp) && !SM_Unavailable(target) &&
           HSD_GObj_Entities->items == NULL;
}

static bool SM_JumpGround(Fighter* fp)
{
    /* Verified IASA: Wait/Walk -> Jump_CheckInput; Dash/Run/RunBrake ->
     * fn_800CAF78. No Turn/TurnRun, crouch, teeter, landing or OOS starts. */
    return fp->ground_or_air == GA_Ground &&
           ((fp->motion_id >= ftCo_MS_Wait && fp->motion_id <= ftCo_MS_WalkFast) ||
            fp->motion_id == ftCo_MS_Dash || fp->motion_id == ftCo_MS_Run ||
            fp->motion_id == ftCo_MS_RunBrake);
}

static bool SM_ButtonsClear(Fighter* fp, u32 allowed)
{
    return !(fp->input.held_buttons[0] & (SM_CONFLICT & ~allowed)) &&
           !(fp->cpu.buttons & (SM_CONFLICT & ~allowed)) &&
           ftCo_GetCpuLTrigger(fp) <= p_ftCommonData->analog_shoulder_deadzone &&
           ftCo_GetCpuRTrigger(fp) <= p_ftCommonData->analog_shoulder_deadzone &&
           fp->input.cstick[0].x == 0.0f && fp->input.cstick[0].y == 0.0f &&
           fp->cpu.cstick.x == 0 && fp->cpu.cstick.y == 0;
}

static bool SM_NeutralObserved(Fighter* fp)
{
    return SM_ButtonsClear(fp, 0) && fp->input.lstick[0].x == 0.0f &&
           fp->input.lstick[0].y == 0.0f && fp->input.triggers[0] == 0.0f;
}

static bool SM_NormalMotion(Fighter* fp, bool self)
{
    float limit = self ? fp->co_attrs.dash_max_velocity + 0.25f : 3.5f;
    return SM_Range(limit, 0.5f, 4.0f) &&
           SM_Range(fp->cur_pos.x, -250.0f, 250.0f) &&
           SM_Range(fp->cur_pos.y, -10.0f, 100.0f) &&
           SM_Range(fp->cur_pos.z, -1.0f, 1.0f) &&
           SM_Range(fp->self_vel.x, -limit, limit) &&
           SM_Range(fp->gr_vel, -limit, limit) &&
           SM_Range(fp->pos_delta.x, -limit - 0.5f, limit + 0.5f) &&
           SM_Range(fp->self_vel.y, 0.0f, self ? 6.0f : 0.25f) &&
           SM_Range(fp->pos_delta.y, -0.25f, 0.25f) &&
           fp->x8c_kb_vel.x == 0.0f && fp->x8c_kb_vel.y == 0.0f &&
           fp->x98_atk_shield_kb.x == 0.0f && fp->x98_atk_shield_kb.y == 0.0f &&
           fp->x74_anim_vel.x == 0.0f && fp->x74_anim_vel.y == 0.0f &&
           !fp->x2228_b2 && !fp->x2222_b6 && !fp->dmg.x1948 &&
           fp->x1064_thrownHitbox.owner == NULL;
}

static bool SM_Constants(Fighter* fp)
{
    return p_ftCommonData != NULL &&
           SM_Range(fp->co_attrs.jump_startup_time, 2.0f, 8.0f) &&
           SM_Range(fp->co_attrs.hop_v_initial_velocity, 0.5f, 6.0f) &&
           SM_Range(fp->co_attrs.jump_v_initial_velocity, 0.5f, 6.0f) &&
           SM_Range(fp->co_attrs.ground_friction, 0.01f, 1.0f) &&
           SM_Range(p_ftCommonData->escapeair_force, 1.0f, 5.0f) &&
           SM_Range(p_ftCommonData->escapeair_decay, 0.5f, 1.0f) &&
           SM_Range(p_ftCommonData->x344, 1.0f, 16.0f);
}

static bool SM_Runway(SM_State* s, float x)
{
    /* Reserve this margin even AFTER the full conservative slide projection.
     * Admission separately requires 40. Applying 40 again at the projected end
     * needlessly prevents a center-stage Battlefield wavedash. */
    return x - s->left >= SM_RESERVE && s->right - x >= SM_RESERVE;
}

static bool SM_FloorQuery(Fighter* fp, float x, float y, int* line,
                           Vec3* contact)
{
    Vec3 normal;
    u32 flags;
    *line = -1;
    return mpCheckFloor(x, y + 2.0f, x, y - 2.0f, 0.0f, contact, line,
                        &flags, &normal, -1, fp->coll_data.joint_id_skip,
                        fp->coll_data.joint_id_only, NULL, NULL) &&
           *line >= 0 && normal.y > 0.999f && !(flags & LINE_FLAG_PLATFORM);
}

static bool SM_Floor(Fighter* fp, Fighter* target, SM_State* s, bool start)
{
    Vec3 contact, theirs, left, right, v0, v1;
    int line, target_line;
    int stage = Stage_80225194();
    if ((stage != St_Kind_Last && stage != St_Kind_Battle) ||
        (!start && stage != s->stage) || target->ground_or_air != GA_Ground ||
        !SM_FloorQuery(fp, fp->cur_pos.x, fp->cur_pos.y, &line, &contact) ||
        !SM_FloorQuery(target, target->cur_pos.x, target->cur_pos.y,
                       &target_line, &theirs) ||
        target->coll_data.floor.index != target_line ||
        !SM_Range(target->cur_pos.y - theirs.y, -0.25f, 0.25f) ||
        (fp->ground_or_air == GA_Ground && fp->coll_data.floor.index != line))
    {
        return false;
    }
    /* Live queried support, never a stale airborne floor index. BF/FD main
     * floors have a wide middle segment and coplanar outer strips. Reserve
     * against the connected chain's ledges, but keep OUR dodge on its line. */
    mpFloorGetLeft(line, &left);
    mpFloorGetRight(line, &right);
    mpLineGetV0Pos(line, &v0);
    mpLineGetV1Pos(line, &v1);
    if (line != target_line) {
        Vec3 target_left, target_right, target_v0, target_v1;
        mpFloorGetLeft(target_line, &target_left);
        mpFloorGetRight(target_line, &target_right);
        mpLineGetV0Pos(target_line, &target_v0);
        mpLineGetV1Pos(target_line, &target_v1);
        /* A rival may stand on an outer strip, not an unrelated support. */
        if (target_left.x != left.x || target_left.y != left.y ||
            target_right.x != right.x || target_right.y != right.y ||
            !SM_Range(target_v0.y - contact.y, -0.1f, 0.1f) ||
            !SM_Range(target_v1.y - contact.y, -0.1f, 0.1f)) { return false; }
    }
    if (!SM_Range(right.x - left.x, 120.0f, 250.0f) ||
        !SM_Range(right.y - left.y, -0.1f, 0.1f) ||
        !SM_Range(v1.y - v0.y, -0.1f, 0.1f) ||
        !SM_Range(contact.y - left.y, -0.1f, 0.1f) ||
        !SM_Range(fp->cur_pos.y - contact.y, -0.25f, 1.0f) ||
        target->cur_pos.x <= left.x + 2.0f || target->cur_pos.x >= right.x - 2.0f)
    {
        return false;
    }
    if (start) {
        s->stage = stage;
        s->floor = line;
        s->floor_y = contact.y;
        s->left = left.x;
        s->right = right.x;
    } else if (line != s->floor || left.x != s->left || right.x != s->right ||
               contact.y != s->floor_y)
    {
        return false;
    }
    if (start && (fp->cur_pos.x - s->left < SM_ENTRY_RESERVE ||
                  s->right - fp->cur_pos.x < SM_ENTRY_RESERVE)) { return false; }
    return SM_Runway(s, fp->cur_pos.x);
}

/* Read-only equivalents of GetCpuLStickX/Y's asymmetric signed conversion
 * and ftCommon_8007D9D4's atan2f. Do NOT temporarily overwrite CPU/input fields
 * to ask the helpers about a future sample. Fighter preprocessing deadzones
 * are checked too. +90/127, -90/128, -64/128 => about 35 degrees DOWN. */
static bool SM_DodgeVelocity(int direction, float* vx, float* vy)
{
    float x = direction > 0 ? 90.0f / 127.0f : -90.0f / 128.0f;
    float y = -64.0f / 128.0f;
    float angle;
    if (!(SM_Abs(x) > p_ftCommonData->horizontal_stick_deadzone) ||
        !(SM_Abs(y) > p_ftCommonData->vertical_stick_deadzone) ||
        (SM_Abs(x) < p_ftCommonData->escapeair_deadzone.x &&
         SM_Abs(y) < p_ftCommonData->escapeair_deadzone.y)) { return false; }
    angle = atan2f(y, x);
    *vx = p_ftCommonData->escapeair_force * cosf(angle);
    *vy = p_ftCommonData->escapeair_force * sinf(angle);
    return SM_Range(*vy, -5.0f, -0.5f);
}

static bool SM_Committed(Fighter* target, float startup)
{
    /* Normal grounded attacks only, facing toward us checked by caller.
     * Late recovery/landing/damage is a punish, not an excuse to retreat.
     * Animation rate handles charges: frozen smash charge is not commitment. */
    return target->motion_id >= ftCo_MS_Attack11 &&
           target->motion_id <= ftCo_MS_AttackLw4 && !target->allow_interrupt &&
           target->frame_speed_mul > 0.0f && target->cur_anim_frame >= 2.0f &&
           target->x8A4_animBlendFrames == 0.0f &&
           (ftAnim_8006F484(target->gobj) - target->cur_anim_frame) /
                   target->frame_speed_mul >= startup + 2.0f;
}

static bool SM_TargetIdleMotion(Fighter* target)
{
    return SM_JumpGround(target) || target->motion_id == ftCo_MS_Turn ||
           target->motion_id == ftCo_MS_TurnRun ||
           (target->motion_id >= ftCo_MS_Squat &&
            target->motion_id <= ftCo_MS_SquatRv);
}

static bool SM_Opportunity(Fighter* fp, Fighter* target, SM_State* s, bool start)
{
    float gap, dx, vx, vy, coast, slide, horizon, closing;
    int toward;
    if (!SM_NormalMotion(fp, true) || !SM_NormalMotion(target, false) ||
        ftColl_8007B868(fp->gobj) != 0 || ftColl_8007B868(target->gobj) != 0 ||
        !(target->facing_dir == 1.0f || target->facing_dir == -1.0f) ||
        !(fp->facing_dir == 1.0f || fp->facing_dir == -1.0f) ||
        !SM_Floor(fp, target, s, start)) { return false; }
    dx = target->cur_pos.x - fp->cur_pos.x;
    toward = dx > 0.0f ? 1 : -1;
    gap = SM_Abs(dx);
    if (start) {
        s->facing = fp->facing_dir;
        s->toward = toward;
        if (SM_Range(gap, 65.0f, 110.0f) && SM_TargetIdleMotion(target)) {
            s->direction = toward;
        } else if (SM_Range(gap, 45.0f, 65.0f) &&
                   target->facing_dir == -toward &&
                   SM_Committed(target, fp->co_attrs.jump_startup_time)) {
            s->direction = -toward;
        } else { return false; }
    } else if (toward != s->toward) { return false; }
    /* Hysteresis tolerates ordinary neutral-frame coast after admission. */
    closing = -target->pos_delta.x * toward;
    if (s->direction == toward) {
        /* Do not chase a rapidly retreating rival with a slower wavedash. */
        if (!SM_TargetIdleMotion(target) || !SM_Range(gap, 55.0f, 114.0f) ||
            closing > 1.5f || closing < -1.0f) { return false; }
    } else if (!SM_Range(gap, 38.0f, 85.0f) || closing > 1.0f ||
               fp->gr_vel * toward > 0.5f ||
               target->facing_dir != -toward ||
               !SM_Committed(target, start ? fp->co_attrs.jump_startup_time : 0.0f))
    {
        return false;
    }
    if (!SM_DodgeVelocity(s->direction, &vx, &vy)) { return false; }
    /* No friction assumption needed for safety: bound coast at current speed,
     * then bound the whole native landing lag at undecayed dodge speed. This
     * leaves running to vanilla at long range and prevents overshooting into
     * the rival or the ledge. Target need not have OUR 40-unit reserve (doing
     * that would make the forward distance band impossible on Battlefield). */
    horizon = start || s->phase == SM_NEUTRAL ?
                  fp->co_attrs.jump_startup_time + 2.0f :
                  (s->phase == SM_X ? fp->co_attrs.jump_startup_time :
                   (s->phase == SM_SQUAT && fp->ground_or_air == GA_Ground ?
                        fp->co_attrs.jump_startup_time - fp->cur_anim_frame : 0.0f));
    if (horizon < 0.0f) { horizon = 0.0f; }
    coast = fp->gr_vel * horizon;
    slide = vx * (p_ftCommonData->x344 + SM_SWEEP);
    /* Coast is an interval between zero and this maximum, not guaranteed
     * displacement. Never credit beneficial coast that friction can remove. */
    if (!SM_Runway(s, fp->cur_pos.x + coast) ||
        !SM_Runway(s, fp->cur_pos.x + slide) ||
        !SM_Runway(s, fp->cur_pos.x + coast + slide)) { return false; }
    coast *= toward;
    if (coast < 0.0f) { coast = 0.0f; }
    if (closing < 0.0f) { closing = 0.0f; }
    return gap - coast - (s->direction == toward ? SM_Abs(slide) : 0.0f) -
                     closing * (horizon + p_ftCommonData->x344 + SM_SWEEP) >=
           (s->direction == toward ? 28.0f : 30.0f);
}

static bool SM_Sweep(Fighter* fp, SM_State* s)
{
    Vec3 contact, normal;
    u32 flags;
    float vx, vy, nx, ny;
    float x = fp->coll_data.cur_pos.x + fp->coll_data.ecb.bottom.x;
    float y = fp->coll_data.cur_pos.y + fp->coll_data.ecb.bottom.y;
    int i, line;
    if (!SM_DodgeVelocity(s->direction, &vx, &vy) ||
        !SM_Range(x - fp->cur_pos.x, -6.0f, 6.0f) ||
        !SM_Range(y - fp->cur_pos.y, -0.25f, 6.0f) ||
        !SM_Range(y - s->floor_y, 0.0f, 6.0f)) { return false; }
    for (i = 0; i < SM_SWEEP; ++i) {
        /* EscapeAir_Phys decays BEFORE movement, including its first frame.
         * No existing upward jump velocity is added: native dodge replaces it.
         * Current ECB/cur_pos, real sweep, same stored static main line. */
        vx *= p_ftCommonData->escapeair_decay;
        vy *= p_ftCommonData->escapeair_decay;
        nx = x + vx;
        ny = y + vy;
        if (!SM_Runway(s, nx)) { return false; }
        line = -1;
        if (mpCheckFloor(x, y, nx, ny, 0.0f, &contact, &line, &flags, &normal,
                         fp->coll_data.floor_skip, fp->coll_data.joint_id_skip,
                         fp->coll_data.joint_id_only, NULL, NULL))
        {
            return line == s->floor && normal.y > 0.999f &&
                   !(flags & LINE_FLAG_PLATFORM) &&
                   SM_Range(contact.y - s->floor_y, -0.1f, 0.1f) &&
                   SM_Runway(s, contact.x);
        }
        x = nx;
        y = ny;
    }
    return false;
}

static void SM_ReleaseCommands(Fighter* fp)
{
    ftCo_800B463C(fp, CpuCmd_ReleaseX);
    ftCo_800B463C(fp, CpuCmd_ReleaseY);
    ftCo_800B463C(fp, CpuCmd_ReleaseL);
    ftCo_800B46B8(fp, CpuCmd_SetLstickX, 0);
    ftCo_800B46B8(fp, CpuCmd_SetLstickY, 0);
}

static bool SM_Input(Fighter* fp, SM_State* s, SM_Phase phase)
{
    /* At most 22 bytes, checked BEFORE the first write. All paths have a
     * one-sample wait and explicit X/Y/L/stick release tail, even if Update
     * ceases. No R pulse: PressR also writes an analog trigger; L is digital.
     * EscapeAir_CheckInput checks pressed L/R, not merely synthetic LR. */
    if (SM_SCRIPT_MAX > (int) sizeof(fp->cpu.buffer)) {
        SM_Stop(fp, s, false, "script buffer too small");
        return false;
    }
    ftCo_800B4A78(fp);
    SM_ReleaseCommands(fp);
    if (phase == SM_X) {
        ftCo_800B463C(fp, CpuCmd_PressX);
    } else if (phase == SM_L) {
        ftCo_800B46B8(fp, CpuCmd_SetLstickX, (u8) (s8) (s->direction * 90));
        ftCo_800B46B8(fp, CpuCmd_SetLstickY, (u8) (s8) -64);
        ftCo_800B463C(fp, CpuCmd_PressL);
    }
    ftCo_800B46B8(fp, CpuCmd_WaitFor, 1);
    s->resume_offset = fp->cpu.write_pos - fp->cpu.buffer;
    SM_ReleaseCommands(fp);
    ftCo_800B49F4(fp);
    s->priority = fp->cpu.x18;
    s->script_size = fp->cpu.write_pos - fp->cpu.buffer;
    memcpy(s->script, fp->cpu.buffer, (size_t) s->script_size);
    if (s->phase != phase) { s->phase_age = 0; }
    s->phase = phase;
    if (phase == SM_L) { SM_Log(fp, "first Jump; dodge sample queued"); }
    return true;
}

bool ShowboatMovement_Update(Fighter* fp, Fighter* target)
{
    SM_State* s;
    bool sampled, transition;
    /* A nonprimary Falcon must not erase the primary's slot sidecar. */
    if (fp == NULL || fp->player_id >= SM_SLOTS) { return false; }
    if (fp->gobj == NULL || Player_GetEntity(fp->player_id) != fp->gobj) {
        ShowboatMovement_Suspend(fp);
        return false;
    }
    s = SM_StateFor(fp);
    if (s->cooldown > 0) { --s->cooldown; }
    if (s->phase != SM_IDLE) {
        ++s->age;
        ++s->phase_age;
        /* Acceptance may clear/replace the VM or change native priority.
         * A direct same-frame LandingFallSpecial also acknowledges the dodge.
         * Never hold the controller through, shorten, or bypass landing lag. */
        if ((s->phase == SM_L || s->phase == SM_AIRDODGE) &&
            target != NULL && s->target == target &&
            s->target_spawn == target->x8_spawnNum && s->age <= SM_BUDGET &&
            fp->motion_id == ftCo_MS_LandingFallSpecial &&
            fp->ground_or_air == GA_Ground && fp->facing_dir == s->facing)
        {
            SM_Stop(fp, s, true, "landing acknowledged; release/yield");
            return false;
        }
    }
    if (!SM_Constants(fp) || !SM_Eligible(fp, target) || !SM_LowPriority(fp) ||
        (s->phase != SM_IDLE &&
         (s->target != target || s->target_spawn != target->x8_spawnNum ||
          fp->facing_dir != s->facing || s->age > SM_BUDGET)))
    {
        SM_Stop(fp, s, false, "eligibility/target/priority/budget");
        return false;
    }
    if (s->phase == SM_IDLE) {
        if (s->cooldown || !SM_JumpGround(fp) || !SM_ButtonsClear(fp, 0) ||
            !SM_MundaneVM(fp) || !SM_Opportunity(fp, target, s, true)) { return false; }
        s->target = target;
        s->target_spawn = target->x8_spawnNum;
        s->age = s->phase_age = 0;
        /* Positive bounded input (2..8), exact ceil without introducing a new
         * libm symbol absent from the retail link. This is only OUR timeout. */
        s->squat_limit = (int) fp->co_attrs.jump_startup_time;
        if ((float) s->squat_limit < fp->co_attrs.jump_startup_time) {
            ++s->squat_limit;
        }
        s->squat_limit += 2;
        SM_Log(fp, s->direction == s->toward ? "start forward; neutral first" :
                                                  "start committed-attack retreat");
        return SM_Input(fp, s, SM_NEUTRAL);
    }
    sampled = SM_Sampled(fp, s);
    if (s->phase == SM_L || s->phase == SM_AIRDODGE) {
        if (fp->ground_or_air != GA_Air || fp->motion_id != ftCo_MS_EscapeAir ||
            (!sampled && !SM_ClearedVM(fp)) ||
            (s->phase == SM_L && s->phase_age != 1) ||
            (s->phase == SM_AIRDODGE && s->phase_age > SM_SWEEP) ||
            !SM_ButtonsClear(fp, HSD_PAD_L | HSD_PAD_LR) ||
            ftColl_8007B868(target->gobj) != 0 ||
            (!SM_TargetIdleMotion(target) && !SM_Committed(target, 0.0f)) ||
            !SM_Floor(fp, target, s, false))
        {
            SM_Stop(fp, s, false, "dodge unconfirmed/replaced or floor lost");
            return false;
        }
        if (s->phase == SM_L) { SM_Log(fp, "EscapeAir acknowledged"); }
        return SM_Input(fp, s, SM_AIRDODGE);
    }
    transition = (s->phase == SM_X && fp->motion_id == ftCo_MS_KneeBend) ||
                 (s->phase == SM_SQUAT && fp->ground_or_air == GA_Air &&
                  (fp->motion_id == ftCo_MS_JumpF || fp->motion_id == ftCo_MS_JumpB));
    if ((!sampled && !(transition && SM_ClearedVM(fp))) ||
        !SM_ButtonsClear(fp, s->phase == SM_X ? HSD_PAD_X : 0) ||
        !SM_Opportunity(fp, target, s, false))
    {
        SM_Stop(fp, s, false, "missing sample/replacement/input/threat/floor");
        return false;
    }
    switch (s->phase) {
    case SM_NEUTRAL:
        if (s->phase_age == 1 && SM_NeutralObserved(fp) && SM_JumpGround(fp)) {
            return SM_Input(fp, s, SM_X);
        }
        break;
    case SM_X:
        if (s->phase_age == 1 && fp->ground_or_air == GA_Ground &&
            fp->motion_id == ftCo_MS_KneeBend &&
            fp->mv.co.kneebend.jump_input == JumpInput_XY &&
            (fp->input.pressed_buttons & HSD_PAD_X) &&
            (fp->input.held_buttons[0] & HSD_PAD_X) &&
            fp->input.lstick[0].x == 0.0f && fp->input.lstick[0].y == 0.0f)
        {
            SM_Log(fp, "KneeBend acknowledged; release BOTH jump buttons");
            return SM_Input(fp, s, SM_SQUAT);
        }
        break;
    case SM_SQUAT:
        if (!SM_NeutralObserved(fp) || s->phase_age > s->squat_limit) { break; }
        if (fp->ground_or_air == GA_Ground && fp->motion_id == ftCo_MS_KneeBend &&
            fp->mv.co.kneebend.jump_input == JumpInput_XY) {
            return SM_Input(fp, s, SM_SQUAT);
        }
        /* Fighter Anim runs BEFORE CPU/input, Phys AFTER it. On the FIRST
         * JumpF/B update x4 is still false and root has not risen. Requiring
         * x4==true here would deliberately miss the wavedash input window.
         * Never dodge from generic free air, a missed jump, or an old ascent. */
        if (fp->ground_or_air == GA_Air &&
            (fp->motion_id == ftCo_MS_JumpF || fp->motion_id == ftCo_MS_JumpB) &&
            !fp->mv.co.jump.x4 && fp->mv.co.jump.x0 &&
            fp->x1968_jumpsUsed == 1 &&
            SM_Range(fp->cur_anim_frame, 0.0f, 1.0f) &&
            SM_Range(fp->cur_pos.y - s->floor_y, -0.25f, 1.0f) &&
            SM_Range(fp->pos_delta.y, -0.25f, 0.25f) && SM_Sweep(fp, s))
        {
            return SM_Input(fp, s, SM_L);
        }
        break;
    default:
        break;
    }
    SM_Stop(fp, s, false, "failed transition/late jump; no repeated pulse");
    return false;
}

int ShowboatMovement_GetAction(Fighter* fp)
{
    SM_State* s;
    if (fp == NULL || fp->player_id >= SM_SLOTS) { return 0; }
    s = &sm_states[fp->player_id];
    return s->owner == fp && s->spawn == fp->x8_spawnNum && s->phase != SM_IDLE ?
               SM_WDASH : 0;
}
