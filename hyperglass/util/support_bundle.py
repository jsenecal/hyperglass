"""Build a metadata-only support bundle without exporting free-form log text."""

# Standard Library
import json
import math
import platform
import re
import typing as t
import builtins
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

# Project
from hyperglass.constants import __version__
from hyperglass.exceptions import public, private

_ERROR_LEVELS = {"ERROR", "CRITICAL"}
_ERROR_TYPES = {
    value.__name__
    for module in (builtins, public, private)
    for value in vars(module).values()
    if isinstance(value, type) and issubclass(value, BaseException)
}
_QUERY_KINDS = ("bgp_route", "bgp_aspath", "bgp_community", "ping", "traceroute")
_TEXT_RECORD = re.compile(
    r"^\[(?P<level>ERROR|CRITICAL)\] \[(?P<time>\d{8} \d{2}:\d{2}:\d{2})\](?:\s|$)"
)
_LEGACY_RECORD = re.compile(r"^\[(?P<time>\d{8} \d{2}:\d{2}:\d{2})\](?:\s|$)")


def _timestamp(value: t.Any) -> t.Optional[str]:
    """Retain only parsed timestamps, never arbitrary strings from log records."""
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value).isoformat()
    except ValueError:
        return None


def _error_type(value: t.Any) -> str:
    """Export known exception names rather than custom or free-form identifiers."""
    return value if isinstance(value, str) and value in _ERROR_TYPES else "UnknownError"


def _query_kind(value: t.Any) -> str:
    """Reduce built-in directive identifiers to a fixed query kind."""
    if isinstance(value, str):
        for kind in _QUERY_KINDS:
            if value == kind or (
                value.startswith("__hyperglass_")
                and value.endswith((f"_{kind}__", f"_{kind}_table__"))
            ):
                return kind
    return "custom"


def _tail(path: Path, limit: int) -> t.List[str]:
    """Read only the final lines from a log file."""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            return list(deque(handle, maxlen=limit))
    except (OSError, UnicodeError):
        return []


def _json_log_errors(path: Path, limit: int) -> t.List[t.Dict[str, t.Any]]:
    """Keep error levels, timestamps and known types; omit messages and extra data."""
    errors: t.List[t.Dict[str, t.Any]] = []
    for line in _tail(path, limit):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict) or not isinstance(record.get("record"), dict):
            continue
        source = record["record"]
        level_data = source.get("level")
        level = level_data.get("name") if isinstance(level_data, dict) else None
        if isinstance(level, str) and level in _ERROR_LEVELS:
            time_data = source.get("time")
            error_record: t.Dict[str, t.Any] = {
                "timestamp": _timestamp(time_data.get("repr"))
                if isinstance(time_data, dict)
                else None,
                "level": level,
                "message": "[REDACTED]",
            }
            exception = source.get("exception")
            if isinstance(exception, dict):
                error_record["exception"] = {
                    "type": _error_type(exception.get("type")),
                    "value": "[REDACTED]",
                }
            errors.append(error_record)
    return errors


def _text_log_records(
    path: Path, limit: int
) -> t.Tuple[t.List[t.Dict[str, t.Any]], t.List[t.Dict[str, t.Any]]]:
    """Extract error metadata and classify old level-less records as unknown."""
    errors: t.List[t.Dict[str, t.Any]] = []
    legacy: t.List[t.Dict[str, t.Any]] = []
    for line in _tail(path, limit):
        match = _TEXT_RECORD.match(line)
        old_match = _LEGACY_RECORD.match(line) if match is None else None
        timestamp = match or old_match
        if timestamp is None:
            continue
        try:
            parsed_time = datetime.strptime(timestamp["time"], "%Y%m%d %H:%M:%S").isoformat()
        except ValueError:
            continue
        record = {
            "timestamp": parsed_time,
            "level": match["level"] if match else "UNKNOWN",
            "message": "[REDACTED]",
        }
        (errors if match else legacy).append(record)
    return errors, legacy


def _query_failures(path: Path, limit: int) -> t.List[t.Dict[str, t.Any]]:
    """Extract only non-sensitive failure metadata from query samples."""
    failures: t.List[t.Dict[str, t.Any]] = []
    for line in _tail(path, limit):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        error = record.get("error")
        if not error:
            continue
        query = record.get("query")
        runtime = record.get("runtime_s")
        valid_runtime = (
            type(runtime) in (int, float) and 0 <= runtime <= 86400 and math.isfinite(runtime)
        )
        failures.append(
            {
                "timestamp": _timestamp(record.get("timestamp")),
                "query_type": _query_kind(query.get("type") if isinstance(query, dict) else None),
                "structured": record.get("structured") is True,
                "runtime_s": runtime if valid_runtime else None,
                "error": {
                    "type": _error_type(error.get("type") if isinstance(error, dict) else None),
                    "message": "[REDACTED]",
                },
            }
        )
    return failures


def build_support_bundle(
    log_directories: t.Iterable[Path], *, log_lines: int = 200
) -> t.Dict[str, t.Any]:
    """Export only allowlisted metadata without reading configuration or contacting services."""
    bundle: t.Dict[str, t.Any] = {
        "format": 2,
        "redaction": "metadata-only",
        "product": "Hyperglass",
        "version": __version__,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runtime": {
            "python": platform.python_version(),
            "system": platform.system(),
            "release": platform.release(),
        },
        "errors": {"json": [], "text": []},
        "unclassified_text": [],
        "query_failures": [],
    }

    seen: t.Set[Path] = set()
    for directory in log_directories:
        directory = directory.expanduser()
        if directory in seen or not directory.is_dir():
            continue
        seen.add(directory)

        json_log = directory / "hyperglass.log.json"
        text_log = directory / "hyperglass.log"
        samples = directory / "hyperglass_query_log.jsonl"

        if json_log.is_file():
            bundle["errors"]["json"].extend(_json_log_errors(json_log, log_lines))
        if text_log.is_file():
            errors, legacy = _text_log_records(text_log, log_lines)
            bundle["errors"]["text"].extend(errors)
            bundle["unclassified_text"].extend(legacy)
        if samples.is_file():
            bundle["query_failures"].extend(_query_failures(samples, log_lines))

    return bundle


def write_support_bundle(
    output: Path, log_directories: t.Iterable[Path], *, log_lines: int = 200
) -> Path:
    """Write a local support bundle and return its path."""
    output = output.expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(build_support_bundle(log_directories, log_lines=log_lines), indent=2) + "\n",
        encoding="utf-8",
    )
    return output
