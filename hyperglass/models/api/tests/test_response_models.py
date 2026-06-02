"""Tests for share response models."""

# Standard Library
from datetime import datetime, timezone

# Project
from hyperglass.models.api.response import QueryResponse, ShareResponse, ShareCreateResponse


def test_query_response_includes_id():
    # `timestamp` is a string per the existing QueryResponse contract.
    r = QueryResponse(
        output="ok",
        id="hyperglass.query.deadbeef",
        cached=False,
        runtime=1,
        timestamp="2026-05-01 12:00:00",
        format="text/plain",
        random="r",
        level="success",
        keywords=[],
    )
    assert r.id == "hyperglass.query.deadbeef"


def test_share_create_response_shape():
    expires = datetime.now(timezone.utc)
    r = ShareCreateResponse(id="abc", url="https://lg.example.com/result/abc", expires_at=expires)
    assert r.id == "abc"
    assert r.url.endswith("/result/abc")
    # camelCase alias on the wire
    dumped = r.model_dump(by_alias=True)
    assert "expiresAt" in dumped


def test_share_response_shape():
    expires = datetime.now(timezone.utc)
    r = ShareResponse(
        id="abc",
        output="ok",
        cached=True,
        shared=True,
        runtime=1,
        timestamp=datetime.now(timezone.utc),
        format="text/plain",
        level="success",
        keywords=[],
        query={
            "query_location": "test1",
            "query_target": "192.0.2.0/24",
            "query_type": "juniper_bgp_route",
        },
        query_labels={"location": "test1", "type": "BGP Route"},
        created_at=datetime.now(timezone.utc),
        expires_at=expires,
    )
    assert r.shared is True
    assert r.query_labels["location"] == "test1"
    # Note: alias_generator only affects the model's own fields, not nested
    # dict keys. `r.query["query_location"]` stays snake_case on the wire.
    dumped = r.model_dump(by_alias=True)
    assert dumped["query"]["query_location"] == "test1"
