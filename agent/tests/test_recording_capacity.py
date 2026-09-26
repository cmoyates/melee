"""Storage bounds remain finite across live capture and offline readers."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from melee_agent.config import Config, ConfigError, Limits, load_config
from melee_agent.incidents import IncidentError, open_regular, stream_records
from melee_agent.matches import preflight
from melee_agent.trace_limits import MAX_SOURCE_BYTES


class RecordingCapacityTests(unittest.TestCase):
    def test_opt_in_full_match_budget_and_oversized_configuration(self):
        root = Path(tempfile.mkdtemp(prefix="jev-capacity-test-")).resolve()
        config = root / "local.toml"
        self.assertEqual(load_config(root).limits.max_artifact_bytes, 268435456)
        config.write_text(f"[limits]\nmax_artifact_bytes = {MAX_SOURCE_BYTES}\n")
        self.assertEqual(load_config(root, config).limits.max_artifact_bytes, MAX_SOURCE_BYTES)
        config.write_text(f"[limits]\nmax_artifact_bytes = {MAX_SOURCE_BYTES+1}\n")
        with self.assertRaisesRegex(ConfigError, "artifact.*512 MiB"):
            load_config(root, config)

    def test_preflight_refuses_unsupported_budget_before_asset_or_process_access(self):
        config = Config(limits=Limits(max_artifact_bytes=MAX_SOURCE_BYTES+1))
        with patch("melee_agent.matches.load_config", return_value=config), \
                patch("melee_agent.matches.digest", side_effect=AssertionError("asset access")), \
                patch("subprocess.Popen", side_effect=AssertionError("process access")):
            with self.assertRaisesRegex(ValueError, "artifact.*512 MiB"):
                preflight(Path.cwd(), 120, 1, "delayed-fake")

    def test_sparse_source_above_old_limit_is_readable_but_ceiling_is_enforced(self):
        root = Path(tempfile.mkdtemp(prefix="jev-capacity-test-")).resolve()
        source = root / "frames.jsonl"
        # A sparse fixture exercises real fstat bounds without allocating 512 MiB.
        # Only its first complete record is consumed; holes are not valid JSON.
        with source.open("wb") as output:
            output.write(b'{"menu":"IN_GAME"}\n')
            output.truncate(MAX_SOURCE_BYTES)
        records = stream_records(source, MAX_SOURCE_BYTES)
        self.assertEqual(next(records)[1], {"menu": "IN_GAME"})
        records.close()
        with self.assertRaisesRegex(IncidentError, "file_type_or_size"):
            open_regular(source, 268435456)
        with source.open("r+b") as output:
            output.truncate(MAX_SOURCE_BYTES+1)
        with self.assertRaisesRegex(IncidentError, "file_type_or_size"):
            next(stream_records(source, MAX_SOURCE_BYTES))

    def test_larger_file_budget_keeps_per_record_guard(self):
        root = Path(tempfile.mkdtemp(prefix="jev-capacity-test-")).resolve()
        source = root / "frames.jsonl"
        source.write_bytes(b" "*65536+b"\n")
        with self.assertRaisesRegex(IncidentError, "oversized_incident_record"):
            next(stream_records(source, MAX_SOURCE_BYTES))

    def test_file_growth_cannot_bypass_the_initial_size_check(self):
        root = Path(tempfile.mkdtemp(prefix="jev-capacity-test-")).resolve()
        source = root / "frames.jsonl"
        source.write_bytes(b'{}\n')
        records = stream_records(source, 5)
        self.assertEqual(next(records)[1], {})
        with source.open("ab") as output:
            output.write(b'{}\n')
        with self.assertRaisesRegex(IncidentError, "source_byte_limit"):
            next(records)
