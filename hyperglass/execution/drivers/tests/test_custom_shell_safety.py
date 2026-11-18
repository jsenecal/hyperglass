"""Custom directive targets remain data when a real POSIX shell parses commands."""

# Standard Library
import subprocess
from types import SimpleNamespace

# Third Party
import pytest

# Project
from hyperglass.models.directive import Directive
from hyperglass.execution.drivers._construct import Construct
from hyperglass.exceptions.public import InputInvalid
from hyperglass.exceptions.private import ConfigError

PLATFORMS = (
    "bird", "frr", "openbgpd", "sonic", "arrcus_arcos", "cumulus_linux", "vyos", "vyos_1_3", "tnsr",
    "linux", "linux_ssh", "cumulus_linux_ssh", "vyos_ssh",
)
TARGETS = (
    "192.0.2.1",
    "^65000_(65001|65002)$",
    "$(printf INJECTED)",
    "`printf INJECTED`",
    'x"; printf INJECTED; #',
    "x'; printf INJECTED; #",
    "x | printf INJECTED",
    "x && printf INJECTED",
    "$HOME ${PATH}",
    "* ? [a-z] ~",
    "a\\ b\\",
    "{target}",
)


def construct(platform, target, command, *, condition="*", **options):
    directive = Directive(
        id="custom_lookup",
        name="Custom lookup",
        field=None,
        rules=[{"condition": condition, "command": command}],
        **options,
    )
    directive.validate_target(target)
    device = SimpleNamespace(platform=platform, name="test", attrs={})
    query = SimpleNamespace(
        device=device, directive=directive, query_type=directive.id, query_target=target
    )
    return Construct(device, query)


def shell_output(command):
    # Fixed test commands capture arguments without contacting a router.
    wrapper = 'capture() { printf "%s\\0" "$@"; }; ' + command
    return subprocess.run(  # noqa: S603 - intentionally exercise shell parsing of test payloads
        ["/bin/sh", "-c", wrapper], check=True, capture_output=True, timeout=5
    ).stdout.split(b"\0")[:-1]


@pytest.mark.parametrize("platform", PLATFORMS)
@pytest.mark.parametrize("target", TARGETS)
@pytest.mark.parametrize("template", ("{target}", "'{target}'", '"{target}"', '"route {target}"'))
def test_custom_target_is_one_literal_argument(platform, target, template):
    command = construct(platform, target, "capture " + template).queries()[0]
    expected = "route " + target if template.startswith('"route ') else target
    assert shell_output(command) == [expected.encode()]


def test_trusted_pipeline_operators_and_quoted_operators():
    command = construct(
        "arrcus_arcos", "$(printf INJECTED)", 'capture "show {target}" "|" | cat'
    ).queries()[0]
    assert shell_output(command) == [b"show $(printf INJECTED)", b"|"]


def test_variable_fragments_and_device_attributes_are_data():
    value = "vpn $(printf INJECTED) ' 1"
    instance = construct(
        "tnsr",
        "192.0.2.1",
        'capture "show {target}{instance}" {source}',
        variables={"instance": {"command": " instance ", "items": [{"value": value}]}},
    )
    instance.query.query_variables = {"instance": value}
    instance.device.attrs = {"source": "$(printf INJECTED)"}
    assert shell_output(instance.queries()[0]) == [
        f"show 192.0.2.1 instance {value}".encode(), b"$(printf INJECTED)"
    ]


def test_optional_variable_omission():
    instance = construct(
        "frr", "192.0.2.1", "capture {target}{instance}",
        variables={"instance": {"command": " instance ", "items": [{"value": "vpn 1"}]}},
    )
    assert shell_output(instance.queries()[0]) == [b"192.0.2.1"]


def test_null_condition_still_quotes_the_target():
    command = construct("frr", "$(printf INJECTED)", "capture {target}", condition=None)
    assert shell_output(command.queries()[0]) == [b"$(printf INJECTED)"]


def test_fallback_and_vrf_commands_use_the_same_boundary():
    instance = construct("frr", "$(printf INJECTED)", "capture {target}")
    rule = instance.directive.rules[0]
    rule.fallback_commands = ["capture 'fallback {target}'"]
    assert shell_output(instance.queries()[0]) == [b"$(printf INJECTED)"]
    assert shell_output(instance.fallbacks[0]) == [b"fallback $(printf INJECTED)"]
    instance.device.vrf = "blue"
    rule.vrf_commands = ['capture "{vrf} {target}"']
    assert shell_output(instance.queries()[0]) == [b"blue $(printf INJECTED)"]


@pytest.mark.parametrize(
    "template", ('capture "{target}', "capture '{target}", "capture {target}\\")
)
def test_malformed_template_fails_closed(template):
    with pytest.raises(ConfigError):
        construct("frr", "192.0.2.1", template).queries()


@pytest.mark.parametrize("delimiter", ("EOF", "'EOF'", '"EOF"'))
def test_here_documents_fail_closed(delimiter):
    with pytest.raises(ConfigError):
        construct("frr", "$(printf INJECTED)", f"cat <<{delimiter}\n{{target}}\nEOF").queries()


@pytest.mark.parametrize("target", ("x\ny", "x\ry", "x\0y"))
def test_transformed_control_characters_fail_closed(target):
    instance = construct("frr", "192.0.2.1", "capture {target}")
    instance.target = target
    with pytest.raises(InputInvalid):
        instance.queries()


def test_numeric_target_does_not_become_a_file_descriptor():
    command = construct("frr", "2", "capture {target}>/dev/null").queries()[0]
    assert shell_output(command) == []


def test_non_shell_directive_preserves_router_syntax():
    assert construct("juniper", "^65000_", 'show route aspath-regex "{target}"').queries() == [
        'show route aspath-regex "^65000_"'
    ]
