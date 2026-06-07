"""CLI smoke tests.

The unit suite otherwise never imports `hyperglass.cli`, so CLI breakage from
dependency updates (e.g. typer API changes) only surfaced when a fresh
install actually ran the entrypoint. These tests import the app and exercise
argument parsing for every command — they intentionally avoid running
commands that require Redis, config files, or Node.
"""

# Third Party
import pytest
from typer.testing import CliRunner

# Project
from hyperglass.cli.main import cli
from hyperglass.constants import __version__

runner = CliRunner()

ALL_COMMANDS = (
    "start",
    "build-ui",
    "system-info",
    "clear-cache",
    "devices",
    "directives",
    "plugins",
    "params",
    "setup",
    "settings",
)


def test_cli_help():
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    for command in ALL_COMMANDS:
        assert command in result.output


def test_cli_version():
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


@pytest.mark.parametrize("command", ALL_COMMANDS)
def test_command_help(command: str):
    result = runner.invoke(cli, [command, "--help"])
    assert result.exit_code == 0


def test_no_args_shows_help():
    result = runner.invoke(cli, [])
    assert "Usage" in result.output
