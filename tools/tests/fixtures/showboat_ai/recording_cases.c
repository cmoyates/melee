/* Recorder/main integration only. Every scenario also runs with recorder off;
 * all gameplay assertions still use update()/suspend() physical-write guards.
 * frame() intentionally does not call PostInput: sample it explicitly here. */
static void recording_watch(void)
{
    recording.count = 0;
    recording.watching = true;
}
static int recording_index(int kind)
{
    for (int i = 0; i < recording.count; ++i) {
        if (recording.trace[i].kind == kind) { return i; }
    }
    CHECK(!"missing recorder orchestration trace entry");
    return -1;
}
static void recording_before(int a, int b)
{
    CHECK(recording_index(a) < recording_index(b));
}
static void recording_post_input(Fighter* fp)
{
    Fighter_GObj old_objects[SB_SLOTS];
    unsigned char old_world[sizeof(world)];
    struct TestCommonData old_common = common_data;
    struct TestEntities old_entities = entities;
    memcpy(old_objects, objects, sizeof(objects));
    memcpy(old_world, &world, sizeof(world));
    post_input(fp); /* compares EVERY Fighter byte, including CPU input */
    safety_verified();
    CHECK(memcmp(old_objects, objects, sizeof(objects)) == 0);
    CHECK(memcmp(old_world, &world, sizeof(world)) == 0);
    CHECK(memcmp(&old_common, &common_data, sizeof(common_data)) == 0);
    CHECK(memcmp(&old_entities, &entities, sizeof(entities)) == 0);
}
static void recording_personality_reasons(const int* expected, int count)
{
    int n = 0;
    for (int i = 0; i < recording.count; ++i) {
        if (recording.trace[i].kind != REC_REASON) { continue; }
        CHECK(recording.trace[i].actor == self);
        CHECK(recording.trace[i].a == SBR_PERSONALITY);
        CHECK(n < count && recording.trace[i].b == expected[n++]);
    }
    CHECK(n == count);
    CHECK(recording.slots[0].reasons[SBR_PERSONALITY] == expected[count - 1]);
    /* Technical modules are spies and emit no reasons here. Main must not
     * pretend that an uninstrumented/uncalled layer evaluated a candidate. */
    for (int i = SBR_COMBAT; i < SBR_TACTICS; ++i) {
        CHECK(recording.slots[0].reasons[i] == SBR_NOT_EVALUATED);
    }
}

static void test_recording_begin_decision_vm_post_frame_order(void)
{
    whiff_context(true);
    combat.borrowed = true; combat.borrower = self; combat.saved_x = 19;
    self->cpu.lstick.x = 99;
    int tick = state->tick, begins = recording.begins, decisions = recording.decisions;
    recording_watch();
    CHECK(update(self));
    CHECK(state->action == SB_SWAGGER && state->tick == tick + 1);
    CHECK(self->cpu.csP == self->cpu.buffer && self->cpu.lstick.y == 0);
    CHECK(recording.frames == 0 && combat.posts == 0);
    CHECK(recording.begins == begins + SHOWBOAT_RECORDER);
    CHECK(recording.decisions == decisions + SHOWBOAT_RECORDER);
    if (SHOWBOAT_RECORDER) {
        CHECK(recording.begin_actor == self && recording.decision_actor == self);
        CHECK(recording.begin_cpu.lstick.x == 19); /* restored BEFORE Begin */
        CHECK(recording.begin_tick == tick && recording.decision_tick == tick + 1);
        CHECK(recording.decision_cpu.csP == self->cpu.buffer); /* not yet sampled */
        CHECK(recording.slots[0].ego == state->ego);
        CHECK(recording.slots[0].action == SB_SWAGGER && recording.slots[0].owns);
        const int reasons[] = { SBR_NO_CANDIDATE, SBR_STARTED };
        recording_personality_reasons(reasons, 2);
        recording_before(REC_RESTORE, REC_BEGIN);
        recording_before(REC_BEGIN, REC_COMBAT);
        recording_before(REC_BEGIN, REC_REASON);
        recording_before(REC_REASON, REC_DECISION);
    }
    interpret(self);
    CHECK(self->cpu.csP == NULL && self->cpu.command_duration == 0);
    CHECK(self->cpu.lstick.y == -100);
    CHECK(recording.frames == 0); /* neither Update nor VM calls Frame */
    recording_post_input(self);
    CHECK(combat.posts == 1 && recording.frames == SHOWBOAT_RECORDER);
    if (SHOWBOAT_RECORDER) {
        recording_before(REC_DECISION, REC_VM);
        recording_before(REC_VM, REC_POST);
        recording_before(REC_POST, REC_FRAME);
        CHECK(recording.frame_actor == self && recording.frame_target == target);
        CHECK(recording.frame_cpu.csP == NULL && recording.frame_cpu.lstick.y == -100);
        CHECK(memcmp(&recording.post_cpu, &recording.frame_cpu, sizeof(self->cpu)) == 0);
    }
}

static void test_recording_output_channels_after_native_vm(void)
{
    for (variant = 0; variant < 2; ++variant) {
        init();
        combat.owns_input = variant != 0;
        recording_watch();
        CHECK(update(self) == (variant != 0));
        CHECK(recording.frames == 0);
        /* Fixture-supplied native channels after arbitration, not a recorder
         * or CombatPostInput write. The tiny VM changes only its known subset. */
        self->cpu.buttons = HSD_PAD_DPADUP;
        self->cpu.lstick.x = -71; self->cpu.lstick.y = 28;
        self->cpu.cstick.x = 39; self->cpu.cstick.y = -42;
        self->cpu.ltrigger = 53; self->cpu.rtrigger = 214;
        if (!variant) {
            const u8 native[] = { CpuCmd_SetLstickX, 61, CpuCmd_SetLstickY,
                                  (u8) -83, CpuCmd_PressB, CpuCmd_Done };
            memcpy(self->cpu.buffer, native, sizeof(native));
            self->cpu.write_pos = self->cpu.buffer + sizeof(native);
            self->cpu.csP = self->cpu.buffer; self->cpu.command_duration = 1;
        }
        interpret(self);
        recording_post_input(self);
        CHECK(self->cpu.buttons == (HSD_PAD_DPADUP | HSD_PAD_B));
        CHECK(self->cpu.lstick.x == (variant ? -71 : 61));
        CHECK(self->cpu.lstick.y == (variant ? 28 : -83));
        CHECK(self->cpu.cstick.x == 39 && self->cpu.cstick.y == -42);
        CHECK(self->cpu.ltrigger == 53 && self->cpu.rtrigger == 214);
        CHECK(self->cpu.csP == NULL && self->cpu.command_duration == 0);
        CHECK(recording.frames == SHOWBOAT_RECORDER);
        if (SHOWBOAT_RECORDER) {
            CHECK(recording.slots[0].owns == (variant != 0));
            CHECK(recording.decision_cpu.cstick.x == 0);
            CHECK(recording.decision_cpu.rtrigger == 0);
            CHECK(memcmp(&recording.frame_cpu, &self->cpu, sizeof(self->cpu)) == 0);
            CHECK(memcmp(&recording.post_cpu, &self->cpu, sizeof(self->cpu)) == 0);
            recording_before(REC_DECISION, REC_VM);
            recording_before(REC_VM, REC_POST);
            recording_before(REC_POST, REC_FRAME);
        }
    }
}

static void test_recording_decision_action_precedence(void)
{
    const int actions[] = { SB_SWAGGER, 5, 9, 10, 11, 8, 0 };
    for (variant = 0; variant < 7; ++variant) {
        if (variant == 0) { whiff_context(true); } else { init(); }
        combat.reported_action = variant < 2 ? 5 : 0;
        switch (variant) {
        case 1: combat.owns_input = true; break;
        case 2: movement.owns_input = true; break;
        case 3: defense.owns_input = true; break;
        case 4: seed_defense(self, 11, false); break;
        case 5: state->toy_frames = 10; break;
        }
        bool owns = variant < 4;
        int decisions = recording.decisions, getters = combat.actions;
        CHECK(frame() == owns);
        if (variant >= 5) { safety_expect(self, target, false, &self->cpu); }
        recording_post_input(self);
        CHECK(recording.decisions == decisions + SHOWBOAT_RECORDER);
        CHECK(recording.frames == SHOWBOAT_RECORDER);
        CHECK(combat.actions == getters + (SHOWBOAT_RECORDER && variant != 0) +
                                (variant != 0)); /* PostInput's ownership gate */
        if (SHOWBOAT_RECORDER) {
            CHECK(recording.slots[0].action == actions[variant]);
            CHECK(recording.slots[0].ego == state->ego);
            CHECK(recording.slots[0].owns == owns);
        }
    }
}

static void test_recording_decision_after_verified_reward(void)
{
    init(); combat.reported_action = 0;
    seed_defense(self, 10, false); defense.perfect_on_update = true;
    state->ego = 0;
    recording_watch();
    CHECK(!frame()); /* contact reward even when defense hands back native VM */
    CHECK(state->ego == 8 && defense.rewards == 1);
    recording_post_input(self);
    if (SHOWBOAT_RECORDER) {
        recording_before(REC_BEGIN, REC_DEFENSE);
        recording_before(REC_DEFENSE, REC_DECISION);
        CHECK(recording.slots[0].ego == 8 && recording.slots[0].action == 11);
        CHECK(!recording.slots[0].owns);
        CHECK(recording.slots[0].mask == 0); /* spy does not fake module events */
    }
    CHECK(!frame()); recording_post_input(self);
    CHECK(state->ego == 8 && defense.rewards == 1);
    CHECK(recording.frames == 2 * SHOWBOAT_RECORDER);
    if (SHOWBOAT_RECORDER) { CHECK(recording.slots[0].ego == 8); }
}

static void test_recording_no_frame_after_lost_eligibility(void)
{
    for (variant = 0; variant < 10; ++variant) {
        init(); recording_post_input(self);
        int frames = recording.frames, decisions = recording.decisions;
        int posts = combat.posts, suspends = recording.suspends;
        switch (variant) {
        case 0: self->cpu.level = 8; break;
        case 1: world.cpu[0] = false; break;
        case 2: self->kind = FTKIND_FOX; break;
        case 3: self->cpu.xC = 3; break;
        case 4: self->x221F_b3 = true; break;
        case 5: world.entity[0] = &objects[2]; break;
        case 6: self->player_id = 255; break;
        case 7: state->owner = (Fighter*) (uintptr_t) 1; break;
        case 8: self->cpu.level = 8; break; /* late gate, no intervening Update */
        case 9: ShowboatAI_ResetSlot(0); break; /* eligible but unowned */
        }
        if (variant < 7) {
            CHECK(!update(self));
            CHECK(recording.decisions == decisions);
        }
        recording_post_input(self);
        CHECK(combat.posts == posts && recording.frames == frames);
        CHECK(recording.suspends == suspends + SHOWBOAT_RECORDER);
        if (SHOWBOAT_RECORDER) { CHECK(recording.suspend_actor == self); }
    }
}

static void test_recording_no_frame_after_lost_target(void)
{
    for (variant = 0; variant < 5; ++variant) {
        whiff_context(true); CHECK(frame()); recording_post_input(self);
        int frames = recording.frames, decisions = recording.decisions;
        int posts = combat.posts, resets = recording.resets[0];
        switch (variant) {
        case 0: world.entity[1] = NULL; break;
        case 1: world.player_state[1] = 0; break;
        case 2: world.player_state[2] = 2; break;
        case 3: world.secondary[1] = &objects[2]; break;
        case 4: world.ally = true; break;
        }
        recording_watch();
        expect_cancel(); /* retains synchronous full owned-input cancellation */
        CHECK(state->owner == NULL);
        recording_post_input(self);
        CHECK(combat.posts == posts && recording.frames == frames);
        CHECK(recording.decisions == decisions);
        CHECK(recording.resets[0] == resets + SHOWBOAT_RECORDER);
        if (SHOWBOAT_RECORDER) {
            recording_before(REC_BEGIN, REC_RESET);
            recording_before(REC_RESET, REC_SUSPEND);
            CHECK(recording.slots[0].owner == NULL);
        }
    }
}

static void test_recording_postinput_late_target_resolution(void)
{
    for (variant = 0; variant < 2; ++variant) {
        init();
        /* PostInput reacquires the entity; it doesn't reuse opponent_owner or
         * rerun singles arbitration. A late missing entity is forwarded NULL;
         * rejection/segment closure belongs to the separately tested recorder. */
        world.entity[1] = variant ? &objects[2] : NULL;
        recording_post_input(self);
        CHECK(combat.posts == 1 && recording.frames == SHOWBOAT_RECORDER);
        if (SHOWBOAT_RECORDER) {
            CHECK(recording.frame_target == (variant ? &fighters[2] : NULL));
            CHECK(recording.frame_actor == self);
        }
    }
}

static void test_recording_reset_slot_private_and_bounds(void)
{
    init();
    if (SHOWBOAT_RECORDER) {
        for (int i = 0; i < SB_SLOTS; ++i) {
            recording.slots[i].owner = i == 2 ? (Fighter*) (uintptr_t) 1 : &fighters[i];
            recording.slots[i].mask = SBR_EVENT_PUNCH_ACK;
            recording.slots[i].ego = 90 + i;
        }
    }
    RecordingSlot saved[SB_SLOTS], zero = { 0 };
    Fighter before[SB_SLOTS];
    int resets[SB_SLOTS];
    memcpy(saved, recording.slots, sizeof(saved));
    memcpy(resets, recording.resets, sizeof(resets));
    memcpy(before, fighters, sizeof(before));
    ShowboatAI_ResetSlot(-1); ShowboatAI_ResetSlot(SB_SLOTS);
    CHECK(memcmp(saved, recording.slots, sizeof(saved)) == 0);
    CHECK(memcmp(resets, recording.resets, sizeof(resets)) == 0);
    ShowboatAI_ResetSlot(2); ShowboatAI_ResetSlot(2);
    CHECK(memcmp(&recording.slots[2], &zero, sizeof(zero)) == 0);
    for (int i = 0; i < SB_SLOTS; ++i) {
        CHECK(recording.resets[i] == resets[i] + (i == 2 ? 2 * SHOWBOAT_RECORDER : 0));
        if (i != 2) { CHECK(memcmp(&saved[i], &recording.slots[i], sizeof(zero)) == 0); }
    }
    CHECK(memcmp(before, fighters, sizeof(before)) == 0); /* bookkeeping ONLY */
}

static void test_recording_suspend_private_owner_lifecycle(void)
{
    for (variant = 0; variant < 5; ++variant) {
        init(); Fighter* actor = self;
        if (SHOWBOAT_RECORDER) {
            recording.slots[0].mask = SBR_EVENT_TAUNT_ACK;
            recording.slots[2].owner = &fighters[2];
            recording.slots[2].mask = SBR_EVENT_PUNCH_ACK;
        }
        switch (variant) {
        case 1: self->cpu.level = 8; break;
        case 2:
            state->owner = (Fighter*) (uintptr_t) 1;
            if (SHOWBOAT_RECORDER) { recording.slots[0].owner = state->owner; }
            break;
        case 3: fighters[2].player_id = 0; actor = &fighters[2]; break;
        case 4: self->player_id = 255; break;
        }
        RecordingSlot saved[SB_SLOTS], zero = { 0 };
        Fighter before[SB_SLOTS];
        memcpy(saved, recording.slots, sizeof(saved));
        memcpy(before, fighters, sizeof(before));
        int suspends = recording.suspends, resets = recording.resets[0];
        recording_watch();
        suspend(actor); suspend(actor);
        CHECK(recording.suspends == suspends + 2 * SHOWBOAT_RECORDER);
        CHECK(recording.resets[0] == resets + (variant == 1 ? SHOWBOAT_RECORDER : 0));
        CHECK(memcmp(before, fighters, sizeof(before)) == 0);
        if (SHOWBOAT_RECORDER) {
            CHECK(recording.suspend_actor == actor);
            CHECK(recording.trace[0].kind == REC_SUSPEND);
            if (variant == 1) { recording_before(REC_SUSPEND, REC_RESET); }
        }
        CHECK(memcmp(&recording.slots[0], variant < 2 ? &zero : &saved[0], sizeof(zero)) == 0);
        for (int i = 1; i < SB_SLOTS; ++i) {
            CHECK(memcmp(&recording.slots[i], &saved[i], sizeof(zero)) == 0);
        }
    }
}

static void test_recording_owner_replacement_and_rebaseline(void)
{
    for (variant = 0; variant < 4; ++variant) {
        init(); state->ego = 99;
        Fighter* actor = self;
        Fighter* rival = target;
        switch (variant) {
        case 0:
            state->owner = (Fighter*) (uintptr_t) 1;
            if (SHOWBOAT_RECORDER) { recording.slots[0].owner = state->owner; }
            break;
        case 1: fighters[2].player_id = 0; world.entity[0] = &objects[2]; actor = &fighters[2]; break;
        case 2: world.entity[1] = &objects[2]; rival = &fighters[2]; break;
        case 3: world.player_state[1] = 0; world.player_state[2] = 2; rival = &fighters[2]; break;
        }
        int resets = recording.resets[0], decisions = recording.decisions;
        recording_watch();
        CHECK(!update(actor));
        CHECK(state->owner == actor && state->ego == SB_BASE_EGO);
        recording_post_input(actor);
        CHECK(recording.resets[0] == resets + SHOWBOAT_RECORDER);
        CHECK(recording.decisions == decisions + SHOWBOAT_RECORDER);
        if (SHOWBOAT_RECORDER) {
            recording_before(REC_BEGIN, REC_RESET);
            recording_before(REC_RESET, REC_DECISION);
            CHECK(recording.slots[0].owner == actor && recording.slots[0].ego == SB_BASE_EGO);
            CHECK(recording.frame_actor == actor && recording.frame_target == rival);
        }
    }
}

static void recording_ack_sequence(bool punch)
{
    for (variant = 0; variant < (punch ? 3 : 4); ++variant) {
        if (punch) { punch_context(true); } else { taunt_context(true); }
        unsigned mask = punch ? SBR_EVENT_PUNCH_ACK : SBR_EVENT_TAUNT_ACK;
        int action = punch ? SB_PUNCH : SB_TAUNT;
        CHECK(frame()); recording_post_input(self); /* neutral setup */
        CHECK(state->action == action && state->age == 1);
        CHECK(recording.events == 0);
        recording_watch();
        CHECK(update(self)); /* press QUEUED, not executed/acknowledged */
        CHECK(self->cpu.csP == self->cpu.buffer && self->cpu.buttons == 0);
        CHECK(recording.events == 0);
        interpret(self); recording_post_input(self);
        CHECK(self->cpu.buttons == (punch ? HSD_PAD_B : HSD_PAD_DPADUP));
        CHECK(self->motion_id == ftCo_MS_Wait && state->age == 2);
        CHECK(recording.events == 0 && recording.slots[0].mask == 0);
        bool ack = variant >= 2;
        if (ack || variant == 1) {
            self->motion_id = punch ? ftCa_MS_SpecialN :
                              variant == 3 ? ftCo_MS_AppealSL : ftCo_MS_AppealSR;
        }
        if (variant == 1) { self->cpu.xA4 = 91; } /* native preemption, even in ack motion */
        recording_watch();
        CHECK(frame() == ack); recording_post_input(self);
        CHECK(recording.events == (ack ? SHOWBOAT_RECORDER : 0));
        if (SHOWBOAT_RECORDER) {
            CHECK(recording.slots[0].mask == (ack ? mask : 0));
            if (ack) {
                recording_before(REC_BEGIN, REC_EVENT);
                recording_before(REC_EVENT, REC_DECISION);
                recording_before(REC_DECISION, REC_VM);
                recording_before(REC_POST, REC_FRAME);
            }
        }
        CHECK(!frame()); recording_post_input(self);
        CHECK(state->action == SB_NONE);
        CHECK(recording.events == (ack ? SHOWBOAT_RECORDER : 0)); /* no repeat */
        CHECK(recording.slots[0].mask == 0); /* Begin clears preceding event args */
    }
}
static void test_recording_taunt_ack_not_queued(void) { recording_ack_sequence(false); }
static void test_recording_punch_ack_not_queued(void) { recording_ack_sequence(true); }

static void test_recording_last_reason_and_not_evaluated(void)
{
    whiff_context(true);
    recording_watch(); CHECK(frame()); recording_post_input(self);
    if (SHOWBOAT_RECORDER) {
        const int reasons[] = { SBR_NO_CANDIDATE, SBR_STARTED };
        recording_personality_reasons(reasons, 2);
    }
    recording_watch(); CHECK(frame()); recording_post_input(self);
    if (SHOWBOAT_RECORDER) {
        const int reasons[] = { SBR_NO_CANDIDATE, SBR_ACTIVE };
        recording_personality_reasons(reasons, 2);
    }
    self->cpu.xA4 = 91; /* a real native selection preempts, never a recorder write */
    recording_watch(); expect_cancel(); recording_post_input(self);
    CHECK(self->cpu.xA4 == 91);
    if (SHOWBOAT_RECORDER) {
        const int reasons[] = { SBR_CANCELLED, SBR_INPUT_OR_SCRIPT };
        recording_personality_reasons(reasons, 2);
        CHECK(!recording.slots[0].owns);
    }
    combat.owns_input = true;
    recording_watch(); CHECK(frame()); recording_post_input(self);
    if (SHOWBOAT_RECORDER) {
        recording_before(REC_BEGIN, REC_COMBAT);
        recording_before(REC_COMBAT, REC_DECISION);
        for (int i = 0; i < SBR_TACTICS; ++i) {
            CHECK(recording.slots[0].reasons[i] == SBR_NOT_EVALUATED);
        }
        for (int i = 0; i < recording.count; ++i) { CHECK(recording.trace[i].kind != REC_REASON); }
        CHECK(recording.slots[0].owns && recording.slots[0].action == 5);
    }
}

static void test_recording_reason_override_paths(void)
{
    const int last[] = { SBR_PHYSICAL_OR_STATE, SBR_EGO_OR_CAUTION,
                         SBR_NATIVE_PRIORITY, SBR_GEOMETRY_OR_WINDOW,
                         SBR_COOLDOWN, SBR_COMPLETED, SBR_BUDGET };
    for (variant = 0; variant < 7; ++variant) {
        init();
        switch (variant) {
        case 0: self->x2219_b5 = true; break;
        case 1: state->serious = 10; break;
        case 2: self->cpu.x18 = 6; break;
        case 3: target->ground_or_air = GA_Air; break;
        case 4: offstage_context(1, false); state->serious = 0; state->offstage_cooldown = 5; break;
        case 5:
            dance_context(true); CHECK(frame()); state->age = 24;
            break;
        case 6: taunt_context(true); CHECK(frame()); target->mv.co.unk_deadleft.x40 = 19; break;
        }
        recording_watch();
        CHECK(!frame()); recording_post_input(self);
        CHECK(recording.frames == SHOWBOAT_RECORDER);
        if (SHOWBOAT_RECORDER) {
            CHECK(recording.slots[0].reasons[SBR_PERSONALITY] == last[variant]);
            int reason = -1;
            for (int i = 0; i < recording.count; ++i) {
                if (recording.trace[i].kind == REC_REASON) {
                    reason = recording.trace[i].b;
                    CHECK(i > recording_index(REC_BEGIN) && i < recording_index(REC_DECISION));
                }
            }
            CHECK(reason == last[variant]);
            CHECK(!recording.slots[0].owns);
        }
    }
}
