"""Generate favicon assets from a single source image.

Replaces the third-party `favicons` package, which is unmaintained and
capped typer, Pillow and rich while dragging in the cairo toolchain via
svglib/reportlab. SVG sources are rasterized with resvg (prebuilt wheels,
no system dependencies); resizing and encoding are done with Pillow.
"""

# Standard Library
import typing as t
from io import BytesIO
from pathlib import Path

# Third Party
import resvg_py
from PIL import Image

FaviconFormat = t.Dict[str, t.Any]

# Formats served by the UI. The list (and its order) must stay in sync with
# `hyperglass/ui/favicon-formats.ts`, which `write_favicon_formats`
# regenerates at build time, and with the filename convention in
# `hyperglass/ui/elements/favicon.tsx`: `{prefix}-{w}x{h}.{image_format}`.
# The ICO entry is the exception — it is written as plain `favicon.ico`.
FORMATS: t.Tuple[FaviconFormat, ...] = (
    {"dimensions": (64, 64), "image_format": "ico", "prefix": "favicon", "rel": None},
    {"dimensions": (16, 16), "image_format": "png", "prefix": "favicon", "rel": "icon"},
    {"dimensions": (32, 32), "image_format": "png", "prefix": "favicon", "rel": "icon"},
    {"dimensions": (64, 64), "image_format": "png", "prefix": "favicon", "rel": "icon"},
    {"dimensions": (96, 96), "image_format": "png", "prefix": "favicon", "rel": "icon"},
    {"dimensions": (180, 180), "image_format": "png", "prefix": "favicon", "rel": "icon"},
    {
        "dimensions": (57, 57),
        "image_format": "png",
        "prefix": "apple-touch-icon",
        "rel": "apple-touch-icon",
    },
    {
        "dimensions": (60, 60),
        "image_format": "png",
        "prefix": "apple-touch-icon",
        "rel": "apple-touch-icon",
    },
    {
        "dimensions": (72, 72),
        "image_format": "png",
        "prefix": "apple-touch-icon",
        "rel": "apple-touch-icon",
    },
    {
        "dimensions": (76, 76),
        "image_format": "png",
        "prefix": "apple-touch-icon",
        "rel": "apple-touch-icon",
    },
    {
        "dimensions": (114, 114),
        "image_format": "png",
        "prefix": "apple-touch-icon",
        "rel": "apple-touch-icon",
    },
    {
        "dimensions": (120, 120),
        "image_format": "png",
        "prefix": "apple-touch-icon",
        "rel": "apple-touch-icon",
    },
    {
        "dimensions": (144, 144),
        "image_format": "png",
        "prefix": "apple-touch-icon",
        "rel": "apple-touch-icon",
    },
    {
        "dimensions": (152, 152),
        "image_format": "png",
        "prefix": "apple-touch-icon",
        "rel": "apple-touch-icon",
    },
    {
        "dimensions": (167, 167),
        "image_format": "png",
        "prefix": "apple-touch-icon",
        "rel": "apple-touch-icon",
    },
    {
        "dimensions": (180, 180),
        "image_format": "png",
        "prefix": "apple-touch-icon",
        "rel": "apple-touch-icon",
    },
    {"dimensions": (70, 70), "image_format": "png", "prefix": "mstile", "rel": None},
    {"dimensions": (270, 270), "image_format": "png", "prefix": "mstile", "rel": None},
    {"dimensions": (310, 310), "image_format": "png", "prefix": "mstile", "rel": None},
    {"dimensions": (310, 150), "image_format": "png", "prefix": "mstile", "rel": None},
    {"dimensions": (196, 196), "image_format": "png", "prefix": "favicon", "rel": "shortcut icon"},
)

# Base raster size for SVG sources; larger than the biggest target (310px)
# so every output is a downscale.
_BASE_SIZE = 512


def _load_source(source: Path) -> Image.Image:
    """Load the source image as RGBA, rasterizing SVG sources with resvg."""
    if source.suffix.lower() == ".svg":
        png_bytes = resvg_py.svg_to_bytes(svg_path=str(source), width=_BASE_SIZE, height=_BASE_SIZE)
        return Image.open(BytesIO(bytes(png_bytes))).convert("RGBA")
    return Image.open(source).convert("RGBA")


def _fit(base: Image.Image, width: int, height: int) -> Image.Image:
    """Scale `base` to fit within width x height, centered on a transparent canvas."""
    scaled = base.copy()
    scaled.thumbnail((width, height), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    canvas.paste(scaled, ((width - scaled.width) // 2, (height - scaled.height) // 2))
    return canvas


def generate_favicons(source: Path, output_directory: Path) -> t.Tuple[FaviconFormat, ...]:
    """Generate every favicon format from `source` into `output_directory`.

    Returns the format definitions for `write_favicon_formats`.
    """
    output_directory.mkdir(parents=True, exist_ok=True)
    base = _load_source(Path(source))

    for fmt in FORMATS:
        width, height = fmt["dimensions"]
        image = _fit(base, width, height)
        if fmt["image_format"] == "ico":
            image.save(output_directory / "favicon.ico", format="ICO", sizes=[(width, height)])
        else:
            image.save(output_directory / f"{fmt['prefix']}-{width}x{height}.png", format="PNG")

    return FORMATS
