/* Included by harness.c: actual production helpers, explicit observations. */
static void normal_time_context(void)
{
    taunt_context(true);
    world.stock_match = false;
    world.stocks[1] = 0;
    test_taunt_mode = GM_VS;
    test_taunt_rules.match_kind = MatchKind_Time;
    test_taunt_elimination = false;
    memset(test_taunt_removal, 0, sizeof(test_taunt_removal));
}

static void test_normal_time_ko_taunt_without_stocks(void)
{
    normal_time_context();
    state->ego = 0; state->serious = 100; state->cooldown = 100;
    CHECK(SB_TauntSafe(self, target));
    CHECK(frame()); CHECK(state->action == SB_TAUNT && state->age == 1);
    CHECK(frame()); CHECK(self->cpu.buttons == HSD_PAD_DPADUP);
    /* Input is not inferred to have forced the 60-frame animation. */
    self->motion_id = ftCo_MS_AppealSR;
    CHECK(frame()); CHECK(!frame()); CHECK(state->action == SB_NONE);
}

static void test_time_ko_certificate_excludes_other_routes(void)
{
    for (variant = 0; variant < 9; ++variant) {
        normal_time_context();
        switch (variant) {
        case 0: test_taunt_mode = GM_TRAINING; break;
        case 1: test_taunt_rules.match_kind = MatchKind_Coin; break;
        case 2: test_taunt_rules.match_kind = MatchKind_Bonus; break;
        case 3: test_taunt_elimination = true; break;
        case 4: test_taunt_removal[1] = 1; break;
        case 5: target->x221F_b4 = true; break;
        case 6: target->motion_id = ftCo_MS_RebirthWait; break;
        case 7: target->mv.co.unk_deadleft.x40 = 0; break;
        case 8: target->mv.co.unk_deadleft.x40 = 19; break;
        }
        CHECK(!SB_TauntSafe(self, target));
    }
    normal_time_context(); test_taunt_rules.match_kind = MatchKind_Stock;
    world.stock_match = true; /* final stock must still refuse */
    CHECK(!SB_TauntSafe(self, target));
    world.stocks[1] = 1; CHECK(SB_TauntSafe(self, target));
    test_taunt_removal[1] = 1; CHECK(!SB_TauntSafe(self, target));
}

static void test_time_ko_rechecks_certificate_before_up(void)
{
    normal_time_context(); CHECK(frame());
    test_taunt_elimination = true;
    expect_cancel(); CHECK(self->cpu.buttons == 0);
}

static void test_native_locomotion_done_padding_takeover(void)
{
    static const u8 code[] = {
        CpuCmd_LstickXTowardDestination, 80, CpuCmd_WaitFor, 3,
        CpuCmd_Done, CpuCmd_Done
    };
    offstage_context(1, false);
    memcpy(self->cpu.buffer, code, sizeof(code));
    self->cpu.csP = self->cpu.buffer + 4; /* waiting before native's two Dones */
    self->cpu.write_pos = self->cpu.buffer + sizeof(code);
    self->cpu.command_duration = 3; self->cpu.lstick.x = 80;
    CHECK(SB_Takeover(self)); CHECK(frame());
    CHECK(state->offstage_style && state->action == SB_DANCE);

    offstage_context(1, false);
    memcpy(self->cpu.buffer, code, sizeof(code));
    self->cpu.buffer[5] = CpuCmd_PressB; /* not accepted as Done padding */
    self->cpu.csP = self->cpu.buffer + 4;
    self->cpu.write_pos = self->cpu.buffer + sizeof(code);
    self->cpu.command_duration = 3;
    struct CpuFighter before = self->cpu;
    CHECK(!SB_Takeover(self)); CHECK(!frame());
    CHECK(memcmp(&before, &self->cpu, sizeof(before)) == 0);
}

static void test_known_teleport_phases_veto_mockery(void)
{
    const int kinds[] = { FTKIND_ZELDA, FTKIND_MEWTWO, FTKIND_SEAK };
    const int starts[] = { ftZd_MS_SpecialHiStart_0, ftMt_MS_SpecialHiStart,
                           ftSk_MS_SpecialHiStart_0 };
    const int ends[] = { ftZd_MS_SpecialAirHi, ftMt_MS_SpecialAirHi,
                         ftSk_MS_SpecialAirHi };
    for (int k = 0; k < 3; ++k) {
        for (int motion = starts[k]; motion <= ends[k]; ++motion) {
            offstage_context(1, false); target->kind = kinds[k];
            target->motion_id = motion;
            CHECK(SB_Teleport(target)); CHECK(!SB_OffstageWindow(self, state, target));
            CHECK(!frame());
        }
        offstage_context(1, false); target->kind = kinds[k];
        CHECK(!SB_Teleport(target)); CHECK(frame());
        target->motion_id = starts[k]; expect_cancel();
    }
    offstage_context(1, false); target->kind = FTKIND_CAPTAIN;
    target->motion_id = ftMt_MS_SpecialHiStart;
    CHECK(!SB_Teleport(target)); /* character-local IDs cannot be global ranges */
    CHECK(SB_OffstageWindow(self, state, target));
}

static void test_offstage_run_settles_using_only_neutral_input(void)
{
    offstage_context(1, false); self->motion_id = ftCo_MS_Run;
    self->self_vel.x = 2.0f;
    CHECK(frame()); CHECK(state->offstage_style && state->age == 0);
    CHECK(state->taunt_settle == 1 && self->cpu.lstick.x == 0);
    CHECK(self->motion_id == ftCo_MS_Run && self->self_vel.x == 2.0f);
    self->motion_id = ftCo_MS_RunBrake; /* explicit native observation */
    for (int i = 0; i < 3; ++i) {
        CHECK(frame()); CHECK(state->age == 0 && self->cpu.lstick.x == 0);
    }
    self->motion_id = ftCo_MS_Wait; self->self_vel.x = 0;
    CHECK(frame()); CHECK(state->age == 1); /* real stance, not timeout */
    CHECK(frame()); CHECK(self->cpu.lstick.x == -127);
}

static void test_offstage_run_settle_timeout_and_threat_preemption(void)
{
    offstage_context(1, false); self->motion_id = ftCo_MS_Run;
    for (int i = 0; i < 12; ++i) { CHECK(frame()); CHECK(state->age == 0); }
    expect_cancel(); CHECK(self->motion_id == ftCo_MS_Run);
    offstage_context(1, false); self->motion_id = ftCo_MS_Run;
    CHECK(frame()); self->cpu.x18 = 7; self->cpu.xA4 = 9;
    CHECK(!frame()); CHECK(state->action == SB_NONE);
    CHECK(self->cpu.x18 == 7 && self->cpu.xA4 == 9);
}
