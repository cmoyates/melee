/* Host mocks, not PPC ABI or native rendering. */

#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>
#define SHOWBOAT_AI_HUD 1
#define HSD_RP_BOTTOMHALF 2
#define DEVTEXT_FLAG_NOWRAP 0x20
#define DEVTEXT_FLAG_HIDEBACKGROUND 0x40
#define FTKIND_CAPTAIN 2
typedef int16_t s16;
typedef struct { unsigned char r,g,b,a; } GXColor;
typedef struct HSD_GObj HSD_GObj;
struct HSD_GObj { HSD_GObj* next; void (*render_cb)(HSD_GObj*,int); void (*user_data_remove_func)(void*); void* user_data; };
static HSD_GObj* lists[64];
static void* HSD_GObj_Entities = lists;
typedef struct Fighter { unsigned char player_id; int kind; HSD_GObj* gobj; } Fighter;
typedef struct { s16 x,y; unsigned char w,h,cursor_x,cursor_y,line_width,flags,current_color; float scale_x,scale_y; char* buf; GXColor colors[4]; } DevText;
static HSD_GObj* players[6];
static int creations, removals, draws, prints;
static bool fail_alloc;
static HSD_GObj* Player_GetEntity(int n) { return players[n]; }
static HSD_GObj* GObj_Create(int c,int p,int priority) { HSD_GObj* g; assert(c==21&&p==24&&priority==0); if(fail_alloc)return NULL; g=calloc(1,sizeof(*g));g->next=lists[24];lists[24]=g;++creations;return g; }
static void GObj_InitUserData(HSD_GObj*g,int k,void(*f)(void*),void*d) { assert(k==21);g->user_data_remove_func=f;g->user_data=d; }
static void GObj_SetupGXLink(HSD_GObj*g,void(*f)(HSD_GObj*,int),int l,int p) { assert(l==17&&p==1);g->render_cb=f; }
static void HSD_GObjPLink_80390228(HSD_GObj*g) { HSD_GObj**p=&lists[24];while(*p!=g){assert(*p);p=&(*p)->next;}*p=g->next;g->user_data_remove_func(g->user_data);free(g);++removals; }
static void HSD_FogSet(void*x) {(void)x;}
static void DevText_SetupCObj(void) {}
static void DevText_SetTextColor(DevText*t,GXColor c) { t->colors[t->current_color]=c; }
static void DevText_Draw(DevText*t) { assert(t->w==64&&t->h==1);++draws; }
static void DevText_SetScale(DevText*t,float x,float y) {t->scale_x=x;t->scale_y=y;}
static void DevText_Erase(DevText*t) {memset(t->buf,0,2*t->w*t->h);}
static void DevText_SetCursorXY(DevText*t,int x,int y) {t->cursor_x=x;t->cursor_y=y;}
static void DevText_Print(DevText*t,char*s) {++prints;while(*s){assert(t->cursor_x<t->w);t->buf[2*t->cursor_x]=*s++;t->cursor_x++;}}
