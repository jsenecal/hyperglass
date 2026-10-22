"""Tests for the /api/health endpoint."""

# Standard Library
import time

# Third Party
import pytest
from redis.exceptions import RedisError


@pytest.fixture
def ui_built(state, monkeypatch, tmp_path):
    """Point the static path at a directory containing a built UI."""
    (tmp_path / "ui").mkdir()
    (tmp_path / "ui" / "index.html").write_text("<html></html>")
    monkeypatch.setattr(type(state.settings), "static_path", property(lambda _: tmp_path))
    monkeypatch.setattr(state.settings, "disable_ui", False)
    return tmp_path


def test_health_ok(client, ui_built):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"redis": "ok", "ui": "ok"}}


def test_health_fails_when_redis_unreachable(client, ui_built, monkeypatch):
    def unreachable(_):
        raise ConnectionError("Connection refused")

    monkeypatch.setattr("hyperglass.api.routes.ping_redis", unreachable)
    response = client.get("/api/health")
    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "error"
    assert payload["checks"]["redis"] == "error"
    # Failure details are logged, never returned to unauthenticated clients.
    assert "refused" not in response.text


def test_health_fails_when_ui_not_built(client, ui_built):
    (ui_built / "ui" / "index.html").unlink()
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json()["checks"]["ui"] == "error"


def test_health_ignores_ui_when_disabled(client, ui_built, state, monkeypatch):
    (ui_built / "ui" / "index.html").unlink()
    monkeypatch.setattr(state.settings, "disable_ui", True)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["checks"]["ui"] == "disabled"


def test_ping_redis_fails_fast_when_unreachable(monkeypatch):
    # Project
    from hyperglass.api.routes import ping_redis

    # A non-routable address (TEST-NET-1) drops packets, so the connect hangs.
    monkeypatch.setattr("hyperglass.api.routes.HEALTH_REDIS_TIMEOUT", 0.5)

    start = time.monotonic()
    with pytest.raises(RedisError):
        ping_redis("redis://192.0.2.1:6379/0")
    assert time.monotonic() - start < 5
