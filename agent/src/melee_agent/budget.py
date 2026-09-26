"""Append-only, cross-process reservations for a bounded provider experiment.

A lost response keeps its entire reservation. A corrupt or incomplete journal
fails closed; restart never resets spend. All dollar values use integer nano-USD.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_CEILING
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import uuid

from .config import owned_path

NANO_USD = 1_000_000_000


class BudgetError(ValueError):
    """Public-safe refusal; never includes request payloads or credentials."""


def cost_units(value):
    if type(value) not in (str, int, float):
        raise BudgetError("Invalid provider cost")
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0 or amount > 1000:
            raise BudgetError("Invalid provider cost")
        return int((amount * NANO_USD).to_integral_value(rounding=ROUND_CEILING))
    except InvalidOperation:
        raise BudgetError("Invalid provider cost") from None


def positive_int(value):
    return type(value) is int and value > 0


def require(condition):
    if not condition:
        raise BudgetError("Budget journal is invalid")


class SpendLedger:
    def __init__(self, path: Path):
        self.path = path

    @classmethod
    def create(cls, root, directory, *, deadline_utc, limit_usd="1", max_requests=600,
                max_input_tokens=1_000_000):
        folder = owned_path(root.resolve(), directory)
        folder.mkdir(parents=True, exist_ok=True)
        deadline = datetime.fromisoformat(deadline_utc)
        if deadline.tzinfo is None:
            raise BudgetError("Budget deadline must include timezone")
        limit = cost_units(limit_usd)
        if not 0 < limit <= NANO_USD or not positive_int(max_requests) or not positive_int(max_input_tokens):
            raise BudgetError("Invalid experiment limits")
        header = {"kind": "budget", "schema_version": 1, "limit_nano_usd": limit,
                    "deadline_utc": deadline.astimezone(timezone.utc).isoformat(),
                    "max_requests": max_requests, "max_input_tokens": max_input_tokens}
        ledger = cls(folder / "spend.jsonl")
        try:
            fd = os.open(ledger.path, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            created = False
        else:
            os.close(fd)
            created = True
        with ledger._locked() as handle:
            records = ledger._read(handle)
            if records:
                if records[0] != header:
                    raise BudgetError("Existing budget cannot be reconfigured")
                ledger._state(records)
            else:
                if not created:
                    raise BudgetError("Existing budget journal is empty")
                ledger._append(handle, header)
        return ledger

    @contextmanager
    def _locked(self):
        fd = os.open(self.path, os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "r+b", buffering=0) as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                raise BudgetError("Budget journal must be a regular file")
            fcntl.flock(handle, fcntl.LOCK_EX)
            yield handle

    @staticmethod
    def _read(handle):
        handle.seek(0)
        raw = handle.read(8_000_001)
        if len(raw) > 8_000_000 or (raw and not raw.endswith(b"\n")):
            raise BudgetError("Budget journal is incomplete or too large")
        try:
            return [json.loads(line) for line in raw.splitlines()]
        except (ValueError, UnicodeError):
            raise BudgetError("Budget journal is corrupt") from None

    @staticmethod
    def _append(handle, value):
        raw = (json.dumps(value, sort_keys=True, allow_nan=False) + "\n").encode()
        handle.seek(0, os.SEEK_END)
        while raw:
            count = handle.write(raw)
            if not count:
                raise BudgetError("Budget journal write failed")
            raw = raw[count:]
        os.fsync(handle.fileno())

    @staticmethod
    def _state(records):
        try:
            header = records[0]
            require(set(header) == {"kind", "schema_version", "limit_nano_usd", "deadline_utc", "max_requests", "max_input_tokens"})
            require(header["kind"] == "budget" and type(header["schema_version"]) is int and header["schema_version"] == 1)
            require(all(positive_int(header[k]) for k in ("limit_nano_usd", "max_requests", "max_input_tokens")))
            require(header["limit_nano_usd"] <= NANO_USD)
            deadline = datetime.fromisoformat(header["deadline_utc"])
            require(deadline.tzinfo is not None)
            reservations, settled = {}, {}
            seal = None
            for index, row in enumerate(records[1:], 1):
                if row["kind"] == "reserve":
                    require(set(row) == {"kind", "id", "cost_nano_usd", "input_tokens", "payload_sha256"})
                    require(row["id"] not in reservations and type(row["id"]) is str)
                    require(positive_int(row["cost_nano_usd"]) and positive_int(row["input_tokens"]))
                    require(type(row["payload_sha256"]) is str and len(row["payload_sha256"]) == 64)
                    reservations[row["id"]] = row
                elif row["kind"] == "seal":
                    require(index == len(records)-1)
                    require(set(row) == {"kind", "directory", "deadline_utc", "limit_nano_usd", "max_requests", "max_input_tokens"})
                    directory = row["directory"]
                    require(type(directory) is str and len(directory) <= 512 and directory.startswith("build/jev/"))
                    require(all(part not in ("", ".", "..") for part in directory.split("/")))
                    child_header = {key: value for key, value in row.items() if key not in ("kind", "directory")}
                    SpendLedger._state([{**child_header, "kind": "budget", "schema_version": 1}])
                    seal = row
                else:
                    require(row["kind"] == "settle")
                    require(set(row) == {"kind", "id", "cost_nano_usd", "input_tokens"})
                    require(row["id"] in reservations and row["id"] not in settled)
                    require(type(row["cost_nano_usd"]) is int and row["cost_nano_usd"] >= 0)
                    require(type(row["input_tokens"]) is int and row["input_tokens"] >= 0)
                    settled[row["id"]] = row
            rows = [settled.get(key, value) for key, value in reservations.items()]
            # An unexpected provider charge above a reservation permanently blocks more calls.
            overrun = any(row["cost_nano_usd"] > reservations[key]["cost_nano_usd"] or
                            row["input_tokens"] > reservations[key]["input_tokens"] for key, row in settled.items())
            cost = sum(r["cost_nano_usd"] for r in rows)
            if seal is not None:
                require(not overrun and seal["limit_nano_usd"] == header["limit_nano_usd"]-cost)
            return header, reservations, settled, cost, sum(r["input_tokens"] for r in rows), overrun
        except (AssertionError, KeyError, IndexError, TypeError, ValueError):
            raise BudgetError("Budget journal is invalid") from None

    def reserve(self, *, cost_nano_usd, input_tokens, payload_sha256):
        if not positive_int(cost_nano_usd) or not positive_int(input_tokens):
            raise BudgetError("Invalid reservation")
        if type(payload_sha256) is not str or len(payload_sha256) != 64 or any(c not in "0123456789abcdef" for c in payload_sha256):
            raise BudgetError("Invalid payload digest")
        with self._locked() as handle:
            records = self._read(handle)
            header, reserved, _, cost, tokens, overrun = self._state(records)
            if records[-1]["kind"] == "seal":
                raise BudgetError("Experiment budget is sealed")
            if datetime.now(timezone.utc) >= datetime.fromisoformat(header["deadline_utc"]):
                raise BudgetError("Experiment deadline reached")
            if (overrun or len(reserved) >= header["max_requests"] or cost + cost_nano_usd > header["limit_nano_usd"] or
                    tokens + input_tokens > header["max_input_tokens"]):
                raise BudgetError("Experiment budget exhausted")
            request_id = uuid.uuid4().hex
            self._append(handle, {"kind": "reserve", "id": request_id, "cost_nano_usd": cost_nano_usd,
                                    "input_tokens": input_tokens, "payload_sha256": payload_sha256})
            return request_id

    def settle(self, request_id, *, cost_usd, input_tokens):
        cost = cost_units(cost_usd)
        if type(input_tokens) is not int or input_tokens < 0:
            raise BudgetError("Invalid provider token usage")
        with self._locked() as handle:
            records = self._read(handle)
            _, reserved, settled, _, _, _ = self._state(records)
            if records[-1]["kind"] == "seal":
                raise BudgetError("Experiment budget is sealed")
            if request_id not in reserved or request_id in settled:
                raise BudgetError("Unknown or already settled reservation")
            self._append(handle, {"kind": "settle", "id": request_id, "cost_nano_usd": cost, "input_tokens": input_tokens})

    def report(self):
        with self._locked() as handle:
            records = self._read(handle)
            header, reserved, settled, cost, tokens, overrun = self._state(records)
        return {**header, "requests": len(reserved), "unsettled_requests": len(reserved) - len(settled),
                "accounted_nano_usd": cost, "reported_nano_usd": sum(r["cost_nano_usd"] for r in settled.values()),
                "accounted_input_tokens": tokens, "reservation_exceeded": overrun,
                **({"sealed": True, "continuation": records[-1]} if records[-1]["kind"] == "seal" else {})}

    @classmethod
    def continue_experiment(cls, root, parent_directory, directory, *, deadline_utc, max_requests, max_input_tokens):
        """Seal one parent and assign its unspent money to exactly one child.

        Call after provider workers stop. Unknown charges stay fully reserved;
        even late settlements cannot refund a sealed parent's accounting.
        Identical retries reuse an existing child without resetting it. An
        interrupted initialization with no child journal fails closed.
        """
        root = root.resolve()
        parent_folder = owned_path(root, parent_directory)
        child_folder = owned_path(root, directory)
        if parent_folder == child_folder:
            raise BudgetError("Continuation requires a separate directory")
        deadline = datetime.fromisoformat(deadline_utc)
        if (deadline.tzinfo is None or deadline <= datetime.now(timezone.utc) or
                not positive_int(max_requests) or not positive_int(max_input_tokens)):
            raise BudgetError("Invalid continuation bounds")
        parent = cls(parent_folder/"spend.jsonl")
        with parent._locked() as handle:
            records = parent._read(handle)
            header, _, _, cost, _, overrun = parent._state(records)
            remaining = header["limit_nano_usd"]-cost
            if overrun or remaining <= 0:
                raise BudgetError("No conservatively unspent budget")
            seal = {"kind": "seal", "directory": str(child_folder.relative_to(root)),
                "deadline_utc": deadline.astimezone(timezone.utc).isoformat(), "limit_nano_usd": remaining,
                "max_requests": max_requests, "max_input_tokens": max_input_tokens}
            if records[-1]["kind"] == "seal":
                if records[-1] != seal:
                    raise BudgetError("Sealed continuation cannot be reconfigured")
                if not (child_folder/"spend.jsonl").is_file():
                    raise BudgetError("Sealed continuation journal is missing")
            else:
                if child_folder.exists():
                    raise BudgetError("Continuation directory already exists")
                parent._state([*records, seal])
                parent._append(handle, seal)
            # Keep the parent lock until child initialization completes. A
            # competing caller cannot authorize a second destination.
            child = cls.create(root, seal["directory"], deadline_utc=seal["deadline_utc"],
                limit_usd=str(Decimal(remaining)/NANO_USD), max_requests=max_requests, max_input_tokens=max_input_tokens)
            handle.seek(0)
            funding = {"schema_version": 1, "parent_ledger": str(parent.path.relative_to(root)),
                "parent_sha256": hashlib.sha256(handle.read()).hexdigest(),
                "parent_limit_nano_usd": header["limit_nano_usd"], "parent_accounted_nano_usd": cost,
                "child_limit_nano_usd": remaining, "parent_sealed": True}
            provenance = child_folder/"funding.json"
            try:
                fd = os.open(provenance, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            except FileExistsError:
                if provenance.is_symlink() or provenance.stat().st_size > 65536 or json.loads(provenance.read_text()) != funding:
                    raise BudgetError("Continuation funding provenance mismatch")
            else:
                with os.fdopen(fd, "w") as output:
                    output.write(json.dumps(funding, sort_keys=True)+"\n")
                    output.flush()
                    os.fsync(output.fileno())
        return child
