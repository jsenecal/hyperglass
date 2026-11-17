"""Check favicon generation with the packaged UI dependencies."""

# Standard Library
from pathlib import Path

# Third Party
import pytest
from PIL import Image

# Project
from hyperglass.frontend import generate_favicons


@pytest.mark.parametrize("source_format", ("svg", "png"))
def test_generate_favicons(tmp_path: Path, source_format: str) -> None:
    """Generate readable icons with the dimensions required by the UI."""
    source = Path(__file__).parents[2] / "images" / "hyperglass-icon.svg"
    if source_format == "png":
        source = tmp_path / "source.png"
        with Image.new("RGBA", (100, 100), "blue") as image:
            image.save(source)
    output = tmp_path / "favicons"

    formats = generate_favicons(source, output)

    assert len(formats) == 21
    assert len(list(output.iterdir())) == 21
    for favicon in formats:
        width, height = favicon["dimensions"]
        name = f"{favicon['prefix']}-{width}x{height}.{favicon['image_format']}"
        with Image.open(output / name) as image:
            assert image.size == (width, height)
            assert image.format.lower() == favicon["image_format"]
