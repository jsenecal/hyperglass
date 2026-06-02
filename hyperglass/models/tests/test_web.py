"""Tests for new Text fields supporting the share feature."""

# Project
from hyperglass.models.config.web import Text


def test_text_share_defaults():
    t = Text()
    assert t.share_button == "Share"
    assert "{expires}" in t.share_expires_at
    assert "{timestamp}" in t.share_snapshot_banner
    assert t.share_not_found
    assert t.refresh_cooldown
