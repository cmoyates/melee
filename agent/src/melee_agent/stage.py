"""Battlefield geometry from the pinned libmelee stages.py static tables.

These are approximate support surfaces, not native collision queries.
"""

STAGE_NAME = "BATTLEFIELD"
STAGE_ID = 31
GROUND_EDGE = 68.4000015259
# Native grounded origins can lie just beyond these approximate intervals.
# Recorded Fox samples include top x=18.80141 and right x=57.63696. This small
# tolerance requires native grounded status and the existing height check; it
# does not expand the separate movement destination/edge safety margins.
SUPPORT_HORIZONTAL_TOLERANCE = 0.1
PLATFORMS = (
    {"id": "left", "height": 27.20009994506836, "left": -57.60000228881836, "right": -20.0},
    {"id": "right", "height": 27.20009994506836, "left": 20.0, "right": 57.60000228881836},
    {"id": "top", "height": 54.40010070800781, "left": -18.80000114440918, "right": 18.80000114440918},
)


def support_surface(x, y, grounded):
    if not grounded:
        return None
    if -GROUND_EDGE-SUPPORT_HORIZONTAL_TOLERANCE <= x <= GROUND_EDGE+SUPPORT_HORIZONTAL_TOLERANCE and abs(y) < 0.5:
        return "ground"
    for platform in PLATFORMS:
        if (platform["left"]-SUPPORT_HORIZONTAL_TOLERANCE <= x <= platform["right"]+SUPPORT_HORIZONTAL_TOLERANCE
                and abs(y - platform["height"]) < 0.5):
            return platform["id"]
    return "unknown"
