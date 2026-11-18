"""Validate lab topology isolation without starting containers."""

# Standard Library
from pathlib import Path

# Third Party
import pytest
import yaml

LAB = Path(__file__).parents[3] / "lab"


@pytest.mark.parametrize("path", sorted(LAB.glob("*.clab.yml")), ids=lambda path: path.name)
def test_topologies_disable_privileged_containers(path):
    """Require explicit defaults and reject kind or node privilege overrides."""
    topology = yaml.safe_load(path.read_text())["topology"]
    assert topology["defaults"]["privileged"] is False
    for settings in topology.get("kinds", {}).values():
        assert settings.get("privileged", False) is False
    for node in topology["nodes"].values():
        assert node.get("privileged", False) is False
