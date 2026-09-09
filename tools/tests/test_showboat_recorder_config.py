"""Recorder opt-in/default wiring; no build, assets or emulator invocation."""
import argparse
from contextlib import redirect_stderr
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


class RecorderConfigTests(unittest.TestCase):
    def test_parser_opt_in_and_last_option_wins(self):
        text = (ROOT / "configure.py").read_text()
        code = compile(text[text.index("parser = argparse.ArgumentParser()"):
                            text.index("config = ProjectConfig()")], "configure.py", "exec")
        cases = [([], False), (["--showboat-ai"], False),
                 (["--showboat-ai", "--showboat-recorder"], True),
                 (["--showboat-ai", "--showboat-recorder", "--no-showboat-recorder"], False),
                 (["--showboat-ai", "--no-showboat-recorder", "--showboat-recorder"], True)]
        for flags, expected in cases:
            with self.subTest(flags=flags), patch.object(sys, "argv", ["configure.py", *flags]):
                scope = dict(argparse=argparse, Path=Path, VERSIONS=["GALE01"],
                             DEFAULT_VERSION=0, is_windows=lambda: False)
                exec(code, scope)
                self.assertEqual(scope["args"].showboat_recorder, expected)
                self.assertFalse(scope["args"].showboat_ai_debug)
        with patch.object(sys, "argv", ["configure.py", "--showboat-recorder"]):
            errors = io.StringIO()
            with redirect_stderr(errors), self.assertRaises(SystemExit) as raised:
                exec(code, dict(argparse=argparse, Path=Path, VERSIONS=["GALE01"],
                                DEFAULT_VERSION=0, is_windows=lambda: False))
            self.assertEqual(raised.exception.code, 2)
            self.assertIn("require --showboat-ai", errors.getvalue())

    def test_helper_and_verifier_options(self):
        helper = (ROOT / "tools/build_showboat.sh").read_text().replace("\\\n", " ")
        self.assertRegex(helper, r'--showboat-recorder\b[^\n]*"\$@"')
        verify = (ROOT / "tools/verify_showboat.py").read_text()
        self.assertIn('"--no-recorder"', verify)
        self.assertIn('"melee/mod/showboat_recorder.o"', verify)
        self.assertIn("Recorder link option mismatch", verify)
        self.assertIn("Recorder DOL marker mismatch", verify)


if __name__ == "__main__":
    unittest.main()
