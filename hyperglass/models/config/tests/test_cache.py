"""Tests for the Cache config model."""

# Project
from hyperglass.models.config.cache import Cache


def test_cache_defaults():
    cache = Cache()
    assert cache.timeout == 600
    assert cache.show_text is True
    assert cache.share_enabled is True
    assert cache.share_timeout == 604800  # 7 days
    assert cache.share_sliding is False
    assert cache.refresh_min_interval == 120


def test_cache_share_timeout_overridable():
    cache = Cache(share_timeout=2592000)  # 30 days
    assert cache.share_timeout == 2592000


def test_cache_share_disabled():
    cache = Cache(share_enabled=False)
    assert cache.share_enabled is False
