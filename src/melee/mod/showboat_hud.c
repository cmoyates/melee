/* Debug-only display: deliberately independent of the showboat AI policy. */
#include "showboat_hud.h"

#if SHOWBOAT_AI_HUD
#include <melee/ft/types.h>
#include <melee/if/textdraw.h>
#include <melee/if/textlib.h>
#include <melee/if/types.h>
#include <melee/pl/player.h>
#include <sysdolphin/baselib/fog.h>
#include <sysdolphin/baselib/gobj.h>
#include <sysdolphin/baselib/gobjgxlink.h>
#include <sysdolphin/baselib/gobjplink.h>
#include <sysdolphin/baselib/gobjuserdata.h>
#include <sysdolphin/baselib/video.h>
#include <stdio.h>
#include <string.h>

#define HUD_SLOTS 6
#define HUD_COLUMNS 64

/* DevText_Draw uses two bytes per cell (character and color index). These
 * private descriptors are never inserted in DevText's shared 32-entry pool or
 * drawlist, so ResetSlot cannot unlink/recycle another debug overlay's text.
 * See DevText_Create/Draw/Print in if/textlib.c and if/textdraw.c. */
typedef struct {
    DevText text;
    char cells[HUD_COLUMNS * 2];
    bool active;
    int ego;
    int action;
    int serious;
} HUD_Row;

static HUD_Row hud_rows[HUD_SLOTS];
static HSD_GObj* hud_gobj;

static void HUD_Removed(void* data)
{
    /* GObj_RemoveUserData calls this on explicit object destruction. Only
     * static storage belongs to us: no fighter/font pointers, no pooled text
     * to free, and no shared camera to destroy. */
    (void) data;
    hud_gobj = NULL;
    memset(hud_rows, 0, sizeof(hud_rows));
}

static void HUD_Draw(HSD_GObj* gobj, int pass)
{
    int i;
    GXColor shadow = { 0, 0, 0, 255 };
    GXColor white = { 255, 255, 255, 255 };
    (void) gobj;
    if ((unsigned int) pass != HSD_RP_BOTTOMHALF) {
        return;
    }

    /* Same setup as DevText_DrawAll. gm_801A4BD4 unconditionally calls
     * un_802FF78C -> DevText_Setup each scene. Reuse that screen-space camera;
     * NEVER call DevText_Setup here (it resets other overlays' pool/camera).
     * DrawASCII's built-in stroke font requires no SIS archive or asset load. */
    HSD_FogSet(NULL);
    DevText_SetupCObj();
    for (i = 0; i < HUD_SLOTS; ++i) {
        DevText* text = &hud_rows[i].text;
        if (!hud_rows[i].active) {
            continue;
        }
        /* A one-pixel shadow keeps the small white text legible on stages
         * without covering gameplay with a background rectangle. */
        ++text->x;
        ++text->y;
        DevText_SetTextColor(text, shadow);
        DevText_Draw(text);
        --text->x;
        --text->y;
        DevText_SetTextColor(text, white);
        DevText_Draw(text);
    }
}

static void HUD_ValidateGObj(void)
{
    HSD_GObj* live;
    if (hud_gobj == NULL) {
        return;
    }
    /* Scene setup (gobjinit.c) replaces the object lists. Do not assume heap
     * resets invoke GObj destructors! Walk only the CURRENT live p_link list,
     * never dereference the cached pointer. The callback and userdata checks
     * also reject an unrelated new GObj allocated at the same address. */
    for (live = ((HSD_GObj**) HSD_GObj_Entities)[24]; live != NULL;
         live = live->next)
    {
        if (live == hud_gobj && live->render_cb == HUD_Draw &&
            live->user_data_remove_func == HUD_Removed &&
            live->user_data == hud_rows)
        {
            return;
        }
    }
    HUD_Removed(NULL);
}

void ShowboatHUD_ResetSlot(int slot)
{
    if (slot >= 0 && slot < HUD_SLOTS) {
        memset(&hud_rows[slot], 0, sizeof(hud_rows[slot]));
    }
    /* Keep the single render GObj until scene exit, even across stock resets.
     * There is no per-row allocation or retained fighter identity. */
}

void ShowboatHUD_Update(Fighter* fp, int ego, int action, int serious)
{
    static char* const names[] = {
        "VANILLA", "TAUNT", "SWAGGER", "PUNCH", "DANCE", "GRAB", "KNEE",
        "UPAIR", "JUGGLE", "WDASH"
    };
    HUD_Row* row;
    DevText* text;
    char line[HUD_COLUMNS];
    int slot;

    if (fp == NULL || fp->player_id >= HUD_SLOTS) {
        return;
    }
    slot = fp->player_id;
    /* Secondary/stale fighters must not overwrite or clear a primary row. */
    if (fp->gobj == NULL || Player_GetEntity(slot) != fp->gobj) {
        return;
    }
    if (fp->kind != FTKIND_CAPTAIN) {
        ShowboatHUD_ResetSlot(slot);
        return;
    }
    HUD_ValidateGObj();
    if (hud_gobj == NULL) {
        /* Same classifier, p_link and GX link as un_802FF78C's DevText_Setup.
         * GX priority 1 draws after the standard debug drawlist (priority 0).
         * The standard debug camera already renders GX link 17 at priority 11.
         * No processes, new cameras, or global text initialization are needed. */
        hud_gobj = GObj_Create(21, 24, 0);
        if (hud_gobj == NULL) {
            return;
        }
        GObj_InitUserData(hud_gobj, 21, HUD_Removed, hud_rows);
        GObj_SetupGXLink(hud_gobj, HUD_Draw, 17, 1);
    }
    if (ego < 0) {
        ego = 0;
    } else if (ego > 100) {
        ego = 100;
    }
    if (action < SHOWBOAT_HUD_VANILLA || action > SHOWBOAT_HUD_WDASH) {
        action = SHOWBOAT_HUD_VANILLA;
    }
    if (serious < 0) {
        serious = 0;
    }
    row = &hud_rows[slot];
    if (row->active && row->ego == ego && row->action == action &&
        row->serious == serious)
    {
        return;
    }
    text = &row->text;
    if (!row->active) {
        /* All other fields are zero from static initialization/reset. Match
         * DevText_Create's layout, but opt out of its pool/list ownership. */
        text->x = 22;
        text->y = (s16) (72 + 18 * slot);
        text->w = HUD_COLUMNS;
        text->h = 1;
        text->buf = row->cells;
        text->line_width = 6;
        text->flags = DEVTEXT_FLAG_NOWRAP | DEVTEXT_FLAG_HIDEBACKGROUND;
        DevText_SetScale(text, 7.0f, 12.0f);
    }
    row->ego = ego;
    row->action = action;
    row->serious = serious;
    /* Stroke font supports parentheses, not square brackets. MSL has no
     * snprintf entry point. With the bounds above and a 32-bit positive int,
     * this fixed format is at most 52 characters plus NUL, fitting line[64].
     * Do not add arbitrary strings here or use DevText_Printf's hidden buffer. */
    sprintf(line, "FALCON P%d EGO %3d /100 (%s) SERIOUS %df", slot + 1, ego,
            names[action], serious);
    DevText_Erase(text);
    DevText_SetCursorXY(text, 0, 0);
    DevText_Print(text, line);
    row->active = true;
}
#endif
