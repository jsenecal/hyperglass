"""Tests for share helper functions."""

# Standard Library
import re


def test_generate_share_id_format(state):
    from hyperglass.api.routes import _generate_share_id
    cache = state.redis
    sid = _generate_share_id(cache)
    assert isinstance(sid, str)
    # secrets.token_urlsafe(8) -> 11 chars, [A-Za-z0-9_-]
    assert re.fullmatch(r"[A-Za-z0-9_-]{11}", sid)


def test_generate_share_id_unique(state):
    from hyperglass.api.routes import _generate_share_id
    cache = state.redis
    seen = {_generate_share_id(cache) for _ in range(100)}
    assert len(seen) == 100


def test_generate_share_id_collision_retry(state, monkeypatch):
    """If the first ID exists, the helper retries."""
    from hyperglass.api import routes
    cache = state.redis

    cache.set_map_item("hyperglass.share.AAAAAAAAAAA", "output", "x")

    sequence = iter(["AAAAAAAAAAA", "BBBBBBBBBBB"])
    monkeypatch.setattr(
        routes.secrets, "token_urlsafe", lambda n: next(sequence)
    )
    sid = routes._generate_share_id(cache)
    assert sid == "BBBBBBBBBBB"
