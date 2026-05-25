"""Badge renderer: composes participant badges from canvas configuration.

This module owns the Pillow rendering pipeline. It reads canvas_data
(stored as JSONB on OrganiserTemplate) and produces a PNG byte string.

Field rendering (text, logo, photo compositing) lands in commits 3 and 4.
This commit covers canvas setup, background rendering, and the render
entry point.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import app.core.pillow  # noqa: F401
from app.core.exceptions import BadgeRenderError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LayoutSpec:
    """Per-layout positioning and styling configuration.

    Ratios are expressed relative to the canvas width or height so layouts
    scale correctly when output dimensions change.
    """

    photo_diameter_ratio: float
    photo_y_ratio: float
    text_y_start_ratio: float
    text_y_start_no_photo: float
    text_color: str
    padding: int


LAYOUT_SPECS: dict[str, LayoutSpec] = {}

DEFAULT_SPEC = LayoutSpec(
    photo_diameter_ratio=0.55,
    photo_y_ratio=0.10,
    text_y_start_ratio=0.62,
    text_y_start_no_photo=0.38,
    text_color="#FFFFFF",
    padding=48,
)

_FONTS_DIR = Path(__file__).resolve().parents[2] / "fonts" / "DM_Sans"
_DEFAULT_FONT_REGULAR = _FONTS_DIR / "DMSans-Regular.ttf"
_DEFAULT_FONT_BOLD = _FONTS_DIR / "DMSans-Bold.ttf"

_MIN_DIMENSION = 500
_MAX_DIMENSION = 4000

_DEFAULT_BACKGROUND = {"type": "solid", "color": "#1A1A2E"}
_DEFAULT_TYPOGRAPHY = {"font_family": "DM Sans", "size_px": 42, "weight": "bold"}
_DEFAULT_WIDTH = 1080
_DEFAULT_HEIGHT = 1350


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    """Convert a hex colour string to an (R, G, B) tuple.

    Accepts ``#RRGGBB`` or ``RRGGBB``. Raises BadgeRenderError on malformed input.
    """
    hex_str = value.strip().lstrip("#")
    if len(hex_str) != 6:
        raise BadgeRenderError(f"Invalid hex colour: {value!r}")
    try:
        return (
            int(hex_str[0:2], 16),
            int(hex_str[2:4], 16),
            int(hex_str[4:6], 16),
        )
    except ValueError as exc:
        raise BadgeRenderError(f"Invalid hex colour: {value!r}") from exc


def _lerp_color(
    start: tuple[int, int, int],
    end: tuple[int, int, int],
    t: float,
) -> tuple[int, int, int]:
    """Linearly interpolate between two RGB colours.

    ``t`` is clamped to the [0, 1] range so callers cannot produce values
    outside the channel range.
    """
    t = max(0.0, min(1.0, t))
    return (
        int(start[0] + (end[0] - start[0]) * t),
        int(start[1] + (end[1] - start[1]) * t),
        int(start[2] + (end[2] - start[2]) * t),
    )


def _load_font(
    font_family: str, size_px: int, *, bold: bool = False
) -> ImageFont.FreeTypeFont:
    """Load a TrueType font at the given size.

    ``font_family`` is currently advisory; we fall back to DM Sans regardless
    until additional fonts are bundled. The fallback is logged so unknown
    families are visible in production.
    """
    if font_family and font_family.lower() != "dm sans":
        logger.info(
            "Unknown font_family %r, falling back to DM Sans",
            font_family,
        )
    path = _DEFAULT_FONT_BOLD if bold else _DEFAULT_FONT_REGULAR
    try:
        return ImageFont.truetype(str(path), size=size_px)
    except OSError as exc:
        raise BadgeRenderError(f"Could not load font at {path}: {exc}") from exc


def _canonicalise_canvas(canvas_data: dict) -> dict:
    """Validate and apply defaults to canvas_data.

    Returns a new dict with all expected keys populated. Output dimensions
    are clamped to ``[_MIN_DIMENSION, _MAX_DIMENSION]`` per axis.

    Raises BadgeRenderError if output dimensions are non-numeric or missing
    in a way we cannot default.
    """
    output = canvas_data.get("output", {})
    try:
        width = min(
            max(int(output.get("width_px", _DEFAULT_WIDTH)), _MIN_DIMENSION),
            _MAX_DIMENSION,
        )
        height = min(
            max(int(output.get("height_px", _DEFAULT_HEIGHT)), _MIN_DIMENSION),
            _MAX_DIMENSION,
        )
    except (TypeError, ValueError) as exc:
        raise BadgeRenderError(
            "canvas_data contains invalid output dimensions"
        ) from exc

    return {
        **canvas_data,
        "background": canvas_data.get("background", _DEFAULT_BACKGROUND),
        "typography": canvas_data.get("typography", _DEFAULT_TYPOGRAPHY),
        "logo": canvas_data.get("logo", {}),
        "fields": canvas_data.get("fields", []),
        "output": {"width_px": width, "height_px": height, "format": "png"},
    }


def _draw_background(img: Image.Image, background: dict) -> None:
    """Render the canvas background in place.

    Supports ``type: "solid"`` and ``type: "gradient"``. Unknown types fall
    back to the default solid colour, logged at warning level.
    """
    bg_type = background.get("type", "solid")

    if bg_type == "solid":
        color = background.get("color", _DEFAULT_BACKGROUND["color"])
        rgb = _hex_to_rgb(color)
        ImageDraw.Draw(img).rectangle(
            (0, 0, img.width, img.height),
            fill=rgb,
        )
        return

    if bg_type == "gradient":
        start_hex = background.get("from", _DEFAULT_BACKGROUND["color"])
        end_hex = background.get("to", _DEFAULT_BACKGROUND["color"])
        start = _hex_to_rgb(start_hex)
        end = _hex_to_rgb(end_hex)
        draw = ImageDraw.Draw(img)
        for y in range(img.height):
            t = y / max(img.height - 1, 1)
            draw.line(
                [(0, y), (img.width - 1, y)],
                fill=_lerp_color(start, end, t),
            )
        return

    logger.warning(
        "Unknown background type %r, falling back to default solid",
        bg_type,
    )
    rgb = _hex_to_rgb(_DEFAULT_BACKGROUND["color"])
    ImageDraw.Draw(img).rectangle((0, 0, img.width, img.height), fill=rgb)


def _draw_logo(img: Image.Image, logo_config: dict) -> None:
    """Render the organiser logo. Implemented in commit 3."""
    return None


def _draw_fields(
    img: Image.Image,
    canvas: dict,
    participant_inputs: dict[str, str],
    photo_data: bytes | None,
    spec: LayoutSpec,
) -> None:
    """Walk canvas.fields and render each. Implemented in commits 3 and 4."""
    return None


def render_badge(
    canvas_data: dict,
    participant_inputs: dict[str, str],
    photo_data: bytes | None = None,
) -> bytes:
    """Render a personalised badge and return the PNG bytes.

    The renderer reads canvas_data (from OrganiserTemplate.canvas_data),
    composites participant inputs, and returns the final image encoded as
    PNG. Optional asset failures (logo, photo) are non-fatal and logged.

    Raises BadgeRenderError on conditions that prevent any output, such as
    invalid output dimensions or font loading failures.
    """
    canvas = _canonicalise_canvas(canvas_data)
    width = canvas["output"]["width_px"]
    height = canvas["output"]["height_px"]
    layout_id = canvas.get("layout_id", "")
    spec = LAYOUT_SPECS.get(layout_id, DEFAULT_SPEC)
    with Image.new("RGB", (width, height)) as img:
        _draw_background(img, canvas["background"])
        _draw_logo(img, canvas.get("logo", {}))
        _draw_fields(img, canvas, participant_inputs, photo_data, spec)

        buf = BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
