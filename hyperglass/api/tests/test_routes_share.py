"""Tests for share-related routes."""

# Standard Library
import re
from datetime import datetime

# Third Party
import pytest


@pytest.fixture
def params() -> dict:
    # fake_output enables routes to return without hitting real devices.
    return {"fake_output": True}


def _seed_query(client) -> str:
    """Run a query and return the cache_id."""
    r = client.post(
        "/api/query",
        json={
            "queryLocation": "test1",
            "queryTarget": "192.0.2.0/24",
            "queryType": "juniper_bgp_route",
        },
    )
    assert r.status_code == 201
    return r.json()["id"]


def test_share_create_returns_opaque_id(client):
    cache_id = _seed_query(client)
    r = client.post(f"/api/query/share/{cache_id}")
    assert r.status_code == 201
    body = r.json()
    assert "id" in body
    # 11-char URL-safe base64
    assert re.fullmatch(r"[A-Za-z0-9_-]{11}", body["id"])
    assert body["url"].endswith(f"/result/{body['id']}")
    assert "expiresAt" in body
    datetime.fromisoformat(body["expiresAt"].replace("Z", "+00:00"))


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

    def test_share_get_404(self, client):
        """GET also 404s when sharing is disabled."""
        r = client.get("/api/query/share/AAAAAAAAAAA")
        assert r.status_code == 404


def test_share_get_returns_full_snapshot(client):
    cache_id = _seed_query(client)
    create_resp = client.post(f"/api/query/share/{cache_id}").json()

    r = client.get(f"/api/query/share/{create_resp['id']}")
    assert r.status_code == 200
    body = r.json()
    assert body["shared"] is True
    # The model's own fields are aliased to camelCase. Keys inside the
    # nested `query` dict are NOT aliased (generic dict). They stay snake_case.
    assert body["query"]["query_location"] == "test1"
    assert body["queryLabels"]["type"] == "BGP Route"
    assert "createdAt" in body
    assert "expiresAt" in body


def test_share_get_404_when_missing(client):
    r = client.get("/api/query/share/nonexistent1")
    assert r.status_code == 404


class TestShareSliding:
    """GET extends the share TTL when share_sliding is enabled."""

    @pytest.fixture
    def params(self) -> dict:
        """Enable sliding TTL with a short share timeout."""
        return {
            "fake_output": True,
            "cache": {"share_sliding": True, "share_timeout": 600},
        }

    def test_get_resets_ttl(self, client, state):
        """A GET on a share must extend its TTL back toward share_timeout."""
        cache_id = _seed_query(client)
        share_id = client.post(f"/api/query/share/{cache_id}").json()["id"]
        share_key = f"hyperglass.share.{share_id}"
        full_key = state.redis.key(share_key)

        # Manually shorten the TTL to verify GET extends it back.
        # RedisManager.expire is keyword-only; use the underlying redis-py
        # client (state.redis.instance) for raw operations not in the
        # manager's API.
        state.redis.instance.expire(full_key, 60)
        r = client.get(f"/api/query/share/{share_id}")
        assert r.status_code == 200

        ttl = state.redis.instance.ttl(full_key)
        assert ttl > 60  # extended back toward share_timeout


class TestShareFixed:
    """GET must NOT extend the share TTL when share_sliding is disabled."""

    @pytest.fixture
    def params(self) -> dict:
        """Disable sliding TTL with a short share timeout."""
        return {
            "fake_output": True,
            "cache": {"share_sliding": False, "share_timeout": 600},
        }

    def test_get_does_not_extend_ttl(self, client, state):
        """A GET on a share must leave its TTL untouched."""
        cache_id = _seed_query(client)
        share_id = client.post(f"/api/query/share/{cache_id}").json()["id"]
        full_key = state.redis.key(f"hyperglass.share.{share_id}")

        state.redis.instance.expire(full_key, 60)
        client.get(f"/api/query/share/{share_id}")
        ttl = state.redis.instance.ttl(full_key)
        assert ttl <= 60  # not extended
