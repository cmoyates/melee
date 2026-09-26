"""Small bounded Slippi result reader; missing end events remain unknown.

Offsets follow https://github.com/project-slippi/slippi-wiki/blob/master/SPEC.md.
"""

import hashlib
import struct

from .stage import STAGE_ID


def game_settings(event):
    if len(event) < 0xF0 or event[0] != 0x36:
        raise ValueError("Incomplete game settings")
    # StartMeleeRules byte 0: match kind in bits 7..5, timer enabled in bit 1.
    # gm_SetupSuddenDeath clears timer_enabled while retaining time_limit.
    return {
        "game_mode": (int(event[0x5]) & 0xE0) >> 5,
        "timer_enabled": bool(event[0x5] & 0x02),
        "timer_counts_up": bool(event[0x5] & 0x01),
        "stage_id": int.from_bytes(event[0x13:0x15], "big"),
        "timer_seconds": int.from_bytes(event[0x15:0x19], "big"),
        "teams": bool(event[0xD]), "items": int(event[0x10]),
        "players": [{"port": i + 1, "character_external": int(event[0x65 + 0x24*i]),
            "type": int(event[0x66 + 0x24*i]), "stocks": int(event[0x67 + 0x24*i]),
            "cpu_level": int(event[0x74 + 0x24*i])} for i in range(4)],
    }


def summarize_raw(raw):
    sizes = {}
    index = 0
    result = {"outcome": "unknown", "winner_port": None, "settings": None}
    while index < len(raw):
        command = raw[index]
        if command == 0x35:
            if index + 2 > len(raw):
                raise ValueError("Truncated event sizes")
            length = raw[index + 1]
            if length < 1 or (length - 1) % 3 or index + length + 1 > len(raw):
                raise ValueError("Invalid event sizes")
            for offset in range(index + 2, index + length + 1, 3):
                sizes[raw[offset]] = int.from_bytes(raw[offset + 1:offset + 3], "big") + 1
            index += length + 1
            continue
        size = sizes.get(command, 0)
        if size < 1 or index + size > len(raw):
            raise ValueError("Unknown or truncated replay event")
        event = raw[index:index + size]
        if command == 0x36:
            result["settings"] = game_settings(event)
        elif command == 0x39:
            if size < 2:
                raise ValueError("Incomplete game end")
            method = int(event[1])
            result["end_method"] = method
            result["outcome"] = {1: "time", 2: "game", 7: "no_contest"}.get(method, "unknown")
            if size >= 7:
                placements = list(struct.unpack("4b", bytes(event[3:7])))
                result["placements"] = placements
                winners = [i + 1 for i, p in enumerate(placements) if p == 0]
                if method in (1, 2) and len(winners) == 1:
                    result["winner_port"] = winners[0]
        index += size
    return result


def summarize_file(path, maximum_bytes):
    import ubjson
    if path.stat().st_size > maximum_bytes:
        raise ValueError("Replay exceeds artifact budget")
    data = path.read_bytes()
    full = ubjson.loadb(data)
    result = summarize_raw(full["raw"])
    result.update(file=path.name, sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))
    return result


def expected_settings(settings, *, phase="regulation"):
    from .rules import STARTING_STOCKS, TIME_LIMIT_SECONDS
    if phase not in ("regulation", "sudden_death"):
        return False
    if not settings or settings["game_mode"] != 1 or settings["stage_id"] != STAGE_ID or settings["teams"]:
        return False
    if settings["timer_seconds"] != TIME_LIMIT_SECONDS or settings["items"] != 255:
        return False
    timed = phase == "regulation"
    if settings.get("timer_enabled", True) is not timed or settings.get("timer_counts_up", False):
        return False
    stocks = STARTING_STOCKS if timed else 1
    a, b, c, d = settings["players"]
    return (a["character_external"] == 2 and a["type"] == 0 and a["stocks"] == stocks and
            b["character_external"] == 8 and b["type"] == 1 and b["stocks"] == stocks and
            b["cpu_level"] == 3 and c["type"] == d["type"] == 3)
