"""Tests for the favicon generator."""

# Standard Library
import json
from pathlib import Path
from collections import OrderedDict

# Third Party
from PIL import Image

# Project
from hyperglass.frontend.favicons import FORMATS, generate_favicons

SOURCE_SVG = Path(__file__).parent.parent.parent / "images" / "hyperglass-icon.svg"
UI_MANIFEST = Path(__file__).parent.parent.parent / "ui" / "favicon-formats.ts"

# Exact file set the `favicons` package produced; the replacement must match.
EXPECTED_FILES = {
    "favicon.ico",
    "favicon-16x16.png",
    "favicon-32x32.png",
    "favicon-64x64.png",
    "favicon-96x96.png",
    "favicon-180x180.png",
    "favicon-196x196.png",
    "apple-touch-icon-57x57.png",
    "apple-touch-icon-60x60.png",
    "apple-touch-icon-72x72.png",
    "apple-touch-icon-76x76.png",
    "apple-touch-icon-114x114.png",
    "apple-touch-icon-120x120.png",
    "apple-touch-icon-144x144.png",
    "apple-touch-icon-152x152.png",
    "apple-touch-icon-167x167.png",
    "apple-touch-icon-180x180.png",
    "mstile-70x70.png",
    "mstile-270x270.png",
    "mstile-310x310.png",
    "mstile-310x150.png",
}


def test_generate_from_svg_source(tmp_path):
    formats = generate_favicons(source=SOURCE_SVG, output_directory=tmp_path)

    assert {p.name for p in tmp_path.iterdir()} == EXPECTED_FILES
    assert formats == FORMATS

    with Image.open(tmp_path / "favicon.ico") as img:
        assert img.size == (64, 64)
    with Image.open(tmp_path / "favicon-16x16.png") as img:
        assert img.size == (16, 16)
    # Non-square target: source is fit centered on a transparent canvas.
    with Image.open(tmp_path / "mstile-310x150.png") as img:
        assert img.size == (310, 150)
        assert img.mode == "RGBA"


def test_generate_from_raster_source(tmp_path):
    source = tmp_path / "icon.png"
    Image.new("RGBA", (256, 256), (255, 0, 0, 255)).save(source)
    output = tmp_path / "out"

    generate_favicons(source=source, output_directory=output)

    assert {p.name for p in output.iterdir()} == EXPECTED_FILES
    with Image.open(output / "apple-touch-icon-180x180.png") as img:
        assert img.size == (180, 180)


def test_formats_serialize_to_checked_in_manifest():
    """FORMATS must reproduce hyperglass/ui/favicon-formats.ts byte-for-byte.

    This mirrors `write_favicon_formats` so the UI-facing contract cannot
    drift silently from the generator.
    """
    ordered = json.dumps([OrderedDict(sorted(fmt.items())) for fmt in FORMATS])
    expected = "import type {{ Favicon }} from '~/types';export default {} as Favicon[];".format(
        ordered
    )
    assert UI_MANIFEST.read_text() == expected
