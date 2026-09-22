import errno
from pathlib import Path
import tempfile
import threading
import time
import unittest

from melee_agent.recorder import FrameRecorder, RecorderError


class ControlledWriter:
    def __init__(self, fail=False):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.fail = fail
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def write(self, data):
        self.entered.set()
        if self.fail:
            raise OSError(errno.ENOSPC, "private path")
        self.release.wait(timeout=3)
        return len(data)
    def flush(self):
        pass


class RecorderTests(unittest.TestCase):
    def test_drains_complete_ordered_jsonl_and_accounts_bytes(self):
        path = Path(tempfile.mkdtemp(prefix="jev-recorder-")) / "frames.jsonl"
        recorder = FrameRecorder(path, capacity=32)
        for frame in range(20):
            recorder.publish({"frame": frame})
        recorder.close()
        self.assertEqual(path.read_text().splitlines(), ['{"frame":%d}' % i for i in range(20)])
        self.assertEqual(recorder.report()["unwritten"], 0)
        self.assertEqual(recorder.bytes_written, path.stat().st_size)
        with self.assertRaisesRegex(RecorderError, "closed"):
            recorder.publish({})

    def test_stalled_disk_never_blocks_producer_and_bounded_close_fails(self):
        writer = ControlledWriter()
        recorder = FrameRecorder(None, capacity=2, opener=lambda: writer)
        try:
            recorder.publish({"frame": 1})
            self.assertTrue(writer.entered.wait(timeout=1))
            recorder.publish({"frame": 2})
            recorder.publish({"frame": 3})
            started = time.monotonic()
            with self.assertRaisesRegex(RecorderError, "queue_full"):
                recorder.publish({"frame": 4})
            self.assertLess(time.monotonic() - started, .1)
            with self.assertRaisesRegex(RecorderError, "queue_full"):
                recorder.close(timeout=.01)
            self.assertEqual(recorder.report()["rejected"], 1)
            self.assertFalse(recorder.report()["writer_stopped"])
        finally:
            writer.release.set()
            recorder.thread.join(timeout=2)

    def test_disk_full_is_reported_without_private_exception_details(self):
        writer = ControlledWriter(fail=True)
        recorder = FrameRecorder(None, opener=lambda: writer)
        recorder.publish({})
        self.assertTrue(recorder.failed.wait(timeout=1))
        with self.assertRaisesRegex(RecorderError, "io_or_encoding_error"):
            recorder.publish({})
        with self.assertRaises(RecorderError):
            recorder.close()
        self.assertEqual(recorder.report()["unwritten"], 1)
        self.assertNotIn("private", str(recorder.report()))

    def test_byte_limit_and_nonfinite_values_fail_closed(self):
        for record, maximum, reason in (({"large": "x" * 100}, 20, "byte_limit"),
                                        ({"x": float("nan")}, 100, "encoding_error")):
            path = Path(tempfile.mkdtemp(prefix="jev-recorder-")) / "frames.jsonl"
            recorder = FrameRecorder(path, max_bytes=maximum)
            recorder.publish(record)
            with self.assertRaisesRegex(RecorderError, reason):
                recorder.close()
            self.assertEqual(recorder.written, 0)

    def test_close_timeout_with_space_left_is_explicit(self):
        writer = ControlledWriter()
        recorder = FrameRecorder(None, opener=lambda: writer)
        try:
            recorder.publish({})
            self.assertTrue(writer.entered.wait(timeout=1))
            with self.assertRaisesRegex(RecorderError, "close_timeout"):
                recorder.close(timeout=.01)
        finally:
            writer.release.set()
            recorder.thread.join(timeout=2)

    def test_short_write_never_counts_a_partial_record_as_written(self):
        writer = ControlledWriter()
        writer.write = lambda data: len(data) - 1
        recorder = FrameRecorder(None, opener=lambda: writer)
        recorder.publish({"frame": 1})
        with self.assertRaisesRegex(RecorderError, "short_write"):
            recorder.close()
        self.assertEqual(recorder.written, 0)
        self.assertEqual(recorder.report()["unwritten"], 1)


if __name__ == "__main__":
    unittest.main()
