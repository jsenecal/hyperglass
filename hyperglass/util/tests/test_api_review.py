"""Regression coverage for query completion and enrichment cache boundaries."""

from importlib import import_module
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from hyperglass.state import use_state
from hyperglass.settings import Settings
from hyperglass.models.api import Query
from hyperglass.models.config.params import Params
from hyperglass.models.config.devices import Devices
from hyperglass.models.data.bgp_route import BGPRouteTable


@pytest.fixture
def routes(monkeypatch):
    monkeypatch.setattr(Settings, "disable_ui", True)
    return import_module("hyperglass.api.routes")


@pytest.mark.asyncio
async def test_empty_mikrotik_route_table_completes_without_retries(monkeypatch, routes):
    output = BGPRouteTable(vrf="default", routes=[], winning_weight="high")
    execute = AsyncMock(return_value=output)
    monkeypatch.setattr(routes, "execute", execute)
    query = SimpleNamespace(
        device=SimpleNamespace(platform="mikrotik_routeros", name="test"),
        query_type="__hyperglass_mikrotik_bgp_route_table__",
    )
    assert await routes._execute_query(query) is output
    execute.assert_awaited_once_with(query)


@pytest.mark.parametrize(
    "key", ["params", "hyperglass.state.params", "generation", "hyperglass.query.invalid"]
)
@pytest.mark.asyncio
async def test_enrichment_never_reads_non_query_cache_keys(routes, key):
    use_state().cache.set("params", Params())
    assert await routes.query_enrichment.fn(query_id=key) == {"status": "not_found"}


@pytest.mark.asyncio
async def test_enrichment_accepts_a_query_digest(routes):
    key = f"hyperglass.query.{'a' * 64}"
    use_state().cache.set_map_item(key, "output", {"routes": []})
    assert await routes.query_enrichment.fn(query_id=key) == {
        "status": "complete",
        "output": {"routes": []},
    }


@pytest.mark.parametrize(
    "kind,flag",
    [("traceroute", "enable_for_traceroute"), ("bgp_route_table", "enable_for_bgp_route")],
)
def test_builtin_ids_honor_structured_feature_flags(kind, flag):
    state = use_state()
    state.cache.set("params", Params(structured={flag: False}))
    state.cache.set(
        "devices",
        Devices(
            {
                "name": "test",
                "address": "192.0.2.1",
                "platform": "frr",
                "credential": {"username": "test", "password": "test"},
                "attrs": {"source4": "192.0.2.1", "source6": "2001:db8::1"},
            }
        ),
    )
    query = Query(
        queryLocation="test", queryType=f"__hyperglass_frr_{kind}__", queryTarget="1.1.1.1"
    )
    assert query.device.structured_output is False
    assert state.devices["test"].structured_output is True
