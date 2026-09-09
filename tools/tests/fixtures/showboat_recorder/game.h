#ifndef RECORDER_TEST_GAME_H
#define RECORDER_TEST_GAME_H
/* Typed host dependency surface, NOT a PPC Fighter ABI/physics simulation.
 * CpuFighter and enums are extracted verbatim from this checkout. */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
typedef uint8_t u8;
typedef int8_t s8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;
typedef int32_t s32;
typedef int enum_t;
typedef u32 HSD_Pad;
typedef void* UNK_T;
typedef struct Fighter Fighter;
typedef struct Item Item;
typedef struct { float x, y; } Vec2;
typedef struct { float x, y, z; } Vec3;
typedef struct { s8 x, y; } S8Vec2;
#include "native_enums.h"
#include "native_cpu.h"

typedef struct Fighter_GObj { Fighter* user_data; } Fighter_GObj;
#define GET_FIGHTER(gobj) ((gobj)->user_data)
struct Fighter {
    Fighter_GObj* gobj;
    FighterKind kind;
    s32 x8_spawnNum;
    u8 player_id, team;
    int motion_id;
    GroundOrAir ground_or_air;
    float cur_anim_frame, gr_vel, shield_health;
    Vec3 cur_pos, self_vel;
    struct { float x1830_percent; } dmg;
    struct { u32 held_buttons[3]; float triggers[3]; Vec2 lstick; } input;
    u8 x221F_b3 : 1;
    u8 x221F_b4 : 1;
    u8 x221C_b6 : 1;
    u8 x2219_b5 : 1;
    u8 x221A_b3 : 1;
    u8 x221D_b6 : 1;
    int x1988, x198C;
    Fighter_GObj *item_gobj, *victim_gobj, *x1A5C;
    struct { void* owner; } x1064_thrownHitbox;
    /* Unrelated motion storage deliberately contains nonzero pointer-like
     * bytes; capture flags must not interpret it outside its valid state. */
    union { unsigned char opaque[248]; void* capture; } mv;
    struct CpuFighter cpu;
    unsigned char unrelated[4096];
};
struct StartMeleeRules {
    u32 match_kind : 3;
    u32 is_stock : 1;
    u32 friendly_fire : 1;
    u32 is_vs : 1;
    u32 timer_enabled : 1;
    u32 timer_counts_up : 1;
    u8 is_teams;
    s8 xB, xC;
    u16 stkind;
    u32 time_limit;
    u64 x20;
    float x30, game_speed;
};
struct TestEntities { Fighter_GObj* items; };
extern struct TestEntities* HSD_GObj_Entities;
u32 gm_GetFrameCount(void);
u16 gm_GetStKind(void);
u8 gm_GetCurrentGameMode(void);
struct StartMeleeRules* gm_GetRules(void);
bool gm_8016B14C(void);
bool gm_8016B168(void);
bool ftCo_800A2040(Fighter* fp);
bool ftCo_IsAlly(Fighter* fp, Fighter* target);
s32 ftColl_8007B868(Fighter_GObj* gobj);
Fighter_GObj* Player_GetEntity(int slot);
Fighter_GObj* Player_GetEntityAtIndex(int slot, int index);
int Player_GetPlayerState(int slot);
int Player_GetStocks(int slot);
int Player_8003248C(int slot, bool secondary);
void OSReport(const char* format, ...) __attribute__((format(printf, 1, 2)));
#endif
