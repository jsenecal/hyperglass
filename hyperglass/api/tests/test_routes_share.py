"""Tests for share-related routes."""

# Standard Library
import re
from pathlib import Path
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


class TestShareViewHtml:
    """GET /result/<share_id> serves the SPA shell when index.html is present.

    Also verifies that invalid-format IDs are rejected with 404.
    """

    @pytest.fixture
    def index_html(self):
        """Ensure a minimal exported index.html exists for the share-view handler.

        The real file is a build artifact (`task ui-build`) that isn't present in
        a bare checkout, so synthesize a placeholder and clean it up afterward.
        Avoids skipping the serving tests in CI/local runs without a UI build.
        """
        index = Path(__file__).parent.parent.parent / "static" / "ui" / "index.html"
        created = False
        if not index.exists():
            index.parent.mkdir(parents=True, exist_ok=True)
            index.write_text("<!doctype html><title>hyperglass</title>")
            created = True
        try:
            yield index
        finally:
            if created:
                index.unlink(missing_ok=True)

    def test_valid_id_serves_index_html(self, client, index_html):
        """A well-formed 11-char share ID must return 200 text/html (the SPA shell)."""
        r = client.get("/result/AAAAAAAAAAA")
        assert r.status_code == 200
        assert "text/html" in r.headers.get("content-type", "")

    def test_valid_id_served_inline_not_download(self, client, index_html):
        """The SPA shell must render in-browser, not be offered as a download.

        Litestar's File response defaults to content_disposition_type="attachment",
        which makes browsers download the page instead of rendering it. The handler
        must serve it inline.
        """
        r = client.get("/result/AAAAAAAAAAA")
        assert "attachment" not in r.headers.get("content-disposition", "")

    def test_invalid_id_returns_404(self, client):
        """An ID that doesn't match [A-Za-z0-9_-]{11} must be rejected with 404."""
        r = client.get("/result/toolong12345")
        assert r.status_code == 404

    def test_short_id_returns_404(self, client):
        """An ID shorter than 11 characters must be rejected with 404."""
        r = client.get("/result/short")
        assert r.status_code == 404
