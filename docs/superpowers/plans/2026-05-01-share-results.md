# Share Results Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in "share this result" feature: a deliberate click promotes a query result to long-term Redis storage with an opaque random ID, exposed at `/result/<id>` for ~7 days (operator-tunable), serving an exact snapshot of the original output.

**Architecture:** Server-authoritative snapshots. The existing query cache write at `routes.py:130-131` is expanded so it carries every field a snapshot needs (output, query, query labels, format, runtime, level, keywords). On Share click, the backend reads that cache entry, generates an opaque random ID via `secrets.token_urlsafe(8)`, copies the snapshot into a new `hyperglass.share.<id>` Redis namespace with the long TTL, and returns a public URL. Frontend gets a new client-rendered page at `pages/result/[id].tsx` that fetches `/api/query/share/<id>` and reuses the existing Result component in read-only mode. UI knobs reach the SPA through the existing build-time `hyperglass.json` channel by extending `Params.frontend()`'s `include` dict.

**Tech Stack:** Python 3.11+, Litestar, Pydantic v2 (backend); Next.js 13 pages router, React, Chakra UI, Zustand, React Query, Vest (frontend); Redis. pytest + pytest-asyncio for backend tests, Vitest + jsdom + @testing-library/react for frontend tests. Black, isort, Ruff, Biome for lint/format.

**Spec reference:** `docs/superpowers/specs/2026-05-01-share-results-design.md`

---

## File Structure

### New backend files

| Path | Purpose |
|------|---------|
| `hyperglass/conftest.py` | Top-level pytest conftest; shared fixtures (`state`, `params`, `devices`, `directives`). Tests are scattered with no shared conftest today; this consolidates the canonical pattern from `hyperglass/state/tests/test_hooks.py`. |
| `hyperglass/api/tests/__init__.py` | Empty package marker. |
| `hyperglass/api/tests/conftest.py` | API-specific fixtures: a `client` fixture wrapping `litestar.testing.TestClient(app=app)`. |
| `hyperglass/api/tests/test_routes_query.py` | Tests for the expanded cache fields and the new `force` flag on `POST /api/query`. |
| `hyperglass/api/tests/test_routes_share.py` | Tests for `POST /api/query/share/{cache_id}` and `GET /api/query/share/{share_id}`. |
| `hyperglass/api/tests/test_share_helpers.py` | Tests for `_generate_share_id` and `_build_share_url` helpers. |

### Modified backend files

| Path | Why |
|------|-----|
| `hyperglass/models/config/cache.py` | Add `share_enabled`, `share_timeout`, `share_sliding`, `refresh_min_interval`. Bump `timeout` default 120 → 600. |
| `hyperglass/models/config/params.py` | Add optional `public_url` field. Extend `frontend()` `include` dict. |
| `hyperglass/models/config/web.py` | Add new string fields to `Text` for share-related copy. |
| `hyperglass/models/api/query.py` | Add `force: bool = False` field. |
| `hyperglass/models/api/response.py` | Add `id` to `QueryResponse`; add `ShareCreateResponse`, `ShareResponse`. |
| `hyperglass/api/routes.py` | Expand cache write fields; honor `force`; add share endpoints; add helpers. |
| `hyperglass/api/__init__.py` | Register the new share route handlers. |

### New frontend files

| Path | Purpose |
|------|---------|
| `hyperglass/ui/hooks/use-share.ts` | Two hooks: `useShareCreate` (POST) and `useShareGet` (GET). |
| `hyperglass/ui/hooks/use-share.test.tsx` | Unit tests for the hooks. |
| `hyperglass/ui/components/results/share-button.tsx` | Share button + popover with copy-to-clipboard. |
| `hyperglass/ui/components/results/share-button.test.tsx` | Tests. |
| `hyperglass/ui/pages/result/[id].tsx` | Read-only share-view page. |
| `hyperglass/ui/pages/result/[id].test.tsx` | Tests. |

### Modified frontend files

| Path | Why |
|------|-----|
| `hyperglass/ui/types/config.ts` | Add `shareEnabled`, `shareTimeout`, `refreshMinInterval` to `_Cache`; add new strings to `_Text`. |
| `hyperglass/ui/types/globals.d.ts` | Add `id` to `QueryResponse`; add `ShareResponse`; add `force?: boolean` to query body. |
| `hyperglass/ui/hooks/use-lg-query.ts` | Support `force: true` in the request body. |
| `hyperglass/ui/components/results/requery-button.tsx` | Add `refreshMinInterval` cooldown gate; pass `force: true` on click. |
| `hyperglass/ui/components/results/individual.tsx` | Add `ShareButton` to result header. |
| `hyperglass/ui/components/looking-glass-form.tsx` | Pre-fill form from query-string params on mount (`?location=&target=&type=`). |

---

## Chunk 1: Backend models and test scaffolding

This chunk introduces the test infrastructure (no API tests exist today) and updates every config / API model. Routes are unchanged in this chunk.

### Task 1.1: Top-level pytest conftest

**Files:**
- Create: `hyperglass/conftest.py`

The canonical state-fixture pattern lives in `hyperglass/state/tests/test_hooks.py:32-89`. Move it up to a top-level `conftest.py` so the API tests can reuse it.

- [ ] **Step 1: Create the conftest with shared fixtures**

```python
"""Top-level pytest fixtures shared across hyperglass test modules."""

# Standard Library
import typing as t

# Third Party
import pytest

# Project
from hyperglass.state import use_state
from hyperglass.configuration import init_ui_params
from hyperglass.models.directive import Directives
from hyperglass.models.config.params import Params
from hyperglass.models.config.devices import Devices

if t.TYPE_CHECKING:
    from hyperglass.state import HyperglassState


@pytest.fixture
def params() -> t.Dict[str, t.Any]:
    return {}


@pytest.fixture
def devices() -> t.Sequence[t.Dict[str, t.Any]]:
    return [
        {
            "name": "test1",
            "address": "127.0.0.1",
            "credential": {"username": "", "password": ""},
            "platform": "juniper",
            "attrs": {"source4": "192.0.2.1", "source6": "2001:db8::1"},
            "directives": ["juniper_bgp_route"],
        }
    ]


@pytest.fixture
def directives() -> t.Sequence[t.Dict[str, t.Any]]:
    return [
        {
            "juniper_bgp_route": {
                "name": "BGP Route",
                "field": {"description": "test"},
            }
        }
    ]


@pytest.fixture
def state(
    *,
    params: t.Dict[str, t.Any],
    directives: t.Sequence[t.Dict[str, t.Any]],
    devices: t.Sequence[t.Dict[str, t.Any]],
) -> t.Generator["HyperglassState", None, None]:
    """Initialize Redis state for a test."""
    _state = use_state()
    _params = Params(**params)
    _directives = Directives.new(*directives)

    with _state.cache.pipeline() as pipeline:
        pipeline.set("params", _params)
        pipeline.set("directives", _directives)

    _devices = Devices(*devices)
    ui_params = init_ui_params(params=_params, devices=_devices)

    with _state.cache.pipeline() as pipeline:
        pipeline.set("devices", _devices)
        pipeline.set("ui_params", ui_params)

    yield _state
    _state.clear()
```

- [ ] **Step 2: Verify existing tests still pass**

Run: `task test -- hyperglass/state/tests/`
Expected: all green. (We didn't break the duplicated fixtures in `state/tests/test_hooks.py` — pytest resolves the closer one.)

- [ ] **Step 3: Commit**

```bash
git add hyperglass/conftest.py
git commit -m "test: add top-level conftest with shared state fixtures"
```

### Task 1.2: API test scaffolding (TestClient fixture)

**Files:**
- Create: `hyperglass/api/tests/__init__.py`
- Create: `hyperglass/api/tests/conftest.py`
- Create: `hyperglass/api/tests/test_smoke.py`

- [ ] **Step 1: Create the `__init__.py` package marker**

Empty file:

```python
```

- [ ] **Step 2: Create the API conftest**

```python
"""API-specific test fixtures."""

# Standard Library
import typing as t

# Third Party
import pytest
from litestar.testing import TestClient


@pytest.fixture
def client(state) -> t.Generator[TestClient, None, None]:
    """Litestar TestClient for hitting hyperglass routes.

    Depends on the `state` fixture from the top-level conftest, which
    populates Redis with params/devices/directives/ui_params.
    """
    # Import here so the `state` fixture has populated Redis before the
    # app's startup hooks run.
    from hyperglass.api import app

    with TestClient(app=app) as test_client:
        yield test_client
```

- [ ] **Step 3: Write a smoke test**

```python
"""Smoke test that the API test scaffolding works."""


def test_devices_endpoint_returns_seeded_device(client):
    response = client.get("/api/devices")
    assert response.status_code == 200
    payload = response.json()
    assert any(d.get("name") == "test1" for d in payload)
```

- [ ] **Step 4: Run the smoke test**

Run: `task test -- hyperglass/api/tests/test_smoke.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add hyperglass/api/tests/
git commit -m "test(api): add TestClient fixture and smoke test"
```

### Task 1.3: Extend `Cache` config model

**Files:**
- Modify: `hyperglass/models/config/cache.py`
- Test: `hyperglass/models/config/tests/test_cache.py` (create if absent)

- [ ] **Step 1: Write failing tests for the new fields**

Create `hyperglass/models/config/tests/__init__.py` (empty) if needed, then `hyperglass/models/config/tests/test_cache.py`:

```python
"""Tests for the Cache config model."""

# Project
from hyperglass.models.config.cache import Cache


def test_cache_defaults():
    cache = Cache()
    assert cache.timeout == 600
    assert cache.show_text is True
    assert cache.share_enabled is True
    assert cache.share_timeout == 604800  # 7 days
    assert cache.share_sliding is False
    assert cache.refresh_min_interval == 120


def test_cache_share_timeout_overridable():
    cache = Cache(share_timeout=2592000)  # 30 days
    assert cache.share_timeout == 2592000


def test_cache_share_disabled():
    cache = Cache(share_enabled=False)
    assert cache.share_enabled is False
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest hyperglass/models/config/tests/test_cache.py -v`
Expected: FAIL — fields don't exist yet.

- [ ] **Step 3: Add the fields**

Replace `hyperglass/models/config/cache.py`:

```python
"""Validation model for cache config."""

# Local
from ..main import HyperglassModel


class Cache(HyperglassModel):
    """Public cache parameters."""

    timeout: int = 600
    show_text: bool = True
    share_enabled: bool = True
    share_timeout: int = 604800
    share_sliding: bool = False
    refresh_min_interval: int = 120
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest hyperglass/models/config/tests/test_cache.py -v`
Expected: PASS.

- [ ] **Step 5: Run lint**

Run: `task lint`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add hyperglass/models/config/cache.py hyperglass/models/config/tests/
git commit -m "feat(config): add share_timeout/share_enabled/share_sliding/refresh_min_interval, bump timeout default to 600"
```

### Task 1.4: Add `force` field to Query model

**Files:**
- Modify: `hyperglass/models/api/query.py`
- Test: `hyperglass/models/api/tests/test_query_force.py` (create)

- [ ] **Step 1: Write the failing test**

Create `hyperglass/models/api/tests/__init__.py` (empty) if needed, then `hyperglass/models/api/tests/test_query_force.py`:

```python
"""Tests for the Query.force flag."""


def test_query_force_default_false(state):
    from hyperglass.models.api import Query
    q = Query(query_location="test1", query_target="192.0.2.0/24",
              query_type="juniper_bgp_route")
    assert q.force is False


def test_query_force_true(state):
    from hyperglass.models.api import Query
    q = Query(query_location="test1", query_target="192.0.2.0/24",
              query_type="juniper_bgp_route", force=True)
    assert q.force is True


def test_query_force_does_not_affect_digest(state):
    """The cache key must not depend on the force flag."""
    from hyperglass.models.api import Query
    q1 = Query(query_location="test1", query_target="192.0.2.0/24",
               query_type="juniper_bgp_route", force=False)
    q2 = Query(query_location="test1", query_target="192.0.2.0/24",
               query_type="juniper_bgp_route", force=True)
    assert q1.digest() == q2.digest()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest hyperglass/models/api/tests/test_query_force.py -v`
Expected: FAIL on `q.force is False` (attribute doesn't exist).

- [ ] **Step 3: Add the field**

In `hyperglass/models/api/query.py`, in the `Query` class (around line 53, after `query_type`), add:

```python
    # Bypass cache and re-execute when True.
    force: bool = False
```

`Query.__repr__` currently returns `repr_from_attrs(self, ("query_location", "query_type", "query_target"))` (line 91). Do **not** add `force` to that tuple — it must not affect the digest.

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest hyperglass/models/api/tests/test_query_force.py -v`
Expected: PASS.

- [ ] **Step 5: Run full test suite to confirm no regressions**

Run: `task test`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add hyperglass/models/api/query.py hyperglass/models/api/tests/
git commit -m "feat(api): add Query.force flag to bypass cache; excluded from digest"
```

### Task 1.5: Add `public_url` field to `Params`

**Files:**
- Modify: `hyperglass/models/config/params.py`
- Test: `hyperglass/models/config/tests/test_params_public_url.py` (create)

- [ ] **Step 1: Write the failing test**

```python
"""Tests for Params.public_url."""

# Project
from hyperglass.models.config.params import Params


def test_public_url_default_none():
    p = Params()
    assert p.public_url is None


def test_public_url_set_to_https_url():
    p = Params(public_url="https://lg.example.com")
    assert str(p.public_url) == "https://lg.example.com/"
```

(Pydantic's `AnyHttpUrl` normalizes by appending a trailing slash; the helper that builds share URLs will rstrip it.)

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest hyperglass/models/config/tests/test_params_public_url.py -v`
Expected: FAIL.

- [ ] **Step 3: Add the field**

In `hyperglass/models/config/params.py`, near the top of the `Params` class (after existing fields), add:

```python
    public_url: t.Optional[AnyHttpUrl] = None
```

Add `from pydantic import AnyHttpUrl` to the imports if not already present.

- [ ] **Step 4: Run the test**

Run: `pytest hyperglass/models/config/tests/test_params_public_url.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add hyperglass/models/config/params.py hyperglass/models/config/tests/test_params_public_url.py
git commit -m "feat(config): add optional Params.public_url for share URL building"
```

### Task 1.6: Extend `Params.frontend()` include set

**Files:**
- Modify: `hyperglass/models/config/params.py:153-168`
- Test: `hyperglass/models/config/tests/test_params_frontend.py` (create)

- [ ] **Step 1: Write the failing test**

```python
"""Tests for Params.frontend() projection."""

# Project
from hyperglass.models.config.params import Params


def test_frontend_includes_share_fields():
    p = Params()
    out = p.frontend()
    assert "cache" in out
    cache = out["cache"]
    assert "share_enabled" in cache
    assert "share_timeout" in cache
    assert "refresh_min_interval" in cache


def test_frontend_excludes_private_share_sliding():
    p = Params()
    cache = p.frontend()["cache"]
    assert "share_sliding" not in cache
```

- [ ] **Step 2: Run the test**

Run: `pytest hyperglass/models/config/tests/test_params_frontend.py -v`
Expected: FAIL (fields not yet projected).

- [ ] **Step 3: Modify the include set**

In `hyperglass/models/config/params.py`, update `frontend()`:

```python
def frontend(self) -> t.Dict[str, t.Any]:
    """Export UI-specific parameters."""
    return self.export_dict(
        include={
            "cache": {
                "show_text",
                "timeout",
                "share_enabled",
                "share_timeout",
                "refresh_min_interval",
            },
            "developer_mode": ...,
            "primary_asn": ...,
            "request_timeout": ...,
            "org_name": ...,
            "site_title": ...,
            "site_description": ...,
            "web": ...,
            "messages": ...,
        }
    )
```

- [ ] **Step 4: Run the test**

Run: `pytest hyperglass/models/config/tests/test_params_frontend.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add hyperglass/models/config/params.py hyperglass/models/config/tests/test_params_frontend.py
git commit -m "feat(config): project share UI knobs through Params.frontend()"
```

### Task 1.7: Add response models — `id` on `QueryResponse`, plus `ShareCreateResponse` and `ShareResponse`

**Files:**
- Modify: `hyperglass/models/api/response.py`
- Test: `hyperglass/models/api/tests/test_response_models.py` (create)

- [ ] **Step 1: Read the existing response module to learn its conventions**

Run: `head -80 hyperglass/models/api/response.py`
(Identify the `QueryResponse` class and its imports; reuse the same field-aliasing convention.)

- [ ] **Step 2: Write failing tests**

```python
"""Tests for share response models."""

# Standard Library
from datetime import datetime, timezone

# Project
from hyperglass.models.api.response import (
    QueryResponse, ShareCreateResponse, ShareResponse,
)


def test_query_response_includes_id():
    r = QueryResponse(
        output="ok",
        id="hyperglass.query.deadbeef",
        cached=False,
        runtime=1,
        timestamp=datetime.now(timezone.utc),
        format="text/plain",
        random="r",
        level="success",
        keywords=[],
    )
    assert r.id == "hyperglass.query.deadbeef"


def test_share_create_response_shape():
    expires = datetime.now(timezone.utc)
    r = ShareCreateResponse(id="abc", url="https://lg.example.com/result/abc",
                            expires_at=expires)
    assert r.id == "abc"
    assert r.url.endswith("/result/abc")


def test_share_response_shape():
    expires = datetime.now(timezone.utc)
    r = ShareResponse(
        id="abc",
        output="ok",
        cached=True,
        shared=True,
        runtime=1,
        timestamp=datetime.now(timezone.utc),
        format="text/plain",
        level="success",
        keywords=[],
        query={"query_location": "test1", "query_target": "192.0.2.0/24",
               "query_type": "juniper_bgp_route"},
        query_labels={"location": "test1", "type": "BGP Route"},
        created_at=datetime.now(timezone.utc),
        expires_at=expires,
    )
    assert r.shared is True
    assert r.query_labels["location"] == "test1"
```

- [ ] **Step 3: Run the test**

Run: `pytest hyperglass/models/api/tests/test_response_models.py -v`
Expected: FAIL.

- [ ] **Step 4: Add the models**

In `hyperglass/models/api/response.py`, add `id: str` to the existing `QueryResponse` model. Then add:

```python
class ShareCreateResponse(BaseModel):
    """Response from POST /api/query/share/{cache_id}."""
    model_config = ConfigDict(alias_generator=snake_to_camel, populate_by_name=True)

    id: str
    url: str
    expires_at: datetime


class ShareResponse(BaseModel):
    """Response from GET /api/query/share/{share_id}.

    Superset of QueryResponse with snapshot metadata.
    """
    model_config = ConfigDict(alias_generator=snake_to_camel, populate_by_name=True)

    id: str
    output: t.Union[str, t.Dict[str, t.Any]]
    cached: bool = True
    shared: bool = True
    runtime: int
    timestamp: datetime
    format: str
    level: str
    keywords: t.List[str]
    query: t.Dict[str, t.Any]
    query_labels: t.Dict[str, str]
    created_at: datetime
    expires_at: datetime
```

(Use the existing imports from the file for `BaseModel`, `ConfigDict`, `datetime`, `t`, and `snake_to_camel`. Mirror the alias convention used by `QueryResponse`.)

- [ ] **Step 5: Run the test**

Run: `pytest hyperglass/models/api/tests/test_response_models.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add hyperglass/models/api/response.py hyperglass/models/api/tests/test_response_models.py
git commit -m "feat(api): add id to QueryResponse, add ShareCreateResponse and ShareResponse"
```

---

## Chunk 2: Backend route changes and share endpoints

### Task 2.1: Expand cache write to store full snapshot fields

**Files:**
- Modify: `hyperglass/api/routes.py:96-134` (the cache-miss branch)
- Test: `hyperglass/api/tests/test_routes_query.py` (create)

The current cache write only stores `output` and `timestamp` (lines 130-131). Expand it so the entry carries everything the share endpoint will need.

- [ ] **Step 1: Write the failing test**

```python
"""Tests for /api/query cache-write expansion and force flag."""


def test_query_caches_all_snapshot_fields(client, state):
    # First call seeds cache.
    r1 = client.post("/api/query", json={
        "queryLocation": "test1",
        "queryTarget": "192.0.2.0/24",
        "queryType": "juniper_bgp_route",
    })
    assert r1.status_code == 200
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

    qmap = cache.get_map(cache_key, "query")
    assert qmap["query_location"] == "test1"

    labels = cache.get_map(cache_key, "query_labels")
    assert "location" in labels
    assert "type" in labels
    assert labels["type"] == "BGP Route"
```

The `state` fixture (top-level conftest) has `params.fake_output: True`? Verify with the existing test seeding — the default `Params()` has `fake_output: False`. The test will hit `execute(data)`, which fails without real network. **Workaround:** override `params` in the test:

```python
@pytest.fixture
def params() -> dict:
    return {"fake_output": True}
```

Add this fixture override **at the top of the test module** (`hyperglass/api/tests/test_routes_query.py`).

- [ ] **Step 2: Run test to verify it fails**

Run: `task test -- hyperglass/api/tests/test_routes_query.py -v`
Expected: FAIL — `query`, `query_labels`, `format`, `runtime`, `level` are not in the cache map.

- [ ] **Step 3: Implement the cache-write expansion**

In `hyperglass/api/routes.py`, in the cache-miss branch (around lines 96–134), replace:

```python
cache.set_map_item(cache_key, "output", raw_output)
cache.set_map_item(cache_key, "timestamp", timestamp)
cache.expire(cache_key, expire_in=_state.params.cache.timeout)
```

With:

```python
response_format = "application/json" if json_output else "text/plain"
query_labels = {
    "location": data.device.display_name or data.device.name,
    "type": data.directive.name,
}

cache.set_map_item(cache_key, "output", raw_output)
cache.set_map_item(cache_key, "timestamp", timestamp)
cache.set_map_item(cache_key, "query", data.dict())
cache.set_map_item(cache_key, "query_labels", query_labels)
cache.set_map_item(cache_key, "format", response_format)
cache.set_map_item(cache_key, "runtime", runtime)
cache.set_map_item(cache_key, "level", "success")
cache.set_map_item(cache_key, "keywords", [])
cache.expire(cache_key, expire_in=_state.params.cache.timeout)
```

`response_format` and `runtime` are computed before this block; the assignments above replace the equivalent post-write computation. The `response = {...}` literal that builds the route's return value can now read these from the cache (or just keep its existing in-memory references — both approaches work). Keep the existing return shape unchanged.

- [ ] **Step 4: Run test to verify it passes**

Run: `task test -- hyperglass/api/tests/test_routes_query.py -v`
Expected: PASS.

- [ ] **Step 5: Run full backend test suite**

Run: `task test`
Expected: green.

- [ ] **Step 6: Commit**

```bash
git add hyperglass/api/routes.py hyperglass/api/tests/test_routes_query.py
git commit -m "feat(api): expand /api/query cache write with full snapshot fields"
```

### Task 2.2: Honor `force` flag in `/api/query`

**Files:**
- Modify: `hyperglass/api/routes.py:81-95` (the cache-hit branch)
- Test: `hyperglass/api/tests/test_routes_query.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `test_routes_query.py`:

```python
def test_force_skips_cache_hit(client, state):
    body = {"queryLocation": "test1", "queryTarget": "192.0.2.0/24",
            "queryType": "juniper_bgp_route"}
    r1 = client.post("/api/query", json=body)
    assert r1.status_code == 200
    assert r1.json()["cached"] is False

    # Second call without force: cache hit.
    r2 = client.post("/api/query", json=body)
    assert r2.json()["cached"] is True

    # Third call with force: cache must be skipped (re-execution).
    r3 = client.post("/api/query", json={**body, "force": True})
    assert r3.status_code == 200
    assert r3.json()["cached"] is False
```

- [ ] **Step 2: Run the test**

Run: `task test -- hyperglass/api/tests/test_routes_query.py::test_force_skips_cache_hit -v`
Expected: FAIL — third call is reported as cached.

- [ ] **Step 3: Implement**

In `hyperglass/api/routes.py`, replace the start of the cache-hit branch:

```python
cache_response = cache.get_map(cache_key, "output")
```

With:

```python
cache_response = None if data.force else cache.get_map(cache_key, "output")
```

Do not pre-delete the cache key; on execution failure, the existing entry stays intact.

- [ ] **Step 4: Run the test**

Run: `task test -- hyperglass/api/tests/test_routes_query.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add hyperglass/api/routes.py hyperglass/api/tests/test_routes_query.py
git commit -m "feat(api): /api/query honors force flag to bypass cache"
```

### Task 2.3: `_generate_share_id` helper

**Files:**
- Modify: `hyperglass/api/routes.py` (add helper near top)
- Test: `hyperglass/api/tests/test_share_helpers.py` (create)

- [ ] **Step 1: Write the failing test**

```python
"""Tests for share helper functions."""

# Standard Library
import re

# Third Party
import pytest


def test_generate_share_id_format(state):
    from hyperglass.api.routes import _generate_share_id
    cache = state.redis
    sid = _generate_share_id(cache)
    assert isinstance(sid, str)
    # secrets.token_urlsafe(8) -> 11 chars, [A-Za-z0-9_-]
    assert re.fullmatch(r"[A-Za-z0-9_-]{11}", sid)


def test_generate_share_id_unique(state):
    from hyperglass.api.routes import _generate_share_id
    cache = state.redis
    seen = {_generate_share_id(cache) for _ in range(100)}
    assert len(seen) == 100


def test_generate_share_id_collision_retry(state, monkeypatch):
    """If the first ID exists, the helper retries."""
    from hyperglass.api import routes
    cache = state.redis

    cache.set_map_item("hyperglass.share.AAAAAAAAAAA", "output", "x")

    sequence = iter(["AAAAAAAAAAA", "BBBBBBBBBBB"])
    monkeypatch.setattr(
        routes.secrets, "token_urlsafe", lambda n: next(sequence)
    )
    sid = routes._generate_share_id(cache)
    assert sid == "BBBBBBBBBBB"
```

- [ ] **Step 2: Run the test**

Run: `task test -- hyperglass/api/tests/test_share_helpers.py -v`
Expected: FAIL — helper doesn't exist.

- [ ] **Step 3: Implement**

In `hyperglass/api/routes.py`, near the top after imports, add:

```python
import secrets

def _generate_share_id(cache, max_attempts: int = 3) -> str:
    """Generate an opaque, unique share ID.

    Returns an 11-char URL-safe-base64 token (64 bits of entropy from
    `secrets.token_urlsafe(8)`). Verifies non-collision against existing
    `hyperglass.share.*` keys; collision is astronomically unlikely but
    the check is cheap.
    """
    for _ in range(max_attempts):
        candidate = secrets.token_urlsafe(8)
        if cache.get_map(f"hyperglass.share.{candidate}", "output") is None:
            return candidate
    raise RuntimeError("Failed to generate a unique share ID after retries.")
```

- [ ] **Step 4: Run the test**

Run: `task test -- hyperglass/api/tests/test_share_helpers.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add hyperglass/api/routes.py hyperglass/api/tests/test_share_helpers.py
git commit -m "feat(api): add _generate_share_id helper with collision retry"
```

### Task 2.4: `_build_share_url` helper

**Files:**
- Modify: `hyperglass/api/routes.py`
- Test: `hyperglass/api/tests/test_share_helpers.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `test_share_helpers.py`:

```python
def test_build_share_url_uses_params_public_url():
    from hyperglass.api.routes import _build_share_url
    from hyperglass.models.config.params import Params

    params = Params(public_url="https://lg.example.com")
    # Pass None for request — params.public_url wins.
    assert _build_share_url(params, None, "abc123") == \
        "https://lg.example.com/result/abc123"


def test_build_share_url_falls_back_to_request(monkeypatch):
    from hyperglass.api.routes import _build_share_url
    from hyperglass.models.config.params import Params

    class FakeURL:
        scheme = "http"
        netloc = "127.0.0.1:8001"

    class FakeRequest:
        headers = {"host": "lg.example.com", "x-forwarded-proto": "https"}
        url = FakeURL()

    params = Params()  # public_url unset
    assert _build_share_url(params, FakeRequest(), "abc123") == \
        "https://lg.example.com/result/abc123"


def test_build_share_url_request_no_proxy_headers():
    from hyperglass.api.routes import _build_share_url
    from hyperglass.models.config.params import Params

    class FakeURL:
        scheme = "http"
        netloc = "127.0.0.1:8001"

    class FakeRequest:
        headers = {}
        url = FakeURL()

    params = Params()
    assert _build_share_url(params, FakeRequest(), "abc") == \
        "http://127.0.0.1:8001/result/abc"
```

- [ ] **Step 2: Run the test**

Run: `task test -- hyperglass/api/tests/test_share_helpers.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

In `hyperglass/api/routes.py`, add:

```python
def _build_share_url(params, request, share_id: str) -> str:
    """Build the public share URL.

    Prefers `params.public_url` when set; otherwise derives from request
    headers. `X-Forwarded-Proto` and `Host` take precedence over the
    direct connection URL so reverse-proxied deployments produce correct
    public URLs without explicit configuration.
    """
    if params.public_url is not None:
        base = str(params.public_url).rstrip("/")
    else:
        host = request.headers.get("host") or request.url.netloc
        scheme = request.headers.get("x-forwarded-proto") or request.url.scheme
        base = f"{scheme}://{host}"
    return f"{base}/result/{share_id}"
```

- [ ] **Step 4: Run the test**

Run: `task test -- hyperglass/api/tests/test_share_helpers.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add hyperglass/api/routes.py hyperglass/api/tests/test_share_helpers.py
git commit -m "feat(api): add _build_share_url helper with public_url and proxy fallback"
```

### Task 2.5: `POST /api/query/share/{cache_id}` endpoint

**Files:**
- Modify: `hyperglass/api/routes.py`
- Modify: `hyperglass/api/__init__.py` (register the new handler)
- Test: `hyperglass/api/tests/test_routes_share.py` (create)

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for share-related routes."""

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
    assert r.status_code == 200
    return r.json()["id"]


def test_share_create_returns_opaque_id(client):
    cache_id = _seed_query(client)
    r = client.post(f"/api/query/share/{cache_id}")
    assert r.status_code == 201 or r.status_code == 200
    body = r.json()
    assert "id" in body
    # 11-char URL-safe base64
    import re
    assert re.fullmatch(r"[A-Za-z0-9_-]{11}", body["id"])
    assert body["url"].endswith(f"/result/{body['id']}")


def test_share_create_410_when_cache_expired(client, state):
    cache_id = _seed_query(client)
    digest = cache_id.removeprefix("hyperglass.query.")
    state.redis.delete(f"hyperglass.state.hyperglass.query.{digest}")

    r = client.post(f"/api/query/share/{cache_id}")
    assert r.status_code == 410


def test_share_create_404_when_disabled(client):
    """When cache.share_enabled is False, share-create returns 404."""
    pass


@pytest.fixture
def params_share_disabled() -> dict:
    return {"fake_output": True, "cache": {"share_enabled": False}}


def test_share_create_404_when_share_disabled(client_with_share_disabled):
    """Verifies the disabled-feature kill switch."""
    # See conftest fixture variant below for client_with_share_disabled.
```

For the `share_enabled=False` test, the simplest pattern is a parametrized variant. Add a second client fixture in `hyperglass/api/tests/conftest.py`:

```python
@pytest.fixture
def client_with_share_disabled(request, monkeypatch):
    """Like `client`, but with cache.share_enabled=False."""
    # Override the params fixture for this test by monkeypatching state.
    pass  # See implementation step below.
```

Realistically, the cleanest approach is to write `test_share_create_404_when_share_disabled` as its own module-level test that overrides the `params` fixture:

```python
class TestShareDisabled:
    @pytest.fixture
    def params(self) -> dict:
        return {"fake_output": True, "cache": {"share_enabled": False}}

    def test_share_create_404(self, client):
        # Even with no cache entry, disabled gate should fire first.
        r = client.post("/api/query/share/hyperglass.query.deadbeef")
        assert r.status_code == 404
```

- [ ] **Step 2: Run the tests**

Run: `task test -- hyperglass/api/tests/test_routes_share.py -v`
Expected: FAIL — endpoint doesn't exist (returns 404 for routing reasons, but the body assertions fail).

- [ ] **Step 3: Implement the endpoint**

In `hyperglass/api/routes.py`, add the imports:

```python
from datetime import UTC, datetime, timedelta
from litestar.exceptions import HTTPException, NotFoundException
```

Add the handler:

```python
@post("/api/query/share/{cache_id:str}", dependencies={"_state": Provide(get_state)})
async def share_create(
    _state: HyperglassState,
    request: Request,
    cache_id: str,
) -> ShareCreateResponse:
    """Promote a cached query result to a long-lived shareable snapshot."""
    if not _state.params.cache.share_enabled:
        raise NotFoundException("Sharing is disabled.")

    digest = cache_id.removeprefix("hyperglass.query.")
    cache_key = f"hyperglass.query.{digest}"

    cache = _state.redis
    output = cache.get_map(cache_key, "output")
    if output is None:
        raise HTTPException(
            status_code=410,
            detail="Result has expired. Refresh the query and try again.",
        )

    share_id = _generate_share_id(cache)
    share_key = f"hyperglass.share.{share_id}"
    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=_state.params.cache.share_timeout)

    for field in ("output", "timestamp", "query", "query_labels",
                  "format", "runtime", "level", "keywords"):
        cache.set_map_item(share_key, field, cache.get_map(cache_key, field))
    cache.set_map_item(share_key, "created_at", now)
    cache.set_map_item(share_key, "expires_at", expires_at)
    cache.expire(share_key, expire_in=_state.params.cache.share_timeout)

    return ShareCreateResponse(
        id=share_id,
        url=_build_share_url(_state.params, request, share_id),
        expires_at=expires_at,
    )
```

Add `share_create` to the `__all__` tuple at the top of `routes.py`.

- [ ] **Step 4: Register the route**

In `hyperglass/api/__init__.py`, find the `HANDLERS` list around line 35 and add `share_create` to the imports from `hyperglass.api.routes` and to the list.

- [ ] **Step 5: Run the tests**

Run: `task test -- hyperglass/api/tests/test_routes_share.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add hyperglass/api/routes.py hyperglass/api/__init__.py hyperglass/api/tests/test_routes_share.py
git commit -m "feat(api): add POST /api/query/share/{cache_id} for share creation"
```

### Task 2.6: `GET /api/query/share/{share_id}` endpoint

**Files:**
- Modify: `hyperglass/api/routes.py`
- Modify: `hyperglass/api/__init__.py`
- Test: `hyperglass/api/tests/test_routes_share.py` (extend)

- [ ] **Step 1: Write the failing tests**

Append to `test_routes_share.py`:

```python
def test_share_get_returns_full_snapshot(client):
    cache_id = _seed_query(client)
    create_resp = client.post(f"/api/query/share/{cache_id}").json()

    r = client.get(f"/api/query/share/{create_resp['id']}")
    assert r.status_code == 200
    body = r.json()
    assert body["shared"] is True
    assert body["query"]["queryLocation"] == "test1"
    assert body["queryLabels"]["type"] == "BGP Route"
    assert "createdAt" in body
    assert "expiresAt" in body


def test_share_get_404_when_missing(client):
    r = client.get("/api/query/share/nonexistent1")
    assert r.status_code == 404


def test_share_get_sliding_extends_ttl(client, state):
    """When share_sliding=True, GET resets the share TTL."""
    pass  # see TestShareSliding below


class TestShareSliding:
    @pytest.fixture
    def params(self) -> dict:
        return {
            "fake_output": True,
            "cache": {"share_sliding": True, "share_timeout": 600},
        }

    def test_get_resets_ttl(self, client, state):
        cache_id = _seed_query(client)
        share_id = client.post(f"/api/query/share/{cache_id}").json()["id"]
        share_key = f"hyperglass.state.hyperglass.share.{share_id}"

        # Manually shorten the TTL to verify GET extends it back.
        state.redis.expire(share_key.removeprefix("hyperglass.state."), 60)
        r = client.get(f"/api/query/share/{share_id}")
        assert r.status_code == 200

        # Use the underlying Redis TTL command via state.cache to verify.
        ttl = state.redis.ttl(share_key.removeprefix("hyperglass.state."))
        assert ttl > 60  # extended back toward share_timeout


class TestShareFixed:
    @pytest.fixture
    def params(self) -> dict:
        return {
            "fake_output": True,
            "cache": {"share_sliding": False, "share_timeout": 600},
        }

    def test_get_does_not_extend_ttl(self, client, state):
        cache_id = _seed_query(client)
        share_id = client.post(f"/api/query/share/{cache_id}").json()["id"]
        key = f"hyperglass.share.{share_id}"

        state.redis.expire(key, 60)
        client.get(f"/api/query/share/{share_id}")
        ttl = state.redis.ttl(key)
        assert ttl <= 60  # not extended
```

(`state.redis.ttl()` is the underlying Redis client; if `RedisManager` does not expose `.ttl` directly, use the lower-level client. Confirm during implementation by reading `hyperglass/state/redis.py`.)

- [ ] **Step 2: Run the tests**

Run: `task test -- hyperglass/api/tests/test_routes_share.py -v`
Expected: FAIL — endpoint not yet defined.

- [ ] **Step 3: Implement the endpoint**

In `hyperglass/api/routes.py`:

```python
@get("/api/query/share/{share_id:str}", dependencies={"_state": Provide(get_state)})
async def share_get(_state: HyperglassState, share_id: str) -> ShareResponse:
    """Read a shared snapshot."""
    if not _state.params.cache.share_enabled:
        raise NotFoundException()

    cache = _state.redis
    share_key = f"hyperglass.share.{share_id}"
    output = cache.get_map(share_key, "output")
    if output is None:
        raise NotFoundException("Share not found or expired.")

    if _state.params.cache.share_sliding:
        cache.expire(share_key, expire_in=_state.params.cache.share_timeout)

    return ShareResponse(
        id=share_id,
        output=output,
        cached=True,
        shared=True,
        runtime=cache.get_map(share_key, "runtime"),
        timestamp=cache.get_map(share_key, "timestamp"),
        format=cache.get_map(share_key, "format"),
        level=cache.get_map(share_key, "level"),
        keywords=cache.get_map(share_key, "keywords") or [],
        query=cache.get_map(share_key, "query"),
        query_labels=cache.get_map(share_key, "query_labels"),
        created_at=cache.get_map(share_key, "created_at"),
        expires_at=cache.get_map(share_key, "expires_at"),
    )
```

Add `share_get` to `__all__` and register it in `hyperglass/api/__init__.py`.

- [ ] **Step 4: Run the tests**

Run: `task test -- hyperglass/api/tests/test_routes_share.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add hyperglass/api/routes.py hyperglass/api/__init__.py hyperglass/api/tests/test_routes_share.py
git commit -m "feat(api): add GET /api/query/share/{share_id} with optional sliding TTL"
```

### Task 2.7: Lint and full backend regression

- [ ] **Step 1: Run Ruff**

Run: `task lint`
Expected: clean (zero errors per CONTRIBUTING.md).

- [ ] **Step 2: Run Black + isort**

Run: `task format && task sort`
Expected: no changes (or stage and commit any formatting deltas).

- [ ] **Step 3: Run full test suite**

Run: `task test`
Expected: all green.

- [ ] **Step 4: Commit any formatting deltas**

```bash
git add -A
git commit -m "style: apply ruff/black/isort to share feature"  # only if needed
```

---

## Chunk 3: Frontend types and API hook

### Task 3.1: Update `Config` types — `_Cache` and `_Text`

**Files:**
- Modify: `hyperglass/ui/types/config.ts`

- [ ] **Step 1: Read the existing `_Cache` and `_Text` interfaces**

Run: `grep -n "_Cache\|_Text" hyperglass/ui/types/config.ts`
Expected: `_Cache` near line 137; `_Text` near line 25.

- [ ] **Step 2: Update `_Cache`**

In `hyperglass/ui/types/config.ts`, replace:

```typescript
interface _Cache {
  showText: boolean;
  timeout: number;
}
```

With:

```typescript
interface _Cache {
  showText: boolean;
  timeout: number;
  shareEnabled: boolean;
  shareTimeout: number;
  refreshMinInterval: number;
}
```

- [ ] **Step 3: Add new fields to `_Text`** (will be populated by Task 4.1 backend, but the type goes here in lockstep with backend additions)

Add to `_Text`:

```typescript
  shareButton: string;
  sharePopoverTitle: string;
  shareCopyLink: string;
  shareLinkCopied: string;
  shareExpiresAt: string;
  shareCreateError: string;
  shareCreateExpired: string;
  shareNotFound: string;
  shareSnapshotBanner: string;
  shareRunFreshQuery: string;
  refreshCooldown: string;
```

(These keys map to the `Text` model fields added in Task 4.1.)

- [ ] **Step 4: Typecheck**

Run: `task ui-typecheck`
Expected: PASS — but note this won't catch missing backend fields until the JSON config is rebuilt; that's fine.

- [ ] **Step 5: Commit**

```bash
git add hyperglass/ui/types/config.ts
git commit -m "feat(ui): extend Config types with share knobs and text strings"
```

### Task 3.2: Update `globals.d.ts` — `QueryResponse`, `ShareResponse`, `force`

**Files:**
- Modify: `hyperglass/ui/types/globals.d.ts`

- [ ] **Step 1: Locate the existing types**

Run: `grep -n "QueryResponse\|interface.*Query" hyperglass/ui/types/globals.d.ts`

- [ ] **Step 2: Add `id` to `QueryResponse`**

```typescript
interface QueryResponse {
  id: string;            // <-- ADD
  output: string | object;
  cached: boolean;
  // ...existing fields...
}
```

- [ ] **Step 3: Add `ShareResponse`**

```typescript
interface ShareResponse {
  id: string;
  output: string | object;
  cached: boolean;
  shared: boolean;
  runtime: number;
  timestamp: string;
  format: string;
  level: string;
  keywords: string[];
  query: { queryLocation: string; queryTarget: string | string[]; queryType: string };
  queryLabels: { location: string; type: string };
  createdAt: string;
  expiresAt: string;
}

interface ShareCreateResponse {
  id: string;
  url: string;
  expiresAt: string;
}
```

- [ ] **Step 4: Add `force?: boolean` to the query body type**

Locate the request-body type used by `useLGQuery` (likely `FormQuery` or `QueryRequest` — `grep` to find it). Add an optional `force?: boolean` field.

- [ ] **Step 5: Typecheck**

Run: `task ui-typecheck`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add hyperglass/ui/types/globals.d.ts
git commit -m "feat(ui): add id to QueryResponse, add ShareResponse, add force? to query body"
```

### Task 3.3: `useShareCreate` and `useShareGet` hooks

**Files:**
- Create: `hyperglass/ui/hooks/use-share.ts`
- Create: `hyperglass/ui/hooks/use-share.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useShareCreate, useShareGet } from './use-share';

const wrapper = ({ children }) => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
};

beforeEach(() => {
  global.fetch = vi.fn();
});

describe('useShareCreate', () => {
  it('POSTs to /api/query/share/<cacheId> and returns the response', async () => {
    (global.fetch as any).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ id: 'aaaaaaaaaaa', url: 'https://x/result/aaaaaaaaaaa', expiresAt: '2026-05-08T00:00:00Z' }),
    });
    const { result } = renderHook(() => useShareCreate(), { wrapper });
    result.current.mutate('hyperglass.query.deadbeef');
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(global.fetch).toHaveBeenCalledWith(
      '/api/query/share/hyperglass.query.deadbeef',
      expect.objectContaining({ method: 'POST' }),
    );
    expect(result.current.data?.id).toBe('aaaaaaaaaaa');
  });

  it('surfaces 410 as an error', async () => {
    (global.fetch as any).mockResolvedValue({ ok: false, status: 410, json: async () => ({}) });
    const { result } = renderHook(() => useShareCreate(), { wrapper });
    result.current.mutate('expired-id');
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect((result.current.error as any).status).toBe(410);
  });
});

describe('useShareGet', () => {
  it('GETs /api/query/share/<id> and returns the snapshot', async () => {
    (global.fetch as any).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ id: 'aaa', shared: true, output: 'x', cached: true, runtime: 1, timestamp: '', format: 'text/plain', level: 'success', keywords: [], query: {}, queryLabels: {}, createdAt: '', expiresAt: '' }),
    });
    const { result } = renderHook(() => useShareGet('aaa'), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(global.fetch).toHaveBeenCalledWith('/api/query/share/aaa', expect.anything());
    expect(result.current.data?.shared).toBe(true);
  });
});
```

- [ ] **Step 2: Run the test**

Run: `task pnpm test -- hooks/use-share.test.tsx`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement**

```ts
// hyperglass/ui/hooks/use-share.ts
import { useMutation, useQuery } from '@tanstack/react-query';

class ShareError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export const useShareCreate = () =>
  useMutation<ShareCreateResponse, ShareError, string>({
    mutationFn: async (cacheId: string) => {
      const res = await fetch(`/api/query/share/${cacheId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      if (!res.ok) throw new ShareError(res.status, await res.text());
      return res.json() as Promise<ShareCreateResponse>;
    },
  });

export const useShareGet = (shareId: string | undefined) =>
  useQuery<ShareResponse, ShareError>({
    queryKey: ['/api/query/share', shareId],
    enabled: Boolean(shareId),
    queryFn: async () => {
      const res = await fetch(`/api/query/share/${shareId}`);
      if (!res.ok) throw new ShareError(res.status, await res.text());
      return res.json() as Promise<ShareResponse>;
    },
  });
```

- [ ] **Step 4: Run the test**

Run: `task pnpm test -- hooks/use-share.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add hyperglass/ui/hooks/use-share.ts hyperglass/ui/hooks/use-share.test.tsx
git commit -m "feat(ui): add useShareCreate (POST) and useShareGet (GET) hooks"
```

### Task 3.4: `useLGQuery` accepts `force`

**Files:**
- Modify: `hyperglass/ui/hooks/use-lg-query.ts`

- [ ] **Step 1: Read the current hook**

Run: `cat hyperglass/ui/hooks/use-lg-query.ts`

- [ ] **Step 2: Extend the request body**

Find the body construction (currently `{ queryLocation, queryTarget, queryType }`). Make the hook accept an optional `force` parameter (or read from a Zustand selector — pick whichever pattern matches the existing call sites).

A minimal change: add an optional `force?: boolean` to the call args, default omitted, and include in the POST body when truthy. The cache key in React Query should also include `force` so a forced fetch isn't deduped with a regular fetch:

```ts
return useQuery({
  queryKey: ['/api/query', { ...query, force }],
  queryFn: async () => {
    const body = { ...query, ...(force ? { force: true } : {}) };
    // ... existing fetch ...
  },
});
```

- [ ] **Step 3: Add a unit test for the force-passthrough**

In `hyperglass/ui/hooks/use-lg-query.test.tsx` (or extend an existing test if present), assert that calling with `force: true` includes `"force": true` in the POST body and produces a distinct cache key.

- [ ] **Step 4: Run UI tests**

Run: `task pnpm test`
Expected: green.

- [ ] **Step 5: Commit**

```bash
git add hyperglass/ui/hooks/
git commit -m "feat(ui): pass-through force flag in useLGQuery"
```

---

## Chunk 4: Frontend UI components, i18n, and form pre-fill

### Task 4.1: Add new strings to backend `Text` model

**Files:**
- Modify: `hyperglass/models/config/web.py:100-129` (the `Text` class)
- Test: extend `hyperglass/models/config/tests/test_web.py` (create if absent)

- [ ] **Step 1: Write failing test**

```python
"""Tests for new Text fields supporting the share feature."""

# Project
from hyperglass.models.config.web import Text


def test_text_share_defaults():
    t = Text()
    assert t.share_button == "Share"
    assert "{expires}" in t.share_expires_at
    assert "{timestamp}" in t.share_snapshot_banner
    assert t.share_not_found
    assert t.refresh_cooldown
```

- [ ] **Step 2: Run the test**

Run: `pytest hyperglass/models/config/tests/test_web.py -v`
Expected: FAIL.

- [ ] **Step 3: Add fields to `Text`**

Append to `Text` in `hyperglass/models/config/web.py`:

```python
    share_button: str = "Share"
    share_popover_title: str = "Share this result"
    share_copy_link: str = "Copy link"
    share_link_copied: str = "Copied!"
    share_expires_at: str = "Expires {expires}"  # JS-formatted
    share_create_error: str = "Could not create share link."
    share_create_expired: str = "This result has expired from cache. Refresh and try again."
    share_not_found: str = "Share not found or expired."
    share_snapshot_banner: str = "Snapshot taken at {timestamp}"  # JS-formatted
    share_run_fresh_query: str = "Run a fresh query"
    refresh_cooldown: str = "Refresh available in {seconds}s"  # JS-formatted
```

- [ ] **Step 4: Run the test**

Run: `pytest hyperglass/models/config/tests/test_web.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add hyperglass/models/config/web.py hyperglass/models/config/tests/test_web.py
git commit -m "feat(config): add share/refresh string fields to Text"
```

### Task 4.2: `RequeryButton` cooldown gate + force flag

**Files:**
- Modify: `hyperglass/ui/components/results/requery-button.tsx`
- Test: `hyperglass/ui/components/results/requery-button.test.tsx` (create or extend)

- [ ] **Step 1: Write the failing test**

```tsx
import { describe, it, expect } from 'vitest';
import { render, fireEvent, screen } from '@testing-library/react';
import { RequeryButton } from './requery-button';
// (...wrap in providers as in use-dns-query.test.tsx)

it('is disabled until refreshMinInterval elapses', async () => {
  // render with config.cache.refreshMinInterval = 5
  // mount; expect disabled
  // advance timers by 5s; expect enabled
});

it('invokes refetch with force=true on click', () => {
  // mount; advance past cooldown; click
  // expect refetch called with the force flag
});
```

(Use `vi.useFakeTimers()` to advance time deterministically.)

- [ ] **Step 2: Run the test**

Run: `task pnpm test -- requery-button.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Implement**

Update `requery-button.tsx` to:
1. Read `cache.refreshMinInterval` from `useConfig()`.
2. Track elapsed-since-mount; disable until `>= refreshMinInterval * 1000`.
3. On click, call `refetch({ force: true })` (the upstream React Query call site reads this from `queryKey`/`queryFn`; adapt to the existing signature in `use-lg-query.ts`).

- [ ] **Step 4: Run the test**

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add hyperglass/ui/components/results/requery-button.tsx hyperglass/ui/components/results/requery-button.test.tsx
git commit -m "feat(ui): add cooldown gate to RequeryButton, send force=true on click"
```

### Task 4.3: `ShareButton` component

**Files:**
- Create: `hyperglass/ui/components/results/share-button.tsx`
- Create: `hyperglass/ui/components/results/share-button.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent, screen, waitFor } from '@testing-library/react';
import { ShareButton } from './share-button';

it('hides itself when shareEnabled is false', () => {
  // render with config.cache.shareEnabled = false
  // expect button absent
});

it('opens popover with copy-link UI on click', async () => {
  // mock POST /api/query/share/<id> -> { id: 'aaa', url: '...', expiresAt: '...' }
  // render; click button; expect popover and link visible
});

it('copies URL to clipboard on copy click', async () => {
  // mock writeText; click copy; expect mock called with the share URL
});

it('shows expired-cache message on 410', async () => {
  // mock POST -> 410; render; click; expect configured share_create_expired text
});
```

- [ ] **Step 2: Run the test**

Run: `task pnpm test -- share-button.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Implement**

Use Chakra `Popover`/`Button`, the existing `useStrf()` + `useConfig()` patterns (see `header.tsx` as a model). Wire to `useShareCreate()`. Handle three states: idle, loading, error (410 vs other).

- [ ] **Step 4: Run the test**

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add hyperglass/ui/components/results/share-button.tsx hyperglass/ui/components/results/share-button.test.tsx
git commit -m "feat(ui): add ShareButton with copy-to-clipboard popover"
```

### Task 4.4: Wire `ShareButton` into result header

**Files:**
- Modify: `hyperglass/ui/components/results/individual.tsx` (or wherever `RequeryButton` is rendered)

- [ ] **Step 1: Locate the existing button placement**

Run: `grep -n "RequeryButton\|<Requery" hyperglass/ui/components/results/individual.tsx`
Expected: a JSX usage of `<RequeryButton ...>` inside the header section.

- [ ] **Step 2: Add `<ShareButton>` next to it**

Pass the response's `id` (the cache key) to the button.

- [ ] **Step 3: Manual verification later in Chunk 5.**

- [ ] **Step 4: Typecheck and lint**

Run: `task ui-typecheck && task ui-lint`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add hyperglass/ui/components/results/individual.tsx
git commit -m "feat(ui): place ShareButton next to RequeryButton in result header"
```

### Task 4.5: Form pre-fill from query string

**Files:**
- Modify: `hyperglass/ui/components/looking-glass-form.tsx`

- [ ] **Step 1: Write the failing test**

In a new or extended `looking-glass-form.test.tsx`:

```tsx
it('pre-fills location/target/type from query string on mount', () => {
  // Mock next/router useRouter to return { query: { location: 'test1', target: '192.0.2.0/24', type: 'juniper_bgp_route' } }
  // render the form
  // assert the inputs have those values
});
```

- [ ] **Step 2: Run the test**

Expected: FAIL.

- [ ] **Step 3: Implement**

In `looking-glass-form.tsx`, on mount, read `router.query.location|target|type` (URL-decoded) and call the form's `setValue` for each.

- [ ] **Step 4: Run the test**

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add hyperglass/ui/components/looking-glass-form.tsx hyperglass/ui/components/looking-glass-form.test.tsx
git commit -m "feat(ui): pre-fill form from ?location=&target=&type= query string"
```

---

## Chunk 5: Result share page and end-to-end verification

### Task 5.1: `pages/result/[id].tsx`

**Files:**
- Create: `hyperglass/ui/pages/result/[id].tsx`
- Create: `hyperglass/ui/pages/result/[id].test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import ResultPage from './[id]';

it('renders the snapshot output for a valid id', async () => {
  // Mock useRouter to return query.id = 'aaa'
  // Mock fetch /api/query/share/aaa -> 200 with snapshot
  // render; expect output text + snapshot banner with timestamp
});

it('shows configured "share not found" message on 404', async () => {
  // Mock fetch -> 404
  // render; expect the configured share_not_found text
});

it('exposes the "Run a fresh query" CTA with prefill query string', async () => {
  // 200 path
  // expect a link to /?location=test1&target=192.0.2.0%2F24&type=juniper_bgp_route
});
```

- [ ] **Step 2: Run the test**

Run: `task pnpm test -- pages/result/`
Expected: FAIL.

- [ ] **Step 3: Implement the page**

```tsx
// hyperglass/ui/pages/result/[id].tsx
import { useRouter } from 'next/router';
import { useShareGet } from '~/hooks/use-share';
// ... use the existing Result component shape, in a read-only mode ...
```

The page reads `router.query.id`, calls `useShareGet`, renders a snapshot banner ("snapshot taken at {timestamp}, expires {expires}") above the existing read-only Result component, and includes a "Run a fresh query" link with pre-filled query params.

The Result component currently pulls everything from the Zustand store (per the survey). The cleanest landing is one of:
- Refactor `Results` (`components/results/group.tsx`) to optionally accept a snapshot prop, falling back to store reads when absent.
- Or, directly use the lower-level `Result` (`components/results/individual.tsx`) for share rendering, in a read-only branch.

Pick whichever minimizes diff in the existing form path. Document the choice in the commit message.

- [ ] **Step 4: Run the test**

Expected: PASS.

- [ ] **Step 5: Typecheck, lint, format**

Run: `task ui-typecheck && task ui-lint && task ui-format`

- [ ] **Step 6: Commit**

```bash
git add hyperglass/ui/pages/result hyperglass/ui/components/results/
git commit -m "feat(ui): add /result/[id] share view page"
```

### Task 5.2: Verify static-export SPA fallback covers `/result/<id>`

**Files:**
- (Possibly) Modify: `hyperglass/api/__init__.py` if `html_mode=True` does not cover the case.

- [ ] **Step 1: Build the UI**

Run: `task ui-build`
Expected: build succeeds, output under `hyperglass/static/ui/`.

- [ ] **Step 2: Start the backend**

Run: `task start`
Expected: server up on port 8001 (or configured port).

- [ ] **Step 3: Test the SPA fallback**

In another shell:

```bash
curl -i http://127.0.0.1:8001/result/aB3kF9pQ2x_
```

Expected: 200 OK with `Content-Type: text/html` returning the SPA's `index.html`.

- [ ] **Step 4 (only if Step 3 returned 404):** Add explicit Litestar route handler

In `hyperglass/api/__init__.py`, before the static-files router at line 53, add:

```python
import re
from pathlib import Path
from litestar import get
from litestar.response import File

@get("/result/{share_id:str}", include_in_schema=False)
async def share_view_html(share_id: str) -> File:
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", share_id):
        raise NotFoundException()
    return File(path=UI_DIR / "index.html", media_type="text/html")
```

Add it to `HANDLERS` ahead of the static-files mount.

Then re-run Step 3 and confirm 200.

- [ ] **Step 5: Commit (if changes made)**

```bash
git add hyperglass/api/__init__.py
git commit -m "feat(api): explicit /result/<id> route handler when html_mode is insufficient"
```

(Skip if `html_mode=True` already covered it; record that fact in the next task's smoke-test notes.)

### Task 5.3: Operator docs and CHANGELOG

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `docs/pages/configuration/` (find the cache config page; if none, add a brief note in the existing config index)

- [ ] **Step 1: Document the `cache.timeout` default change**

In `CHANGELOG.md`, under the Unreleased section, note:

> **Behavior change:** `cache.timeout` default raised from 120s → 600s. End-user UX is preserved by `cache.refresh_min_interval` (UI cooldown, default 120s) and the new `force` flag, but operators relying on 2-minute staleness should set `cache.timeout: 120` explicitly to retain the old behavior.

- [ ] **Step 2: Document the share feature**

In the relevant docs page (likely under `docs/pages/configuration/`), add a section describing:
- `cache.share_enabled`, `cache.share_timeout`, `cache.share_sliding`, `cache.refresh_min_interval`
- `params.public_url` for stable share URLs behind a proxy
- The `/result/<id>` URL shape
- Note that disabling sharing requires a UI rebuild (build-time `hyperglass.json`)

- [ ] **Step 3: Commit**

```bash
git add CHANGELOG.md docs/
git commit -m "docs: document share-results feature and cache.timeout default change"
```

### Task 5.4: End-to-end smoke test

- [ ] **Step 1: Boot stack against fake_output**

Set `params.fake_output: true` in your dev config, then `task start`.

- [ ] **Step 2: Run a query in the browser**

- Open `http://127.0.0.1:8001/`
- Submit a real-shaped query (any device + target + type your seed config has)

- [ ] **Step 3: Verify Share button**

- Confirm Share button is visible in the result header
- Click Share → confirm popover opens with a `/result/<id>` URL
- Click Copy → confirm clipboard contains the URL

- [ ] **Step 4: Open the share URL incognito**

- Confirm the snapshot renders with the banner
- Confirm output matches what you saw in the original result

- [ ] **Step 5: Verify refresh cooldown**

- Click Refresh < 120s after submitting → confirm disabled with cooldown message
- Wait > 120s → confirm enabled, click → confirm new query result and a new shareable id

- [ ] **Step 6: Verify expired-cache 410**

- Run a query
- Manually set the cache TTL to 1s: `redis-cli EXPIRE hyperglass.state.hyperglass.query.<digest> 1`, wait
- Click Share → confirm the configured `share_create_expired` message

- [ ] **Step 7: Verify share-not-found**

- Open `http://127.0.0.1:8001/result/notarealid` → confirm the configured `share_not_found` message

- [ ] **Step 8: Sign-off commit (if any deltas surfaced)**

```bash
git add -A
git commit -m "test: smoke test fixes for share-results"  # if needed
```

### Task 5.5: Final lint / format / typecheck

- [ ] **Step 1: Backend**

Run: `task lint && task format && task sort && task test`
Expected: all clean and green.

- [ ] **Step 2: Frontend**

Run: `task ui-typecheck && task ui-lint && task ui-format && task pnpm test`
Expected: all clean and green.

- [ ] **Step 3: Combined check**

Run: `task check`
Expected: clean.

- [ ] **Step 4: Final commit (if needed)**

```bash
git add -A
git commit -m "chore: final lint/format pass for share-results"
```
