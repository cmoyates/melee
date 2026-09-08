#!/usr/bin/env python3
"""Deterministic HOST unit tests of the actual showboat_ai.c (NOT an emulator test).

Run: python3 -m unittest discover -s tools/tests -p 'test_showboat_ai.py' -v
Or:  python3 tools/tests/test_showboat_ai.py -v

Requires clang; no game assets, configure step, target SDK, or Python packages.
Both debug modes run with AddressSanitizer and UndefinedBehaviorSanitizer. The
real module is #included, unmodified, so its private state/helpers are exercised.
Game layouts/queries and a small input-script VM are stubs, not the game engine:
these tests do NOT prove in-game animation timing, collision, stock arbitration,
build opt-in wiring, PPC ABI correctness, or behavior in Dolphin/hardware.

Fixtures live in fixtures/showboat_ai/. Add C cases to the CASE(...) registry;
load_tests discovers them, so command-weighting tests can be added there without
rewriting this runner. Unknown native calls/opcodes fail rather than silently
being treated as neutral. Enum declarations are copied from current game headers
so range comparisons and script bytes aren't based on invented motion IDs.
"""

from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "showboat_ai"
HARNESS = FIXTURES / "harness.c"

# Only this include tree is available to the host compilation, not the PPC SDK.
STUB_HEADERS = (
    "melee/ft/forward.h",
    "melee/ft/fighter.h",
    "melee/ft/ftcoll.h",
    "melee/ft/ftcmdscript.h",
    "melee/ft/kinds/ftCaptain/forward.h",
    "melee/ft/kinds/ftCommon/ftCo_0A01.h",
    "melee/ft/types.h",
    "melee/gm/gm_16AE.h",
    "melee/pl/player.h",
    "melee/mp/mpcoll.h",
    "dolphin/os.h",
)
ENUMS = (
    ("src/melee/ft/forward.h", "FighterKind"),
    ("src/melee/ft/kinds/ftCommon/forward.h", "ftCommon_MotionState"),
    ("src/melee/ft/kinds/ftCaptain/forward.h", "ftCaptain_MotionState"),
    ("src/melee/ft/ftcmdscript.h", "CPUCommand"),
)


class ShowboatHostTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which(os.environ.get("SHOWBOAT_TEST_CC", "clang"))
        if compiler is None:
            raise RuntimeError("clang is required (or set SHOWBOAT_TEST_CC)")
        cls.temp = tempfile.TemporaryDirectory(prefix="showboat-host-tests-")
        cls.addClassCleanup(cls.temp.cleanup)
        work = Path(cls.temp.name)
        include = work / "include"
        include.mkdir()
        shutil.copyfile(FIXTURES / "game.h", include / "sb_test_game.h")
        enums = []
        for path, name in ENUMS:
            source = (ROOT / path).read_text()
            match = re.search(
                rf"typedef enum {name}\s*\{{.*?\}}\s*{name};", source, re.S
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
            binary = work / f"showboat-debug-{debug}"
            command = [
                compiler, "-std=c99", "-O1", "-g", "-Wall", "-Wextra",
                "-Werror", "-Wno-sign-compare",  # native s32 spawn vs u32 state
                "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
                f"-DSHOWBOAT_AI_DEBUG={debug}", "-I", str(include),
                "-I", str(ROOT / "src/melee/mod"), str(HARNESS),
                "-o", str(binary),
            ]
            result = subprocess.run(command, capture_output=True, text=True, timeout=60)
            if result.returncode:
                raise AssertionError(
                    f"Host compile failed (debug={debug}):\n"
                    f"{result.stdout}{result.stderr}"
                )
            cls.binaries.append(binary)

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
    # Read only the explicit registry, not C function bodies or production code.
    names = re.findall(r"^\s*CASE\((\w+)\),?$", HARNESS.read_text(), re.M)
    if not names or len(names) != len(set(names)):
        raise AssertionError("C harness case registry must be nonempty and unique")
    for name in names:
        def test(self, case=name):
            self.run_case(case)
        test.__name__ = f"test_{name}"
        setattr(ShowboatHostTests, test.__name__, test)
    return loader.loadTestsFromTestCase(ShowboatHostTests)


if __name__ == "__main__":
    unittest.main()
