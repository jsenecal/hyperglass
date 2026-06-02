# Project
from hyperglass.models.api import Query

# Local
from .._construct import Construct


def test_construct(state):
    query = Query(
        queryLocation="test1",
        queryTarget="192.0.2.0/24",
        queryType="juniper_bgp_route",
    )
    constructor = Construct(device=state.devices["test1"], query=query)
    assert constructor.target == "192.0.2.0/24"
