"""Regression gate for framework deprecations in hyperglass code.

These deprecations are removed in Litestar v3 / Pydantic v3, so catching their
reintroduction here keeps the path to those majors clear. Each test rebuilds
the relevant object under an error filter — re-running signature parsing /
schema generation so a reintroduced deprecation is re-emitted (and raised)
rather than silently deduplicated after first import.

Third-party deprecations (netmiko telnetlib, paramiko TripleDES) are out of
scope and tracked separately.
"""

# Standard Library
import warnings

# Third Party
import pytest
from litestar import Litestar
from litestar.exceptions import LitestarDeprecationWarning
from pydantic.warnings import PydanticDeprecatedSince20, PydanticDeprecatedSince212


def test_route_handlers_use_no_deprecated_parameter_style(state):
    """Building the app must not emit Litestar inferred-parameter warnings.

    `state` seeds Redis: hyperglass.api reads state at import (module-level
    `STATE = use_state()` and the OpenAPI config).
    """
    # Project
    from hyperglass.api import HANDLERS, OPEN_API

    with warnings.catch_warnings():
        warnings.simplefilter("error", LitestarDeprecationWarning)
        Litestar(route_handlers=HANDLERS, openapi_config=OPEN_API)


@pytest.mark.parametrize("category", [PydanticDeprecatedSince20, PydanticDeprecatedSince212])
def test_models_emit_no_pydantic_deprecations(category):
    """Rebuilding a HyperglassModel schema must not emit Pydantic deprecations.

    Credential extends HyperglassModel, so a force rebuild re-runs both the
    base-model schema generation (catching a reintroduced `json_encoders`) and
    the validator wiring (catching a `mode='after'` classmethod validator).
    """
    # Project
    from hyperglass.models.config.credential import Credential

    with warnings.catch_warnings():
        warnings.simplefilter("error", category)
        Credential.model_rebuild(force=True)
