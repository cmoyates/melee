#ifndef SB_TEST_GAME_H
#define SB_TEST_GAME_H

/* Host-only dependency surface, NOT ABI-compatible game structures. */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef uint8_t u8;
typedef int8_t s8;
typedef uint32_t u32;
typedef int32_t s32;
typedef float f32;
#include "sb_native_enums.h"

typedef struct Fighter Fighter;
typedef struct Fighter_GObj {
    Fighter* user_data;
} Fighter_GObj;
#define GET_FIGHTER(gobj) ((gobj)->user_data)

typedef struct { float x, y, z; } Vec3;
typedef struct { s8 x, y; } TestStick;
typedef struct { bool on_platform; } CollData;
enum { GA_Ground, GA_Air };
enum { HSD_PAD_DPADUP = 0x0008, HSD_PAD_B = 0x0200 };

struct CpuFighter {
    int level, xC, x18, xA4;
    bool xFA_b5;
    u32 buttons;
    TestStick lstick, cstick;
    u8 ltrigger, rtrigger;
    u8 buffer[0x100];
    u8* write_pos;
    u8* csP;
    u32 command_duration;
};

struct Fighter {
    Fighter_GObj* gobj;
    FighterKind kind;
    s32 x8_spawnNum;
    u8 player_id;
    int motion_id;
    int ground_or_air;
    float facing_dir, cur_anim_frame;
    Vec3 cur_pos, self_vel;
    CollData coll_data;
    struct { float x1830_percent; } dmg;
    bool x221F_b3, x221C_b6, x2219_b5;
    void* victim_gobj;
    void* x1A5C;
    void* item_gobj;
    struct CpuFighter cpu;
};

/* Only the table-identity surface used by personality command weighting. */
struct TestFighterData { void* x8[FTKIND_MAX]; };
extern struct TestFighterData* Fighter_804D64FC;

bool mpColl_IsOnPlatform(CollData* data);
bool ftCo_800A2040(Fighter* fp);
float ftCo_800A2A70(Fighter* fp, bool right);
bool ftCo_IsAlly(Fighter* fp, Fighter* target);
int ftColl_8007B868(Fighter_GObj* gobj);
Fighter_GObj* Player_GetEntity(int slot);
Fighter_GObj* Player_GetEntityAtIndex(int slot, int index);
int Player_GetPlayerState(int slot);
int Player_GetStocks(int slot);
bool gm_8016B094(void);
void OSReport(const char* format, ...);
void ftCo_800B4A78(Fighter* fp);
void ftCo_800B463C(Fighter* fp, u8 command);
void ftCo_800B46B8(Fighter* fp, u8 command, u8 argument);
void ftCo_800B49F4(Fighter* fp);

#endif
