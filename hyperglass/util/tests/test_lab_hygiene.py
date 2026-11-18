"""Static checks for portable lab names and anonymized traceroute fixtures."""

import re
from pathlib import Path
from ipaddress import ip_address


ROOT = Path(__file__).resolve().parents[3]


def test_lab_uses_hyperglass_names():
    for path in (ROOT / "lab").rglob("*"):
        if path.is_file() and "__pycache__" not in path.parts:
            assert "ultraglass" not in str(path.relative_to(ROOT)).lower()
            assert "ultraglass" not in path.read_text().lower()


def test_traceroute_upstream_ipv4_addresses_are_not_public():
    fixtures = ROOT / "hyperglass/plugins/tests/fixtures"
    for path in fixtures.rglob("*"):
        if path.is_file() and (path.name.startswith("trace") or "traceroute" in path.name):
            addresses = re.findall(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])", path.read_text())
            for address in addresses:
                assert address == "1.1.1.1" or not ip_address(address).is_global, path
