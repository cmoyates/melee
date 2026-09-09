/* Controller-only competence. No fighter transitions or gameplay-state writes.
 * V2 converts existing free airtime only. Short-hop chasing, forced jumps,
 * DI, SDI and techs remain deferred/vanilla. Predictions are NOT hit guarantees. */
#include "showboat_combat.h"
#include "showboat_recorder.h"

#include <melee/ft/fighter.h>
#include <melee/ft/ftanim.h>
#include <melee/ft/ftcoll.h>
#include <melee/ft/ftcmdscript.h>
#include <melee/ft/kinds/ftCommon/ftCo_0A01.h>
#include <melee/ft/types.h>
#include <melee/mp/mplib.h>
#include <melee/gr/stage.h>
#include <dolphin/os.h>
#include <math.h>
#include <string.h>

#define SC_SLOTS 6
#define SC_GRAB 5
#define SC_KNEE 6
#define SC_UPAIR 7
#define SC_SCRIPT_MAX 13
#define SC_PREDICT_MAX 16 /* Knee 14 + neutral sample + timing reserve. */
#define SC_HITSTUN_RESERVE 2
#define SC_DEFENSE (HSD_PAD_L | HSD_PAD_R | HSD_PAD_Z | HSD_PAD_LR)
#define SC_CONFLICT (SC_DEFENSE | HSD_PAD_A | HSD_PAD_B | HSD_PAD_X | HSD_PAD_Y)

typedef struct {
    Fighter* owner; /* Identity tokens only; never dereference saved pointers. */
    Fighter* target;
    s32 spawn, target_spawn;
    int action, age, cooldown, lc_cooldown, log_cooldown;
    int priority, script_size, resume_offset;
    s8 script[SC_SCRIPT_MAX];
    bool analog_owned;
    u8 old_ltrigger;
} SC_State;

static SC_State sc_states[SC_SLOTS];

static float SC_Abs(float x) { return x < 0.0f ? -x : x; }

static void SC_Log(Fighter* fp, char* event)
{
#if SHOWBOAT_AI_DEBUG
    OSReport("SHOWBOAT COMBAT P%d: %s\n", fp->player_id + 1, event);
#else
    (void) fp;
    (void) event;
#endif
}

void ShowboatCombat_ResetSlot(int slot)
{
    if (slot >= 0 && slot < SC_SLOTS) {
        memset(&sc_states[slot], 0, sizeof(SC_State));
    }
}

static SC_State* SC_StateFor(Fighter* fp)
{
    SC_State* s;
    if (fp == NULL || fp->player_id >= SC_SLOTS) {
        return NULL;
    }
    s = &sc_states[fp->player_id];
    if (s->owner != fp || s->spawn != fp->x8_spawnNum) {
        ShowboatCombat_ResetSlot(fp->player_id);
        s->owner = fp;
        s->spawn = fp->x8_spawnNum;
    }
    return s;
}

static bool SC_Eligible(Fighter* fp)
{
    /* Main additionally verifies primary identity, singles and no active Nana. */
    return fp->kind == FTKIND_CAPTAIN && fp->cpu.level == 9 &&
           fp->cpu.xC == 4 && ftCo_800A2040(fp);
}

static bool SC_Unavailable(Fighter* fp)
{
    return fp->x221F_b3 || fp->x2219_b5 || fp->x221A_b3 ||
           fp->x2224_b2 || fp->x221D_b4 ||
           fp->victim_gobj != NULL || fp->x1A5C != NULL ||
           fp->motion_id < ftCo_MS_Wait ||
           (fp->motion_id >= ftCo_MS_Entry && fp->motion_id <= ftCo_MS_EntryEnd);
}

static bool SC_LowPriority(Fighter* fp)
{
    /* Explicit allowlist: recovery 4, defense 7, grab 9, damage 15/18,
     * ledges, items and all unknown scenarios retain vanilla ownership. */
    return fp->cpu.x18 == 1 || fp->cpu.x18 == 2 || fp->cpu.x18 == 3 ||
           fp->cpu.x18 == 8 || fp->cpu.x18 == 10;
}

static bool SC_TriggerHeld(Fighter* fp)
{
    return (fp->cpu.buttons & SC_DEFENSE) ||
           ftCo_GetCpuLTrigger(fp) > p_ftCommonData->analog_shoulder_deadzone ||
           ftCo_GetCpuRTrigger(fp) > p_ftCommonData->analog_shoulder_deadzone;
}

static void SC_RestoreAnalog(Fighter* fp, SC_State* s)
{
    /* Do not undo a new native write. Only the channel we borrowed is restored. */
    if (s->analog_owned && fp->cpu.ltrigger == 128) {
        fp->cpu.ltrigger = s->old_ltrigger;
    }
    s->analog_owned = false;
}

void ShowboatCombat_RestoreInput(Fighter* fp)
{
    SC_State* s;
    if (fp == NULL || fp->player_id >= SC_SLOTS) { return; }
    s = &sc_states[fp->player_id];
    /* Never dereference the saved owner (including on slot reuse/suspend). */
    if (s->owner == fp && s->spawn == fp->x8_spawnNum) {
        SC_RestoreAnalog(fp, s);
    }
}

static bool SC_ScriptMatches(Fighter* fp, SC_State* s)
{
    /* Store the actual WaitFor resume offset, not a guess based on size.
     * A new cached A4 can coexist with our OLD script: distinguish those so
     * cleanup can release our input without delaying/dropping the fresh attack. */
    return s->script_size > 0 && s->script_size <= SC_SCRIPT_MAX &&
           s->script_size <= (int) sizeof(fp->cpu.buffer) &&
           s->resume_offset > 0 && s->resume_offset < s->script_size &&
           fp->cpu.x18 == s->priority &&
           fp->cpu.write_pos == fp->cpu.buffer + s->script_size &&
           memcmp(fp->cpu.buffer, s->script, (size_t) s->script_size) == 0 &&
           ((fp->cpu.csP == fp->cpu.buffer && fp->cpu.command_duration == 1) ||
            (fp->cpu.csP == fp->cpu.buffer + s->resume_offset &&
             fp->cpu.command_duration == 1) ||
            (fp->cpu.csP == NULL && fp->cpu.command_duration == 0));
}

static bool SC_OurScript(Fighter* fp, SC_State* s)
{
    return fp->cpu.xA4 == 0 && SC_ScriptMatches(fp, s);
}

static void SC_Stop(Fighter* fp, SC_State* s, char* reason)
{
    if (s->action != 0) {
#if SHOWBOAT_AI_DEBUG
        OSReport("SHOWBOAT COMBAT P%d action %d: %s\n",
                 fp->player_id + 1, s->action, reason);
#else
        (void) reason;
#endif
        if (SC_ScriptMatches(fp, s)) {
            int selected = fp->cpu.xA4;
            ftCo_800B4A78(fp); /* releases only our old A/Z/stick script */
            fp->cpu.xA4 = selected; /* let native builder use its fresh attack */
        }
        /* Never clear a replacement native priority script/cached attack. */
        s->action = 0;
        s->script_size = 0;
        s->resume_offset = 0;
        s->cooldown = 45; /* Also bound retries after a late cancel/ack. */
    }
}

static bool SC_GrabOpportunity(Fighter* fp, Fighter* target, int frames)
{
    float dx, predicted;
    bool lag;
    if (target == NULL || target == fp || SC_Unavailable(target) ||
        fp->ground_or_air != GA_Ground || target->ground_or_air != GA_Ground ||
        fp->motion_id < ftCo_MS_Wait || fp->motion_id > ftCo_MS_WalkFast ||
        fp->item_gobj != NULL || target->item_gobj != NULL ||
        fp->coll_data.floor.index < 0 ||
        fp->coll_data.floor.index != target->coll_data.floor.index ||
        SC_Abs(fp->cur_pos.y - target->cur_pos.y) > 3.0f ||
        SC_Abs(fp->self_vel.x) > 0.5f || SC_Abs(target->pos_delta.x) > 0.5f ||
        ftColl_8007B868(fp->gobj) != 0 ||
        ftColl_8007B868(target->gobj) != 0)
    {
        /* Broad grab admission: target/state/items/support/motion/protection. */
        ShowboatRecorder_Reason(fp, SBR_COMBAT, SBR_PHYSICAL_OR_STATE);
        return false;
    }
    dx = (target->cur_pos.x - fp->cur_pos.x) * fp->facing_dir;
    predicted = dx + (target->pos_delta.x - fp->pos_delta.x) *
                         fp->facing_dir * frames;
    if (dx <= 0.0f || dx > 11.0f || predicted <= 0.0f || predicted > 11.0f) {
        ShowboatRecorder_Reason(fp, SBR_COMBAT, SBR_GEOMETRY_OR_WINDOW);
        return false;
    }
    if (target->motion_id == ftCo_MS_GuardOn ||
        target->motion_id == ftCo_MS_Guard ||
        target->motion_id == ftCo_MS_GuardSetOff ||
        target->motion_id == ftCo_MS_GuardReflect)
    {
        return true; /* Reactive shield grab, not a guarantee they keep guarding. */
    }
    /* Only read the damage union in compatible grounded damage states. */
    if (target->motion_id >= ftCo_MS_DamageHi1 &&
        target->motion_id <= ftCo_MS_DamageLw3)
    {
        ShowboatRecorder_Reason(fp, SBR_COMBAT, SBR_GEOMETRY_OR_WINDOW);
        return target->x221C_b6 && target->mv.co.damage.x0 >= frames;
    }
    ShowboatRecorder_Reason(fp, SBR_COMBAT, SBR_GEOMETRY_OR_WINDOW);
    lag = (target->motion_id >= ftCo_MS_LandingAirN &&
           target->motion_id <= ftCo_MS_LandingAirLw) ||
          (target->motion_id == ftCo_MS_LandingFallSpecial &&
           !target->mv.co.landing.allow_interrupt);
    /* LandingAir's actual animation rate already reflects L-cancelled lag.
     * No guessed per-character lag table or arbitrary elapsed-frame cutoff. */
    return lag && target->frame_speed_mul > 0.0f &&
           target->x8A4_animBlendFrames == 0.0f &&
           (ftAnim_8006F484(target->gobj) - target->cur_anim_frame) /
                   target->frame_speed_mul >= frames;
}

static bool SC_Range(float x, float lo, float hi)
{
    return x >= lo && x <= hi; /* Reject NaN as well as unbounded inputs. */
}

static bool SC_FreeAir(Fighter* fp)
{
    /* Contiguous common Jump/JumpAerial/Fall variants only, NOT DamageFall,
     * FallSpecial, aerial attacks, landing, jump squat or character specials. */
    return fp->ground_or_air == GA_Air &&
           fp->motion_id >= ftCo_MS_JumpF &&
           fp->motion_id <= ftCo_MS_FallAerialB &&
           /* Jump's initial Phys skips gravity once; wait for its actual flag,
            * not a guessed animation/input age, before predicting normally. */
           (fp->motion_id > ftCo_MS_JumpB || fp->mv.co.jump.x4);
}

static int SC_Startup(int action)
{
    return action == SC_KNEE ? 14 : 6;
}

static float SC_Decay(float v, float amount)
{
    if (v > amount) { return v - amount; }
    if (v < -amount) { return v + amount; }
    return 0.0f;
}

/* Read-only counterpart of common aerial drift; only +/-1 or neutral input.
 * After the one-frame stick pulse, bracket BOTH native drift extremes rather
 * than assuming vanilla will maintain our chosen drift until the hit. */
static float SC_Drift(Fighter* fp, float vx, int stick)
{
    float accel, limit;
    if (!stick) { return SC_Decay(vx, fp->co_attrs.aerial_friction); }
    accel = stick * (fp->co_attrs.air_drift_stick_mul +
                     fp->co_attrs.aerial_drift_base);
    limit = stick * fp->co_attrs.air_drift_max;
    if (vx * accel >= 0.0f) {
        if (stick > 0 && vx + accel > limit) {
            accel = -fp->co_attrs.aerial_friction;
            if (vx + accel < limit) { accel = limit - vx; }
            if (vx + accel > fp->co_attrs.air_max_horizontal_velocity) {
                accel = fp->co_attrs.air_max_horizontal_velocity - vx;
            }
        } else if (stick < 0 && vx + accel < limit) {
            accel = fp->co_attrs.aerial_friction;
            if (vx + accel > limit) { accel = limit - vx; }
            if (vx + accel < -fp->co_attrs.air_max_horizontal_velocity) {
                accel = -fp->co_attrs.air_max_horizontal_velocity - vx;
            }
        }
    }
    return vx + accel;
}

static bool SC_Predictable(Fighter* fp)
{
    /* Exclude nonstandard displacement/KB paths rather than silently treating
     * them as ordinary gravity. pos_delta is a sanity veto, NOT our velocity. */
    return !fp->x2228_b2 && !fp->x2222_b6 && !fp->dmg.x1948 &&
           fp->x1064_thrownHitbox.owner == NULL &&
           fp->x98_atk_shield_kb.x == 0.0f && fp->x98_atk_shield_kb.y == 0.0f &&
           fp->x74_anim_vel.x == 0.0f && fp->x74_anim_vel.y == 0.0f &&
           SC_Range(fp->cur_pos.x, -1000.0f, 1000.0f) &&
           SC_Range(fp->cur_pos.y, -1000.0f, 1000.0f) &&
           SC_Range(fp->cur_pos.z, -1.0f, 1.0f) &&
           SC_Range(fp->self_vel.x, -10.0f, 10.0f) &&
           SC_Range(fp->self_vel.y, -10.0f, 10.0f) &&
           SC_Range(fp->x8c_kb_vel.x, -12.0f, 12.0f) &&
           SC_Range(fp->x8c_kb_vel.y, -12.0f, 12.0f) &&
           SC_Range(fp->pos_delta.x - fp->self_vel.x - fp->x8c_kb_vel.x,
                    -2.0f, 2.0f) &&
           SC_Range(fp->pos_delta.y - fp->self_vel.y - fp->x8c_kb_vel.y,
                    -2.0f, 2.0f) &&
           SC_Range(fp->co_attrs.gravity, 0.01f, 1.0f) &&
           SC_Range(fp->co_attrs.terminal_velocity, 0.1f, 10.0f) &&
           SC_Range(fp->co_attrs.fast_fall_velocity, 0.1f, 10.0f) &&
           SC_Range(fp->co_attrs.aerial_friction, 0.0f, 1.0f) &&
           SC_Range(fp->co_attrs.air_drift_stick_mul, 0.0f, 1.0f) &&
           SC_Range(fp->co_attrs.aerial_drift_base, 0.0f, 1.0f) &&
           SC_Range(fp->co_attrs.air_drift_max, 0.1f, 10.0f) &&
           SC_Range(fp->co_attrs.air_max_horizontal_velocity, 0.1f, 10.0f);
}

static bool SC_FloorBelow(Fighter* fp, Vec3* pos)
{
    Vec3 contact, normal, left, right;
    u32 flags;
    int line = -1;
    /* Real query, not a stale airborne coll_data.floor.index. Restrict callers
     * to static BF/FD geometry: no moving-floor extrapolation or stage hazards.
     * A signed 12-unit runway margin and <=90-unit drop at EVERY predicted step
     * are conservative onstage vetoes, not a full recovery planner. */
    if (!mpCheckFloor(pos->x, pos->y, pos->x, pos->y - 90.0f, 0.0f,
                      &contact, &line, &flags, &normal, -1,
                      fp->coll_data.joint_id_skip, fp->coll_data.joint_id_only,
                      NULL, NULL) || line < 0 || !(normal.y > 0.99f))
    {
        return false;
    }
    mpFloorGetLeft(line, &left);
    mpFloorGetRight(line, &right);
    return pos->x > left.x + 12.0f && pos->x < right.x - 12.0f &&
           SC_Range(right.y - left.y, -1.0f, 1.0f) &&
           pos->y > contact.y + 4.0f;
}

static bool SC_Project(Fighter* fp, int action, int delay, int steer,
                       int frames, Vec3* path)
{
    Vec3 contact, normal;
    u32 flags;
    int i, line, stick;
    float vx = fp->self_vel.x, vy = fp->self_vel.y;
    float kx = fp->x8c_kb_vel.x, ky = fp->x8c_kb_vel.y;
    float mag, scale, bx, by;
    if (frames < 1 || frames > SC_PREDICT_MAX || !SC_Predictable(fp)) {
        return false;
    }
    bx = fp->coll_data.cur_pos.x + fp->coll_data.ecb.bottom.x - fp->cur_pos.x;
    by = fp->coll_data.cur_pos.y + fp->coll_data.ecb.bottom.y - fp->cur_pos.y;
    if (!SC_Range(bx, -12.0f, 12.0f) || !SC_Range(by, -12.0f, 12.0f)) {
        return false;
    }
    path[0] = fp->cur_pos;
    if (!SC_FloorBelow(fp, &path[0])) { return false; }
    for (i = 1; i <= frames; ++i) {
        /* Target damage Phys uses normal gravity/friction, even if fall_fast
         * was set. Self preserves an ALREADY active fast fall; never starts it. */
        if (action && fp->fall_fast) {
            vy = -fp->co_attrs.fast_fall_velocity;
        } else {
            vy -= fp->co_attrs.gravity;
            if (vy < -fp->co_attrs.terminal_velocity) {
                vy = -fp->co_attrs.terminal_velocity;
            }
        }
        stick = 0;
        if (action && i == delay + 1 && action == SC_KNEE) {
            stick = fp->facing_dir > 0.0f ? 1 : -1;
        } else if (action && i > delay + 1) {
            stick = steer;
        }
        vx = SC_Drift(fp, vx, stick);
        mag = sqrtf(kx * kx + ky * ky);
        if (mag <= p_ftCommonData->x204_knockbackFrameDecay) {
            kx = ky = 0.0f;
        } else {
            scale = (mag - p_ftCommonData->x204_knockbackFrameDecay) / mag;
            kx *= scale;
            ky *= scale;
        }
        path[i] = path[i - 1];
        path[i].x += vx + kx;
        path[i].y += vy + ky;
        line = -1;
        /* Sweep the current ECB, INCLUDING the startup/reserve frames. Any
         * floor hit (even an ambiguous normal/line) invalidates an intercept.
         * Also veto a low root: attack ECB/pose can differ from the current one. */
        if (mpCheckFloor(path[i - 1].x + bx, path[i - 1].y + by,
                          path[i].x + bx, path[i].y + by, 0.0f,
                          &contact, &line, &flags, &normal,
                          fp->coll_data.floor_skip,
                          fp->coll_data.joint_id_skip,
                          fp->coll_data.joint_id_only, NULL, NULL) ||
            !SC_FloorBelow(fp, &path[i]))
        {
            return false;
        }
    }
    return true;
}

static bool SC_AirOpportunity(Fighter* fp, Fighter* target, int action,
                              int delay)
{
    Vec3 ours[SC_PREDICT_MAX + 1], theirs[SC_PREDICT_MAX + 1];
    int i, steer, hit = SC_Startup(action) + delay;
    float dx, dy;
    StKind stage = Stage_80225194();
    if ((stage != St_Kind_Battle && stage != St_Kind_Last) ||
        !SC_FreeAir(fp) || !fp->cpu.xFA_b5 ||
        target == NULL || target == fp || SC_Unavailable(target) ||
        target->ground_or_air != GA_Air || fp->item_gobj != NULL ||
        target->item_gobj != NULL ||
        !(fp->facing_dir == 1.0f || fp->facing_dir == -1.0f) ||
        ftColl_8007B868(fp->gobj) != 0 ||
        ftColl_8007B868(target->gobj) != 0 ||
        /* Only these common states own the damage union/hitstun physics. */
        target->motion_id < ftCo_MS_DamageHi1 ||
        target->motion_id > ftCo_MS_DamageFlyRoll || !target->x221C_b6 ||
        !(target->mv.co.damage.x0 >= hit + SC_HITSTUN_RESERVE) ||
        !SC_Range(p_ftCommonData->x204_knockbackFrameDecay, 0.0f, 1.0f) ||
        !SC_Project(target, 0, 0, 0, hit + 1, theirs))
    {
        /* Broad air admission, including target/state/items and projection. */
        ShowboatRecorder_Reason(fp, SBR_COMBAT, SBR_GEOMETRY_OR_WINDOW);
        return false;
    }
    for (steer = -1; steer <= 1; ++steer) {
        if (!SC_Project(fp, action, delay, steer, hit + 1, ours)) {
            ShowboatRecorder_Reason(fp, SBR_COMBAT, SBR_GEOMETRY_OR_WINDOW);
            return false;
        }
        /* Input age is our sampled neutral/pulse protocol, NEVER anim age.
         * Check startup AND one later frame to reject marginal timing fits.
         * Tight root-relative boxes are heuristics, not decoded hurt/hitboxes:
         * do not advertise a guaranteed sweetspot or a guaranteed hit. */
        for (i = hit; i <= hit + 1; ++i) {
            dx = (theirs[i].x - ours[i].x) * fp->facing_dir;
            dy = theirs[i].y - ours[i].y;
            if (action == SC_KNEE) {
                if (!SC_Range(dx, 5.0f, 20.0f) ||
                    !SC_Range(dy, 0.0f, 9.0f)) {
                    ShowboatRecorder_Reason(fp, SBR_COMBAT, SBR_GEOMETRY_OR_WINDOW);
                    return false;
                }
            } else if (!SC_Range(dx, -8.0f, 8.0f) ||
                       !SC_Range(dy, 7.0f, 22.0f)) {
                ShowboatRecorder_Reason(fp, SBR_COMBAT, SBR_GEOMETRY_OR_WINDOW);
                return false;
            }
        }
    }
    return true;
}

static bool SC_Opportunity(Fighter* fp, Fighter* target, int action, int delay)
{
    if (action == SC_GRAB) {
        return SC_GrabOpportunity(fp, target, 7 + delay);
    }
    return SC_AirOpportunity(fp, target, action, delay);
}

static bool SC_ActionInput(Fighter* fp, SC_State* s, bool press)
{
    ftCo_800B4A78(fp);
    fp->cpu.xA4 = 0;
    if (press) {
        if (s->action != SC_GRAB) {
            /* Proven local air scripts: 8 Knee (facing X80), 6 up-air (Y80).
             * Encode just the legal one-sample pulse, not their longer waits. */
            ftCo_800B46B8(fp, CpuCmd_SetLstickX,
                         (u8) (s->action == SC_KNEE ?
                                   (s8) (fp->facing_dir * 80) : 0));
            ftCo_800B46B8(fp, CpuCmd_SetLstickY,
                         (u8) (s->action == SC_UPAIR ? 80 : 0));
        }
        ftCo_800B463C(fp, s->action == SC_GRAB ? CpuCmd_PressZ : CpuCmd_PressA);
    }
    /* Bounded 3/5/13 bytes; one wait, then release A/Z AND analog even if main
     * stops calling Update. No input timer, animation or gameplay-state writes. */
    ftCo_800B46B8(fp, CpuCmd_WaitFor, 1);
    s->resume_offset = fp->cpu.write_pos - fp->cpu.buffer;
    if (press) {
        ftCo_800B463C(fp, s->action == SC_GRAB ? CpuCmd_ReleaseZ : CpuCmd_ReleaseA);
        if (s->action != SC_GRAB) {
            ftCo_800B46B8(fp, CpuCmd_SetLstickX, 0);
            ftCo_800B46B8(fp, CpuCmd_SetLstickY, 0);
        }
    }
    ftCo_800B49F4(fp);
    s->priority = fp->cpu.x18;
    s->script_size = fp->cpu.write_pos - fp->cpu.buffer;
    memcpy(s->script, fp->cpu.buffer, (size_t) s->script_size);
    ++s->age;
    return true;
}

bool ShowboatCombat_Update(Fighter* fp, Fighter* target)
{
    SC_State* s = SC_StateFor(fp);
    int action = 0;
    bool sampled, acknowledged;
    ShowboatRecorder_Reason(fp, SBR_COMBAT, SBR_NO_CANDIDATE);
    if (s == NULL) {
        ShowboatRecorder_Reason(fp, SBR_COMBAT, SBR_PHYSICAL_OR_STATE);
        return false;
    }
    ShowboatCombat_RestoreInput(fp); /* Idempotent with main's FIRST-call hook. */
    if (s->cooldown > 0) { --s->cooldown; }
    if (s->lc_cooldown > 0) { --s->lc_cooldown; }
    if (s->log_cooldown > 0) { --s->log_cooldown; }
    if (s->action) {
        /* Every owned call advances to the sole pulse or ends. Never wait for
         * animation age or chain jumps. A missing interpreter sample cancels. */
        sampled = SC_OurScript(fp, s) &&
                  fp->cpu.csP == fp->cpu.buffer + s->resume_offset &&
                  fp->cpu.command_duration == 1;
        acknowledged = (s->action == SC_GRAB &&
                        (fp->motion_id == ftCo_MS_Catch ||
                         fp->motion_id == ftCo_MS_CatchDash)) ||
                       (s->action == SC_KNEE && fp->ground_or_air == GA_Air &&
                        fp->motion_id == ftCo_MS_AttackAirF) ||
                       (s->action == SC_UPAIR && fp->ground_or_air == GA_Air &&
                        fp->motion_id == ftCo_MS_AttackAirHi);
        if (s->age == 2) {
            /* Acceptance can itself switch native priority (Catch -> 9) and
             * replace our script before this hook. The observed motion still
             * acknowledges acceptance, never a hit. Do not artificially delay
             * the next conversion after a successful action; real animation
             * and actionability, not our retry budget, limit followups. */
            ShowboatRecorder_Event(fp, acknowledged ?
                (s->action == SC_GRAB ? SBR_EVENT_GRAB_ACK : SBR_EVENT_AERIAL_ACK) : 0);
            ShowboatRecorder_Reason(fp, SBR_COMBAT,
                                   acknowledged ? SBR_COMPLETED : SBR_CANCELLED);
            SC_Stop(fp, s, acknowledged ?
                    "acknowledged motion; release/yield to vanilla" :
                    "cancel: single pulse unconfirmed/replaced");
            if (acknowledged) { s->cooldown = 0; }
            return false;
        }
        if (!sampled || s->age != 1) {
            ShowboatRecorder_Reason(fp, SBR_COMBAT, SBR_INPUT_OR_SCRIPT);
            SC_Stop(fp, s, "cancel: lost script ownership/neutral not sampled");
            return false;
        }
    }
    if (!SC_Eligible(fp) || SC_Unavailable(fp) || fp->x221C_b6 ||
        fp->item_gobj != NULL || !SC_LowPriority(fp) || target == NULL ||
        fp->cpu.xA4 != 0)
    {
        /* Broad eligibility/state/items/native-priority/target/cached group. */
        ShowboatRecorder_Reason(fp, SBR_COMBAT, SBR_PHYSICAL_OR_STATE);
        SC_Stop(fp, s, "cancel: unavailable/native priority or cached attack");
        return false;
    }
    if (s->action) {
        if (s->target != target || s->target_spawn != target->x8_spawnNum ||
            SC_TriggerHeld(fp) || (fp->input.held_buttons[0] & SC_CONFLICT) ||
            fp->input.lstick[0].x != 0.0f || fp->input.lstick[0].y != 0.0f ||
            fp->input.cstick[0].x != 0.0f || fp->input.cstick[0].y != 0.0f)
        {
            /* Only the already-evaluated target prefix is distinguished. */
            ShowboatRecorder_Reason(fp, SBR_COMBAT,
                s->target != target || s->target_spawn != target->x8_spawnNum ?
                    SBR_TARGET : SBR_INPUT_OR_SCRIPT);
            SC_Stop(fp, s, "cancel: target changed/neutral input not observed");
            return false;
        }
        if (!SC_Opportunity(fp, target, s->action, 0)) {
            /* Recheck may downgrade Knee, never upgrade a vertical followup
             * into a slower Knee without its own neutral/prediction budget. */
            if (s->action == SC_KNEE &&
                SC_AirOpportunity(fp, target, SC_UPAIR, 0))
            {
                s->action = SC_UPAIR;
                SC_Log(fp, "KNEE recheck fell back to UPAIR");
            } else {
                ShowboatRecorder_Reason(fp, SBR_COMBAT, SBR_GEOMETRY_OR_WINDOW);
                SC_Stop(fp, s, "cancel: intercept/punish no longer safe");
                return false;
            }
        }
        ShowboatRecorder_Reason(fp, SBR_COMBAT, SBR_ACTIVE);
        return SC_ActionInput(fp, s, true);
    }
    if (s->cooldown || SC_TriggerHeld(fp) ||
        (fp->input.held_buttons[0] & SC_CONFLICT) ||
        (fp->cpu.buttons & SC_CONFLICT))
    {
        ShowboatRecorder_Reason(fp, SBR_COMBAT,
                               s->cooldown ? SBR_COOLDOWN : SBR_INPUT_OR_SCRIPT);
        return false;
    }
    if (SC_GrabOpportunity(fp, target, 8)) { action = SC_GRAB; }
    else if (SC_AirOpportunity(fp, target, SC_KNEE, 1)) { action = SC_KNEE; }
    else if (SC_AirOpportunity(fp, target, SC_UPAIR, 1)) { action = SC_UPAIR; }
    if (!action) { return false; }
    s->action = action;
    s->age = 0;
    s->cooldown = 45; /* Two samples max: neutral, then ONE A/Z, then yield. */
    s->target = target;
    s->target_spawn = target->x8_spawnNum;
    SC_Log(fp, action == SC_GRAB ? "start GRAB: neutral then recheck" :
               action == SC_KNEE ? "start KNEE: free-air intercept; neutral first" :
                                   "start UPAIR: vertical intercept; neutral first");
    ShowboatRecorder_Reason(fp, SBR_COMBAT, SBR_STARTED);
    return SC_ActionInput(fp, s, false);
}

/* Read-only sweep of the current ECB bottom along up to three predicted frames.
 * mpCheckFloor takes segment endpoints, y offset, outputs, then floor/joint
 * filters and optional callback. Never pass the fighter's collision outputs. */
static int SC_Touchdown(Fighter* fp)
{
    Vec3 contact, normal;
    u32 flags;
    int i, line;
    float x = fp->coll_data.cur_pos.x + fp->coll_data.ecb.bottom.x;
    float y = fp->coll_data.cur_pos.y + fp->coll_data.ecb.bottom.y;
    float vy = fp->self_vel.y;
    float nx, ny;
    if (vy >= 0.0f || fp->pos_delta.y >= 0.0f) {
        return 0;
    }
    for (i = 1; i <= 3; ++i) {
        if (!fp->fall_fast) {
            vy -= fp->co_attrs.gravity;
            if (vy < -fp->co_attrs.terminal_velocity) {
                vy = -fp->co_attrs.terminal_velocity;
            }
        }
        nx = x + fp->pos_delta.x;
        ny = y + vy;
        line = -1;
        if (mpCheckFloor(x, y, nx, ny, 0.0f, &contact, &line, &flags, &normal,
                         fp->coll_data.floor_skip, fp->coll_data.joint_id_skip,
                         fp->coll_data.joint_id_only, NULL, NULL))
        {
            return line >= 0 && normal.y > 0.0f ? i : 0;
        }
        x = nx;
        y = ny;
    }
    return 0;
}

void ShowboatCombat_PostInput(Fighter* fp)
{
    SC_State* s = SC_StateFor(fp);
    int eta;
    ShowboatRecorder_Reason(fp, SBR_LCANCEL, SBR_NO_CANDIDATE);
    if (s == NULL || s->analog_owned || s->lc_cooldown || !SC_Eligible(fp) ||
        SC_Unavailable(fp) || fp->x221C_b6 || fp->ground_or_air != GA_Air ||
        fp->motion_id < ftCo_MS_AttackAirN || fp->motion_id > ftCo_MS_AttackAirLw ||
        !fp->cmd_vars[0] || SC_TriggerHeld(fp) ||
        (fp->input.held_buttons[0] & SC_DEFENSE) ||
        128.0f / 255.0f <= p_ftCommonData->analog_shoulder_deadzone)
    {
        /* Distinguish only the evaluated prefix; the remaining eligibility/
         * state/aerial-window/input/deadzone checks stay a broad group. */
        ShowboatRecorder_Reason(fp, SBR_LCANCEL,
            s == NULL ? SBR_PHYSICAL_OR_STATE :
            s->analog_owned ? SBR_INPUT_OR_SCRIPT :
            s->lc_cooldown ? SBR_COOLDOWN : SBR_PHYSICAL_OR_STATE);
        return;
    }
    eta = SC_Touchdown(fp);
    if (!eta || fp->x67F + eta + 1 < p_ftCommonData->xE4) {
        ShowboatRecorder_Reason(fp, SBR_LCANCEL, SBR_GEOMETRY_OR_WINDOW);
        return; /* An existing LR edge already covers the predicted landing. */
    }
    /* Analog > .30 synthesizes LR during normal input sampling. Digital L/R
     * alone update x680/tech lockout and allow airdodge: never emit those here.
     * No sticks/buttons are cleared to fabricate a fresh edge. */
    s->old_ltrigger = fp->cpu.ltrigger;
    s->analog_owned = true;
    s->lc_cooldown = 6;
    fp->cpu.ltrigger = 128;
    /* An emitted sample, NOT confirmation of reduced landing lag. */
    ShowboatRecorder_Reason(fp, SBR_LCANCEL, SBR_STARTED);
    ShowboatRecorder_Event(fp, SBR_EVENT_LCANCEL_SAMPLE);
    if (!s->log_cooldown) {
        SC_Log(fp, "L-cancel: one analog-only sample, touchdown <=3 frames");
        s->log_cooldown = 120;
    }
}

int ShowboatCombat_GetAction(Fighter* fp)
{
    SC_State* s;
    if (fp == NULL || fp->player_id >= SC_SLOTS) { return 0; }
    s = &sc_states[fp->player_id];
    return s->owner == fp && s->spawn == fp->x8_spawnNum ? s->action : 0;
}
