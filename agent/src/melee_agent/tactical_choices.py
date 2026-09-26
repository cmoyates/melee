"""One ordered grounded tactical catalog for comparable selectors."""

from .skills import can_start, relative_skill

LABELS = ("neutral", "approach", "retreat", "jump", "shield", "jab", "dtilt", "grab")
PROFILE = "grounded-tactical-v1"


def legal_candidates(observation):
    return tuple(label for label in LABELS if can_start(relative_skill(label, observation), observation) is None)
