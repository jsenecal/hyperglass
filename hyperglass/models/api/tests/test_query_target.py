"""Query targets must not carry control characters.

Netmiko's ``normalize_cmd`` only strips trailing whitespace, so an embedded
newline would be sent to the device as a second command line.
"""

# Third Party
import pytest

# Project
from hyperglass.exceptions.public import InputInvalid


@pytest.mark.parametrize(
    "target",
    ("192.0.2.0/24\nshow running-config", "192.0.2.0/24\rreload", "192.0.2.\x00", "192.0.2.1\x7f"),
)
def test_query_rejects_control_characters(state, target: str):
    # Project
    from hyperglass.models.api import Query

    with pytest.raises(InputInvalid):
        Query(query_location="test1", query_target=target, query_type="juniper_bgp_route")


def test_query_rejects_control_characters_in_target_list(state):
    # Project
    from hyperglass.models.api import Query

    with pytest.raises(InputInvalid):
        Query(
            query_location="test1",
            query_target=["192.0.2.0/24", "198.51.100.0/24\nreload"],
            query_type="juniper_bgp_route",
        )


def test_query_still_strips_surrounding_whitespace(state):
    # Project
    from hyperglass.models.api import Query

    query = Query(
        query_location="test1", query_target=" 192.0.2.0/24\n", query_type="juniper_bgp_route"
    )
    assert query.query_target == "192.0.2.0/24"
