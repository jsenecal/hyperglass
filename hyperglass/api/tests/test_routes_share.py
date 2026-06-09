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


class TestShareViewHtml:
    """GET /result/<share_id> serves the exported result page when present.

    Also verifies that invalid-format IDs are rejected with 404.
    """

    @pytest.fixture
    def result_page(self, tmp_path, monkeypatch):
        """Point the handler at a tmp UI dir holding the result placeholder page.

        The handler serves `<UI_DIR>/result/shared.html` (the `/result/[id]`
        export), NOT index.html — index.html is the home page and would render
        the landing page instead of the result. The real file is a build
        artifact (`task ui-build`); rather than depend on its presence (UI_DIR
        resolves to app_path/static/ui, which differs across dev/CI), redirect
        UI_DIR to a tmp dir and synthesize the placeholder there.
        """
        # Project
        import hyperglass.api as api

        ui_dir = tmp_path / "ui"
        (ui_dir / "result").mkdir(parents=True)
        page = ui_dir / "result" / "shared.html"
        page.write_text("<!doctype html><title>hyperglass result</title>")
        # UI_DIR is a module global read at request time, so patching it here
        # takes effect for the handler without rebuilding the app.
        monkeypatch.setattr(api, "UI_DIR", ui_dir)
        yield page

    def test_valid_id_serves_result_page(self, client, result_page):
        """A well-formed 11-char share ID must return 200 text/html (the result page).

        Must serve the /result/[id] export, not index.html (the home page) —
        serving index.html renders the landing page instead of the result.
        """
        r = client.get("/result/AAAAAAAAAAA")
        assert r.status_code == 200
        assert "text/html" in r.headers.get("content-type", "")
        assert "hyperglass result" in r.text

    def test_missing_result_page_returns_404(self, client, tmp_path, monkeypatch):
        """Respond 404 when the result export is absent (UI not built).

        Must not fall back to index.html, which would render the home page.
        """
        import hyperglass.api as api

        monkeypatch.setattr(api, "UI_DIR", tmp_path / "empty-ui")
        r = client.get("/result/AAAAAAAAAAA")
        assert r.status_code == 404

    def test_valid_id_served_inline_not_download(self, client, result_page):
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
