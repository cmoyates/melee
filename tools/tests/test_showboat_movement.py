#!/usr/bin/env python3
"""Host tests including ACTUAL showboat_movement.c; no assets or PPC SDK.

Run: python3 tools/tests/test_showboat_movement.py -v
Both SHOWBOAT_AI_DEBUG modes use ASan/UBSan. Typed host fixtures are not the
PPC ABI or a physics/animation emulator. Motion observations are explicit;
controller script age never changes motion. No copied movement/AI policy.
Unknown production APIs fail compilation/linking; unknown VM opcodes fail.
"""

from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "showboat_movement"
STUB_HEADERS = (
    "melee/ft/forward.h", "melee/ft/fighter.h", "melee/ft/ftanim.h",
    "melee/ft/ftcoll.h", "melee/ft/ftcmdscript.h", "melee/ft/types.h",
    "melee/ft/kinds/ftCommon/ftCo_0A01.h", "melee/mp/mplib.h",
    "melee/gr/stage.h", "dolphin/os.h", "melee/pl/player.h",
    "sysdolphin/baselib/gobj.h",
)
ENUMS = (
    ("src/melee/ft/forward.h", "FighterKind"),
    ("src/melee/ft/forward.h", "GroundOrAir"),
    ("src/melee/ft/kinds/ftCommon/forward.h", "ftCommon_MotionState"),
    ("src/melee/ft/kinds/ftCommon/forward.h", "ftCo_JumpInput"),
    ("src/melee/ft/kinds/ftCaptain/forward.h", "ftCaptain_MotionState"),
    ("src/melee/ft/ftcmdscript.h", "CPUCommand"),
    ("src/melee/gr/forward.h", "StKind"),
)


class ShowboatMovementHostTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which(os.environ.get("SHOWBOAT_TEST_CC", "clang"))
        if compiler is None:
            raise RuntimeError("clang is required (or set SHOWBOAT_TEST_CC)")
        # Compile in place, never a copied production implementation. Reject
        # concurrent revisions rather than accidentally compare different modes.
        paths = {
            ROOT / "src/melee/mod/showboat_movement.c",
            ROOT / "src/melee/mod/showboat_movement.h",
            *(ROOT / path for path, _ in ENUMS),
            *FIXTURES.glob("*.c"), *FIXTURES.glob("*.h"),
        }
        sources = {path: path.read_bytes() for path in paths}
        cls.temp = tempfile.TemporaryDirectory(prefix="showboat-movement-tests-")
        cls.addClassCleanup(cls.temp.cleanup)
        work = Path(cls.temp.name)
        include = work / "include"
        include.mkdir()
        shutil.copyfile(FIXTURES / "game.h", include / "sb_test_game.h")
        enums = []
        for path, name in ENUMS:
            match = re.search(
                rf"typedef enum {name}\s*\{{.*?\}}\s*{name};",
                sources[ROOT / path].decode(), re.S,
            )
            if match is None:
                raise AssertionError(f"Cannot extract native enum {name} from {path}")
            enums.append(match.group())
        (include / "sb_native_enums.h").write_text("\n".join(enums) + "\n")
        for header in STUB_HEADERS:
            dest = include / header
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text('#include "sb_test_game.h"\n')
        cls.binaries = []
        for debug in (0, 1):
            binary = work / f"movement-debug-{debug}"
            command = [
                compiler, "-std=c99", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
                "-Wno-sign-compare", "-fsanitize=address,undefined",
                "-fno-omit-frame-pointer", f"-DSHOWBOAT_AI_DEBUG={debug}",
                "-I", str(include), "-I", str(ROOT / "src/melee/mod"),
                str(FIXTURES / "harness.c"), "-lm", "-o", str(binary),
            ]
            result = subprocess.run(command, capture_output=True, text=True, timeout=60)
            if result.returncode:
                raise AssertionError(
                    f"Host compile failed (debug={debug}):\n{result.stdout}{result.stderr}"
                )
            cls.binaries.append(binary)
        if any(path.read_bytes() != content for path, content in sources.items()):
            raise AssertionError("Movement/native headers/fixtures changed during build; rerun")

    def run_case(self, name):
        for binary in self.binaries:
            with self.subTest(mode=binary.name):
                env = dict(os.environ)
                env["ASAN_OPTIONS"] = "detect_leaks=0:halt_on_error=1"
                env["UBSAN_OPTIONS"] = "halt_on_error=1:print_stacktrace=1"
                result = subprocess.run(
                    [str(binary), name], capture_output=True, text=True,
                    timeout=10, env=env,
                )
                self.assertEqual(
                    result.returncode, 0,
                    f"{name} ({binary.name}):\n{result.stdout}{result.stderr}",
                )
                self.assertEqual(result.stdout.strip(), f"PASS {name}")


def load_tests(loader, tests, pattern):
    names = re.findall(
        r"^\s*CASE\((\w+)\),?$", (FIXTURES / "harness.c").read_text(), re.M,
    )
    if not names or len(names) != len(set(names)):
        raise AssertionError("C harness registry must be nonempty and unique")
    for name in names:
        def test(self, case=name):
            self.run_case(case)
        test.__name__ = f"test_{name}"
        setattr(ShowboatMovementHostTests, test.__name__, test)
    return loader.loadTestsFromTestCase(ShowboatMovementHostTests)


if __name__ == "__main__":
    unittest.main()
