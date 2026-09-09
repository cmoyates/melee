#!/usr/bin/env python3
"""Actual recorder C + typed native stubs, debug 0/1 under ASan/UBSan.

No assets, DOL build, emulator, subprocess game, or third-party packages.
Native enums, complete CpuFighter definition and read-only helper bodies come
from this checkout. Fighter is a host stub: byte-for-byte checks cover its ENTIRE
storage and the ENTIRE extracted CPU, not retail PPC execution or hook placement.
A separate PPC clang syntax-only check uses real headers; it does not build/link
any object or DOL, execute native physics, or touch the running playtest.
"""
from collections import Counter, defaultdict
from copy import deepcopy
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import struct
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
FIX = Path(__file__).resolve().parent / "fixtures/showboat_recorder"
MODULE = ROOT / "src/melee/mod/showboat_recorder.c"
HEADER = MODULE.with_suffix(".h")
ENUMS = (
    ("src/melee/ft/forward.h", "FighterKind"),
    ("src/melee/ft/forward.h", "GroundOrAir"),
    ("src/melee/ft/kinds/ftCommon/forward.h", "ftCommon_MotionState"),
    ("src/melee/gr/forward.h", "StKind"),
    ("src/melee/gm/forward.h", "MatchKind"),
    ("src/melee/gm/forward.h", "GameModeKind"),
    ("src/melee/pl/forward.h", "Gm_PKind"),
)
HEADERS = (
    "melee/ft/forward.h", "melee/ft/fighter.h", "melee/ft/ftcoll.h",
    "melee/ft/kinds/ftCommon/ftCo_0A01.h",
    "melee/ft/kinds/ftCommon/forward.h", "melee/ft/types.h",
    "melee/gm/gm_16AE.h", "melee/gm/gm_1A3F.h", "melee/mn/types.h",
    "melee/pl/player.h", "sysdolphin/baselib/gobj.h", "dolphin/os.h",
)
FLOAT_INDICES = (3, 4, 5, 6, 7, 8, 9, 11)


INVALID = ("level mode kind human owner_secondary target_secondary owner_subflag "
           "target_subflag ally third owner_slot target_slot owner_gobj target_gobj "
           "missing inactive_slot null self bad_target bad_owner no_rules bad_rules").split()


def run(cmd, **kwargs):
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, **kwargs)
    if result.returncode:
        raise AssertionError(f"{cmd}\n{result.stdout}\n{result.stderr}")
    return result


def rows_of(rows, kind):
    return [r for r in rows if r["type"] == kind]


class RecorderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc = shutil.which(os.environ.get("SHOWBOAT_TEST_CC", "clang"))
        if not cc:
            raise RuntimeError("clang required (or set SHOWBOAT_TEST_CC)")
        cls.cc = cc
        cls.temp = tempfile.TemporaryDirectory(prefix="showboat-recorder-")
        cls.addClassCleanup(cls.temp.cleanup)
        work = Path(cls.temp.name)
        inc = work / "include"
        inc.mkdir()
        shutil.copyfile(FIX / "game.h", inc / "game.h")
        protected = {p: p.read_bytes() for p in (MODULE, HEADER)}
        enums = []
        for path, name in ENUMS:
            match = re.search(rf"typedef enum(?: {name})?\s*\{{[^{{}}]*\}}\s*{name};",
                              (ROOT / path).read_text(), re.S)
            if not match:
                raise AssertionError(f"Native enum missing: {name}")
            enums.append(match.group())
        pads = (ROOT / "src/sysdolphin/baselib/controller.h").read_text()
        enums += [line.replace("(1 <<", "(1U <<") for line in pads.splitlines()
                  if re.match(r"#define HSD_PAD_\w+ \(1 << \d+\)", line)]
        (inc / "native_enums.h").write_text("\n".join(enums))
        cpu = []
        types = (ROOT / "src/melee/ft/types.h").read_text()
        for name in ("Fighter_x1A88_xFC_t", "CpuFighter"):
            match = re.search(rf"^struct {name} \{{.*?^\}};", types, re.S | re.M)
            if not match:
                raise AssertionError(f"Native struct missing: {name}")
            cpu.append(match.group())
        (inc / "native_cpu.h").write_text("\n".join(cpu))
        groups = {
            "src/melee/ft/ftcoll.c": ("ftColl_8007B868",),
            "src/melee/ft/kinds/ftCommon/ftCo_0A01.c": (
                "ftCo_800A2040", "ftCo_IsAlly"),
            "src/melee/gm/gm_16AE.c": ("gm_GetStKind", "gm_8016B14C", "gm_8016B168"),
        }
        native = []
        for path, names in groups.items():
            source = (ROOT / path).read_text()
            for name in names:
                match = re.search(rf"^(?:bool|s32|u16) {name}\([^;]*?\)\n\{{.*?^\}}",
                                  source, re.S | re.M)
                if not match:
                    raise AssertionError(f"Native function missing: {name}")
                native.append(match.group())
        (inc / "native_functions.h").write_text("\n\n".join(native))
        for header in HEADERS:
            dest = inc / header
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text('#include "game.h"\n')
        base = [cc, "-std=c99", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
                "-I", str(inc), "-I", str(MODULE.parent)]
        sanitize = ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
        cls.env = dict(os.environ, ASAN_OPTIONS="detect_leaks=0:halt_on_error=1",
                       UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1")
        cls.binaries, cls.disabled = [], []
        for debug in (0, 1):
            binary = work / f"recorder-debug-{debug}"
            flags = [f"-DSHOWBOAT_AI_DEBUG={debug}"]
            run(base + sanitize + flags + ["-DSHOWBOAT_RECORDER=1", str(MODULE),
                str(FIX / "harness.c"), "-lm", "-o", str(binary)])
            cls.binaries.append(binary)
            disabled = work / f"disabled-debug-{debug}"
            run(base + sanitize + flags + ["-DSHOWBOAT_RECORDER=0", str(MODULE),
                str(FIX / "disabled.c"), "-o", str(disabled)])
            cls.disabled.append(disabled)
        # Independent non-sanitized TU dependency check. No accidental RNG,
        # allocation, network, planners, CheckInput or controller writers.
        cls.symbols = {}
        for enabled in (0, 1):
            obj = work / f"recorder-{enabled}.o"
            run(base + [f"-DSHOWBOAT_RECORDER={enabled}", "-c", str(MODULE), "-o", str(obj)])
            output = run(["nm", "-u", str(obj)]).stdout
            cls.symbols[enabled] = {line.split()[-1].removeprefix("_")
                                    for line in output.splitlines() if line.strip()}
        # Obtain numeric expectations from the checkout, not duplicate enum IDs.
        names = ["FTKIND_CAPTAIN", "FTKIND_FOX", "ftCo_MS_Wait", "ftCo_MS_CaptureWaitHi",
                 "HSD_PAD_R", "HSD_PAD_A", "MatchKind_Stock", "MatchKind_Time", "GM_VS",
                 "ftCo_MS_Dash", "ftCo_MS_Fall"]
        probe = work / "enums.c"
        probe.write_text('#include "game.h"\n#include <stdio.h>\nint main(void) {\n' +
                         "\n".join(f'printf("{n} %d\\n", (int){n});' for n in names) + "\n}\n")
        run(base + [str(probe), "-o", str(work / "enums")])
        cls.native = {k: int(v) for k, v in (line.split() for line in
                      run([str(work / "enums")]).stdout.splitlines())}
        # Fault injection only in temporary copies: the production buffer and
        # control flow stay untouched. Exact-fit/one-byte-short also exercise
        # the trailing newline and NUL reservation, not just gross overflow.
        baseline = run([str(cls.binaries[0]), "capacity_baseline"], env=cls.env).stdout
        sample = next(line for line in baseline.splitlines(keepends=True)
                      if '"type":"sample"' in line)
        cls.sample_bytes = len(sample.encode())
        cls.capacity_binaries = {}
        source = MODULE.read_text()
        assert source.count("#define SR_LINE_CAP 1024") == 1
        for cap in (64, cls.sample_bytes, cls.sample_bytes + 1):
            copy = work / f"recorder-cap-{cap}.c"
            copy.write_text(source.replace("#define SR_LINE_CAP 1024",
                                           f"#define SR_LINE_CAP {cap}"))
            binaries = []
            for debug in (0, 1):
                binary = work / f"recorder-cap-{cap}-debug-{debug}"
                run(base + sanitize + [f"-DSHOWBOAT_AI_DEBUG={debug}",
                    "-DSHOWBOAT_RECORDER=1", str(copy), str(FIX / "harness.c"),
                    "-lm", "-o", str(binary)])
                binaries.append(binary)
            cls.capacity_binaries[cap] = binaries
        if any(p.read_bytes() != content for p, content in protected.items()):
            raise AssertionError("Recorder/header changed during build; rerun")

    def records(self, case, *, raw=False, binaries=None):
        outputs, wires = [], []
        for binary in self.binaries if binaries is None else binaries:
            with self.subTest(debug=binary.name):
                result = run([str(binary), case], env=self.env)
                self.assertEqual(result.stderr, "")
                self.assertTrue(not result.stdout or result.stdout.endswith("\n"))
                wires.append(result.stdout)
                rows = []
                for line in result.stdout.splitlines():
                    self.assertLessEqual(len(line.encode()) + 2, 1024)
                    self.assertTrue(line.startswith("SBREC "))
                    def reject_constant(value):
                        raise AssertionError(f"Non-JSON constant: {value}")
                    def unique(pairs):
                        keys = [k for k, _ in pairs]
                        self.assertEqual(len(keys), len(set(keys)))
                        return dict(pairs)
                    rows.append(json.loads(line[6:], parse_constant=reject_constant,
                                           object_pairs_hook=unique))
                self.validate(rows)
                outputs.append(rows)
        self.assertEqual(wires[0], wires[1], "Debug must not alter wire bytes")
        self.assertEqual(outputs[0], outputs[1], "Debug must not alter telemetry")
        self.last_wire = wires[0]
        if raw:
            return outputs[0]
        # Legacy numeric assertions operate on copies only. Strict validation
        # above and the CLI seam below always see the original wire strings.
        decoded = deepcopy(outputs[0])
        for row in rows_of(decoded, "sample"):
            for side in ("self", "rival"):
                for index in FLOAT_INDICES:
                    row[side][index] = struct.unpack(">f", bytes.fromhex(row[side][index]))[0]
        return decoded

    def validate(self, rows):
        fields = {
            "begin": "stage mode match_kind target interval",
            "sample": "ego action owns events gap float_encoding self rival native input reasons",
            "gate": "from tactic reason count batch",
            "end": "reason observations",
        }
        base = set("v type segment slot frame".split())
        segments, active = {}, {}
        last_id = 0
        for row in rows:
            kind = row["type"]
            self.assertIn(kind, fields)
            self.assertEqual(set(row), base | set(fields[kind].split()))
            self.assertEqual(row["v"], 2)
            for key in ("v", "segment", "slot", "frame"):
                self.assertIs(type(row[key]), int)
            self.assertIn(row["slot"], range(6))
            self.assertTrue(0 <= row["frame"] <= 0xFFFFFFFF)
            ident, slot = row["segment"], row["slot"]
            if kind == "begin":
                self.assertGreater(ident, last_id)
                last_id = ident
                self.assertNotIn(slot, active)
                active[slot] = ident
                segments[ident] = {"last": row["frame"], "samples": set(), "gates": Counter(),
                                   "batch": 0, "window": None}
                self.assertEqual(row["interval"], 12)
                self.assertIn(row["target"], range(6))
                self.assertNotEqual(slot, row["target"])
                for key in fields[kind].split():
                    self.assertIs(type(row[key]), int)
                continue
            self.assertEqual(active[slot], ident)
            s = segments[ident]
            self.assertGreaterEqual(row["frame"], s["last"])
            s["last"] = row["frame"]
            if kind == "sample":
                self.assertNotIn(row["frame"], s["samples"])
                s["samples"].add(row["frame"])
                self.assertEqual(row["float_encoding"], "ieee754-binary32-hex")
                for key, size in (("self", 13), ("rival", 13), ("native", 3), ("input", 7)):
                    self.assertIs(type(row[key]), list)
                    self.assertEqual(len(row[key]), size)
                for key in ("self", "rival"):
                    for index in FLOAT_INDICES:
                        value = row[key][index]
                        self.assertIs(type(value), str)
                        self.assertIsNotNone(re.fullmatch(r"[0-9a-f]{8}", value))
                        self.assertNotEqual(int(value, 16) & 0x7F800000, 0x7F800000)
                        self.assertTrue(math.isfinite(struct.unpack(">f", bytes.fromhex(value))[0]))
                    for index in (0, 1, 2, 10, 12):
                        self.assertIs(type(row[key][index]), int)
                        if index != 12:
                            self.assertTrue(-0x80000000 <= row[key][index] <= 0x7FFFFFFF)
                    self.assertIn(row[key][12], range(256))
                for key in ("native", "input"):
                    self.assertTrue(all(type(v) is int for v in row[key]))
                for key in ("ego", "action", "owns", "events", "gap"):
                    self.assertIs(type(row[key]), int)
                self.assertIn(row["ego"], range(101))
                self.assertIn(row["action"], range(12))
                self.assertIn(row["owns"], (0, 1))
                self.assertIn(row["gap"], (0, 1))
                self.assertIn(row["events"], range(128))
                self.assertEqual(len(row["reasons"]), 5)
                self.assertTrue(all(type(v) is int and 0 <= v < 16 for v in row["reasons"]))
                self.assertTrue(0 <= row["input"][0] <= 0xFFFFFFFF)
                self.assertTrue(all(-128 <= v <= 127 for v in row["input"][1:5]))
                self.assertTrue(all(0 <= v <= 255 for v in row["input"][5:]))
            elif kind == "gate":
                for key in fields[kind].split():
                    self.assertIs(type(row[key]), int)
                self.assertLessEqual(row["from"], row["frame"])
                self.assertIn(row["tactic"], range(5))
                self.assertIn(row["reason"], range(16))
                self.assertIn(row["count"], range(1, 61))
                if row["batch"] != s["batch"]:
                    self.assertEqual(row["batch"], s["batch"] + 1)
                    s["batch"] = row["batch"]
                    s["window"] = (row["from"], row["frame"])
                self.assertEqual(s["window"], (row["from"], row["frame"]))
                s["gates"][row["tactic"]] += row["count"]
            else:
                self.assertIn(row["reason"], {"reset", "suspend", "identity", "spawn",
                    "frame_rollback", "context", "target", "ineligible", "limit"})
                self.assertIs(type(row["observations"]), int)
                self.assertGreater(row["observations"], 0)
                self.assertEqual(s["gates"], Counter({t: row["observations"] for t in range(5)}))
                del active[slot]
        self.assertFalse(active, "These fixtures explicitly close every segment")

    def ppc_syntax_command(self):
        # Real headers only, never the host include stubs.
        base = [self.cc, "-fsyntax-only", "-xc", "-std=c99", "-nostdinc",
                "-fno-builtin", "--target=ppc32-none-eabi", "-DLINT",
                "-fno-short-enums", "-Werror", "-Wno-typedef-redefinition",
                "-I", str(ROOT / "src")]
        for path in ("src/MSL", "extern/dolphin/include", "extern/dolphin/src"):
            base += ["-isystem", str(ROOT / path)]
        return base

    def test_native_header_syntax(self):
        # Catch dependencies/types hidden by the host stubs (the freestanding
        # MSL, for example, does not provide the host's <float.h>).
        for enabled in (0, 1):
            for debug in (0, 1):
                run(self.ppc_syntax_command() + [f"-DSHOWBOAT_RECORDER={enabled}",
                            f"-DSHOWBOAT_AI_DEBUG={debug}", str(MODULE)])

    def test_actual_codec_ppc_syntax(self):
        # Compile the actual internal codec with real PPC types and sentinel
        # call sites. Syntax ONLY: no target object, linking or runtime proof.
        for debug in (0, 1):
            run(self.ppc_syntax_command() + ["-DSHOWBOAT_RECORDER=1",
                f"-DSHOWBOAT_AI_DEBUG={debug}", str(FIX / "ppc_codec.c")])

    def test_disabled_header_and_dependencies(self):
        for binary in self.disabled:
            self.assertEqual(run([str(binary)], env=self.env).stdout, "")
        self.assertEqual(self.symbols[0], set())
        # Darwin clang lowers zeroing memset to bzero and adds stack canaries
        # for the bounded local line. These are compiler runtime dependencies,
        # not new gameplay queries or allocation/formatting services.
        allowed = {"OSReport", "memset", "memcpy", "bzero", "__stack_chk_fail",
                   "__stack_chk_guard", "Player_GetEntity", "Player_GetEntityAtIndex",
                   "Player_GetPlayerState", "Player_GetStocks", "ftCo_800A2040", "ftCo_IsAlly",
                   "ftColl_8007B868", "gm_GetFrameCount", "gm_GetCurrentGameMode",
                   "gm_GetRules", "gm_GetStKind", "HSD_GObj_Entities"}
        self.assertLessEqual(self.symbols[1], allowed)
        self.assertIn("ftColl_8007B868", self.symbols[1])

    def test_schema(self):
        rows = self.records("schema")
        self.assertEqual(Counter(r["type"] for r in rows), {"begin": 1, "sample": 1, "gate": 5, "end": 1})
        n = self.native
        b, s = rows[0:2]
        self.assertEqual((b["stage"], b["mode"], b["match_kind"], b["frame"]),
                         (31, n["GM_VS"], n["MatchKind_Stock"], 1000))
        self.assertEqual(s["self"], [100, n["FTKIND_CAPTAIN"], n["ftCo_MS_CaptureWaitHi"],
            2.5, -25.25, 13.5, -1.25, 2.75, 0.125, 23.5, 3, 51.25, 255])
        self.assertEqual(s["rival"], [101, n["FTKIND_FOX"], n["ftCo_MS_Wait"],
            0, 45, 0, 0, 0, 0, 0, 4, 60, 128])
        self.assertEqual(s["native"], [2, 42, 2])
        self.assertEqual(s["input"], [n["HSD_PAD_R"] | n["HSD_PAD_A"], -80, 79, 5, -6, 11, 255])
        self.assertEqual([s[k] for k in ("ego", "action", "owns", "events", "gap")], [73, 11, 1, 127, 0])
        self.assertEqual({r["tactic"]: r["reason"] for r in rows_of(rows, "gate")},
                         {0: 2, 1: 0, 2: 0, 3: 0, 4: 15})

    def test_sample_transport_single_pointer(self):
        source = MODULE.read_text()
        emit = re.search(r"^static bool SR_Emit\([^;]*?\n\{.*?^\}",
                         source, re.S | re.M)
        self.assertIsNotNone(emit)
        # Runtime va_arg checks cannot detect unused trailing arguments. Pin
        # the complete call expression too: literal %s and exactly b.text.
        self.assertEqual(re.findall(r"\bOSReport\s*\([^;]*;", emit.group()),
                         ['OSReport("%s", b.text);'])
        self.assertRegex(emit.group(), r"\bSR_Line b;")
        self.assertIn("#define SR_LINE_CAP 1024", source)

    def test_exact_sentinel_mapping(self):
        rows = self.records("sentinels", raw=True)
        n = self.native
        s = rows_of(rows, "sample")[0]
        self.assertEqual(s, {
            "v": 2, "type": "sample", "segment": 1, "slot": 0, "frame": 0xFFFFFFFD,
            "float_encoding": "ieee754-binary32-hex",
            "ego": 97, "action": 9, "owns": 1, "events": 85, "gap": 0,
            "self": [-0x80000000, n["FTKIND_CAPTAIN"], n["ftCo_MS_Dash"],
                     "80000000", "00000001", "7f7fffff", "80800000",
                     "3f123456", "bf654321", "412abcde", 7, "c2480001", 21],
            "rival": [0x7FFFFFFF, n["FTKIND_FOX"], n["ftCo_MS_Fall"],
                      "00000000", "80000001", "ff7fffff", "00800000",
                      "3eaaaaab", "c1234567", "42f6e979", 13, "3f800001", 74],
            "native": [-0x80000000, 0x7FFFFFFF, 3],
            "input": [0xFFFFFFFF, -128, 127, -73, 0, 17, 254],
            "reasons": [1, 4, 7, 10, 13],
        })
        self.assertEqual(len({s[side][i] for side in ("self", "rival")
                              for i in FLOAT_INDICES}), 16)
        self.assertEqual(rows[0], {
            "v": 2, "type": "begin", "segment": 1, "slot": 0, "frame": 0xFFFFFFFD,
            "stage": 31, "mode": n["GM_VS"], "match_kind": n["MatchKind_Stock"],
            "target": 1, "interval": 12,
        })
        self.assertEqual(rows[2:-1], [
            {"v": 2, "type": "gate", "segment": 1, "slot": 0, "frame": 0xFFFFFFFD,
             "from": 0xFFFFFFFD, "tactic": t, "reason": 1 + t * 3, "count": 1,
             "batch": 1} for t in range(5)])
        self.assertEqual(rows[-1], {
            "v": 2, "type": "end", "segment": 1, "slot": 0, "frame": 0xFFFFFFFD,
            "reason": "reset", "observations": 1,
        })

    def test_raw_wire_validator_rejects_noncanonical_floats(self):
        rows = self.records("sentinels", raw=True)
        for side in ("self", "rival"):
            for index in FLOAT_INDICES:
                for bad in (0, 1.0, True, None, "0x3f800000", "3F800000", "0000000",
                            "000000000", " 00000000", "00000000\n", "gggggggg",
                            "7f800000", "ff800000", "7fc00000", "7f800001"):
                    with self.subTest(side=side, index=index, bad=bad):
                        altered = deepcopy(rows)
                        altered[1][side][index] = bad
                        with self.assertRaises(AssertionError):
                            self.validate(altered)
        for encoding in (None, "ieee754-binary32", 2):
            altered = deepcopy(rows)
            altered[1]["float_encoding"] = encoding
            with self.assertRaises(AssertionError):
                self.validate(altered)
        altered = deepcopy(rows)
        del altered[1]["float_encoding"]
        with self.assertRaises(AssertionError):
            self.validate(altered)
        for index in range(len(rows)):
            altered = deepcopy(rows)
            altered[index]["v"] = 1
            with self.assertRaises(AssertionError):
                self.validate(altered)

    def test_overflow_publishes_no_partial_samples(self):
        rows = self.records("overflow", raw=True, binaries=self.capacity_binaries[64])
        self.assertEqual(Counter(r["type"] for r in rows), {"begin": 1, "gate": 10, "end": 1})
        self.assertEqual([(r["batch"], r["from"], r["frame"], r["count"])
                          for r in rows_of(rows, "gate")],
                         [(1, 1, 60, 60)] * 5 + [(2, 61, 61, 1)] * 5)
        self.assertEqual(rows[-1]["observations"], 61)

    def test_line_capacity_exact_boundary(self):
        for extra, count in ((0, 0), (1, 1)):
            with self.subTest(nul_capacity=extra):
                rows = self.records("capacity_baseline", raw=True,
                                    binaries=self.capacity_binaries[self.sample_bytes + extra])
                self.assertEqual(Counter(r["type"] for r in rows),
                                 Counter({"begin": 1, "gate": 5, "end": 1, "sample": count}))
                self.assertEqual(rows[-1]["observations"], 1)

    def test_overflow_recovers_with_gap(self):
        rows = self.records("overflow_recovery", raw=True,
                            binaries=self.capacity_binaries[self.sample_bytes + 1])
        samples = rows_of(rows, "sample")
        self.assertEqual([(s["frame"], s["gap"]) for s in samples], [(1, 0), (3, 1)])
        for key in ("self", "rival", "native", "input", "reasons"):
            self.assertEqual(samples[0][key], samples[1][key])
        self.assertEqual(Counter(r["type"] for r in rows),
                         {"begin": 1, "sample": 2, "gate": 5, "end": 1})
        self.assertEqual(rows[-1]["observations"], 4)
        self.assertEqual([g["count"] for g in rows_of(rows, "gate")], [4] * 5)

    def test_frame_phase(self):
        rows = self.records("phase")
        s = rows_of(rows, "sample")[0]
        self.assertEqual(s["input"], [self.native["HSD_PAD_A"] | self.native["HSD_PAD_R"],
                                      -40, 0, 0, 0, 0, 255])
        self.assertEqual(s["native"][0], 7)
        self.assertEqual(s["self"][3], 6)
        self.assertEqual(s["rival"][9], 7)
        self.assertEqual(s["action"], 7)

    def test_periodic(self):
        rows = self.records("periodic")
        samples = rows_of(rows, "sample")
        self.assertEqual([s["frame"] for s in samples], [1, 13, 25, 37])
        self.assertEqual([s["input"][1] for s in samples], [1, 13, 25, 37])
        self.assertTrue(all(s["gap"] == 0 for s in samples))
        self.assertEqual(rows[-1]["observations"], 37)

    def test_changes(self):
        samples = rows_of(self.records("changes"), "sample")
        self.assertEqual([s["frame"] for s in samples], list(range(1, 17)))
        self.assertEqual(samples[-2]["events"], 2)
        self.assertEqual(samples[-1]["events"], 0)

    def test_gaps_and_one_per_frame(self):
        rows = self.records("gaps")
        samples = rows_of(rows, "sample")
        self.assertEqual([(s["frame"], s["gap"]) for s in samples], [(1, 0), (7, 1), (8, 1)])
        self.assertEqual(rows[-1]["observations"], 5)
        self.assertTrue(all(s["events"] == 0 for s in samples))

    def test_gates(self):
        rows = self.records("gates")
        actual = Counter()
        batches = defaultdict(list)
        for r in rows_of(rows, "gate"):
            actual[(r["from"], r["frame"], r["tactic"], r["reason"])] += r["count"]
            batches[(r["from"], r["frame"])].append(r)
        expected = Counter()
        for n in range(1, 126):
            start = (n - 1) // 60 * 60 + 1
            end = min(start + 59, 125)
            for t in range(5):
                reason = 0 if t == 4 or (t == 1 and n % 2 == 0) else (n + t) % 16
                expected[(start, end, t, reason)] += 1
        self.assertEqual(actual, expected)
        self.assertTrue(all(len(batch) <= 80 for batch in batches.values()))
        self.assertEqual(rows[-1]["observations"], 125)

    def test_exact_flush(self):
        rows = self.records("exact_flush")
        gates = rows_of(rows, "gate")
        self.assertEqual(len(gates), 10)
        self.assertEqual([(r["frame"], r["from"], r["count"]) for r in gates],
                         [(60, 1, 60)] * 5 + [(61, 61, 1)] * 5)
        self.assertEqual([r["observations"] for r in rows_of(rows, "end")], [60, 1])

    def test_nonfinite(self):
        rows = self.records("nonfinite")
        samples = rows_of(rows, "sample")
        self.assertEqual([s["frame"] for s in samples], [1] + list(range(3, 98, 2)))
        self.assertTrue(all(s["gap"] == 1 for s in samples[1:]))
        self.assertEqual(rows[-1]["observations"], 97)

    def test_extremes(self):
        rows = self.records("extremes")
        s = rows_of(rows, "sample")[0]
        self.assertEqual(s["frame"], 0xFFFFFFFF)
        self.assertEqual((s["ego"], s["action"]), (100, 0))
        self.assertGreater(s["self"][3], 3e38)
        self.assertEqual(s["input"][0], 0xFFFFFFFF)
        wire = next(json.loads(line[6:]) for line in self.last_wire.splitlines()
                    if '"type":"sample"' in line)
        # Full signed decimal boundaries as well as exact +/- max-finite bits;
        # these deliberately non-gameplay integers are not sent to the CLI's
        # stricter semantic plausibility checks (sentinels above are).
        for side in ("self", "rival"):
            self.assertEqual(wire[side], [-0x80000000, self.native["FTKIND_CAPTAIN"],
                0x7FFFFFFF, "7f7fffff", "7f7fffff", "ff7fffff", "7f7fffff",
                "ff7fffff", "7f7fffff", "ff7fffff", -0x80000000, "ff7fffff", 0])
        self.assertEqual(wire["native"], [-0x80000000, -0x80000000, 2])
        self.assertEqual(wire["input"], [0xFFFFFFFF, 0, 0, 0, 0, 0, 0])

    def test_lifecycle(self):
        rows = self.records("lifecycle")
        begins, ends = rows_of(rows, "begin"), rows_of(rows, "end")
        self.assertEqual([b["segment"] for b in begins], list(range(1, 13)))
        self.assertEqual([e["reason"] for e in ends], ["spawn", "spawn"] +
                         ["context"] * 6 + ["frame_rollback", "suspend", "reset", "reset"])
        self.assertTrue(all(e["observations"] == 1 for e in ends))
        self.assertEqual([b["stage"] for b in begins], [31] * 3 + [32] * 9)

    def test_pending(self):
        rows = self.records("pending")
        samples = rows_of(rows, "sample")
        self.assertEqual([(s["frame"], s["events"], s["action"]) for s in samples],
                         [(1, 8, 7), (2, 32, 10), (3, 0, 0), (5, 0, 0), (6, 0, 0)])
        counts = {(r["segment"], r["tactic"], r["reason"]): r["count"]
                  for r in rows_of(rows, "gate")}
        self.assertEqual(counts[(1, 2, 8)], 1)
        self.assertEqual(counts[(2, 3, 3)], 1)
        self.assertEqual(counts[(3, 0, 0)], 3)  # Reset may clear initial reason.
        self.assertEqual(counts[(3, 4, 15)], 1)
        self.assertEqual([s["gap"] for s in samples], [0, 0, 0, 1, 1])

    def test_same_frame_splits(self):
        rows = self.records("same_frame")
        self.assertEqual([r["frame"] for r in rows_of(rows, "sample")], [1, 2])
        self.assertEqual([r["observations"] for r in rows_of(rows, "end")], [1, 1, 2])
        self.assertEqual(rows_of(rows, "sample")[-1]["gap"], 1)

    def test_repeated_clock_flushes_have_distinct_batches(self):
        rows = self.records("repeated_clock")
        self.assertEqual(rows[-1]["observations"], 126)
        samples = rows_of(rows, "sample")
        self.assertEqual([r["frame"] for r in samples], [1, 2])
        self.assertEqual(samples[-1]["gap"], 1)
        gates = [r for r in rows_of(rows, "gate") if r["tactic"] == 0]
        self.assertEqual([(r["batch"], r["from"], r["frame"], r["count"]) for r in gates],
                         [(1, 1, 1, 60), (2, 1, 1, 60), (3, 1, 2, 6)])

    def test_sample_reasons_are_final_branch_values_not_extra_counts(self):
        rows = self.records("schema")
        self.assertEqual(rows_of(rows, "sample")[0]["reasons"], [2, 0, 0, 0, 15])
        self.assertEqual(sum(r["count"] for r in rows_of(rows, "gate")), 5)

    def test_actual_c_records_through_analyzer_cli(self):
        # Transport/schema seam: producer C output, not handcrafted sample data.
        # Coverage warnings remain legitimate; no match/result claims are tested.
        import sys
        with tempfile.TemporaryDirectory(prefix="showboat-recorder-analysis-") as work:
            log = Path(work) / "runtime.log"
            report = Path(work) / "report.json"
            cases = [(case, self.binaries) for case in (
                "schema", "periodic", "gaps", "gates", "pending", "same_frame",
                "repeated_clock", "stale", "slots", "sentinels", "nonfinite")]
            cases += [("overflow", self.capacity_binaries[64]),
                      ("overflow_recovery", self.capacity_binaries[self.sample_bytes + 1])]
            for case, binaries in cases:
                with self.subTest(case=case):
                    rows = self.records(case, raw=True, binaries=binaries)
                    log.write_text(self.last_wire)
                    run = subprocess.run([sys.executable, str(ROOT / "tools/analyze_showboat.py"),
                                          str(log), "--json", str(report)],
                                         capture_output=True, text=True, timeout=20)
                    self.assertEqual(run.returncode, 0, run.stderr)
                    scan = json.loads(report.read_text())["scan"]
                    self.assertEqual(scan["rejected_records"], 0)
                    self.assertEqual(scan["accepted_records"], len(rows))

    def test_stale_lifecycle(self):
        rows = self.records("stale")
        self.assertEqual([r["reason"] for r in rows_of(rows, "end")], ["target", "identity", "suspend"])
        self.assertEqual([r["observations"] for r in rows_of(rows, "end")], [1, 1, 2])

    def test_freed_token_teardown(self):
        rows = self.records("teardown")
        self.assertEqual([r["reason"] for r in rows_of(rows, "end")], ["reset", "suspend"])

    def test_invalidation(self):
        rows = self.records("invalidation")
        self.assertEqual([r["reason"] for r in rows_of(rows, "end")],
                         ["ineligible", "target", "suspend", "context", "identity", "context", "reset"])
        self.assertEqual([r["frame"] for r in rows_of(rows, "begin")], [1, 3, 5, 7, 9, 10, 11])
        self.assertEqual(rows_of(rows, "begin")[-1]["stage"], 1)

    def test_replacement(self):
        rows = self.records("replacement")
        self.assertEqual([r["reason"] for r in rows_of(rows, "end")], ["identity", "identity", "reset"])

    def test_flags(self):
        samples = rows_of(self.records("flags"), "sample")
        self.assertEqual([r["frame"] for r in samples], list(range(1, 10)) + [11, 12])
        self.assertEqual([r["self"][12] for r in samples], [0] + [32] * 6 + [0, 64, 0, 128])

    def test_slots(self):
        rows = self.records("slots")
        self.assertEqual([r["slot"] for r in rows_of(rows, "begin")], list(range(6)) + [0, 1])
        counts = {(r["segment"], r["tactic"], r["reason"]): r["count"]
                  for r in rows_of(rows, "gate")}
        self.assertEqual(counts[(7, 0, 3)], 1)
        self.assertEqual(counts[(8, 4, 15)], 1)


def load_tests(loader, tests, pattern):
    for name in INVALID:
        setattr(RecorderTests, f"test_invalid_{name}",
                lambda self, case=name: self.assertEqual(self.records("invalid_" + case), []))
    return loader.loadTestsFromTestCase(RecorderTests)


if __name__ == "__main__":
    unittest.main()
