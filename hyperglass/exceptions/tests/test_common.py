"""Tests for the HyperglassError message-formatting helper."""

# Project
from hyperglass.exceptions._common import HyperglassError


def test_safe_format_substitutes_known_keys():
    result = HyperglassError._safe_format("{device} is not allowed", device="rtr1")
    assert result == "rtr1 is not allowed"


def test_safe_format_casts_non_string_values():
    result = HyperglassError._safe_format("count is {n}", n=5)
    assert result == "count is 5"


def test_safe_format_leaves_unknown_placeholders_intact():
    # A placeholder with no matching kwarg must not raise; it is left verbatim.
    result = HyperglassError._safe_format("{device} at {site}", device="rtr1")
    assert result == "rtr1 at {site}"


def test_safe_format_does_not_crash_on_brace_laden_message():
    # Upstream error bodies often embed dict/JSON reprs whose braces look like
    # format fields but are not. Formatting must pass them through unchanged
    # rather than raising KeyError (regression: GitHub issue #7).
    message = "SERVICE UNAVAILABLE: {'data': '<html>503</html>'}"
    result = HyperglassError._safe_format(message)
    assert result == message


def test_safe_format_replaces_repeated_placeholder():
    result = HyperglassError._safe_format("{device} talks to {device}", device="rtr1")
    assert result == "rtr1 talks to rtr1"


def test_safe_format_substitutes_around_literal_braces():
    message = "{name} returned {'error': 'boom'}"
    result = HyperglassError._safe_format(message, name="provider")
    assert result == "provider returned {'error': 'boom'}"
