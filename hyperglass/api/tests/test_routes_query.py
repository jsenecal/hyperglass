"""Tests for /api/query cache-write expansion and force flag."""

# Third Party
import pytest


@pytest.fixture
def params() -> dict:
    # fake_output enables routes to return without hitting real devices.
    return {"fake_output": True}


def test_query_caches_all_snapshot_fields(client, state):
    # First call seeds cache.
    r1 = client.post("/api/query", json={
        "queryLocation": "test1",
        "queryTarget": "192.0.2.0/24",
        "queryType": "juniper_bgp_route",
    })
    assert r1.status_code == 201
    cache_id = r1.json()["id"]

    cache = state.redis
    digest = cache_id.removeprefix("hyperglass.query.")
    cache_key = f"hyperglass.query.{digest}"

    assert cache.get_map(cache_key, "output") is not None
    assert cache.get_map(cache_key, "timestamp") is not None
    assert cache.get_map(cache_key, "query") is not None
    assert cache.get_map(cache_key, "query_labels") is not None
    assert cache.get_map(cache_key, "format") is not None
    assert cache.get_map(cache_key, "runtime") is not None
    assert cache.get_map(cache_key, "level") is not None
    assert cache.get_map(cache_key, "keywords") == []

    qmap = cache.get_map(cache_key, "query")
    assert qmap["query_location"] == "test1"

    labels = cache.get_map(cache_key, "query_labels")
    assert "location" in labels
    assert "type" in labels
    assert labels["type"] == "BGP Route"


def test_query_hit_path_returns_cached(client, state):
    """Second POST of the same query must return a 201 with cached=True."""
    payload = {
        "queryLocation": "test1",
        "queryTarget": "192.0.2.0/24",
        "queryType": "juniper_bgp_route",
    }

    r1 = client.post("/api/query", json=payload)
    assert r1.status_code == 201

    r2 = client.post("/api/query", json=payload)
    assert r2.status_code == 201
    body = r2.json()
    assert body["cached"] is True
    # format field must be present and non-empty (no 500 on format handling).
    assert body.get("format") in ("application/json", "text/plain")


def test_force_skips_cache_hit(client, state):
    """Force flag must bypass cache and re-execute the query."""
    body = {"queryLocation": "test1", "queryTarget": "192.0.2.0/24",
            "queryType": "juniper_bgp_route"}
    r1 = client.post("/api/query", json=body)
    assert r1.status_code == 201
    assert r1.json()["cached"] is False

    # Second call without force: cache hit.
    r2 = client.post("/api/query", json=body)
    assert r2.json()["cached"] is True

    # Third call with force: cache must be skipped (re-execution).
    r3 = client.post("/api/query", json={**body, "force": True})
    assert r3.status_code == 201
    assert r3.json()["cached"] is False
