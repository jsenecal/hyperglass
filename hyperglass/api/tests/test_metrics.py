"""Tests for Prometheus metrics."""

# Standard Library
import os
import typing as t

# Third Party
import pytest
from litestar.testing import TestClient
from prometheus_client import REGISTRY

# Project
from hyperglass.main import prepare_metrics_dir
from hyperglass.api.metrics import UNKNOWN, error_reason
from hyperglass.exceptions.public import AuthError, DeviceTimeout, QueryLocationNotFound

QUERY = {
    "queryLocation": "test1",
    "queryTarget": "192.0.2.0/24",
    "queryType": "juniper_bgp_route",
}


def sample(name: str, **labels: str) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


@pytest.fixture
def params() -> dict:
    return {"fake_output": True, "metrics": {"enable": True}}


@pytest.fixture
def metrics_client(state) -> t.Generator[TestClient, None, None]:
    """Client for an app built with metrics enabled.

    `hyperglass.api.app` is built once, at first import, from whatever state
    exists then, so build a fresh app from this module's state instead.
    """
    # Project
    from hyperglass.api import create_app

    with TestClient(app=create_app()) as test_client:
        yield test_client


def test_metrics_endpoint_exposes_hyperglass_metrics(metrics_client):
    response = metrics_client.get("/metrics")
    assert response.status_code == 200
    assert "hyperglass_build_info" in response.text
    assert "hyperglass_queries_total" in response.text


def test_metrics_disabled_by_default(client):
    response = client.get("/metrics")
    assert response.status_code == 404


def test_successful_query_counted(metrics_client):
    labels = {"device": "test1", "query_type": "juniper_bgp_route"}
    before = sample("hyperglass_queries_total", **labels, status="success")
    durations = sample("hyperglass_query_duration_seconds_count", **labels)
    hits = sample("hyperglass_query_cache_total", result="hit")

    payload = {**QUERY, "queryTarget": "198.51.100.0/24"}
    assert metrics_client.post("/api/query", json=payload).status_code == 201
    assert metrics_client.post("/api/query", json=payload).status_code == 201

    assert sample("hyperglass_queries_total", **labels, status="success") == before + 2
    # Only the first (uncached) query is executed against the device.
    assert sample("hyperglass_query_duration_seconds_count", **labels) == durations + 1
    assert sample("hyperglass_query_cache_total", result="hit") == hits + 1


class TestDeviceFailures:
    """Failures raised while executing a query against a device."""

    @pytest.fixture
    def params(self) -> dict:
        """Execute against the (patched) device driver rather than fake output."""
        return {"fake_output": False, "metrics": {"enable": True}}

    @pytest.mark.parametrize(
        ("error", "reason"),
        [
            (
                lambda q: DeviceTimeout(error=TimeoutError("timed out"), device=q.device),
                "device_timeout",
            ),
            (lambda q: AuthError(error=PermissionError("denied"), device=q.device), "auth_error"),
            (lambda q: RuntimeError("boom"), "internal_error"),
        ],
    )
    def test_counted_with_reason(self, metrics_client, monkeypatch, error, reason):
        """Device failures are attributed to the device, with the failure reason."""

        async def fail(query):
            raise error(query)

        monkeypatch.setattr("hyperglass.api.routes.execute", fail)
        labels = {"device": "test1", "query_type": "juniper_bgp_route"}
        before = sample("hyperglass_query_errors_total", **labels, reason=reason)
        errors = sample("hyperglass_queries_total", **labels, status="error")

        payload = {**QUERY, "queryTarget": "203.0.113.0/24"}
        response = metrics_client.post("/api/query", json=payload)

        assert response.status_code >= 400
        assert sample("hyperglass_query_errors_total", **labels, reason=reason) == before + 1
        assert sample("hyperglass_queries_total", **labels, status="error") == errors + 1


def test_invalid_location_counted_without_untrusted_labels(metrics_client):
    labels = {"device": UNKNOWN, "query_type": UNKNOWN}
    reason = "query_location_not_found"
    before = sample("hyperglass_query_errors_total", **labels, reason=reason)

    response = metrics_client.post("/api/query", json={**QUERY, "queryLocation": "attacker-chosen"})

    assert response.status_code >= 400
    assert sample("hyperglass_query_errors_total", **labels, reason=reason) == before + 1
    assert "attacker-chosen" not in metrics_client.get("/metrics").text


def test_malformed_request_counted(metrics_client):
    labels = {"device": UNKNOWN, "query_type": UNKNOWN, "reason": "invalid_request"}
    before = sample("hyperglass_query_errors_total", **labels)

    # Note: validation_handler currently responds 200 to validation failures,
    # so only the metric is asserted here.
    metrics_client.post("/api/query", json={"queryTarget": "192.0.2.0/24"})

    assert sample("hyperglass_query_errors_total", **labels) == before + 1


def test_non_query_errors_not_counted(metrics_client):
    before = sample("hyperglass_queries_total", device=UNKNOWN, query_type=UNKNOWN, status="error")
    assert metrics_client.get("/api/devices/nonexistent").status_code >= 400
    after = sample("hyperglass_queries_total", device=UNKNOWN, query_type=UNKNOWN, status="error")
    assert after == before


def test_http_metrics_group_paths(metrics_client):
    metrics_client.get("/api/devices/test1")
    text = metrics_client.get("/metrics").text
    assert 'path="/api/devices/{id}"' in text
    assert 'path="/api/devices/test1"' not in text


def test_error_reason_is_snake_case_class_name():
    assert error_reason(QueryLocationNotFound(location="x")) == "query_location_not_found"


def test_prepare_metrics_dir_creates_temporary_dir(monkeypatch):
    monkeypatch.delenv("PROMETHEUS_MULTIPROC_DIR", raising=False)
    path = prepare_metrics_dir()
    assert path.is_dir()
    assert os.environ["PROMETHEUS_MULTIPROC_DIR"] == str(path)


def test_prepare_metrics_dir_clears_stale_values(monkeypatch, tmp_path):
    (tmp_path / "counter_1234.db").write_bytes(b"stale")
    (tmp_path / "keep.txt").write_text("not ours")
    monkeypatch.setenv("PROMETHEUS_MULTIPROC_DIR", str(tmp_path))

    assert prepare_metrics_dir() == tmp_path
    assert not (tmp_path / "counter_1234.db").exists()
    assert (tmp_path / "keep.txt").exists()
