"""Tests for the Query.force flag."""


def test_query_force_default_false(state):
    from hyperglass.models.api import Query
    q = Query(query_location="test1", query_target="192.0.2.0/24",
              query_type="juniper_bgp_route")
    assert q.force is False


def test_query_force_true(state):
    from hyperglass.models.api import Query
    q = Query(query_location="test1", query_target="192.0.2.0/24",
              query_type="juniper_bgp_route", force=True)
    assert q.force is True


def test_query_force_does_not_affect_digest(state):
    """The cache key must not depend on the force flag."""
    from hyperglass.models.api import Query
    q1 = Query(query_location="test1", query_target="192.0.2.0/24",
               query_type="juniper_bgp_route", force=False)
    q2 = Query(query_location="test1", query_target="192.0.2.0/24",
               query_type="juniper_bgp_route", force=True)
    assert q1.digest() == q2.digest()
