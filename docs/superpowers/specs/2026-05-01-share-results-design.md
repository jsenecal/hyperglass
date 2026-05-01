# Share Results — Design

**Status:** Draft
**Date:** 2026-05-01
**Owner:** Jonathan Senecal

## Problem

Users who run a query in hyperglass cannot share the result with anyone else. The result lives only in the requesting browser's memory, and the underlying Redis cache entry expires after `params.cache.timeout` seconds (currently 120s). The only way for one user to show another what they saw is to copy/paste the rendered output.

We want every result to be sharable as a permalink with a meaningful retention window — long enough for the share to survive a workday, a Slack thread, or a ticket investigation, without committing every casual probe to long-term storage.

## Goals

- Let a user explicitly mint a sharable URL for any successful query result.
- Recipient of the URL sees the **exact output** the original user saw — a snapshot, not a re-execution.
- Default retention 7 days, operator-tunable.
- No new auth surface; the looking glass remains public.
- Backend is the source of truth for snapshot content (clients cannot fabricate snapshots).

## Non-goals

- Authenticating sharers or recipients.
- Revocation of an issued share (deferred — could be added later as an admin endpoint).
- Rate limiting of share creation (deferred — flagged as a follow-up).
- Server-side pre-rendering / OG-tag link previews for share URLs (looking glass is not optimized for SEO; the SPA renders client-side).
- Sharing query parameters only (re-runs against the device on each visit) — explicitly rejected; snapshots are the contract.
- Any caching/sharing of failed queries.

## Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | **Snapshot semantics**: shares always return the exact captured output, never re-execute. The existing refresh button continues to mint a new query, which the user can then share separately. | Honest contract; identical link can never produce different output day to day. |
| 2 | **Opt-in**: only a deliberate "Share" click promotes a result to long-term storage with a new opaque ID. | Smaller Redis footprint; avoids URL enumerability of `sha256(location\|target\|type)`. |
| 3 | **URL shape**: `/result/<id>` (frontend) backed by `/api/query/share/<id>` (backend). Namespaced under `/result/` to keep the root path free for future top-level routes. | Self-describing; no risk of an ID colliding with a future feature path. |
| 4 | **TTL**: configurable via two new fields under `params.cache`: `share_timeout` (default `604800` = 7 days) and `share_sliding` (default `false`). Fixed-from-creation by default. | Operator can extend; sliding is available as a knob, not a default. |
| 5 | **Bump default `params.cache.timeout` from `120` to `600`** (10 min). | Gives the user a forgiving window between query and share-click before the source cache entry expires. |
| 6 | **Add a `force` flag to the query request body**, default `false`. The UI's existing refresh button enables after 120s and posts `force: true`, bypassing the cache and re-executing. | Decouples UI cooldown (120s, controllable by operator) from cache TTL (600s). |
| 7 | **Expose share configuration to the frontend** via `/api/info` (specifically: `share_enabled`, `share_timeout`, `refresh_min_interval`). | UI hides Share button when disabled and shows accurate "expires in N days" copy. |

## Architecture

```
┌───────────┐   POST /api/query                 ┌────────────┐
│  Browser  │──────────────────────────────────▶│  Litestar  │
│   (SPA)   │                                   │  /api      │
└─────┬─────┘                                   └──────┬─────┘
      │  click "Share"                                 │
      │  POST /api/query/share/<cache_id>              │
      │───────────────────────────────────────────────▶│
      │            { id, url, expires_at }            │
      │◀───────────────────────────────────────────────│
      │                                                │
      │  recipient opens https://lg/result/<id>       │
      │───────────────────────────────────────────────▶│
      │            (Litestar SPA fallback             │
      │             serves index.html)                │
      │  GET /api/query/share/<id>                    │
      │───────────────────────────────────────────────▶│
      │            { snapshot fields }                │
      │◀───────────────────────────────────────────────│

                       Redis (state)
                       ┌────────────────────────────────┐
                       │ hyperglass.query.<digest>      │  TTL = cache.timeout (600s)
                       │   { output, query, query_labels│
                       │     timestamp, format, runtime,│
                       │     level, keywords }          │
                       │                                │
                       │ hyperglass.share.<opaque_id>   │  TTL = cache.share_timeout (7d)
                       │   (same fields + created_at,   │
                       │    expires_at)                 │
                       └────────────────────────────────┘
```

### Trust model

The backend is the only writer of share storage. The share-create endpoint takes a `cache_id` (the value already returned to the client as `response.id`), looks up the entry the backend wrote during query execution, and copies it into the share namespace. The client cannot fabricate output and have it served from a hyperglass URL.

If the original cache entry has expired before the user clicks Share (i.e. > `cache.timeout` after the query), the endpoint returns `410 Gone`; the UI prompts the user to refresh and try again.

## Backend changes

### Configuration model — `hyperglass/models/config/cache.py`

```python
class Cache(HyperglassModel):
    timeout: int = 600                # was 120
    show_text: bool = True
    share_enabled: bool = True        # NEW — kill switch
    share_timeout: int = 604800       # NEW — 7 days
    share_sliding: bool = False       # NEW — extend on view?
    refresh_min_interval: int = 120   # NEW — UI refresh cooldown
```

`refresh_min_interval` lives on `Cache` for proximity to the related TTL knobs even though it is a UI-only concept; it ends up in the `/api/info` payload.

### Query model — `hyperglass/models/api/query.py`

Add an optional `force: bool = False` field. When `force=True`, the route handler skips the cache lookup and proceeds straight to execution. The `digest()` method is **not** affected by `force` (the cache key remains the canonical hash of `query_location` / `query_type` / `query_target`); a forced execution overwrites the existing entry on completion.

### Cache write expansion — `hyperglass/api/routes.py`

Inside the cache-miss branch (lines 96–134), the cache write is expanded:

```python
cache.set_map_item(cache_key, "output", raw_output)
cache.set_map_item(cache_key, "timestamp", timestamp)
cache.set_map_item(cache_key, "query", data.dict())
cache.set_map_item(cache_key, "query_labels", {
    "location": data.device.name,                  # frozen display name
    "type": data.directive.name,                   # frozen directive label
})
cache.set_map_item(cache_key, "format", response_format)
cache.set_map_item(cache_key, "runtime", runtime)
cache.set_map_item(cache_key, "level", "success")
cache.set_map_item(cache_key, "keywords", [])
cache.expire(cache_key, expire_in=_state.params.cache.timeout)
```

`response_format` is computed before the existing line that re-reads the entry; we move that determination earlier. The full set of stored fields makes both routes (`/api/query` and `/api/query/share`) able to return identical payloads without re-deriving anything.

When `force=True`, the route handler bypasses the initial `cache.get_map(...)` lookup and proceeds straight to execution. The cache entry is overwritten on completion, so subsequent non-force calls see the fresh result.

### Share endpoints — `hyperglass/api/routes.py`

```python
@post("/api/query/share/{cache_id:str}", dependencies={"_state": Provide(get_state)})
async def share_create(_state: HyperglassState, cache_id: str) -> ShareCreateResponse:
    """Promote a cached query result to a long-lived shareable snapshot."""
    if not _state.params.cache.share_enabled:
        raise NotFoundException("Sharing is disabled.")

    # Accept either "hyperglass.query.<digest>" or just "<digest>"
    digest = cache_id.removeprefix("hyperglass.query.")
    cache_key = f"hyperglass.query.{digest}"

    cache = _state.redis
    output = cache.get_map(cache_key, "output")
    if output is None:
        raise GoneException("Result has expired. Refresh the query and try again.")

    share_id = _generate_share_id(cache, max_attempts=3)
    share_key = f"hyperglass.share.{share_id}"
    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=_state.params.cache.share_timeout)

    # Copy every field from the source map plus share metadata.
    for field in ("output", "timestamp", "query", "query_labels",
                  "format", "runtime", "level", "keywords"):
        cache.set_map_item(share_key, field, cache.get_map(cache_key, field))
    cache.set_map_item(share_key, "created_at", now)
    cache.set_map_item(share_key, "expires_at", expires_at)
    cache.expire(share_key, expire_in=_state.params.cache.share_timeout)

    return ShareCreateResponse(
        id=share_id,
        url=f"{_state.params.public_url()}/result/{share_id}",
        expires_at=expires_at,
    )


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

`_generate_share_id` produces an opaque token (`secrets.token_urlsafe(8)` ≈ 11 URL-safe characters, 64 bits of entropy). The function checks for an existing entry and retries on the astronomically unlikely collision; after `max_attempts=3` it raises an internal error.

`GoneException` and `NotFoundException` are Litestar-native exception types; no new exception classes needed.

### Public URL — `hyperglass/models/config/params.py`

Add a `public_url()` helper to `Params` that returns the operator-configured base URL. Hyperglass already needs to know its own URL for some behaviors (webhooks, OG tags); reuse the existing source if there is one (`web.location`, `general.public_url`, etc. — to be confirmed during implementation). If none exists, derive from the request host as a fallback for share-create response building.

### `/api/info` payload

`Params.export_api()` is extended to include:

```python
{
    ...,
    "cache": {
        "show_text": ...,
        "share_enabled": ...,
        "share_timeout": ...,
        "refresh_min_interval": ...,
    },
}
```

Non-public fields (`timeout`, `share_sliding`) stay private. The UI uses `share_enabled` to conditionally render the share button, `share_timeout` for "expires in N days" copy, and `refresh_min_interval` to gate the existing refresh button.

### Response models — `hyperglass/models/api/response.py`

Add:

- `ShareCreateResponse` — `{ id: str, url: str, expires_at: datetime }`
- `ShareResponse` — superset of `QueryResponse` with `shared: bool`, `query: SimpleQuery`, `query_labels: dict[str, str]`, `created_at: datetime`, `expires_at: datetime`.

Add `id: str` to `QueryResponse` (it is already returned today but is not part of the typed response model — see `routes.py:148-150`).

## Frontend changes

### New page — `hyperglass/ui/pages/result/[id].tsx`

A dedicated read-only result view. Behavior:

1. On mount, read `id` from `next/router`.
2. `fetch('/api/query/share/' + id)`.
3. On success: render the existing `Results` component (pulled out of its current form-coupled state in a small refactor — see below) with a snapshot banner above it: "Snapshot taken at `<timestamp>` · expires `<expires_at>`."
4. On 404: show a configurable "Share not found or expired" message, with a CTA back to `/`.
5. The page provides a "Run a fresh query" button that links to `/?location=<>&target=<>&type=<>` to pre-fill the form.

Because hyperglass uses `next export`, `[id].tsx` cannot pre-render unknown IDs. The build emits a single `result/[id].html` that the SPA hydrates client-side. Litestar must serve this single HTML for any path matching `/result/{id:str}` so bookmarked share URLs resolve. This is added in `hyperglass/api/__init__.py` alongside the existing static-file routing for the SPA.

### Results component — small refactor

The existing `Results` (under `hyperglass/ui/components/results/`) currently couples to form state via `useFormState()` Zustand store. Refactor so it accepts the response payload and query metadata as props, with an optional `readOnly: boolean` flag. The form path keeps reading from the store and passes props down; the share path passes props from the share-fetch result. This keeps the component a single source of rendering truth without growing a second copy.

This is a targeted refactor in the spirit of "improving code I'm working in" — it directly serves the share flow.

### Share button

Added to the result view next to the existing refresh affordance. UX:

1. Disabled until query response has an `id` (it always will, post-merge).
2. Hidden when `/api/info` returns `cache.share_enabled === false`.
3. Click → `POST /api/query/share/<cache_id>`.
4. On success: open a popover with the URL and a copy-to-clipboard button. Show "Expires `<expires_at>`."
5. On 410: display a configurable message ("This result has expired from cache — refresh and try again.") and surface a refresh action.
6. On other errors: display a configurable generic error.

### Refresh button

Add a `refresh_min_interval` cooldown gate (read from `/api/info`, default 120s). The existing refresh button:

1. Becomes disabled for `refresh_min_interval` seconds after each query submission.
2. When clicked, sends `POST /api/query` with the same body but `force: true`.
3. The result replaces the prior result in store; `id` updates accordingly so a subsequent share captures the new snapshot.

### TypeScript types — `hyperglass/ui/types/globals.d.ts`

Add:

- `id: string` to `QueryResponse`.
- `ShareResponse` mirroring the backend model.
- `force?: boolean` to the request type.
- `share_enabled`, `share_timeout`, `refresh_min_interval` to whatever type holds the `/api/info` response.

### i18n — no hard-coded strings

All new user-visible strings — Share button label, copy-link tooltip, snapshot banner, expiry messages, "share not found" message, "result expired" message — are added to `params.web.text` (or `params.messages` where they are error-shaped) and consumed via the existing config flow. CLAUDE.md mandates this; the spec mandates it explicitly.

## Edge cases

| Case | Behavior |
|------|----------|
| Cache expired between query and Share click | `POST /api/query/share/<id>` returns `410`; UI prompts to refresh. |
| Share recipient opens an expired link | `GET /api/query/share/<id>` returns `404` (Redis TTL has elapsed); page shows "Share not found or expired." |
| `share_enabled = false` | UI hides Share button (read from `/api/info`); both endpoints return `404`. |
| Device renamed or removed after snapshot | Share page renders correctly because labels are frozen at write time. The "Run a fresh query" CTA may fail validation — that's fine. |
| Directive deleted after snapshot | Same as above. |
| Two simultaneous Shares of the same query | Two distinct opaque IDs, two share entries. By design. |
| Snapshot output very large (e.g. full BGP table) | Stored as-is, same as current cache. Carries longer. Documented as a Redis-footprint concern; no hard cap in v1. |
| Redis unavailable | Same 5xx behavior as today. No new failure modes. |
| ID collision | `_generate_share_id` retries up to 3 times; 64-bit entropy makes this effectively impossible. |
| Force-refresh while another client is reading the same cache key | Cache write is a Redis hash; the field-level writes are atomic per-field. Worst case a reader sees a partially updated map for milliseconds; acceptable. The same hazard exists today for the timestamp/output pair. |

## Testing

### Backend (pytest, `hyperglass/api/`)

- `test_query_caches_full_snapshot_fields` — after a query, all of `output`, `query`, `query_labels`, `format`, `runtime`, `level`, `keywords`, `timestamp` are present in the cache entry.
- `test_share_create_returns_opaque_id` — ID is URL-safe, length 11.
- `test_share_create_410_when_cache_expired` — manually delete the cache key, confirm 410.
- `test_share_create_404_when_disabled` — `share_enabled=false` → 404 from both endpoints.
- `test_share_get_returns_full_snapshot` — round-trip create/get returns identical content.
- `test_share_get_404_when_missing` — unknown ID → 404.
- `test_share_get_sliding_extends_ttl` — when `share_sliding=true`, GET resets TTL.
- `test_share_get_fixed_does_not_extend_ttl` — when `share_sliding=false`, GET does not reset.
- `test_force_skips_cache` — `force=true` re-executes even when the entry is hot.

### Frontend (Vitest, `hyperglass/ui/`)

- `pages/result/[id].test.tsx` — happy path: fetch + render snapshot banner + read-only Result.
- `pages/result/[id].test.tsx` — 404 path: shows configured "not found" message with CTA.
- Share-button component — happy path, 410 path, disabled state when `share_enabled=false`, clipboard interaction.
- Refresh-button component — disabled for `refresh_min_interval`, sends `force: true` when clicked.

### Manual

- End-to-end flow against a real network device on a dev install.
- Verify share URL works in an incognito window (no auth dependency).
- Verify share URL still works after `params.cache.timeout` has elapsed (i.e. the original cache is gone but the share remains).

## Deferred

- **Rate limiting** of `POST /api/query/share/*`. A bad actor could spam-create shares and bloat Redis. Mitigation today: the underlying queries are already rate-limited by device responsiveness; share-creation rate is bounded by query-creation rate. Worth tightening with an explicit per-IP limit in a follow-up.
- **Revocation**. Operators may want to delete a specific share. Could be a CLI command or admin endpoint; not in v1.
- **Audit log of share creations**. Logging is fine for now; structured retention is a follow-up.
- **OG-tag preview rendering** for share URLs. Would require server-rendered HTML; not a fit for `next export` without Litestar templating.

## Risks

- **Redis footprint growth.** Worst case a popular looking glass mints thousands of shares per day. At ~10 KB/share (average textual command output) × 7 days × 1k/day = ~70 MB. Operators with high traffic may want to lower `share_timeout` or disable the feature. Documented in operator docs; no hard cap in v1.
- **Cache-write change risk.** Expanding the cache map might surface subtle bugs in `cache.get_map` deserialization for new field types (especially `dict` for `query`/`query_labels`). The Redis layer pickles values, so any picklable type works; tests cover the round-trip.
- **Static-export SPA fallback.** The Litestar route addition to serve `result/[id].html` for arbitrary IDs is a small change but it's the kind of thing that's easy to break in future Next.js upgrades. Documented inline.
- **Trust model under share-by-URL with no auth.** Anyone with the URL can view; that is intended for a public looking glass but worth highlighting in operator docs (do not share output that includes operationally sensitive context, e.g. internal hostnames in BGP communities).
