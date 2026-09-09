#include "gmboot.h"

#include "gm_unsplit.h"
#include "gmmain_lib.h"
#include "types.h"
#include <melee/lb/lbcardgame.h>
#include <melee/lb/lbcardnew.h>
#include <melee/lb/lblanguage.h>
#include <melee/ty/toy.h>

#if SHOWBOAT_QUICKSTART
#include "gmvsmelee.h"
#include <melee/ft/forward.h>
#include <melee/mn/types.h>
#include <melee/pl/forward.h>
#include <dolphin/os.h>
#endif

/* 1BF948 */ static void bootOnLoad(GameModeState*);
/* 1BF9A8 */ static void bootOnLeave(GameModeState*);
/* 1BFA3C */ static void memcardOnLoad(GameModeState*);

/// @todo Move to toy header
enum {
    TROPHY_PIKMIN = 275,
};

struct loadData {
    u32 x0;
    u8 x4;
    u8 mode_id; ///< Copied to ::leaveData::mode_id to set next mode
};

struct leaveData {
    u32 x0;
    u8 mode_id;
};

static struct loadData load_data;
static struct leaveData leave_data;

GameModeState gm_Mode_Boot_States[] = {
    {
        0,
        1,
        0,
        bootOnLoad,
        bootOnLeave,
        GS_MEMCARD,
        &load_data,
        &leave_data,
    },
    {
        -1,
    },
};

void bootOnLoad(GameModeState* scene)
{
    struct loadData* scene_data = gm_GetGameModeStateEnterData(scene);
    scene_data->x4 = 0;
    scene_data->x0 = 0;
    if (gmMainLib_8046B0F0.skip_intro == true) {
        scene_data->mode_id = GM_TITLE;
    } else {
        gm_801BF708(0);
        scene_data->mode_id = GM_OPENING_MV;
    }
}

void bootOnLeave(GameModeState* data)
{
    struct leaveData* scene_data = gm_GetGameModeStateExitData(data);
#if SHOWBOAT_QUICKSTART
    VsModeData* vs;
    int i;
#endif

    if (!Toy_803048C0(TROPHY_PIKMIN)) {
        if (!lb_8001C2D8(0, "01",
                         lbLang_GetLanguageSetting() == LANG_JP ? "GPIJ"
                                                                : "GPIE",
                         "Pikmin dataFile"))
        {
            Toy_803124BC();
            Toy_SetUnlockState(TROPHY_PIKMIN, true);
        }
    }

    gm_SetGameModeOverride(lbCardGame_DecideGameMode);

#if SHOWBOAT_QUICKSTART
    /* Boot exit is AFTER normal save/card initialization and test unlocks.
     * Set menu defaults once, not on every CSS load: results, Back and tester
     * changes retain their normal behavior. Never auto-start a match. */
    (void) scene_data;
    vs = gmVsMelee_GetVsData();
    for (i = 0; i < GM_MAX_PLAYERS; ++i) {
        vs->start.players[i].ckind = CHKIND_NONE;
        vs->start.players[i].slot_type = Gm_PKind_NA;
    }
    vs->start.rules.is_teams = false;
    vs->start.players[0].slot_type = Gm_PKind_Human;
    /* CSS uses EXTERNAL CharacterKind (Captain = 0), not FighterKind (2). */
    vs->start.players[1].ckind = CKIND_CAPTAIN;
    vs->start.players[1].slot_type = Gm_PKind_Cpu;
    vs->start.players[1].color = 0;
    vs->start.players[1].cpu_kind = 4;
    vs->start.players[1].cpu_level = 9;
#if SHOWBOAT_AI_DEBUG
    OSReport("SHOWBOAT QUICKSTART: VS CSS; P1 choose, P2 Captain CPU9 "
             "(ckind=%d type=%d level=%d)\n",
             vs->start.players[1].ckind, vs->start.players[1].slot_type,
             vs->start.players[1].cpu_level);
#endif
    gm_ChangeGameModeAfterCurrentScene(GM_VS);
#else
    gm_ChangeGameModeAfterCurrentScene(scene_data->mode_id);
#endif
}

GameModeState gm_Mode_MemCard_States[] = {
    {
        0,
        3,
        0,
        memcardOnLoad,
        NULL,
        {
            GS_MEMCARD,
            &load_data,
            &leave_data,
        },
    },
    { -1 },
};

void memcardOnLoad(GameModeState* scene)
{
    struct loadData* temp_r3 = gm_GetGameModeStateEnterData(scene);
    temp_r3->x4 = 0;
    temp_r3->x0 = 1;
}
