"""A completed BGP query never starts another SSH session."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from hyperglass.execution.drivers.ssh_netmiko import delay_factor_override


@pytest.mark.parametrize("platform", ["mikrotik_routeros", "frr"])
@pytest.mark.parametrize("output", ["empty", "routes"])
@pytest.mark.asyncio
async def test_completed_queries_run_once(monkeypatch, platform, output):
    from hyperglass.api import routes

    query = SimpleNamespace(device=SimpleNamespace(platform=platform))
    execute = AsyncMock(return_value=output)
    monkeypatch.setattr(routes, "execute", execute)
    assert await routes._execute_query(query) == output
    execute.assert_awaited_once_with(query)
    assert delay_factor_override.get() is None


@pytest.mark.asyncio
async def test_failed_query_preserves_the_error(monkeypatch):
    from hyperglass.api import routes

    execute = AsyncMock(side_effect=RuntimeError("connection failed"))
    monkeypatch.setattr(routes, "execute", execute)
    with pytest.raises(RuntimeError, match="connection failed"):
        await routes._execute_query(SimpleNamespace())
    execute.assert_awaited_once()
