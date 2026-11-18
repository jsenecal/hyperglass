"""Malformed router data raises a parsing error instead of an attribute error."""

import pytest

from hyperglass.exceptions.private import ParsingError
from hyperglass.models.parsing.cisco_ios import parse_cisco_ios_routes
from hyperglass.plugins._builtin.bgp_route_frr import parse_frr
from hyperglass.plugins._builtin.bgp_route_openbgpd import parse_openbgpd


@pytest.mark.parametrize("parse", [parse_frr, parse_openbgpd])
@pytest.mark.parametrize("payload", ["[]", "null", "1", '"text"'])
def test_non_object_json_is_a_parsing_error(parse, payload):
    with pytest.raises(ParsingError):
        parse([payload])


def test_blank_summary_path_does_not_raise_index_error():
    text = (
        "     Network          Next Hop            Metric LocPrf Weight Path\n"
        "*>   192.0.2.0/24     192.0.2.1                0         32768     "
    )
    routes = parse_cisco_ios_routes(text)
    assert not routes or routes[0]["as_path"] == []
