"""Test external http client.

These tests are hermetic: the low-level reachability probe and the httpx
request layer are stubbed so the suite never touches the network. A small
fake reproduces the subset of httpbin.org echo behaviour the client relies on
(`/get`, `/post`, and a `/delay/*` endpoint that simulates a timeout).
"""

# Standard Library
import asyncio

# Third Party
import httpx
import pytest

# Project
from hyperglass.exceptions.private import ExternalError
from hyperglass.models.config.logging import Http

# Local
from .._base import BaseExternal

config = Http(provider="generic", host="https://httpbin.org")

BASE_URL = "https://httpbin.org"


def _fake_response(**request: object) -> httpx.Response:
    """Mimic httpbin's echo endpoints from the kwargs BaseExternal sends.

    `BaseExternal._build_request` passes `method`, `url` (the endpoint path),
    and optionally `params`/`json`/`timeout` to `httpx.Client.request`.
    """
    # `_build_request` strips the leading slash; httpx rejoins against base_url.
    path = str(request["url"]).lstrip("/")
    full_url = f"{BASE_URL}/{path}"
    params = request.get("params") or {}
    json_body = request.get("json") or {}

    if path.startswith("delay/"):
        # Simulate the timeout httpbin would produce for a slow endpoint.
        raise httpx.ConnectTimeout(
            "simulated timeout", request=httpx.Request(request["method"], full_url)
        )
    if path == "get":
        return httpx.Response(200, json={"url": full_url, "args": dict(params)})
    if path == "post":
        return httpx.Response(200, json={"json": json_body})
    return httpx.Response(404, json={"error": f"no fake for {path}"})


@pytest.fixture(autouse=True)
def _stub_network(monkeypatch):
    """Stub the socket reachability probe and the httpx request layer."""
    # `_test`/`_atest` open a raw socket to host:443 — skip it.
    monkeypatch.setattr(BaseExternal, "_test", lambda self: True)

    def _sync_request(self, **kwargs):
        return _fake_response(**kwargs)

    async def _async_request(self, **kwargs):
        return _fake_response(**kwargs)

    monkeypatch.setattr(httpx.Client, "request", _sync_request)
    monkeypatch.setattr(httpx.AsyncClient, "request", _async_request)


def test_base_external_sync():
    with BaseExternal(base_url=BASE_URL, config=config) as client:
        res1 = client._get("/get")
        res2 = client._get("/get", params={"key": "value"})
        res3 = client._post("/post", data={"strkey": "value", "intkey": 1})
    assert res1["url"] == "https://httpbin.org/get"
    assert res2["args"].get("key") == "value"
    assert res3["json"].get("strkey") == "value"
    assert res3["json"].get("intkey") == 1

    with pytest.raises(ExternalError):
        with BaseExternal(base_url=BASE_URL, config=config, timeout=2) as client:
            client._get("/delay/4")


async def _run_test_base_external_async():
    async with BaseExternal(base_url=BASE_URL, config=config) as client:
        res1 = await client._aget("/get")
        res2 = await client._aget("/get", params={"key": "value"})
        res3 = await client._apost("/post", data={"strkey": "value", "intkey": 1})
    assert res1["url"] == "https://httpbin.org/get"
    assert res2["args"].get("key") == "value"
    assert res3["json"].get("strkey") == "value"
    assert res3["json"].get("intkey") == 1

    with pytest.raises(ExternalError):
        async with BaseExternal(base_url=BASE_URL, config=config, timeout=2) as client:
            await client._aget("/delay/4")


def test_base_external_async():
    asyncio.run(_run_test_base_external_async())
