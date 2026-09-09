/* Include the ACTUAL production translation unit. Only dependencies below are
 * host fixtures; no copied AI, asset files, game runtime, or ego implementation. */
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "showboat_movement.c"

static const char* case_name;
static int variant;
#define CHECK(e) do { if (!(e)) { \
    fprintf(stderr, "%s variant=%d %s:%d: %s\n", \
            case_name, variant, __FILE__, __LINE__, #e); exit(1); \
} } while (0)
#define CLOSE(a, b) CHECK(fabsf((a) - (b)) < 0.0001f)
#include "engine.c"
#include "cases.c"
#include "guards.c"
#include "lifecycle.c"
#include "admission.c"

#define CASE(name) { #name, name }
static const struct { const char* name; void (*run)(void); } cases[] = {
    CASE(jumpf_escapeair_ack),
    CASE(jumpb_escapeair_ack),
    CASE(direct_landing_special_ack),
    CASE(release_observed_kneebend),
    CASE(x_release_tail_without_update),
    CASE(l_release_tail_without_update),
    CASE(jump_not_inferred_from_input_age),
    CASE(no_kneebend_observation_no_dodge),
    CASE(no_jump_observation_no_dodge),
    CASE(repeated_jump_sample_no_repeated_l),
    CASE(missed_neutral_sample),
    CASE(missed_x_sample),
    CASE(missed_kneebend_release_sample),
    CASE(stale_airborne_start),
    CASE(late_first_jump_sample),
    CASE(nonjump_airborne_after_knees),
    CASE(finite_failed_jump_cooldown_retry),
    CASE(native_landing_lag_not_rewritten),
    CASE(invalid_public_arguments),
    CASE(retreat_committed_normal_attack),
    CASE(retreat_requires_commitment),
    CASE(forward_medium_band_and_native_run),
    CASE(unsupported_ground_motions),
    CASE(eligibility_and_live_native_priority),
    CASE(unavailable_actor_or_target),
    CASE(conflicting_controls),
    CASE(neutral_must_be_observed),
    CASE(xy_kneebend_requires_observed_press),
    CASE(first_jump_precise_guards),
    CASE(missing_floor_platform_edge_stage),
    CASE(runway_accounts_for_direction_and_coast),
    CASE(floor_continuity_during_action),
    CASE(ecb_sweep_not_origin_or_air_index),
    CASE(sweep_gap_skip_and_stale_ecb_veto),
    CASE(unsafe_physics_and_constants),
    CASE(new_native_priority_and_script_win),
    CASE(cached_a4_preserved_old_inputs_released),
    CASE(changed_priority_releases_old_vm_preserves_decision),
    CASE(replacement_neutral_vm_not_retaken),
    CASE(malformed_or_replaced_vm_not_retaken),
    CASE(consumed_tail_is_missed_sample_not_clear_vm),
    CASE(empty_native_vm_transition_retake),
    CASE(suspend_all_phases_idempotent),
    CASE(target_identity_and_threat_changes),
    CASE(slot_spawn_and_primary_identity),
    CASE(slots_are_independent),
    CASE(escape_ack_release_is_bounded),
    CASE(native_landing_ack_preserves_new_script),
    CASE(success_changes_only_script_and_cpu_outputs),
    CASE(queued_native_attack_or_unknown_command_wins),
    CASE(malformed_pending_native_vm_rejected),
    CASE(pending_mundane_locomotion_admitted),
    CASE(new_precise_threat_and_facing_guards),
};
int main(int argc, char** argv)
{
    CHECK(argc == 2); case_name = argv[1];
    for (unsigned i = 0; i < sizeof(cases) / sizeof(cases[0]); ++i) {
        if (!strcmp(case_name, cases[i].name)) {
            cases[i].run(); printf("PASS %s\n", case_name); return 0;
        }
    }
    fprintf(stderr, "unknown case: %s\n", case_name); return 2;
}
