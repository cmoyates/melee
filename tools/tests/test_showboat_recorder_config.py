"""Recorder opt-in/default wiring; no build, assets or emulator invocation."""
import argparse
from contextlib import redirect_stderr
import io
import hashlib
import importlib.util
import struct
import tempfile
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

    def test_verifier_rejects_old_transport_and_accepts_v2_or_opt_out(self):
        # Synthetic DOL layout and object graph only; no retail assets/builds.
        spec = importlib.util.spec_from_file_location('recorder_verify_fixture',
                                                     ROOT / 'tools/verify_showboat.py')
        verify = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verify)
        for recorder, marker, valid in ((True, False, False), (True, True, True),
                                        (False, False, True), (False, True, False)):
            with self.subTest(recorder=recorder, marker=marker), tempfile.TemporaryDirectory() as work:
                root = Path(work)
                def put(name, data):
                    p = root / name
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_bytes(data)
                stock = b'fixture stock reference, not an executable'
                put('orig/GALE01/sys/main.dol', stock)
                put('build/GALE01/main.dol', stock)
                data = bytearray(512)
                struct.pack_into('>I', data, 0, 256)
                struct.pack_into('>I', data, 0x48, 0x80003100)
                struct.pack_into('>I', data, 0x90, 256)
                struct.pack_into('>3I', data, 0xD8, 0x80400000, 256, 0x80003100)
                tags = (b'SBREC ' if recorder else b'') + (b'ieee754-binary32-hex' if marker else b'')
                data[256:256 + len(tags)] = tags
                put('build/showboat/GALE01/main.dol', data)
                names = verify.EXPECTED_OBJECTS | {'melee/gm/gmboot.o', 'melee/gm/gmmain_lib.o'}
                if recorder:
                    names = names | {'melee/mod/showboat_recorder.o'}
                (root / 'build/cstick/GALE01/src').mkdir(parents=True)
                for name in names:
                    put('build/showboat/GALE01/src/' + name, b'fixture object')
                put('build.ninja', ('build build/showboat/GALE01/main.elf : link ' +
                    ' '.join('build/showboat/GALE01/src/' + n for n in sorted(names)) + '\n').encode())
                with patch.object(verify, 'ROOT', root), \
                     patch.object(verify, 'STOCK_SHA1', hashlib.sha1(stock).hexdigest()), \
                     patch.object(sys, 'argv', ['verify'] + ([] if recorder else ['--no-recorder'])):
                    if valid:
                        from contextlib import redirect_stdout
                        with redirect_stdout(io.StringIO()):
                            verify.main()
                    else:
                        with self.assertRaisesRegex(SystemExit, 'Recorder v2 transport marker mismatch'):
                            verify.main()

    def test_helper_and_verifier_options(self):
        helper = (ROOT / "tools/build_showboat.sh").read_text().replace("\\\n", " ")
        self.assertRegex(helper, r'--showboat-recorder\b[^\n]*"\$@"')
        verify = (ROOT / "tools/verify_showboat.py").read_text()
        self.assertIn('"--no-recorder"', verify)
        self.assertIn('"melee/mod/showboat_recorder.o"', verify)
        self.assertIn("Recorder link option mismatch", verify)
        self.assertIn("Recorder DOL marker mismatch", verify)
        self.assertIn("Recorder v2 transport marker mismatch", verify)
        self.assertIn("ieee754-binary32-hex", verify)


if __name__ == "__main__":
    unittest.main()
