"""Test state recovery."""

# Standard Library
import typing as t
import asyncio
import pickle
import threading
from fnmatch import fnmatch

# Third Party
import pytest

# Project
from hyperglass.exceptions.private import StateError

# Local
from .. import recovery
from ..redis import RedisManager
from ..store import HyperglassState
from ..recovery import rebuild_state

NAMESPACE = "hyperglass.state"
STATE_KEYS = tuple(f"{NAMESPACE}.{key}" for key in recovery.REQUIRED_KEYS)
LOCK = f"{NAMESPACE}.rebuild.lock"


class FakeRedis:
    """Minimal stand-in for a Redis client."""

    data: t.Dict[str, t.Any]

    def __init__(self, **data: t.Any) -> None:
        self.data = dict(data)

    def exists(self, *names: str) -> int:
        """Count stored keys."""
        return sum(1 for name in names if name in self.data)

    def get(self, name: str) -> t.Any:
        """Read a stored value."""
        return self.data.get(name)

    def set(self, name: str, value: t.Any, nx: bool = False, ex: int = None) -> t.Optional[bool]:
        """Store a value with optional uniqueness."""
        if nx and name in self.data:
            return None
        self.data[name] = value
        return True

    def delete(self, *names: str) -> None:
        """Remove stored keys."""
        for name in names:
            self.data.pop(name, None)

    def scan_iter(self, match: str, count: int = None) -> t.Generator[str, None, None]:
        """Yield matching keys."""
        yield from [key for key in list(self.data) if fnmatch(key, match)]


def cache_with(*keys: str) -> RedisManager:
    """Build a cache manager containing `keys`."""
    return RedisManager(
        instance=FakeRedis(**dict.fromkeys(keys, pickle.dumps(None))), namespace=NAMESPACE
    )


def state_with(cache: RedisManager) -> HyperglassState:
    """Build a state instance around `cache`, without opening a Redis connection."""
    state = HyperglassState.__new__(HyperglassState)
    state.redis = cache
    return state


@pytest.fixture(autouse=True)
def no_cooldown():
    """Ensure a failure in one test does not suppress the rebuild in the next."""
    recovery._last_failure = 0.0
    yield
    recovery._last_failure = 0.0


@pytest.fixture
def instant_sleep(monkeypatch):
    """Remove the poll delay so waiting tests do not take real time."""
    monkeypatch.setattr(recovery.time, "sleep", lambda _: None)


def test_populated_state_is_not_rebuilt(monkeypatch):
    """State that is present must not be re-initialized."""
    calls = []
    monkeypatch.setattr(recovery, "_initialize", lambda: calls.append(True))
    cache = cache_with(*STATE_KEYS)

    assert rebuild_state(cache) is True
    assert calls == []


def test_partial_state_is_rebuilt(monkeypatch):
    """State missing any required key is rebuilt, and the lock is released."""
    cache = cache_with(STATE_KEYS[0])

    def initialize():
        for key in STATE_KEYS:
            cache.instance.data[key] = pickle.dumps(None)

    monkeypatch.setattr(recovery, "_initialize", initialize)

    assert rebuild_state(cache) is True
    assert cache.instance.exists(*STATE_KEYS) == len(STATE_KEYS)
    assert LOCK not in cache.instance.data


def test_waits_for_another_process(monkeypatch):
    """A process that loses the lock waits instead of rebuilding in parallel."""
    calls = []
    monkeypatch.setattr(recovery, "_initialize", lambda: calls.append(True))
    cache = cache_with(LOCK)

    def sleep(_):
        for key in STATE_KEYS:
            cache.instance.data[key] = pickle.dumps(None)
        cache.instance.delete(LOCK)  # the winner finished and released the lock

    monkeypatch.setattr(recovery.time, "sleep", sleep)

    assert rebuild_state(cache) is True
    assert calls == [], "rebuilt state while another process held the lock"


def test_wait_times_out(monkeypatch, instant_sleep):
    """Waiting on a lock holder that never finishes eventually gives up."""
    monkeypatch.setattr(recovery, "WAIT_TIMEOUT", 0.01)
    cache = cache_with(LOCK)

    assert rebuild_state(cache) is False


def test_failure_backs_off(monkeypatch):
    """A failed rebuild is not retried on every request."""
    calls = []

    def initialize():
        calls.append(True)
        raise RuntimeError("bad config")

    monkeypatch.setattr(recovery, "_initialize", initialize)
    cache = cache_with()

    assert rebuild_state(cache) is False
    assert LOCK not in cache.instance.data, "lock left behind after a failed rebuild"

    assert rebuild_state(cache) is False
    assert len(calls) == 1, "configuration was re-read during the failure cooldown"


def test_property_read_rebuilds_lost_state(monkeypatch):
    """Reading a state property directly must recover, not just `use_state`.

    `Query.device` and the query route read `state.devices` and `state.params` off an
    instance on every request, so this is the path that fails in production.
    """
    cache = cache_with()
    state = state_with(cache)

    def initialize():
        cache.instance.data.update(dict.fromkeys(STATE_KEYS, pickle.dumps(None)))
        cache.set("devices", ["recovered"])

    monkeypatch.setattr(recovery, "_initialize", initialize)

    assert state.devices == ["recovered"]


def test_property_read_raises_when_rebuild_fails(monkeypatch):
    """A rebuild that cannot repopulate state must surface the original error."""

    def initialize():
        raise RuntimeError("bad config")

    monkeypatch.setattr(recovery, "_initialize", initialize)
    state = state_with(cache_with())

    with pytest.raises(StateError):
        _ = state.devices


def test_clear_is_scoped_to_hyperglass():
    """Clearing state must not delete keys belonging to other applications."""
    cache = cache_with(*STATE_KEYS, "someotherapp.session.1")
    state = state_with(cache)

    state.clear()

    assert cache.instance.exists(*STATE_KEYS) == 0
    assert "someotherapp.session.1" in cache.instance.data


def test_configuration_without_plugins_is_not_ready(monkeypatch):
    cache = cache_with(
        *(f"{NAMESPACE}.{key}" for key in ("params", "directives", "devices", "ui_params"))
    )
    calls = []

    def initialize():
        calls.append(True)
        cache.instance.data.update(dict.fromkeys(STATE_KEYS, pickle.dumps(None)))

    monkeypatch.setattr(recovery, "_initialize", initialize)
    assert rebuild_state(cache) is True
    assert calls == [True]


def test_incomplete_initialization_is_retried_after_cooldown(monkeypatch):
    cache = cache_with()
    monkeypatch.setattr(recovery, "_initialize", lambda: cache.set("params", {}))
    assert rebuild_state(cache) is False
    assert not recovery.is_populated(cache)
    recovery._last_failure = 0.0

    def initialize():
        cache.instance.data.update(dict.fromkeys(STATE_KEYS, pickle.dumps(None)))

    monkeypatch.setattr(recovery, "_initialize", initialize)
    assert rebuild_state(cache) is True


@pytest.mark.asyncio
@pytest.mark.parametrize("waiting", [False, True])
async def test_async_recovery_does_not_block_event_loop(monkeypatch, waiting):
    cache = cache_with(LOCK) if waiting else cache_with()
    state = state_with(cache)
    started = threading.Event()
    release = threading.Event()
    thread_ids = []

    def initialize_or_wait(*args):
        thread_ids.append(threading.get_ident())
        started.set()
        if not release.wait(timeout=2):
            raise RuntimeError("Event loop did not continue during recovery")
        cache.instance.data.update(dict.fromkeys(STATE_KEYS, pickle.dumps(None)))
        cache.instance.delete(LOCK)
        return True

    monkeypatch.setattr(
        recovery, "_wait_for_rebuild" if waiting else "_initialize", initialize_or_wait
    )
    task = asyncio.create_task(state.ensure_ready())
    try:
        async with asyncio.timeout(3):
            while not started.is_set():
                await asyncio.sleep(0)
        assert thread_ids != [threading.get_ident()]
    finally:
        release.set()
        await task


@pytest.mark.asyncio
async def test_mid_request_state_loss_never_rebuilds_on_event_loop(monkeypatch):
    calls = []
    monkeypatch.setattr(recovery, "_initialize", lambda: calls.append(True))
    with pytest.raises(StateError):
        _ = state_with(cache_with()).devices
    assert calls == []


def test_generation_and_plugin_readiness_follow_complete_initialization(monkeypatch):
    from hyperglass import configuration
    from hyperglass.state import use_state
    from hyperglass.plugins import register_all_plugins
    from hyperglass.models.directive import Directives
    from hyperglass.models.config.devices import Devices

    state = use_state()
    devices = Devices(
        {
            "name": "test",
            "address": "192.0.2.1",
            "platform": "frr",
            "credential": {"username": "test", "password": "test"},
            "attrs": {"source4": "192.0.2.1", "source6": "2001:db8::1"},
        }
    )
    monkeypatch.setattr(configuration, "init_files", lambda: None)
    monkeypatch.setattr(configuration, "init_directives", Directives)
    monkeypatch.setattr(configuration, "init_ui_params", lambda **kwargs: {})
    configuration.init_user_config(params=state.params, devices=devices)
    first_generation = state.generation
    assert first_generation is not None
    assert not recovery.is_populated(state.redis)
    register_all_plugins()
    assert recovery.is_populated(state.redis)
    assert state.plugins("output")

    configuration.init_user_config(params=state.params, devices=devices)
    assert state.generation != first_generation
    assert not recovery.is_populated(state.redis)


def test_api_request_recovers_before_reading_state(monkeypatch):
    from litestar.testing import TestClient

    from hyperglass.state import use_state
    from hyperglass.settings import Settings

    monkeypatch.setattr(Settings, "disable_ui", True)
    from hyperglass.api import app

    state = use_state()
    params = state.params
    calls = []

    def initialize():
        calls.append(threading.get_ident())
        for key in recovery.REQUIRED_KEYS:
            state.cache.set(key, None)
        state.cache.set("params", params)

    monkeypatch.setattr(recovery, "_initialize", initialize)
    state.clear()
    with TestClient(app=app) as client:
        response = client.get("/api/info")
    assert response.status_code == 200
    assert len(calls) == 1
