"""Input validation for BGP AS-path and community directives.

The builtin AS-path and community directives previously used ``condition: "*"``,
which compiled to a start-anchored ``.+`` and therefore accepted any string,
including one that breaks out of the device-command argument. A target such as
``.*" | save /var/tmp/x`` closes a quoted ``aspath-regex "<...>"`` argument, and
on the (partly unquoted) community templates a bare ``|`` adds a CLI pipe
modifier without needing a quote at all. These tests pin the strict patterns.
"""

# Standard Library
import typing as t

# Third Party
import pytest

# Project
from hyperglass.constants import PATTERN_BGP_COMMUNITY
from hyperglass.exceptions.private import InputValidationError
from hyperglass.defaults.directives import init_builtin_directives

# Local
from ..directive import Directive, RuleWithPattern

BUILTINS = init_builtin_directives()
ASPATH = [d for d in BUILTINS if "aspath" in d.id]
COMMUNITY = [d for d in BUILTINS if "community" in d.id]

VALID_AS_PATHS = ("_65000_", "^65000$", ".* 65000 .*", "(65000|65001)", "65000{1,3}", "207777")
VALID_COMMUNITIES = (
    "65000",
    "4259840001",
    "65000:1",
    "65000:4294967295",
    "65000:65001:65002",
    "192.0.2.1:100",
    "target:65000:1",
)

# Each of these breaks out of (or past) the device command on at least one
# builtin template: a quote closes a quoted argument, and a bare ``|``/``;``
# reaches the CLI on the unquoted community templates.
INJECTIONS = (
    '.*" | save /var/tmp/x',
    '207176" | save "/var/tmp/tstping.txt',
    "65000:1 | save /var/tmp/x",
    "65000:1 | match foo",
    "65000; id",
    "65000 && id",
    "65000`id`",
    "65000$(id)",
    "65000\\",
    '65000"',
    "65000'",
)


def _ids(directives: t.List[Directive]) -> t.List[str]:
    return [d.id for d in directives]


def test_builtins_have_aspath_and_community():
    assert ASPATH, "no AS-path directives discovered"
    assert COMMUNITY, "no community directives discovered"


@pytest.mark.parametrize("directive", ASPATH, ids=_ids(ASPATH))
@pytest.mark.parametrize("target", VALID_AS_PATHS)
def test_aspath_accepts_valid(directive: Directive, target: str):
    assert directive.validate_target(target) is True


@pytest.mark.parametrize("directive", COMMUNITY, ids=_ids(COMMUNITY))
@pytest.mark.parametrize("target", VALID_COMMUNITIES)
def test_community_accepts_valid(directive: Directive, target: str):
    assert directive.validate_target(target) is True


@pytest.mark.parametrize("directive", ASPATH + COMMUNITY, ids=_ids(ASPATH + COMMUNITY))
@pytest.mark.parametrize("target", INJECTIONS)
def test_rejects_injection(directive: Directive, target: str):
    with pytest.raises(InputValidationError):
        directive.validate_target(target)


@pytest.mark.parametrize(
    "target", ("65000:1 | save /var/tmp/x", "65000:1; id", '65000:1" detail', "no-export")
)
def test_community_rejects_non_community(target: str):
    """The community pattern has no ``|``, space or quote, so a pipe can't be smuggled in."""
    for directive in COMMUNITY:
        with pytest.raises(InputValidationError):
            directive.validate_target(target)


def test_wildcard_rule_rejects_quotes_and_requires_full_match():
    """A ``condition: "*"`` rule rejects quote/backtick breakout characters."""
    rule = RuleWithPattern(condition="*", command="show {target}")
    assert rule.validate_target("(65000|65001)", multiple=False) is True
    assert rule.validate_target('65000" | save x', multiple=False) is False
    assert rule.validate_target("65000`id`", multiple=False) is False


def test_custom_pattern_is_anchored():
    """A custom regex condition must match the whole target, not just its start."""
    rule = RuleWithPattern(condition=r"\d+", command="show {target}")
    assert rule.validate_target("65000", multiple=False) is True
    assert rule.validate_target('65000" | save x', multiple=False) is False


@pytest.mark.parametrize(
    "condition,target",
    (
        ("65000", "65000:666"),
        (r"10\.", "10.0.0.1"),
        ("_65000_", "_65000_ _1_"),
        ("*", '65000" | save x'),
    ),
)
def test_deny_rule_keeps_prefix_match(condition: str, target: str):
    """A deny condition still blocks every target it matches the start of.

    Only permit rules require a full match; tightening deny rules the same way would let a
    target that a deny rule used to block fall through to a later permit rule.
    """
    rule = RuleWithPattern(condition=condition, action="deny", command="show {target}")
    with pytest.raises(InputValidationError):
        rule.validate_target(target, multiple=False)


def test_deny_rule_blocks_before_later_permit():
    """A prefix-matched deny rule wins over a broader permit rule that follows it."""
    directive = Directive(
        id="test-deny-prefix",
        name="Test",
        rules=[
            {"condition": "65000", "action": "deny", "command": "show {target}"},
            {"condition": PATTERN_BGP_COMMUNITY, "action": "permit", "command": "show {target}"},
        ],
        field=None,
    )
    assert directive.validate_target("65001:1") is True
    with pytest.raises(InputValidationError):
        directive.validate_target("65000:666")
