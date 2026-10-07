"""Command construction must not let a query target escape into the shell.

FRR, BIRD and OpenBGPD are driven through Netmiko's ``linux_ssh`` device type,
so on these platforms the constructed command string is parsed by a POSIX shell.
TNSR's builtin BGP directives (``dataplane shell sudo vtysh -c ...``) are
covered by the template tests only: Netmiko has no ``tnsr`` device type, so a
TNSR device cannot currently be configured.
"""

# Standard Library
import shlex
import shutil
import typing as t
import subprocess

# Third Party
import pytest

# Project
from hyperglass.models.api import Query

# Local
from .._construct import Construct, shell_format

# Targets that tried to break out of the builtin FRR/BIRD/OpenBGPD/TNSR templates.
# If any of them reaches the shell, `$((6*7))` is evaluated and `42INJ` appears.
PAYLOADS = (
    '_65000"; echo $((6*7))INJ; echo "',
    "_65000'; echo $((6*7))INJ; echo '",
    "_65000; echo $((6*7))INJ",
    "_65000 $(echo $((6*7))INJ)",
    "_65000 `echo $((6*7))INJ`",
    "_65000 | echo $((6*7))INJ",
    "_65000 && echo $((6*7))INJ",
    "_65000 > /dev/null; echo $((6*7))INJ",
    "65000:100\\",
    "!!",
)

# Every builtin shell-platform template shape: double-quoted, unquoted, and
# multi-word with other fields. The first word is swapped for `printf` when the
# command is executed so the test needs no routing daemon.
TEMPLATES = (
    'vtysh -c "show bgp ipv4 unicast regexp {target}"',
    "bgpctl show rib inet as {target}",
    'birdc "show route all where bgp_path ~ {target}"',
    'dataplane shell sudo vtysh -c "show bgp ipv6 unicast community {target}"',
    "ping -4 -c 5 -I {source4} {target}",
)

BASH = shutil.which("bash")


@pytest.mark.parametrize("template", TEMPLATES)
@pytest.mark.parametrize("target", PAYLOADS)
def test_shell_format_keeps_target_inside_its_word(template: str, target: str):
    """The shell sees the same words as the template, with the target filled in literally."""
    command = shell_format(template, target=target, source4="192.0.2.1")
    expected = [w.format(target=target, source4="192.0.2.1") for w in shlex.split(template)]
    assert shlex.split(command) == expected


@pytest.mark.skipif(BASH is None, reason="bash is not installed")
@pytest.mark.parametrize("template", TEMPLATES)
@pytest.mark.parametrize("target", PAYLOADS)
def test_shell_format_does_not_execute_target(template: str, target: str):
    """Running the constructed command in bash never executes the target."""
    template = "printf '%s\\n' " + template.split(" ", 1)[1]
    command = shell_format(template, target=target, source4="192.0.2.1")

    result = subprocess.run(  # noqa: S603
        [BASH, "-c", command], capture_output=True, text=True, check=True
    )

    assert "42INJ" not in result.stdout
    assert target in result.stdout


@pytest.mark.parametrize(
    "target",
    ("192.0.2.0/24", "2001:db8::/32", "65000:100", "65000:65001:65002", "_65000_", "target:1:2"),
)
def test_shell_format_leaves_plain_targets_unquoted(target: str):
    """Ordinary targets produce exactly the command the template always produced."""
    template = "ping -4 -c 5 -I {source4} {target}"
    command = shell_format(template, target=target, source4="192.0.2.1")
    assert command == template.format(target=target, source4="192.0.2.1")


@pytest.mark.skipif(BASH is None, reason="bash is not installed")
def test_shell_format_keeps_template_control_operators():
    """Pipes and command lists written in a (trusted) template still work."""
    command = shell_format("echo {target} | tr a-z A-Z && echo done", target="as_path")

    result = subprocess.run(  # noqa: S603
        [BASH, "-c", command], capture_output=True, text=True, check=True
    )

    assert result.stdout.split() == ["AS_PATH", "done"]


@pytest.mark.parametrize(
    "template",
    (
        "traceroute -6 {target} 2>&1",
        'grep "|" {target}',
        "echo it\\'s {target}",
        "printf --opt='a b' {target}",
        "awk '{{print $1}}' {target}",
    ),
)
def test_shell_format_leaves_words_without_fields_as_written(template: str):
    """Template words without a field are sent exactly as written (escaped braces aside)."""
    command = shell_format(template, target="2001:db8::1")
    assert command == template.format(target="2001:db8::1")


@pytest.mark.parametrize(
    "template",
    ("printf --opt={target}", "printf --opt='{target}'", 'printf "x {target}"y'),
)
def test_shell_format_quotes_field_inside_partly_quoted_word(template: str):
    """A field within a word that is only partly quoted still cannot escape that word."""
    target = PAYLOADS[0]
    command = shell_format(template, target=target)
    assert shlex.split(command) == [w.format(target=target) for w in shlex.split(template)]


def test_shell_format_target_cannot_add_control_operator():
    """A target made only of operator characters stays a literal argument."""
    command = shell_format("echo {target}", target="|")
    assert shlex.split(command) == ["echo", "|"]


@pytest.fixture
def directives() -> t.Sequence[t.Dict[str, t.Any]]:
    """Provide an unrestricted pattern directive, like the builtin AS path/community ones."""
    return [
        {
            "aspath": {
                "name": "BGP AS Path",
                "rules": [
                    {
                        "condition": "*",
                        "action": "permit",
                        "command": 'vtysh -c "show bgp ipv4 unicast regexp {target}"',
                    }
                ],
                "field": {"description": "AS Path Regular Expression"},
            }
        }
    ]


@pytest.fixture
def devices() -> t.Sequence[t.Dict[str, t.Any]]:
    """One device per configurable shell-backed platform, plus a non-shell NOS."""
    base = {
        "address": "127.0.0.1",
        "credential": {"username": "", "password": ""},
        "attrs": {},
        "directives": ["aspath"],
    }
    return [
        {**base, "name": platform, "platform": platform}
        for platform in ("frr", "bird", "openbgpd", "arista_eos")
    ]


@pytest.mark.parametrize("platform", ("frr", "bird", "openbgpd"))
def test_construct_quotes_target_on_shell_platforms(state, platform: str):
    """The constructor shell-quotes the target for shell-backed platforms."""
    target = PAYLOADS[0]
    query = Query(queryLocation=platform, queryTarget=target, queryType="aspath")
    constructor = Construct(device=state.devices[platform], query=query)

    (command,) = constructor.queries()

    assert shlex.split(command) == ["vtysh", "-c", f"show bgp ipv4 unicast regexp {target}"]


def test_construct_leaves_non_shell_platforms_unchanged(state):
    """Platforms whose CLI is not a POSIX shell keep plain template formatting."""
    target = "_65000$"
    query = Query(queryLocation="arista_eos", queryTarget=target, queryType="aspath")
    constructor = Construct(device=state.devices["arista_eos"], query=query)

    assert constructor.queries() == [f'vtysh -c "show bgp ipv4 unicast regexp {target}"']
