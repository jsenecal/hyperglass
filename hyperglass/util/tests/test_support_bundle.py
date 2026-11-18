"""Tests for local support bundle generation."""

# Standard Library
import json

# Third Party
import pytest
from typer.testing import CliRunner

# Project
from hyperglass.cli import cli
from hyperglass.log import log, _FMT_FILE
from hyperglass.util.support_bundle import build_support_bundle, write_support_bundle


def test_support_bundle_only_includes_sanitized_query_failures(tmp_path):
    """Query samples must not expose targets, devices, raw output, or parsed output."""
    sample = {
        "timestamp": "2026-08-26T10:00:00+00:00",
        "device": {"id": "router-1", "name": "Production Router", "address": "192.0.2.1"},
        "query": {"type": "ping", "target": "198.51.100.5", "location": "Johannesburg"},
        "structured": False,
        "runtime_s": 1.25,
        "error": {"type": "DeviceTimeout", "message": "Timed out connecting to 192.0.2.1"},
        "raw": "private device output",
        "parsed": {"private": "route data"},
    }
    (tmp_path / "hyperglass_query_log.jsonl").write_text(json.dumps(sample) + "\n")

    bundle = build_support_bundle([tmp_path])
    failure = bundle["query_failures"][0]

    assert failure == {
        "timestamp": "2026-08-26T10:00:00+00:00",
        "query_type": "ping",
        "structured": False,
        "runtime_s": 1.25,
        "error": {"type": "DeviceTimeout", "message": "[REDACTED]"},
    }
    assert "Production Router" not in json.dumps(bundle)
    assert "private device output" not in json.dumps(bundle)
    assert "route data" not in json.dumps(bundle)


def test_support_bundle_redacts_json_log_secrets_and_addresses(tmp_path):
    """Structured errors retain metadata without copying message or extra fields."""
    record = {
        "record": {
            "level": {"name": "ERROR"},
            "file": {"name": "/srv/private/source.py"},
            "message": "Request failed for 192.0.2.10",
            "extra": {"password": "do-not-share", "target": "192.0.2.20"},
        }
    }
    (tmp_path / "hyperglass.log.json").write_text(json.dumps(record) + "\n")

    bundle = build_support_bundle([tmp_path])
    serialized = json.dumps(bundle)

    assert "do-not-share" not in serialized
    assert "192.0.2.10" not in serialized
    assert "192.0.2.20" not in serialized
    assert "/srv/private/source.py" not in serialized
    assert bundle["redaction"] == "metadata-only"
    assert bundle["errors"]["json"][0]["message"] == "[REDACTED]"


def test_write_support_bundle_creates_local_json(tmp_path):
    """The command writes a JSON file and does not require application state."""
    output = tmp_path / "nested" / "support.json"

    result = write_support_bundle(output, [tmp_path])

    assert result == output
    assert json.loads(output.read_text())["product"] == "Hyperglass"


@pytest.mark.parametrize(
    "private_text",
    [
        "2001:db8::10",
        "2001:db8:1:2:3:4:5:6",
        "[fe80::1%eth0]:22",
        "::ffff:192.0.2.10",
        "192.0.2.10.",
        "router.internal.example",
        "edge01",
        "Production Router West",
        "reader-alice",
        "ssh://alice:secret-ssh@router.internal.example:22/",
        "sftp://alice:secret-sftp@router.internal.example/",
        "redis://alice:secret-redis@cache.internal.example:6379/0",
        "postgresql://alice:secret-db@db.internal.example/app",
        "https://alice:secret-http@router.internal.example/",
        "password=secret-password",
        'token="secret-token with spaces"',
        "Bearer secret-bearer",
    ],
)
def test_bundle_omits_free_form_identifiers_and_credentials(tmp_path, private_text):
    """All log sources omit arbitrary identifiers, not just recognizable address syntax."""
    record = {
        "record": {
            "level": {"name": "ERROR"},
            "time": {"repr": "2026-08-26T10:00:00+00:00"},
            "message": private_text,
            "exception": {"type": "ValueError", "value": private_text},
            "extra": {private_text: private_text},
        }
    }
    (tmp_path / "hyperglass.log.json").write_text(json.dumps(record) + "\n")
    (tmp_path / "hyperglass.log").write_text(
        f"[ERROR] [20260826 10:00:00] {private_text}\n"
        f"[20260826 10:00:01] {private_text}\n"
    )
    sample = {
        "timestamp": "2026-08-26T10:00:00+00:00",
        "query": {"type": "ping", "target": private_text, "location": private_text},
        "device": {"name": private_text, "username": private_text},
        "error": {"type": "DeviceTimeout", "message": private_text, private_text: private_text},
        "raw": private_text,
        "parsed": private_text,
    }
    (tmp_path / "hyperglass_query_log.jsonl").write_text(json.dumps(sample) + "\n")

    bundle = build_support_bundle([tmp_path])

    assert private_text not in json.dumps(bundle)
    assert bundle["errors"]["json"][0]["exception"]["type"] == "ValueError"
    assert bundle["errors"]["text"][0]["level"] == "ERROR"
    assert bundle["unclassified_text"][0]["level"] == "UNKNOWN"
    assert bundle["query_failures"][0]["error"]["type"] == "DeviceTimeout"


def test_default_file_format_retains_error_levels(tmp_path):
    """Replay the actual file format rather than assuming stdout's level tags."""
    handler = log.add(tmp_path / "hyperglass.log", format=_FMT_FILE, enqueue=False)
    try:
        log.info("ordinary private message")
        log.error("private error message")
        log.critical("private critical message")
    finally:
        log.remove(handler)

    bundle = build_support_bundle([tmp_path])

    assert [entry["level"] for entry in bundle["errors"]["text"]] == ["ERROR", "CRITICAL"]
    assert all(entry["timestamp"] for entry in bundle["errors"]["text"])
    assert bundle["unclassified_text"] == []
    assert "private" not in json.dumps(bundle)


def test_legacy_text_logs_are_unclassified_not_silently_empty(tmp_path):
    """Old file logs have no level, so report metadata without guessing severity."""
    (tmp_path / "hyperglass.log").write_text(
        "# hyperglass log header\n"
        "[20260826 10:00:00] router.internal.example failed as alice\n"
        "[20260826 10:00:01] token=private-value\n"
        "[20269999 99:99:99] invalid timestamp\n"
    )
    bundle = build_support_bundle([tmp_path])
    assert bundle["errors"]["text"] == []
    assert len(bundle["unclassified_text"]) == 2
    assert bundle["unclassified_text"][0] == {
        "timestamp": "2026-08-26T10:00:00",
        "level": "UNKNOWN",
        "message": "[REDACTED]",
    }
    assert "private-value" not in json.dumps(bundle)


def test_bundle_validates_all_exported_sample_fields(tmp_path):
    """Custom IDs and malformed metadata must not bypass the message omission policy."""
    private_value = "router.private.example/alice/token=private"
    sample = {
        "timestamp": private_value,
        "query": {"type": private_value},
        "structured": private_value,
        "runtime_s": private_value,
        "error": {"type": private_value, "message": private_value},
    }
    path = tmp_path / "hyperglass_query_log.jsonl"
    path.write_text(json.dumps(sample) + "\n[]\nnull\ninvalid JSON\n")

    bundle = build_support_bundle([tmp_path])

    assert bundle["query_failures"] == [
        {
            "timestamp": None,
            "query_type": "custom",
            "structured": False,
            "runtime_s": None,
            "error": {"type": "UnknownError", "message": "[REDACTED]"},
        }
    ]
    assert private_value not in json.dumps(bundle)


@pytest.mark.parametrize(
    "query_type,expected",
    [
        ("ping", "ping"),
        ("__hyperglass_cisco_ios_bgp_route_table__", "bgp_route"),
        ("__hyperglass_frr_bgp_community__", "bgp_community"),
        ("private-router-query", "custom"),
    ],
)
def test_bundle_exports_fixed_query_kinds(tmp_path, query_type, expected):
    sample = {"query": {"type": query_type}, "error": {"type": "ValueError"}}
    (tmp_path / "hyperglass_query_log.jsonl").write_text(json.dumps(sample) + "\n")
    assert build_support_bundle([tmp_path])["query_failures"][0]["query_type"] == expected


def test_support_bundle_uses_hyperglass_default_filename(tmp_path, monkeypatch):
    """The default command output retains the Hyperglass product name."""
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(cli, ["support-bundle", "--log-directory", str(tmp_path)])
    assert result.exit_code == 0, result.output
    output = tmp_path / "hyperglass-support-bundle.json"
    assert output.is_file()
    assert json.loads(output.read_text())["redaction"] == "metadata-only"
    assert not (tmp_path / "ultraglass-support-bundle.json").exists()
