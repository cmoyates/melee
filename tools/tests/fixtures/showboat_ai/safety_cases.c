/* Main's output-filter call contract only. Safety geometry/native VM policy
 * belongs to the real safety module's separate tests. Each allowed call is
 * explicitly armed; forbidden calls fail even when a spy would return false. */
static void safety_observe(Fighter* fp, const struct CpuFighter* expected)
{
    Fighter before[SB_SLOTS];
    Fighter_GObj old_objects[SB_SLOTS];
    unsigned char old_world[sizeof(world)], old_states[sizeof(sb_states)];
    struct TestCommonData old_common = common_data;
    struct TestEntities old_entities = entities;
    int old_clears = clears, old_writes = writes, old_scripts = scripts;
    int old_takes = defense.takes, old_rewards = defense.rewards;
    memcpy(before, fighters, sizeof(before));
    memcpy(old_objects, objects, sizeof(objects));
    memcpy(old_world, &world, sizeof(world));
    memcpy(old_states, sb_states, sizeof(sb_states));
    /* Unlike the old read-only post_input guard, permit ONLY the exact planned
     * output edit; no blanket CPU mask, script cancellation, or physical writes. */
    for (int i = 0; i < SB_SLOTS; ++i) {
        if (&fighters[i] == fp) { memcpy(&before[i].cpu, expected, sizeof(*expected)); }
    }
    ShowboatAI_PostInput(fp);
    safety_verified();
    CHECK(memcmp(before, fighters, sizeof(before)) == 0);
    CHECK(memcmp(old_objects, objects, sizeof(objects)) == 0);
    CHECK(memcmp(old_world, &world, sizeof(world)) == 0);
    CHECK(memcmp(old_states, sb_states, sizeof(sb_states)) == 0); /* ego/RNG too */
    CHECK(memcmp(&old_common, &common_data, sizeof(common_data)) == 0);
    CHECK(memcmp(&old_entities, &entities, sizeof(entities)) == 0);
    CHECK(clears == old_clears && writes == old_writes && scripts == old_scripts);
    CHECK(defense.takes == old_takes && defense.rewards == old_rewards);
}
static void safety_unchanged(Fighter* fp)
{
    struct CpuFighter expected;
    memcpy(&expected, &fp->cpu, sizeof(expected));
    safety_observe(fp, &expected);
}
static int safety_trace_count(int kind)
{
    int count = 0;
    for (int i = 0; i < recording.count; ++i) {
        if (recording.trace[i].kind == kind) { ++count; }
    }
    return count;
}
static void safety_sampled(Fighter* fp, Fighter* rival, int frames)
{
    CHECK(recording.frames == frames * SHOWBOAT_RECORDER);
    if (SHOWBOAT_RECORDER) {
        CHECK(recording.frame_actor == fp && recording.frame_target == rival);
        CHECK(memcmp(&recording.frame_cpu, &fp->cpu, sizeof(fp->cpu)) == 0);
    }
}
static void safety_no_event(void)
{
    CHECK(recording.events == 0 && safety.logs == 0);
    CHECK(safety_trace_count(REC_EVENT) == 0 && safety_trace_count(REC_LOG) == 0);
}

static void test_safety_native_vm_filter_before_recording(void)
{
    for (variant = 0; variant < 3; ++variant) {
        init(); combat.reported_action = 0;
        state->ego = variant == 0 ? 0 : variant == 1 ? 55 : 100;
        state->serious = 70; state->toy_frames = 10;
        recording_watch();
        CHECK(!update(self)); /* native fallback; ego/caution/JUGGLE don't block */
        const u8 native[] = { CpuCmd_SetLstickX, 83, CpuCmd_SetLstickY,
                              (u8) -27, CpuCmd_PressB, CpuCmd_Done };
        self->cpu.buttons = HSD_PAD_DPADUP;
        self->cpu.cstick.x = -44; self->cpu.cstick.y = 55;
        self->cpu.ltrigger = 123; self->cpu.rtrigger = 234;
        native_vm(native, sizeof(native), 0, 1);
        CHECK(recording.frames == 0 && safety.calls == 0);
        interpret(self);
        CHECK(self->cpu.buttons == (HSD_PAD_DPADUP | HSD_PAD_B));
        CHECK(self->cpu.lstick.x == 83 && self->cpu.lstick.y == -27);
        CHECK(self->cpu.csP == NULL && self->cpu.command_duration == 0);
        combat.post_overlay = variant != 0;
        struct CpuFighter input, output;
        memcpy(&input, &self->cpu, sizeof(input));
        if (combat.post_overlay) { input.lstick.x = -91; }
        memcpy(&output, &input, sizeof(output));
        output.buttons &= ~HSD_PAD_B; output.lstick.x = 0;
        safety_expect(self, target, true, &input);
        safety.watching_logs = true;
        safety_observe(self, &output);
        CHECK(safety.calls == 1 && combat.posts == 1);
        CHECK(self->cpu.buttons == HSD_PAD_DPADUP && self->cpu.lstick.x == 0);
        CHECK(state->ego == (variant == 0 ? 0 : variant == 1 ? 55 : 100));
        CHECK(SBR_EVENT_SIDEB_VETO == 128); /* real public enum, not a local copy */
        CHECK(recording.events == SHOWBOAT_RECORDER);
        CHECK(safety.logs == SHOWBOAT_AI_DEBUG);
        CHECK(safety_trace_count(REC_SAFETY) == 1);
        recording_before(REC_VM, REC_POST);
        recording_before(REC_POST, REC_SAFETY);
        if (SHOWBOAT_AI_DEBUG) {
            CHECK(strstr(safety.last_log, "SIDE-B VETO") != NULL);
            recording_before(REC_SAFETY, REC_LOG);
        }
        safety_sampled(self, target, 1);
        if (SHOWBOAT_RECORDER) {
            CHECK(recording.slots[0].mask == 128);
            CHECK(safety_trace_count(REC_EVENT) == 1);
            CHECK(recording.trace[recording_index(REC_EVENT)].actor == self);
            CHECK(recording.trace[recording_index(REC_EVENT)].a == 128);
            CHECK(memcmp(&recording.event_cpu, &output, sizeof(output)) == 0);
            CHECK(memcmp(&recording.post_cpu, &input, sizeof(input)) == 0);
            CHECK(recording.slots[0].ego == state->ego && !recording.slots[0].owns);
            recording_before(REC_DECISION, REC_VM);
            recording_before(REC_SAFETY, REC_EVENT);
            if (SHOWBOAT_AI_DEBUG) { recording_before(REC_LOG, REC_EVENT); }
            recording_before(REC_EVENT, REC_FRAME);
        }
        /* Next sample: explicit false result, no repeated log/event or ego gain.
         * No implicit VM release/requeue is needed for the filter to be called. */
        safety.watching_logs = false;
        combat.post_overlay = false;
        CHECK(!update(self));
        recording_watch(); safety.watching_logs = true;
        safety_expect(self, target, false, &self->cpu);
        safety_unchanged(self);
        CHECK(safety.calls == 2 && recording.events == SHOWBOAT_RECORDER);
        CHECK(safety.logs == SHOWBOAT_AI_DEBUG);
        CHECK(safety_trace_count(REC_EVENT) == 0 && safety_trace_count(REC_LOG) == 0);
        CHECK(recording.slots[0].mask == 0); /* Begin cleared previous event */
        safety_sampled(self, target, 2);
    }
}

static void test_safety_false_preserves_running_native_output(void)
{
    for (variant = 0; variant < 2; ++variant) {
        init(); combat.reported_action = 0;
        const u8 native[] = { CpuCmd_PressB, CpuCmd_Done };
        native_vm(native, sizeof(native), 0, variant ? 3 : 1);
        dirty_controls(self);
        CHECK(!update(self)); /* already running native program, not a custom one */
        interpret(self);
        CHECK(self->cpu.csP == (variant ? self->cpu.buffer : NULL));
        CHECK(self->cpu.command_duration == (variant ? 2U : 0U));
        recording_watch(); safety.watching_logs = true;
        safety_expect(self, target, false, &self->cpu);
        safety_unchanged(self);
        CHECK(safety.calls == 1 && combat.posts == 1);
        CHECK(self->cpu.buttons & HSD_PAD_B);
        safety_no_event(); safety_sampled(self, target, 1);
        recording_before(REC_POST, REC_SAFETY);
        if (SHOWBOAT_RECORDER) { recording_before(REC_SAFETY, REC_FRAME); }
    }
}

static void test_safety_never_cancels_personality_programs(void)
{
    for (int style = 0; style < 6; ++style) {
        for (variant = 0; variant < 2; ++variant) {
            personality_context(style); combat.reported_action = 0;
            CHECK(update(self));
            CHECK(state->action != SB_NONE);
            if (variant) { interpret(self); }
            dirty_controls(self); /* tempting B/x bytes must NOT invoke safety */
            recording_watch(); safety.watching_logs = true;
            safety_unchanged(self);
            CHECK(safety.calls == 0 && combat.posts == 1);
            CHECK(state->action != SB_NONE);
            safety_no_event(); safety_sampled(self, target, 1);
        }
    }
}

static void test_safety_never_cancels_technical_or_perfect_actions(void)
{
    for (int action = 5; action <= 11; ++action) {
        if (action == 8) { continue; } /* JUGGLE is informational, tested above */
        for (variant = 0; variant < 2; ++variant) {
            init(); combat.reported_action = 0;
            if (action <= 7) {
                combat.owns_input = true; combat.reported_action = action;
            } else if (action == 9) {
                movement.owns_input = true;
            } else if (action == 10) {
                defense.owns_input = true;
            }
            CHECK(update(self) == (action != 11));
            if (action == 11) {
                seed_defense(self, 11, true); /* observed PERFECT, no input ownership */
            }
            CHECK(state->action == SB_NONE);
            if (variant) { interpret(self); }
            dirty_controls(self);
            recording_watch(); safety.watching_logs = true;
            safety_unchanged(self);
            CHECK(safety.calls == 0 && combat.posts == 1);
            if (action == 11) { CHECK(defense.slots[0].pending); }
            safety_no_event(); safety_sampled(self, target, 1);
        }
    }
}

static void test_safety_late_target_identity_and_slot_gates(void)
{
    for (variant = 0; variant < 10; ++variant) {
        init(); combat.reported_action = 0;
        Fighter* observed = target;
        switch (variant) {
        case 0: world.entity[1] = NULL; observed = NULL; break;
        case 1: objects[1].user_data = NULL; observed = NULL; break;
        case 2:
            world.entity[1] = &objects[2]; observed = &fighters[2];
            fighters[2].x8_spawnNum = target->x8_spawnNum; break;
        case 3: ++target->x8_spawnNum; break;
        case 4: state->opponent_owner = (Fighter*) (uintptr_t) 1; break;
        case 5: state->opponent_owner = NULL; break;
        case 6: state->opponent_slot = -1; observed = NULL; break;
        case 7: state->opponent_slot = SB_SLOTS; observed = NULL; break;
        case 8: state->opponent_slot = 255; observed = NULL; break;
        case 9: state->opponent_slot = 2; observed = &fighters[2]; break;
        }
        dirty_input(self);
        recording_watch(); safety.watching_logs = true;
        safety_unchanged(self); /* no Update: identity changes after arbitration */
        CHECK(safety.calls == 0 && combat.posts == 1);
        CHECK(recording.suspends == 0);
        safety_no_event(); safety_sampled(self, observed, 1);
        if (SHOWBOAT_RECORDER) { recording_before(REC_POST, REC_FRAME); }
    }
}

static void test_safety_late_self_spawn_owner_and_eligibility_gates(void)
{
    for (variant = 0; variant < 14; ++variant) {
        init(); combat.reported_action = 0;
        Fighter* actor = self;
        switch (variant) {
        case 0: ++self->x8_spawnNum; break;
        case 1: state->owner = (Fighter*) (uintptr_t) 1; break;
        case 2: state->owner = NULL; break;
        case 3: self->cpu.level = 8; break;
        case 4: self->kind = FTKIND_FOX; break;
        case 5: self->cpu.xC = 3; break;
        case 6: self->x221F_b3 = true; break;
        case 7: world.cpu[0] = false; break;
        case 8: world.entity[0] = &objects[2]; break;
        case 9: self->player_id = 255; break;
        case 10: self->player_id = SB_SLOTS; break;
        case 11: world.entity[0] = NULL; break;
        case 12:
            actor = &fighters[2]; actor->player_id = 0;
            actor->x8_spawnNum = self->x8_spawnNum;
            world.entity[0] = &objects[2]; break;
        case 13: ShowboatAI_ResetSlot(0); break;
        }
        dirty_input(actor);
        recording_watch(); safety.watching_logs = true;
        int actions = combat.actions;
        safety_unchanged(actor);
        CHECK(safety.calls == 0 && combat.posts == 0 && combat.actions == actions);
        CHECK(recording.frames == 0 && recording.suspends == SHOWBOAT_RECORDER);
        if (SHOWBOAT_RECORDER) { CHECK(recording.suspend_actor == actor); }
        safety_no_event();
    }
}

static void test_safety_resumes_only_after_update_rebinds_identity(void)
{
    for (variant = 0; variant < 4; ++variant) {
        init(); combat.reported_action = 0;
        Fighter *actor = self, *rival = target;
        switch (variant) {
        case 0: ++self->x8_spawnNum; break;
        case 1: ++target->x8_spawnNum; break;
        case 2: rival = &fighters[2]; world.entity[1] = &objects[2]; break;
        case 3:
            actor = &fighters[2]; actor->player_id = 0;
            world.entity[0] = &objects[2]; break;
        }
        safety_unchanged(actor);
        CHECK(safety.calls == 0);
        CHECK(!update(actor));
        CHECK(state->owner == actor && state->spawn == actor->x8_spawnNum);
        CHECK(state->opponent_owner == rival && state->opponent_spawn == rival->x8_spawnNum);
        dirty_controls(actor);
        safety_expect(actor, rival, true, &actor->cpu);
        struct CpuFighter output;
        memcpy(&output, &actor->cpu, sizeof(output));
        output.buttons &= ~HSD_PAD_B; output.lstick.x = 0;
        safety_observe(actor, &output);
        CHECK(safety.calls == 1 && recording.events == SHOWBOAT_RECORDER);
        if (SHOWBOAT_RECORDER) {
            CHECK(recording.frame_actor == actor && recording.frame_target == rival);
            CHECK(recording.slots[0].mask == 128);
            CHECK(memcmp(&recording.frame_cpu, &output, sizeof(output)) == 0);
        }
    }
}
