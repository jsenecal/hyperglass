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


def test_build_share_url_uses_params_public_url():
    from hyperglass.api.routes import _build_share_url
    from hyperglass.models.config.params import Params

    params = Params(public_url="https://lg.example.com")
    # Pass None for request — params.public_url wins.
    assert _build_share_url(params, None, "abc123") == \
        "https://lg.example.com/result/abc123"


def test_build_share_url_falls_back_to_request():
    from hyperglass.api.routes import _build_share_url
    from hyperglass.models.config.params import Params

    class FakeURL:
        scheme = "http"
        netloc = "127.0.0.1:8001"

    class FakeRequest:
        headers = {"host": "lg.example.com", "x-forwarded-proto": "https"}
        url = FakeURL()

    params = Params()  # public_url unset
    assert _build_share_url(params, FakeRequest(), "abc123") == \
        "https://lg.example.com/result/abc123"


def test_build_share_url_request_no_proxy_headers():
    from hyperglass.api.routes import _build_share_url
    from hyperglass.models.config.params import Params

    class FakeURL:
        scheme = "http"
        netloc = "127.0.0.1:8001"

    class FakeRequest:
        headers = {}
        url = FakeURL()

    params = Params()
    assert _build_share_url(params, FakeRequest(), "abc") == \
        "http://127.0.0.1:8001/result/abc"
