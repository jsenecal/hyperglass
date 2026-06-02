"""Tests for Params.public_url."""

# Project
from hyperglass.models.config.params import Params


def test_public_url_default_none():
    p = Params()
    assert p.public_url is None


def test_public_url_set_to_https_url():
    p = Params(public_url="https://lg.example.com")
    # Pydantic AnyHttpUrl normalization varies across 2.x patch versions
    # (sometimes adds trailing slash, sometimes preserves). Use startswith
    # so the test is robust to either form.
    assert str(p.public_url).startswith("https://lg.example.com")
