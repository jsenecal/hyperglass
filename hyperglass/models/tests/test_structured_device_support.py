"""Retain legacy structured defaults and require opt-in for additional parsers."""

import pytest

from hyperglass.constants import DEFAULT_STRUCTURED_OUTPUT, SUPPORTED_STRUCTURED_OUTPUT
from hyperglass.models.config.devices import Device


@pytest.mark.parametrize("platform", SUPPORTED_STRUCTURED_OUTPUT)
def test_structured_output_opt_in(platform):
    config = {
        "name": "test",
        "address": "127.0.0.1",
        "platform": platform,
        "credential": {"username": "lg", "password": ""},
        "attrs": {"source4": "192.0.2.1", "source6": "2001:db8::1"},
    }
    assert Device(**config).structured_output is (platform in DEFAULT_STRUCTURED_OUTPUT)
    assert Device(**config, structured_output=False).structured_output is False
    assert Device(**config, structured_output=True).structured_output is True
