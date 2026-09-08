#ifndef SB_COMBAT_TEST_GAME_H
#define SB_COMBAT_TEST_GAME_H

/* Deliberately small, typed host dependency surface, NOT a PPC layout mirror.
 * No catch-all functions/macros: newly used engine APIs need explicit mocks. */
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
typedef struct Fighter_GObj { Fighter* user_data; } Fighter_GObj;
#define GET_FIGHTER(gobj) ((gobj)->user_data)
typedef struct { float x, y, z; } Vec3;
typedef struct { float x, y; } Vec2;
typedef struct { s8 x, y; } TestStick;
typedef struct {
    Vec3 cur_pos, prev_pos;
    struct { Vec2 bottom, top, left, right; } ecb;
    struct { int index; u32 flags; Vec3 normal; } floor;
    int floor_skip, joint_id_skip, joint_id_only;
    u32 env_flags;
} CollData;
enum { GA_Ground, GA_Air };
/* Native PAD masks from dolphin/pad/pad.h and sysdolphin/baselib/controller.h. */
enum {
    HSD_PAD_Z = 0x10, HSD_PAD_R = 0x20, HSD_PAD_L = 0x40,
    HSD_PAD_A = 0x100, HSD_PAD_B = 0x200, HSD_PAD_X = 0x400,
    HSD_PAD_Y = 0x800, HSD_PAD_LR = 0x80000000u
};
struct CpuFighter {
    int level, xC, x18, xA4;
    bool xFA_b5;
    u32 buttons;
    TestStick lstick, cstick;
    u8 ltrigger, rtrigger;
    s8 buffer[0x100];
    s8* write_pos;
    s8* csP;
    u32 command_duration;
};
struct Fighter {
    Fighter_GObj* gobj;
    FighterKind kind;
    s32 x8_spawnNum;
    u8 player_id;
    int motion_id, ground_or_air;
    float facing_dir, cur_anim_frame, frame_speed_mul, x8A4_animBlendFrames;
    Vec3 cur_pos, prev_pos, self_vel, pos_delta, x8c_kb_vel;
    Vec3 x98_atk_shield_kb, x74_anim_vel;
    struct { void* owner; } x1064_thrownHitbox;
    CollData coll_data;
    struct {
        float gravity, terminal_velocity, fast_fall_velocity, aerial_friction;
        float air_drift_stick_mul, aerial_drift_base, air_drift_max;
        float air_max_horizontal_velocity;
    } co_attrs;
    struct { float x1830_percent; int x1860, x1948; } dmg;
    struct {
        u32 held_buttons[2], prev_held_buttons, pressed_buttons, released_buttons;
        Vec2 lstick[2], cstick[2];
        float ltrigger, rtrigger;
    } input;
    u8 x670_timer_lstick_tilt_x, x671_timer_lstick_tilt_y;
    u8 x67F, x680, x681, x682, x683, x684, x685;
    int cmd_vars[4];
    bool fall_fast;
    bool x221F_b3, x221C_b6, x2219_b5, x221A_b3, x2224_b2, x221D_b4;
    bool x2228_b2, x2222_b6;
    void* victim_gobj;
    void* x1A5C;
    void* item_gobj;
    union {
        struct {
            union {
                struct { float x0; } damage;
                struct { bool allow_interrupt; } landing;
                struct { int x0; bool x4; } jump;
            };
        } co;
    } mv;
    struct CpuFighter cpu;
};
struct TestCommonData {
    float analog_shoulder_deadzone, x204_knockbackFrameDecay;
    int xE4;
};
extern struct TestCommonData* p_ftCommonData;
bool ftCo_800A2040(Fighter* fp);
int ftColl_8007B868(Fighter_GObj* gobj);
float ftAnim_8006F484(Fighter_GObj* gobj);
float ftCo_GetCpuLTrigger(Fighter* fp);
float ftCo_GetCpuRTrigger(Fighter* fp);
bool mpCheckFloor(float ax, float ay, float bx, float by, float y_offset,
                  Vec3* vec_out, int* line_id_out, u32* flags_out,
                  Vec3* normal_out, int line_id_skip, int joint_id_skip,
                  int joint_id_only, bool (*callback)(Fighter_GObj*, int),
                  Fighter_GObj* gobj);
void mpFloorGetLeft(int line, Vec3* out);
void mpFloorGetRight(int line, Vec3* out);
StKind Stage_80225194(void);
void OSReport(const char* format, ...);
void ftCo_800B4A78(Fighter* fp);
void ftCo_800B463C(Fighter* fp, u8 command);
void ftCo_800B46B8(Fighter* fp, u8 command, u8 argument);
void ftCo_800B49F4(Fighter* fp);
#endif
