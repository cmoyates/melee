#!/usr/bin/env python3
"""Deterministic HOST tests of unmodified src/melee/mod/showboat_combat.c.

Run: python3 tools/tests/test_showboat_combat.py -v
Requires clang, no assets/configure/PPC SDK or third-party Python packages.
Both SHOWBOAT_AI_DEBUG modes run under ASan/UBSan. Lightweight host fixtures
are NOT the PPC ABI, an emulator, or a frame-accurate collision/animation test.
The fixture VM only samples controller scripts; motion changes are explicit
external observations, NEVER inferred from script age. Unknown APIs fail to
compile/link and unknown script opcodes fail at runtime.
"""

from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "showboat_combat"
HARNESS = FIXTURES / "harness.c"
STUB_HEADERS = (
    "melee/ft/forward.h", "melee/ft/fighter.h", "melee/ft/ftanim.h",
    "melee/ft/ftcoll.h", "melee/ft/ftcmdscript.h", "melee/ft/types.h",
    "melee/ft/kinds/ftCaptain/forward.h",
    "melee/ft/kinds/ftCommon/ftCo_0A01.h", "melee/mp/mplib.h", "dolphin/os.h",
    "melee/gr/stage.h",
)
ENUMS = (
    ("src/melee/ft/forward.h", "FighterKind"),
    ("src/melee/ft/kinds/ftCommon/forward.h", "ftCommon_MotionState"),
    ("src/melee/ft/kinds/ftCaptain/forward.h", "ftCaptain_MotionState"),
    ("src/melee/ft/ftcmdscript.h", "CPUCommand"),
    ("src/melee/gr/forward.h", "StKind"),
)


class ShowboatCombatHostTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which(os.environ.get("SHOWBOAT_TEST_CC", "clang"))
        if compiler is None:
            raise RuntimeError("clang is required (or set SHOWBOAT_TEST_CC)")
        # Do not accidentally validate debug modes from different concurrent
        # revisions. Include production in place, but reject mid-build edits.
        sources = {
            ROOT / path: (ROOT / path).read_bytes()
            for path in [
                "src/melee/mod/showboat_combat.c",
                "src/melee/mod/showboat_combat.h",
                *(path for path, _ in ENUMS),
            ]
        }
        cls.temp = tempfile.TemporaryDirectory(prefix="showboat-combat-tests-")
        cls.addClassCleanup(cls.temp.cleanup)
        work = Path(cls.temp.name)
        include = work / "include"
        include.mkdir()
        shutil.copyfile(FIXTURES / "game.h", include / "sb_test_game.h")
        enums = []
        for path, name in ENUMS:
            match = re.search(
                rf"typedef enum {name}\s*\{{.*?\}}\s*{name};",
                (ROOT / path).read_text(), re.S,
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
            binary = work / f"combat-debug-{debug}"
            command = [
                compiler, "-std=c99", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
                "-Wno-sign-compare", "-fsanitize=address,undefined",
                "-fno-omit-frame-pointer", f"-DSHOWBOAT_AI_DEBUG={debug}",
                "-I", str(include), "-I", str(ROOT / "src/melee/mod"),
                str(HARNESS), "-lm", "-o", str(binary),
            ]
            result = subprocess.run(command, capture_output=True, text=True, timeout=60)
            if result.returncode:
                raise AssertionError(
                    f"Host compile failed (debug={debug}):\n{result.stdout}{result.stderr}"
                )
            cls.binaries.append(binary)
        if any(path.read_bytes() != content for path, content in sources.items()):
            raise AssertionError("Combat/native headers changed during compilation; rerun")

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
    names = re.findall(r"^\s*CASE\((\w+)\),?$", HARNESS.read_text(), re.M)
    if not names or len(names) != len(set(names)):
        raise AssertionError("C harness registry must be nonempty and unique")
    for name in names:
        def test(self, case=name):
            self.run_case(case)
        test.__name__ = f"test_{name}"
        setattr(ShowboatCombatHostTests, test.__name__, test)
    return loader.loadTestsFromTestCase(ShowboatCombatHostTests)


if __name__ == "__main__":
    unittest.main()
