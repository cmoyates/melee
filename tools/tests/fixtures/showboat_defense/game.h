#ifndef SD_TEST_GAME_H
#define SD_TEST_GAME_H
/* Typed dependency surface derived from ft/types.h, ftCommon/types.h,
 * lb/types.h, player.h and lbcollision.h. NOT the PPC ABI or engine physics.
 * No permissive catch-all macros/functions. Native enums/masks are extracted
 * by the runner; production is compiled as a separate, unmodified C TU. */
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
typedef int8_t s8;
typedef uint8_t u8;
typedef int32_t s32;
typedef uint32_t u32;
typedef float f32;
typedef void* UNK_T;
#include "native_enums.h"
typedef struct Fighter Fighter;
typedef struct HSD_GObj { Fighter* user_data; } HSD_GObj;
typedef HSD_GObj Fighter_GObj;
#define GET_FIGHTER(gobj) ((gobj)->user_data)
typedef struct { float x, y, z; } Vec3;
typedef struct { float x, y; } Vec2;
typedef struct { s8 x, y; } S8Vec2;
typedef struct { ItemKind kind; Vec3 pos; } Item;
enum { GA_Ground, GA_Air };
typedef struct { void* victim; u32 x4; } HitVictim;
typedef struct HitCapsule {
    HitCapsuleState state;
    u32 element;
    float damage, scale;
    int x34;
    Vec3 hurt_coll_pos;
    unsigned x40_b3 : 1;
    unsigned x42_b5 : 1;
    unsigned x43_b2 : 1;
    unsigned hit_grabbed_victim_only : 1;
    Vec3 x4C, x58;
    HitVictim victims_1[12];
} HitCapsule;
struct CpuFighter {
    u32 buttons;
    S8Vec2 lstick, cstick;
    u8 ltrigger, rtrigger;
    int xC, level, x18, x1C, xA4;
    Vec3 x54;
    Fighter* x44;
    Fighter* xF0;
    void* xF4;
    unsigned xF8_b12 : 2;
    u32 command_duration;
    s8* csP;
    s8 buffer[0x100];
    s8* write_pos;
    float x568;
    u8 unrelated_native_cpu_bytes[64];
};
struct Fighter {
    Fighter_GObj* gobj;
    FighterKind kind;
    s32 x8_spawnNum;
    u8 player_id;
    int motion_id, ground_or_air;
    float shield_health, facing_dir;
    struct { int x1924; float x1928, x192c; } dmg;
    float lightshield_amount, specialn_facing_dir, shield_unk0, x1964;
    int x19A4, x19A0_shieldDamageTaken, x19BC_shieldDamageTaken3;
    u32 x19B0;
    Fighter_GObj* x19A8;
    unsigned x221F_b6 : 1;
    Vec3 cur_pos, pos_delta, self_vel, x8c_kb_vel;
    struct { struct { int index; Vec3 normal; } floor; } coll_data;
    struct { void* owner; } x1064_thrownHitbox;
    void *victim_gobj, *x1A5C, *item_gobj;
    unsigned x221F_b3 : 1;
    unsigned x221F_b4 : 1;
    unsigned x221C_b6 : 1;
    unsigned x2224_b2 : 1;
    unsigned x221D_b4 : 1;
    unsigned x2219_b5 : 1;
    unsigned x221A_b3 : 1;
    unsigned x221C_b2 : 1;
    unsigned x221C_b1 : 1;
    unsigned x221C_b3 : 1;
    unsigned reflecting : 1;
    unsigned allow_sdi : 1;
    struct {
        Vec2 lstick[3], cstick[3];
        float triggers[3];
        u32 held_buttons[3], pressed_buttons, released_buttons;
    } input;
    u8 trigger_analog_timer, x670_timer_lstick_tilt_x, x671_timer_lstick_tilt_y;
    HitCapsule x914[4];
    union {
        struct {
            union {
                struct {
                    float x0, x4, x8;
                    bool xC;
                    float x10, x14, x18;
                    int x1C, x20, x24;
                } guard;
                u8 other_motion[80];
            };
        } co;
    } mv;
    struct CpuFighter cpu;
};
struct TestEntities { void* items; };
extern struct TestEntities* HSD_GObj_Entities;
bool ftCo_800A2040(Fighter* fp);
float ftCo_800A2A70(Fighter* fp, bool side);
s32 Player_GetPlayerState(s32 slot);
HSD_GObj* Player_GetEntity(s32 slot);
HSD_GObj* Player_GetEntityAtIndex(int slot, int index);
bool lbColl_8000ACFC(void* victim, HitCapsule* hit);
bool lbColl_80006094(Vec3*, Vec3*, Vec3*, Vec3*, Vec3*, Vec3*, float, float);
void OSReport(const char* fmt, ...);
#endif
