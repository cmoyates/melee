"""Bounded off-loop JSONL writing. A failed logger stops control explicitly."""

import json
from queue import Empty, Full, Queue
import threading
import time


class RecorderError(RuntimeError):
    pass


class FrameRecorder:
    def __init__(self, path, *, capacity=256, max_bytes=200_000_000, opener=None):
        if type(capacity) is not int or capacity < 1 or type(max_bytes) is not int or max_bytes < 1:
            raise ValueError("Invalid recorder limits")
        self.path, self.max_bytes = path, max_bytes
        self.queue = Queue(maxsize=capacity)
        self.closed = threading.Event()
        self.ready = threading.Event()
        self.failed = threading.Event()
        self.failure = None
        self.error_type = None
        self.accepted = self.written = self.bytes_written = self.rejected = 0
        self.high_water = 0
        self.opener = opener or (lambda: path.open("xb", buffering=65536))
        self.thread = threading.Thread(target=self._write, name="jev-frame-recorder", daemon=True)
        self.thread.start()
        if not self.ready.wait(timeout=1):
            self._fail("recorder_start_timeout")
            self.closed.set()
        self.check()

    def _fail(self, reason):
        # First cause remains useful even if a later drain/close also fails.
        if not self.failed.is_set():
            self.failure = reason
            self.failed.set()

    def check(self):
        if self.failed.is_set():
            raise RecorderError(self.failure)

    def publish(self, record):
        """Transfer ownership of a fresh record; the caller must not mutate it."""
        self.check()
        if self.closed.is_set():
            raise RecorderError("recorder_closed")
        try:
            self.queue.put_nowait(record)
        except Full:
            self.rejected += 1
            self._fail("recorder_queue_full")
            self.check()
        self.accepted += 1
        self.high_water = max(self.high_water, self.queue.qsize())

    def _write(self):
        try:
            with self.opener() as handle:
                self.ready.set()
                last_flush = time.monotonic()
                while not self.closed.is_set() or not self.queue.empty():
                    try:
                        record = self.queue.get(timeout=.1)
                    except Empty:
                        record = None
                    if record is not None:
                        data = (json.dumps(record, allow_nan=False, separators=(",", ":")) + "\n").encode()
                        if len(data) > 65536:
                            raise RecorderError("recorder_record_too_large")
                        if self.bytes_written + len(data) > self.max_bytes:
                            raise RecorderError("recorder_byte_limit")
                        if handle.write(data) != len(data):
                            raise RecorderError("recorder_short_write")
                        self.bytes_written += len(data)
                        self.written += 1
                    if time.monotonic() - last_flush >= .25:
                        handle.flush()
                        last_flush = time.monotonic()
                handle.flush()
        except Exception as error:
            self.error_type = type(error).__name__
            # Local worker.log only. Public reports expose stable reason/type.
            import traceback
            traceback.print_exc()
            self._fail(str(error) if isinstance(error, RecorderError) else "recorder_io_or_encoding_error")
        finally:
            self.ready.set()

    def close(self, timeout=1):
        self.closed.set()
        self.thread.join(timeout=timeout)
        if self.thread.is_alive():
            self._fail("recorder_close_timeout")
        self.check()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        # Do not wait here: controller neutralization must precede bounded join.
        self.closed.set()

    def report(self):
        return {"status": "error" if self.failed.is_set() else "closed" if self.closed.is_set() else "running",
                "reason": self.failure, "error_type": self.error_type,
                "accepted": self.accepted, "written": self.written,
                "unwritten": self.accepted - self.written, "rejected": self.rejected,
                "bytes_written": self.bytes_written, "queue_capacity": self.queue.maxsize,
                "queue_high_water": self.high_water, "writer_stopped": not self.thread.is_alive()}
