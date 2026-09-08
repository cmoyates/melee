#!/usr/bin/env python3
"""Insert the rebuilt DOL into our generated, verified stock ISO copy only.

First convert the user's CISO to build/cstick/Melee-Single-Player-C-Stick.iso
using dtk disc convert. This script refuses an already-patched or unknown ISO.
It never writes the user's source disc or orig/GALE01/sys/main.dol.
"""

import hashlib
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ISO = ROOT / "build/cstick/Melee-Single-Player-C-Stick.iso"
DOL = ROOT / "build/cstick/GALE01/main.dol"
ORIGINAL = ROOT / "orig/GALE01/sys/main.dol"
DISC_SHA1 = "d4e70c064cc714ba8400a849cf299dbd1aa326fc"
DOL_SHA1 = "08e0bf20134dfcb260699671004527b2d6bb1a45"


def require(condition, message):
    if not condition:
        raise SystemExit(message)


def main():
    require(not ISO.is_symlink(), "Refusing to patch a symlink")
    original = ORIGINAL.read_bytes()
    rebuilt = DOL.read_bytes()
    require(hashlib.sha1(original).hexdigest() == DOL_SHA1,
            "Original DOL is not Melee US v1.02")
    require(len(rebuilt) >= 0x100 and rebuilt != original,
            "Expected a rebuilt, modified DOL")

    # Validate each initialized section's extent and the executable entry point.
    offsets = struct.unpack_from(">18I", rebuilt, 0)
    addresses = struct.unpack_from(">18I", rebuilt, 0x48)
    sizes = struct.unpack_from(">18I", rebuilt, 0x90)
    entry = struct.unpack_from(">I", rebuilt, 0xE0)[0]
    for offset, size in zip(offsets, sizes):
        if size:
            require(0x100 <= offset and offset + size <= len(rebuilt),
                    "Invalid rebuilt DOL section")
    require(any(address <= entry < address + size
                for address, size in zip(addresses[:7], sizes[:7]) if size),
            "DOL entry point is outside its text sections")

    with ISO.open("r+b") as image:
        require(hashlib.file_digest(image, "sha1").hexdigest() == DISC_SHA1,
                "ISO is not the unmodified US v1.02 disc. Reconvert the original CISO first.")
        image.seek(0)
        header = image.read(0x440)
        require(header[:6] == b"GALE01" and header[7] == 2,
                "Wrong game/revision")
        dol_offset, fst_offset = struct.unpack_from(">II", header, 0x420)
        require(0 < dol_offset < fst_offset and len(rebuilt) <= fst_offset - dol_offset,
                "Rebuilt DOL will not fit before the filesystem table; no changes made")
        image.seek(dol_offset)
        require(image.read(len(original)) == original,
                "Embedded original DOL does not match the verified input")
        image.seek(dol_offset)
        image.write(rebuilt)
        image.flush()
        image.seek(dol_offset)
        require(image.read(len(rebuilt)) == rebuilt, "Embedded DOL verification failed")

    print(f"Packaged: {ISO}")
    print(f"DOL SHA-1: {hashlib.sha1(rebuilt).hexdigest()}")
    print("Only the embedded DOL was overwritten; source disc and original DOL untouched.")


if __name__ == "__main__":
    main()
