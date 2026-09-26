"""One ordered grounded tactical catalog for comparable selectors."""

from .skills import can_start, relative_skill

LABELS = ("neutral", "approach", "retreat", "jump", "shield", "jab", "dtilt", "grab")
PROFILE = "grounded-tactical-v1"
OPTION_PROFILE = "approach-jab-v1"
AERIAL_PROFILE = "fox-aerial-v1"
PROFILES = {PROFILE: LABELS, OPTION_PROFILE: (*LABELS, "approach_jab"),
    AERIAL_PROFILE: (*LABELS, "approach_jab", "sh_nair")}


def profile_labels(profile=PROFILE):
    if profile not in PROFILES:
        raise ValueError("Unknown tactical candidate profile")
    return PROFILES[profile]


def legal_candidates(observation, profile=PROFILE):
    return tuple(label for label in profile_labels(profile) if can_start(relative_skill(label, observation), observation) is None)
