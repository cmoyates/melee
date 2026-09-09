#!/usr/bin/env python3
"""CLI/launcher tests using only a temporary repo, fake processes and tiny assets."""

from datetime import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
STDOUT = b"stdout\x00\xff\r\n"
STDERR = b"stderr\x00\xfe\n"
FAKE = r'''
import json
import os
from pathlib import Path
import signal
import sys

Path(os.environ["FAKE_ARGS"]).write_text(json.dumps(sys.argv[1:]))
assert sys.stdin.buffer.read() == b"", "launch must not inherit stdin"
mode = os.environ.get("FAKE_MODE", "exit")
os.write(1, b"stdout\x00\xff\r\n")
os.write(2, b"stderr\x00\xfe\n")
if mode == "large":
    for _ in range(64):
        os.write(1, b"\x00\xff" * 32768)
        os.write(2, b"\xfe\x01" * 32768)
if mode == "signal":
    sig = int(os.environ["FAKE_SIGNAL"])
    if sig != signal.SIGKILL:
        signal.signal(sig, signal.SIG_DFL)
    os.kill(os.getpid(), sig)
if mode in ("wait", "wait-default"):
    def caught(sig, frame):
        os.write(2, ("caught=%d\n" % sig).encode())
        sys.exit(int(os.environ["FAKE_EXIT"]))
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, caught if mode == "wait" else signal.SIG_DFL)
    signal.alarm(15)  # A failed forwarding test cannot leave a permanent fake child.
    Path(os.environ["FAKE_READY"]).write_text(json.dumps({
        "pid": os.getpid(), "pgid": os.getpgrp(),
    }))
    while True:
        signal.pause()
sys.exit(int(os.environ.get("FAKE_EXIT", "0")))
'''


class ShowboatCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="showboat-capture-")
        self.addCleanup(self.temporary.cleanup)
        # macOS /var and /tmp may themselves be symlinks. All capture paths in
        # successful tests deliberately use the real temporary-directory path.
        self.work = Path(self.temporary.name).resolve()
        self.repo = self.work / "repo"
        self.repo.mkdir()
        self.tools = self.repo / "tools"
        self.tools.mkdir()
        for name in ("showboat_capture.py", "run_showboat.sh"):
            shutil.copyfile(ROOT / "tools" / name, self.tools / name)
        self.helper = self.tools / "showboat_capture.py"
        self.bin = self.work / "bin"
        self.bin.mkdir()
        self.home = self.work / "home"
        self.home.mkdir()
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith(("GIT_", "FAKE_"))}
        self.env.update({
            "HOME": str(self.home),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PATH": str(self.bin) + os.pathsep + os.environ.get("PATH", os.defpath),
            "FAKE_ARGS": str(self.work / "args.json"),
            "FAKE_READY": str(self.work / "ready.json"),
            "FAKE_EXIT": "0",
            "GUARD_CALLS": str(self.work / "guard-calls"),
            "COPY_CALLS": str(self.work / "copy-calls"),
            "EXTRACT_CALLS": str(self.work / "extract-calls"),
            "FAKE_PGREP_STATUS": "1",
        })
        self.fake = self.bin / "fake Dolphin"
        self.executable(self.fake, "#!" + sys.executable + "\n" + FAKE)
        self.env["DOLPHIN"] = str(self.fake)
        self.executable(self.bin / "pgrep", '''#!/bin/sh
printf '%s\\n' "$@" >> "$GUARD_CALLS"
exit "$FAKE_PGREP_STATUS"
''')
        real_cp = shutil.which("cp")
        self.assertIsNotNone(real_cp)
        self.executable(self.bin / "cp", f'''#!/bin/sh
printf '%s\\n' "$@" >> "$COPY_CALLS"
exec "{real_cp}" "$@"
''')
        self.build = self.repo / "build/showboat"
        self.dol = self.build / "GALE01/main.dol"
        self.put(self.dol, b"tiny rebuilt fixture DOL\x00SBREC \xff")
        self.disc = self.build / "disc"
        self.put(self.disc / "sys/boot.bin", b"GALE01\x00\x02" + bytes(24))
        self.virtual_dol = self.disc / "sys/main.dol"
        self.put(self.virtual_dol, b"previous virtual DOL: must survive refusal")
        self.put(self.disc / "files/fixture", b"tiny extracted-asset placeholder")
        self.source_disc = self.repo / "SourceDisc/fixture.ciso"
        self.put(self.source_disc, b"fixture source disc: never extract or modify")
        self.stock_dol = self.repo / "stock/main.dol"
        self.put(self.stock_dol, b"fixture stock DOL: never modify")
        self.controller = self.home / "Library/Application Support/Dolphin/Config/GCPadNew.ini"
        self.put(self.controller, b"[GCPad1]\nDevice = fixture-controller\n")
        self.user = self.build / "dolphin-user"
        self.recordings = self.build / "recordings"
        self.executable(self.repo / "build/tools/dtk", '''#!/bin/sh
printf '%s\\n' "$@" >> "$EXTRACT_CALLS"
exit 99
''')
        python = self.repo / ".venv/bin/python"
        python.parent.mkdir(parents=True)
        python.symlink_to(sys.executable)
        self.put(self.repo / ".gitignore", b"build/\n.venv/\n__pycache__/\n")
        self.git("init", "-q")
        self.git("add", ".")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "-c", "core.hooksPath=/dev/null", "commit", "-qm", "fixture")
        self.commit = self.git("rev-parse", "HEAD").stdout.strip()

    def put(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def executable(self, path, source):
        self.put(path, source.encode())
        path.chmod(0o755)

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.repo, env=self.env,
                              text=True, capture_output=True, check=True, timeout=10)

    def cli(self, command=None, destination=None, controller=None):
        args = [sys.executable, "-B", str(self.helper), "--dol", str(self.dol),
                "--recordings-dir", str(destination or self.recordings)]
        if controller is not None:
            args += ["--controller-config", str(controller)]
        return args + ["--"] + (command if command is not None else [str(self.fake)])

    def run_cli(self, **kwargs):
        return subprocess.run(self.cli(**kwargs), cwd=self.repo, env=self.env,
                              input=b"must not reach the child", capture_output=True, timeout=20)

    def launch_shell(self):
        return subprocess.run(["/bin/sh", "tools/run_showboat.sh", str(self.source_disc)],
                              cwd=self.repo, env=self.env, input=b"not interactive",
                              capture_output=True, timeout=20)

    def archive(self, result):
        lines = result.stdout.decode().splitlines()
        self.assertEqual(len(lines), 1, result)
        path = Path(lines[0])
        self.assertEqual(path.parent, self.recordings)
        self.assertRegex(path.name, r"^\d{8}T\d{6}\.\d{6}Z-[0-9a-f]{32}$")
        self.assertEqual({p.name for p in path.iterdir()},
                         {"runtime.log", "launch.json", "metadata.json"})
        launch = json.loads((path / "launch.json").read_text())
        self.assertNotIn("returncode", launch)
        self.assertNotIn("end_utc", launch)
        metadata = json.loads((path / "metadata.json").read_text())
        self.assertEqual(launch, {key: metadata[key] for key in launch})
        start = datetime.fromisoformat(metadata["start_utc"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(metadata["end_utc"].replace("Z", "+00:00"))
        self.assertLessEqual(start, end)
        self.assertEqual(start.utcoffset().total_seconds(), 0)
        self.assertEqual(end.utcoffset().total_seconds(), 0)
        return path, metadata

    def module(self):
        spec = importlib.util.spec_from_file_location("fixture_capture", self.helper)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_binary_capture_metadata_and_nonzero_exits(self):
        for status in (0, 1, 37, 255):
            with self.subTest(status=status):
                self.env["FAKE_EXIT"] = str(status)
                result = self.run_cli(controller=self.controller)
                self.assertEqual(result.returncode, status, result.stderr)
                path, metadata = self.archive(result)
                self.assertEqual((path / "runtime.log").read_bytes(), STDOUT + STDERR)
                self.assertEqual(metadata["returncode"], status)
                self.assertEqual(metadata["dol"], str(self.dol))
                self.assertEqual(metadata["dol_sha1"], hashlib.sha1(self.dol.read_bytes()).hexdigest())
                self.assertEqual(metadata["dol_size"], self.dol.stat().st_size)
                self.assertIs(metadata["recorder_marker_present"], True)
                self.assertEqual(metadata["controller_config_sha1"],
                                 hashlib.sha1(self.controller.read_bytes()).hexdigest())
                self.assertEqual(metadata["git_commit"], self.commit)
                self.assertIs(metadata["git_dirty"], False)
                self.assertNotIn("source", metadata)

    def test_marker_absence_and_chunk_boundary(self):
        module = self.module()
        for data, present in ((b"no recorder", False),
                              (b"x" * (module.CHUNK_SIZE - 3) + b"SBREC tail", True)):
            with self.subTest(present=present):
                self.dol.write_bytes(data)
                result = self.run_cli()
                self.assertEqual(result.returncode, 0, result.stderr)
                _, metadata = self.archive(result)
                self.assertIs(metadata["recorder_marker_present"], present)
                self.assertEqual(metadata["dol_sha1"], hashlib.sha1(data).hexdigest())
                self.assertNotIn("controller_config_sha1", metadata)

    def test_git_dirty_tracked_and_untracked_and_unavailable(self):
        for path in (self.stock_dol, self.repo / "untracked.txt"):
            with self.subTest(path=path):
                original = path.read_bytes() if path.exists() else None
                self.put(path, b"dirty fixture")
                _, metadata = self.archive(self.run_cli())
                self.assertIs(metadata["git_dirty"], True)
                self.assertEqual(metadata["git_commit"], self.commit)
                if original is None:
                    path.unlink()
                else:
                    path.write_bytes(original)
        shutil.rmtree(self.repo / ".git")
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        _, metadata = self.archive(result)
        self.assertNotIn("git_commit", metadata)
        self.assertNotIn("git_dirty", metadata)

    def test_literal_command_arguments_no_shell_evaluation(self):
        sentinel = self.work / "must-not-exist"
        args = ["two words", "", "*", f"$(touch '{sentinel}')",
                f"; touch '{sentinel}'", "--option=a=b", "quote'\"\\\n"]
        result = self.run_cli(command=[str(self.fake), *args])
        self.assertEqual(result.returncode, 0, result.stderr)
        _, metadata = self.archive(result)
        self.assertEqual(json.loads(Path(self.env["FAKE_ARGS"]).read_text()), args)
        self.assertEqual(metadata["command"], [str(self.fake), *args])
        self.assertFalse(sentinel.exists())

    def test_concurrent_unique_archives_do_not_overwrite(self):
        processes = [subprocess.Popen(self.cli(), cwd=self.repo, env=self.env,
                                      stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE) for _ in range(4)]
        paths = []
        try:
            for process in processes:
                out, err = process.communicate(timeout=20)
                self.assertEqual(process.returncode, 0, err)
                path, _ = self.archive(subprocess.CompletedProcess(process.args, 0, out, err))
                paths.append(path)
            self.assertEqual(len(set(paths)), 4)
            before = {str(p): p.read_bytes() for path in paths for p in path.iterdir()}
            self.assertEqual(self.run_cli().returncode, 0)
            self.assertEqual(before, {p: Path(p).read_bytes() for p in before})
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.communicate()

    def test_large_log_is_not_relayed_or_buffered_on_stdout(self):
        self.env["FAKE_MODE"] = "large"
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        path, _ = self.archive(result)
        expected = hashlib.sha1(STDOUT + STDERR)
        for _ in range(64):
            expected.update(b"\x00\xff" * 32768)
            expected.update(b"\xfe\x01" * 32768)
        sha1, size, _ = self.module().fingerprint(path / "runtime.log")
        self.assertEqual(size, len(STDOUT + STDERR) + 8 * 1024 * 1024)
        self.assertEqual(sha1, expected.hexdigest())

    def test_command_not_found_and_not_executable_are_archived(self):
        denied = self.bin / "not-executable"
        denied.write_bytes(b"not executable")
        for command, status in ((self.bin / "does-not-exist", 127), (denied, 126)):
            with self.subTest(status=status):
                result = self.run_cli(command=[str(command)])
                self.assertEqual(result.returncode, status, result.stderr)
                path, metadata = self.archive(result)
                self.assertEqual(metadata["returncode"], status)
                self.assertIn("launch_error", metadata)
                self.assertEqual((path / "runtime.log").read_bytes(), b"")
        self.assertFalse(Path(self.env["FAKE_ARGS"]).exists())

    def test_missing_command_or_dol_never_launches(self):
        result = self.run_cli(command=[])
        self.assertEqual(result.returncode, 2)
        self.dol.unlink()
        result = self.run_cli()
        self.assertEqual(result.returncode, 1)
        self.assertFalse(self.recordings.exists())
        self.assertFalse(Path(self.env["FAKE_ARGS"]).exists())

    def test_symlink_capture_destinations_and_ancestors_are_rejected(self):
        outside = self.work / "outside"
        outside.mkdir()
        self.put(outside / "sentinel", b"unchanged")
        link = self.build / "redirect"
        link.symlink_to(outside, target_is_directory=True)
        dangling = self.build / "dangling"
        dangling.symlink_to(self.work / "not-created", target_is_directory=True)
        for destination in (link, link / "nested/recordings", dangling):
            with self.subTest(destination=destination):
                result = self.run_cli(destination=destination)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertEqual(result.stdout, b"")
                self.assertFalse(Path(self.env["FAKE_ARGS"]).exists())
        self.assertEqual(list(outside.iterdir()), [outside / "sentinel"])
        self.assertEqual((outside / "sentinel").read_bytes(), b"unchanged")
        self.assertFalse((self.work / "not-created").exists())

    def test_exclusive_files_and_atomic_metadata_refuse_existing_entries(self):
        module = self.module()
        path, directory = module.open_capture_directory(self.recordings)
        self.addCleanup(os.close, directory)
        target = self.work / "untouched"
        target.write_bytes(b"untouched")
        for name in ("runtime.log", "metadata.json"):
            (path / name).symlink_to(target)
        with self.assertRaises(FileExistsError):
            module.exclusive_file(directory, "runtime.log")
        with self.assertRaises(FileExistsError):
            module.write_metadata(directory, {"returncode": 0})
        self.assertEqual(target.read_bytes(), b"untouched")
        (path / "metadata.json").unlink()
        original_link = module.os.link

        def inspect_before_publish(source, destination, **kwargs):
            self.assertFalse((path / "metadata.json").exists())
            self.assertEqual(json.loads((path / source).read_text()), {"returncode": 23})
            return original_link(source, destination, **kwargs)

        with patch.object(module.os, "link", side_effect=inspect_before_publish):
            module.write_metadata(directory, {"returncode": 23})
        with self.assertRaises(FileExistsError):
            module.write_metadata(directory, {"returncode": 24})
        self.assertEqual(json.loads((path / "metadata.json").read_text()), {"returncode": 23})
        self.assertEqual({p.name for p in path.iterdir()}, {"runtime.log", "metadata.json"})

    def test_child_signal_status_is_preserved(self):
        self.env["FAKE_MODE"] = "signal"
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGKILL):
            with self.subTest(signal=sig):
                self.env["FAKE_SIGNAL"] = str(sig.value)
                result = self.run_cli()
                self.assertEqual(result.returncode, -sig, result.stderr)
                path, metadata = self.archive(result)
                self.assertEqual(metadata["returncode"], -sig)
                self.assertEqual((path / "runtime.log").read_bytes(), STDOUT + STDERR)

    def test_forwarded_signals_graceful_exit_and_same_process_group(self):
        for mode in ("wait", "wait-default"):
            for sig in (signal.SIGINT, signal.SIGTERM):
                with self.subTest(mode=mode, signal=sig):
                    ready = Path(self.env["FAKE_READY"])
                    ready.unlink(missing_ok=True)
                    self.env.update(FAKE_MODE=mode, FAKE_EXIT="29")
                    # Only these test fakes get a private group for safe test cleanup.
                    # The helper itself must not put its child in another group.
                    process = subprocess.Popen(self.cli(), cwd=self.repo, env=self.env,
                                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                               stderr=subprocess.PIPE, start_new_session=True)
                    try:
                        deadline = time.monotonic() + 10
                        while not ready.exists() and time.monotonic() < deadline:
                            self.assertIsNone(process.poll())
                            time.sleep(0.01)
                        self.assertTrue(ready.exists(), "fake never became ready")
                        # File creation and write can race; retry JSON parsing briefly.
                        while True:
                            try:
                                info = json.loads(ready.read_text())
                                break
                            except json.JSONDecodeError:
                                if time.monotonic() >= deadline:
                                    raise
                                time.sleep(0.01)
                        self.assertEqual(info["pgid"], process.pid)
                        live = [p for p in self.recordings.iterdir()
                                if not (p / "metadata.json").exists()]
                        self.assertEqual(len(live), 1)
                        launch = json.loads((live[0] / "launch.json").read_text())
                        self.assertEqual(launch["dol_sha1"],
                                         hashlib.sha1(self.dol.read_bytes()).hexdigest())
                        self.assertNotIn("end_utc", launch)
                        process.send_signal(sig)  # Only the wrapper, not its group.
                        out, err = process.communicate(timeout=10)
                        status = 29 if mode == "wait" else -sig
                        self.assertEqual(process.returncode, status, err)
                        path, metadata = self.archive(
                            subprocess.CompletedProcess(process.args, status, out, err))
                        self.assertEqual(metadata["returncode"], status)
                        suffix = f"caught={sig.value}\n".encode() if mode == "wait" else b""
                        self.assertEqual((path / "runtime.log").read_bytes(), STDOUT + STDERR + suffix)
                    finally:
                        if process.poll() is None:
                            os.killpg(process.pid, signal.SIGKILL)
                            process.communicate()

    def test_running_guard_and_check_failure_precede_any_copy_or_extraction(self):
        before = self.virtual_dol.read_bytes()
        for status in (0, 2, 127):
            with self.subTest(status=status):
                self.env["FAKE_PGREP_STATUS"] = str(status)
                result = self.launch_shell()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(b"no DOL copied", result.stderr)
                self.assertEqual(self.virtual_dol.read_bytes(), before)
                self.assertFalse(self.recordings.exists())
                self.assertFalse(self.user.exists())
                for name in ("FAKE_ARGS", "COPY_CALLS", "EXTRACT_CALLS"):
                    self.assertFalse(Path(self.env[name]).exists())
        shutil.rmtree(self.disc)
        self.env["FAKE_PGREP_STATUS"] = "0"
        self.assertNotEqual(self.launch_shell().returncode, 0)
        self.assertFalse(self.disc.exists())
        self.assertFalse(Path(self.env["EXTRACT_CALLS"]).exists())
        self.assertTrue(Path(self.env["GUARD_CALLS"]).exists())

    def test_shell_disc_validation_still_precedes_dol_copy(self):
        before = self.virtual_dol.read_bytes()
        self.put(self.disc / "sys/boot.bin", b"GALE01\x00\x01")
        result = self.launch_shell()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"Expected Melee US v1.02", result.stderr)
        self.assertEqual(self.virtual_dol.read_bytes(), before)
        self.assertFalse(Path(self.env["COPY_CALLS"]).exists())
        self.assertFalse(Path(self.env["FAKE_ARGS"]).exists())
        self.assertFalse(self.recordings.exists())

    def test_shell_preserves_flags_assets_and_controller_profile(self):
        source = self.source_disc.read_bytes()
        stock = self.stock_dol.read_bytes()
        normal = self.controller.read_bytes()
        self.env["FAKE_EXIT"] = "17"
        result = self.launch_shell()
        self.assertEqual(result.returncode, 17, result.stderr)
        _, metadata = self.archive(result)
        self.assertEqual(metadata["returncode"], 17)
        self.assertEqual(metadata["dol"], str(self.virtual_dol))
        self.assertEqual(self.virtual_dol.read_bytes(), self.dol.read_bytes())
        self.assertEqual(metadata["dol_sha1"], hashlib.sha1(self.dol.read_bytes()).hexdigest())
        profile = self.user / "Config/GCPadNew.ini"
        self.assertEqual(profile.read_bytes(), normal)
        expected = ["--user", str(self.user)]
        for setting in ("Main.Core.CPUThread=False", "Main.Core.EnableCheats=False",
                        "Logger.Options.WriteToFile=True", "Logger.Options.WriteToConsole=True",
                        "Logger.Options.Verbosity=4", "Logger.Logs.OSREPORT=True",
                        "Logger.Logs.OSREPORT_HLE=True", "Logger.Logs.BOOT=True"):
            expected += ["-C", setting]
        expected += ["--exec", str(self.virtual_dol)]
        self.assertEqual(json.loads(Path(self.env["FAKE_ARGS"]).read_text()), expected)
        profile.write_bytes(b"custom test mapping: preserve on subsequent launches")
        _, second = self.archive(self.launch_shell())
        self.assertEqual(second["controller_config_sha1"], hashlib.sha1(profile.read_bytes()).hexdigest())
        self.assertEqual(self.controller.read_bytes(), normal)
        self.assertEqual(self.source_disc.read_bytes(), source)
        self.assertEqual(self.stock_dol.read_bytes(), stock)
        self.assertFalse(Path(self.env["EXTRACT_CALLS"]).exists())
        self.assertEqual(len(list(self.recordings.iterdir())), 2)

    def test_shell_without_controller_configuration(self):
        self.controller.unlink()
        result = self.launch_shell()
        self.assertEqual(result.returncode, 0, result.stderr)
        _, metadata = self.archive(result)
        self.assertNotIn("controller_config_sha1", metadata)
        self.assertFalse((self.user / "Config/GCPadNew.ini").exists())


if __name__ == "__main__":
    unittest.main()
