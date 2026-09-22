"""Retain Slippi values before libmelee normalizes action-frame indexing.

Offsets mirror the pinned libmelee Console.__post_frame implementation. Native
IDs are an explicit mapping, never inferred by treating distinct enums equally.
"""

from collections import OrderedDict
import math
import struct

from .stage import GROUND_EDGE, PLATFORMS, STAGE_ID, STAGE_NAME, support_surface


CHARACTERS = {0: {"name": "MARIO", "native_fighter_kind": 0, "external_css_id": 8},
                1: {"name": "FOX", "native_fighter_kind": 1, "external_css_id": 2}}
# Explicit common-motion subset checked against ft/kinds/ftCommon/forward.h.
# Character-specific action semantics are deliberately left unmapped for J18.
NATIVE_ACTIONS = {0: "ftCo_MS_DeadDown", 12: "ftCo_MS_Rebirth", 13: "ftCo_MS_RebirthWait",
    14: "ftCo_MS_Wait", 18: "ftCo_MS_Turn", 20: "ftCo_MS_Dash", 21: "ftCo_MS_Run",
    24: "ftCo_MS_KneeBend", 25: "ftCo_MS_JumpF", 26: "ftCo_MS_JumpB",
    27: "ftCo_MS_JumpAerialF", 28: "ftCo_MS_JumpAerialB", 29: "ftCo_MS_Fall",
    178: "ftCo_MS_GuardOn", 179: "ftCo_MS_Guard", 180: "ftCo_MS_GuardOff"}
POST_FIELDS = {"character_internal_id": (0x7, ">B"), "action_id": (0x8, ">H"),
    "x": (0xa, ">f"), "y": (0xe, ">f"), "facing": (0x12, ">f"),
    "percent": (0x16, ">f"), "shield": (0x1a, ">f"), "stocks": (0x21, ">B"),
    "action_frame_raw": (0x22, ">f"), "state_flags_2": (0x27, ">B"), "state_flags_4": (0x29, ">B"),
    "misc_as_raw": (0x2b, ">f"),
    "airborne": (0x2f, ">B"), "jumps": (0x32, ">B"), "hurtbox_state": (0x34, ">B"),
    "speed_air_x_self": (0x35, ">f"), "speed_y_self": (0x39, ">f"),
    "speed_x_attack": (0x3d, ">f"), "speed_y_attack": (0x41, ">f"),
    "speed_ground_x_self": (0x45, ">f"), "hitlag_raw": (0x49, ">f")}


def decode_post(event):
    if len(event) < 7 or event[0] != 0x38:
        raise ValueError("Invalid post-frame event")
    result = {"frame": struct.unpack_from(">i", event, 1)[0], "port": event[5] + 1,
                "secondary": bool(event[6]), "event_bytes": len(event), "available": {}}
    for name, (offset, fmt) in POST_FIELDS.items():
        present = offset + struct.calcsize(fmt) <= len(event)
        value = struct.unpack_from(fmt, event, offset)[0] if present else None
        result["available"][name] = present and (not isinstance(value, float) or math.isfinite(value))
        result[name] = value if result["available"][name] else None
    return result


def normalized_hurtbox(raw):
    value = raw.get("hurtbox_state")
    return value if raw.get("available", {}).get("hurtbox_state") and type(value) is int and value in (0, 1, 2) else None


def combat_counters(raw):
    """0x2B is a reused motion field; only flag 4 bit 0x02 means hitstun.

    Source: project-slippi/slippi-wiki SPEC.md, Post-Frame Update/state flags.
    A still-set flag with a zero/fractional remainder conservatively inhibits
    actions for this observation. Original floats/flags remain in the raw trace.
    """
    required = ("state_flags_2", "state_flags_4", "misc_as_raw", "hitlag_raw")
    if not all(raw["available"].get(name) for name in required):
        raise ValueError("Combat state flags/counters unavailable")
    hitlag = max(1, math.ceil(raw["hitlag_raw"])) if raw["state_flags_2"] & 0x20 else 0
    hitstun = max(1, math.ceil(raw["misc_as_raw"])) if raw["state_flags_4"] & 0x02 else 0
    return hitlag, hitstun


class RawStreamTap:
    """Pinned adapter hook; at most 64 post-frame events are retained."""
    def __init__(self, console):
        self.events = OrderedDict()
        original = console._Console__post_frame
        def post(state, event):
            original(state, event)
            # libmelee passes the remaining stream buffer, not just this event.
            decoded = decode_post(event[:int(console.eventsize[0x38])])
            if not decoded["secondary"]:
                self.events[decoded["frame"], decoded["port"]] = decoded
                while len(self.events) > 64:
                    self.events.popitem(last=False)
        console._Console__post_frame = post

    def take(self, frame, port):
        try:
            return self.events.pop((frame, port))
        except KeyError:
            raise ValueError("Missing raw observation for returned frame") from None


class LifeTracker:
    """Life generation changes on stock loss; includes the death/respawn phase."""
    def __init__(self):
        self.previous = {}

    def observe(self, episode, port, stocks):
        key = (episode, port)
        previous, generation = self.previous.get(key, (stocks, 1))
        if stocks > previous:
            raise ValueError("Stocks increased inside an episode")
        generation += previous - stocks
        self.previous = {k: v for k, v in self.previous.items() if k[0] == episode}
        self.previous[key] = (stocks, generation)
        return generation


def player_record(player, raw, episode, port, lives, zero_indices):
    port = int(port)  # libmelee player-map keys are NumPy integers.
    character_id = raw["character_internal_id"]
    action_id = raw["action_id"]
    if character_id != int(player.character.value) or action_id != int(player.action.value):
        raise ValueError("Raw and normalized IDs disagree")
    normalized = int(player.action_frame)
    raw_frame = raw["action_frame_raw"]
    adjustment = int(action_id in zero_indices.get(character_id, set()))
    if raw_frame is None or normalized != int(raw_frame) + adjustment:
        raise ValueError("Action-frame normalization disagrees with pinned adapter")
    name = getattr(player.action, "name", None)
    return {"port": port, "life_generation_derived": lives.observe(episode, port, int(player.stock)),
        "life_phase_derived": "dead" if 0 <= action_id <= 10 else
            "respawn" if action_id in (12, 13) else "active_or_unknown",
        "raw_post": raw, "character_mapping": CHARACTERS.get(character_id),
        "action_mapping": {"libmelee_name": name, "available": name is not None,
                            "native_motion_state_mapping": NATIVE_ACTIONS.get(action_id)},
        "action_frame_libmelee": normalized, "action_frame_adjustment": adjustment,
        "hitstun_libmelee": int(player.hitstun_frames_left),
        "hitlag_libmelee": int(player.hitlag_left),
        "grounded_libmelee": bool(player.on_ground),
        "invulnerable_libmelee": bool(player.invulnerable),
        "support_surface_derived": support_surface(float(player.position.x), float(player.position.y), bool(player.on_ground))}


def stage_record():
    return {"name": STAGE_NAME, "slippi_external_id": STAGE_ID, "libmelee_id": STAGE_ID,
            "native_gr_kind_mapped": 0x24, "ground_edge_approximate": GROUND_EDGE,
            "platforms_approximate": PLATFORMS, "native_collision_query_available": False}
