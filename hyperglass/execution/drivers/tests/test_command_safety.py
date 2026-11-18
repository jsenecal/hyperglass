"""Validate built-in targets again before rendering shell commands."""

# Standard Library
import shlex
from types import SimpleNamespace

# Third Party
import pytest

# Project
from hyperglass.models.directive import BuiltinDirective, RuleWithPattern
from hyperglass.exceptions.private import InputValidationError
from hyperglass.exceptions.public import InputInvalid
from hyperglass.execution.drivers._construct import Construct


def query_for(platform, target, validated=None):
    """Build a query whose only rule otherwise permits arbitrary input."""
    directive = BuiltinDirective(
        id=f"__hyperglass_{platform}_bgp_aspath__",
        name="BGP AS Path",
        field=None,
        platforms=[platform],
        rules=[RuleWithPattern(condition="*", command='vtysh -c "show bgp regexp {target}"')],
    )
    device = SimpleNamespace(platform=platform, name="test", attrs={})
    query = SimpleNamespace(
        device=device,
        directive=directive,
        query_type=directive.id,
        query_target=target,
        _validated_target=validated,
    )
    return device, query


@pytest.mark.parametrize("platform", ("bird", "frr", "openbgpd", "vyos", "tnsr", "cisco_ios"))
@pytest.mark.parametrize(
    "target", ('13335"; id; #', "$(id)", "`id`", "13335\nid", "13335\\", "13335\x00")
)
def test_execution_boundary_rejects_unvalidated_bgp_targets(platform, target):
    device, query = query_for(platform, target)
    with pytest.raises(InputValidationError):
        Construct(device, query)


def test_execution_boundary_rechecks_plugin_output():
    device, query = query_for("frr", '13335"; id; #', validated="13335")
    with pytest.raises(InputValidationError):
        Construct(device, query)


@pytest.mark.parametrize("platform", ("bird", "frr", "openbgpd", "vyos", "tnsr"))
@pytest.mark.parametrize("target", ("_13335$", "^(13335|65001)$", "_13335(_.+_)65001$"))
def test_regular_expression_is_one_shell_argument(platform, target):
    device, query = query_for(platform, target)
    if platform in ("bird", "openbgpd") and target != "_13335$":
        with pytest.raises(InputInvalid):
            Construct(device, query)
        return
    command = Construct(device, query).queries()[0]
    rendered = {"bird": "[= * 13335 =]", "openbgpd": "13335"}.get(platform, target)
    assert shlex.split(command) == ["vtysh", "-c", f"show bgp regexp {rendered}"]
