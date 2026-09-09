/* Output-only ground side-B veto; not a move/physics simulator.
 * Native ftcpuattack.c's priority-9 throw followups append PlCo 0x39/0x3A:
 * f41 full forward X / Y=0 / B; f42 release / neutral / wait55; f97 jump.
 * We suppress ONLY the unsafe f41 sample. The native VM, 55-update idle tail,
 * priority arbitration and later inputs intentionally remain intact.
 *
 * Verified PlCaAJ ground startup root-Z: 0@0, -10@4, -9.996094@16,
 * 9.998047@20, 44.998047@35, 59.998047@80 (Hermite max about 60.227).
 * Ground startup zeros normal velocity and ground physics consumes TransN;
 * empty IASAs cannot cancel the whiff. Round OUT to +61/-11 model units,
 * scale by normal physical/model scale, then reserve 6 world units EACH side.
 * This bounded vanilla FD/BF policy is an engineering margin, not a universal
 * exact-physics proof, hit prediction, or claim of live prevention. */
#include "showboat_safety.h"

#include <melee/ft/fighter.h>
#include <melee/ft/ftcoll.h>
#include <melee/ft/kinds/ftCommon/ftCo_0A01.h>
#include <melee/ft/types.h>
#include <melee/gr/stage.h>
#include <melee/mp/mplib.h>
#include <melee/pl/player.h>
#include <sysdolphin/baselib/gobj.h>

#define SS_FORWARD 61.0f
#define SS_BACKWARD 11.0f
#define SS_RESERVE 6.0f
#define SS_SCALE_EPS 0.0001f

static bool SS_Range(float x, float lo, float hi)
{
    return x >= lo && x <= hi; /* Finite bounds reject NaN and infinity. */
}

static bool SS_Vector(const Vec3* v, float limit)
{
    return SS_Range(v->x, -limit, limit) &&
           SS_Range(v->y, -limit, limit) && SS_Range(v->z, -limit, limit);
}

static bool SS_Live(Fighter* fp)
{
    /* Main owns ready singles, teams, spawn continuity and custom ownership.
     * Recheck primary identity and unavailable/protected/item state only.
     * In particular TARGET hitstun/hitlag, velocity and location do NOT gate
     * this self-runway test: the motivating f7095 rival is DamageFlyTop. */
    return fp != NULL && fp->player_id < 6 && fp->gobj != NULL &&
           !fp->x221F_b4 && Player_GetPlayerState(fp->player_id) == 2 &&
           Player_GetEntity(fp->player_id) == fp->gobj &&
           GET_FIGHTER(fp->gobj) == fp && !fp->x221F_b3 &&
           fp->item_gobj == NULL &&
           fp->motion_id >= ftCo_MS_Wait &&
           !(fp->motion_id >= ftCo_MS_Entry &&
             fp->motion_id <= ftCo_MS_EntryEnd) &&
           ftColl_8007B868(fp->gobj) == 0;
}

static bool SS_NewSideB(Fighter* fp)
{
    /* Full raw X is unambiguous at native x218=.6 / reversal x220=.2,
     * regardless of current facing. Previous horizontal walking is fine.
     * No mixed intentions, held B, c-stick or sampled analog shoulders. */
    return fp->cpu.buttons == HSD_PAD_B &&
           (fp->cpu.lstick.x == 127 || fp->cpu.lstick.x == -127 ||
            fp->cpu.lstick.x == -128) &&
           fp->cpu.lstick.y == 0 && fp->cpu.cstick.x == 0 &&
           fp->cpu.cstick.y == 0 && fp->cpu.ltrigger == 0 &&
           fp->cpu.rtrigger == 0 && fp->input.held_buttons[0] == 0 &&
           fp->input.triggers[0] == 0.0f &&
           fp->input.cstick[0].x == 0.0f && fp->input.cstick[0].y == 0.0f;
}

static bool SS_MainLine(int line, int stage)
{
    return line == 0 || line == 1 ||
           line == (stage == St_Kind_Battle ? 5 : 2);
}

static bool SS_FloorLine(int line, const Vec3* left, const Vec3* right,
                         const Vec3* root)
{
    Vec3 connected_left, connected_right, v0, v1;
    float x0, y0, x1, y1;
    mpFloorGetLeft(line, &connected_left);
    mpFloorGetRight(line, &connected_right);
    mpLineGetV0Pos(line, &v0);
    mpLineGetV1Pos(line, &v1);
    if (!SS_Vector(&v0, 100.0f) || !SS_Vector(&v1, 100.0f) ||
        connected_left.x != left->x || connected_left.y != left->y ||
        connected_left.z != left->z || connected_right.x != right->x ||
        connected_right.y != right->y || connected_right.z != right->z ||
        !(v0.x < v1.x) || v0.x < left->x || v1.x > right->x ||
        v0.y != left->y || v1.y != left->y ||
        v0.z != 0.0f || v1.z != 0.0f) { return false; }

    /* mpCheckFloor uses these NATIVE extended endpoints, with first equal-
     * distance hit winning. Thus BF x=-59.5 can query strip 0 while stored
     * support is 1; even equal indices can have root outside actual v0/v1.
     * Only the same certified flat connected floor is equivalent. Check BOTH
     * lines' own native envelope so a far/stale main-chain index still yields.
     * Do not approximate by +/-1: extending the left endpoint first changes
     * the right extension to possibly 1 + 1/length. This helper is read-only. */
    mpLib_8004ED5C(line, &x0, &y0, &x1, &y1);
    return SS_Range(x0, -100.0f, 100.0f) &&
           SS_Range(x1, -100.0f, 100.0f) &&
           SS_Range(y0, -100.0f, 100.0f) &&
           SS_Range(y1, -100.0f, 100.0f) &&
           x0 <= v0.x && x1 >= v1.x && y0 == v0.y && y1 == v1.y &&
           SS_Range(root->x, x0, x1) &&
           SS_Range(root->y - y0, -0.25f, 0.25f);
}

static bool SS_UnsafeFloor(Fighter* fp)
{
    Vec3 contact, normal, left, right;
    u32 flags;
    int line = -1;
    int stage = Stage_80225194();
    float extent, forward, backward;
    float scale = fp->x34_scale.y * fp->co_attrs.model_scaling;
    if (stage != St_Kind_Battle && stage != St_Kind_Last) { return false; }
    if (!mpCheckFloor(fp->cur_pos.x, fp->cur_pos.y + 2.0f,
                      fp->cur_pos.x, fp->cur_pos.y - 2.0f, 0.0f,
                      &contact, &line, &flags, &normal, -1,
                      fp->coll_data.joint_id_skip,
                      fp->coll_data.joint_id_only, NULL, NULL) ||
        !SS_MainLine(line, stage) ||
        !SS_MainLine(fp->coll_data.floor.index, stage) ||
        (flags & LINE_FLAG_PLATFORM) ||
        !SS_Range(normal.x, -0.001f, 0.001f) ||
        !SS_Range(normal.y, 0.999f, 1.001f) ||
        !SS_Range(normal.z, -0.001f, 0.001f)) { return false; }

    /* mpCheckFloor verifies enabled, nonempty floor contact (its returned
     * flags are lo_flags, NOT the line-kind/enable bits). Same read-only
     * query as SM_Floor. Use ACTUAL CONNECTED ledges, not segment endpoints.
     * Sanity-check known flat vanilla geometry; modified stages, platforms,
     * slopes, stale support and nonfinite geometry deliberately yield. */
    mpFloorGetLeft(line, &left);
    mpFloorGetRight(line, &right);
    extent = stage == St_Kind_Battle ? 68.4f : 85.5657f;
    if (!SS_Vector(&contact, 100.0f) || !SS_Vector(&left, 100.0f) ||
        !SS_Vector(&right, 100.0f) ||
        !SS_Range(left.x + extent, -0.1f, 0.1f) ||
        !SS_Range(right.x - extent, -0.1f, 0.1f) ||
        !SS_Range(left.y, -0.1f, 0.1f) ||
        right.y != left.y ||
        !SS_Range(contact.y - left.y, -0.1f, 0.1f) ||
        !SS_Range(contact.x - fp->cur_pos.x, -0.1f, 0.1f) ||
        !SS_Range(fp->cur_pos.y - contact.y, -0.25f, 0.25f) ||
        left.z != 0.0f || right.z != 0.0f || contact.z != 0.0f ||
        !(left.x < right.x) ||
        fp->cur_pos.x < left.x || fp->cur_pos.x > right.x ||
        !SS_FloorLine(line, &left, &right, &fp->cur_pos) ||
        !SS_FloorLine(fp->coll_data.floor.index, &left, &right,
                      &fp->cur_pos)) { return false; }
    if (fp->cpu.lstick.x < 0) {
        forward = fp->cur_pos.x - left.x;
        backward = right.x - fp->cur_pos.x;
    } else {
        forward = right.x - fp->cur_pos.x;
        backward = fp->cur_pos.x - left.x;
    }
    /* BOTH must be strictly greater. Even inward B near a ledge can fail the
     * initial backwards windup reserve. No opponent-offstage condition. */
    return forward <= SS_FORWARD * scale + SS_RESERVE ||
           backward <= SS_BACKWARD * scale + SS_RESERVE;
}

bool ShowboatSafety_PostInput(Fighter* fp, Fighter* target)
{
    /* Cheap self/output gates precede all player/protection/world queries;
     * most native samples are not this priority-9 fresh grounded B pulse. */
    if (fp == NULL || fp->cpu.x18 != 9 || fp->cpu.xA4 != 0 ||
        fp->ground_or_air != GA_Ground ||
        fp->motion_id < ftCo_MS_Wait || fp->motion_id > ftCo_MS_WalkFast ||
        !SS_NewSideB(fp)) { return false; }
    if (!SS_Live(fp) || !SS_Live(target) || fp == target ||
        fp->player_id == target->player_id || fp->kind != FTKIND_CAPTAIN ||
        fp->cpu.level != 9 || fp->cpu.xC != 4 || !ftCo_800A2040(fp) ||
        HSD_GObj_Entities == NULL || HSD_GObj_Entities->items != NULL ||
        fp->cpu.xF4 != NULL ||
        fp->x2219_b5 || fp->x221A_b3 || fp->x2224_b2 || fp->x221D_b4 ||
        fp->x221C_b6 || fp->x2228_b2 || fp->x2222_b6 || fp->dmg.x1948 ||
        fp->victim_gobj != NULL || fp->x1A5C != NULL ||
        fp->x1064_thrownHitbox.owner != NULL ||
        (fp->facing_dir != -1.0f && fp->facing_dir != 1.0f) ||
        !SS_Range(fp->x34_scale.y, 1.0f - SS_SCALE_EPS, 1.0f + SS_SCALE_EPS) ||
        !SS_Range(fp->co_attrs.model_scaling, 0.97f - SS_SCALE_EPS,
                  0.97f + SS_SCALE_EPS) ||
        !SS_Vector(&fp->cur_pos, 1000.0f) ||
        !SS_Range(fp->cur_pos.z, -1.0f, 1.0f) ||
        !SS_Range(fp->gr_vel, -2.5f, 2.5f) ||
        !SS_Vector(&fp->self_vel, 2.5f) || !SS_Vector(&fp->pos_delta, 2.5f) ||
        !SS_Vector(&fp->x8c_kb_vel, 0.0f) ||
        !SS_Vector(&fp->x98_atk_shield_kb, 0.0f) ||
        !SS_Vector(&fp->x74_anim_vel, 0.0f) ||
        !SS_UnsafeFloor(fp)) { return false; }

    /* No VM reads/validation: even foreign cursors and opaque scripts are
     * untouched. No borrowed-B restore, state, RNG or native planner calls. */
    fp->cpu.buttons &= ~HSD_PAD_B;
    fp->cpu.lstick.x = 0;
    return true;
}
