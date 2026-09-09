#!/usr/bin/env python3
"""Host-check the actual native post-load unlock block, not a Dolphin/save test."""
from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


def function(source, signature):
    match = re.search(r"^" + re.escape(signature) + r"[^\n]*\n\{.*?^\}\n",
                      source, re.M | re.S)
    if not match:
        raise AssertionError(f"Cannot extract native function {signature}")
    return match.group()


class ShowboatUnlockTests(unittest.TestCase):
    def test_actual_postload_block_opt_in_and_native_masks(self):
        compiler = shutil.which(os.environ.get("SHOWBOAT_TEST_CC", "clang"))
        self.assertIsNotNone(compiler, "clang required")
        main = (ROOT / "src/melee/gm/gmmain_lib.c").read_text()
        game = (ROOT / "src/melee/gm/gm_1601.c").read_text()
        header = (ROOT / "src/melee/gm/gm_1601.h").read_text()
        db_header = (ROOT / "src/melee/db/db.h").read_text()
        enum = re.search(r"typedef enum DbLKind\s*\{.*?\}\s*DbLKind;", db_header, re.S)
        count = re.search(r"^#define NUM_UNLOCKABLE_CHARACTERS \d+$", header, re.M)
        self.assertIsNotNone(enum)
        self.assertIsNotNone(count)
        source = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
typedef int s32;
typedef uint16_t u16;
typedef int GXRenderModeObj;
#define PAD_STACK(n) ((void)0)
struct Save { struct { u16 chars, x186A; unsigned char x186C, guard[32]; } thing; } save;
static struct Save* gmMainLib_804D3EE0 = &save;
static struct { bool skip_intro; } gmMainLib_8046B0F0;
static int DbLevel, db_804D6B20;
static bool invalid;
static int resets, power, notices, trophy_notices, audio, finalize, logs;
static u16 final_chars, final_stages;
static unsigned char final_options;
static char message[128];
u16* gmMainLib_GetUnlockedCharactersBitmaskPtr(void) { return &save.thing.chars; }
u16* gmMainLib_8015EDA4(void) { return &save.thing.x186A; }
int lb_8001B6E0(int i) { assert(i >= 1 && i < 9); return invalid; }
void gmMainLib_8015F600(int i, int zero) {
    assert(i >= 1 && i < 9 && zero == 0); ++resets;
    if (i == 1) { save.thing.chars = save.thing.x186A = save.thing.x186C = 0; }
}
void gm_IncrementPowerCount(void) { ++power; }
/* Native notification helpers are explicit spies; masks below are REAL code. */
void gm_8017297C(void) { ++notices; }
void gm_801741FC(void) { ++trophy_notices; }
void lbAudioAx_80028690(void) { ++audio; }
void gmMainLib_8015F500(void) {
    ++finalize; final_chars = save.thing.chars; final_stages = save.thing.x186A;
    final_options = save.thing.x186C;
}
void OSReport(const char* fmt, ...) {
    va_list args; va_start(args, fmt); vsnprintf(message, sizeof(message), fmt, args);
    va_end(args); ++logs;
}
'''
        source += enum.group() + "\n" + count.group() + "\n"
        source += function(game, "void gm_80164F18(void)")
        source += function(game, "void gm_8016468C(void)")
        source += function(main, "void gmMainLib_8015FA34(s32 arg0)")
        source += r'''
int main(void) {
    int args[] = { 0, 2, 1, -1 };
    int levels[] = { DbLKind_Master, DbLKind_DebugDevelop, DbLKind_DebugRom, DbLKind_Develop };
    for (int a = 0; a < 4; ++a) for (int bad = 0; bad < 2; ++bad)
    for (int d = 0; d < 4; ++d) for (int enabled = 0; enabled < 2; ++enabled)
    for (int skip = 0; skip < 2; ++skip) {
        memset(&save, 0, sizeof(save)); memset(save.thing.guard, 0xA5, sizeof(save.thing.guard));
        save.thing.chars = 0x8000; save.thing.x186A = 0x4000; save.thing.x186C = 0x20;
        invalid = bad; DbLevel = levels[d]; db_804D6B20 = enabled;
        gmMainLib_8046B0F0.skip_intro = skip;
        resets = power = notices = trophy_notices = audio = finalize = logs = 0;
        message[0] = 0;
        bool reset = bad || (args[a] != 0 && args[a] != 2);
        bool unlock = EXPECT_UNLOCK || (DbLevel > DbLKind_DebugDevelop && enabled);
        gmMainLib_8015FA34(args[a]);
        assert(DbLevel == levels[d] && db_804D6B20 == enabled);
        assert(resets == (reset ? 8 : 0)); assert(power == (!reset && !skip));
        assert(notices == unlock && trophy_notices == unlock);
        assert(audio == 1 && finalize == 1 && logs == EXPECT_UNLOCK);
        assert(save.thing.chars == ((reset ? 0 : 0x8000) | (unlock ? 0x7FF : 0)));
        assert(save.thing.x186A == ((reset ? 0 : 0x4000) | (unlock ? 0x7FF : 0)));
        assert(save.thing.x186C == (unlock ? 0xFF : reset ? 0 : 0x20));
        assert(final_chars == save.thing.chars && final_stages == save.thing.x186A);
        assert(final_options == save.thing.x186C);
        for (unsigned i = 0; i < sizeof(save.thing.guard); ++i) assert(save.thing.guard[i] == 0xA5);
        if (EXPECT_UNLOCK) {
            char expected[128];
            snprintf(expected, sizeof(expected), "SHOWBOAT UNLOCK: characters=%04x stages=%04x options=ff\n",
                     (unsigned) save.thing.chars, (unsigned) save.thing.x186A);
            assert(strcmp(message, expected) == 0);
        }
    }
    puts("PASS: post-load masks, invalid/missing saves, native debug fallback, opt-in, ordering, guards");
}
'''
        with tempfile.TemporaryDirectory(prefix="showboat-unlocks-") as work:
            path = Path(work) / "test.c"
            path.write_text(source)
            for flag in (None, 0, 1):
                with self.subTest(flag=flag):
                    binary = Path(work) / f"unlocks-{flag}"
                    cmd = [compiler, "-std=c99", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
                           "-Wno-unused-variable",  # unmodified native var_r3
                           "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
                           f"-DEXPECT_UNLOCK={int(flag == 1)}"]
                    if flag is not None:
                        cmd.append(f"-DSHOWBOAT_UNLOCK_ALL={flag}")
                    result = subprocess.run(cmd + [str(path), "-o", str(binary)],
                                            capture_output=True, text=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    env = dict(os.environ, ASAN_OPTIONS="detect_leaks=0:halt_on_error=1",
                               UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1")
                    result = subprocess.run([str(binary)], capture_output=True, text=True,
                                            env=env, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertTrue(result.stdout.startswith("PASS:"))

    def test_unlock_flag_requires_showboat_build(self):
        result = subprocess.run([os.sys.executable, str(ROOT / "configure.py"),
                                 "--showboat-unlock-all"], cwd=ROOT,
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 2)
        self.assertIn("require --showboat-ai", result.stderr)


if __name__ == "__main__":
    unittest.main()
