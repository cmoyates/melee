/* A personality, not a replacement CPU. All actions use the stock input VM. */
#include "showboat_ai.h"
#include "showboat_combat.h"

#if SHOWBOAT_AI_HUD
#include "showboat_hud.h"
#endif

#include <melee/ft/fighter.h>
#include <melee/ft/ftcoll.h>
#include <melee/ft/ftcmdscript.h>
#include <melee/ft/ftcommon.h>
#include <melee/gr/stage.h>
#include <melee/mp/mplib.h>
#include <sysdolphin/baselib/gobj.h>
#include <melee/ft/kinds/ftCaptain/forward.h>
#include <melee/ft/kinds/ftCommon/ftCo_0A01.h>
#include <melee/ft/types.h>
#include <melee/gm/gm_16AE.h>
#include <melee/pl/player.h>
#include <melee/mp/mpcoll.h>
#include <dolphin/os.h>
#include <string.h>

#define SB_SLOTS 6
#define SB_BASE_EGO 55
#define SB_ADVANTAGE_PERIOD 90
#define SB_STYLE_COOLDOWN 90
#define SB_TAUNT_COOLDOWN 180
#define SB_PUNISH_WINDOW 30
#define SB_SERIOUS_FRAMES 90
#define SB_EDGE_MARGIN 22.0f

/* These are mod states, NOT CPU scenario IDs or fighter motion IDs. */
typedef enum {
    SB_NONE,
    SB_TAUNT,
    SB_SWAGGER,
    SB_PUNCH,
    SB_DANCE
} SB_Action;

typedef struct {
    Fighter* owner; /* identity only; never dereferenced between updates */
    s32 spawn;
    int opponent_slot;
    int ego;
    int tick;
    int cooldown;
    int taunt_cooldown;
    int taunt_settle;
    int serious;
    int recent_style;
    int celebration;
    int ko_lockout;
    int bias_log_cooldown;
    int toy_frames;
    int stocks;
    int opponent_stocks;
    float percent;
    float opponent_percent;
    bool opponent_dead;
    bool stock_loss_pending;
    bool spawn_loss_pending;
    bool danger;
    bool whiff;
    bool vulnerable;
    SB_Action action;
    int age;
    int dance_direction;
    int dance_turns;
    int dance_floor;
    float dance_origin;
    u32 random;
} SB_State;

static SB_State sb_states[SB_SLOTS];

static float SB_Abs(float x)
{
    return x < 0.0f ? -x : x;
}

static void SB_Ego(Fighter* fp, SB_State* s, int delta, char* reason)
{
    int old = s->ego;
    s->ego += delta;
    if (s->ego < 0) {
        s->ego = 0;
    } else if (s->ego > 100) {
        s->ego = 100;
    }
#if SHOWBOAT_AI_DEBUG
    if (old != s->ego) {
        OSReport("SHOWBOAT P%d ego %d -> %d: %s\n", fp->player_id + 1,
                 old, s->ego, reason);
    }
#else
    (void) fp;
    (void) old;
    (void) reason;
#endif
}

static void SB_Log(Fighter* fp, SB_State* s, char* reason)
{
#if SHOWBOAT_AI_DEBUG
    OSReport("SHOWBOAT P%d ego=%d action=%d age=%d: %s\n",
             fp->player_id + 1, s->ego, s->action, s->age, reason);
#else
    (void) fp;
    (void) s;
    (void) reason;
#endif
}

void ShowboatAI_ResetSlot(int slot)
{
    if (slot >= 0 && slot < SB_SLOTS) {
#if SHOWBOAT_AI_HUD
        ShowboatHUD_ResetSlot(slot);
#endif
        ShowboatCombat_ResetSlot(slot);
        memset(&sb_states[slot], 0, sizeof(SB_State));
    }
}

static bool SB_Eligible(Fighter* fp)
{
    return fp->player_id < SB_SLOTS && fp->kind == FTKIND_CAPTAIN &&
           fp->cpu.level == 9 && fp->cpu.xC == 4 && !fp->x221F_b3 &&
           ftCo_800A2040(fp) && Player_GetEntity(fp->player_id) == fp->gobj;
}

/* V1 is deliberately singles-only. Do not celebrate a third party's KO or
 * ignore a second attacker while posing. Reacquire from live player slots. */
static int SB_OpponentSlot(Fighter* fp)
{
    int i;
    int result = -1;
    for (i = 0; i < SB_SLOTS; ++i) {
        if (i != fp->player_id && Player_GetPlayerState(i) == 2) {
            if (result != -1) {
                return -1;
            }
            result = i;
        }
    }
    return result;
}

static bool SB_Dead(Fighter* fp)
{
    return fp->motion_id >= ftCo_MS_DeadDown &&
           fp->motion_id <= ftCo_MS_DeadUpFallHitCameraIce;
}

static bool SB_Standing(Fighter* fp)
{
    return fp->motion_id >= ftCo_MS_Wait &&
           fp->motion_id <= ftCo_MS_WalkFast;
}

static bool SB_GroundFree(Fighter* fp)
{
    return SB_Standing(fp) ||
           (fp->motion_id >= ftCo_MS_Squat &&
            fp->motion_id <= ftCo_MS_SquatRv);
}

static bool SB_Interior(Fighter* fp)
{
    /* Distance helper returns -1 for air or missing island: fail closed. */
    return fp->ground_or_air == GA_Ground &&
           ftCo_800A2A70(fp, true) > SB_EDGE_MARGIN &&
           ftCo_800A2A70(fp, false) > SB_EDGE_MARGIN;
}

static bool SB_Forced(Fighter* fp)
{
    return fp->x221C_b6 || fp->victim_gobj != NULL || fp->x1A5C != NULL ||
           fp->motion_id < ftCo_MS_Wait ||
           (fp->motion_id >= ftCo_MS_Entry &&
            fp->motion_id <= ftCo_MS_EntryEnd);
}

/* Strict first movement/long-pose support: static main floors on FD/BF.
 * Endpoint distance alone is not signed runway clearance. */
static bool SB_Court(Fighter* fp, Vec3* left, Vec3* right, float margin)
{
    StKind stage = Stage_80225194();
    if ((stage != St_Kind_Battle && stage != St_Kind_Last) ||
        fp->ground_or_air != GA_Ground || fp->coll_data.floor.index < 0 ||
        mpColl_IsOnPlatform(&fp->coll_data) || HSD_GObj_Entities->items != NULL)
    {
        return false;
    }
    mpFloorGetLeft(fp->coll_data.floor.index, left);
    mpFloorGetRight(fp->coll_data.floor.index, right);
    return right->x - left->x >= 100.0f && SB_Abs(right->y - left->y) < 1.0f &&
           SB_Abs(fp->cur_pos.y - left->y) < 6.0f &&
           fp->cur_pos.x > left->x + margin &&
           fp->cur_pos.x < right->x - margin;
}

static bool SB_TauntMovement(Fighter* fp)
{
    Vec3 left, right;
    return (fp->motion_id == ftCo_MS_Dash || fp->motion_id == ftCo_MS_Turn ||
            fp->motion_id == ftCo_MS_Run || fp->motion_id == ftCo_MS_RunBrake) &&
           SB_Abs(fp->self_vel.x) <= 2.5f &&
           SB_Court(fp, &left, &right, 40.0f);
}

static bool SB_TauntSafe(Fighter* fp, Fighter* target)
{
    Vec3 left, right;
    float budget;
    if (!SB_Dead(target) || !gm_8016B094() ||
        Player_GetStocks(target->player_id) <= 0 || SB_Forced(fp) ||
        fp->x2219_b5 || !SB_Court(fp, &left, &right, SB_EDGE_MARGIN))
    {
        return false;
    }
    /* All death motions use this counter slot, followed by mandatory Rebirth
     * on the normal stock route. Do NOT count actionable RebirthWait. Reading
     * only the current death phase underestimates star/screen KO time safely.
     * Retail Falcon taunt is 60 frames; budget includes 20 frames of reserve. */
    /* x5D0 is still UNK_T upstream; retail Rebirth casts this exact field
     * to int in ft_0D4D.c. Do not reinterpret it as floating-point bits. */
    budget = target->mv.co.unk_deadleft.x40 + (int) p_ftCommonData->x5D0;
    return target->mv.co.unk_deadleft.x40 > 0 && budget >= 80.0f;
}

static bool SB_Down(Fighter* fp)
{
    return fp->motion_id == ftCo_MS_DownBoundU ||
           fp->motion_id == ftCo_MS_DownWaitU ||
           fp->motion_id == ftCo_MS_DownBoundD ||
           fp->motion_id == ftCo_MS_DownWaitD ||
           fp->motion_id == ftCo_MS_Furafura;
}

static bool SB_Roll(SB_State* s, int chance)
{
    /* Private, deterministic RNG: personality rolls do not consume HSD RNG. */
    s->random = s->random * 1664525U + 1013904223U;
    return (int) ((s->random >> 16) % 100) < chance;
}

static void SB_Stop(Fighter* fp, SB_State* s, char* reason)
{
    if (s->action != SB_NONE) {
        SB_Log(fp, s, reason);
        s->action = SB_NONE;
        /* Done and ReleaseAll are insufficient: sticks also persist. */
        ftCo_800B4A78(fp);
        fp->cpu.xA4 = 0; /* reselect attacks against the current situation */
    }
}

void ShowboatAI_Suspend(Fighter* fp)
{
    SB_State* s;
    if (fp->player_id >= SB_SLOTS) {
        return;
    }
    s = &sb_states[fp->player_id];
    if (s->owner != fp) {
        return;
    }
    ShowboatCombat_RestoreInput(fp);
    ShowboatCombat_Update(fp, NULL); /* abort only a still-owned combat script */
    ShowboatCombat_ResetSlot(fp->player_id);
    SB_Stop(fp, s, "cancelled: CPU control suspended");
    s->celebration = 0;
    if (!ftCo_800A2040(fp) || fp->kind != FTKIND_CAPTAIN ||
        fp->cpu.level != 9 || fp->cpu.xC != 4)
    {
        ShowboatAI_ResetSlot(fp->player_id);
    }
}

static void SB_Start(Fighter* fp, SB_State* s, SB_Action action, char* reason)
{
    s->action = action;
    s->age = 0;
    s->taunt_settle = 0;
    if (action == SB_TAUNT) {
        s->taunt_cooldown = SB_TAUNT_COOLDOWN;
    } else {
        s->cooldown = SB_STYLE_COOLDOWN;
    }
    s->recent_style = action == SB_TAUNT ? 75 : SB_PUNISH_WINDOW;
    SB_Log(fp, s, reason);
}

static void SB_Countdown(int* value)
{
    if (*value > 0) {
        --*value;
    }
}

static bool SB_DanceInput(Fighter* fp, SB_State* s, Fighter* target)
{
    Vec3 left, right;
    float next;
    int selected;
    bool motion_ok = SB_Standing(fp) || fp->motion_id == ftCo_MS_Dash ||
                     fp->motion_id == ftCo_MS_Turn;
    /* A new candidate after the previous owned frame is fresh: preserve it
     * when yielding instead of throwing away a real punish for movement. */
    if (fp->cpu.x18 != 1 && fp->cpu.x18 != 10) {
        selected = fp->cpu.xA4;
        SB_Stop(fp, s, "dance yields: vanilla attack/defense priority");
        fp->cpu.xA4 = selected;
        return false;
    }
    if (!motion_ok || fp->x2219_b5 || SB_Forced(fp) ||
        !SB_Court(fp, &left, &right, 30.0f) ||
        fp->coll_data.floor.index != s->dance_floor ||
        SB_Abs(fp->cur_pos.x - s->dance_origin) > 24.0f ||
        SB_Abs(target->cur_pos.x - fp->cur_pos.x) < 45.0f ||
        target->x221C_b6 || SB_Down(target) ||
        ftColl_8007B868(target->gobj) != 0)
    {
        SB_Stop(fp, s, "dance yields: pressure/punish/clearance");
        return false;
    }
    if (s->age >= 24 ||
        (s->dance_turns >= 2 && fp->motion_id == ftCo_MS_Dash &&
         fp->cur_anim_frame >= 3.0f))
    {
        SB_Stop(fp, s, "dance complete; vanilla resumes");
        return false;
    }
    /* Fresh forward Dash cannot reverse during its first four frames. Hold
     * the absolute world direction through Turn; never force facing/timers. */
    if (fp->motion_id == ftCo_MS_Dash && fp->cur_anim_frame > 5.0f &&
        fp->facing_dir * s->dance_direction > 0.0f && s->dance_turns < 2)
    {
        s->dance_direction = -s->dance_direction;
        ++s->dance_turns;
    }
    next = fp->cur_pos.x + s->dance_direction * 22.0f;
    if (next <= left.x + 18.0f || next >= right.x - 18.0f) {
        SB_Stop(fp, s, "dance yields: insufficient next-leg runway");
        return false;
    }
    ftCo_800B4A78(fp);
    fp->cpu.xA4 = 0;
    /* A takeover during EARLY forward Dash also needs a fresh reversal.
     * Do not spend that initial flick inside retail's unturnable frames. */
    if (s->age != 0 &&
        !(fp->motion_id == ftCo_MS_Dash && fp->cur_anim_frame <= 4.0f &&
          fp->facing_dir * s->dance_direction < 0.0f))
    {
        ftCo_800B46B8(fp, CpuCmd_SetLstickX,
                     (u8) (s->dance_direction * 127));
    }
    ftCo_800B49F4(fp);
    ++s->age;
    return true;
}

/* Build at most five bytes per frame. Vanilla arbitration still runs before
 * this hook; forced states can cancel us before the interpreter executes. */
static bool SB_Input(Fighter* fp, SB_State* s, Fighter* target)
{
    int duration = s->action == SB_SWAGGER ? 22 : 3;
    bool compatible = SB_GroundFree(fp);
    float distance = SB_Abs(target->cur_pos.x - fp->cur_pos.x);
    if (s->action == SB_DANCE) {
        return SB_DanceInput(fp, s, target);
    }
    if (s->action == SB_SWAGGER &&
        ((fp->cpu.x18 != 1 && fp->cpu.x18 != 10) || target->x221C_b6 ||
         SB_Down(target)))
    {
        int selected = fp->cpu.xA4;
        SB_Stop(fp, s, "swagger yields: real punish/priority");
        fp->cpu.xA4 = selected;
        return false;
    }
    if (s->action == SB_TAUNT && s->age < 2 && !SB_TauntSafe(fp, target)) {
        SB_Stop(fp, s, "cancelled: taunt reset budget expired");
        return false;
    }
    if (s->action == SB_TAUNT && s->age == 0 && !SB_GroundFree(fp)) {
        /* Let retail friction/action transitions settle a running KO winner.
         * No fabricated Wait or shortened RunBrake; recheck the reset budget
         * and signed runway every update, and never press Up while unready. */
        if (s->taunt_settle >= 18 || !SB_TauntMovement(fp)) {
            SB_Stop(fp, s, "cancelled: couldn't settle safely for taunt");
            return false;
        }
        ftCo_800B4A78(fp);
        fp->cpu.xA4 = 0;
        ftCo_800B49F4(fp);
        ++s->taunt_settle;
        return true;
    }
    if (s->action == SB_TAUNT && s->age >= 2) {
        compatible = fp->motion_id == ftCo_MS_AppealSR ||
                     fp->motion_id == ftCo_MS_AppealSL;
        if (s->age == 2 && compatible) {
            SB_Log(fp, s, "TAUNT acknowledged by normal action state");
        }
    }
    if (s->action == SB_PUNCH && s->age >= 2) {
        compatible = fp->motion_id == ftCa_MS_SpecialN;
        if (s->age == 2 && compatible) {
            SB_Log(fp, s, "PUNCH acknowledged by normal action state");
        }
    }
    if (!SB_Interior(fp) || !compatible || fp->x2219_b5 ||
        (s->action == SB_SWAGGER &&
         (distance < 32.0f || mpColl_IsOnPlatform(&fp->coll_data))) ||
        (s->action == SB_PUNCH && s->age < 2 && !SB_Standing(fp)) ||
        (s->action == SB_TAUNT && !SB_Dead(target) && distance < 70.0f) ||
        (s->action == SB_PUNCH && ftColl_8007B868(target->gobj) != 0))
    {
        SB_Stop(fp, s, "cancelled: danger/incompatible state");
        return false;
    }
    if (s->age >= duration) {
        SB_Stop(fp, s, "input sequence complete; vanilla resumes");
        return false;
    }
    ftCo_800B4A78(fp);
    fp->cpu.xA4 = 0; /* arbitration may have cached a vanilla selection */
    if (s->action == SB_TAUNT && s->age == 1) {
        ftCo_800B463C(fp, CpuCmd_PressUp);
    } else if (s->action == SB_PUNCH && s->age == 1) {
        ftCo_800B463C(fp, CpuCmd_PressB);
    } else if (s->action == SB_SWAGGER &&
               (s->age < 8 || (s->age >= 14 && s->age < 21)))
    {
        ftCo_800B46B8(fp, CpuCmd_SetLstickY, (u8) -100);
    }
    ftCo_800B49F4(fp);
    ++s->age;
    return true;
}

static bool SB_Update(Fighter* fp)
{
    SB_State* s;
    Fighter* target;
    Fighter_GObj* target_gobj;
    int slot;
    int stocks;
    int target_stocks;
    float dealt;
    float taken;
    float dx;
    float dy;
    bool dead;
    bool danger;
    bool whiff;
    bool vulnerable;
    bool stock_match;
    bool stock_lost;
    bool spawned;

    if (fp->player_id >= SB_SLOTS) {
        return false;
    }
    s = &sb_states[fp->player_id];
    if (!SB_Eligible(fp)) {
        if (s->owner == fp) {
            ShowboatCombat_Update(fp, NULL);
            SB_Stop(fp, s, "disabled: CPU configuration changed");
            ShowboatAI_ResetSlot(fp->player_id);
        }
        return false;
    }
    slot = SB_OpponentSlot(fp);
    target_gobj = slot >= 0 ? Player_GetEntity(slot) : NULL;
    if (target_gobj == NULL ||
        (Player_GetEntityAtIndex(slot, 1) != NULL &&
         Player_GetEntityAtIndex(slot, 1) != target_gobj &&
         !GET_FIGHTER(Player_GetEntityAtIndex(slot, 1))->x221F_b3))
    {
        ShowboatCombat_Update(fp, NULL);
        SB_Stop(fp, s, "cancelled: lost singles opponent");
        ShowboatAI_ResetSlot(fp->player_id);
        return false;
    }
    target = GET_FIGHTER(target_gobj);
    if (ftCo_IsAlly(fp, target)) {
        ShowboatCombat_Update(fp, NULL);
        SB_Stop(fp, s, "disabled: ally only");
        ShowboatAI_ResetSlot(fp->player_id);
        return false;
    }
    stocks = Player_GetStocks(fp->player_id);
    target_stocks = Player_GetStocks(slot);
    dead = SB_Dead(target);
    stock_match = gm_8016B094();
    if (s->owner != fp || s->opponent_slot != slot) {
        if (s->owner == fp) {
            ShowboatCombat_Update(fp, NULL);
            SB_Stop(fp, s, "cancelled: opponent identity changed");
        }
        ShowboatAI_ResetSlot(fp->player_id);
        s->owner = fp;
        s->spawn = fp->x8_spawnNum;
        s->opponent_slot = slot;
        s->ego = SB_BASE_EGO;
        s->percent = fp->dmg.x1830_percent;
        s->opponent_percent = target->dmg.x1830_percent;
        s->stocks = stocks;
        s->opponent_stocks = target_stocks;
        s->opponent_dead = dead;
        s->random = fp->x8_spawnNum * 747796405U + fp->player_id + 1;
        SB_Log(fp, s, "initialized normal Level 9 Falcon (singles)");
    }
    SB_Countdown(&s->cooldown);
    SB_Countdown(&s->taunt_cooldown);
    SB_Countdown(&s->serious);
    SB_Countdown(&s->recent_style);
    SB_Countdown(&s->celebration);
    SB_Countdown(&s->ko_lockout);
    SB_Countdown(&s->bias_log_cooldown);
    SB_Countdown(&s->toy_frames);

    spawned = s->spawn != fp->x8_spawnNum;
    stock_lost = stock_match && stocks < s->stocks;
    if (spawned || stock_lost) {
        /* Pair accounting and respawn even if a reset changes observation
         * order. Neither halves nor their separation use cooldown heuristics. */
        if (!((spawned && s->stock_loss_pending) ||
              (stock_lost && s->spawn_loss_pending)))
        {
            SB_Ego(fp, s, -15, "lost stock / new life");
        }
        if (spawned && stock_lost) {
            s->stock_loss_pending = false;
            s->spawn_loss_pending = false;
        } else if (spawned) {
            s->spawn_loss_pending = !s->stock_loss_pending;
            s->stock_loss_pending = false;
        } else {
            s->stock_loss_pending = !s->spawn_loss_pending;
            s->spawn_loss_pending = false;
        }
        ShowboatCombat_Update(fp, NULL);
        ShowboatCombat_ResetSlot(fp->player_id);
        SB_Stop(fp, s, "cancelled: new life");
        s->serious = 120;
        s->celebration = 0;
        s->toy_frames = 0;
        s->percent = fp->dmg.x1830_percent;
        s->spawn = fp->x8_spawnNum;
    }
    taken = fp->dmg.x1830_percent - s->percent;
    dealt = target->dmg.x1830_percent - s->opponent_percent;
    if (taken > 0.0f) {
        SB_Ego(fp, s, -(3 + (int) (taken * 0.5f)), "took damage");
        if (s->recent_style > 0) {
            SB_Ego(fp, s, -10, "punished for showing off");
            s->recent_style = 0;
        }
        s->serious = SB_SERIOUS_FRAMES;
        s->celebration = 0;
        s->toy_frames = 0;
        SB_Stop(fp, s, "cancelled: hit");
    } else if (dealt > 0.0f && !dead && !SB_Forced(fp)) {
        int gain = 2 + (int) (dealt * 0.4f);
        SB_Ego(fp, s, gain > 12 ? 12 : gain, "opponent took damage");
        if (fp->motion_id == ftCa_MS_SpecialN ||
            fp->motion_id == ftCo_MS_AttackAirF ||
            fp->motion_id == ftCo_MS_AttackAirLw)
        {
            SB_Ego(fp, s, 8, "flashy hit (approximate)");
            s->celebration = 120;
        }
    }
    if (((dead && !s->opponent_dead) ||
         (stock_match && target_stocks < s->opponent_stocks)) &&
        s->ko_lockout == 0)
    {
        SB_Ego(fp, s, 22, "opponent stock/death event");
        s->celebration = 180;
        s->toy_frames = 0;
        s->ko_lockout = 240;
    }
    s->stocks = stocks;
    s->opponent_stocks = target_stocks;
    s->percent = fp->dmg.x1830_percent;
    s->opponent_percent = target->dmg.x1830_percent;
    s->opponent_dead = dead;

    /* xFA_b5 is recomputed by vanilla's floor-below/blast-zone query.
     * This is a veto, not a claim that floor-below guarantees recovery. */
    danger = SB_Forced(fp) ||
             (fp->ground_or_air == GA_Air && !fp->cpu.xFA_b5);
    if (danger) {
        s->toy_frames = 0;
        if (!s->danger && fp->motion_id >= ftCo_MS_Wait &&
            fp->motion_id < ftCo_MS_Entry)
        {
            SB_Ego(fp, s, -4, "launched/offstage danger");
        }
        if (s->serious < 30) {
            s->serious = 30;
        }
    }
    s->danger = danger;
    if (++s->tick >= SB_ADVANTAGE_PERIOD) {
        s->tick = 0;
        if (!danger && s->serious == 0 && !dead &&
            ((stock_match && stocks > target_stocks) ||
             target->dmg.x1830_percent - fp->dmg.x1830_percent >= 30.0f ||
             (target->dmg.x1830_percent >= 100.0f &&
              fp->dmg.x1830_percent < 80.0f)))
        {
            SB_Ego(fp, s, 4, "sustained advantage");
        } else if (s->ego > SB_BASE_EGO) {
            SB_Ego(fp, s, -1, "confidence settling");
        }
    }
    dx = target->cur_pos.x - fp->cur_pos.x;
    dy = SB_Abs(target->cur_pos.y - fp->cur_pos.y);
    /* A deliberately approximate 'you swung the wrong way', not frame data. */
    whiff = !dead && target->ground_or_air == GA_Ground && dy < 12.0f &&
            SB_Abs(dx) > 45.0f && SB_Abs(dx) < 85.0f &&
            dx * target->facing_dir > 0.0f &&
            target->motion_id >= ftCo_MS_Attack11 &&
            target->motion_id <= ftCo_MS_AttackLw4 &&
            target->cur_anim_frame >= 18.0f;
    vulnerable = !dead && target->motion_id == ftCo_MS_Furafura &&
                 target->grab_timer > 300.0f && dy < 12.0f &&
                 SB_Abs(dx) >= 18.0f && SB_Abs(dx) <= 42.0f &&
                 dx * fp->facing_dir > 0.0f;
    /* Observe event endings even during cooldown/forced states. Consume only
     * an actual eligible roll, not an opportunity seen during our own lag. */
    if (!whiff) {
        s->whiff = false;
    }
    if (!vulnerable) {
        s->vulnerable = false;
    }
    /* A certified KO reset overrides emotional caution, NEVER physical
     * danger. It has its own cooldown, so a tiny shuffle cannot suppress it. */
    if (!danger && !fp->x2219_b5 &&
        (fp->cpu.x18 == 1 || fp->cpu.x18 == 10))
    {
        if (s->action == SB_TAUNT) {
            return SB_Input(fp, s, target);
        }
        if (s->celebration > 0 && s->taunt_cooldown == 0 &&
            (SB_GroundFree(fp) || SB_TauntMovement(fp)) &&
            SB_TauntSafe(fp, target))
        {
            SB_Stop(fp, s, "KO reset takes precedence over flourish");
            s->celebration = 0;
            SB_Start(fp, s, SB_TAUNT, "starting TAUNT: certified KO reset");
            return SB_Input(fp, s, target);
        }
    }
    /* Technical competence is independent of ego and serious-mode duration.
     * The combat module has its own physical/priority/intercept vetoes. */
    if (ShowboatCombat_Update(fp, target)) {
        if (s->action != SB_NONE) {
            SB_Log(fp, s, "flourish yields to combat conversion");
            s->action = SB_NONE; /* preserve the new combat script */
        }
        return true;
    }
    if (s->action == SB_DANCE) {
        if (danger || s->serious) {
            SB_Stop(fp, s, "dance yields: physical danger/caution");
            return false;
        }
        return SB_DanceInput(fp, s, target);
    }
    /* No override of defense, recovery, grabs, ledges or forced scenarios.
     * Vanilla priority arbitration has already run on this frame. */
    if (danger || s->serious || fp->x2219_b5 ||
        !(fp->cpu.x18 == 1 || fp->cpu.x18 == 2 || fp->cpu.x18 == 3 ||
          fp->cpu.x18 == 8 || fp->cpu.x18 == 10))
    {
        SB_Stop(fp, s, "cancelled: serious/vanilla priority");
        return false;
    }
    if (s->action != SB_NONE) {
        return SB_Input(fp, s, target);
    }
    if (s->cooldown == 0 && s->ego >= 40 && !dead &&
        (fp->cpu.x18 == 1 || fp->cpu.x18 == 10) && fp->cpu.xA4 == 0 &&
        fp->cpu.csP == NULL && fp->cpu.command_duration == 0 &&
        (SB_Standing(fp) || fp->motion_id == ftCo_MS_Dash) &&
        !target->x221C_b6 && !SB_Down(target) && dy < 20.0f &&
        SB_Abs(dx) >= 55.0f && SB_Abs(dx) <= 115.0f &&
        ftColl_8007B868(target->gobj) == 0)
    {
        Vec3 left, right;
        if (SB_Court(fp, &left, &right, 40.0f)) {
            s->cooldown = 45; /* failed rolls do not repeat every update */
            if (SB_Roll(s, 75)) {
                s->dance_direction = dx > 0.0f ? -1 : 1;
                s->dance_turns = 0;
                s->dance_floor = fp->coll_data.floor.index;
                s->dance_origin = fp->cur_pos.x;
                SB_Start(fp, s, SB_DANCE, "starting DANCE: baiting neutral reset");
                s->cooldown = s->ego >= 80 ? 60 : SB_STYLE_COOLDOWN;
                return SB_DanceInput(fp, s, target);
            }
        }
    }
    if (s->cooldown || !SB_Interior(fp) || !SB_GroundFree(fp) ||
        fp->item_gobj != NULL || SB_Abs(fp->self_vel.x) > 1.0f)
    {
        return false;
    }
    if (ftColl_8007B868(target->gobj) == 0) {
        if (vulnerable && !s->vulnerable && s->ego >= 75 && SB_Standing(fp)) {
            s->vulnerable = true;
            if (SB_Roll(s, 35)) {
                SB_Start(fp, s, SB_PUNCH,
                         "starting PUNCH: long shield-break daze");
            }
        } else if (whiff && !s->whiff && s->ego >= 45 &&
                   (fp->cpu.x18 == 1 || fp->cpu.x18 == 10) &&
                   fp->cpu.xA4 == 0 && fp->cpu.csP == NULL &&
                   fp->cpu.command_duration == 0 && SB_Abs(dx) >= 70.0f &&
                   !mpColl_IsOnPlatform(&fp->coll_data))
        {
            s->whiff = true;
            if (SB_Roll(s, 50)) {
                SB_Start(fp, s, SB_SWAGGER,
                         "starting SWAGGER: opponent swung away");
            }
        }
    }
    return s->action != SB_NONE ? SB_Input(fp, s, target) : false;
}

bool ShowboatAI_Update(Fighter* fp)
{
    bool owns_input;
    /* Restore a prior borrowed analog channel before any slot reset, missing
     * target, eligibility gate or certified-taunt early return can bypass it. */
    ShowboatCombat_RestoreInput(fp);
    owns_input = SB_Update(fp);
#if SHOWBOAT_AI_HUD
    if (fp->player_id < SB_SLOTS) {
        SB_State* s = &sb_states[fp->player_id];
        if (s->owner == fp) {
            int action = s->action != SB_NONE ? s->action :
                         ShowboatCombat_GetAction(fp);
            if (action == 0 && s->toy_frames > 0) {
                action = 8; /* JUGGLE: recent control-over-finisher bias */
            }
            ShowboatHUD_Update(fp, s->ego, action, s->serious);
        }
    }
#endif
    return owns_input;
}

void ShowboatAI_PostInput(Fighter* fp)
{
    if (SB_Eligible(fp) && sb_states[fp->player_id].owner == fp) {
        ShowboatCombat_PostInput(fp);
    }
}

float ShowboatAI_AttackWeight(Fighter* fp, void* table, int command,
                             float weight)
{
    SB_State* s;
    float factor;
    if (!SB_Eligible(fp)) {
        return weight;
    }
    s = &sb_states[fp->player_id];
    if (s->owner != fp || s->spawn != fp->x8_spawnNum || s->ego <= 45 ||
        s->serious || s->danger || SB_Forced(fp) || fp->x2219_b5 ||
        fp->dmg.x1830_percent > s->percent ||
        fp->dmg.x1830_percent >= 110.0f || !fp->cpu.xFA_b5 ||
        fp->cpu.x18 == 4 || fp->cpu.x18 == 6 || fp->cpu.x18 == 7 ||
        fp->cpu.x18 == 15 || fp->cpu.x18 == 18)
    {
        return weight;
    }
    /* Verified in US 1.02 PlCo.dat: air script 8 = forward-A (Knee),
     * 10 = down-A (Stomp). Script 10 also exists as a GROUNDED down-A:
     * table identity is essential. Never mutate the shared archive tables. */
    if (table != Fighter_804D64FC->x8[FTKIND_CAPTAIN] ||
        fp->ground_or_air != GA_Air)
    {
        return weight;
    }
    /* Selective mercy, not a claim of guaranteed nonlethality. At a huge
     * stock/percent lead and central hitstun advantage, favor an ALREADY
     * ELIGIBLE up-air (verified script 6) over Knee. Never refuse all attacks,
     * hold the rival in place, or prevent a stock from ending. */
    if (s->ego >= 90 && gm_8016B094() && fp->dmg.x1830_percent <= 40.0f &&
        s->opponent_slot >= 0 && s->opponent_slot < SB_SLOTS &&
        Player_GetStocks(fp->player_id) >= Player_GetStocks(s->opponent_slot) + 2)
    {
        Fighter_GObj* rival_gobj = Player_GetEntity(s->opponent_slot);
        if (rival_gobj != NULL) {
            Fighter* rival = GET_FIGHTER(rival_gobj);
            StKind stage = Stage_80225194();
            if ((stage == St_Kind_Battle || stage == St_Kind_Last) &&
                rival->dmg.x1830_percent >= 80.0f && rival->x221C_b6 &&
                SB_Abs(fp->cur_pos.x) < 45.0f &&
                SB_Abs(rival->cur_pos.x) < 45.0f &&
                (command == 6 || command == 8))
            {
                if (s->toy_frames == 0) {
                    SB_Log(fp, s, "JUGGLE: huge lead, prefer control over Knee");
                }
                s->toy_frames = 45;
                return weight * (command == 6 ? 4.0f : 0.35f);
            }
        }
    }
    if (command != 8 && command != 10) {
        return weight;
    }
    factor = 1.0f + 2.0f * (s->ego - 45) / 55.0f;
    if (s->bias_log_cooldown == 0) {
        SB_Log(fp, s, "eligible Knee/Stomp weight boosted (not forced)");
        s->bias_log_cooldown = 120;
    }
    return weight * factor;
}
