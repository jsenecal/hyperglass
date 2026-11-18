"""Validate `platform: http` devices."""

# Third Party
import pytest

# Project
from hyperglass.models.config.devices import Device

CONFIG = {
    "name": "http-device",
    "address": "192.0.2.10",
    "credential": {"username": "lg", "password": "secret"},
}


@pytest.mark.parametrize("explicit_null", [False, True])
def test_http_platform_defaults_http_block(explicit_null):
    kwargs = {"http": None} if explicit_null else {}
    device = Device(**CONFIG, platform="http", **kwargs)
    client = device.http.create_client(device=device)
    assert str(client.base_url).rstrip("/") == "https://192.0.2.10"


def test_http_driver_defaults_http_block():
    device = Device(
        **CONFIG,
        platform="cisco_ios",
        driver="hyperglass_http_client",
        attrs={"source4": "192.0.2.1", "source6": "2001:db8::1"},
    )
    assert device.http is not None
    assert device.http.create_client(device=device) is not None


def test_http_platform_with_http_block():
    device = Device(**CONFIG, platform="http", http={"path": "/query"})

    assert device.platform == "http"
    assert device.http.path == "/query"


def test_ssh_platform_has_no_http_block():
    device = Device(
        **CONFIG, platform="frr", attrs={"source4": "192.0.2.1", "source6": "2001:db8::1"}
    )

    assert device.http is None


@pytest.mark.parametrize(
    ("scheme", "port", "expected"),
    [
        ("https", 8080, "https://192.0.2.10:8080"),
        ("http", 8080, "http://192.0.2.10:8080"),
        ("https", 443, "https://192.0.2.10"),
        ("http", 80, "http://192.0.2.10"),
        ("http", 443, "http://192.0.2.10:443"),
        ("https", 80, "https://192.0.2.10:80"),
        ("https", 22, "https://192.0.2.10:22"),
    ],
)
def test_http_client_base_url_port(scheme, port, expected):
    device = Device(**CONFIG, platform="http", port=port, http={"scheme": scheme})
    client = device.http.create_client(device=device)

    assert str(client.base_url).rstrip("/") == expected


@pytest.mark.parametrize("scheme", ["http", "https"])
def test_http_client_base_url_unset_port(scheme):
    device = Device(**CONFIG, platform="http", http={"scheme": scheme})
    client = device.http.create_client(device=device)

    assert str(client.base_url).rstrip("/") == f"{scheme}://192.0.2.10"


@pytest.mark.parametrize(
    ("port", "expected"),
    [(None, "https://[2001:db8::10]"), (8443, "https://[2001:db8::10]:8443")],
)
def test_http_client_base_url_ipv6(port, expected):
    """An IPv6 device address is bracketed in the base URL (#188)."""
    extra = {} if port is None else {"port": port}
    config = {**CONFIG, "address": "2001:db8::10"}
    device = Device(**config, platform="http", http={"scheme": "https"}, **extra)
    client = device.http.create_client(device=device)

    assert str(client.base_url).rstrip("/") == expected
