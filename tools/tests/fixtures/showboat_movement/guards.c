/* Independent policy stimuli; positive controls accompany negative matrices. */
static void retreat_committed_normal_attack(void)
{
    for (variant = 0; variant < 2; ++variant) {
        setup(); int sign = variant ? -1 : 1;
        target->cur_pos.x = target->coll_data.cur_pos.x = sign * 55;
        target->facing_dir = -sign;
        observe(target, ftCo_MS_AttackS3S, GA_Ground, 3);
        dodge(ftCo_MS_JumpF, -sign);
        observe(self, ftCo_MS_LandingFallSpecial, GA_Ground, 0); abort_now();
    }
}
static void retreat_requires_commitment(void)
{
    for (variant = 0; variant < 14; ++variant) {
        setup(); target->cur_pos.x = target->coll_data.cur_pos.x = 55;
        target->facing_dir = -1; observe(target, ftCo_MS_AttackS3S, GA_Ground, 3);
        switch (variant) {
        case 0: target->motion_id = ftCo_MS_Wait; break;
        case 1: target->motion_id = ftCo_MS_Guard; break;
        case 2: target->motion_id = ftCo_MS_LandingFallSpecial; break;
        case 3: target->motion_id = ftCo_MS_DamageN1; break;
        case 4: target->motion_id = ftCo_MS_AttackAirF; break;
        case 5: target->motion_id = ftCa_MS_SpecialN; break;
        case 6: target->cur_anim_frame = 1; break;
        case 7: target->cur_anim_frame = 29; break;
        case 8: target->frame_speed_mul = 0; break;
        case 9: target->frame_speed_mul = -1; break;
        case 10: target->x8A4_animBlendFrames = 1; break;
        case 11: target->facing_dir = 1; break;
        case 12: target->pos_delta.x = -1.01f; break;
        case 13: target->allow_interrupt = true; break;
        }
        expect_no_start(); CHECK(calls.x_ops == 0 && calls.l_ops == 0);
    }
}
static void forward_medium_band_and_native_run(void)
{
    const int motions[] = { ftCo_MS_Wait, ftCo_MS_WalkSlow, ftCo_MS_WalkMiddle,
        ftCo_MS_WalkFast, ftCo_MS_Dash, ftCo_MS_Run, ftCo_MS_RunBrake };
    for (variant = 0; variant < (int) (sizeof(motions) / sizeof(motions[0])); ++variant) {
        setup(); self->motion_id = motions[variant]; start_neutral();
    }
    setup(); self->facing_dir = -1; dodge(ftCo_MS_JumpB, 1); /* no facing write */
    for (variant = 0; variant < 3; ++variant) {
        setup(); self->motion_id = ftCo_MS_Run;
        self->cur_pos.x = self->coll_data.cur_pos.x = -75;
        target->cur_pos.x = target->coll_data.cur_pos.x = 75 + variant * 10;
        self->gr_vel = self->self_vel.x = self->pos_delta.x = 2.3f;
        self->cpu.lstick.x = 100;
        self->cpu.buffer[0] = (s8) CpuCmd_SetLstickX; self->cpu.buffer[1] = 100;
        self->cpu.buffer[2] = (s8) CpuCmd_WaitFor; self->cpu.buffer[3] = 5;
        self->cpu.buffer[4] = CpuCmd_Done;
        self->cpu.write_pos = self->cpu.buffer + 5;
        self->cpu.csP = self->cpu.buffer + 4; self->cpu.command_duration = 5;
        expect_no_start(); CHECK(calls.clears == 0 && calls.scripts == 0);
    }
}
static void unsupported_ground_motions(void)
{
    const int motions[] = { ftCo_MS_Turn, ftCo_MS_TurnRun, ftCo_MS_Squat,
        ftCo_MS_SquatWait, ftCo_MS_Ottotto, ftCo_MS_Guard, ftCo_MS_Landing,
        ftCo_MS_LandingFallSpecial, ftCo_MS_Attack11, ftCo_MS_KneeBend,
        ftCo_MS_Catch, ftCo_MS_DamageN1, ftCo_MS_CliffWait, ftCo_MS_Entry };
    for (variant = 0; variant < (int) (sizeof(motions) / sizeof(motions[0])); ++variant) {
        setup(); self->motion_id = motions[variant]; expect_no_start();
    }
}
static void eligibility_and_live_native_priority(void)
{
    const int priorities[] = { 0, 2, 3, 4, 5, 6, 7, 8, 9, 11, 15, 18, 255, -1 };
    for (variant = 0; variant < (int) (sizeof(priorities) / sizeof(priorities[0])); ++variant) {
        setup(); self->cpu.x18 = priorities[variant]; expect_no_start();
    }
    setup(); self->cpu.x18 = 10; start_neutral();
    for (variant = 0; variant < 10; ++variant) {
        setup();
        switch (variant) {
        case 0: self->kind = FTKIND_FOX; break;
        case 1: self->cpu.level = 8; break;
        case 2: self->cpu.xC = 3; break;
        case 3: world.cpu[0] = false; break;
        case 4: self->cpu.xA4 = 24; break;
        case 5: world.primary[0] = NULL; break;
        case 6: world.primary[1] = NULL; break;
        case 7: world.entities.items = &objects[2]; break;
        case 8: self->gobj = NULL; break;
        case 9: target->gobj = NULL; break;
        }
        expect_no_start();
    }
}
static void unavailable_actor_or_target(void)
{
    for (int who = 0; who < 2; ++who) {
        for (variant = 0; variant < 16; ++variant) {
            setup(); Fighter* f = who ? target : self;
            switch (variant) {
            case 0: f->x221F_b3 = true; break;
            case 1: f->x2219_b5 = true; break;
            case 2: f->x221A_b3 = true; break;
            case 3: f->x2224_b2 = true; break;
            case 4: f->x221D_b4 = true; break;
            case 5: f->x221C_b6 = true; break;
            case 6: f->victim_gobj = &objects[2]; break;
            case 7: f->x1A5C = &objects[2]; break;
            case 8: f->item_gobj = &objects[2]; break;
            case 9: world.protection[who] = 1; break;
            case 10: f->dmg.x1948 = 1; break;
            case 11: f->x2228_b2 = true; break;
            case 12: f->x2222_b6 = true; break;
            case 13: f->x1064_thrownHitbox.owner = &objects[2]; break;
            case 14: f->motion_id = ftCo_MS_Entry; break;
            case 15: f->motion_id = ftCo_MS_DeadDown; break;
            }
            expect_no_start();
        }
    }
}
static void conflicting_controls(void)
{
    const u32 masks[] = { HSD_PAD_A, HSD_PAD_B, HSD_PAD_X, HSD_PAD_Y,
        HSD_PAD_L, HSD_PAD_R, HSD_PAD_Z, HSD_PAD_LR, HSD_PAD_DPADUP };
    for (int who = 0; who < 2; ++who) {
        for (variant = 0; variant < (int) (sizeof(masks) / sizeof(masks[0])); ++variant) {
            setup();
            if (who) { self->input.held_buttons[0] = masks[variant]; }
            else { self->cpu.buttons = masks[variant]; }
            expect_no_start();
        }
    }
    for (variant = 0; variant < 6; ++variant) {
        setup();
        switch (variant) {
        case 0: self->cpu.ltrigger = 128; break;
        case 1: self->cpu.rtrigger = 128; break;
        case 2: self->cpu.cstick.x = 1; break;
        case 3: self->cpu.cstick.y = -1; break;
        case 4: self->input.cstick[0].x = 0.1f; break;
        case 5: self->input.cstick[0].y = -0.1f; break;
        }
        expect_no_start();
    }
}
static void neutral_must_be_observed(void)
{
    for (variant = 0; variant < 5; ++variant) {
        setup(); start_neutral();
        switch (variant) {
        case 0: self->input.lstick[0].x = 0.1f; break;
        case 1: self->input.lstick[0].y = -0.1f; break;
        case 2: self->input.triggers[0] = 0.1f; break;
        case 3: self->input.held_buttons[0] = HSD_PAD_X; break;
        case 4: self->input.cstick[0].x = 0.1f; break;
        }
        abort_now(); CHECK(calls.x_ops == 0 && calls.l_ops == 0);
    }
}
static void xy_kneebend_requires_observed_press(void)
{
    for (variant = 0; variant < 7; ++variant) {
        setup(); press_jump(); observe(self, ftCo_MS_KneeBend, GA_Ground, 1);
        self->mv.co.kneebend.jump_input = JumpInput_XY;
        self->input.held_buttons[0] = self->input.pressed_buttons = HSD_PAD_X;
        switch (variant) {
        case 0: self->mv.co.kneebend.jump_input = JumpInput_LStick; break;
        case 1: self->mv.co.kneebend.jump_input = JumpInput_CStick; break;
        case 2: self->input.pressed_buttons = 0; break;
        case 3: self->input.held_buttons[0] = 0; break;
        case 4: self->input.lstick[0].x = 0.1f; break;
        case 5: self->input.lstick[0].y = 0.1f; break;
        case 6: self->ground_or_air = GA_Air; break;
        }
        abort_now(); CHECK(calls.x_ops == 1 && calls.l_ops == 0);
    }
}
static void first_jump_precise_guards(void)
{
    for (variant = 0; variant < 10; ++variant) {
        setup(); knees(); observe(self, ftCo_MS_JumpF, GA_Air, 0);
        self->mv.co.jump.x4 = false; self->mv.co.jump.x0 = true;
        self->x1968_jumpsUsed = 1;
        self->cur_pos.y = self->coll_data.cur_pos.y = 1;
        switch (variant) {
        case 0: self->mv.co.jump.x4 = true; break; /* Phys already ran */
        case 1: self->mv.co.jump.x0 = false; break; /* full hop */
        case 2: self->x1968_jumpsUsed = 2; break;
        case 3: self->x1968_jumpsUsed = 0; break;
        case 4: self->cur_pos.y = self->coll_data.cur_pos.y = 1.01f; break;
        case 5: self->pos_delta.y = 0.26f; break;
        case 6: self->input.held_buttons[0] = HSD_PAD_X; break;
        case 7: self->input.held_buttons[0] = HSD_PAD_Y; break;
        case 8: self->input.lstick[0].x = 0.1f; break;
        case 9: self->input.triggers[0] = 0.1f; break;
        }
        abort_now(); CHECK(calls.l_ops == 0);
    }
}
static void missing_floor_platform_edge_stage(void)
{
    for (variant = 0; variant < 16; ++variant) {
        setup();
        switch (variant) {
        case 0: world.floor_enabled = false; break;
        case 1: world.floor_normal_y = 0.999f; break;
        case 2: world.floor_flags = LINE_FLAG_PLATFORM; break;
        case 3: self->coll_data.floor.index = -1; break;
        case 4: target->coll_data.floor.index = 5; break;
        case 5: world.floor_left = -59; world.floor_right = 59; break;
        case 6: world.floor_left = -130; world.floor_right = 130; break;
        case 7: world.right_y = 0.11f; break;
        case 8: world.v1_y = 0.11f; break;
        case 9: self->cur_pos.x = 90; target->cur_pos.x = 10; break;
        case 10: self->cur_pos.x = 121; target->cur_pos.x = 41; break;
        case 11: world.stage = St_Kind_Castle; break;
        case 12: world.stage = (StKind) -1; break;
        case 13: target->cur_pos.y = 0.26f; break;
        case 14: target->ground_or_air = GA_Air; break;
        case 15: world.floor_y = -5; break;
        }
        expect_no_start();
    }
    setup(); world.stage = St_Kind_Battle; start_neutral();
}
static void runway_accounts_for_direction_and_coast(void)
{
    setup(); target->cur_pos.x = target->coll_data.cur_pos.x = -20;
    self->cur_pos.x = self->coll_data.cur_pos.x = -75;
    target->facing_dir = -1; observe(target, ftCo_MS_AttackS3S, GA_Ground, 3);
    expect_no_start(); /* Entry has 45 units; projected retreat exhausts reserve. */
    setup(); target->cur_pos.x = target->coll_data.cur_pos.x = -5;
    self->cur_pos.x = self->coll_data.cur_pos.x = -60;
    target->facing_dir = -1; observe(target, ftCo_MS_AttackS3S, GA_Ground, 3);
    start_neutral(); /* 40 entry / 22 projected reserve are intentionally distinct. */
    setup(); self->gr_vel = self->self_vel.x = self->pos_delta.x = 2.3f;
    target->cur_pos.x = 70; expect_no_start(); /* coast+slide too close to rival */
    setup(); self->gr_vel = self->self_vel.x = self->pos_delta.x = 0.2f;
    start_neutral(); /* No fake friction update required to decide safely. */
    /* Beneficial coast is NOT guaranteed: friction could erase the credit. */
    setup(); world.floor_left = -85.5657f; world.floor_right = 85.5657f;
    self->cur_pos.x = self->coll_data.cur_pos.x = -33.5f;
    self->gr_vel = self->self_vel.x = self->pos_delta.x = 0.5f;
    target->cur_pos.x = target->coll_data.cur_pos.x = 21.5f;
    target->facing_dir = -1; observe(target, ftCo_MS_AttackS3S, GA_Ground, 3);
    expect_no_start(); CHECK(calls.x_ops == 0);
    /* BF/FD scaled native widths and connected, coplanar outer supports.
     * Our projected path stays on the middle line; the rival may use a strip. */
    for (variant = 0; variant < 4; ++variant) {
        setup(); world.stage = variant & 1 ? St_Kind_Last : St_Kind_Battle;
        world.floor_right = variant & 1 ? 85.5657f : 68.4f;
        world.floor_left = -world.floor_right;
        world.main_extent = world.split_x = variant & 1 ? 75 : 60;
        world.split_enabled = true; world.split_connected = !(variant & 2);
        target->coll_data.floor.index = world.floor_line + 1;
        target->cur_pos.x = target->coll_data.cur_pos.x = variant & 1 ? 80 : 65;
        if (variant & 2) { expect_no_start(); }
        else { start_neutral(); }
    }
    setup(); world.stage = St_Kind_Battle;
    world.floor_left = -68.4f; world.floor_right = 68.4f; world.main_extent = 60;
    target->cur_pos.x = target->coll_data.cur_pos.x = 50;
    target->facing_dir = -1; observe(target, ftCo_MS_AttackS3S, GA_Ground, 3);
    start_neutral();
}
static void floor_continuity_during_action(void)
{
    for (variant = 0; variant < 7; ++variant) {
        setup(); knees();
        switch (variant) {
        case 0: world.floor_enabled = false; break;
        case 1: world.floor_line = 5;
            self->coll_data.floor.index = target->coll_data.floor.index = 5; break;
        case 2: world.floor_left -= 1; break;
        case 3: world.floor_right += 1; break;
        case 4: world.stage = St_Kind_Battle; break;
        case 5: world.floor_flags = LINE_FLAG_PLATFORM; break;
        case 6:
            world.floor_y = world.right_y = world.v0_y = world.v1_y = 0.2f;
            self->cur_pos.y = target->cur_pos.y = 0.2f; break;
        }
        abort_now(); CHECK(calls.l_ops == 0);
    }
}
static void ecb_sweep_not_origin_or_air_index(void)
{
    setup(); knees(); observe(self, ftCo_MS_JumpF, GA_Air, 0);
    self->mv.co.jump.x4 = false; self->x1968_jumpsUsed = 1;
    self->cur_pos.y = 0;
    self->coll_data.cur_pos = (Vec3) { 2, 1, 0 };
    self->coll_data.ecb.bottom = (Vec2) { 1, 1 };
    self->coll_data.floor.index = -1; /* In air, ONLY successful live query matters. */
    self->coll_data.joint_id_skip = -7; self->coll_data.joint_id_only = -9;
    int before = calls.floor;
    CHECK(frame()); CHECK(self->cpu.buttons == HSD_PAD_L);
    bool saw_ecb = false;
    for (int i = before; i < calls.floor; ++i) {
        if (calls.sweep[i].ax != calls.sweep[i].bx) {
            CHECK(calls.sweep[i].by < calls.sweep[i].ay);
            CHECK(calls.sweep[i].skip == -1 && calls.sweep[i].joint_skip == -7);
            CHECK(calls.sweep[i].joint_only == -9);
            if (!saw_ecb) { CLOSE(calls.sweep[i].ax, 3); CLOSE(calls.sweep[i].ay, 2); }
            saw_ecb = true;
        }
    }
    CHECK(saw_ecb); CHECK(self->cpu.lstick.x == 90 && self->cpu.lstick.y == -64);
}
static void sweep_gap_skip_and_stale_ecb_veto(void)
{
    for (variant = 0; variant < 6; ++variant) {
        setup(); knees(); observe(self, ftCo_MS_JumpF, GA_Air, 0);
        self->mv.co.jump.x4 = false; self->x1968_jumpsUsed = 1;
        self->cur_pos.y = self->coll_data.cur_pos.y = 1;
        switch (variant) {
        case 0: self->coll_data.floor_skip = world.floor_line; break;
        case 1: world.hole_enabled = true; world.hole_left = 0.5f; world.hole_right = 10; break;
        case 2: self->coll_data.ecb.bottom.x = 7; break;
        case 3: self->coll_data.ecb.bottom.y = 6; break;
        case 4: self->coll_data.cur_pos.y = -1; break;
        case 5: world.split_enabled = true; world.split_x = 1; break;
        }
        abort_now(); CHECK(calls.l_ops == 0);
    }
}
static void unsafe_physics_and_constants(void)
{
    for (variant = 0; variant < 24; ++variant) {
        setup();
        switch (variant) {
        case 0: self->cur_pos.x = NAN; break;
        case 1: self->cur_pos.y = INFINITY; break;
        case 2: self->cur_pos.z = 1.01f; break;
        case 3: self->facing_dir = 0; break;
        case 4: target->facing_dir = NAN; break;
        case 5: self->self_vel.x = 4; break;
        case 6: self->gr_vel = -4; break;
        case 7: self->x8c_kb_vel.x = 0.1f; break;
        case 8: self->x98_atk_shield_kb.y = 0.1f; break;
        case 9: self->x74_anim_vel.x = 0.1f; break;
        case 10: target->self_vel.y = 0.3f; break;
        case 11: target->pos_delta.x = -1.51f; break;
        case 12: self->co_attrs.jump_startup_time = NAN; break;
        case 13: self->co_attrs.jump_startup_time = 9; break;
        case 14: self->co_attrs.hop_v_initial_velocity = 0; break;
        case 15: self->co_attrs.jump_v_initial_velocity = INFINITY; break;
        case 16: self->co_attrs.ground_friction = 0; break;
        case 17: self->co_attrs.dash_max_velocity = 5; break;
        case 18: rules.escapeair_force = 0; break;
        case 19: rules.escapeair_decay = 1.1f; break;
        case 20: rules.x344 = 0; break;
        case 21: rules.horizontal_stick_deadzone = 1; break;
        case 22: rules.vertical_stick_deadzone = 1; break;
        case 23: rules.escapeair_deadzone = (Vec2) { 1, 1 }; break;
        }
        expect_no_start();
    }
}
