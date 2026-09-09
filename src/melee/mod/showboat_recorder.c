/* Read-only, game-thread schema-v1 observer. No saved Fighter token is ever
 * dereferenced: reacquire primary entities before reading either argument.
 * This records observed intervals, not complete matches or attributed hits. */
#include "showboat_recorder.h"

#if SHOWBOAT_RECORDER
#include <melee/ft/fighter.h>
#include <melee/ft/ftcoll.h>
#include <melee/ft/kinds/ftCommon/ftCo_0A01.h>
#include <melee/ft/kinds/ftCommon/forward.h>
#include <melee/ft/types.h>
#include <melee/gm/gm_16AE.h>
#include <melee/gm/gm_1A3F.h>
#include <melee/mn/types.h>
#include <melee/pl/player.h>
#include <sysdolphin/baselib/gobj.h>
#include <dolphin/os.h>
#include <string.h>

#define SR_SLOTS 6
#define SR_INTERVAL 12
#define SR_FLUSH 60
#define SR_EVENTS 127U
#define SR_MAX_U32 0xFFFFFFFFU

typedef struct {
    int spawn, kind, motion, stocks;
    float anim, x, y, vx, vy, ground_v, percent, shield;
    unsigned flags;
} SR_Fighter;

typedef struct {
    SR_Fighter self, rival;
    int ego, action, owns, priority, cached_attack, threat;
    unsigned buttons;
    int lx, ly, cx, cy, lt, rt;
} SR_Sample;

typedef struct {
    int stage, mode, match_kind, teams, stock, friendly_fire, is_vs;
    int timer, counts_up, item_frequency, sd_penalty;
    u32 time_limit;
    u64 items;
    float damage, speed;
} SR_Context;

typedef struct {
    bool ready;
    u32 frame;
    s32 spawn;
    u8 reasons[SBR_TACTICS];
    unsigned events;
    int ego, action, owns;
} SR_Update;

typedef struct {
    bool active, have_sample, gap;
    Fighter* target; /* comparison token only */
    s32 spawn, target_spawn;
    int target_slot, target_kind;
    SR_Context context;
    u32 id, observations, last_frame, sample_frame, from, batch;
    unsigned updates, gates[SBR_TACTICS][SBR_REASONS];
    SR_Sample sample;
} SR_Segment;

typedef struct {
    Fighter* owner; /* comparison token only */
    SR_Update pending; /* independent of segment opening/splitting */
    SR_Segment run;
    /* Preserve the per-slot output cap across Reset and same-frame splits. */
    bool emitted;
    u32 emitted_frame;
} SR_State;

static SR_State sr_states[SR_SLOTS];
/* Capture-local, not a native match ID. Exhaustion stops opening segments;
 * neither slot reset nor frame rollback can reuse an ID. */
static u32 sr_next_id;

static bool SR_Finite(float x)
{
    /* IEEE f32 maximum; this checkout's freestanding MSL has no float.h. */
    return x >= -3.402823466e38F && x <= 3.402823466e38F;
}

static void SR_Flush(SR_Segment* s, int slot)
{
    int tactic, reason;
    if (s->updates == 0) { return; }
    ++s->batch; /* Distinguishes flushes even if the native clock is unchanged. */
    for (tactic = 0; tactic < SBR_TACTICS; ++tactic) {
        for (reason = 0; reason < SBR_REASONS; ++reason) {
            unsigned n = s->gates[tactic][reason];
            if (n != 0) {
                OSReport("SBREC {\"v\":1,\"type\":\"gate\",\"segment\":%u,"
                         "\"slot\":%d,\"frame\":%u,\"from\":%u,\"tactic\":%d,"
                         "\"reason\":%d,\"count\":%u,\"batch\":%u}\n",
                         (unsigned) s->id, slot, (unsigned) s->last_frame,
                         (unsigned) s->from, tactic, reason, n, (unsigned) s->batch);
            }
        }
    }
    memset(s->gates, 0, sizeof(s->gates));
    s->updates = 0;
}

static void SR_End(SR_State* state, int slot, const char* reason)
{
    SR_Segment* s = &state->run;
    if (s->active) {
        SR_Flush(s, slot);
        /* Close on the last observed native frame, including on rollback.
         * Never invent observations between that frame and a lifecycle call. */
        OSReport("SBREC {\"v\":1,\"type\":\"end\",\"segment\":%u,\"slot\":%d,"
                 "\"frame\":%u,\"reason\":\"%s\",\"observations\":%u}\n",
                 (unsigned) s->id, slot, (unsigned) s->last_frame, reason,
                 (unsigned) s->observations);
    }
    memset(s, 0, sizeof(*s));
}

void ShowboatRecorder_ResetSlot(int slot)
{
    SR_State* s;
    if (slot < 0 || slot >= SR_SLOTS) { return; }
    s = &sr_states[slot];
    SR_End(s, slot, "reset");
    s->owner = NULL;
    memset(&s->pending, 0, sizeof(s->pending));
}

void ShowboatRecorder_Suspend(Fighter* fp)
{
    int i;
    if (fp == NULL) { return; }
    /* Even fp itself may be a retired identity token at teardown. */
    for (i = 0; i < SR_SLOTS; ++i) {
        SR_State* s = &sr_states[i];
        if (s->owner == fp) {
            SR_End(s, i, "suspend");
            s->owner = NULL;
            memset(&s->pending, 0, sizeof(s->pending));
        }
    }
}

static int SR_Primary(Fighter* token)
{
    int i;
    if (token == NULL) { return -1; }
    for (i = 0; i < SR_SLOTS; ++i) {
        Fighter_GObj* gobj;
        if (Player_GetPlayerState(i) != 2) { continue; }
        gobj = Player_GetEntity(i);
        if (gobj != NULL && GET_FIGHTER(gobj) == token) {
            /* Only now is token a live primary Fighter. */
            if (token->player_id == i && token->gobj == gobj &&
                !token->x221F_b4 && Player_GetEntityAtIndex(i, 1) == NULL)
            { return i; }
            return -1;
        }
    }
    return -1;
}

static SR_State* SR_Bind(Fighter* fp)
{
    int slot = SR_Primary(fp);
    SR_State* s;
    if (slot < 0) { ShowboatRecorder_Suspend(fp); return NULL; }
    s = &sr_states[slot];
    if (s->owner != fp) {
        SR_End(s, slot, "identity");
        memset(&s->pending, 0, sizeof(s->pending));
        s->owner = fp;
    }
    if (fp->kind != FTKIND_CAPTAIN || fp->cpu.xC != 4 ||
        fp->cpu.level != 9 || !ftCo_800A2040(fp))
    {
        SR_End(s, slot, "ineligible");
        memset(&s->pending, 0, sizeof(s->pending));
        return NULL;
    }
    return s;
}

static void SR_Pending(SR_State* s, Fighter* fp, bool begin)
{
    u32 frame = gm_GetFrameCount();
    if (begin || !s->pending.ready || s->pending.frame != frame ||
        s->pending.spawn != fp->x8_spawnNum)
    {
        memset(&s->pending, 0, sizeof(s->pending));
        s->pending.ready = true;
        s->pending.frame = frame;
        s->pending.spawn = fp->x8_spawnNum;
    }
}

void ShowboatRecorder_Begin(Fighter* fp)
{
    SR_State* s = SR_Bind(fp);
    if (s != NULL) { SR_Pending(s, fp, true); }
}

void ShowboatRecorder_Reason(Fighter* fp, int tactic, int reason)
{
    SR_State* s;
    if (tactic < 0 || tactic >= SBR_TACTICS ||
        reason < 0 || reason >= SBR_REASONS) { return; }
    s = SR_Bind(fp);
    if (s != NULL) {
        SR_Pending(s, fp, false);
        s->pending.reasons[tactic] = (u8) reason;
    }
}

void ShowboatRecorder_Event(Fighter* fp, unsigned mask)
{
    SR_State* s = SR_Bind(fp);
    if (s != NULL) {
        SR_Pending(s, fp, false);
        s->pending.events |= mask & SR_EVENTS;
    }
}

void ShowboatRecorder_Decision(Fighter* fp, int ego, int action, bool owns)
{
    SR_State* s = SR_Bind(fp);
    if (s != NULL) {
        SR_Pending(s, fp, false);
        s->pending.ego = ego < 0 ? 0 : ego > 100 ? 100 : ego;
        s->pending.action = action >= 0 && action <= 11 ? action : 0;
        s->pending.owns = owns != 0;
    }
}

static int SR_Rival(Fighter* fp, Fighter* target)
{
    int i, other = -1;
    for (i = 0; i < SR_SLOTS; ++i) {
        if (Player_GetPlayerState(i) != 2) { continue; }
        if (Player_GetEntityAtIndex(i, 1) != NULL) { return -1; }
        if (i != fp->player_id) {
            if (other >= 0) { return -1; }
            other = i;
        }
    }
    /* Do not dereference target until it matches the sole live primary. */
    if (other < 0 || SR_Primary(target) != other || target == fp) { return -1; }
    return ftCo_IsAlly(fp, target) ? -1 : other;
}

static bool SR_GetContext(SR_Context* c)
{
    struct StartMeleeRules* r = gm_GetRules();
    if (r == NULL || !SR_Finite(r->x30) || !SR_Finite(r->game_speed))
    { return false; }
    memset(c, 0, sizeof(*c));
    /* gm_GetStKind returns rules.stkind, the global StKind enum (Battle=31,
     * Last=32), NOT an internal map ID. No stage allowlist for telemetry. */
    c->stage = gm_GetStKind();
    c->mode = gm_GetCurrentGameMode();
    c->match_kind = r->match_kind;
    c->teams = r->is_teams;
    c->stock = r->is_stock;
    c->friendly_fire = r->friendly_fire;
    c->is_vs = r->is_vs;
    c->timer = r->timer_enabled;
    c->counts_up = r->timer_counts_up;
    c->time_limit = r->time_limit;
    c->item_frequency = r->xB;
    c->sd_penalty = r->xC;
    c->items = r->x20;
    c->damage = r->x30;
    c->speed = r->game_speed;
    return true;
}

static bool SR_ContextChanged(SR_Context* a, SR_Context* b)
{
    return a->stage != b->stage || a->mode != b->mode ||
        a->match_kind != b->match_kind || a->teams != b->teams ||
        a->stock != b->stock || a->friendly_fire != b->friendly_fire ||
        a->is_vs != b->is_vs || a->timer != b->timer ||
        a->counts_up != b->counts_up || a->time_limit != b->time_limit ||
        a->item_frequency != b->item_frequency || a->sd_penalty != b->sd_penalty ||
        a->items != b->items || a->damage != b->damage || a->speed != b->speed;
}

static bool SR_Captured(Fighter* fp)
{
    int m = fp->motion_id;
    /* State IDs, not stale motion-union pointers (nor the attacker's victim
     * pointer). No union member is inspected in an unrelated motion. */
    return (m >= ftCo_MS_CapturePulledHi && m <= ftCo_MS_CaptureFoot) ||
        (m >= ftCo_MS_ThrownF && m <= ftCo_MS_ThrownlwWomen) ||
        (m >= ftCo_MS_ShoulderedWait && m <= ftCo_MS_ThrownKirby) ||
        (m >= ftCo_MS_CaptureMewtwo && m <= ftCo_MS_ThrownMewtwoAir) ||
        (m >= ftCo_MS_CaptureMasterHand && m <= ftCo_MS_CaptureLikelike) ||
        (m >= ftCo_MS_CaptureCrazyHand && m <= ftCo_MS_ThrownCrazyHand);
}

static bool SR_Observe(Fighter* fp, SR_Fighter* out, unsigned items)
{
    out->spawn = fp->x8_spawnNum;
    out->kind = fp->kind;
    out->motion = fp->motion_id;
    out->anim = fp->cur_anim_frame;
    out->x = fp->cur_pos.x;
    out->y = fp->cur_pos.y;
    out->vx = fp->self_vel.x;
    out->vy = fp->self_vel.y;
    out->ground_v = fp->gr_vel;
    out->percent = fp->dmg.x1830_percent;
    out->stocks = Player_GetStocks(fp->player_id);
    out->shield = fp->shield_health;
    out->flags = items |
        (fp->ground_or_air == GA_Air ? 1U : 0U) |
        (fp->x221C_b6 ? 2U : 0U) | (fp->x2219_b5 ? 4U : 0U) |
        (fp->x221F_b3 ? 8U : 0U) | (fp->item_gobj != NULL ? 16U : 0U) |
        (SR_Captured(fp) ? 32U : 0U) |
        (ftColl_8007B868(fp->gobj) != 0 ? 64U : 0U);
    return SR_Finite(out->anim) && SR_Finite(out->x) && SR_Finite(out->y) &&
        SR_Finite(out->vx) && SR_Finite(out->vy) && SR_Finite(out->ground_v) &&
        SR_Finite(out->percent) && SR_Finite(out->shield);
}

static bool SR_FighterChanged(SR_Fighter* a, SR_Fighter* b)
{
    return a->spawn != b->spawn || a->motion != b->motion ||
        a->stocks != b->stocks || a->percent != b->percent ||
        a->flags != b->flags || a->kind != b->kind;
}

static bool SR_Changed(SR_Sample* a, SR_Sample* b)
{
    return SR_FighterChanged(&a->self, &b->self) ||
        SR_FighterChanged(&a->rival, &b->rival) || a->priority != b->priority ||
        a->action != b->action || a->owns != b->owns ||
        a->buttons != b->buttons || a->lt != b->lt || a->rt != b->rt;
}

/* One bounded call/line, no strings from gameplay, no pointer serialization.
 * Nine significant digits round-trip native f32; even FLT_MAX is bounded in
 * %g notation. Worst-case schema-v1 sample is less than 1024 bytes. */
#define SR_FIGHTER_FMT "[%d,%d,%d,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%d,%.9g,%u]"
#define SR_FIGHTER_ARGS(f) (f).spawn, (f).kind, (f).motion, (f).anim, \
    (f).x, (f).y, (f).vx, (f).vy, (f).ground_v, (f).percent, (f).stocks, \
    (f).shield, (f).flags

static void SR_Emit(SR_Segment* s, int slot, SR_Sample* v, unsigned events,
                    const u8* reasons)
{
    OSReport("SBREC {\"v\":1,\"type\":\"sample\",\"segment\":%u,\"slot\":%d,"
             "\"frame\":%u,\"ego\":%d,\"action\":%d,\"owns\":%d,\"events\":%u,"
             "\"gap\":%d,\"self\":" SR_FIGHTER_FMT ",\"rival\":" SR_FIGHTER_FMT
             ",\"native\":[%d,%d,%d],\"input\":[%u,%d,%d,%d,%d,%d,%d],"
             "\"reasons\":[%d,%d,%d,%d,%d]}\n",
             (unsigned) s->id, slot, (unsigned) s->last_frame,
             v->ego, v->action, v->owns, events,
             s->gap ? 1 : 0, SR_FIGHTER_ARGS(v->self), SR_FIGHTER_ARGS(v->rival),
             v->priority, v->cached_attack, v->threat, v->buttons,
             v->lx, v->ly, v->cx, v->cy, v->lt, v->rt,
             reasons[0], reasons[1], reasons[2], reasons[3], reasons[4]);
}

void ShowboatRecorder_Frame(Fighter* fp, Fighter* target)
{
    SR_State* state = SR_Bind(fp);
    SR_Segment* s;
    SR_Context context;
    SR_Sample sample;
    SR_Update update;
    u32 frame = gm_GetFrameCount();
    unsigned items;
    int slot, rival, i;
    bool valid;
    if (state == NULL) { return; }
    slot = fp->player_id;
    s = &state->run;
    /* Ally's native query also reads rules, so validate context first. */
    if (!SR_GetContext(&context)) {
        SR_End(state, slot, "context");
        memset(&state->pending, 0, sizeof(state->pending));
        return;
    }
    rival = SR_Rival(fp, target);
    if (rival < 0) {
        SR_End(state, slot, "target");
        memset(&state->pending, 0, sizeof(state->pending));
        return;
    }
    if (s->active) {
        const char* end = NULL;
        if (s->target != target || s->target_slot != rival ||
            s->target_kind != (int) target->kind) { end = "identity"; }
        else if (s->spawn != fp->x8_spawnNum ||
                 s->target_spawn != target->x8_spawnNum) { end = "spawn"; }
        else if (frame < s->last_frame) {
            end = "frame_rollback";
            state->emitted = false; /* A new native timeline, not a duplicate. */
        }
        else if (SR_ContextChanged(&s->context, &context)) { end = "context"; }
        else if (s->observations == SR_MAX_U32) { end = "limit"; }
        if (end != NULL) { SR_End(state, slot, end); }
    }
    if (!s->active) {
        if (sr_next_id == SR_MAX_U32) { return; }
        s->active = true;
        s->id = ++sr_next_id;
        s->spawn = fp->x8_spawnNum;
        s->target = target;
        s->target_spawn = target->x8_spawnNum;
        s->target_slot = rival;
        s->target_kind = target->kind;
        s->context = context;
        s->last_frame = frame;
        OSReport("SBREC {\"v\":1,\"type\":\"begin\",\"segment\":%u,\"slot\":%d,"
                 "\"frame\":%u,\"stage\":%d,\"mode\":%d,\"match_kind\":%d,"
                 "\"target\":%d,\"interval\":12}\n", (unsigned) s->id, slot,
                 (unsigned) frame,
                 context.stage, context.mode, context.match_kind, rival);
    } else if (!state->pending.ready && frame == s->last_frame) {
        return; /* Repeated Frame without another observed CPU update. */
    }
    memset(&update, 0, sizeof(update));
    if (state->pending.ready && state->pending.frame == frame &&
        state->pending.spawn == fp->x8_spawnNum)
    { update = state->pending; }
    else { s->gap = true; } /* Missing/mismatched Begin, including AI reset. */
    memset(&state->pending, 0, sizeof(state->pending));
    if (s->observations != 0 && frame > s->last_frame &&
        frame - s->last_frame > 1) { s->gap = true; }
    s->last_frame = frame;
    ++s->observations;
    if (s->updates == 0) { s->from = frame; }
    for (i = 0; i < SBR_TACTICS; ++i) { ++s->gates[i][update.reasons[i]]; }
    ++s->updates;

    items = HSD_GObj_Entities != NULL && HSD_GObj_Entities->items != NULL ? 128U : 0U;
    valid = SR_Observe(fp, &sample.self, items);
    valid = SR_Observe(target, &sample.rival, items) && valid;
    sample.ego = update.ego;
    sample.action = update.action;
    sample.owns = update.owns;
    sample.priority = fp->cpu.x18;
    sample.cached_attack = fp->cpu.xA4;
    sample.threat = fp->cpu.xF8_b12;
    sample.buttons = fp->cpu.buttons;
    sample.lx = fp->cpu.lstick.x;
    sample.ly = fp->cpu.lstick.y;
    sample.cx = fp->cpu.cstick.x;
    sample.cy = fp->cpu.cstick.y;
    sample.lt = fp->cpu.ltrigger;
    sample.rt = fp->cpu.rtrigger;
    if (!valid) {
        s->gap = true; /* Skip non-finite snapshots; next valid row exposes loss. */
    } else if (!s->have_sample || s->gap || update.events != 0 ||
               frame - s->sample_frame >= SR_INTERVAL ||
               SR_Changed(&sample, &s->sample))
    {
        if (!state->emitted || state->emitted_frame != frame) {
            SR_Emit(s, slot, &sample, update.events, update.reasons);
            s->sample = sample;
            s->sample_frame = frame;
            s->have_sample = true;
            s->gap = false;
            state->emitted = true;
            state->emitted_frame = frame;
        } else {
            s->gap = true; /* A second update cannot emit a second row. */
        }
    }
    if (s->updates >= SR_FLUSH) { SR_Flush(s, slot); }
}
#endif
