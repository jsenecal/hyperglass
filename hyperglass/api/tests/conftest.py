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
    # Import here so seeding precedes the FIRST IMPORT of hyperglass.api: the
    # module reads state at import time (STATE = use_state(), OpenAPI config),
    # not merely in startup hooks.
    # Project
    from hyperglass.api import app

    with TestClient(app=app) as test_client:
        yield test_client
