"""API Routes."""

# Standard Library
import json
import secrets
import time
import typing as t
from datetime import UTC, datetime, timedelta

# Third Party
from litestar import Request, Response, get, post
from litestar.di import Provide
from litestar.background_tasks import BackgroundTask
from litestar.exceptions import HTTPException, NotFoundException

# Project
from hyperglass.log import log
from hyperglass.state import HyperglassState
from hyperglass.exceptions import HyperglassError
from hyperglass.models.api import Query
from hyperglass.models.data import OutputDataModel
from hyperglass.util.typing import is_type
from hyperglass.execution.main import execute
from hyperglass.models.api.response import QueryResponse, ShareCreateResponse, ShareResponse
from hyperglass.models.config.params import Params, APIParams
from hyperglass.models.config.devices import Devices, APIDevice

# Local
from .state import get_state, get_params, get_devices
from .tasks import send_webhook
from .fake_output import fake_output

__all__ = (
    "device",
    "devices",
    "queries",
    "info",
    "query",
    "share_create",
    "share_get",
)


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


@get("/api/devices/{id:str}", dependencies={"devices": Provide(get_devices)})
async def device(devices: Devices, id: str) -> APIDevice:
    """Retrieve a device by ID."""
    return devices[id].export_api()


@get("/api/devices", dependencies={"devices": Provide(get_devices)})
async def devices(devices: Devices) -> t.List[APIDevice]:
    """Retrieve all devices."""
    return devices.export_api()


@get("/api/queries", dependencies={"devices": Provide(get_devices)})
async def queries(devices: Devices) -> t.List[str]:
    """Retrieve all directive names."""
    return devices.directive_names()


@get("/api/info", dependencies={"params": Provide(get_params)})
async def info(params: Params) -> APIParams:
    """Retrieve looking glass parameters."""
    return params.export_api()


@post("/api/query", dependencies={"_state": Provide(get_state)})
async def query(_state: HyperglassState, request: Request, data: Query) -> QueryResponse:
    """Ingest request data pass it to the backend application to perform the query."""

    timestamp = datetime.now(UTC)

    # Initialize cache
    cache = _state.redis

    # Use hashed `data` string as key for for k/v cache store so
    # each command output value is unique.
    cache_key = f"hyperglass.query.{data.digest()}"

    _log = log.bind(query=data.summary())

    _log.info("Starting query execution")

    cache_response = None if data.force else cache.get_map(cache_key, "output")
    json_output = False
    cached = False
    runtime = 65535

    if cache_response:
        _log.bind(cache_key=cache_key).debug("Cache hit")

        # If a cached response exists, reset the expiration time.
        cache.expire(cache_key, expire_in=_state.params.cache.timeout)

        cached = True
        runtime = 0
        timestamp = cache.get_map(cache_key, "timestamp")

    elif not cache_response:
        _log.bind(cache_key=cache_key).debug("Cache miss")

        timestamp = data.timestamp

        starttime = time.time()

        if _state.params.fake_output:
            # Return fake, static data for development purposes, if enabled.
            output = await fake_output(
                query_type=data.query_type,
                structured=data.device.structured_output or False,
            )
        else:
            # Pass request to execution module
            output = await execute(data)

        endtime = time.time()
        elapsedtime = round(endtime - starttime, 4)
        _log.debug("Runtime: {!s} seconds", elapsedtime)

        if output is None:
            raise HyperglassError(message=_state.params.messages.general, alert="danger")

        json_output = is_type(output, OutputDataModel)

        if json_output:
            # Export structured output as JSON string to guarantee value
            # is serializable, then convert it back to a dict.
            as_json = output.export_json()
            raw_output = json.loads(as_json)
        else:
            raw_output = str(output)

        runtime = int(round(elapsedtime, 0))

        response_format = "application/json" if json_output else "text/plain"
        query_labels = {
            "location": data.device.display_name or data.device.name,
            "type": data.directive.name,
        }

        with cache.pipeline() as pipe:
            pipe.set_map_item(cache_key, "output", raw_output)
            pipe.set_map_item(cache_key, "timestamp", timestamp)
            pipe.set_map_item(cache_key, "query", data.dict())
            pipe.set_map_item(cache_key, "query_labels", query_labels)
            pipe.set_map_item(cache_key, "format", response_format)
            pipe.set_map_item(cache_key, "runtime", runtime)
            pipe.set_map_item(cache_key, "level", "success")
            pipe.set_map_item(cache_key, "keywords", [])
            pipe.expire(cache_key, expire_in=_state.params.cache.timeout)

        _log.bind(cache_timeout=_state.params.cache.timeout).debug("Response cached")

    # If it does, return the cached entry
    cache_response = cache.get_map(cache_key, "output")

    if cached:
        # Read format from cache; fall back to detecting from output type for old entries.
        response_format = cache.get_map(cache_key, "format") or (
            "application/json" if is_type(cache_response, t.Dict) else "text/plain"
        )
    _log.info("Execution completed")

    response = {
        "output": cache_response,
        "id": cache_key,
        "cached": cached,
        "runtime": runtime,
        "timestamp": timestamp,
        "format": response_format,
        "random": data.random(),
        "level": "success",
        "keywords": [],
    }

    return Response(
        response,
        background=BackgroundTask(
            send_webhook,
            params=_state.params,
            data=data,
            request=request,
            timestamp=timestamp,
        ),
    )


@post("/api/query/share/{cache_id:str}", dependencies={"_state": Provide(get_state)})
async def share_create(
    _state: HyperglassState,
    request: Request,
    cache_id: str,
) -> Response:
    """Promote a cached query result to a long-lived shareable snapshot."""
    # TODO: make configurable via params.messages (no existing precedent for
    # messages-driven HTTP 404/410 detail strings in this file).
    if not _state.params.cache.share_enabled:
        raise NotFoundException("Sharing is disabled.")

    digest = cache_id.removeprefix("hyperglass.query.")
    cache_key = f"hyperglass.query.{digest}"

    cache = _state.redis
    # Reads must happen on the live manager (not the pipeline) so values are
    # returned immediately rather than queued.
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

    with cache.pipeline() as pipe:
        for field in ("output", "timestamp", "query", "query_labels",
                      "format", "runtime", "level", "keywords"):
            pipe.set_map_item(share_key, field, cache.get_map(cache_key, field))
        pipe.set_map_item(share_key, "created_at", now)
        pipe.set_map_item(share_key, "expires_at", expires_at)
        pipe.expire(share_key, expire_in=_state.params.cache.share_timeout)

    resp = ShareCreateResponse(
        id=share_id,
        url=_build_share_url(_state.params, request, share_id),
        expires_at=expires_at,
    )
    return Response(resp.model_dump(by_alias=True, mode="json"), status_code=201)


@get("/api/query/share/{share_id:str}", dependencies={"_state": Provide(get_state)})
async def share_get(_state: HyperglassState, share_id: str) -> Response:
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

    resp = ShareResponse(
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
    return Response(resp.model_dump(by_alias=True, mode="json"))
