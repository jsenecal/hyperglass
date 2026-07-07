"""Regression tests for the Webhook model validator.

Tracks https://github.com/thatmattlove/hyperglass/issues/282 — Slack / MS Teams
/ generic HTTP logging silently failed because the `mode="before"` validator
treated its raw-dict input as a model instance.
"""

# Standard Library
import typing as t
from datetime import datetime, timezone

# Project
from hyperglass.models.webhook import Webhook


def _query(source: str, network: t.Optional[dict] = None) -> dict:
    return {
        "query_location": "test",
        "query_type": "bgp_route",
        "query_target": "192.0.2.0/24",
        "headers": {},
        "source": source,
        "network": network if network is not None else {"prefix": "192.0.2.0/24", "asn": "65000"},
        "timestamp": datetime.now(timezone.utc),
    }


def test_webhook_constructs_with_public_source():
    """The validator must not raise on a normal public-IP source."""
    hook = Webhook(**_query(source="203.0.113.7"))
    assert hook.source == "203.0.113.7"
    assert hook.network.prefix == "192.0.2.0/24"
    assert hook.network.asn == "65000"


def test_webhook_resets_network_for_localhost_v4():
    """A 127.0.0.1 source should clear the network info to defaults."""
    hook = Webhook(**_query(source="127.0.0.1"))
    assert hook.source == "127.0.0.1"
    # WebhookNetwork defaults all fields to "Unknown" when given an empty dict.
    assert hook.network.prefix == "Unknown"
    assert hook.network.asn == "Unknown"


def test_webhook_resets_network_for_localhost_v6():
    """`::1` should also be treated as localhost."""
    hook = Webhook(**_query(source="::1"))
    assert hook.network.prefix == "Unknown"
    assert hook.network.asn == "Unknown"


def test_webhook_slack_payload_renders():
    """End-to-end: the Slack payload must build without raising."""
    hook = Webhook(**_query(source="203.0.113.7"))
    payload = hook.slack()
    assert payload["text"]
    assert any("203.0.113.7" in str(block) for block in payload["blocks"])


def test_webhook_msteams_payload_renders():
    """End-to-end: the MS Teams payload must build without raising."""
    hook = Webhook(**_query(source="203.0.113.7"))
    payload = hook.msteams()
    assert payload["@type"] == "MessageCard"
