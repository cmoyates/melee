"""Bounded shutdown for the pinned libmelee receiver's backpressured IPC pipe."""


def stop_state_receiver(console):
    if getattr(console, "_process", None) is not None or getattr(console, "temp_dir", None):
        raise RuntimeError("Unexpected console process or temporary-home ownership")
    stream = getattr(console, "_slippstream", None)
    if stream is None:
        console.stop()  # Asset-free test consoles have no native receiver.
        return {"stopped": True, "kind": "test_console"}
    worker = stream._worker
    report = {"kind": "libmelee_receiver", "pid": worker.pid if worker is not None else None,
              "stopped": worker is None, "terminated": False, "killed": False}
    if worker is not None:
        stream._shutdown.set()
        # libmelee joins before closing this read end. If its child is blocked
        # sending into a full pipe, that join never returns. Closing our owned
        # read end first wakes the sender with EOF/broken pipe.
        stream._buffer.close()
        if worker.pid is not None:
            worker.join(timeout=.5)
            if worker.is_alive():
                report["terminated"] = True
                worker.terminate()
                worker.join(timeout=.5)
            if worker.is_alive():
                report["killed"] = True
                worker.kill()
                worker.join(timeout=.5)
            report["stopped"] = not worker.is_alive()
            report["exit_code"] = worker.exitcode
        else:
            report["stopped"] = True
        if not report["stopped"]:
            return report
        stream._worker = None
    stream.running = False
    console.stop()
    return report
