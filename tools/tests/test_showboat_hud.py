#!/usr/bin/env python3
"""Mocked HUD lifecycle/format tests of current C source; NOT a visual test."""
from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures/showboat_hud"


class ShowboatHUDTests(unittest.TestCase):
    def test_format_and_scene_lifetime(self):
        compiler = shutil.which(os.environ.get("SHOWBOAT_TEST_CC", "clang"))
        self.assertIsNotNone(compiler, "clang required")
        # Replace only include directives with host definitions. The actual
        # current header and implementation bodies are compiled, not a copy.
        parts = [(FIXTURES / "stubs.c").read_text()]
        for name in ("showboat_hud.h", "showboat_hud.c"):
            source = (ROOT / "src/melee/mod" / name).read_text()
            parts.append(re.sub(r"^#include[^\n]*", "", source, flags=re.M))
        parts.append((FIXTURES / "cases.c").read_text())
        with tempfile.TemporaryDirectory(prefix="showboat-hud-tests-") as directory:
            work = Path(directory)
            source = work / "test.c"
            binary = work / "test"
            source.write_text("\n".join(parts))
            compiled = subprocess.run(
                [compiler, "-std=c99", "-Wall", "-Wextra", "-Werror", "-g",
                 "-Wno-deprecated-declarations",  # MSL has sprintf, not snprintf
                 "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
                 str(source), "-o", str(binary)],
                text=True, capture_output=True, timeout=60,
            )
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            env = dict(os.environ, ASAN_OPTIONS="detect_leaks=0:halt_on_error=1",
                       UBSAN_OPTIONS="halt_on_error=1")
            result = subprocess.run([str(binary)], text=True, capture_output=True,
                                    timeout=10, env=env)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("PASS:", result.stdout)


if __name__ == "__main__":
    unittest.main()
