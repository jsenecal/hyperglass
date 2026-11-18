"""Keep runtime consumers compatible with the configuration shipped beside them."""

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from hyperglass.state import use_state
from hyperglass.constants import DNS_OVER_HTTPS
from hyperglass.models.api import Query
from hyperglass.exceptions.private import ConfigError
from hyperglass.exceptions.public import DeviceCommandError
from hyperglass.models.directive import Directive, Directives
from hyperglass.models.data.bgp_route import BGPRoute
from hyperglass.models.config.params import Params
from hyperglass.models.config.devices import Device, Devices
from hyperglass.execution.drivers._construct import Construct


def device_config(platform, **kwargs):
    return {
        "name": "test",
        "address": "192.0.2.1",
        "credential": {"username": "test", "password": "test"},
        "platform": platform,
        "attrs": {"source4": "192.0.2.1", "source6": "2001:db8::1"},
        **kwargs,
    }


@pytest.mark.parametrize("platform", ["frr", "juniper", "arista_eos"])
def test_original_platforms_keep_structured_output_default(platform):
    device = Device(**device_config(platform))
    assert device.structured_output is True
    assert any("table" in name for name in device.directive_ids)


@pytest.mark.parametrize("platform", ["cisco_ios", "huawei", "mikrotik_routeros"])
def test_platforms_without_table_directives_default_to_text(platform):
    assert Device(**device_config(platform)).structured_output is False
    with pytest.raises(ConfigError):
        Device(**device_config(platform, structured_output=True))


@pytest.mark.parametrize(
    ("kind", "target", "pattern"),
    [
        ("bgp_aspath", "_65000$", r"(^|[ ,]|\$)65000\$"),
        ("bgp_community", "65000:100", r"(^|[,;])65000:100([,;]|\$)"),
    ],
)
def test_mikrotik_templates_match_formatted_regex(kind, target, pattern):
    state = use_state()
    state.cache.set("devices", Devices(device_config("mikrotik_routeros")))
    query = Query(
        queryLocation="test", queryType=f"__hyperglass_mikrotik_{kind}__", queryTarget=target
    )
    commands = Construct(query.device, query).queries()
    assert len(commands) == 2
    assert all(f'~"{pattern}"' in command for command in commands)


def test_device_rejection_has_a_user_facing_message():
    error = DeviceCommandError(device=SimpleNamespace(name="test"), error="% Invalid input")
    assert "The device rejected the query command." in str(error)
    assert "device_command_error" not in str(error)


def test_named_communities_preserve_unmatched_values():
    params = Params(structured={"communities": {"mode": "name", "names": {"65000:100": "Transit"}}})
    use_state().cache.set("params", params)
    route = BGPRoute(
        prefix="192.0.2.0/24",
        active=True,
        age=0,
        weight=0,
        med=0,
        local_preference=100,
        as_path=[65000],
        communities=["65000:100", "65000:200"],
        next_hop="192.0.2.1",
        source_as=65000,
        source_rid="192.0.2.1",
        peer_rid="192.0.2.2",
        rpki_state=0,
    )
    assert route.communities == ["65000:100,Transit", "65000:200"]


@pytest.mark.parametrize("vrf", [100, "100", "blue"])
def test_custom_vrf_directive_normalizes_routing_context(vrf):
    state = use_state()
    custom = Directive(
        id="custom",
        name="Custom",
        field=None,
        rules=[
            {
                "condition": "*",
                "command": "show route {target}",
                "vrf_command": "show route vrf {vrf} {target}",
            }
        ],
    )
    state.cache.set("directives", state.directives + Directives(custom))
    device = Device(**device_config("cisco_ios", vrf=vrf, directives=["custom"]))
    assert device.vrf == str(vrf)
    assert device.directive_ids == ["custom"]
    state.cache.set("devices", Devices(device_config("cisco_ios", vrf=vrf, directives=["custom"])))
    query = Query(queryLocation="test", queryType="custom", queryTarget="192.0.2.2")
    assert Construct(device, query).queries() == [f"show route vrf {vrf} 192.0.2.2"]


@pytest.mark.parametrize("vrf", [True, "", "blue;id", "blue\n", "blue space"])
def test_vrf_rejects_invalid_routing_context(vrf):
    with pytest.raises(ValidationError, match="vrf must be"):
        Device(**device_config("cisco_ios", vrf=vrf))


def test_vrf_without_usable_directives_is_a_configuration_error():
    with pytest.raises(ConfigError, match="no VRF-capable directives"):
        Device(**device_config("cisco_ios", vrf=100))


def test_dns_choices_only_advertise_implemented_providers():
    assert all(not url.startswith("/") for url in DNS_OVER_HTTPS.values())
