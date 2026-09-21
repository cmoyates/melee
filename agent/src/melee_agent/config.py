"""Strict local configuration; public diagnostics never interpolate user values."""

from dataclasses import dataclass, field
import math
from pathlib import Path
import re
import tomllib


class ConfigError(ValueError):
    """A deliberately public-safe error message."""


@dataclass(frozen=True)
class Limits:
    max_run_seconds: int = 120
    max_requests: int = 600
    max_input_tokens: int = 1_000_000
    max_cost_usd: float = 1.0
    max_artifact_bytes: int = 268_435_456


@dataclass(frozen=True)
class Config:
    stock_dol: str = "orig/GALE01/sys/main.dol"
    disc_image: str = ""
    runtime: str = ""
    runtime_sha256: str = ""
    run_root: str = "build/jev/runs"
    slippi_port: int = 51441
    limits: Limits = field(default_factory=Limits)


def read_path(root: Path, value: str) -> Path:
    """Explicit input assets may be outside the workspace; they are read only."""
    path = Path(value).expanduser()
    return path if path.is_absolute() else root / path


def owned_path(root: Path, value: str) -> Path:
    """Future outputs stay inside build/jev, including through existing symlinks."""
    base = root / "build" / "jev"
    target = read_path(root, value).resolve()
    if base.resolve() != base or not target.is_relative_to(base) or target == base:
        raise ConfigError("Run storage must be below workspace build/jev without escaping symlinks.")
    if target.exists() and not target.is_dir():
        raise ConfigError("Run storage must be a directory.")
    return target


def load_config(root: Path, path: Path | None = None) -> Config:
    explicit = path is not None
    path = path or root / "agent" / "local.toml"
    if not path.is_absolute():
        path = root / path
    try:
        if not path.resolve().is_relative_to(root):
            raise ConfigError("Configuration must remain inside the workspace.")
        if not path.exists() and not explicit:
            data = {}
        else:
            if not path.is_file() or path.stat().st_size > 65536:
                raise ConfigError("Configuration is missing, not a file, or exceeds 64 KiB.")
            data = tomllib.loads(path.read_text(encoding="utf-8"))
    except ConfigError:
        raise
    except (OSError, UnicodeError, ValueError, RuntimeError):
        raise ConfigError("Cannot read valid local TOML configuration.") from None

    allowed = {"paths", "execution", "limits"}
    if set(data) - allowed:
        raise ConfigError("Unknown configuration section; credentials belong in the environment.")
    for section in allowed:
        if not isinstance(data.get(section, {}), dict):
            raise ConfigError("Configuration sections must be tables.")
    paths = data.get("paths", {})
    execution = data.get("execution", {})
    limits = data.get("limits", {})
    if set(paths) - {"stock_dol", "disc_image", "runtime", "runtime_sha256"}:
        raise ConfigError("Unknown paths setting.")
    if set(execution) - {"environment", "run_root", "slippi_port"}:
        raise ConfigError("Unknown execution setting.")
    if execution.get("environment", "local") != "local":
        raise ConfigError("Only local offline matches are supported.")
    if set(limits) - set(Limits.__dataclass_fields__):
        raise ConfigError("Unknown budget setting.")
    for name, value in limits.items():
        expected = (int, float) if name == "max_cost_usd" else (int,)
        if (type(value) not in expected or value <= 0 or
                (type(value) is float and not math.isfinite(value))):
            raise ConfigError("All budgets must be finite positive numbers; counts must be integers.")
    values = dict(paths)
    values.update({k: v for k, v in execution.items() if k != "environment"})
    for name in ("stock_dol", "disc_image", "runtime", "runtime_sha256", "run_root"):
        if name in values and (not isinstance(values[name], str) or "\x00" in values[name]):
            raise ConfigError("Path and digest settings must be strings without NUL characters.")
    for name in ("stock_dol", "run_root"):
        if name in values and not values[name].strip():
            raise ConfigError("Stock executable and run storage paths cannot be empty.")
    port = values.get("slippi_port", 51441)
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ConfigError("Slippi port must be an integer between 1024 and 65535.")
    digest = values.get("runtime_sha256", "")
    if digest and not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ConfigError("Runtime SHA-256 must be 64 lowercase hexadecimal characters.")
    config = Config(**values, limits=Limits(**limits))
    try:
        owned_path(root, config.run_root)
    except (OSError, RuntimeError, ValueError) as error:
        if isinstance(error, ConfigError):
            raise
        raise ConfigError("Cannot validate owned run storage.") from None
    return config
