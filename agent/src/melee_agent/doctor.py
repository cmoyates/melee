"""Read-only capability probes: no subprocesses, downloads or provider calls."""

from dataclasses import asdict
import errno
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import socket
import sys

from .config import ConfigError, load_config, owned_path, read_path


STOCK_DOL_SHA1 = "08e0bf20134dfcb260699671004527b2d6bb1a45"
STOCK_DISC_SHA1 = "d4e70c064cc714ba8400a849cf299dbd1aa326fc"
WIBO_SHA256 = "bfb53e13706506fef31c331a1b4312af84a5c71af451f0cafe42c5511b2acbe4"
RANK = {"pass": 0, "blocked": 1, "fail": 2}
EXIT = {"pass": 0, "blocked": 2, "fail": 1}


def check(name, status, message, remediation="", **evidence):
    return dict(id=name, status=status, message=message, remediation=remediation,
                evidence=evidence)


def digest(path, algorithm):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, algorithm).hexdigest()


def verified_file(name, path, expected, algorithm="sha1"):
    if not path.is_file():
        return check(name, "blocked", "Required local file is absent.",
                        "Configure an existing user-owned input; doctor never downloads assets.")
    actual = digest(path, algorithm)
    if actual != expected:
        return check(name, "fail", "Local file does not match the required fingerprint.",
                        "Use the pinned original input; do not overwrite or patch the supplied file.")
    return check(name, "pass", "Required fingerprint matches.", **{algorithm: expected})


def disc_check(root, config):
    if not config.disc_image:
        return check("game_assets", "blocked", "No full stock disc image configured.",
                        "Set paths.disc_image to a user-owned uncompressed US1.02 ISO/GCM.")
    path = read_path(root, config.disc_image)
    if not path.is_file():
        return check("game_assets", "blocked", "Configured full disc image is absent.",
                        "Configure an existing user-owned US1.02 image.")
    with path.open("rb") as handle:
        header = handle.read(8)
    if header[:4] in (b"CISO", b"RVZ\x01", b"WBFS", b"WIA\x01"):
        return check("game_assets", "blocked", "Compressed disc verification is not implemented.",
                        "Use a separately prepared uncompressed stock image; keep the source intact.")
    if header[:6] != b"GALE01" or header[7:] != b"\x02":
        return check("game_assets", "fail", "Disc header is not Melee US1.02.",
                        "Select the original GALE01 revision 2 disc.")
    return verified_file("game_assets", path, STOCK_DISC_SHA1)


def runtime_check(root, config):
    if not config.runtime:
        return check("runtime_file", "blocked", "No pinned Slippi executable configured.",
                        "J03 must select and probe a compatible macOS Slippi runtime.")
    path = read_path(root, config.runtime)
    if not path.is_file() or not os.access(path, os.X_OK):
        return check("runtime_file", "blocked", "Configured runtime is not an executable file.",
                        "Set paths.runtime to the executable, not an application directory.")
    if not config.runtime_sha256:
        return check("runtime_file", "blocked", "Runtime exists but has no pinned fingerprint.",
                        "Record the verified release/source checksum during J03.")
    return verified_file("runtime_file", path, config.runtime_sha256, "sha256")


def port_check(port):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.bind(("127.0.0.1", port))
    except OSError as error:
        occupied = error.errno == errno.EADDRINUSE
        return check("slippi_port", "blocked",
                        "Loopback UDP port is occupied." if occupied else "Loopback UDP availability could not be probed.",
                        "Choose an unused local port or resolve the probe restriction; do not stop another session.")
    return check("slippi_port", "pass", "Loopback UDP bind succeeded; no packets sent.",
                    port=port, reservation=False)


def runtime_evidence(root, config):
    blocked = check("runtime_compatibility", "blocked", "Three pinned cold-launch input probes are not certified.",
                    "Run and retain three input probes for this runtime; file presence alone is insufficient.")
    certificate = root / "build/jev/runtime/certification.json"
    if not certificate.is_file() or certificate.stat().st_size > 65536:
        return blocked
    try:
        data = json.loads(certificate.read_text())
        if data["runtime_sha256"] != config.runtime_sha256 or len(data["probes"]) != 3:
            return blocked
        if len({p["run_id"] for p in data["probes"]}) != 3:
            return blocked
        for probe in data["probes"]:
            run_id = probe["run_id"]
            if len(run_id) != 38 or not run_id.startswith("match-") or not all(c in "0123456789abcdef" for c in run_id[6:]):
                return blocked
            run = owned_path(root, str(read_path(root, config.run_root) / run_id))
            summary = run / "summary.json"
            if summary.stat().st_size > 65536 or digest(summary, "sha256") != probe["summary_sha256"]:
                return blocked
            result = json.loads(summary.read_text())
            launch = json.loads((run / "launch.json").read_text())
            if (result["status"] != "probe_verified" or not result["emulator_stopped"] or
                    launch["runtime_sha256"] != config.runtime_sha256 or launch["disc_sha1"] != STOCK_DISC_SHA1):
                return blocked
        return check("runtime_compatibility", "pass", "Three pinned cold-launch input probes verified.",
                        graphical=True, headless_verified=False, cold_launches=3)
    except (KeyError, TypeError, ValueError, OSError):
        return blocked


def toolchain_check(root):
    required = (
        "build/tools/dtk", "build/tools/objdiff-cli", "build/tools/sjiswrap.exe",
        "build/compilers/GC/2.6/mwcceppc.exe", "build/binutils/powerpc-eabi-as",
    )
    missing = sum(not (root / p).is_file() for p in required)
    if missing or not shutil.which("ninja"):
        return check("decomp_tools", "blocked", "Some existing decomp build tools are absent.",
                        "Follow LOCAL_SETUP.md with upstream-pinned tools; preserve the existing build tree.",
                        missing_files=missing)
    return check("decomp_tools", "pass", "Expected tool files and Ninja are present; not executed.",
                    build_verified=False)


def probe_safely(name, function):
    try:
        return function()
    except (OSError, ValueError, RuntimeError):
        return check(name, "blocked", "Probe could not read or inspect the configured resource.",
                        "Check local input permissions and paths; exception details are omitted from public output.")


def diagnose(root: Path, config_path=None, require="all"):
    root = root.resolve()
    checks = []
    workspace_ok = (root / "configure.py").is_file() and (root / "agent/pyproject.toml").is_file()
    checks.append(check("workspace", "pass" if workspace_ok else "fail",
                        "Melee agent workspace found." if workspace_ok else "Expected workspace markers are missing.",
                        "Use --workspace to select the Melee checkout." if not workspace_ok else ""))
    python_ok = sys.version_info[:3] == (3, 13, 12)
    checks.append(check("python", "pass" if python_ok else "blocked",
                        "Pinned Python 3.13.12 is active." if python_ok else "Pinned Python 3.13.12 is not active.",
                        "Run agent/bootstrap.sh using the installed pinned interpreter." if not python_ok else ""))
    try:
        config = load_config(root, config_path)
    except ConfigError as error:
        checks.append(check("config", "fail", str(error), "Correct the local TOML using config.example.toml."))
        return assemble(checks, {"offline": ["workspace", "python", "config"]}, require, None)
    checks.append(check("config", "pass", "Local-only configuration and finite budgets validated."))
    architecture = platform.machine()
    supported = platform.system() == "Darwin" and architecture in ("arm64", "x86_64")
    checks.append(check("host", "pass" if supported else "blocked",
                        "Initial macOS host profile available." if supported else "Live runtime support for this host is not established.",
                        "J03 establishes runtime compatibility; offline development remains available.",
                        architecture=architecture if architecture in ("arm64", "x86_64", "aarch64") else "other"))
    checks.extend([
        probe_safely("stock_dol", lambda: verified_file("stock_dol", read_path(root, config.stock_dol), STOCK_DOL_SHA1)),
        probe_safely("game_assets", lambda: disc_check(root, config)),
        probe_safely("runtime_file", lambda: runtime_check(root, config)),
        probe_safely("runtime_compatibility", lambda: runtime_evidence(root, config)),
        probe_safely("slippi_port", lambda: port_check(config.slippi_port)),
        probe_safely("decomp_tools", lambda: toolchain_check(root)),
        probe_safely("wibo", lambda: verified_file("wibo", root / "build/tools/wibo-1.0.3", WIBO_SHA256, "sha256")),
    ])
    compiler = bool(shutil.which("clang") or shutil.which("cc"))
    checks.append(check("host_compiler", "pass" if compiler else "blocked",
                        "Host compiler is on PATH; not executed." if compiler else "No host C compiler found.",
                        "Install the host compiler before C fixture checks." if not compiler else ""))
    credential = bool(os.environ.get("OPENROUTER_API_KEY", "").strip())
    checks.append(check("jev_credential", "pass" if credential else "blocked",
                        "Provider credential is present; not authenticated." if credential else "Provider credential is absent.",
                        "Load OPENROUTER_API_KEY from agent/.env for J09; never paste it into logs or GitHub." if not credential else ""))
    checks.append(check("jev_access", "blocked", "Provider access and latency have not been measured by J09.",
                        "Run the bounded J09 smoke/benchmark after the adapter exists."))
    capabilities = {
        "offline": ["workspace", "python", "config"],
        "host_tests": ["workspace", "python", "config", "host_compiler"],
        "decomp": ["workspace", "stock_dol", "decomp_tools", "wibo"],
        "live": ["workspace", "python", "config", "host", "stock_dol", "game_assets",
                    "runtime_file", "runtime_compatibility", "slippi_port"],
        "provider": ["python", "config", "jev_credential", "jev_access"],
    }
    return assemble(checks, capabilities, require, config)


def assemble(checks, capabilities, require, config):
    lookup = {item["id"]: item["status"] for item in checks}
    results = {name: {"status": max((lookup[k] for k in keys), key=RANK.get), "checks": keys}
                for name, keys in capabilities.items()}
    # Invalid configuration blocks every requested mode, even if no later probes ran.
    selected = [item["status"] for item in checks] if require == "all" else [
        results.get(require, {"status": "fail"})["status"]]
    status = max(selected, key=RANK.get)
    return {
        "schema_version": 1, "command": "doctor", "required_capability": require,
        "status": status, "exit_code": EXIT[status], "checks": checks, "capabilities": results,
        "policy": {"character": "FOX", "environment": "local", "provider_contacted": False,
                    "emulator_launched": False, "budgets_enforced_by_doctor": False},
        "limits": asdict(config.limits) if config else None,
    }
