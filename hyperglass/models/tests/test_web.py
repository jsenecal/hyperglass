"""Tests for new Text fields supporting the share feature."""

# Project
from hyperglass.models.config.web import Text
from hyperglass.models.config.messages import Messages


def test_text_share_defaults():
    t = Text()
    assert t.share_button == "Share"
    assert "{expires}" in t.share_expires_at
    assert "{timestamp}" in t.share_snapshot_banner
    assert t.share_not_found
    assert t.refresh_cooldown
    assert t.requery_tooltip == "Reload Query"


def test_text_history_string_defaults():
    text = Text()
    assert text.history_title == "Recent queries"
    assert text.history_clear_all == "Clear all"
    assert text.history_disabled_hint == "Results for this query type are not saved to history."
    assert text.history_open == "Open"
    assert text.history_delete == "Delete"


def test_messages_history_device_unavailable_default():
    msgs = Messages()
    assert msgs.history_device_unavailable == "The device for this saved query is no longer available."
