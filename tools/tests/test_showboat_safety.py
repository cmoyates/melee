#!/usr/bin/env python3
"""Actual safety production TU, COMPLETE native Fighter/CpuFighter declarations.

Run: python3 tools/tests/test_showboat_safety.py -v
Requires clang (ASan/UBSan + PPC syntax target), nm, and this checkout's native
headers. No Python packages, assets, configure, DOL, emulator or live playtest.

Unlike shortened host stubs, all native Fighter fields/unions/padding are copied
and compared for both fighters and a third sentinel. Native headers are used
unchanged on host (longs/pointers/layout differ from PPC); host builds do NOT
assert PPC offsets. Separate freestanding PPC syntax checks enable native layout
assertions with LINT. Map/player queries are controlled stubs; read-only native
eligibility, extension/adjacency and horizontal intersection bodies are extracted
verbatim. The overlap fixture models mpCheckFloor's strict first-hit tie scan,
including all three isolated BF platforms without adjacent extension. Platform
certificates use controlled native MapCollData/CollJoint/CollLine declarations;
legacy main-floor cases prohibit those new getters. The 37.6-wide platforms
intentionally veto both directions: safe inward drops are NOT modeled. The
f5302 fixture separates recorded binary32 fields from explicit unknown stubs.
This proves bounded policy/output
immutability under those inputs, NOT native physics, actual VM execution, hook
placement, a universal animation proof or live prevention. Main's ready singles,
team/custom/spawn gates and telemetry are tested by its independently owned suite.
"""
from pathlib import Path
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
FIX = Path(__file__).resolve().parent / "fixtures/showboat_safety"
MODULE = ROOT / "src/melee/mod/showboat_safety.c"
HEADER = MODULE.with_suffix(".h")
HARNESS = FIX / "harness.c"


def run(command, **kwargs):
    result = subprocess.run(command, capture_output=True, text=True, timeout=60, **kwargs)
    if result.returncode:
        raise AssertionError(f"{command}\n{result.stdout}{result.stderr}")
    return result


class SafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cc = shutil.which(os.environ.get("SHOWBOAT_TEST_CC", "clang"))
        if not cls.cc:
            raise RuntimeError("clang required (or set SHOWBOAT_TEST_CC)")
        cls.temp = tempfile.TemporaryDirectory(prefix="showboat-safety-")
        cls.addClassCleanup(cls.temp.cleanup)
        work = Path(cls.temp.name)
        native = []
        for path, name in (
            ("src/melee/ft/ftcoll.c", "ftColl_8007B868"),
            ("src/melee/ft/kinds/ftCommon/ftCo_0A01.c", "ftCo_800A2040"),
            ("src/melee/mp/mplib.c", "mpLineGetPrev"),
            ("src/melee/mp/mplib.c", "mpLineGetNext"),
            ("src/melee/mp/mplib.c", "mpLib_8004ED5C"),
            ("src/melee/mp/mplib.c", "mpLineIntersectionH"),
        ):
            match = re.search(rf"^(?:bool|s32|int|void) {name}\([^;]*?\)\n\{{.*?^\}}",
                              (ROOT / path).read_text(), re.S | re.M)
            if not match:
                raise AssertionError(f"Native helper missing: {name}")
            native.append(match.group())
        (work / "native_functions.h").write_text("\n\n".join(native))
        cls.includes = ["-I", str(ROOT / "src")]
        for directory in ("src/MSL", "extern/dolphin/include", "extern/dolphin/src"):
            cls.includes += ["-isystem", str(ROOT / directory)]
        cls.base = [cls.cc, "-std=c99", "-O1", "-g", "-fno-builtin",
                    "-Wall", "-Wextra", "-Werror", "-Wno-typedef-redefinition",
                    "-fno-short-enums"] + cls.includes + [
                    "-I", str(work), "-I", str(MODULE.parent)]
        cls.env = dict(os.environ, ASAN_OPTIONS="detect_leaks=0:halt_on_error=1",
                       UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1")
        cls.binaries, cls.symbols = [], []
        cls.guard_counts = {}
        cls.legacy_guard_counts = {}
        cls.footprints = {}
        protected = {p: p.read_bytes() for p in (MODULE, HEADER)}
        for debug in (0, 1):
            binary = work / f"safety-debug-{debug}"
            flags = [f"-DSHOWBOAT_AI_DEBUG={debug}"]
            run(cls.base + flags + ["-fsanitize=address,undefined",
                "-fno-omit-frame-pointer", str(MODULE), str(HARNESS), "-lm", "-o", str(binary)])
            cls.binaries.append(binary)
            footprint = run([str(binary), "footprint"], env=cls.env).stdout.strip()
            if not re.fullmatch(r"Fighter=[1-9][0-9]* CpuFighter=[1-9][0-9]* "
                                r"guarded_bytes=[1-9][0-9]* cases=[1-9][0-9]*", footprint):
                raise AssertionError(f"Invalid footprint: {footprint}")
            cls.footprints[binary.name] = footprint
            obj = work / f"safety-debug-{debug}.o"
            run(cls.base + flags + ["-c", str(MODULE), "-o", str(obj)])
            cls.symbols.append(run(["nm", str(obj)]).stdout)
        if any(p.read_bytes() != b for p, b in protected.items()):
            raise AssertionError("Safety source changed during compile; rerun")

    def run_case(self, name):
        for binary in self.binaries:
            with self.subTest(debug=binary.name):
                output = run([str(binary), name], env=self.env).stdout.strip()
                self.assertRegex(output, rf"^PASS {name} [1-9][0-9]*$")
                count = int(output.rsplit(" ", 1)[1])
                self.guard_counts[binary.name] = self.guard_counts.get(binary.name, 0) + count
                if not name.startswith("platform_") and name != "observed_platform_f5302":
                    self.legacy_guard_counts[binary.name] = (
                        self.legacy_guard_counts.get(binary.name, 0) + count)

    @classmethod
    def tearDownClass(cls):
        counts = ", ".join(f"{name}={count}" for name, count in sorted(cls.guard_counts.items()))
        print(f"Full-Fighter guards: {counts}; total={sum(cls.guard_counts.values())}; "
              f"legacy={sum(cls.legacy_guard_counts.values())}")
        for name, footprint in sorted(cls.footprints.items()):
            print(f"Host diagnostic footprint ({name}): {footprint}")

    def test_native_ppc_header_syntax(self):
        # All REAL headers, native LINT layout assertions, no host fixture shim.
        for debug in (0, 1):
            run([self.cc, "-fsyntax-only", "-xc", "-std=c99", "-nostdinc",
                 "-fno-builtin", "--target=ppc32-none-eabi", "-DLINT",
                 "-fno-short-enums", "-Werror", "-Wno-typedef-redefinition",
                 f"-DSHOWBOAT_AI_DEBUG={debug}"] + self.includes + [str(MODULE)])

    def test_dependencies_and_no_static_state(self):
        expected = {"Player_GetPlayerState", "Player_GetEntity", "ftCo_800A2040",
                    "ftColl_8007B868", "HSD_GObj_Entities", "Stage_80225194",
                    "mpCheckFloor", "mpFloorGetLeft", "mpFloorGetRight",
                    "mpLineGetV0Pos", "mpLineGetV1Pos", "mpLib_8004ED5C",
                    "mpLib_8004D164", "mpGetGroundCollJoint", "mpGetGroundCollLine"}
        for symbols in self.symbols:
            undefined = {line.split()[-1].removeprefix("_")
                         for line in symbols.splitlines()
                         if re.search(r"\bU\s", line)}
            self.assertEqual(undefined, expected)
            # No writable globals, static sidecar/state, restore or RNG source.
            # Mach-O labels debug sections with local `s ltmpN` markers.
            data = "\n".join(line for line in symbols.splitlines()
                             if not re.search(r"\bltmp\d+$", line))
            self.assertFalse(re.search(r"^\S+\s+[bBdDgGsScC]\s+", data, re.M), symbols)

    def test_general_write_guards(self):
        # AST over ALL own functions, not a search for a few named forbidden
        # fields. Every indirect/arrow store is rejected except the two exact
        # output assignments, in the public function only. Direct local stores
        # (line/flags/runway calculations) are allowed. Dependency allowlist
        # independently forbids mutating native helper calls, memcpy, RNG, etc.
        source = MODULE.read_text()
        # Discover definitions regardless of return type/name, so a new
        # differently named helper cannot silently evade the write guard.
        names = re.findall(r"^[\w* ]+\s+(\w+)\([^;]*?\)\s*\{", source, re.M)
        self.assertIn("ShowboatSafety_PostInput", names)
        self.assertEqual(len(names), len(set(names)))
        writes = []
        for name in names:
            raw = run(self.base + ["-fsyntax-only", "-Xclang", "-ast-dump=json",
                      "-Xclang", f"-ast-dump-filter={name}", str(MODULE)]).stdout
            # The public function has a real-header prototype AND definition;
            # clang emits separate JSON objects for a filtered dump.
            trees = []
            decoder = json.JSONDecoder()
            while raw.strip():
                tree, end = decoder.raw_decode(raw.lstrip())
                trees.append(tree)
                raw = raw.lstrip()[end:]
            definitions = [tree for tree in trees if any(
                n.get("kind") == "CompoundStmt" for n in tree.get("inner", []))]
            self.assertEqual(len(definitions), 1)
            tree = definitions[0]

            def walk(node):
                if isinstance(node, dict):
                    yield node
                    for child in node.get("inner", []):
                        yield from walk(child)

            def label(node):
                kind = node.get("kind")
                if kind in ("ImplicitCastExpr", "ParenExpr"):
                    return label(node["inner"][0])
                if kind == "DeclRefExpr":
                    return node["referencedDecl"]["name"]
                if kind == "MemberExpr":
                    return label(node["inner"][0]) + "." + node["name"]
                return "?"

            for node in walk(tree):
                op = node.get("opcode", "")
                if ((node.get("kind") in ("BinaryOperator", "CompoundAssignOperator")
                     and op in {"=", "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=", "<<=", ">>="})
                    or (node.get("kind") == "UnaryOperator" and op in {"++", "--"})):
                    lhs = node["inner"][0]
                    indirect = any(n.get("isArrow") or
                        (n.get("kind") == "UnaryOperator" and n.get("opcode") == "*")
                        or n.get("kind") == "ArraySubscriptExpr" for n in walk(lhs))
                    if indirect:
                        writes.append((name, label(lhs), op))
        self.assertEqual(writes, [
            ("ShowboatSafety_PostInput", "fp.cpu.buttons", "&="),
            ("ShowboatSafety_PostInput", "fp.cpu.lstick.x", "="),
        ])


def load_tests(loader, tests, pattern):
    names = re.findall(r"^\s*CASE\((\w+)\),?$", HARNESS.read_text(), re.M)
    if not names or len(names) != len(set(names)):
        raise AssertionError("C registry must be nonempty and unique")
    for name in names:
        def test(self, case=name):
            self.run_case(case)
        test.__name__ = f"test_{name}"
        setattr(SafetyTests, test.__name__, test)
    return loader.loadTestsFromTestCase(SafetyTests)


if __name__ == "__main__":
    unittest.main()
