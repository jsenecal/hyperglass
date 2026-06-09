"""SSH transport integration test (Tier 1).

Exercises the real `NetmikoConnection` driver — and therefore the live
netmiko/paramiko transport stack — against an actual OpenSSH server, instead
of mocking it. This is the layer that dependency bumps (netmiko, paramiko)
most affect (auth, prompt detection, channel read/write, timeouts), which the
rest of the suite never touches because it relies on ``fake_output``.

`frr` maps to Netmiko's ``linux_ssh`` device type (see
``Device.get_device_type``), so a plain OpenSSH server is a representative
target for the linux-based platforms hyperglass actually supports (FRR / BIRD /
OpenBGPD), not a synthetic stand-in.

The test is skipped unless an SSH server is advertised via environment
variables. CI starts an ``openssh-server`` service container and sets them; to
run locally, point these at any reachable SSH server with a POSIX shell::

    docker run -d --name hg-ssh -e PASSWORD_ACCESS=true \
        -e USER_NAME=hyperglass -e USER_PASSWORD=hyperglass -e SUDO_ACCESS=false \
        -p 2222:2222 lscr.io/linuxserver/openssh-server
    HYPERGLASS_TEST_SSH_HOST=127.0.0.1 HYPERGLASS_TEST_SSH_PORT=2222 \
        pytest hyperglass/execution/drivers/tests/test_ssh_integration.py
"""

# Standard Library
import os
import typing as t

# Third Party
import pytest

# Project
from hyperglass.models.api import Query
from hyperglass.exceptions.public import AuthError
from hyperglass.execution.drivers import NetmikoConnection

SSH_HOST = os.getenv("HYPERGLASS_TEST_SSH_HOST")
SSH_PORT = os.getenv("HYPERGLASS_TEST_SSH_PORT")
SSH_USER = os.getenv("HYPERGLASS_TEST_SSH_USERNAME", "hyperglass")
SSH_PASS = os.getenv("HYPERGLASS_TEST_SSH_PASSWORD", "hyperglass")

# Skip the whole module (before any fixture runs) unless a server is advertised.
pytestmark = pytest.mark.skipif(
    not (SSH_HOST and SSH_PORT),
    reason="No SSH server advertised; set HYPERGLASS_TEST_SSH_HOST/_PORT to run.",
)

# A unique marker echoed back over the channel proves end-to-end command flow.
MARKER = "HG_SSH_OK"


@pytest.fixture
def directives() -> t.Sequence[t.Dict[str, t.Any]]:
    """Provide a linux directive whose command is a plain shell echo.

    `echo {target}` runs on any POSIX shell, so the round-trip validates the
    transport without needing a real routing daemon.
    """
    return [
        {
            "echo_ssh": {
                "name": "Echo SSH",
                "rules": [
                    {
                        "condition": "0.0.0.0/0",
                        "action": "permit",
                        "command": f"echo {MARKER}_{{target}}",
                    },
                    {
                        "condition": "::/0",
                        "action": "permit",
                        "command": f"echo {MARKER}_{{target}}",
                    },
                ],
                "field": {"description": "Target"},
            }
        }
    ]


@pytest.fixture
def devices() -> t.Sequence[t.Dict[str, t.Any]]:
    """One reachable `frr`/linux_ssh device and one with bad credentials."""
    base = {
        "address": SSH_HOST,
        "port": int(SSH_PORT),
        "platform": "frr",
        "attrs": {},
        "directives": ["echo_ssh"],
    }
    return [
        {**base, "name": "ssh_ok", "credential": {"username": SSH_USER, "password": SSH_PASS}},
        {
            **base,
            "name": "ssh_badauth",
            "credential": {"username": SSH_USER, "password": "definitely-wrong-password"},
        },
    ]


@pytest.mark.asyncio
async def test_netmiko_collects_over_real_ssh(state):
    """A query runs end-to-end over a real SSH channel and returns its output."""
    query = Query(queryLocation="ssh_ok", queryTarget="192.0.2.1", queryType="echo_ssh")
    conn = NetmikoConnection(device=state.devices["ssh_ok"], query_data=query)

    responses = await conn.collect()

    assert responses, "expected at least one command response"
    assert any(f"{MARKER}_192.0.2.1" in r for r in responses), responses


@pytest.mark.asyncio
async def test_netmiko_bad_credentials_raise_autherror(state):
    """A bad password surfaces as hyperglass AuthError (paramiko auth path)."""
    query = Query(queryLocation="ssh_badauth", queryTarget="192.0.2.1", queryType="echo_ssh")
    conn = NetmikoConnection(device=state.devices["ssh_badauth"], query_data=query)

    with pytest.raises(AuthError):
        await conn.collect()
