/* Queued-but-not-yet-sampled native commands must retain arbitration. These
 * byte streams are read by production's guard, NOT executed by the fixture VM. */
static void queued_native_attack_or_unknown_command_wins(void)
{
    const u8 scripts[][8] = {
        { CpuCmd_PressA, CpuCmd_Done },
        { CpuCmd_PressB, CpuCmd_Done },
        { CpuCmd_PressX, CpuCmd_Done },
        { CpuCmd_PressL, CpuCmd_Done },
        { CpuCmd_PressXFor, 1, CpuCmd_Done },
        { CpuCmd_SetCstickX, 100, CpuCmd_Done },
        { CpuCmd_SetCstickY, 100, CpuCmd_Done },
        { CpuCmd_SetLtrigger, 128, CpuCmd_Done },
        { CpuCmd_SetRtrigger, 255, CpuCmd_Done },
        { CpuCmd_WaitFor, 1, CpuCmd_PressA, CpuCmd_Done },
        { CpuCmd_ReleaseAll, CpuCmd_WaitFor, 1, CpuCmd_PressL, CpuCmd_Done },
        { CpuCmd_Unk0x93, 7, CpuCmd_Done },
        { 0x7E, CpuCmd_Done }, /* Unrecognized native byte, never silently noop. */
    };
    const u8 sizes[] = { 2, 2, 2, 2, 3, 3, 3, 3, 3, 4, 5, 3, 2 };
    for (variant = 0; variant < (int) (sizeof(sizes) / sizeof(sizes[0])); ++variant) {
        setup(); memcpy(self->cpu.buffer, scripts[variant], sizes[variant]);
        self->cpu.csP = self->cpu.buffer;
        self->cpu.write_pos = self->cpu.buffer + sizes[variant];
        self->cpu.command_duration = 1;
        neutral(); expect_no_start(); CHECK(calls.scripts == 0 && calls.clears == 0);
    }
}
static void malformed_pending_native_vm_rejected(void)
{
    for (variant = 0; variant < 6; ++variant) {
        setup(); self->cpu.buffer[0] = (s8) CpuCmd_SetLstickX;
        self->cpu.buffer[1] = 0; self->cpu.buffer[2] = CpuCmd_Done;
        self->cpu.csP = self->cpu.buffer; self->cpu.write_pos = self->cpu.buffer + 3;
        self->cpu.command_duration = 1;
        switch (variant) {
        case 0: self->cpu.command_duration = 0; break;
        case 1: self->cpu.write_pos = self->cpu.buffer + 1; break; /* missing arg */
        case 2: self->cpu.write_pos = self->cpu.buffer + 2; break; /* no Done */
        case 3: self->cpu.csP = self->cpu.write_pos; break;
        case 4: self->cpu.csP = fighters[2].cpu.buffer; break;
        case 5: self->cpu.write_pos = fighters[2].cpu.buffer; break;
        }
        expect_no_start();
    }
}
static void pending_mundane_locomotion_admitted(void)
{
    const u8 script[] = { CpuCmd_SetLstickX, 30, CpuCmd_SetLstickY, 0,
        CpuCmd_SetCstickX, 0, CpuCmd_SetLtrigger, 0,
        CpuCmd_WaitFor, 1, CpuCmd_Done };
    setup(); memcpy(self->cpu.buffer, script, sizeof(script));
    self->cpu.write_pos = self->cpu.buffer + sizeof(script);
    self->cpu.csP = self->cpu.buffer; self->cpu.command_duration = 1;
    start_neutral();
    /* Only remaining bytecode is relevant: a consumed prefix cannot poison an
     * otherwise released locomotion VM. No synthetic execution of that prefix. */
    setup(); self->cpu.buffer[0] = CpuCmd_PressA;
    memcpy(self->cpu.buffer + 1, script, sizeof(script));
    self->cpu.write_pos = self->cpu.buffer + 1 + sizeof(script);
    self->cpu.csP = self->cpu.buffer + 1; self->cpu.command_duration = 1;
    start_neutral();
}
static void new_precise_threat_and_facing_guards(void)
{
    setup(); target->pos_delta.x = 1.01f; expect_no_start(); /* rapid retreat */
    setup(); target->cur_pos.x = 55; target->facing_dir = -1;
    observe(target, ftCo_MS_AttackS3S, GA_Ground, 3);
    self->gr_vel = 0.51f; expect_no_start(); /* don't reverse a fast approach */
    setup(); knees(); self->facing_dir = -1; abort_now();
    for (variant = 0; variant < 4; ++variant) {
        setup(); dodge(ftCo_MS_JumpF, 1);
        observe(self, ftCo_MS_EscapeAir, GA_Air, 0);
        switch (variant) {
        case 0: world.protection[1] = 1; break;
        case 1: target->motion_id = ftCa_MS_SpecialN; break;
        case 2: world.floor_enabled = false; break;
        case 3: self->facing_dir = -1; break;
        }
        abort_now(); CHECK(calls.l_ops == 1);
    }
}
