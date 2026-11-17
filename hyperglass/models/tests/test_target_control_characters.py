"""Reject command separators before targets reach device commands."""

# Standard Library
from types import SimpleNamespace

# Third Party
import pytest
from pydantic import ValidationError

# Project
from hyperglass.models.api import query as query_module
from hyperglass.plugins import _manager as plugin_manager
from hyperglass.models.directive import Directive, RuleWithIP, RuleWithIPv4, RuleWithIPv6
from hyperglass.defaults.directives import init_builtin_directives
from hyperglass.exceptions.private import InputValidationError
from hyperglass.execution.drivers._construct import Construct

IP_DIRECTIVES = [
    directive
    for directive in init_builtin_directives()
    if any(isinstance(rule, RuleWithIP) for rule in directive.rules)
]

HOSTILE_ZONES = (
    "fe80::1%eth0\nshow version",
    "fe80::1%eth0\rshow version",
    "fe80::1%eth0\r\nshow version",
    "fe80::1%\nshow version",
    "2001:db8::1%x\x00",
    "2001:db8::1%x\x1b[A",
    "2001:db8::1%x\u2028show version",
    "2001:db8::1%eth0;id",
    "2001:db8::1%eth0 | include secret",
    "2001:db8::1%$(id)",
    "2001:db8::%a\nshow version/64",
)


def test_ip_directives_include_both_diagnostics():
    ids = {directive.id for directive in IP_DIRECTIVES}
    assert "__hyperglass_frr_ping__" in ids
    assert "__hyperglass_frr_traceroute__" in ids
    assert "__hyperglass_cisco_ios_ping__" in ids
    assert "__hyperglass_cisco_ios_traceroute__" in ids


@pytest.mark.parametrize("directive", IP_DIRECTIVES, ids=lambda directive: directive.id)
@pytest.mark.parametrize("target", HOSTILE_ZONES)
def test_ip_directives_reject_command_syntax_in_zone(directive, target):
    directive = directive.model_copy(deep=True)
    with pytest.raises(InputValidationError):
        directive.validate_target(target)


@pytest.mark.parametrize("target", ("fe80::1%eth0", "fe80::1%br-lan", "fe80::1%3"))
def test_safe_ipv6_zones_remain_valid(target):
    rule = RuleWithIPv6(condition="::/0", command="ping {target}")
    assert rule.validate_target(target, multiple=False) is True


@pytest.fixture
def query_context(monkeypatch):
    """Exercise the query model without external state or device connections."""
    directive = Directive(id="test-query", name="Test", field=None)
    device = SimpleNamespace(
        name="test-device",
        platform="frr",
        attrs={},
        directives=SimpleNamespace(matching=lambda _: [directive]),
        has_directives=lambda _: True,
    )

    class Devices(list):
        def valid_id_or_name(self, name):
            return name == device.name

        def __getitem__(self, key):
            return device if key == device.name else super().__getitem__(key)

    state = SimpleNamespace(devices=Devices([device]), plugins=lambda _: [])

    def use_state(attr=None):
        return getattr(state, attr) if attr else state

    monkeypatch.setattr(query_module, "use_state", use_state)
    monkeypatch.setattr(plugin_manager, "use_state", use_state)
    return directive, device


@pytest.mark.parametrize(
    "char", ("\n", "\r", "\x00", "\x1b", "\x7f", "\x85", "\u2028", "\u2029", "\u200b")
)
@pytest.mark.parametrize("as_list", (False, True))
def test_query_rejects_control_characters_with_permissive_directive(query_context, char, as_list):
    target = f"192.0.2.1{char}show version"
    if as_list:
        target = ["192.0.2.2", target]
    with pytest.raises(ValidationError, match="control characters"):
        query_module.Query(
            query_location="test-device", query_type="test-query", query_target=target
        )


@pytest.mark.parametrize("target", ("192.0.2.1", "2001:db8::1", "_13335$", "65000:100", ["a", "b"]))
def test_query_preserves_non_ip_custom_targets(query_context, target):
    query = query_module.Query(
        query_location="test-device", query_type="test-query", query_target=target
    )
    assert query.query_target == target


@pytest.mark.parametrize(
    "target, expected",
    (
        ("2001:DB8:0:0::1", "2001:db8::1"),
        ("2001:DB8::1/64", "2001:db8::/64"),
        ("192.0.2.1/24", "192.0.2.0/24"),
        ("fe80::1%br-lan", "fe80::1%br-lan"),
        (["2001:DB8:0:0::1"], ["2001:db8::1"]),
    ),
)
def test_command_uses_validated_canonical_ip(query_context, target, expected):
    directive, device = query_context
    directive.rules = [
        RuleWithIPv4(condition="0.0.0.0/0", command="ping {target}"),
        RuleWithIPv6(condition="::/0", command="ping {target}"),
    ]
    query = query_module.Query(
        query_location="test-device", query_type="test-query", query_target=target
    )
    assert query.query_target == expected
    command_target = expected[0] if isinstance(expected, list) else expected
    assert Construct(device, query).queries() == [f"ping {command_target}"]
