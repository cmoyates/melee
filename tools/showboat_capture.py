#!/usr/bin/env python3
"""Archive one explicitly requested launch; never discover or stop existing games."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import uuid


CHUNK_SIZE = 64 * 1024
MARKER = b"SBREC "


def utc_now():
    return datetime.now(timezone.utc)


def fingerprint(path):
    """Hash incrementally, including markers split across read boundaries."""
    digest = hashlib.sha1()
    size = 0
    present = False
    tail = b""
    with open(path, "rb") as source:
        while chunk := source.read(CHUNK_SIZE):
            digest.update(chunk)
            size += len(chunk)
            present = present or MARKER in tail + chunk
            tail = chunk[-(len(MARKER) - 1):]
    return digest.hexdigest(), size, present


def git_metadata():
    """Optional local provenance, without source content or index writes."""
    git = ["git", "--no-optional-locks", "-c", "core.fsmonitor=false"]
    try:
        commit = subprocess.run(
            git + ["rev-parse", "--verify", "HEAD"],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, check=True,
        ).stdout.decode("ascii").strip()
        with subprocess.Popen(
            git + ["status", "--porcelain=v1", "-z", "--untracked-files=normal"],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        ) as process:
            dirty = False
            while chunk := process.stdout.read(CHUNK_SIZE):
                dirty = True
            if process.wait() != 0:
                return {}
        return {"git_commit": commit, "git_dirty": dirty}
    except (OSError, subprocess.CalledProcessError, UnicodeError):
        return {}


def open_capture_directory(destination):
    """Walk with directory FDs so even symlinked ancestors cannot redirect writes.

    The returned FD pins a private, exclusively created UTC-nonce directory.
    Do not resolve() the caller's path: that would hide symlinks.
    """
    path = Path(destination).absolute()
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    directory = os.open(path.anchor, flags)
    try:
        for part in path.parts[1:]:
            try:
                os.mkdir(part, mode=0o700, dir_fd=directory)
            except FileExistsError:
                pass
            child = os.open(part, flags, dir_fd=directory)
            os.close(directory)
            directory = child
        while True:
            name = utc_now().strftime("%Y%m%dT%H%M%S.%fZ") + "-" + uuid.uuid4().hex
            try:
                os.mkdir(name, mode=0o700, dir_fd=directory)
                break
            except FileExistsError:
                continue
        child = os.open(name, flags, dir_fd=directory)
        return path / name, child
    finally:
        os.close(directory)


def exclusive_file(directory, name):
    return os.fdopen(os.open(
        name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600, dir_fd=directory,
    ), "wb")


def write_metadata(directory, metadata, name="metadata.json"):
    """Publish an immutable manifest atomically, without replacing an entry."""
    if name not in ("launch.json", "metadata.json"):
        raise ValueError("invalid manifest name")
    temporary = ".metadata-" + uuid.uuid4().hex + ".tmp"
    with exclusive_file(directory, temporary) as target:
        target.write((json.dumps(metadata, indent=2, ensure_ascii=True) + "\n").encode())
        target.flush()
        os.fsync(target.fileno())
    try:
        # Unlike replace(), link() also refuses an existing metadata symlink/file.
        os.link(temporary, name, src_dir_fd=directory,
                dst_dir_fd=directory, follow_symlinks=False)
    finally:
        os.unlink(temporary, dir_fd=directory)


def capture(args):
    dol_sha1, dol_size, marker = fingerprint(args.dol)
    metadata = {
        "dol": str(Path(args.dol).absolute()),
        "dol_sha1": dol_sha1,
        "dol_size": dol_size,
        "recorder_marker_present": marker,
        "command": args.command,
    }
    if args.controller_config is not None:
        controller_sha1, _, _ = fingerprint(args.controller_config)
        metadata["controller_config_sha1"] = controller_sha1
    # Sample before creating the archive, so it cannot make a clean repo dirty.
    metadata.update(git_metadata())
    path, directory = open_capture_directory(args.recordings_dir)
    process = None
    pending_signals = set()

    def forward(signum, _frame):
        if process is None:
            pending_signals.add(signum)
        else:
            try:
                process.send_signal(signum)
            except ProcessLookupError:
                pass

    previous = {}
    try:
        with exclusive_file(directory, "runtime.log") as log:
            for signum in (signal.SIGINT, signal.SIGTERM):
                previous[signum] = signal.signal(signum, forward)
            metadata["start_utc"] = utc_now().isoformat().replace("+00:00", "Z")
            # Retain provenance even while live or if SIGKILL prevents cleanup.
            # Final metadata.json is a separate immutable completion manifest.
            write_metadata(directory, metadata, "launch.json")
            print(path, flush=True)
            try:
                # Write both binary streams directly to disk, not a RAM buffer.
                # No shell, stdin, new session or new process group: Pi can still
                # terminate its own tree, and forwarded signals target only this child.
                process = subprocess.Popen(
                    args.command, stdin=subprocess.DEVNULL,
                    stdout=log, stderr=subprocess.STDOUT,
                )
            except OSError as error:
                returncode = 127 if isinstance(error, FileNotFoundError) else 126
                metadata["launch_error"] = str(error)
                print(f"showboat_capture: {error}", file=sys.stderr)
            else:
                for signum in pending_signals:
                    forward(signum, None)
                returncode = process.wait()
            metadata["end_utc"] = utc_now().isoformat().replace("+00:00", "Z")
            # Raw subprocess convention: negative means terminated by that signal.
            metadata["returncode"] = returncode
        write_metadata(directory, metadata)
        return returncode
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)
        os.close(directory)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dol", required=True, help="DOL actually being launched")
    parser.add_argument("--recordings-dir", required=True)
    parser.add_argument("--controller-config")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="-- COMMAND [ARG ...]")
    args = parser.parse_args(argv)
    if not args.command or args.command[0] != "--" or len(args.command) == 1:
        parser.error("provide -- COMMAND [ARG ...]")
    args.command = args.command[1:]
    try:
        return capture(args)
    except OSError as error:
        print(f"showboat_capture: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    status = main()
    if status < 0:
        # Preserve signal termination for subprocess callers as well as shells
        # (which report 128 + signal). Metadata is already safely published.
        signum = -status
        if signum not in (signal.SIGKILL, signal.SIGSTOP):
            signal.signal(signum, signal.SIG_DFL)
        os.kill(os.getpid(), signum)
        status = 128 + signum
    sys.exit(status)
