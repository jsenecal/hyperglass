"""Tests for share-related routes."""

# Standard Library
import re

# Third Party
import pytest


@pytest.fixture
def params() -> dict:
    # fake_output enables routes to return without hitting real devices.
    return {"fake_output": True}


def _seed_query(client) -> str:
    """Run a query and return the cache_id."""
    r = client.post("/api/query", json={
        "queryLocation": "test1",
        "queryTarget": "192.0.2.0/24",
        "queryType": "juniper_bgp_route",
    })
    assert r.status_code == 201
    return r.json()["id"]


def test_share_create_returns_opaque_id(client):
    cache_id = _seed_query(client)
    r = client.post(f"/api/query/share/{cache_id}")
    assert r.status_code in (200, 201)
    body = r.json()
    assert "id" in body
    # 11-char URL-safe base64
    assert re.fullmatch(r"[A-Za-z0-9_-]{11}", body["id"])
    assert body["url"].endswith(f"/result/{body['id']}")


def test_share_create_410_when_cache_expired(client, state):
    cache_id = _seed_query(client)
    digest = cache_id.removeprefix("hyperglass.query.")
    # state.redis.delete() applies the namespace prefix via _key_join.
    state.redis.delete(f"hyperglass.query.{digest}")

    r = client.post(f"/api/query/share/{cache_id}")
    assert r.status_code == 410


class TestShareDisabled:
    """Verify the disabled-feature kill switch.

    Overrides the module-level ``params`` fixture so ``share_enabled`` is False.
    """

    @pytest.fixture
    def params(self) -> dict:
        """Return params with sharing disabled."""
        return {"fake_output": True, "cache": {"share_enabled": False}}

    def test_share_create_404(self, client):
        """Return 404 when sharing is disabled, even without a cache entry."""
        # The disabled gate fires before any cache lookup.
        r = client.post("/api/query/share/hyperglass.query.deadbeef")
        assert r.status_code == 404
