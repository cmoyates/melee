
/* Test-only scene cleanup; production detects bulk resets on the next update. */
static void test_cleanup(void) {
 HUD_ValidateGObj();
 if(hud_gobj) HSD_GObjPLink_80390228(hud_gobj);
 else HUD_Removed(NULL);
}
static void expect_row(int i,const char* expected) { char out[65];int j;for(j=0;j<64;j++)out[j]=hud_rows[i].cells[j*2];out[64]=0;assert(strcmp(out,expected)==0); }
int main(void) {
 HSD_GObj fighter_obj[6]={{0}}; Fighter fp[6]; int i, before; HSD_GObj *old, *other;
 for(i=0;i<6;i++){players[i]=&fighter_obj[i];fp[i].player_id=i;fp[i].kind=FTKIND_CAPTAIN;fp[i].gobj=players[i];}
 ShowboatHUD_ResetSlot(-1);ShowboatHUD_ResetSlot(6);test_cleanup();ShowboatHUD_Update(NULL,0,0,0);assert(!hud_gobj);
 fail_alloc=true;ShowboatHUD_Update(&fp[1],62,0,120);assert(!hud_gobj&&!hud_rows[1].active);fail_alloc=false;
 ShowboatHUD_Update(&fp[1],62,0,120);assert(creations==1);expect_row(1,"FALCON P2 EGO  62 /100 (VANILLA) SERIOUS 120f");
 before=prints;ShowboatHUD_Update(&fp[1],62,0,120);assert(prints==before);
 for(i=0;i<6;i++)ShowboatHUD_Update(&fp[i],100,i%4,INT_MAX);assert(creations==1);
 ShowboatHUD_Update(&fp[5],INT_MAX,2,INT_MAX);expect_row(5,"FALCON P6 EGO 100 /100 (SWAGGER) SERIOUS 2147483647f");
 ShowboatHUD_Update(&fp[0],INT_MIN,INT_MAX,INT_MIN);expect_row(0,"FALCON P1 EGO   0 /100 (VANILLA) SERIOUS 0f");
 ShowboatHUD_Update(&fp[0],90,SHOWBOAT_HUD_DANCE,0);expect_row(0,"FALCON P1 EGO  90 /100 (DANCE) SERIOUS 0f");
 ShowboatHUD_Update(&fp[0],90,SHOWBOAT_HUD_GRAB,0);expect_row(0,"FALCON P1 EGO  90 /100 (GRAB) SERIOUS 0f");
 ShowboatHUD_Update(&fp[0],90,SHOWBOAT_HUD_KNEE,0);expect_row(0,"FALCON P1 EGO  90 /100 (KNEE) SERIOUS 0f");
 ShowboatHUD_Update(&fp[0],90,SHOWBOAT_HUD_UPAIR,0);expect_row(0,"FALCON P1 EGO  90 /100 (UPAIR) SERIOUS 0f");
 ShowboatHUD_Update(&fp[0],90,SHOWBOAT_HUD_JUGGLE,0);expect_row(0,"FALCON P1 EGO  90 /100 (JUGGLE) SERIOUS 0f");
 ShowboatHUD_Update(&fp[0],90,SHOWBOAT_HUD_WDASH,0);expect_row(0,"FALCON P1 EGO  90 /100 (WDASH) SERIOUS 0f");
 ShowboatHUD_Update(&fp[0],90,SHOWBOAT_HUD_BLOCK,0);expect_row(0,"FALCON P1 EGO  90 /100 (BLOCK) SERIOUS 0f");
 ShowboatHUD_Update(&fp[0],90,SHOWBOAT_HUD_PERFECT,0);expect_row(0,"FALCON P1 EGO  90 /100 (PERFECT) SERIOUS 0f");
 HUD_Draw(hud_gobj,0);assert(draws==0);HUD_Draw(hud_gobj,2);assert(draws==12);assert(hud_rows[0].text.x==22&&hud_rows[0].text.y==72);
 fp[1].gobj=NULL;ShowboatHUD_Update(&fp[1],1,1,1);assert(hud_rows[1].ego==100);fp[1].gobj=players[1];
 fp[1].kind=0;ShowboatHUD_Update(&fp[1],1,1,1);assert(!hud_rows[1].active);fp[1].kind=FTKIND_CAPTAIN;
 ShowboatHUD_ResetSlot(0);assert(!hud_rows[0].active&&hud_rows[2].active);
 test_cleanup();assert(!hud_gobj&&removals==1);test_cleanup();
 for(i=0;i<100;i++) { ShowboatHUD_Update(&fp[0],i,0,0);old=hud_gobj;lists[24]=NULL;free(old); /* Bulk scene heap reset, NO destructor. */ ShowboatHUD_Update(&fp[1],62,1,3);assert(!hud_rows[0].active&&hud_rows[1].active);test_cleanup(); }
 ShowboatHUD_Update(&fp[0],1,0,0);other=hud_gobj;other->render_cb=NULL;other->user_data=NULL;other->user_data_remove_func=NULL; /* address reused by unrelated live object */
 test_cleanup();assert(!hud_gobj&&lists[24]==other);lists[24]=NULL;free(other);
 ShowboatHUD_Update(&fp[0],1,0,0);HSD_GObjPLink_80390228(hud_gobj);assert(!hud_gobj&&!hud_rows[0].active);
 puts("PASS: formatting/clamps, six slots, cache, allocation failure, secondary rejection, reset isolation, render pass, explicit destruction, 100 bulk resets, reused-address rejection");return 0;
}
