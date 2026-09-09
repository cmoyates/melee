/* Controller-only fresh melee defense choice, NOT a perfect-contact oracle.
 * Source audit:
 * - ftcpuattack.c: BB9B4 caches F8_b12/F0/F4; BB104 forecasts initialized
 *   capsules three frames against a body sphere, NOT the future shield.
 *   BA9A0/inline2 ordinarily chooses a roll for melee. We deliberately choose
 *   hardshield ONLY before that fresh empty defense7 script is built.
 * - ftcmdscript.c: PressR sets digital R AND raw rtrigger=255; ReleaseR clears
 *   both. fighter.c synthesizes LR and trigger=1 from either digital L/R.
 * - ftCo_Guard.c: powershield_input_window=2; x2B4=3 counts down BELOW zero
 *   (four fighter collision samples), x2A4 is the two-sample projectile window.
 *   No timers are written here. GuardReflect / x221C_b2 alone prove nothing.
 * - ftcoll.c: ftColl_80076CBC's fighter PS branch calls 80094138, setting
 *   guard.x1C=x2B8 (normally 0x20), x10=0. It does NOT set guard.x20.
 *   GuardSetOff + positive x1C + zero minhold is persistent evidence;
 *   b2 is the expiring window, NOT a persistent contact requirement. Fresh
 *   GuardOn/GuardReflect entry clears x1C, ordinary blocks never set it.
 *   x19A4/x19A8 are transient and cleared by Fighter's collision processing.
 *   No items at each observed update, live singles, and one credit per attempt
 *   deliberately favor missed credit over attributing a projectile/retap.
 */
#include "showboat_defense.h"
#include "showboat_recorder.h"

#include <melee/ft/fighter.h>
#include <melee/ft/ftcmdscript.h>
#include <melee/ft/kinds/ftCommon/ftCo_0A01.h>
#include <melee/ft/types.h>
#include <melee/lb/lbcollision.h>
#include <melee/pl/player.h>
#include <sysdolphin/baselib/gobj.h>
#include <dolphin/os.h>
#include <string.h>

#define SD_SLOTS 6
#define SD_HOLD 10
#define SD_RETRY 12
#define SD_TOAST 30
#define SD_BUTTONS (HSD_PAD_A | HSD_PAD_B | HSD_PAD_X | HSD_PAD_Y | \
                    HSD_PAD_Z | HSD_PAD_L | HSD_PAD_R | HSD_PAD_LR)

/* No initial release, no retap, no one-frame opening. This tail also works if
 * the caller stops updating us or ResetSlot forgets a still-running VM. */
static const s8 sd_script[] = {
    CpuCmd_SetLstickX, 0, CpuCmd_SetLstickY, 0,
    CpuCmd_SetCstickX, 0, CpuCmd_SetCstickY, 0,
    CpuCmd_PressR, CpuCmd_WaitFor, SD_HOLD, CpuCmd_ReleaseR, CpuCmd_Done
};
#define SD_RESUME 11

typedef struct {
    Fighter* owner; /* Identity tokens only, never dereference saved pointers. */
    Fighter* opponent;
    s32 spawn, opponent_spawn;
    int age, cooldown, action, toast;
    bool active, acknowledged, pending;
} SD_State;
static SD_State sd_states[SD_SLOTS];

void ShowboatDefense_ResetSlot(int slot)
{
    if (slot >= 0 && slot < SD_SLOTS) {
        memset(&sd_states[slot], 0, sizeof(SD_State));
    }
}

static SD_State* SD_Owner(Fighter* fp)
{
    SD_State* s;
    if (fp == NULL || fp->player_id >= SD_SLOTS) { return NULL; }
    s = &sd_states[fp->player_id];
    return s->owner == fp ? s : NULL;
}

static SD_State* SD_Find(Fighter* fp)
{
    SD_State* s = SD_Owner(fp);
    return s != NULL && s->spawn == fp->x8_spawnNum ? s : NULL;
}

/* Priority and A4 are deliberately NOT part of the old-byte ownership test.
 * Fresh native decisions can coexist with our old buffer. Never rewrite them. */
static bool SD_OldVM(Fighter* fp, SD_State* s)
{
    return s->active &&
        fp->cpu.write_pos == fp->cpu.buffer + sizeof(sd_script) &&
        memcmp(fp->cpu.buffer, sd_script, sizeof(sd_script)) == 0 &&
        ((fp->cpu.csP == fp->cpu.buffer && fp->cpu.command_duration == 1) ||
         (fp->cpu.csP == fp->cpu.buffer + SD_RESUME &&
          fp->cpu.command_duration >= 1 && fp->cpu.command_duration <= SD_HOLD) ||
         (fp->cpu.csP == NULL && fp->cpu.command_duration == 0));
}

static void SD_ClearVM(Fighter* fp)
{
    /* Unlike B4A78 this does NOT clear controller channels, priority or A4. */
    fp->cpu.csP = NULL;
    fp->cpu.command_duration = 0;
    fp->cpu.write_pos = fp->cpu.buffer;
}

/* Call only after SD_OldVM. Pending PressR has not acquired the channel;
 * completed ReleaseR has already relinquished it. Neither owns a later R. */
static void SD_ReleaseOwnedR(Fighter* fp)
{
    if (fp->cpu.csP == fp->cpu.buffer + SD_RESUME) {
        fp->cpu.buttons &= ~HSD_PAD_R;
        if (fp->cpu.rtrigger == 255) { fp->cpu.rtrigger = 0; }
    }
}

void ShowboatDefense_Suspend(Fighter* fp)
{
    /* A new spawn at the SAME live pointer invalidates credit, not proof of
     * the old VM. Clean that VM before forgetting; never dereference owner. */
    SD_State* s = SD_Owner(fp);
    if (s == NULL) { return; }
    if (SD_OldVM(fp, s)) {
        SD_ReleaseOwnedR(fp);
        SD_ClearVM(fp);
    }
    ShowboatDefense_ResetSlot(fp->player_id);
}

static bool SD_Range(float x, float lo, float hi)
{
    return x >= lo && x <= hi; /* Also reject NaN/Inf. */
}

/* The wait opcode does not rewrite inputs. Yield if either its raw output or
 * the preceding Fighter sample lost hard R; never repair it with a new press.
 * Native proc2 runs CPU/VM, proc3 samples/normalizes input (fighter.c). */
static bool SD_HeldR(Fighter* fp)
{
    return (fp->cpu.buttons & HSD_PAD_R) && fp->cpu.rtrigger == 255 &&
           (fp->input.held_buttons[0] & HSD_PAD_R) &&
           fp->input.triggers[0] == 1.0f;
}

static bool SD_Standing(Fighter* fp)
{
    return fp->motion_id >= ftCo_MS_Wait && fp->motion_id <= ftCo_MS_WalkFast;
}

static bool SD_Shield(Fighter* fp)
{
    return fp->motion_id == ftCo_MS_GuardOn ||
           fp->motion_id == ftCo_MS_Guard ||
           fp->motion_id == ftCo_MS_GuardReflect ||
           fp->motion_id == ftCo_MS_GuardSetOff;
}

static bool SD_Forced(Fighter* fp)
{
    return fp->x221F_b3 || fp->x221C_b6 || fp->x2224_b2 || fp->x221D_b4 ||
           fp->victim_gobj != NULL || fp->x1A5C != NULL ||
           fp->x1064_thrownHitbox.owner != NULL;
}

static bool SD_Live(Fighter* fp, Fighter* target)
{
    int i, others = 0;
    Fighter_GObj* other = NULL;
    if (fp->kind != FTKIND_CAPTAIN || fp->cpu.level != 9 || fp->cpu.xC != 4 ||
        !ftCo_800A2040(fp) || fp->gobj == NULL ||
        Player_GetPlayerState(fp->player_id) != 2 ||
        Player_GetEntity(fp->player_id) != fp->gobj ||
        GET_FIGHTER(fp->gobj) != fp || fp->x221F_b3 || fp->x221F_b4)
    { return false; }
    for (i = 0; i < SD_SLOTS; ++i) {
        if (Player_GetPlayerState(i) == 2) {
            if (Player_GetEntityAtIndex(i, 1) != NULL) { return false; }
            if (i != fp->player_id) {
                ++others;
                other = Player_GetEntity(i);
            }
        }
    }
    /* Compare to the live slot before dereferencing the supplied target. */
    if (others != 1 || other == NULL || GET_FIGHTER(other) != target ||
        target == NULL || target == fp)
    { return false; }
    return target->player_id < SD_SLOTS && target->player_id != fp->player_id &&
           Player_GetEntity(target->player_id) == other &&
           target->gobj == other && !target->x221F_b3 && !target->x221F_b4;
}

static bool SD_NoItems(Fighter* fp, Fighter* target)
{
    return HSD_GObj_Entities->items == NULL && fp->item_gobj == NULL &&
           target->item_gobj == NULL && fp->cpu.xF4 == NULL;
}

static bool SD_Interior(Fighter* fp, Fighter* target)
{
    return fp->ground_or_air == GA_Ground &&
           target->ground_or_air == GA_Ground && fp->coll_data.floor.index >= 0 &&
           fp->coll_data.floor.index == target->coll_data.floor.index &&
           fp->coll_data.floor.normal.y > 0.99f &&
           ftCo_800A2A70(fp, true) > 22.0f &&
           ftCo_800A2A70(fp, false) > 22.0f &&
           SD_Range(target->cur_pos.y - fp->cur_pos.y, -3, 3) &&
           SD_Range(target->cur_pos.z - fp->cur_pos.z, -2, 2) &&
           SD_Range(fp->pos_delta.x, -2, 2) &&
           SD_Range(target->pos_delta.x, -3, 3);
}

static bool SD_Threat(Fighter* fp, Fighter* target)
{
    int i;
    bool intersects = false;
    float radius = fp->cpu.x568 * 0.5f;
    Vec3 body = fp->cur_pos;
    /* Reached threat group: cached target/attack, physical/interior limits,
     * supported capsules and intersection. Not an atomic collision miss. */
    ShowboatRecorder_Reason(fp, SBR_DEFENSE, SBR_GEOMETRY_OR_WINDOW);
    /* Grounded common normals only: no aerials, grabs, getup/ledge attacks,
     * character specials (including BB768's heuristics), items or throws. */
    if (fp->cpu.xF8_b12 != 1 || fp->cpu.xF0 != target ||
        target->motion_id < ftCo_MS_Attack11 ||
        target->motion_id > ftCo_MS_AttackLw4 || SD_Forced(target) ||
        target->x2219_b5 || target->x221A_b3 ||
        !SD_Range(radius, 3, 20) || !SD_Interior(fp, target))
    { return false; }
    body.y += radius;
    for (i = 0; i < 4; ++i) {
        HitCapsule* hit = &target->x914[i];
        Vec3 start, end, out0, out1;
        if (hit->state == HitCapsule_Disabled) { continue; }
        /* Reject the whole opportunity on ANY uninitialized/unsupported box,
         * even when another valid one intersects. Native Enabled has no valid
         * sweep history yet. No catch, inert, unusual elements or unblockables. */
        if (hit->state <= HitCapsule_Enabled || hit->state > HitCapsule_Max ||
            hit->x43_b2 || !hit->x42_b5 || !hit->x40_b3 ||
            hit->hit_grabbed_victim_only || hit->element > HitElement_Slash ||
            !SD_Range(hit->damage, 1, 30) || !SD_Range(hit->scale, 0.1f, 12) ||
            !SD_Range(hit->x4C.x - hit->x58.x, -8, 8) ||
            !SD_Range(hit->x4C.y - hit->x58.y, -8, 8) ||
            !SD_Range(hit->x4C.z - hit->x58.z, -4, 4) ||
            !SD_Range(hit->x4C.x - body.x, -60, 60) ||
            !SD_Range(hit->x4C.y - body.y, -40, 40) ||
            !SD_Range(hit->x4C.z - body.z, -10, 10))
        { return false; }
        if (lbColl_8000ACFC(fp, hit)) { continue; }
        start = hit->x4C;
        end.x = start.x + 3.0f * (start.x - hit->x58.x);
        end.y = start.y + 3.0f * (start.y - hit->x58.y);
        end.z = start.z + 3.0f * (start.z - hit->x58.z);
        /* Read-only revalidation, same geometry as BB104/BB9B4; no call to a
         * mutating CheckInput, no hitbox initialization or future anim scripts. */
        if (lbColl_80006094(&start, &end, &body, &body, &out0, &out1,
                           hit->scale, radius))
        { intersects = true; }
    }
    return intersects;
}

static void SD_Handoff(Fighter* fp, SD_State* s)
{
    if (SD_OldVM(fp, s)) {
        if (fp->cpu.x18 != 7) {
            /* Remove only our old R for a new recovery/punish decision, not
             * its priority, A4, sticks or other buttons. A replaced VM never
             * comes here. Do not leave the old wait delaying native dispatch. */
            SD_ReleaseOwnedR(fp);
        }
        SD_ClearVM(fp); /* Defense7 preserves HELD R, including in hitlag. */
    }
    /* Replaced VM: no writes at all. Native replacement owns its inputs.
     * Never remove a fresh A4 or cancel/delay a native punish.
     * BA9A0 threat0 emits ReleaseR and restores the previous priority;
     * melee roll builders explicitly release R, native block presses R.
     * The caller must run native dispatch immediately when we return false. */
    s->active = false;
    /* Success has no extra lockout: natural release, actionability and fresh
     * native threat selection still gate another attempt. Never pump R. */
    s->cooldown = s->action == 11 ? 0 : SD_RETRY;
    if (s->action != 11) { s->action = 0; }
}

bool ShowboatDefense_Update(Fighter* fp, Fighter* target)
{
    SD_State* s;
    ShowboatRecorder_Reason(fp, SBR_DEFENSE, SBR_NO_CANDIDATE);
    if (fp == NULL || fp->player_id >= SD_SLOTS) {
        ShowboatRecorder_Reason(fp, SBR_DEFENSE, SBR_PHYSICAL_OR_STATE);
        return false;
    }
    s = SD_Find(fp);
    if (s == NULL) {
        if (SD_Owner(fp) != NULL) {
            ShowboatRecorder_Reason(fp, SBR_DEFENSE, SBR_CANCELLED);
            ShowboatDefense_Suspend(fp);
            return false; /* Respawn cleanup cannot also start a new attempt. */
        }
        ShowboatDefense_ResetSlot(fp->player_id);
        s = &sd_states[fp->player_id];
        s->owner = fp;
        s->spawn = fp->x8_spawnNum;
    }
    if (!SD_Live(fp, target)) {
        /* Live self/target identities and singles eligibility as one group. */
        ShowboatRecorder_Reason(fp, SBR_DEFENSE, SBR_TARGET);
        ShowboatDefense_Suspend(fp);
        return false;
    }
    if (s->opponent != NULL && (s->opponent != target ||
                               s->opponent_spawn != target->x8_spawnNum))
    {
        ShowboatRecorder_Reason(fp, SBR_DEFENSE, SBR_TARGET);
        ShowboatDefense_Suspend(fp);
        return false;
    }
    s->opponent = target;
    s->opponent_spawn = target->x8_spawnNum;
    if (s->toast > 0) { --s->toast; }
    if (!s->active) {
        if (!SD_Shield(fp) || s->toast == 0) { s->action = 0; }
        if (s->cooldown > 0) {
            ShowboatRecorder_Reason(fp, SBR_DEFENSE, SBR_COOLDOWN);
            --s->cooldown;
            return false;
        }
    } else {
        ++s->age; /* Bounded updates, NOT fabricated game/hitlag timers. */
        /* Observe BEFORE the hitlag exclusion: shield contact often IS in
         * hitlag. No x19A8 dependency after Fighter clears its transient data.
         * Stop observing this attempt on the very first handoff/replacement. */
        if (SD_OldVM(fp, s) && fp->cpu.csP == fp->cpu.buffer + SD_RESUME &&
            SD_HeldR(fp) &&
            SD_NoItems(fp, target) && !SD_Forced(fp) &&
            fp->motion_id == ftCo_MS_GuardSetOff &&
            fp->mv.co.guard.x1C > 0 && fp->mv.co.guard.x10 == 0.0f)
        {
            s->pending = true;
            s->action = 11;
            s->toast = SD_TOAST;
            ShowboatRecorder_Reason(fp, SBR_DEFENSE, SBR_SUCCESS);
            ShowboatRecorder_Event(fp, SBR_EVENT_POWERSHIELD_CONTACT);
#if SHOWBOAT_AI_DEBUG
            OSReport("SHOWBOAT DEFENSE P%d: fighter PS contact\n", fp->player_id + 1);
#endif
        }
        if (SD_Shield(fp) && !s->acknowledged) {
            s->acknowledged = true;
#if SHOWBOAT_AI_DEBUG
            OSReport("SHOWBOAT DEFENSE P%d: guard acknowledged ms=%d (not contact)\n",
                     fp->player_id + 1, fp->motion_id);
#endif
        }
        /* Preserve owned contact through its mandatory handoff. Otherwise
         * default to the combined VM/input/priority/state/items/age group;
         * only a reached threat planner can replace it with geometry/window. */
        ShowboatRecorder_Reason(fp, SBR_DEFENSE,
                               s->action == 11 ? SBR_SUCCESS : SBR_CANCELLED);
        if (!SD_OldVM(fp, s) || fp->cpu.csP == NULL ||
            (fp->cpu.csP == fp->cpu.buffer + SD_RESUME && !SD_HeldR(fp)) ||
            fp->cpu.x18 != 7 || fp->cpu.xA4 != 0 ||
            fp->motion_id == ftCo_MS_GuardSetOff || SD_Forced(fp) ||
            fp->x2219_b5 || fp->x221A_b3 || !SD_NoItems(fp, target) ||
            !SD_Range(fp->shield_health, 45, 60) || s->age >= SD_HOLD ||
            (!SD_Shield(fp) && (!SD_Standing(fp) || s->acknowledged || s->age >= 3)) ||
            !SD_Threat(fp, target))
        {
            SD_Handoff(fp, s);
            return false;
        }
        ShowboatRecorder_Reason(fp, SBR_DEFENSE, SBR_ACTIVE);
        return true;
    }
    /* FRESH EMPTY defense7 only. No running/built script, A4, native R delay,
     * GuardOff cancel, or held shield release/repress for a new PS window.
     * Fighter input[0] is the previous naturally sampled output at this hook.
     * Exact zero analog is conservative, including synthesized digital L/R. */
    /* First priority gate is atomic; otherwise use the fresh-VM/input/state/
     * shield/items group until the threat planner is actually reached. */
    ShowboatRecorder_Reason(fp, SBR_DEFENSE,
        fp->cpu.x18 != 7 ? SBR_NATIVE_PRIORITY : SBR_INPUT_OR_SCRIPT);
    if (fp->cpu.x18 != 7 || fp->cpu.csP != NULL ||
        fp->cpu.command_duration != 0 || fp->cpu.write_pos != fp->cpu.buffer ||
        fp->cpu.xA4 != 0 || !SD_Standing(fp) || SD_Forced(fp) ||
        fp->x2219_b5 || fp->x221A_b3 || !SD_Range(fp->shield_health, 45, 60) ||
        !SD_NoItems(fp, target) || (fp->cpu.buttons & SD_BUTTONS) ||
        fp->cpu.ltrigger != 0 || fp->cpu.rtrigger != 0 ||
        (fp->input.held_buttons[0] & SD_BUTTONS) || fp->input.triggers[0] != 0 ||
        !SD_Threat(fp, target))
    { return false; }
    memcpy(fp->cpu.buffer, sd_script, sizeof(sd_script));
    fp->cpu.write_pos = fp->cpu.buffer + sizeof(sd_script);
    fp->cpu.csP = fp->cpu.buffer;
    fp->cpu.command_duration = 1;
    s->active = true;
    s->acknowledged = false;
    s->pending = false;
    s->toast = 0;
    s->age = 0;
    s->action = 10;
    ShowboatRecorder_Reason(fp, SBR_DEFENSE, SBR_STARTED);
#if SHOWBOAT_AI_DEBUG
    OSReport("SHOWBOAT DEFENSE P%d: hardshield onset queued\n", fp->player_id + 1);
#endif
    return true;
}

static bool SD_Current(Fighter* fp, SD_State* s)
{
    return s != NULL && SD_Live(fp, s->opponent) &&
           s->opponent->x8_spawnNum == s->opponent_spawn;
}

int ShowboatDefense_GetAction(Fighter* fp)
{
    SD_State* s = SD_Find(fp);
    return SD_Current(fp, s) ? s->action : 0;
}

bool ShowboatDefense_TakePerfect(Fighter* fp)
{
    SD_State* s = SD_Find(fp);
    bool pending = SD_Current(fp, s) && s->pending;
    if (s != NULL) { s->pending = false; }
    return pending;
}
