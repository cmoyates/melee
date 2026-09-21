"""Public-contract tests using retained synthetic workspaces, never game assets."""

from contextlib import redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from melee_agent.cli import main
from melee_agent.config import ConfigError, load_config
from melee_agent.doctor import diagnose, disc_check, port_check


class DoctorTests(unittest.TestCase):
    def setUp(self):
        # Retain fixtures for diagnosis. No TemporaryDirectory/rmtree cleanup.
        self.root = Path(tempfile.mkdtemp(prefix="jev-doctor-test-")).resolve()
        (self.root / "configure.py").write_text("# fixture\n")
        (self.root / "agent").mkdir()
        (self.root / "agent/pyproject.toml").write_text("# fixture\n")
        self.config = self.root / "agent/local.toml"

    def report(self, require="all"):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": ""}):
            return diagnose(self.root, require=require)

    def checks(self, report):
        return {c["id"]: c for c in report["checks"]}

    def test_missing_live_dependencies_do_not_block_offline(self):
        report = self.report("offline")
        self.assertEqual(report["schema_version"], 1)
        self.assertEqual((report["status"], report["exit_code"]), ("pass", 0))
        for name in ("live", "provider", "decomp"):
            self.assertEqual(report["capabilities"][name]["status"], "blocked")
        self.assertEqual(report["policy"]["character"], "FOX")

    def test_all_mode_reports_missing_capabilities(self):
        report = self.report()
        self.assertEqual((report["status"], report["exit_code"]), ("blocked", 2))
        for item in report["checks"]:
            if item["status"] != "pass":
                self.assertTrue(item["remediation"])

    def test_wrong_stock_dol_fails_but_offline_is_available(self):
        p = self.root / "orig/GALE01/sys/main.dol"
        p.parent.mkdir(parents=True)
        p.write_bytes(b"a wrong game executable")
        report = self.report()
        self.assertEqual(self.checks(report)["stock_dol"]["status"], "fail")
        self.assertEqual(report["exit_code"], 1)
        self.assertEqual(self.report("offline")["exit_code"], 0)
        self.assertEqual(p.read_bytes(), b"a wrong game executable")

    def test_correct_fingerprint_uses_actual_file_bytes(self):
        p = self.root / "fixture.dol"
        p.write_bytes(b"synthetic stock fixture")
        self.config.write_text('[paths]\nstock_dol = "fixture.dol"\n')
        with patch("melee_agent.doctor.STOCK_DOL_SHA1", hashlib.sha1(p.read_bytes()).hexdigest()):
            self.assertEqual(self.checks(self.report())["stock_dol"]["status"], "pass")

    def test_wrong_disc_revision_is_rejected(self):
        p = self.root / "fixture.iso"
        p.write_bytes(b"GALE01\x00\x01")
        self.config.write_text('[paths]\ndisc_image = "fixture.iso"\n')
        self.assertEqual(self.checks(self.report())["game_assets"]["status"], "fail")

    def test_header_alone_cannot_pass_full_assets_check(self):
        p = self.root / "fixture.iso"
        p.write_bytes(b"GALE01\x00\x02")
        self.config.write_text('[paths]\ndisc_image = "fixture.iso"\n')
        self.assertEqual(self.checks(self.report())["game_assets"]["status"], "fail")

    def test_valid_full_disc_fingerprint(self):
        p = self.root / "fixture.iso"
        p.write_bytes(b"GALE01\x00\x02" + b"synthetic disc bytes")
        self.config.write_text('[paths]\ndisc_image = "fixture.iso"\n')
        with patch("melee_agent.doctor.STOCK_DISC_SHA1", hashlib.sha1(p.read_bytes()).hexdigest()):
            result = disc_check(self.root, load_config(self.root))
        self.assertEqual(result["status"], "pass")

    def test_compressed_asset_is_blocked_not_misclassified(self):
        (self.root / "fixture.ciso").write_bytes(b"CISO" + bytes(12))
        self.config.write_text('[paths]\ndisc_image = "fixture.ciso"\n')
        self.assertEqual(self.checks(self.report())["game_assets"]["status"], "blocked")

    def test_external_input_is_allowed_but_never_executed(self):
        p = self.root.parent / (self.root.name + "-input")
        p.write_bytes(b"input only")
        self.config.write_text('[paths]\nstock_dol = ' + json.dumps(str(p)) + '\n')
        with patch("subprocess.Popen", side_effect=AssertionError("Unexpected process")):
            report = self.report()
        self.assertEqual(self.checks(report)["stock_dol"]["status"], "fail")

    def test_escaping_output_paths_fail(self):
        for path in ("../elsewhere", "build/showboat/runs", "/tmp/escaped-jev", "build/jev"):
            with self.subTest(path=path):
                self.config.write_text('[execution]\nrun_root = ' + json.dumps(path) + '\n')
                report = self.report("offline")
                self.assertEqual(report["exit_code"], 1)
                self.assertEqual(self.checks(report)["config"]["status"], "fail")

    def test_symlinked_output_base_cannot_own_showboat(self):
        (self.root / "build/showboat").mkdir(parents=True)
        (self.root / "build/jev").symlink_to(self.root / "build/showboat", target_is_directory=True)
        self.assertEqual(self.report("offline")["exit_code"], 1)

    def test_symlinked_output_child_escape_fails(self):
        (self.root / "build/jev").mkdir(parents=True)
        (self.root / "build/jev/runs").symlink_to(self.root / "agent", target_is_directory=True)
        self.assertEqual(self.report("offline")["exit_code"], 1)

    def test_configuration_path_escape_fails(self):
        outside = self.root.parent / (self.root.name + ".toml")
        outside.write_text("")
        self.assertEqual(diagnose(self.root, outside, "offline")["exit_code"], 1)
        self.config.symlink_to(outside)
        self.assertEqual(self.report("offline")["exit_code"], 1)

    def test_bad_config_never_exposes_private_values(self):
        secret = "private-user-do-not-report-secret"
        for content in ('[paths]\nruntime = "' + secret, 'api_key = "' + secret + '"',
                        '[paths]\nunknown_' + secret + ' = "value"'):
            with self.subTest(content=content):
                self.config.write_text(content)
                output = json.dumps(self.report())
                self.assertNotIn(secret, output)
                self.assertNotIn(str(self.root), output)
                self.assertEqual(self.report()["exit_code"], 1)

    def test_invalid_budgets_and_types_fail(self):
        for line in ("max_requests = true", "max_requests = 1.5", "max_requests = 0",
                        "max_cost_usd = nan", "max_cost_usd = inf", "max_cost_usd = -1",
                        'max_input_tokens = "secret"'):
            with self.subTest(line=line):
                self.config.write_text("[limits]\n" + line)
                self.assertEqual(self.report("offline")["exit_code"], 1)

    def test_integer_parser_limit_is_a_public_config_failure(self):
        self.config.write_text("[limits]\nmax_requests = " + "9" * 5000)
        report = self.report("offline")
        self.assertEqual(report["exit_code"], 1)
        self.assertEqual(self.checks(report)["config"]["status"], "fail")
        self.assertNotIn(str(self.config), json.dumps(report))

    def test_nonlocal_modes_and_invalid_ports_fail(self):
        for line in ('environment = "public"', 'environment = "private_netplay"',
                        "slippi_port = true", "slippi_port = 0", "slippi_port = 65536"):
            with self.subTest(line=line):
                self.config.write_text("[execution]\n" + line)
                self.assertEqual(self.report()["exit_code"], 1)

    def test_malformed_sections_and_paths_fail(self):
        for content in ('paths = 1', '[paths]\nruntime = []', '[execution]\nrun_root = ""',
                        '[paths]\nstock_dol = ""', '[paths]\nruntime_sha256 = "bad"'):
            with self.subTest(content=content):
                self.config.write_text(content)
                with self.assertRaises(ConfigError):
                    load_config(self.root)

    def test_runtime_pin_does_not_imply_compatibility(self):
        runtime = self.root / "runtime"
        runtime.write_text("#!/bin/sh\nexit 99\n")
        runtime.chmod(0o700)
        self.config.write_text('[paths]\nruntime = "runtime"\nruntime_sha256 = "' +
                                hashlib.sha256(runtime.read_bytes()).hexdigest() + '"\n')
        report = self.report()
        checks = self.checks(report)
        self.assertEqual(checks["runtime_file"]["status"], "pass")
        self.assertEqual(checks["runtime_compatibility"]["status"], "blocked")
        self.assertFalse(report["policy"]["emulator_launched"])

    def test_wrong_runtime_fingerprint_fails(self):
        runtime = self.root / "runtime"
        runtime.write_text("fixture")
        runtime.chmod(0o700)
        self.config.write_text('[paths]\nruntime = "runtime"\nruntime_sha256 = "' + "0" * 64 + '"\n')
        self.assertEqual(self.checks(self.report())["runtime_file"]["status"], "fail")

    def test_credentials_are_presence_only_and_never_echoed(self):
        secret = "test-secret-not-for-output"
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": secret}):
            report = diagnose(self.root)
        self.assertEqual(self.checks(report)["jev_credential"]["status"], "pass")
        self.assertEqual(self.checks(report)["jev_access"]["status"], "blocked")
        self.assertNotIn(secret, json.dumps(report))
        self.assertFalse(report["policy"]["provider_contacted"])

    def test_occupied_and_restricted_ports_have_distinct_messages(self):
        import errno
        for code, text in ((errno.EADDRINUSE, "occupied"), (errno.EPERM, "could not be probed")):
            with patch("melee_agent.doctor.socket.socket", side_effect=OSError(code, "private details")):
                result = port_check(51441)
            self.assertEqual(result["status"], "blocked")
            self.assertIn(text, result["message"])
            self.assertNotIn("private details", json.dumps(result))

    def test_port_probe_closes_socket_without_sending(self):
        with patch("melee_agent.doctor.socket.socket") as create:
            result = port_check(51441)
            probe = create.return_value.__enter__.return_value
            probe.bind.assert_called_once_with(("127.0.0.1", 51441))
            probe.connect.assert_not_called()
            probe.send.assert_not_called()
            probe.sendto.assert_not_called()
            create.return_value.__exit__.assert_called_once()
        self.assertEqual(result["status"], "pass")
        self.assertFalse(result["evidence"]["reservation"])

    def test_cli_json_exit_and_read_only_repeatability(self):
        self.config.write_text('[paths]\nstock_dol = "missing-private-path"\n')
        before = {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        for _ in range(2):
            output = io.StringIO()
            with redirect_stdout(output):
                status = main(["doctor", "--json", "--workspace", str(self.root), "--require", "offline"])
            report = json.loads(output.getvalue())
            self.assertEqual(status, report["exit_code"])
            self.assertEqual(status, 0)
            self.assertNotIn(str(self.root), output.getvalue())
            self.assertNotIn("missing-private-path", output.getvalue())
        after = {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_installed_cli_exit_matches_json(self):
        result = subprocess.run([sys.executable, "-B", "-m", "melee_agent.cli", "doctor", "--json",
                                    "--workspace", str(self.root)], capture_output=True, text=True)
        report = json.loads(result.stdout)
        self.assertEqual(result.returncode, report["exit_code"])
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
