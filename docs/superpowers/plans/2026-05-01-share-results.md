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

- [x] **Step 1: Create the conftest with shared fixtures**

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

- [x] **Step 2: Verify existing tests still pass**

Run: `task test -- hyperglass/state/tests/`
Expected: all green. (We didn't break the duplicated fixtures in `state/tests/test_hooks.py` — pytest resolves the closer one.)

- [x] **Step 3: Commit**

```bash
git add hyperglass/conftest.py
git commit -m "test: add top-level conftest with shared state fixtures"
```

### Task 1.2: API test scaffolding (TestClient fixture)

**Files:**
- Create: `hyperglass/api/tests/__init__.py`
- Create: `hyperglass/api/tests/conftest.py`
- Create: `hyperglass/api/tests/test_smoke.py`

- [x] **Step 1: Create the `__init__.py` package marker**

Empty file:

```python
```

- [x] **Step 2: Create the API conftest**

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

- [x] **Step 3: Write a smoke test**

```python
"""Smoke test that the API test scaffolding works."""


def test_devices_endpoint_returns_seeded_device(client):
    response = client.get("/api/devices")
    assert response.status_code == 200
    payload = response.json()
    assert any(d.get("name") == "test1" for d in payload)
```

- [x] **Step 4: Run the smoke test**

Run: `task test -- hyperglass/api/tests/test_smoke.py -v`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add hyperglass/api/tests/
git commit -m "test(api): add TestClient fixture and smoke test"
```

### Task 1.3: Extend `Cache` config model

**Files:**
- Modify: `hyperglass/models/config/cache.py`
- Test: `hyperglass/models/config/tests/test_cache.py` (create if absent)

- [x] **Step 1: Write failing tests for the new fields**

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

- [x] **Step 2: Run the test to verify it fails**

Run: `pytest hyperglass/models/config/tests/test_cache.py -v`
Expected: FAIL — fields don't exist yet.

- [x] **Step 3: Add the fields**

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

- [x] **Step 4: Run the test to verify it passes**

Run: `pytest hyperglass/models/config/tests/test_cache.py -v`
Expected: PASS.

- [x] **Step 5: Run lint**

Run: `task lint`
Expected: clean.

- [x] **Step 6: Commit**

```bash
git add hyperglass/models/config/cache.py hyperglass/models/config/tests/
git commit -m "feat(config): add share_timeout/share_enabled/share_sliding/refresh_min_interval, bump timeout default to 600"
```

### Task 1.4: Add `force` field to Query model

**Files:**
- Modify: `hyperglass/models/api/query.py`
- Test: `hyperglass/models/api/tests/test_query_force.py` (create)

- [x] **Step 1: Write the failing test**

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

- [x] **Step 2: Run the test to verify it fails**

Run: `pytest hyperglass/models/api/tests/test_query_force.py -v`
Expected: FAIL on `q.force is False` (attribute doesn't exist).

- [x] **Step 3: Add the field**

In `hyperglass/models/api/query.py`, in the `Query` class — **after `query_type` (line 53) and BEFORE `_kwargs: t.Dict[str, t.Any]` (line 54)** — add:

```python
    # Bypass cache and re-execute when True.
    force: bool = False
```

`Query.__repr__` currently returns `repr_from_attrs(self, ("query_location", "query_type", "query_target"))` (line 91). Do **not** add `force` to that tuple — it must not affect the digest.

- [x] **Step 4: Run the test to verify it passes**

Run: `pytest hyperglass/models/api/tests/test_query_force.py -v`
Expected: PASS.

- [x] **Step 5: Run full test suite to confirm no regressions**

Run: `task test`
Expected: all green.

- [x] **Step 6: Commit**

```bash
git add hyperglass/models/api/query.py hyperglass/models/api/tests/
git commit -m "feat(api): add Query.force flag to bypass cache; excluded from digest"
```

### Task 1.5: Add `public_url` field to `Params`

**Files:**
- Modify: `hyperglass/models/config/params.py`
- Test: `hyperglass/models/config/tests/test_params_public_url.py` (create)

- [x] **Step 1: Write the failing test**

```python
"""Tests for Params.public_url."""

# Project
from hyperglass.models.config.params import Params


def test_public_url_default_none():
    p = Params()
    assert p.public_url is None


def test_public_url_set_to_https_url():
    p = Params(public_url="https://lg.example.com")
    # Pydantic AnyHttpUrl normalization varies across 2.x patch versions
    # (sometimes adds trailing slash, sometimes preserves). Use startswith
    # so the test is robust to either form.
    assert str(p.public_url).startswith("https://lg.example.com")
```

- [x] **Step 2: Run the test to verify it fails**

Run: `pytest hyperglass/models/config/tests/test_params_public_url.py -v`
Expected: FAIL.

- [x] **Step 3: Add the field**

In `hyperglass/models/config/params.py`, near the top of the `Params` class (after existing fields), add:

```python
    public_url: t.Optional[AnyHttpUrl] = None
```

Add `from pydantic import AnyHttpUrl` to the imports if not already present.

- [x] **Step 4: Run the test**

Run: `pytest hyperglass/models/config/tests/test_params_public_url.py -v`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add hyperglass/models/config/params.py hyperglass/models/config/tests/test_params_public_url.py
git commit -m "feat(config): add optional Params.public_url for share URL building"
```

### Task 1.6: Extend `Params.frontend()` include set

**Files:**
- Modify: `hyperglass/models/config/params.py:153-168`
- Test: `hyperglass/models/config/tests/test_params_frontend.py` (create)

- [x] **Step 1: Write the failing test**

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

- [x] **Step 2: Run the test**

Run: `pytest hyperglass/models/config/tests/test_params_frontend.py -v`
Expected: FAIL (fields not yet projected).

- [x] **Step 3: Modify the include set**

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

- [x] **Step 4: Run the test**

Run: `pytest hyperglass/models/config/tests/test_params_frontend.py -v`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add hyperglass/models/config/params.py hyperglass/models/config/tests/test_params_frontend.py
git commit -m "feat(config): project share UI knobs through Params.frontend()"
```

### Task 1.7: Add response models — `id` on `QueryResponse`, plus `ShareCreateResponse` and `ShareResponse`

**Files:**
- Modify: `hyperglass/models/api/response.py`
- Test: `hyperglass/models/api/tests/test_response_models.py` (create)

- [x] **Step 1: Read the existing response module to learn its conventions**

Run: `cat hyperglass/models/api/response.py`

Note the existing `QueryResponse`:
- It is a Pydantic `BaseModel`-derived class with `model_config = ConfigDict(json_schema_extra=...)` — **no `alias_generator`** today.
- `timestamp: str` (not `datetime`) — wire format is a string.
- The route handler at `routes.py:148-158` already injects `id: str` into the response dict but the model does not declare it.

The existing module does **not** import `datetime` or `snake_to_camel`. Add them in Step 4.

For wire-format consistency with the spec ("camelCase on the wire"), the new share models will use `alias_generator=snake_to_camel`. `QueryResponse`'s existing fields are all single-word (`cached`, `runtime`, `timestamp`, `format`, `random`, `level`, `keywords`, plus the new `id`), so we also add the same `alias_generator` to it for consistency — single-word field aliases are no-ops, so behavior is unchanged. **Do not change `QueryResponse.timestamp`'s type from `str` to `datetime`** — that's a separate decision out of scope here.

- [x] **Step 2: Write failing tests**

Create `hyperglass/models/api/tests/__init__.py` (empty) if needed, then `test_response_models.py`:

```python
"""Tests for share response models."""

# Standard Library
from datetime import datetime, timezone

# Project
from hyperglass.models.api.response import (
    QueryResponse, ShareCreateResponse, ShareResponse,
)


def test_query_response_includes_id():
    # `timestamp` is a string per the existing QueryResponse contract.
    r = QueryResponse(
        output="ok",
        id="hyperglass.query.deadbeef",
        cached=False,
        runtime=1,
        timestamp="2026-05-01 12:00:00",
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
    # camelCase alias on the wire
    dumped = r.model_dump(by_alias=True)
    assert "expiresAt" in dumped


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
    # Note: alias_generator only affects the model's own fields, not nested
    # dict keys. `r.query["query_location"]` stays snake_case on the wire.
    dumped = r.model_dump(by_alias=True)
    assert dumped["query"]["query_location"] == "test1"
```

- [x] **Step 3: Run the test**

Run: `pytest hyperglass/models/api/tests/test_response_models.py -v`
Expected: FAIL — `id`, `ShareCreateResponse`, `ShareResponse` don't exist yet.

- [x] **Step 4: Add imports and update `QueryResponse`**

In `hyperglass/models/api/response.py`, add to the imports:

```python
from datetime import datetime
from pydantic import ConfigDict
from hyperglass.util import snake_to_camel
```

(Some of these may already be imported — check first; do not duplicate.)

Add `alias_generator=snake_to_camel, populate_by_name=True` to `QueryResponse.model_config`, and add `id: str` to its fields. The existing fields are unchanged; the alias generator is a no-op for single-word names.

- [x] **Step 5: Add the new models**

Append to `hyperglass/models/api/response.py`:

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

`query` and `query_labels` are typed `t.Dict[str, t.Any]` / `t.Dict[str, str]` — generic dicts. **The `alias_generator` does NOT camelCase keys inside these nested dicts.** On the wire, `response.query.query_location` stays as `query_location`, not `queryLocation`. Tests in Chunk 2 assert against this snake_case shape.

- [x] **Step 6: Run the test**

Run: `pytest hyperglass/models/api/tests/test_response_models.py -v`
Expected: PASS.

- [x] **Step 7: Commit**

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

- [x] **Step 1: Write the failing test**

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

- [x] **Step 2: Run test to verify it fails**

Run: `task test -- hyperglass/api/tests/test_routes_query.py -v`
Expected: FAIL — `query`, `query_labels`, `format`, `runtime`, `level` are not in the cache map.

- [x] **Step 3: Implement the cache-write expansion**

This change has three parts: (a) compute `response_format` and `query_labels` BEFORE the cache write, (b) write the expanded fields, (c) **remove the now-redundant post-write re-read** at lines 138-145.

In `hyperglass/api/routes.py`, in the cache-miss branch (lines 96-134), replace:

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

Then **delete** the post-write re-read block (lines 138-145):

```python
# DELETE these lines — they're now redundant since response_format
# is already set:
cache_response = cache.get_map(cache_key, "output")
json_output = is_type(cache_response, t.Dict)
response_format = "text/plain"
if json_output:
    response_format = "application/json"
```

The cache-hit branch (lines 81-95) still needs `response_format` set; on a cache hit, read it from the map: `response_format = cache.get_map(cache_key, "format")`. Add this read inside the cache-hit branch.

The `response = {...}` literal (lines 148-158) keeps its existing shape; `cache_response` (the output to return) is now `raw_output` on miss or `cache.get_map(cache_key, "output")` on hit — adjust the dict assembly to use whichever is in scope.

- [x] **Step 4: Run test to verify it passes**

Run: `task test -- hyperglass/api/tests/test_routes_query.py -v`
Expected: PASS.

- [x] **Step 5: Run full backend test suite**

Run: `task test`
Expected: green.

- [x] **Step 6: Commit**

```bash
git add hyperglass/api/routes.py hyperglass/api/tests/test_routes_query.py
git commit -m "feat(api): expand /api/query cache write with full snapshot fields"
```

### Task 2.2: Honor `force` flag in `/api/query`

**Files:**
- Modify: `hyperglass/api/routes.py:81-95` (the cache-hit branch)
- Test: `hyperglass/api/tests/test_routes_query.py` (extend)

- [x] **Step 1: Write the failing test**

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

- [x] **Step 2: Run the test**

Run: `task test -- hyperglass/api/tests/test_routes_query.py::test_force_skips_cache_hit -v`
Expected: FAIL — third call is reported as cached.

- [x] **Step 3: Implement**

In `hyperglass/api/routes.py`, replace the start of the cache-hit branch:

```python
cache_response = cache.get_map(cache_key, "output")
```

With:

```python
cache_response = None if data.force else cache.get_map(cache_key, "output")
```

Do not pre-delete the cache key; on execution failure, the existing entry stays intact.

- [x] **Step 4: Run the test**

Run: `task test -- hyperglass/api/tests/test_routes_query.py -v`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add hyperglass/api/routes.py hyperglass/api/tests/test_routes_query.py
git commit -m "feat(api): /api/query honors force flag to bypass cache"
```

### Task 2.3: `_generate_share_id` helper

**Files:**
- Modify: `hyperglass/api/routes.py` (add helper near top)
- Test: `hyperglass/api/tests/test_share_helpers.py` (create)

- [x] **Step 1: Write the failing test**

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

- [x] **Step 2: Run the test**

Run: `task test -- hyperglass/api/tests/test_share_helpers.py -v`
Expected: FAIL — helper doesn't exist.

- [x] **Step 3: Implement**

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

- [x] **Step 4: Run the test**

Run: `task test -- hyperglass/api/tests/test_share_helpers.py -v`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add hyperglass/api/routes.py hyperglass/api/tests/test_share_helpers.py
git commit -m "feat(api): add _generate_share_id helper with collision retry"
```

### Task 2.4: `_build_share_url` helper

**Files:**
- Modify: `hyperglass/api/routes.py`
- Test: `hyperglass/api/tests/test_share_helpers.py` (extend)

- [x] **Step 1: Write the failing test**

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

- [x] **Step 2: Run the test**

Run: `task test -- hyperglass/api/tests/test_share_helpers.py -v`
Expected: FAIL.

- [x] **Step 3: Implement**

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

- [x] **Step 4: Run the test**

Run: `task test -- hyperglass/api/tests/test_share_helpers.py -v`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add hyperglass/api/routes.py hyperglass/api/tests/test_share_helpers.py
git commit -m "feat(api): add _build_share_url helper with public_url and proxy fallback"
```

### Task 2.5: `POST /api/query/share/{cache_id}` endpoint

**Files:**
- Modify: `hyperglass/api/routes.py`
- Modify: `hyperglass/api/__init__.py` (register the new handler)
- Test: `hyperglass/api/tests/test_routes_share.py` (create)

- [x] **Step 1: Write the failing tests**

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
    # state.redis.delete() automatically applies the namespace prefix.
    state.redis.delete(f"hyperglass.query.{digest}")

    r = client.post(f"/api/query/share/{cache_id}")
    assert r.status_code == 410


class TestShareDisabled:
    """Verifies the disabled-feature kill switch by overriding the
    module-level `params` fixture for tests in this class."""

    @pytest.fixture
    def params(self) -> dict:
        return {"fake_output": True, "cache": {"share_enabled": False}}

    def test_share_create_404(self, client):
        # Even with no cache entry, the disabled gate fires first.
        r = client.post("/api/query/share/hyperglass.query.deadbeef")
        assert r.status_code == 404
```

- [x] **Step 2: Run the tests**

Run: `task test -- hyperglass/api/tests/test_routes_share.py -v`
Expected: FAIL — endpoint doesn't exist (returns 404 for routing reasons, but the body assertions fail).

- [x] **Step 3: Implement the endpoint**

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

- [x] **Step 4: Register the route**

In `hyperglass/api/__init__.py`, the `HANDLERS` list lives at lines 39-45 (initial) and 47-56 (with UI handlers). Add `share_create` to the imports from `hyperglass.api.routes` near line 38 and append it to the `HANDLERS` list before the `if not STATE.settings.disable_ui:` block.

- [x] **Step 5: Run the tests**

Run: `task test -- hyperglass/api/tests/test_routes_share.py -v`
Expected: PASS.

- [x] **Step 6: Commit**

```bash
git add hyperglass/api/routes.py hyperglass/api/__init__.py hyperglass/api/tests/test_routes_share.py
git commit -m "feat(api): add POST /api/query/share/{cache_id} for share creation"
```

### Task 2.6: `GET /api/query/share/{share_id}` endpoint

**Files:**
- Modify: `hyperglass/api/routes.py`
- Modify: `hyperglass/api/__init__.py`
- Test: `hyperglass/api/tests/test_routes_share.py` (extend)

- [x] **Step 1: Write the failing tests**

Append to `test_routes_share.py`:

```python
def test_share_get_returns_full_snapshot(client):
    cache_id = _seed_query(client)
    create_resp = client.post(f"/api/query/share/{cache_id}").json()

    r = client.get(f"/api/query/share/{create_resp['id']}")
    assert r.status_code == 200
    body = r.json()
    assert body["shared"] is True
    # The model's own fields are aliased to camelCase. Keys inside the
    # nested `query` dict are NOT aliased (they're a generic dict, see
    # Task 1.7 Step 5 note). They stay snake_case.
    assert body["query"]["query_location"] == "test1"
    assert body["queryLabels"]["type"] == "BGP Route"
    assert "createdAt" in body
    assert "expiresAt" in body


def test_share_get_404_when_missing(client):
    r = client.get("/api/query/share/nonexistent1")
    assert r.status_code == 404


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
    @pytest.fixture
    def params(self) -> dict:
        return {
            "fake_output": True,
            "cache": {"share_sliding": False, "share_timeout": 600},
        }

    def test_get_does_not_extend_ttl(self, client, state):
        cache_id = _seed_query(client)
        share_id = client.post(f"/api/query/share/{cache_id}").json()["id"]
        full_key = state.redis.key(f"hyperglass.share.{share_id}")

        state.redis.instance.expire(full_key, 60)
        client.get(f"/api/query/share/{share_id}")
        ttl = state.redis.instance.ttl(full_key)
        assert ttl <= 60  # not extended
```

`RedisManager` (see `hyperglass/state/redis.py`) does not expose `.ttl()` directly and `.expire(...)` is keyword-only (`expire_in=` / `expire_at=`). For tests that need raw Redis operations, drop down to `state.redis.instance` (the underlying `redis.Redis` client) and use `state.redis.key(<logical_key>)` to get the namespaced full key.

- [x] **Step 2: Run the tests**

Run: `task test -- hyperglass/api/tests/test_routes_share.py -v`
Expected: FAIL — endpoint not yet defined.

- [x] **Step 3: Implement the endpoint**

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

- [x] **Step 4: Run the tests**

Run: `task test -- hyperglass/api/tests/test_routes_share.py -v`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add hyperglass/api/routes.py hyperglass/api/__init__.py hyperglass/api/tests/test_routes_share.py
git commit -m "feat(api): add GET /api/query/share/{share_id} with optional sliding TTL"
```

### Task 2.7: Lint and full backend regression

- [x] **Step 1: Run Ruff**

Run: `task lint`
Expected: clean (zero errors per CONTRIBUTING.md).

- [x] **Step 2: Run Black + isort**

Run: `task format && task sort`
Expected: no changes (or stage and commit any formatting deltas).

- [x] **Step 3: Run full test suite**

Run: `task test`
Expected: all green.

- [x] **Step 4: Commit any formatting deltas**

```bash
git add -A
git commit -m "style: apply ruff/black/isort to share feature"  # only if needed
```

---

## Chunk 3: Frontend types and API hook

### Task 3.1: Update `Config` types — `_Cache` and `_Text`

**Files:**
- Modify: `hyperglass/ui/types/config.ts`

**Important:** the underscore-prefixed interfaces (`_Cache`, `_Text`, etc.) hold the **raw snake_case shape** that mirrors the backend JSON (`hyperglass.json`). The exported camelCase types (`Cache`, `Text`, …) are derived via `type-fest`'s `CamelCasedPropertiesDeep` at the export boundary (line ~175). Add new fields in **snake_case**, matching backend field names.

- [x] **Step 1: Read the existing `_Cache` and `_Text` interfaces**

Run: `grep -n "_Cache\|_Text" hyperglass/ui/types/config.ts`
Expected: `_Cache` around line 137; `_Text` around line 25.

- [x] **Step 2: Update `_Cache`**

In `hyperglass/ui/types/config.ts`, replace:

```typescript
interface _Cache {
  show_text: boolean;
  timeout: number;
}
```

With:

```typescript
interface _Cache {
  show_text: boolean;
  timeout: number;
  share_enabled: boolean;
  share_timeout: number;
  refresh_min_interval: number;
}
```

- [x] **Step 3: Add new fields to `_Text`** in snake_case (will be populated by Task 4.1 backend Text model fields)

Add to `_Text` (existing fields are all snake_case — match the convention):

```typescript
  share_button: string;
  share_popover_title: string;
  share_copy_link: string;
  share_link_copied: string;
  share_expires_at: string;
  share_create_error: string;
  share_create_expired: string;
  share_not_found: string;
  share_snapshot_banner: string;
  share_run_fresh_query: string;
  refresh_cooldown: string;
```

When consumers do `useConfig().web.text.shareButton`, the `CamelCasedProperties` transform converts these to camelCase access automatically.

- [x] **Step 4: Typecheck**

Run: `task ui-typecheck`
Expected: PASS — but note this won't catch missing backend fields until the JSON config is rebuilt; that's fine.

- [x] **Step 5: Commit**

```bash
git add hyperglass/ui/types/config.ts
git commit -m "feat(ui): extend Config types with share knobs and text strings"
```

### Task 3.2: Update `globals.d.ts` — `QueryResponse`, `ShareResponse`, `force`

**Files:**
- Modify: `hyperglass/ui/types/globals.d.ts`

**Important context:** `globals.d.ts` is wrapped in a `declare global { ... }` block (line 1). All new global types must be added INSIDE that block, otherwise hooks in Task 3.3 cannot reference `ShareResponse` / `ShareCreateResponse` without explicit imports. The existing `QueryResponse` is a `type` alias (not `interface`) and currently has fields `random`, `cached`, `runtime`, `level`, `timestamp`, `keywords`, `output`, `format`. It does NOT have `id` today — the backend route returns `id` in the response dict (see `routes.py:148-150`) but the type is missing it.

- [x] **Step 1: Locate the existing types**

Run: `grep -n "type QueryResponse\|declare global" hyperglass/ui/types/globals.d.ts`
Expected: `declare global` near line 1; `type QueryResponse` near line 44.

- [x] **Step 2: Add `id` to the existing `QueryResponse` type alias**

In `hyperglass/ui/types/globals.d.ts`, find:

```typescript
  type QueryResponse = {
    random: string;
    cached: boolean;
    runtime: number;
    level: ResponseLevel;
    timestamp: string;
    keywords: string[];
    output: string | StructuredResponse;
    format: 'text/plain' | 'application/json';
  };
```

Add `id: string;` as the first field:

```typescript
  type QueryResponse = {
    id: string;
    random: string;
    cached: boolean;
    runtime: number;
    level: ResponseLevel;
    timestamp: string;
    keywords: string[];
    output: string | StructuredResponse;
    format: 'text/plain' | 'application/json';
  };
```

- [x] **Step 3: Add `ShareResponse` and `ShareCreateResponse` inside the `declare global { ... }` block**

Add immediately after `type QueryResponse = { ... };`:

```typescript
  type ShareResponse = {
    id: string;
    output: string | StructuredResponse;
    cached: boolean;
    shared: boolean;
    runtime: number;
    timestamp: string;
    format: string;
    level: ResponseLevel;
    keywords: string[];
    // Nested dict keys are NOT camelCased by backend pydantic; keep snake_case.
    query: { query_location: string; query_target: string | string[]; query_type: string };
    queryLabels: { location: string; type: string };
    createdAt: string;
    expiresAt: string;
  };

  type ShareCreateResponse = {
    id: string;
    url: string;
    expiresAt: string;
  };
```

- [x] **Step 4: Add `force?: boolean` to `FormQuery`**

`FormQuery` is defined in `hyperglass/ui/types/data.ts:7` as `Swap<FormData, 'queryLocation', string>`. Adding `force` to `FormData` would propagate to the form schema (undesirable). Cleanest approach: extend `FormQuery` directly:

```typescript
// In hyperglass/ui/types/data.ts
export type FormQuery = Swap<FormData, 'queryLocation', string> & { force?: boolean };
```

Verify the change compiles by running `task ui-typecheck` (Step 5 below).

- [x] **Step 5: Typecheck**

Run: `task ui-typecheck`
Expected: PASS.

- [x] **Step 6: Commit**

```bash
git add hyperglass/ui/types/globals.d.ts hyperglass/ui/types/data.ts
git commit -m "feat(ui): add id to QueryResponse, add ShareResponse, add force? to FormQuery"
```

### Task 3.3: `useShareCreate` and `useShareGet` hooks

**Files:**
- Create: `hyperglass/ui/hooks/use-share.ts`
- Create: `hyperglass/ui/hooks/use-share.test.tsx`

**Note on test pattern:** there is no existing `fetch` mock pattern in this codebase (`use-dns-query.test.tsx` hits real network). This task introduces a new pattern: monkeypatch `global.fetch` per-test via `vi.fn()`. Document this choice in the test file's docstring so future contributors recognize the pattern.

- [x] **Step 1: Write the failing test**

```tsx
/**
 * Tests for useShareCreate / useShareGet.
 * Pattern: mock global.fetch per-test with vi.fn(). Resets between tests.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useShareCreate, useShareGet } from './use-share';

const wrapper = ({ children }: { children: React.ReactNode }) => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
};

const mockResponse = (overrides: Partial<Response>) =>
  ({
    ok: true,
    status: 200,
    json: async () => ({}),
    text: async () => '',
    ...overrides,
  } as unknown as Response);

beforeEach(() => {
  global.fetch = vi.fn();
});

describe('useShareCreate', () => {
  it('POSTs to /api/query/share/<cacheId> and returns the response', async () => {
    (global.fetch as any).mockResolvedValue(mockResponse({
      json: async () => ({ id: 'aaaaaaaaaaa', url: 'https://x/result/aaaaaaaaaaa', expiresAt: '2026-05-08T00:00:00Z' }),
    }));
    const { result } = renderHook(() => useShareCreate(), { wrapper });
    result.current.mutate('hyperglass.query.deadbeef');
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(global.fetch).toHaveBeenCalledWith(
      '/api/query/share/hyperglass.query.deadbeef',
      expect.objectContaining({ method: 'POST' }),
    );
    expect(result.current.data?.id).toBe('aaaaaaaaaaa');
  });

  it('surfaces 410 as a ShareError with status', async () => {
    (global.fetch as any).mockResolvedValue(mockResponse({ ok: false, status: 410 }));
    const { result } = renderHook(() => useShareCreate(), { wrapper });
    result.current.mutate('expired-id');
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect((result.current.error as any).status).toBe(410);
  });
});

describe('useShareGet', () => {
  it('GETs /api/query/share/<id> and returns the snapshot', async () => {
    (global.fetch as any).mockResolvedValue(mockResponse({
      json: async () => ({ id: 'aaa', shared: true, output: 'x', cached: true, runtime: 1, timestamp: '', format: 'text/plain', level: 'success', keywords: [], query: {}, queryLabels: {}, createdAt: '', expiresAt: '' }),
    }));
    const { result } = renderHook(() => useShareGet('aaa'), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(global.fetch).toHaveBeenCalledWith('/api/query/share/aaa', expect.anything());
    expect(result.current.data?.shared).toBe(true);
  });

  it('does not fetch when shareId is undefined (enabled: false)', async () => {
    renderHook(() => useShareGet(undefined), { wrapper });
    // Yield a tick so React Query has a chance to fire (it should not).
    await new Promise(r => setTimeout(r, 0));
    expect(global.fetch).not.toHaveBeenCalled();
  });
});
```

The `mockResponse` helper provides both `.json()` and `.text()` so error paths that read the body don't trip on a missing method.

- [x] **Step 2: Run the test**

Run: `task pnpm test -- hooks/use-share.test.tsx`
Expected: FAIL — module doesn't exist.

- [x] **Step 3: Implement**

```ts
// hyperglass/ui/hooks/use-share.ts
import { useMutation, useQuery } from '@tanstack/react-query';

export class ShareError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

const parseError = async (res: Response): Promise<string> => {
  try {
    return (await res.text()) || res.statusText;
  } catch {
    return res.statusText;
  }
};

export const useShareCreate = () =>
  useMutation<ShareCreateResponse, ShareError, string>({
    mutationFn: async (cacheId: string) => {
      const res = await fetch(`/api/query/share/${cacheId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      if (!res.ok) throw new ShareError(res.status, await parseError(res));
      return res.json() as Promise<ShareCreateResponse>;
    },
  });

export const useShareGet = (shareId: string | undefined) =>
  useQuery<ShareResponse, ShareError>({
    queryKey: ['/api/query/share', shareId],
    enabled: Boolean(shareId),
    queryFn: async () => {
      const res = await fetch(`/api/query/share/${shareId}`);
      if (!res.ok) throw new ShareError(res.status, await parseError(res));
      return res.json() as Promise<ShareResponse>;
    },
  });
```

`ShareError` is exported so consumers (Task 4.3) can do `error instanceof ShareError` and branch on `error.status`.

Note: this hook uses bare `fetch` rather than `useLGQuery`'s `fetchWithTimeout`. Share fetches are short-lived control-plane requests (Redis read, no device interaction) so the global `request_timeout` knob is over-kill here. If this becomes a problem in production, switch to `fetchWithTimeout` with a small fixed timeout (e.g. 10s) and add a follow-up.

- [x] **Step 4: Run the test**

Run: `task pnpm test -- hooks/use-share.test.tsx`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add hyperglass/ui/hooks/use-share.ts hyperglass/ui/hooks/use-share.test.tsx
git commit -m "feat(ui): add useShareCreate (POST) and useShareGet (GET) hooks"
```

### Task 3.4: `useLGQuery` accepts `force`

**Files:**
- Modify: `hyperglass/ui/hooks/use-lg-query.ts`
- Create: `hyperglass/ui/hooks/use-lg-query.test.tsx`

- [x] **Step 1: Read the current hook**

Run: `cat hyperglass/ui/hooks/use-lg-query.ts`

Note `LGQueryKey = [string, FormQuery]` (line 14) and the `useQuery` call at line 72. Because Task 3.2 Step 4 already extended `FormQuery` with optional `force?: boolean`, the existing tuple typing already accepts `force`; no `LGQueryKey` change is needed.

- [x] **Step 2: Extend the body and queryKey**

In `useLGQuery`'s `runQuery` (around line 36), the POST body is constructed from the query object. The hook currently sends **camelCase** keys (`queryLocation`, `queryTarget`, `queryType`) because the backend `Query` Pydantic model uses `alias_generator=snake_to_camel` and `populate_by_name=True`. Inside `runQuery`, the destructured tuple is `[, data]` from `ctx.queryKey` (the second element of `LGQueryKey`). Adapt the existing body literal to also include `force`:

```ts
body: JSON.stringify({
  queryLocation: data.queryLocation,
  queryTarget: data.queryTarget,
  queryType: data.queryType,
  ...(data.force ? { force: true } : {}),
}),
```

Use `data.force` (not `query.force`) — `data` is the destructured queryKey element inside `runQuery`. **Read the existing `runQuery` and `body:` literal first** so the change is purely additive (don't accidentally rename existing fields).

The `queryKey` at line ~72 already uses the query object as the second tuple element. Because `force` is now a field of `FormQuery`, React Query will naturally treat `{...same..., force: true}` as a different key from `{...same..., force: undefined}` — no explicit change to `LGQueryKey` is needed.

- [x] **Step 3: Add a unit test**

Create `hyperglass/ui/hooks/use-lg-query.test.tsx`:

```tsx
/**
 * Tests for useLGQuery's force flag pass-through.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { HyperglassContext } from '~/context';
import { useLGQuery } from './use-lg-query';

const config = {
  cache: { timeout: 600 },
  requestTimeout: 30,
  // ...add other minimum config fields the hook reads...
} as unknown as Config;

const wrapper = ({ children }: { children: React.ReactNode }) => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <HyperglassContext.Provider value={config}>
        {children}
      </HyperglassContext.Provider>
    </QueryClientProvider>
  );
};

beforeEach(() => {
  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({ id: 'x', random: '', cached: false, runtime: 1, level: 'success', timestamp: '', keywords: [], output: 'ok', format: 'text/plain' }),
    text: async () => '',
  } as unknown as Response);
});

describe('useLGQuery force flag', () => {
  it('omits force from body when not set', async () => {
    const query = { queryLocation: 'test1', queryTarget: ['1.2.3.4'], queryType: 'bgp' };
    renderHook(() => useLGQuery(query as any), { wrapper });
    // Wait a tick for the fetch to fire
    await new Promise(r => setTimeout(r, 10));
    const body = JSON.parse((global.fetch as any).mock.calls[0][1].body);
    expect(body.force).toBeUndefined();
  });

  it('includes force=true in body when set', async () => {
    const query = { queryLocation: 'test1', queryTarget: ['1.2.3.4'], queryType: 'bgp', force: true };
    renderHook(() => useLGQuery(query as any), { wrapper });
    await new Promise(r => setTimeout(r, 10));
    const body = JSON.parse((global.fetch as any).mock.calls[0][1].body);
    expect(body.force).toBe(true);
  });
});
```

(Adapt the `config` mock fields to whatever `useLGQuery` actually reads — read the hook source to know.)

- [x] **Step 4: Run UI tests**

Run: `task pnpm test -- hooks/use-lg-query.test.tsx`
Expected: pass.

- [x] **Step 5: Commit**

```bash
git add hyperglass/ui/hooks/
git commit -m "feat(ui): pass-through force flag in useLGQuery"
```

---

## Chunk 4: Frontend UI components, i18n, and form pre-fill

### Task 4.1: Add new strings to backend `Text` model

**Files:**
- Modify: `hyperglass/models/config/web.py:100-129` (the `Text` class)
- Test: `hyperglass/models/tests/test_web.py` (note: `hyperglass/models/tests/` already exists with other model tests; `hyperglass/models/config/tests/` does NOT exist — use the existing dir)

- [x] **Step 1: Write failing test**

Create `hyperglass/models/tests/test_web.py` (this directory already exists with other model tests). Tasks 1.3, 1.5, and 1.6 create `hyperglass/models/config/tests/` for cache- and params-specific tests; we keep web tests under `hyperglass/models/tests/` since `web.py` is the model the test exercises and that's where existing model tests live:

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

- [x] **Step 2: Run the test**

Run: `pytest hyperglass/models/tests/test_web.py -v`
Expected: FAIL.

- [x] **Step 3: Add fields to `Text`**

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

- [x] **Step 4: Run the test**

Run: `pytest hyperglass/models/tests/test_web.py -v`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add hyperglass/models/config/web.py hyperglass/models/tests/test_web.py
git commit -m "feat(config): add share/refresh string fields to Text"
```

### Task 4.2: `RequeryButton` cooldown gate + force flag

**Files:**
- Modify: `hyperglass/ui/components/results/requery-button.tsx`
- Modify: caller of `RequeryButton` in `hyperglass/ui/components/results/individual.tsx` (because the `force=true` retry must rotate the React Query key — see Step 3)
- Test: `hyperglass/ui/components/results/requery-button.test.tsx` (create)

**Design note:** React Query's `refetch()` does NOT accept arbitrary args that propagate to `queryFn`. Per Task 3.4, `force` is part of the `query` object passed to `useLGQuery`, which makes it part of the React Query key — flipping `query.force` from `undefined` to `true` and then calling `refetch()` (or letting React Query auto-fetch the new key) is the mechanism. So `RequeryButton` doesn't directly invoke `force`; instead it asks the parent (or a Zustand action) to **toggle the force state**. The cleanest API: `RequeryButton` accepts an `onRequery: () => void` callback that the parent wires to a state setter that flips `force` to `true` and triggers refetch.

- [x] **Step 1: Write the failing test**

Wrapper pattern is from `hyperglass/ui/hooks/use-dns-query.test.tsx:15-26`. Reproduce here:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, fireEvent, screen, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { HyperglassContext } from '~/context';
import { RequeryButton } from './requery-button';

const baseConfig = {
  cache: { timeout: 600, refreshMinInterval: 5 },
  web: { text: { refreshCooldown: 'Wait {seconds}s' } },
} as unknown as Config;

const buildWrapper = (config: Config) => ({ children }: { children: React.ReactNode }) => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <HyperglassContext.Provider value={config}>
        {children}
      </HyperglassContext.Provider>
    </QueryClientProvider>
  );
};

beforeEach(() => { vi.useFakeTimers(); });

describe('RequeryButton', () => {
  it('is disabled until refreshMinInterval elapses (since lastResponseAt)', async () => {
    const onRequery = vi.fn();
    const Wrapper = buildWrapper(baseConfig);
    const lastResponseAt = Date.now();

    render(
      <RequeryButton onRequery={onRequery} lastResponseAt={lastResponseAt} isDisabled={false} />,
      { wrapper: Wrapper },
    );
    const btn = screen.getByRole('button', { name: /Reload Query/i });
    expect(btn).toBeDisabled();

    act(() => { vi.advanceTimersByTime(5000); });
    expect(btn).toBeEnabled();
  });

  it('calls onRequery on click after cooldown', () => {
    const onRequery = vi.fn();
    const Wrapper = buildWrapper(baseConfig);
    const lastResponseAt = Date.now() - 10_000;  // already past cooldown

    render(
      <RequeryButton onRequery={onRequery} lastResponseAt={lastResponseAt} isDisabled={false} />,
      { wrapper: Wrapper },
    );
    fireEvent.click(screen.getByRole('button', { name: /Reload Query/i }));
    expect(onRequery).toHaveBeenCalledTimes(1);
  });
});
```

- [x] **Step 2: Run the test**

Run: `task pnpm test -- requery-button.test.tsx`
Expected: FAIL.

- [x] **Step 3: Implement `RequeryButton`**

Replace the prop signature: instead of `requery: refetch`, accept `{ onRequery: () => void; lastResponseAt: number; isDisabled?: boolean }`. Read `cache.refreshMinInterval` from `useConfig()`. Compute remaining cooldown from `(lastResponseAt + refreshMinInterval * 1000) - Date.now()`. Use a `setInterval` ticking each second to trigger re-render until cooldown elapses. Disable button when cooldown > 0; enabled otherwise.

On click, call `onRequery()` and update parent state to record the new `lastResponseAt` (the parent owns the state).

- [x] **Step 4: Wire the parent**

In `hyperglass/ui/components/results/individual.tsx` (where `<RequeryButton requery={refetch} ...>` lives at line 221), refactor so the parent:
1. Holds `force` state (e.g. `useState<boolean>(false)`).
2. Passes `force` into the `useLGQuery({...query, force})` call.
3. Tracks `lastResponseAt` (set when `data` updates via React Query).
4. Defines `onRequery` that sets `force=true` and calls `refetch()` (React Query will see the key change and refetch with the new body).
5. After the response settles, resets `force` back to `false` so the next refetch isn't sticky-forced. (Or leave it; the cache key stability is preserved either way.)

- [x] **Step 5: Run the test**

Expected: PASS.

- [x] **Step 6: Commit**

```bash
git add hyperglass/ui/components/results/
git commit -m "feat(ui): RequeryButton cooldown gate; parent wires force=true through useLGQuery"
```

### Task 4.3: `ShareButton` component

**Files:**
- Create: `hyperglass/ui/components/results/share-button.tsx`
- Create: `hyperglass/ui/components/results/share-button.test.tsx`

**Prop signature:**

```ts
interface ShareButtonProps {
  cacheId: string;
}
```

The parent (`individual.tsx`) passes `data?.id` from the React Query result. The button is gated on `cacheId` truthiness AND on `config.cache.shareEnabled`.

- [x] **Step 1: Write the failing test**

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, fireEvent, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { HyperglassContext } from '~/context';
import { ShareButton } from './share-button';

const buildConfig = (overrides: any = {}): Config => ({
  cache: { timeout: 600, shareEnabled: true, shareTimeout: 604800, refreshMinInterval: 120 },
  web: { text: {
    shareButton: 'Share',
    sharePopoverTitle: 'Share this result',
    shareCopyLink: 'Copy link',
    shareLinkCopied: 'Copied!',
    shareExpiresAt: 'Expires {expires}',
    shareCreateError: 'Could not create share link.',
    shareCreateExpired: 'Result expired. Refresh and try again.',
  } },
  ...overrides,
} as unknown as Config);

const buildWrapper = (config: Config) => ({ children }: { children: React.ReactNode }) => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <HyperglassContext.Provider value={config}>
        {children}
      </HyperglassContext.Provider>
    </QueryClientProvider>
  );
};

beforeEach(() => {
  global.fetch = vi.fn();
});

describe('ShareButton', () => {
  it('hides itself when shareEnabled is false', () => {
    const Wrapper = buildWrapper(buildConfig({
      cache: { timeout: 600, shareEnabled: false, shareTimeout: 0, refreshMinInterval: 120 },
    }));
    render(<ShareButton cacheId="hyperglass.query.deadbeef" />, { wrapper: Wrapper });
    expect(screen.queryByRole('button', { name: /Share/i })).not.toBeInTheDocument();
  });

  it('renders with the configured share_button text', () => {
    const Wrapper = buildWrapper(buildConfig());
    render(<ShareButton cacheId="hyperglass.query.deadbeef" />, { wrapper: Wrapper });
    expect(screen.getByText('Share')).toBeInTheDocument();
  });

  it('POSTs the cacheId on click and shows the popover', async () => {
    (global.fetch as any).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ id: 'aaaaaaaaaaa', url: 'https://lg.test/result/aaaaaaaaaaa', expiresAt: '2026-05-08T00:00:00Z' }),
      text: async () => '',
    } as unknown as Response);
    const Wrapper = buildWrapper(buildConfig());
    render(<ShareButton cacheId="hyperglass.query.deadbeef" />, { wrapper: Wrapper });

    fireEvent.click(screen.getByText('Share'));
    await waitFor(() => expect(global.fetch).toHaveBeenCalledWith(
      '/api/query/share/hyperglass.query.deadbeef',
      expect.objectContaining({ method: 'POST' }),
    ));
    await waitFor(() => expect(screen.getByText('Copy link')).toBeInTheDocument());
  });

  it('copies URL to clipboard on copy click', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    (global.fetch as any).mockResolvedValue({
      ok: true, status: 200,
      json: async () => ({ id: 'aaaaaaaaaaa', url: 'https://lg.test/result/aaaaaaaaaaa', expiresAt: '2026-05-08' }),
      text: async () => '',
    } as unknown as Response);

    const Wrapper = buildWrapper(buildConfig());
    render(<ShareButton cacheId="hyperglass.query.deadbeef" />, { wrapper: Wrapper });
    fireEvent.click(screen.getByText('Share'));
    await waitFor(() => screen.getByText('Copy link'));
    fireEvent.click(screen.getByText('Copy link'));
    expect(writeText).toHaveBeenCalledWith('https://lg.test/result/aaaaaaaaaaa');
  });

  it('shows configured share_create_expired text on 410', async () => {
    (global.fetch as any).mockResolvedValue({
      ok: false, status: 410,
      json: async () => ({}),
      text: async () => 'expired',
    } as unknown as Response);

    const Wrapper = buildWrapper(buildConfig());
    render(<ShareButton cacheId="hyperglass.query.deadbeef" />, { wrapper: Wrapper });
    fireEvent.click(screen.getByText('Share'));
    await waitFor(() => expect(screen.getByText('Result expired. Refresh and try again.')).toBeInTheDocument());
  });
});
```

- [x] **Step 2: Run the test**

Run: `task pnpm test -- share-button.test.tsx`
Expected: FAIL.

- [x] **Step 3: Implement**

```tsx
// hyperglass/ui/components/results/share-button.tsx
// Use Chakra Popover + Button. Read config via useConfig(); read text via useStrf().
// Call useShareCreate() from ~/hooks/use-share. On 410, switch the popover content
// to web.text.shareCreateExpired; otherwise show the URL with a Copy button.
```

Pattern reference: `hyperglass/ui/components/results/header.tsx:34-35` for `useStrf()`/`useConfig()` usage.

- [x] **Step 4: Run the test**

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add hyperglass/ui/components/results/share-button.tsx hyperglass/ui/components/results/share-button.test.tsx
git commit -m "feat(ui): add ShareButton with copy-to-clipboard popover"
```

### Task 4.4: Wire `ShareButton` into result header

**Files:**
- Modify: `hyperglass/ui/components/results/individual.tsx`

- [x] **Step 1: Locate the existing button placement**

Run: `grep -n "RequeryButton\|<Requery" hyperglass/ui/components/results/individual.tsx`
Expected: `<RequeryButton requery={refetch} isDisabled={isLoading} />` around line 221.

- [x] **Step 2: Add `<ShareButton>` next to it**

Render conditionally on `data?.id` truthiness. The React Query result variable is named `data` (and `refetch`, `isLoading`) per the existing destructuring in this file:

```tsx
{data?.id && <ShareButton cacheId={data.id} />}
<RequeryButton onRequery={onRequery} lastResponseAt={lastResponseAt} isDisabled={isLoading} />
```

(`onRequery` and `lastResponseAt` come from the parent state added in Task 4.2 Step 4.)

- [x] **Step 3: Typecheck and lint**

Run: `task ui-typecheck && task ui-lint`
Expected: clean.

- [x] **Step 4: Commit**

```bash
git add hyperglass/ui/components/results/individual.tsx
git commit -m "feat(ui): place ShareButton next to RequeryButton in result header"
```

### Task 4.5: Form pre-fill from query string

**Files:**
- Modify: `hyperglass/ui/components/looking-glass-form.tsx`
- Create: `hyperglass/ui/components/looking-glass-form.test.tsx`

**URL → form mapping:**

| URL param | Form field | Type in form schema | Wrap |
|-----------|------------|---------------------|------|
| `?location=test1` | `queryLocation` | `string[]` | `[value]` |
| `?target=192.0.2.0/24` | `queryTarget` | `string[]` | `[value]` (or split on comma if multi-target supported) |
| `?type=juniper_bgp_route` | `queryType` | `string` | scalar |

The form's `defaultValues.queryLocation` is `[]` (array), so a single-string URL param must be wrapped in an array via `setValue('queryLocation', [value])`. Calling `setValue('queryLocation', value)` with a string would fail Vest validation.

- [x] **Step 1: Write the failing test**

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { HyperglassContext } from '~/context';
import { LookingGlassForm } from './looking-glass-form';

vi.mock('next/router', () => ({
  useRouter: () => ({
    query: { location: 'test1', target: '192.0.2.0/24', type: 'juniper_bgp_route' },
    isReady: true,
    push: vi.fn(),
    replace: vi.fn(),
  }),
}));

const config = { /* ...sufficient mock config for form rendering... */ } as unknown as Config;

const wrapper = ({ children }: { children: React.ReactNode }) => {
  const qc = new QueryClient();
  return (
    <QueryClientProvider client={qc}>
      <HyperglassContext.Provider value={config}>
        {children}
      </HyperglassContext.Provider>
    </QueryClientProvider>
  );
};

it('pre-fills location/target/type from query string on mount', async () => {
  render(<LookingGlassForm />, { wrapper });
  // Assert via the form's underlying state — easiest via querying the inputs.
  // The exact selector depends on how the form labels its fields; consult
  // looking-glass-form.tsx for the label keys (use web.text.queryLocation etc.).
  expect(await screen.findByDisplayValue('test1')).toBeInTheDocument();
  expect(await screen.findByDisplayValue('192.0.2.0/24')).toBeInTheDocument();
});
```

(The mock `config` needs to provide enough fields to let the form render. Read `looking-glass-form.tsx` and provide the minimum.)

- [x] **Step 2: Run the test**

Run: `task pnpm test -- looking-glass-form.test.tsx`
Expected: FAIL.

- [x] **Step 3: Implement**

In `looking-glass-form.tsx`, after the `useForm` setup:

```tsx
import { useRouter } from 'next/router';

const router = useRouter();
useEffect(() => {
  if (!router.isReady) return;
  const { location, target, type } = router.query;
  if (typeof location === 'string') setValue('queryLocation', [location]);
  if (typeof target === 'string') setValue('queryTarget', [target]);
  if (typeof type === 'string') setValue('queryType', type);
}, [router.isReady, router.query, setValue]);
```

- [x] **Step 4: Run the test**

Expected: PASS.

- [x] **Step 5: Commit**

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
- Modify: `hyperglass/ui/components/results/individual.tsx` (add `readOnly` prop to suppress Share/Refresh buttons in share view)
- Modify: `hyperglass/ui/components/results/share-button.tsx` (no-op when `readOnly`; or just don't render when called from the share view) — alternatively skip via the parent and don't change ShareButton

**Refactor recommendation (resolves the open choice from the spec):**

Keep `Results` (`components/results/group.tsx`) as the form-driven path. For the share view, render the lower-level `Result` (`components/results/individual.tsx`) directly with a snapshot prop and `readOnly: true`. This minimizes blast radius:

- `Results` keeps reading from the Zustand store. No changes there.
- `Result` (`individual.tsx`) gets a new optional prop signature: `{ snapshot?: ShareResponse; readOnly?: boolean }`. When `snapshot` is provided, it renders directly from `snapshot.output`, `snapshot.queryLabels`, `snapshot.timestamp`, `snapshot.format` — skipping the React Query fetch and the Zustand store read. When `readOnly`, it suppresses `<RequeryButton>` and `<ShareButton>`.
- The share page constructs and passes the snapshot prop.

This refactor is bounded to `individual.tsx` and the share page; `Results`, `LookingGlassForm`, `useFormState`, etc. stay untouched.

- [x] **Step 1: Add `snapshot` and `readOnly` props to `individual.tsx`**

In `hyperglass/ui/components/results/individual.tsx`, change the props type:

```ts
interface ResultProps {
  // existing props...
  snapshot?: ShareResponse;
  readOnly?: boolean;
}
```

When `snapshot` is provided: skip the React Query fetch, render directly from `snapshot.output` and `snapshot.queryLabels.location` / `snapshot.queryLabels.type` for the header. When `readOnly`: omit `<ShareButton>` and `<RequeryButton>` from the header.

- [x] **Step 2: Write the failing page test**

```tsx
// hyperglass/ui/pages/result/[id].test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { HyperglassContext } from '~/context';
import ResultPage from './[id]';

vi.mock('next/router', () => ({
  useRouter: () => ({
    query: { id: 'aaaaaaaaaaa' },
    isReady: true,
    push: vi.fn(),
  }),
}));

const config = {
  cache: { timeout: 600, shareEnabled: true, shareTimeout: 604800, refreshMinInterval: 120 },
  web: { text: {
    shareSnapshotBanner: 'Snapshot taken at {timestamp}',
    shareNotFound: 'Share not found or expired.',
    shareRunFreshQuery: 'Run a fresh query',
    shareExpiresAt: 'Expires {expires}',
  } },
} as unknown as Config;

const wrapper = ({ children }: { children: React.ReactNode }) => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <HyperglassContext.Provider value={config}>{children}</HyperglassContext.Provider>
    </QueryClientProvider>
  );
};

beforeEach(() => { global.fetch = vi.fn(); });

const fakeSnapshot = {
  id: 'aaaaaaaaaaa',
  shared: true,
  cached: true,
  output: 'BGP table output here',
  runtime: 1,
  timestamp: '2026-05-01 12:00:00',
  format: 'text/plain',
  level: 'success',
  keywords: [],
  query: { query_location: 'test1', query_target: '192.0.2.0/24', query_type: 'juniper_bgp_route' },
  queryLabels: { location: 'test1', type: 'BGP Route' },
  createdAt: '2026-05-01T12:00:00Z',
  expiresAt: '2026-05-08T12:00:00Z',
};

it('renders the snapshot output for a valid id', async () => {
  (global.fetch as any).mockResolvedValue({
    ok: true, status: 200,
    json: async () => fakeSnapshot,
    text: async () => '',
  } as unknown as Response);
  render(<ResultPage />, { wrapper });
  await waitFor(() => expect(screen.getByText('BGP table output here')).toBeInTheDocument());
  expect(screen.getByText(/Snapshot taken at/)).toBeInTheDocument();
});

it('shows configured "share not found" message on 404', async () => {
  (global.fetch as any).mockResolvedValue({
    ok: false, status: 404,
    json: async () => ({}),
    text: async () => 'not found',
  } as unknown as Response);
  render(<ResultPage />, { wrapper });
  await waitFor(() => expect(screen.getByText('Share not found or expired.')).toBeInTheDocument());
});

it('exposes a "Run a fresh query" link with prefilled query string', async () => {
  (global.fetch as any).mockResolvedValue({
    ok: true, status: 200, json: async () => fakeSnapshot, text: async () => '',
  } as unknown as Response);
  render(<ResultPage />, { wrapper });
  await waitFor(() => screen.getByText('Run a fresh query'));
  const link = screen.getByText('Run a fresh query').closest('a');
  expect(link?.getAttribute('href')).toMatch(/^\/\?location=test1/);
  expect(link?.getAttribute('href')).toContain('target=192.0.2.0%2F24');
  expect(link?.getAttribute('href')).toContain('type=juniper_bgp_route');
});
```

- [x] **Step 3: Run the test**

Run: `task pnpm test -- pages/result/`
Expected: FAIL.

- [x] **Step 4: Implement the page**

```tsx
// hyperglass/ui/pages/result/[id].tsx
import { useRouter } from 'next/router';
import { useShareGet } from '~/hooks/use-share';
import { Result } from '~/components/results/individual';
import { useConfig, useStrf } from '~/hooks';

export default function ResultPage() {
  const router = useRouter();
  const config = useConfig();
  const strf = useStrf();
  const id = typeof router.query.id === 'string' ? router.query.id : undefined;
  const { data: snapshot, isLoading, error } = useShareGet(id);

  if (isLoading || !router.isReady) return null;
  if (error || !snapshot) {
    return <p>{config.web.text.shareNotFound}</p>;
  }

  const banner = strf(config.web.text.shareSnapshotBanner, { timestamp: snapshot.timestamp });
  const expires = strf(config.web.text.shareExpiresAt, { expires: snapshot.expiresAt });
  const freshUrl = `/?location=${encodeURIComponent(snapshot.query.query_location)}&target=${encodeURIComponent(typeof snapshot.query.query_target === 'string' ? snapshot.query.query_target : snapshot.query.query_target[0])}&type=${encodeURIComponent(snapshot.query.query_type)}`;

  return (
    <>
      <div role="banner">{banner} · {expires}</div>
      <Result snapshot={snapshot} readOnly />
      <a href={freshUrl}>{config.web.text.shareRunFreshQuery}</a>
    </>
  );
}
```

- [x] **Step 5: Run the test**

Expected: PASS.

- [x] **Step 6: Typecheck, lint, format**

Run: `task ui-typecheck && task ui-lint && task ui-format`

- [x] **Step 7: Commit**

```bash
git add hyperglass/ui/pages/result/ hyperglass/ui/components/results/individual.tsx
git commit -m "feat(ui): add /result/[id] share view; Result component accepts snapshot+readOnly"
```

### Task 5.2: Verify static-export SPA fallback covers `/result/<id>`

**Files:**
- (Possibly) Modify: `hyperglass/api/__init__.py` if `html_mode=True` does not cover the case.

- [x] **Step 1: Build the UI**

Run: `task ui-build`
Expected: build succeeds, output under `hyperglass/static/ui/`.

- [x] **Step 2: Start the backend**

Run: `task start`
Expected: server up on port 8001 (or configured port).

- [x] **Step 3: Test the SPA fallback**

In another shell:

```bash
curl -i http://127.0.0.1:8001/result/aB3kF9pQ2x_
```

Expected: 200 OK with `Content-Type: text/html` returning the SPA's `index.html`.

- [x] **Step 4 (only if Step 3 returned 404):** Add explicit Litestar route handler

In `hyperglass/api/__init__.py`, add the imports near the top (alongside existing Litestar imports):

```python
import re
from litestar import get
from litestar.exceptions import NotFoundException
from litestar.response import File
```

Define the handler (above the `HANDLERS` list):

```python
@get("/result/{share_id:str}", include_in_schema=False)
async def share_view_html(share_id: str) -> File:
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", share_id):
        raise NotFoundException()
    return File(path=UI_DIR / "index.html", media_type="text/html")
```

Add `share_view_html` to the `HANDLERS` list at line 39, **before** the `if not STATE.settings.disable_ui:` block (so it's registered ahead of the static-files mount).

Then re-run Step 3 and confirm 200.

- [x] **Step 5: Commit (if changes made)**

```bash
git add hyperglass/api/__init__.py
git commit -m "feat(api): explicit /result/<id> route handler when html_mode is insufficient"
```

(Skip if `html_mode=True` already covered it; record that fact in the next task's smoke-test notes.)

### Task 5.3: Operator docs and CHANGELOG

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `docs/pages/configuration/config/caching.mdx` (the existing cache docs page; uses a markdown table format we extend)
- Modify: `docs/pages/configuration/config.mdx` (the params index — gets the `public_url` row, since `public_url` is a top-level `params.*` field, not under `params.cache.*`)

- [x] **Step 1: Document the share feature in CHANGELOG**

In `CHANGELOG.md`, under the `## [Unreleased]` section, the existing subsections are `Fixed`, `Security`, `Updated`, `Added`. Add the share feature under `Added` and the cache.timeout default change under `Updated`:

```markdown
### Added
- Sharable result snapshots: clicking the new Share button on a result mints a `/result/<id>` URL (default 7-day TTL, operator-tunable via `cache.share_timeout`).
- `params.public_url` (optional): when set, share URLs use this base; otherwise derived from request headers.

### Updated
- `cache.timeout` default raised from 120s → 600s. End-user refresh behavior is preserved by `cache.refresh_min_interval` (UI cooldown, default 120s) and the new query `force` flag. Operators relying on 2-minute cache staleness should set `cache.timeout: 120` explicitly.
```

- [x] **Step 2: Document cache fields in `caching.mdx`**

In `docs/pages/configuration/config/caching.mdx`, the existing parameter table looks like:

```markdown
| Parameter         | Type    | Default Value | Description                                                                     |
| :---------------- | :------ | :------------ | :------------------------------------------------------------------------------ |
| `cache.timeout`   | Number  | 120           | Number of seconds for which to cache device responses.                          |
| `cache.show_text` | Boolean | True          | If true, an indication that a user is viewing cached information will be shown. |
```

**Update `cache.timeout` default to 600** (it changed in this release), and append four new rows in the same format:

```markdown
| `cache.timeout`              | Number  | 600   | Number of seconds for which to cache device responses.                                                          |
| `cache.show_text`            | Boolean | True  | If true, an indication that a user is viewing cached information will be shown.                                 |
| `cache.share_enabled`        | Boolean | True  | Enable the shareable-result feature. Disabling requires a UI rebuild.                                           |
| `cache.share_timeout`        | Number  | 604800 | Seconds to retain a shared snapshot (default 7 days).                                                          |
| `cache.share_sliding`        | Boolean | False | If true, viewing a share extends its TTL by another `share_timeout`.                                            |
| `cache.refresh_min_interval` | Number  | 120   | Minimum seconds between manual refreshes from the UI.                                                           |
```

Also update the example-with-defaults YAML block to include the new fields with their defaults.

Add a callout below the table: "Disabling `share_enabled` (or changing any cache UI knob) requires a UI rebuild — the values are baked into the static `hyperglass.json` at build time."

- [x] **Step 3: Document `public_url` on the params index page**

`public_url` is a top-level `params` field, not a cache subfield. In `docs/pages/configuration/config.mdx`, add it to the appropriate `params.*` reference table (or example block) — match the existing format. Suggested row:

```markdown
| `public_url` | URL    | (unset) | Public-facing base URL for the looking glass. When set, share links use this base; otherwise derived from request `Host` / `X-Forwarded-Proto` headers. Set this when running behind a reverse proxy. |
```

- [x] **Step 4: Commit**

```bash
git add CHANGELOG.md docs/pages/configuration/config/caching.mdx docs/pages/configuration/config.mdx
git commit -m "docs: document share-results feature and cache.timeout default change"
```

### Task 5.4: End-to-end smoke test

- [x] **Step 1: Boot stack against fake_output**

Set `params.fake_output: true` in your dev config, then `task start`.

- [x] **Step 2: Run a query in the browser**

- Open `http://127.0.0.1:8001/`
- Submit a real-shaped query (any device + target + type your seed config has)

- [x] **Step 3: Verify Share button**

- Confirm Share button is visible in the result header
- Click Share → confirm popover opens with a `/result/<id>` URL
- Click Copy → confirm clipboard contains the URL

- [x] **Step 4: Open the share URL incognito**

- Confirm the snapshot renders with the banner
- Confirm output matches what you saw in the original result

- [x] **Step 5: Verify refresh cooldown**

- Click Refresh < 120s after submitting → confirm disabled with cooldown message
- Wait > 120s → confirm enabled, click → confirm new query result and a new shareable id

- [x] **Step 6: Verify expired-cache 410 path**

Find the redis-cli command appropriate to your environment:
- **Local Redis (native):** `redis-cli` connects to localhost:6379 by default.
- **Docker Compose (per `compose.yaml`):** `docker compose exec redis redis-cli`.

Find the digest:
```bash
# After running the query in Step 2, find the cache key:
redis-cli --scan --pattern 'hyperglass.state.hyperglass.query.*'
```

Pick the most-recent digest, then expire it:
```bash
redis-cli EXPIRE hyperglass.state.hyperglass.query.<digest> 1
sleep 2
```

Click Share in the UI → confirm the configured `share_create_expired` message.

- [x] **Step 7: Verify share survives query-cache expiry (the headline guarantee)**

- Run a fresh query (Step 2)
- Click Share, copy the `/result/<id>` URL
- Expire the underlying query cache as in Step 6 (`redis-cli EXPIRE hyperglass.state.hyperglass.query.<digest> 1; sleep 2`)
- Confirm the query cache is gone: `redis-cli EXISTS hyperglass.state.hyperglass.query.<digest>` → returns `0`
- Open the share URL in a fresh incognito window
- **Expect:** snapshot still renders correctly. The share has its own TTL (`cache.share_timeout`, default 7 days) independent of the query cache.

- [x] **Step 8: Verify share-not-found**

- Open `http://127.0.0.1:8001/result/notarealid` → confirm the configured `share_not_found` message

- [x] **Step 9: Verify `params.public_url` shaping (optional)**

- Set `public_url: https://lg.example.test` in the dev config; restart
- Run a query, click Share
- Confirm the popover URL is `https://lg.example.test/result/<id>` (not the local `127.0.0.1` URL)
- Unset and restart; confirm derived URL returns

- [x] **Step 10: Sign-off commit (if any deltas surfaced)**

```bash
git add -A
git commit -m "test: smoke test fixes for share-results"  # if needed
```

### Task 5.5: Final lint / format / typecheck

- [x] **Step 1: Backend**

Run: `task lint && task format && task sort && task test`
Expected: all clean and green.

- [x] **Step 2: Frontend**

Run: `task ui-typecheck && task ui-lint && task ui-format && task pnpm test`
Expected: all clean and green.

- [x] **Step 3: Combined check**

Run: `task check`
Expected: clean.

- [x] **Step 4: Final commit (if needed)**

```bash
git add -A
git commit -m "chore: final lint/format pass for share-results"
```
