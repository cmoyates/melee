/* Native arbitration/slot lifecycle observations, separate from movement. */
static void native_replacement(int priority, int cached)
{
    /* Explicit replacement VM + outputs. Never a mock AI decision. */
    struct CpuFighter* c = &self->cpu;
    c->x18 = priority; c->xA4 = cached;
    c->buffer[0] = (s8) CpuCmd_SetLstickX; c->buffer[1] = 72;
    c->buffer[2] = (s8) CpuCmd_WaitFor; c->buffer[3] = 4;
    c->buffer[4] = CpuCmd_Done;
    c->write_pos = c->buffer + 5; c->csP = c->buffer + 4;
    c->command_duration = 4;
    c->buttons = HSD_PAD_A | HSD_PAD_R; c->lstick = (TestStick) { 72, 11 };
    c->cstick = (TestStick) { 3, -4 }; c->ltrigger = 23; c->rtrigger = 255;
}
static void expect_native_preserved(bool do_suspend)
{
    struct CpuFighter before; memcpy(&before, &self->cpu, sizeof(before));
    if (do_suspend) { suspend(self); }
    else { CHECK(!update(self, target)); }
    CHECK(action(self) == 0);
    CHECK(memcmp(&before, &self->cpu, sizeof(before)) == 0);
}
static void new_native_priority_and_script_win(void)
{
    const int priorities[] = { 1, 10, 2, 4, 7, 9, 15, 18, 255 };
    for (int stop = 0; stop < 2; ++stop) {
        for (variant = 0; variant < (int) (sizeof(priorities) / sizeof(priorities[0])); ++variant) {
            setup(); dodge(ftCo_MS_JumpF, 1);
            native_replacement(priorities[variant], variant ? 25 : 0);
            expect_native_preserved(stop);
        }
    }
}
static void cached_a4_preserved_old_inputs_released(void)
{
    for (variant = 0; variant < 4; ++variant) {
        setup();
        if (variant & 1) {
            dodge(ftCo_MS_JumpF, 1); observe(self, ftCo_MS_EscapeAir, GA_Air, 0);
        } else { knees(); }
        self->cpu.xA4 = 37;
        if (variant & 2) { suspend(self); }
        else { CHECK(!update(self, target)); }
        CHECK(action(self) == 0 && self->cpu.xA4 == 37); neutral();
        CHECK(!self->cpu.csP && !self->cpu.command_duration);
        CHECK(self->cpu.write_pos == self->cpu.buffer);
    }
}
static void changed_priority_releases_old_vm_preserves_decision(void)
{
    const int priorities[] = { 2, 4, 7, 8, 10 };
    for (variant = 0; variant < 5; ++variant) {
        setup(); press_jump(); self->cpu.x18 = priorities[variant];
        self->cpu.xA4 = 37;
        CHECK(!update(self, target)); neutral();
        CHECK(action(self) == 0 && self->cpu.x18 == priorities[variant]);
        CHECK(self->cpu.xA4 == 37 && !self->cpu.csP);
        CHECK(!self->cpu.command_duration && self->cpu.write_pos == self->cpu.buffer);
        /* Native dispatch is available this sample, not behind our old tail. */
    }
    setup(); press_jump(); self->cpu.x18 = 8;
    CHECK(!update(self, target)); neutral();
    CHECK(!self->cpu.csP && self->cpu.x18 == 8 && self->cpu.xA4 == 0);
}
static void replacement_neutral_vm_not_retaken(void)
{
    for (variant = 0; variant < 2; ++variant) {
        setup(); knees();
        native_replacement(variant ? 10 : 1, 0);
        self->cpu.buttons = 0;
        self->cpu.lstick = self->cpu.cstick = (TestStick) { 0, 0 };
        self->cpu.ltrigger = self->cpu.rtrigger = 0;
        self->cpu.command_duration = 1;
        /* All motion/input/threat guards are still valid. Only the replacement
         * script disallows continuing/retaking this low-priority VM. */
        expect_native_preserved(false);
    }
}
static void malformed_or_replaced_vm_not_retaken(void)
{
    for (variant = 0; variant < 5; ++variant) {
        setup(); knees();
        switch (variant) {
        case 0: self->cpu.buffer[0] = CpuCmd_ReleaseL; break;
        case 1: self->cpu.csP = self->cpu.buffer + 1; break;
        case 2: self->cpu.command_duration = 2; break;
        case 3: --self->cpu.write_pos; break;
        case 4: self->cpu.csP = NULL; self->cpu.command_duration = 7; break;
        }
        /* Do not interpret malformed script; production must not own/edit it. */
        expect_native_preserved(false);
    }
}
static void consumed_tail_is_missed_sample_not_clear_vm(void)
{
    setup(); press_jump(); vm(self); neutral();
    observe(self, ftCo_MS_KneeBend, GA_Ground, 1);
    self->mv.co.kneebend.jump_input = JumpInput_XY;
    self->input.held_buttons[0] = self->input.pressed_buttons = HSD_PAD_X;
    abort_now(); CHECK(calls.l_ops == 0);
    setup(); knees(); vm(self); neutral();
    observe(self, ftCo_MS_JumpF, GA_Air, 0);
    self->mv.co.jump.x4 = false; self->x1968_jumpsUsed = 1;
    abort_now(); CHECK(calls.l_ops == 0);
}
static void native_clear(void)
{
    /* An explicit engine arbitration event, not automatic script-age logic. */
    allowed_actor = self; ftCo_800B4A78(self); allowed_actor = NULL;
}
static void empty_native_vm_transition_retake(void)
{
    setup(); press_jump(); native_clear();
    observe(self, ftCo_MS_KneeBend, GA_Ground, 1);
    self->mv.co.kneebend.jump_input = JumpInput_XY;
    self->input.held_buttons[0] = self->input.pressed_buttons = HSD_PAD_X;
    CHECK(frame()); neutral(); CHECK(calls.x_ops == 1 && calls.l_ops == 0);
    self->input.held_buttons[0] = self->input.pressed_buttons = 0;
    observe(self, ftCo_MS_JumpF, GA_Air, 0);
    self->mv.co.jump.x0 = true; self->mv.co.jump.x4 = false;
    self->x1968_jumpsUsed = 1; self->cur_pos.y = self->coll_data.cur_pos.y = 1;
    native_clear(); self->cpu.x18 = 10;
    CHECK(frame()); CHECK(self->cpu.buttons == HSD_PAD_L); CHECK(calls.l_ops == 1);
    native_clear(); observe(self, ftCo_MS_EscapeAir, GA_Air, 0);
    CHECK(frame()); neutral();
    observe(self, ftCo_MS_LandingFallSpecial, GA_Ground, 0); abort_now();
    setup(); start_neutral(); native_clear(); abort_now(); CHECK(calls.x_ops == 0);
}
static void suspend_all_phases_idempotent(void)
{
    for (variant = 0; variant < 5; ++variant) {
        setup();
        switch (variant) {
        case 0: start_neutral(); break;
        case 1: press_jump(); break;
        case 2: knees(); break;
        case 3: dodge(ftCo_MS_JumpF, 1); break;
        case 4: dodge(ftCo_MS_JumpF, 1);
            observe(self, ftCo_MS_EscapeAir, GA_Air, 0); CHECK(frame()); break;
        }
        suspend(self); CHECK(action(self) == 0); neutral();
        int clears = calls.clears;
        suspend(self); CHECK(calls.clears == clears); neutral();
        vm(self); neutral();
        reset(0); CHECK(action(self) == 0); /* Suspend BEFORE occupied reset. */
    }
}
static void target_identity_and_threat_changes(void)
{
    for (variant = 0; variant < 9; ++variant) {
        setup(); knees();
        Fighter* other = target;
        switch (variant) {
        case 0: other = NULL; break;
        case 1: other = &fighters[2]; other->cur_pos.x = 80; break;
        case 2: ++target->x8_spawnNum; break;
        case 3: target->player_id = 0; break;
        case 4: target->player_id = 6; break;
        case 5: target->cur_pos.x = -80; break;
        case 6: target->motion_id = ftCo_MS_AttackS3S; break;
        case 7: target->ground_or_air = GA_Air; break;
        case 8: world.entities.items = &objects[2]; break;
        }
        CHECK(!update(self, other)); CHECK(action(self) == 0); neutral();
        CHECK(calls.l_ops == 0);
    }
}
static void slot_spawn_and_primary_identity(void)
{
    setup(); press_jump(); ++self->x8_spawnNum;
    CHECK(action(self) == 0); /* GetAction must not create fresh sidecar. */
    struct CpuFighter old; memcpy(&old, &self->cpu, sizeof(old));
    suspend(self); CHECK(memcmp(&old, &self->cpu, sizeof(old)) == 0);
    CHECK(!update(self, target)); CHECK(action(self) == 0); vm(self); neutral();
    setup(); start_neutral();
    Fighter* partner = &fighters[2]; partner->player_id = 0;
    CHECK(!update(partner, target)); CHECK(action(partner) == 0);
    suspend(partner); CHECK(action(self) == 9); /* Partner cannot erase primary. */
    CHECK(frame()); CHECK(self->cpu.buttons == HSD_PAD_X);
    setup(); knees(); world.primary[0] = &objects[2];
    CHECK(!update(self, target)); CHECK(action(self) == 0); neutral();
}
static void slots_are_independent(void)
{
    setup(); start_neutral();
    Fighter* other = &fighters[2]; other->cur_pos.x = other->coll_data.cur_pos.x = 0;
    CHECK(update(other, target)); vm(other); CHECK(action(other) == 9);
    suspend(other); CHECK(action(other) == 0 && action(self) == 9);
    reset(2); CHECK(frame()); CHECK(self->cpu.buttons == HSD_PAD_X);
    CHECK(action(self) == 9 && action(other) == 0);
}
static void escape_ack_release_is_bounded(void)
{
    setup(); dodge(ftCo_MS_JumpF, 1);
    observe(self, ftCo_MS_EscapeAir, GA_Air, 0);
    CHECK(frame()); neutral();
    for (int i = 0; i < 20; ++i) { frame(); neutral(); }
    CHECK(action(self) == 0 && calls.x_ops == 1 && calls.l_ops == 1);
    CHECK(self->motion_id == ftCo_MS_EscapeAir);
}
static void native_landing_ack_preserves_new_script(void)
{
    setup(); dodge(ftCo_MS_JumpF, 1);
    observe(self, ftCo_MS_LandingFallSpecial, GA_Ground, 0);
    native_replacement(7, 41); expect_native_preserved(false);
}
static void success_changes_only_script_and_cpu_outputs(void)
{
    setup();
    self->self_vel.z = 0.375f; self->prev_pos = (Vec3) { 4, 5, 6 };
    self->gr_vel = self->self_vel.x = self->pos_delta.x = 0.125f;
    self->cmd_vars[0] = 17; self->cmd_vars[1] = -1;
    self->x8A4_animBlendFrames = 3.25f;
    self->cpu.lstick = (TestStick) { 30, -10 };
    dodge(ftCo_MS_JumpF, 1); /* Every successful Update is byte-snapshotted. */
    CLOSE(self->self_vel.z, 0.375f); CLOSE(self->gr_vel, 0.125f);
    CHECK(self->cmd_vars[0] == 17 && self->cmd_vars[1] == -1);
    CLOSE(self->x8A4_animBlendFrames, 3.25f);
    CHECK(self->x67F == 255 && self->x680 == 17 && self->x681 == 21);
    CHECK(self->x682 == 83 && self->x683 == 5 && self->x684 == 199 && self->x685 == 231);
    CHECK(self->x670_timer_lstick_tilt_x == 111 && self->x671_timer_lstick_tilt_y == 87);
}
