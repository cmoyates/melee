#!/usr/bin/env python3
"""Validate the local modified DOL and source-object isolation, not gameplay."""
import argparse
import hashlib
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STOCK_SHA1 = "08e0bf20134dfcb260699671004527b2d6bb1a45"
EXPECTED_OBJECTS = {
    "melee/ft/fighter.o",
    "melee/ft/ftcpuattack.o",
    "melee/ft/kinds/ftCommon/ftCo_0A01.o",
    "melee/mod/showboat_ai.o",
    "melee/mod/showboat_combat.o",
    "melee/mod/showboat_movement.o",
    "melee/mod/showboat_defense.o",
    "melee/mod/showboat_hud.o",
    "melee/pl/player.o",
}


def require(ok, message):
    if not ok:
        raise SystemExit(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-unlocks", action="store_true",
                        help="expect a build made with --no-showboat-unlock-all")
    parser.add_argument("--no-quickstart", action="store_true",
                        help="expect a build made with --no-showboat-quickstart")
    args = parser.parse_args()
    expected = EXPECTED_OBJECTS.copy()
    if not args.no_quickstart:
        expected.add("melee/gm/gmboot.o")
    if not args.no_unlocks:
        expected.add("melee/gm/gmmain_lib.o")
    path = ROOT / "build/showboat/GALE01/main.dol"
    data = path.read_bytes()
    require(len(data) >= 256, "Truncated DOL")
    offsets = struct.unpack_from(">18I", data)
    addresses = struct.unpack_from(">18I", data, 0x48)
    sizes = struct.unpack_from(">18I", data, 0x90)
    bss, bss_size, entry = struct.unpack_from(">3I", data, 0xD8)
    require(0x80000000 <= bss < bss + bss_size <= 0x81800000,
            "BSS outside GameCube main RAM")
    sections = []
    for i, (offset, address, size) in enumerate(zip(offsets, addresses, sizes)):
        if size == 0:
            continue
        require(256 <= offset and offset + size <= len(data), "Invalid section extent")
        require(0x80000000 <= address < address + size <= 0x81800000,
                "Section outside GameCube main RAM")
        sections.append(dict(index=i, offset=offset, address=address, size=size))
    require(any(s["index"] < 7 and s["address"] <= entry < s["address"] + s["size"]
                for s in sections), "Entry point outside text")
    for i, a in enumerate(sections):
        for b in sections[i + 1:]:
            for coordinate in ("address", "offset"):
                require(a[coordinate] + a["size"] <= b[coordinate] or
                        b[coordinate] + b["size"] <= a[coordinate],
                        "Overlapping initialized sections")
    # Retail's BSS envelope includes initialized small-data sections. It is
    # intentionally not subjected to the initialized-section overlap test.
    for name in ("orig/GALE01/sys/main.dol", "build/GALE01/main.dol"):
        require(hashlib.sha1((ROOT / name).read_bytes()).hexdigest() == STOCK_SHA1,
                f"Stock reference changed: {name}")
    current = ROOT / "build/showboat/GALE01/src"
    baseline = ROOT / "build/cstick/GALE01/src"
    require(baseline.is_dir(), "Need preserved C-stick source objects for isolation check")
    changed = set()
    for obj in current.rglob("*.o"):
        name = obj.relative_to(current)
        old = baseline / name
        if not old.exists() or obj.read_bytes() != old.read_bytes():
            changed.add(name.as_posix())
    require(changed == expected, f"Unexpected changed objects: {sorted(changed)}")
    report = dict(
        dol=path.relative_to(ROOT).as_posix(), size=len(data),
        sha1=hashlib.sha1(data).hexdigest(), entry=hex(entry),
        bss=[hex(bss), bss_size], valid_sections=sections,
        original_dols_preserved=True, test_unlocks=not args.no_unlocks,
        test_quickstart=not args.no_quickstart,
        objects_different_from_cstick=sorted(changed),
    )
    (ROOT / "build/showboat/verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Validated {report['dol']}: {len(data):,} bytes, SHA-1 {report['sha1']}")
    count = 4 + int(not args.no_unlocks) + int(not args.no_quickstart)
    print(f"Stock DOLs unchanged; exactly {count} hooked objects plus the AI/combat/movement/defense/HUD modules differ from C-stick.")


if __name__ == "__main__":
    main()
