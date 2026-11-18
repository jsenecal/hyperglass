"""Keep reviewed documentation aligned with the runtime contracts."""

import re
from pathlib import Path
from importlib.util import module_from_spec, spec_from_file_location

import pytest
import yaml

from hyperglass.defaults._strings import CREDIT
from hyperglass.util.support_bundle import build_support_bundle

ROOT = Path(__file__).resolve().parents[3]


def test_public_credit_and_original_author():
    readme = (ROOT / "README.md").read_text()
    assert "Matt Love" in readme
    assert "https://github.com/thatmattlove" in readme
    assert "fork of" not in CREDIT
    assert "{upstream_url}" in CREDIT


def test_my_ip_example_matches_its_description():
    text = (ROOT / "docs/content/configuration/config/web-ui.mdx").read_text()
    block = re.search(r"```yaml[^\n]*\n(.*?)```", text, re.S).group(1)
    assert yaml.safe_load(block)["web"]["my_ip"] == "server"


def test_support_bundle_documentation_matches_format(tmp_path):
    text = (ROOT / "docs/content/configuration/config/logging.mdx").read_text()
    bundle = build_support_bundle([tmp_path])
    assert f'format `{bundle["format"]}`' in text
    assert bundle["redaction"] in text
    assert "unclassified_text" in text
    assert "[REDACTED]" in text
    assert not (ROOT / "docs/ultraglass-history.md").exists()


def version_module():
    spec = spec_from_file_location("hyperglass_version_review", ROOT / "version.py")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_version_target_matches_current_source():
    module = version_module()
    assert len(module.UPGRADES) == 4
    for name, path, pattern in module.UPGRADES:
        assert sum(bool(pattern.match(line)) for line in path.read_text().splitlines()) == 1, name


def test_version_update_rejects_an_unmatched_target(tmp_path):
    module = version_module()
    path = tmp_path / "unmatched.txt"
    path.write_text("not a version\n")
    version = module.Version(name="test", new_version="0.0.0", line_pattern=r"^v(.+)$", file=path)
    with pytest.raises(ValueError, match="did not match"):
        version.upgrade()
    assert path.read_text() == "not a version\n"
