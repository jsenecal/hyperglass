"""Tests for the `hyperglass healthcheck` command."""

# Standard Library
import socket
import typing as t
import threading
from ipaddress import ip_address
from http.server import HTTPServer, BaseHTTPRequestHandler

# Third Party
import pytest
from typer.testing import CliRunner

# Project
from hyperglass.cli.main import cli
from hyperglass.settings import Settings

runner = CliRunner()


class HTTPServerV6(HTTPServer):
    """HTTP server listening on IPv6."""

    address_family = socket.AF_INET6


def serve(status: int, host: str = "127.0.0.1") -> t.Tuple[HTTPServer, t.List[str]]:
    """Serve `status` for every request on a random loopback port, recording paths."""
    paths = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 (BaseHTTPRequestHandler interface)
            paths.append(self.path)
            self.send_response(status)
            self.end_headers()
            self.wfile.write(b'{"status":"error"}')

        def log_message(self, *args):
            pass

    server_class = HTTPServerV6 if ip_address(host).version == 6 else HTTPServer
    server = server_class((host, 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, paths


@pytest.fixture
def listen(monkeypatch):
    """Point Settings at a test server answering with the given status."""
    servers = []

    def _listen(status: int, host: str = "127.0.0.1", bind: str = "127.0.0.1") -> t.List[str]:
        server, paths = serve(status, bind)
        servers.append(server)
        monkeypatch.setattr(Settings, "host", ip_address(host))
        monkeypatch.setattr(Settings, "port", server.server_address[1])
        return paths

    yield _listen
    for server in servers:
        server.shutdown()


def test_healthy(listen):
    paths = listen(200)
    result = runner.invoke(cli, ["healthcheck"])
    assert result.exit_code == 0
    assert paths == ["/api/health"]


def test_unhealthy(listen):
    listen(503)
    result = runner.invoke(cli, ["healthcheck"])
    assert result.exit_code == 1


def test_wildcard_listen_address_uses_loopback(listen):
    paths = listen(200, host="0.0.0.0")  # noqa: S104 (listen address under test)
    result = runner.invoke(cli, ["healthcheck"])
    assert result.exit_code == 0
    assert paths == ["/api/health"]


@pytest.mark.parametrize("host", ["::1", "::"])
def test_ipv6_listen_address(listen, host):
    paths = listen(200, host=host, bind="::1")
    result = runner.invoke(cli, ["healthcheck"])
    assert result.exit_code == 0
    assert paths == ["/api/health"]


def test_unreachable(monkeypatch):
    server, _ = serve(200)
    port = server.server_address[1]
    server.shutdown()
    server.server_close()
    monkeypatch.setattr(Settings, "host", ip_address("127.0.0.1"))
    monkeypatch.setattr(Settings, "port", port)
    result = runner.invoke(cli, ["healthcheck", "--timeout", "1"])
    assert result.exit_code == 1
