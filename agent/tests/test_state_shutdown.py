import multiprocessing as mp
import signal
import time
from types import SimpleNamespace
import unittest

from melee_agent.state_shutdown import stop_state_receiver


def backpressured_sender(connection, ready):
    ready.set()
    try:
        while True:
            connection.send_bytes(b"x" * 65536)
    except (BrokenPipeError, EOFError, OSError):
        pass


def ignores_shutdown(ready):
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    ready.set()
    time.sleep(10)


class StateShutdownTests(unittest.TestCase):
    def exercise(self, stubborn=False):
        context = mp.get_context("spawn")
        reader, writer = context.Pipe(False)
        ready = context.Event()
        worker = context.Process(target=ignores_shutdown if stubborn else backpressured_sender,
            args=(ready,) if stubborn else (writer, ready))
        worker.start()
        calls = []
        stream = SimpleNamespace(_worker=worker, _shutdown=context.Event(), _buffer=reader, running=True)
        console = SimpleNamespace(_slippstream=stream, _process=None, temp_dir=None, stop=lambda: calls.append("stopped"))
        try:
            self.assertTrue(ready.wait(2))
            time.sleep(.02)
            started = time.monotonic()
            report = stop_state_receiver(console)
            self.assertLess(time.monotonic()-started, 2)
            self.assertTrue(report["stopped"])
            self.assertFalse(worker.is_alive())
            self.assertIsNone(stream._worker)
            self.assertEqual(calls, ["stopped"])
            return report
        finally:
            if worker.is_alive():
                worker.kill()
                worker.join(timeout=1)
            reader.close()
            writer.close()

    def test_full_receiver_pipe_closes_before_join(self):
        report = self.exercise()
        self.assertFalse(report["killed"])

    def test_unresponsive_owned_receiver_is_killed_within_bound(self):
        report = self.exercise(stubborn=True)
        self.assertTrue(report["terminated"])
        self.assertTrue(report["killed"])
        self.assertEqual(report["exit_code"], -9)

    def test_unexpected_emulator_or_temporary_home_ownership_is_refused(self):
        for values in ({"_process": object()}, {"temp_dir": "/private/fixture"}):
            with self.assertRaises(RuntimeError):
                stop_state_receiver(SimpleNamespace(**values))


if __name__ == "__main__":
    unittest.main()
