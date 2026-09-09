#!/usr/bin/env python3
"""Sanitized host checks of native boot callbacks; no emulator or build outputs."""
import argparse
from contextlib import redirect_stderr
import io
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def extract(source, pattern):
    match = re.search(pattern, source, re.M | re.S)
    if not match:
        raise AssertionError(f"Cannot extract native declaration: {pattern}")
    return match.group() + "\n"


def function(source, name):
    # Same top-level closing-brace extraction as test_showboat_unlocks.py.
    return extract(source, rf"^void {name}\(GameModeState\*[^\n]*\n\{{.*?^\}}\n")


def native_declarations(boot):
    declarations = ""
    for path, name in (("ft/forward.h", "CharacterKind"),
                       ("gm/forward.h", "GameModeKind"),
                       ("pl/forward.h", "Gm_PKind"), ("mn/types.h", "CpuKind")):
        source = (ROOT / "src/melee" / path).read_text()
        declarations += extract(source, rf"typedef enum(?: {name})?\s*\{{[^{{}}]*\}}\s*{name};")
    gm = (ROOT / "src/melee/gm/forward.h").read_text()
    declarations += extract(gm, r"^#define GM_MAX_PLAYERS \d+$")
    language = (ROOT / "src/melee/lb/lblanguage.h").read_text()
    declarations += extract(language, r"enum \{[^{}]*LANG_JP[^{}]*\};")
    declarations += extract(boot, r"enum \{[^{}]*TROPHY_PIKMIN[^{}]*\};")
    menu = (ROOT / "src/melee/mn/types.h").read_text()
    for name in ("PlayerInitData", "StartMeleeRules", "StartMeleeData", "VsModeData"):
        declarations += f"typedef struct {name} {name};\n"
        declarations += extract(menu, rf"^struct {name} \{{.*?^\}};")
    for name in ("loadData", "leaveData"):
        declarations += extract(boot, rf"^struct {name} \{{.*?^\}};")
    return declarations


HARNESS = r'''
/* Actual native data declarations above, with host ABI (not a PPC layout test). */
typedef struct { struct loadData enter; struct leaveData exit; } GameModeState;
static GameModeState scene, scene_before;
static struct { bool skip_intro; } gmMainLib_8046B0F0;
static struct GuardedVs { u8 before[32]; VsModeData vs; u8 after[32]; } live, original, expected;
static int owned, card_result, language, next_mode;
static char events[32];
static size_t event_count;
static void event(char e) {
    assert(event_count + 1 < sizeof(events));
    events[event_count++] = e; events[event_count] = 0;
}
static void unchanged(void) { assert(memcmp(&live, &original, sizeof(live)) == 0); }
void* gm_GetGameModeStateEnterData(GameModeState* s) {
    assert(s == &scene); event('E'); unchanged(); return &s->enter;
}
void* gm_GetGameModeStateExitData(GameModeState* s) {
    assert(s == &scene); event('X'); unchanged(); return &s->exit;
}
void gm_801BF708(int arg) { assert(arg == 0); event('I'); unchanged(); }
s32 Toy_803048C0(int trophy) {
    assert(trophy == TROPHY_PIKMIN); event('T'); unchanged(); return owned;
}
int lbLang_GetLanguageSetting(void) { event('L'); unchanged(); return language; }
int lb_8001C2D8(int channel, const char* company, const char* game, const char* file) {
    assert(channel == 0 && strcmp(company, "01") == 0);
    assert(strcmp(game, language == LANG_JP ? "GPIJ" : "GPIE") == 0);
    assert(strcmp(file, "Pikmin dataFile") == 0);
    event('C'); unchanged(); return card_result;
}
void Toy_803124BC(void) { event('R'); unchanged(); }
void Toy_SetUnlockState(int trophy, bool unlock) {
    assert(trophy == TROPHY_PIKMIN && unlock); event('U'); unchanged();
}
u8 lbCardGame_DecideGameMode(void) {
    assert(!"override must be registered, not invoked"); return 0;
}
void gm_SetGameModeOverride(u8 (*callback)(void)) {
    assert(callback == lbCardGame_DecideGameMode); event('O'); unchanged();
}
VsModeData* gmVsMelee_GetVsData(void) {
    assert(EXPECT_QUICKSTART && event_count && events[event_count - 1] == 'O');
    event('V'); unchanged(); return &live.vs;
}
void OSReport(const char* format, ...) {
    char message[160];
    va_list args; va_start(args, format);
    vsnprintf(message, sizeof(message), format, args); va_end(args);
    assert(EXPECT_QUICKSTART && SHOWBOAT_AI_DEBUG);
    assert(strcmp(message, "SHOWBOAT QUICKSTART: VS CSS; P1 choose, P2 Captain CPU9 "
                           "(ckind=0 type=1 level=9)\n") == 0);
    assert(memcmp(&live, &expected, sizeof(live)) == 0); event('D');
}
void gm_ChangeGameModeAfterCurrentScene(int mode) {
    assert(mode == (EXPECT_QUICKSTART ? GM_VS : scene.exit.mode_id));
    assert(memcmp(&live, &expected, sizeof(live)) == 0);
    event('M'); next_mode = mode;
}
/* Deliberately no match-start/CSS-load stubs: unexpected calls fail compilation. */
'''

CHECKS = r'''
static void reset(int seed) {
    memset(&live, seed, sizeof(live));
    memcpy(&original, &live, sizeof(live));
    memcpy(&expected, &live, sizeof(live));
    memset(&scene, seed, sizeof(scene));
    event_count = 0; events[0] = 0; next_mode = -1;
}
int main(void) {
    /* Guard against confusing external Falcon 0 with internal FighterKind 2. */
    assert(CKIND_CAPTAIN == 0 && CHKIND_NONE == 33 && GM_VS == 2);
    assert(Gm_PKind_Human == 0 && Gm_PKind_Cpu == 1 && Gm_PKind_NA == 3);
    assert(CpuKind_4 == 4 && GM_MAX_PLAYERS == 6);
    int seeds[] = { 0, 0x5A, 0xA5, 0xFF };
    for (unsigned seed = 0; seed < sizeof(seeds) / sizeof(seeds[0]); ++seed) {
        for (int skip = 0; skip < 2; ++skip) {
            reset(seeds[seed]); gmMainLib_8046B0F0.skip_intro = skip;
            memcpy(&scene_before, &scene, sizeof(scene));
            scene_before.enter.x0 = 0; scene_before.enter.x4 = 0;
            scene_before.enter.mode_id = skip ? GM_TITLE : GM_OPENING_MV;
            bootOnLoad(&scene);
            assert(memcmp(&scene, &scene_before, sizeof(scene)) == 0);
            assert(strcmp(events, skip ? "E" : "EI") == 0);
            assert(next_mode == -1); unchanged();
            assert(gmMainLib_8046B0F0.skip_intro == skip);

            reset(seeds[seed]); memcpy(&scene_before, &scene, sizeof(scene));
            scene_before.enter.x0 = 1; scene_before.enter.x4 = 0;
            memcardOnLoad(&scene);
            assert(memcmp(&scene, &scene_before, sizeof(scene)) == 0);
            assert(strcmp(events, "E") == 0 && next_mode == -1); unchanged();
        }
        for (owned = 0; owned < 2; ++owned)
        for (card_result = -1; card_result <= 1; ++card_result)
        for (language = LANG_JP; language <= LANG_US; ++language)
        /* Every u8 exit mode, including opening/title and card-selected modes. */
        for (int mode = 0; mode <= 255; ++mode) {
            reset(seeds[seed]); scene.exit.mode_id = mode;
            memcpy(&scene_before, &scene, sizeof(scene));
            if (EXPECT_QUICKSTART) {
                expected.vs.start.rules.is_teams = false;
                expected.vs.start.players[0].slot_type = Gm_PKind_Human;
                expected.vs.start.players[0].ckind = CHKIND_NONE;
                expected.vs.start.players[1].slot_type = Gm_PKind_Cpu;
                expected.vs.start.players[1].ckind = CKIND_CAPTAIN;
                expected.vs.start.players[1].cpu_level = 9;
                expected.vs.start.players[1].cpu_kind = CpuKind_4;
                expected.vs.start.players[1].color = 0;
                for (int i = 2; i < GM_MAX_PLAYERS; ++i) {
                    expected.vs.start.players[i].slot_type = Gm_PKind_NA;
                    expected.vs.start.players[i].ckind = CHKIND_NONE;
                }
            }
            bootOnLeave(&scene);
            char want[32];
            snprintf(want, sizeof(want), "XT%sO%sM",
                     owned ? "" : card_result == 0 ? "LCRU" : "LC",
                     EXPECT_QUICKSTART ? (SHOWBOAT_AI_DEBUG ? "VD" : "V") : "");
            assert(strcmp(events, want) == 0);
            assert(next_mode == (EXPECT_QUICKSTART ? GM_VS : mode));
            assert(memcmp(&scene, &scene_before, sizeof(scene)) == 0);
            /* Includes all six players, rules, VS metadata, padding and guards. */
            assert(memcmp(&live, &expected, sizeof(live)) == 0);
        }
    }
    puts("PASS: native boot preset, intro/card paths, ordering, preservation, no auto-match");
}
'''


class ShowboatQuickstartTests(unittest.TestCase):
    def test_native_boot_callbacks_sanitized_matrix(self):
        compiler = shutil.which(os.environ.get("SHOWBOAT_TEST_CC", "clang"))
        self.assertIsNotNone(compiler, "clang required")
        boot = (ROOT / "src/melee/gm/gmboot.c").read_text()
        source = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
typedef int8_t s8;
typedef uint8_t u8;
typedef uint16_t u16;
typedef int32_t s32;
typedef uint32_t u32;
typedef uint64_t u64;
typedef void (*Event)(void);
'''
        source += native_declarations(boot) + HARNESS
        source += "\n".join(function(boot, name) for name in
                            ("bootOnLoad", "bootOnLeave", "memcardOnLoad"))
        source += CHECKS
        with tempfile.TemporaryDirectory(prefix="showboat-quickstart-") as work:
            path = Path(work) / "test.c"
            path.write_text(source)
            for debug in (0, 1):
                for flag in (None, 0, 1):
                    with self.subTest(debug=debug, flag=flag):
                        binary = Path(work) / f"boot-{debug}-{flag}"
                        cmd = [compiler, "-std=c99", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
                               "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
                               f"-DDEBUG={debug}", f"-DSHOWBOAT_AI_DEBUG={debug}",
                               f"-DEXPECT_QUICKSTART={int(flag == 1)}"]
                        if flag is not None:
                            cmd.append(f"-DSHOWBOAT_QUICKSTART={flag}")
                        result = subprocess.run(cmd + [str(path), "-o", str(binary)],
                                                capture_output=True, text=True, timeout=30)
                        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                        env = dict(os.environ, ASAN_OPTIONS="detect_leaks=0:halt_on_error=1",
                                   UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1")
                        result = subprocess.run([str(binary)], capture_output=True, text=True,
                                                env=env, timeout=15)
                        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                        self.assertTrue(result.stdout.startswith("PASS:"))

    def test_configure_parser_and_helper_defaults(self):
        # Execute the actual parser prefix, stopping before ProjectConfig/build generation.
        configure = (ROOT / "configure.py").read_text()
        start = configure.index("parser = argparse.ArgumentParser()")
        end = configure.index("config = ProjectConfig()", start)
        parser_code = compile(configure[start:end], "configure.py", "exec")
        cases = (([], False), (["--showboat-ai"], False),
                 (["--showboat-ai", "--showboat-quickstart"], True),
                 (["--showboat-ai", "--showboat-quickstart", "--no-showboat-quickstart"], False),
                 (["--showboat-ai", "--no-showboat-quickstart", "--showboat-quickstart"], True))
        for flags, expected in cases:
            with self.subTest(flags=flags), patch.object(sys, "argv", ["configure.py", *flags]):
                scope = dict(argparse=argparse, Path=Path, VERSIONS=["GALE01"],
                             DEFAULT_VERSION=0, is_windows=lambda: False)
                exec(parser_code, scope)
                self.assertEqual(scope["args"].showboat_quickstart, expected)
        with patch.object(sys, "argv", ["configure.py", "--showboat-quickstart"]):
            errors = io.StringIO()
            with redirect_stderr(errors), self.assertRaises(SystemExit) as raised:
                exec(parser_code, dict(argparse=argparse, Path=Path, VERSIONS=["GALE01"],
                                       DEFAULT_VERSION=0, is_windows=lambda: False))
            self.assertEqual(raised.exception.code, 2)
            self.assertIn("require --showboat-ai", errors.getvalue())
        helper = (ROOT / "tools/build_showboat.sh").read_text().replace("\\\n", " ")
        self.assertRegex(helper, r'--showboat-ai\b[^\n]*--showboat-quickstart\s+"\$@"')

    def test_quickstart_is_boot_exit_only(self):
        boot = (ROOT / "src/melee/gm/gmboot.c").read_text()
        leave = function(boot, "bootOnLeave")
        self.assertIn("SHOWBOAT_QUICKSTART", leave)
        self.assertNotIn("SHOWBOAT_QUICKSTART", function(boot, "bootOnLoad"))
        self.assertNotIn("SHOWBOAT_QUICKSTART", function(boot, "memcardOnLoad"))
        # CSS loads and results/back must not reapply the boot-only preset.
        for path in (ROOT / "src/melee/gm").glob("*.c"):
            if path.name != "gmboot.c":
                with self.subTest(path=path.name):
                    self.assertNotIn("SHOWBOAT_QUICKSTART", path.read_text())


if __name__ == "__main__":
    unittest.main()
