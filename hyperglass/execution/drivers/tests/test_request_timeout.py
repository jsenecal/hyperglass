"""A request timeout returns the DeviceTimeout error, not an unhandled exception."""

# Standard Library
import time
import asyncio
from types import SimpleNamespace

# Third Party
import pytest

# Project
from hyperglass.execution import main
from hyperglass.exceptions.public import DeviceTimeout


def _query():
    device = SimpleNamespace(id="lab-frr", name="lab-frr", driver="netmiko", proxy=None)
    return SimpleNamespace(
        device=device,
        query_type="__hyperglass_frr_traceroute__",
        query_target="192.0.2.1",
        summary=lambda: "query",
    )


@pytest.fixture
def slow_driver(monkeypatch):
    params = SimpleNamespace(
        request_timeout=2,
        messages=SimpleNamespace(general="error"),
        logging=SimpleNamespace(samples=SimpleNamespace(enable=False), directory=None),
    )
    monkeypatch.setattr(main, "use_state", lambda _: params)

    def factory(collect):
        class Driver:
            def __init__(self, *_):
                pass

            async def response(self, response):
                return response

        Driver.collect = collect
        monkeypatch.setattr(main, "map_driver", lambda _: Driver)

    return factory


@pytest.mark.asyncio
async def test_blocking_session_times_out_as_device_timeout(slow_driver):
    """A device session in an executor thread is cut off inside the request."""

    async def collect(self):
        await asyncio.get_running_loop().run_in_executor(None, time.sleep, 3)
        return ("never",)

    slow_driver(collect)
    started = time.monotonic()
    with pytest.raises(DeviceTimeout):
        await main.execute(_query())
    assert time.monotonic() - started < 2


@pytest.mark.asyncio
async def test_driver_timeout_error_is_not_rewritten(slow_driver):
    """A TimeoutError raised by the driver itself keeps its own type."""

    async def collect(self):
        raise TimeoutError("driver timeout")

    slow_driver(collect)
    with pytest.raises(TimeoutError, match="driver timeout"):
        await main.execute(_query())
