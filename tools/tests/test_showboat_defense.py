#!/usr/bin/env python3
"""Host-test the ACTUAL defense C TU; no Dolphin/assets or third-party packages.

Typed small stubs, not a PPC ABI/physics simulation.
Native enums, pad masks, VM, defense builders and fighter-contact code are extracted
from this checkout. Both debug modes run every case under ASan and UBSan.
"""
from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
FIX = Path(__file__).resolve().parent / "fixtures/showboat_defense"
MODULE = ROOT / "src/melee/mod/showboat_defense.c"
ENUMS = (
    ("src/melee/ft/forward.h", "FighterKind"),
    ("src/melee/ft/kinds/ftCommon/forward.h", "ftCommon_MotionState"),
    ("src/melee/ft/kinds/ftCaptain/forward.h", "ftCaptain_MotionState"),
    ("src/melee/ft/ftcmdscript.h", "CPUCommand"),
    ("src/melee/lb/forward.h", "HitCapsuleState"),
    ("src/melee/lb/forward.h", "HitElement"),
    ("src/melee/it/forward.h", "ItemKind"),
)
HEADERS = (
    "melee/ft/forward.h", "melee/ft/fighter.h", "melee/ft/ftcmdscript.h",
    "melee/ft/kinds/ftCommon/ftCo_0A01.h", "melee/ft/types.h",
    "melee/lb/lbcollision.h", "melee/pl/player.h",
    "sysdolphin/baselib/gobj.h", "dolphin/os.h",
)


class DefenseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc = shutil.which(os.environ.get("SHOWBOAT_TEST_CC", "clang"))
        if cc is None:
            raise RuntimeError("clang required (or set SHOWBOAT_TEST_CC)")
        cls.temp = tempfile.TemporaryDirectory(prefix="showboat-defense-")
        cls.addClassCleanup(cls.temp.cleanup)
        work = Path(cls.temp.name)
        inc = work / "include"
        inc.mkdir()
        shutil.copyfile(FIX / "game.h", inc / "game.h")
        enums = []
        for path, name in ENUMS:
            match = re.search(rf"typedef enum {name}\s*\{{.*?\}}\s*{name};",
                              (ROOT / path).read_text(), re.S)
            if match is None:
                raise AssertionError(f"Native enum missing: {name}")
            enums.append(match.group())
        pads = (ROOT / "src/sysdolphin/baselib/controller.h").read_text()
        # Native 1<<31 is signed-UB on the host: retain mask, use unsigned 1.
        enums += [line.replace("(1 <<", "(1U <<") for line in pads.splitlines()
                  if re.match(r"#define HSD_PAD_\w+ \(1 << \d+\)", line)]
        (inc / "native_enums.h").write_text("\n".join(enums))
        # Whole named function bodies, verbatim from this checkout. No invented
        # perfect-contact or native roll model; dependency stubs are in harness.
        groups = {
            "src/melee/ft/fighter.c": ("Fighter_Spaghetti_8006AD10_Inner1",),
            "src/melee/lb/lbcollision.c": ("lbColl_8000ACFC",),
            "src/melee/ft/ftcmdscript.c": (
                "ftCo_800B3E04", "ftCo_800B462C", "ftCo_800B463C",
                "ftCo_800B46B8", "ftCo_800B49F4", "ftCo_800B4A78"),
            "src/melee/ft/kinds/ftCommon/ftCo_0A01.c": (
                "ftCo_800A0C8C",),
            "src/melee/ft/ftcpuattack.c": (
                "ftCo_CpuSetNeutralStick", "ftCo_800B9F90", "ftCo_800BA080",
                "ftCo_800BA080_dontinline", "ftCo_800BA160", "ftCo_800BA224",
                "inline0", "inline1", "inline2", "ftCo_CpuIsRollOrAirDodge",
                "ftCo_CpuIsSpotDodge", "ftCo_CpuFireBlaster", "ftCo_CpuRetapR",
                "ftCo_800BA9A0", "ftCo_800BB104"),
            "src/melee/ft/kinds/ftCommon/ftCo_Guard.c": (
                "ftCo_80094138", "ftCo_80093694", "ftCo_80093BC0"),
            "src/melee/ft/ftcoll.c": ("getEnvDmg", "ftColl_80076CBC"),
        }
        native = []
        for path, names in groups.items():
            source = (ROOT / path).read_text()
            for name in names:
                match = re.search(
                    rf"^(?:static (?:inline )?)?(?:void|bool|int) {name}\([^;]*?\)\n\{{.*?^\}}",
                    source, re.S | re.M)
                if match is None:
                    raise AssertionError(f"Native function missing: {path}: {name}")
                native.append(match.group())
        (inc / "native_functions.h").write_text("\n\n".join(native))
        for header in HEADERS:
            dest = inc / header
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text('#include "game.h"\n')
        cls.binaries = []
        sources = {p: p.read_bytes() for p in (MODULE, MODULE.with_suffix('.h'))}
        for debug in (0, 1):
            binary = work / f"defense-debug-{debug}"
            cmd = [cc, "-std=c99", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
                   "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
                   f"-DSHOWBOAT_AI_DEBUG={debug}", "-I", str(inc),
                   "-I", str(MODULE.parent), str(MODULE), str(FIX / "harness.c"),
                   "-lm", "-o", str(binary)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode:
                raise AssertionError(result.stdout + result.stderr)
            cls.binaries.append(binary)
        if any(p.read_bytes() != data for p, data in sources.items()):
            raise AssertionError("Module changed during builds; rerun")

    def run_case(self, case):
        for binary in self.binaries:
            with self.subTest(debug=binary.name):
                env = dict(os.environ, ASAN_OPTIONS="detect_leaks=0:halt_on_error=1",
                           UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1")
                result = subprocess.run([str(binary), case], env=env,
                                        capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(result.stdout.strip(), f"PASS {case}")


def load_tests(loader, tests, pattern):
    names = re.findall(r"^\s*CASE\((\w+)\),?$", (FIX / 'harness.c').read_text(), re.M)
    if not names or len(names) != len(set(names)):
        raise AssertionError("Empty/duplicate harness registry")
    for name in names:
        setattr(DefenseTests, f"test_{name}", lambda self, case=name: self.run_case(case))
    return loader.loadTestsFromTestCase(DefenseTests)


if __name__ == "__main__":
    unittest.main()
