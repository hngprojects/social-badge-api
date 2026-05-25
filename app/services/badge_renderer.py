"""Badge renderer: composes participant badges from canvas configuration.

This module owns the Pillow rendering pipeline. It reads canvas_data
(stored as JSONB on OrganiserTemplate) and produces a PNG byte string.

Commit 2 laid down canvas setup, background rendering, and the render
entry point. Commit 3 adds text fitting, logo rendering, and field layout.
Photo compositing lands in Commit 4.
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


LAYOUT_SPECS: dict[str, LayoutSpec] = {
    "photo_gradient_v1": LayoutSpec(
        photo_diameter_ratio=0.55,
        photo_y_ratio=0.08,
        text_y_start_ratio=0.60,
        text_y_start_no_photo=0.35,
        text_color="#FFFFFF",
        padding=48,
    ),
    "dev_summit_dark_v1": LayoutSpec(
        photo_diameter_ratio=0.50,
        photo_y_ratio=0.10,
        text_y_start_ratio=0.62,
        text_y_start_no_photo=0.38,
        text_color="#FFFFFF",
        padding=48,
    ),
    "name_role_dark_v1": LayoutSpec(
        photo_diameter_ratio=0.45,
        photo_y_ratio=0.12,
        text_y_start_ratio=0.58,
        text_y_start_no_photo=0.30,
        text_color="#FFFFFF",
        padding=48,
    ),
    "next_gen_mint_v1": LayoutSpec(
        photo_diameter_ratio=0.50,
        photo_y_ratio=0.08,
        text_y_start_ratio=0.60,
        text_y_start_no_photo=0.35,
        text_color="#1A1A1A",
        padding=48,
    ),
}

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


# ---------------------------------------------------------------------------
# Text fitting
# ---------------------------------------------------------------------------


def _fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font_family: str,
    base_size: int,
    *,
    bold: bool,
    max_width: int,
) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    """Find a font size and line layout that fits ``text`` within ``max_width``.

    Strategy:
      1. Try the base size on a single line.
      2. If it overflows, wrap at whitespace into two lines.
      3. If still overflowing, reduce size by 20 percent and wrap again.

    Returns the font to use and the list of lines to draw.
    """
    font = _load_font(font_family, base_size, bold=bold)
    if draw.textlength(text, font=font) <= max_width:
        return font, [text]

    wrapped = _wrap_at_whitespace(text, draw, font, max_width)
    if all(draw.textlength(line, font=font) <= max_width for line in wrapped):
        return font, wrapped

    smaller_size = max(int(base_size * 0.8), 12)
    font = _load_font(font_family, smaller_size, bold=bold)
    wrapped = _wrap_at_whitespace(text, draw, font, max_width)
    return font, wrapped


def _wrap_at_whitespace(
    text: str,
    draw: ImageDraw.ImageDraw,
    font: ImageFont.FreeTypeFont,
    max_width: int,
) -> list[str]:
    """Wrap ``text`` into at most two lines, splitting at whitespace.

    Returns a single-line list when the text fits or has no whitespace to
    split on; otherwise returns two lines balanced as evenly as possible.
    """
    words = text.split()
    if len(words) < 2:
        return [text]

    best_split = 1
    for i in range(1, len(words)):
        first = " ".join(words[:i])
        if draw.textlength(first, font=font) <= max_width:
            best_split = i
        else:
            break

    return [" ".join(words[:best_split]), " ".join(words[best_split:])]


# ---------------------------------------------------------------------------
# Logo rendering
# ---------------------------------------------------------------------------


def _draw_logo(img: Image.Image, logo_config: dict) -> None:
    """Fetch and paste the organiser logo onto the canvas.

    Logo failures (network, decode, oversized) are logged and skipped so
    the badge still renders without it. The logo is sized to 25 percent of
    the canvas width with aspect ratio preserved, and positioned per
    ``logo.position`` with a 48 px margin from the canvas edge.
    """
    url = logo_config.get("url")
    if not url:
        return

    logo_bytes = _fetch_remote_image(url)
    if logo_bytes is None:
        return

    try:
        with Image.open(BytesIO(logo_bytes)) as raw:
            raw.load()
            logo = raw.convert("RGBA")
    except Exception:
        logger.warning("Could not decode logo from %s, skipping", url)
        return

    target_width = int(img.width * 0.25)
    if logo.width == 0 or logo.height == 0:
        logger.warning("Logo at %s has zero dimensions, skipping", url)
        return
    scale = target_width / logo.width
    target_height = max(int(logo.height * scale), 1)
    logo = logo.resize((target_width, target_height), Image.LANCZOS)

    position = logo_config.get("position", "top-center")
    margin = DEFAULT_SPEC.padding
    y = margin
    if position == "top-left":
        x = margin
    elif position == "top-right":
        x = img.width - target_width - margin
    else:  # top-center and any unknown value
        x = (img.width - target_width) // 2

    img.paste(logo, (x, y), logo)


def _fetch_remote_image(url: str) -> bytes | None:
    """Fetch a remote image with a 5-second timeout.

    Returns the raw bytes on success or None on any failure (network,
    timeout, non-2xx status). All failures are logged at warning level.

    Stub for Commit 3 — Commit 8 will route this through the remote-image
    circuit breaker and the shared validation helper in app/services/badge.
    """
    try:
        import httpx

        with httpx.Client(timeout=5.0) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.content
    except Exception:
        logger.warning("Failed to fetch remote image from %s, skipping", url)
        return None


def _composite_photo(
    img: Image.Image,
    photo_data: bytes,
    spec: LayoutSpec,
) -> bool:
    """Composite a circular participant photo onto the canvas.

    Opens photo bytes, center-crops to a square, resizes to the layout's
    photo diameter, applies a circular alpha mask, and pastes centered
    horizontally at the layout's photo_y_ratio.

    Returns True on success, False if the photo could not be decoded or
    failed any safety check. Failures log a warning and continue; the
    badge still renders without the photo.
    """
    diameter = int(img.width * spec.photo_diameter_ratio)
    if diameter <= 0:
        logger.warning("Photo diameter resolved to zero, skipping composite")
        return False

    y_offset = int(img.height * spec.photo_y_ratio)

    try:
        with Image.open(BytesIO(photo_data)) as raw:
            raw.load()
            photo = raw.convert("RGBA")
    except Image.DecompressionBombError:
        logger.warning("Participant photo exceeds pixel limit, skipping composite")
        return False
    except Exception:
        logger.warning("Could not decode participant photo, skipping composite")
        return False

    side = min(photo.width, photo.height)
    left = (photo.width - side) // 2
    top = (photo.height - side) // 2
    photo = photo.crop((left, top, left + side, top + side)).resize(
        # pyrefly: ignore [missing-attribute]
        (diameter, diameter),
        Image.LANCZOS,
    )
    mask = Image.new("L", (diameter, diameter), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, diameter, diameter), fill=255)
    photo.putalpha(mask)

    x_offset = (img.width - diameter) // 2
    img.paste(photo, (x_offset, y_offset), photo)
    return True


def _draw_fields(
    img: Image.Image,
    canvas: dict,
    participant_inputs: dict[str, str],
    photo_data: bytes | None,
    spec: LayoutSpec,
) -> None:
    """Walk canvas.fields in order and draw static and participant_input fields.

    Field rendering rules:
      - ``visible: false`` fields are skipped.
      - ``static`` fields use ``field.value`` rendered at 55 percent of base size.
      - ``participant_input`` with key ``participant_name`` uses base size, bold.
      - Other ``participant_input`` fields use 60 percent of base size.
      - ``participant_upload`` is handled by _composite_photo (Commit 4).

    Long text is wrapped or downsized via _fit_text.
    """
    fields = canvas.get("fields", [])
    typography = canvas["typography"]
    font_family = typography.get("font_family", "DM Sans")
    base_size = int(typography.get("size_px", 42))
    text_color = _hex_to_rgb(spec.text_color)

    has_photo = photo_data is not None and any(
        f.get("type") == "participant_upload" for f in fields
    )
    start_ratio = spec.text_y_start_ratio if has_photo else spec.text_y_start_no_photo
    y_cursor = int(img.height * start_ratio)
    max_text_width = int(img.width * 0.85)

    draw = ImageDraw.Draw(img)

    for field in fields:
        if field.get("visible", True) is False:
            continue

        field_type = field.get("type")
        field_key = field.get("key", "")

        if field_type == "static":
            content = str(field.get("value", ""))
            size = max(int(base_size * 0.55), 12)
            bold = False
        elif field_type == "participant_input":
            content = participant_inputs.get(field_key, "")
            if field_key == "participant_name":
                size = base_size
                bold = True
            else:
                size = max(int(base_size * 0.6), 12)
                bold = False
        elif field_type == "participant_upload":
            if photo_data is not None:
                _composite_photo(img, photo_data, spec)
            continue
        else:
            # Unknown types: skip
            continue

        if not content:
            continue

        font, lines = _fit_text(
            draw,
            content,
            font_family,
            size,
            bold=bold,
            max_width=max_text_width,
        )
        line_spacing = int(size * 0.2)
        for line in lines:
            line_width = draw.textlength(line, font=font)
            x = (img.width - int(line_width)) // 2
            draw.text((x, y_cursor), line, font=font, fill=text_color)
            y_cursor += size + line_spacing


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
