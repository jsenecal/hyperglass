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
    # Project
    from hyperglass.state import HyperglassState


def _seed_stub_state() -> None:
    """Seed Redis with minimal stub state so api modules can be imported during collection.

    hyperglass.api reads Redis at module import time. pytest loads this
    top-level conftest before any nested conftest in both
    path-targeted and directory runs, so module-level seeding here is
    guaranteed to precede the first ``import hyperglass.api``. A
    ``pytest_configure`` hook defined in this conftest would NOT be sufficient:
    it fires after this module body, and on direct test-file invocations
    (``pytest hyperglass/api/tests/test_x.py``) nested conftests are imported
    during initial conftest loading — before any configure hook — triggering the
    ``hyperglass.api`` import with unseeded Redis.

    This overwrites the params/directives/devices/ui_params keys unconditionally —
    never point the test suite at a Redis instance holding real configuration
    (the ``state`` fixture teardown flushes the whole DB anyway, so a disposable
    Redis is already a hard requirement).
    """
    _state = use_state()
    _params = Params()
    _directives = Directives.new()

    with _state.cache.pipeline() as pipeline:
        pipeline.set("params", _params)
        pipeline.set("directives", _directives)

    _devices = Devices()
    _ui_params = init_ui_params(params=_params, devices=_devices)

    with _state.cache.pipeline() as pipeline:
        pipeline.set("devices", _devices)
        pipeline.set("ui_params", _ui_params)


_seed_stub_state()


@pytest.fixture
def params() -> t.Dict[str, t.Any]:
    """Provide default Params overrides for the state fixture."""
    return {}


@pytest.fixture
def devices() -> t.Sequence[t.Dict[str, t.Any]]:
    """Seed device definitions."""
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
    """Seed directive definitions."""
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
    """Test fixture to initialize Redis store."""
    _state = use_state()
    _params = Params(**params)
    _directives = Directives.new(*directives)

    with _state.cache.pipeline() as pipeline:
        # Write params and directives to the cache first to avoid a race condition where ui_params
        # or devices try to access params or directives before they're available.
        pipeline.set("params", _params)
        pipeline.set("directives", _directives)

    _devices = Devices(*devices)
    ui_params = init_ui_params(params=_params, devices=_devices)

    with _state.cache.pipeline() as pipeline:
        pipeline.set("devices", _devices)
        pipeline.set("ui_params", ui_params)

    yield _state
    _state.clear()
