"""Regression tests for bounded lookups and optional structured enrichment."""

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import Mock, AsyncMock

import pytest

from hyperglass.state import use_state
from hyperglass.external import ip_enrichment
from hyperglass.models.config.params import Params
from hyperglass.models.data.traceroute import TracerouteHop, TracerouteResult
from hyperglass.execution.drivers._common import Connection
from hyperglass.plugins._builtin.traceroute_ip_enrichment import ZTracerouteIpEnrichment


@pytest.mark.parametrize(
    "address", ["router.example", "damaged", "192.0.2.999", "2001:db8::bad::1"]
)
def test_invalid_hop_address_does_not_reject_trace(address):
    hop = TracerouteHop(hop_number=1, ip_address=address, rtt1=1.2)
    assert hop.ip_address is None
    assert hop.rtt1 == 1.2


@pytest.mark.asyncio
async def test_output_plugins_run_outside_event_loop():
    started = threading.Event()
    release = threading.Event()
    thread_ids = []

    def process(**kwargs):
        thread_ids.append(threading.get_ident())
        started.set()
        if not release.wait(timeout=2):
            raise RuntimeError("Output processing blocked the event loop")
        return "parsed"

    driver = SimpleNamespace(plugin_manager=SimpleNamespace(execute=process), query_data=None)
    task = asyncio.create_task(Connection.response(driver, ["output"]))
    try:
        async with asyncio.timeout(3):
            while not started.is_set():
                await asyncio.sleep(0)
        assert thread_ids != [threading.get_ident()]
    finally:
        release.set()
    assert await task == "parsed"


@pytest.mark.parametrize("enabled", [False, True])
def test_traceroute_never_performs_supplemental_reverse_dns(monkeypatch, enabled):
    use_state().cache.set(
        "params", Params(structured={"ip_enrichment": {"enrich_traceroute": enabled}})
    )
    reverse = Mock(side_effect=AssertionError("Unexpected reverse DNS"))
    monkeypatch.setattr("socket.gethostbyaddr", reverse)
    enrich_ip = AsyncMock()
    enrich_asn = AsyncMock()
    monkeypatch.setattr(TracerouteResult, "enrich_with_ip_enrichment", enrich_ip)
    monkeypatch.setattr(TracerouteResult, "enrich_asn_organizations", enrich_asn)
    output = TracerouteResult(
        target="192.0.2.2",
        source="test",
        hops=[{"hop_number": 1, "ip_address": "192.0.2.1", "hostname": "router.example"}],
    )
    assert ZTracerouteIpEnrichment().process(output=output, query=None) is output
    assert output.hops[0].hostname == "router.example"
    assert enrich_ip.await_count == int(enabled)
    assert enrich_asn.await_count == int(enabled)
    reverse.assert_not_called()


@pytest.mark.parametrize("name", ["Netflix", "Equinix", "Citrix", "Example Internet Exchange"])
@pytest.mark.asyncio
async def test_organization_names_never_replace_valid_asns(name):
    service = ip_enrichment.IPEnrichmentService()
    service._cache_ip("1.1.1.1", (65000, name, "1.1.1.0/24"))
    single = await service.lookup_ip("1.1.1.1")
    bulk = await service.lookup_ips_bulk(["1.1.1.1"])
    assert single.asn == bulk["1.1.1.1"].asn == 65000
    assert not single.is_ixp
    assert not bulk["1.1.1.1"].is_ixp


def test_only_explicit_exchange_without_asn_is_an_ixp():
    service = ip_enrichment.IPEnrichmentService()
    assert service._ip_info_from_lookup("1.1.1.1", None, "Example Internet Exchange", None).is_ixp
    assert not service._ip_info_from_lookup("1.1.1.1", None, "Netflix", None).is_ixp


def test_ip_cache_has_capacity_and_expiry(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(ip_enrichment.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(ip_enrichment, "IP_CACHE_MAXSIZE", 2)
    service = ip_enrichment.IPEnrichmentService()
    for address in ["1.1.1.1", "8.8.8.8", "9.9.9.9"]:
        service._cache_ip(address, (65000, "Example", None))
    assert len(service._ip_cache) == 2
    assert service._cached_ip("1.1.1.1") is None
    assert service._cached_ip("8.8.8.8") == (65000, "Example", None)
    now[0] += ip_enrichment.IP_CACHE_TTL + 1
    assert service._cached_ip("8.8.8.8") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("bulk", [False, True])
async def test_whois_responses_have_a_byte_limit(monkeypatch, bulk):
    sizes = []
    connection = Mock()
    connection.__enter__ = Mock(return_value=connection)
    connection.__exit__ = Mock(return_value=False)

    def receive(size):
        sizes.append(size)
        return b"x" * size

    connection.recv.side_effect = receive
    monkeypatch.setattr(ip_enrichment.socket, "create_connection", Mock(return_value=connection))
    service = ip_enrichment.IPEnrichmentService()
    if bulk:
        await service._query_bgp_tools_bulk(["1.1.1.1"])
    else:
        await service._query_bgp_tools_for_ip("1.1.1.1")
    assert sum(sizes) == ip_enrichment.WHOIS_MAX_BYTES


def test_parsers_wait_for_directives_and_traceroute_ui():
    from hyperglass.plugins import _builtin

    assert not hasattr(_builtin, "BGPSTRRoutePluginHuawei")
    assert not hasattr(_builtin, "BGPSTRRoutePluginMikrotik")
    assert not hasattr(_builtin, "TraceroutePluginFrr")
