"""Tests for app.services.badge_renderer (canvas + background)."""

from __future__ import annotations

import pytest
from PIL import Image, ImageDraw

from app.core.exceptions import BadgeRenderError
from app.services.badge_renderer import (
    DEFAULT_SPEC,
    LAYOUT_SPECS,
    LayoutSpec,
    _canonicalise_canvas,
    _draw_background,
    _hex_to_rgb,
    _lerp_color,
    _load_font,
    render_badge,
)


class TestHexToRgb:
    def test_accepts_hash_prefix(self) -> None:
        assert _hex_to_rgb("#FF0000") == (255, 0, 0)

    def test_accepts_no_hash_prefix(self) -> None:
        assert _hex_to_rgb("00FF00") == (0, 255, 0)

    def test_lowercase_hex(self) -> None:
        assert _hex_to_rgb("#0000ff") == (0, 0, 255)

    def test_mixed_case_hex(self) -> None:
        assert _hex_to_rgb("#aAbBcC") == (170, 187, 204)

    def test_strips_whitespace(self) -> None:
        assert _hex_to_rgb("  #FFFFFF  ") == (255, 255, 255)

    def test_pure_black(self) -> None:
        assert _hex_to_rgb("#000000") == (0, 0, 0)

    def test_pure_white(self) -> None:
        assert _hex_to_rgb("#FFFFFF") == (255, 255, 255)

    def test_invalid_length_raises(self) -> None:
        with pytest.raises(BadgeRenderError, match="Invalid hex colour"):
            _hex_to_rgb("#FFF")

    def test_invalid_characters_raises(self) -> None:
        with pytest.raises(BadgeRenderError, match="Invalid hex colour"):
            _hex_to_rgb("#GGGGGG")

    def test_empty_string_raises(self) -> None:
        with pytest.raises(BadgeRenderError, match="Invalid hex colour"):
            _hex_to_rgb("")


class TestLerpColor:
    def test_t_zero_returns_start(self) -> None:
        assert _lerp_color((0, 0, 0), (255, 255, 255), 0.0) == (0, 0, 0)

    def test_t_one_returns_end(self) -> None:
        assert _lerp_color((0, 0, 0), (255, 255, 255), 1.0) == (255, 255, 255)

    def test_midpoint_is_average(self) -> None:
        result = _lerp_color((0, 0, 0), (255, 255, 255), 0.5)
        assert result == (127, 127, 127)

    def test_quarter_point(self) -> None:
        result = _lerp_color((0, 0, 0), (200, 100, 40), 0.25)
        assert result == (50, 25, 10)

    def test_t_clamped_below_zero(self) -> None:
        assert _lerp_color((10, 20, 30), (200, 100, 50), -1.0) == (10, 20, 30)

    def test_t_clamped_above_one(self) -> None:
        assert _lerp_color((10, 20, 30), (200, 100, 50), 5.0) == (200, 100, 50)

    def test_different_channels_interpolate_independently(self) -> None:
        result = _lerp_color((0, 128, 255), (255, 128, 0), 0.5)
        assert result == (127, 128, 127)


class TestLoadFont:
    def test_loads_regular_font(self) -> None:
        font = _load_font("DM Sans", 42, bold=False)
        assert font.size == 42

    def test_loads_bold_font(self) -> None:
        font = _load_font("DM Sans", 56, bold=True)
        assert font.size == 56

    def test_unknown_family_falls_back_to_dm_sans(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        import logging

        with caplog.at_level(logging.INFO, logger="app.services.badge_renderer"):
            font = _load_font("Comic Sans", 32, bold=False)
        assert font.size == 32
        assert any("falling back to DM Sans" in r.message for r in caplog.records)

    def test_empty_family_loads_default_without_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        import logging

        with caplog.at_level(logging.INFO, logger="app.services.badge_renderer"):
            font = _load_font("", 24, bold=False)
        assert font.size == 24
        assert not any("falling back" in r.message for r in caplog.records)


class TestCanonicaliseCanvas:
    def test_applies_all_defaults_for_empty_input(self) -> None:
        result = _canonicalise_canvas({})
        assert result["background"] == {"type": "solid", "color": "#1A1A2E"}
        assert result["typography"]["font_family"] == "DM Sans"
        assert result["logo"] == {}
        assert result["fields"] == []
        assert result["output"]["width_px"] == 1080
        assert result["output"]["height_px"] == 1350
        assert result["output"]["format"] == "png"

    def test_preserves_provided_values(self) -> None:
        input_data = {
            "background": {"type": "solid", "color": "#FF0000"},
            "fields": [{"key": "name", "type": "participant_input"}],
            "output": {"width_px": 800, "height_px": 1000},
        }
        result = _canonicalise_canvas(input_data)
        assert result["background"] == {"type": "solid", "color": "#FF0000"}
        assert result["fields"] == [{"key": "name", "type": "participant_input"}]
        assert result["output"]["width_px"] == 800
        assert result["output"]["height_px"] == 1000

    def test_clamps_width_to_max(self) -> None:
        result = _canonicalise_canvas(
            {"output": {"width_px": 10000, "height_px": 1000}}
        )
        assert result["output"]["width_px"] == 4000

    def test_clamps_height_to_max(self) -> None:
        result = _canonicalise_canvas(
            {"output": {"width_px": 1000, "height_px": 10000}}
        )
        assert result["output"]["height_px"] == 4000

    def test_clamps_width_to_min(self) -> None:
        result = _canonicalise_canvas({"output": {"width_px": 100, "height_px": 1000}})
        assert result["output"]["width_px"] == 500

    def test_clamps_height_to_min(self) -> None:
        result = _canonicalise_canvas({"output": {"width_px": 1000, "height_px": 100}})
        assert result["output"]["height_px"] == 500

    def test_invalid_width_raises(self) -> None:
        with pytest.raises(BadgeRenderError, match="invalid output dimensions"):
            _canonicalise_canvas({"output": {"width_px": "wide", "height_px": 1000}})

    def test_invalid_height_raises(self) -> None:
        with pytest.raises(BadgeRenderError, match="invalid output dimensions"):
            _canonicalise_canvas({"output": {"width_px": 1000, "height_px": None}})

    def test_extra_keys_are_preserved(self) -> None:
        result = _canonicalise_canvas({"layout_id": "photo_gradient_v1"})
        assert result["layout_id"] == "photo_gradient_v1"


class TestDrawBackground:
    def test_solid_fills_uniform_color(self) -> None:
        img = Image.new("RGB", (50, 50))
        _draw_background(img, {"type": "solid", "color": "#FF0000"})
        assert img.getpixel((0, 0)) == (255, 0, 0)
        assert img.getpixel((25, 25)) == (255, 0, 0)
        assert img.getpixel((49, 49)) == (255, 0, 0)

    def test_gradient_transitions_top_to_bottom(self) -> None:
        img = Image.new("RGB", (10, 100))
        _draw_background(img, {"type": "gradient", "from": "#000000", "to": "#FFFFFF"})
        top = img.getpixel((5, 0))
        middle = img.getpixel((5, 50))
        bottom = img.getpixel((5, 99))
        assert top[0] < middle[0] < bottom[0]
        assert top == (0, 0, 0)
        assert bottom == (255, 255, 255)

    def test_unknown_type_falls_back_to_default(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        import logging

        img = Image.new("RGB", (10, 10))
        with caplog.at_level(logging.WARNING, logger="app.services.badge_renderer"):
            _draw_background(img, {"type": "starfield"})
        assert img.getpixel((0, 0)) == _hex_to_rgb("#1A1A2E")
        assert any("Unknown background type" in r.message for r in caplog.records)

    def test_solid_missing_color_uses_default(self) -> None:
        img = Image.new("RGB", (10, 10))
        _draw_background(img, {"type": "solid"})
        assert img.getpixel((0, 0)) == _hex_to_rgb("#1A1A2E")

    def test_gradient_missing_endpoints_uses_default(self) -> None:
        img = Image.new("RGB", (10, 10))
        _draw_background(img, {"type": "gradient"})
        assert img.getpixel((0, 0)) == _hex_to_rgb("#1A1A2E")
        assert img.getpixel((9, 9)) == _hex_to_rgb("#1A1A2E")


class TestRenderBadge:
    def test_returns_valid_png_bytes(self) -> None:
        result = render_badge(
            canvas_data={"output": {"width_px": 500, "height_px": 500}},
            participant_inputs={"participant_name": "Jane"},
        )
        assert result[:8] == b"\x89PNG\r\n\x1a\n"

    def test_output_dimensions_match_canvas_config(self) -> None:
        from io import BytesIO

        result = render_badge(
            canvas_data={"output": {"width_px": 600, "height_px": 800}},
            participant_inputs={},
        )
        with Image.open(BytesIO(result)) as img:
            assert img.size == (600, 800)

    def test_returns_bytes_with_empty_canvas_data(self) -> None:
        result = render_badge(canvas_data={}, participant_inputs={})
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_unknown_layout_falls_back_to_default_spec(self) -> None:
        result = render_badge(
            canvas_data={"layout_id": "nonexistent_layout"},
            participant_inputs={},
        )
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_solid_background_applied_in_full_pipeline(self) -> None:
        from io import BytesIO

        result = render_badge(
            canvas_data={
                "background": {"type": "solid", "color": "#00FF00"},
                "output": {"width_px": 200, "height_px": 200},
            },
            participant_inputs={},
        )
        with Image.open(BytesIO(result)) as img:
            img.load()
            assert img.getpixel((100, 100)) == (0, 255, 0)

    def test_gradient_background_applied_in_full_pipeline(self) -> None:
        from io import BytesIO

        result = render_badge(
            canvas_data={
                "background": {
                    "type": "gradient",
                    "from": "#000000",
                    "to": "#FFFFFF",
                },
                "output": {"width_px": 500, "height_px": 1000},
            },
            participant_inputs={},
        )
        with Image.open(BytesIO(result)) as img:
            img.load()
            top = img.getpixel((250, 0))
            bottom = img.getpixel((250, 999))
            assert top == (0, 0, 0)
            assert bottom == (255, 255, 255)

    def test_invalid_dimensions_raise_badge_render_error(self) -> None:
        with pytest.raises(BadgeRenderError):
            render_badge(
                canvas_data={"output": {"width_px": "wide", "height_px": 100}},
                participant_inputs={},
            )


class TestLayoutSpec:
    def test_default_spec_has_expected_ratios(self) -> None:
        assert 0 < DEFAULT_SPEC.photo_diameter_ratio < 1
        assert 0 < DEFAULT_SPEC.photo_y_ratio < 1
        assert 0 < DEFAULT_SPEC.text_y_start_ratio < 1
        assert 0 < DEFAULT_SPEC.text_y_start_no_photo < 1

    def test_default_spec_text_color_is_hex(self) -> None:
        assert DEFAULT_SPEC.text_color.startswith("#")
        _hex_to_rgb(DEFAULT_SPEC.text_color)

    def test_layout_spec_is_frozen(self) -> None:
        import dataclasses

        with pytest.raises(dataclasses.FrozenInstanceError):
            DEFAULT_SPEC.padding = 100  # type: ignore[misc]

    def test_layout_specs_dict_exists(self) -> None:
        assert isinstance(LAYOUT_SPECS, dict)


class TestWrapAtWhitespace:
    def _setup(self, base_size: int = 42):
        """Create a draw context and a font for measuring."""
        from app.services.badge_renderer import _load_font, _wrap_at_whitespace

        img = Image.new("RGB", (1000, 200))
        draw = ImageDraw.Draw(img)
        font = _load_font("DM Sans", base_size, bold=False)
        return draw, font, _wrap_at_whitespace

    def test_single_word_returns_unchanged(self) -> None:
        draw, font, wrap = self._setup()
        assert wrap("Jane", draw, font, 1000) == ["Jane"]

    def test_empty_string_returns_unchanged(self) -> None:
        draw, font, wrap = self._setup()
        assert wrap("", draw, font, 1000) == [""]

    def test_two_words_split_when_too_wide(self) -> None:
        draw, font, wrap = self._setup()
        result = wrap("Jane Doe", draw, font, 50)
        assert len(result) == 2
        assert result == ["Jane", "Doe"]

    def test_long_name_wraps_to_two_lines(self) -> None:
        draw, font, wrap = self._setup()
        result = wrap("Adebayo Olanrewaju Adekunle", draw, font, 200)
        assert len(result) == 2
        assert all(line.strip() for line in result)


class TestFitText:
    def _setup(self):
        from app.services.badge_renderer import _fit_text

        img = Image.new("RGB", (1000, 200))
        draw = ImageDraw.Draw(img)
        return draw, _fit_text

    def test_short_text_fits_single_line_at_base_size(self) -> None:
        draw, fit = self._setup()
        font, lines = fit(draw, "Jane", "DM Sans", 42, bold=False, max_width=1000)
        assert lines == ["Jane"]
        assert font.size == 42

    def test_long_text_wraps_to_two_lines(self) -> None:
        draw, fit = self._setup()
        font, lines = fit(
            draw,
            "Adebayo Olanrewaju Adekunle",
            "DM Sans",
            42,
            bold=False,
            max_width=420,
        )
        assert len(lines) == 2
        assert font.size == 42

    def test_very_long_text_reduces_size(self) -> None:
        draw, fit = self._setup()
        font, lines = fit(
            draw,
            "Adebayo Olanrewaju Adekunle Babatunde",
            "DM Sans",
            42,
            bold=False,
            max_width=80,
        )
        assert font.size < 42

    def test_minimum_font_size_floor(self) -> None:
        draw, fit = self._setup()
        font, _ = fit(
            draw,
            "ridiculously long unreasonable test name string",
            "DM Sans",
            14,
            bold=False,
            max_width=10,
        )
        assert font.size >= 12

    def test_bold_flag_propagates(self) -> None:
        draw, fit = self._setup()
        font, _ = fit(draw, "Jane", "DM Sans", 42, bold=True, max_width=1000)
        assert font.size == 42


class TestDrawLogo:
    def _make_logo_png_bytes(
        self,
        width: int = 200,
        height: int = 100,
        color: tuple[int, int, int] = (255, 0, 0),
    ) -> bytes:
        from io import BytesIO

        logo = Image.new("RGB", (width, height), color)
        buf = BytesIO()
        logo.save(buf, format="PNG")
        return buf.getvalue()

    def test_returns_silently_when_no_url(self) -> None:
        from app.services.badge_renderer import _draw_logo

        img = Image.new("RGB", (1000, 1000), (0, 0, 0))
        _draw_logo(img, {})  # no url
        assert img.getpixel((500, 100)) == (0, 0, 0)

    def test_returns_silently_on_fetch_failure(
        self, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import logging
        from app.services import badge_renderer

        monkeypatch.setattr(badge_renderer, "_fetch_remote_image", lambda url: None)

        img = Image.new("RGB", (1000, 1000), (0, 0, 0))
        with caplog.at_level(logging.WARNING, logger="app.services.badge_renderer"):
            badge_renderer._draw_logo(img, {"url": "https://example.com/logo.png"})
        assert img.getpixel((500, 100)) == (0, 0, 0)

    def test_pastes_logo_at_top_center_by_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.services import badge_renderer

        red_logo = self._make_logo_png_bytes(color=(255, 0, 0))
        monkeypatch.setattr(badge_renderer, "_fetch_remote_image", lambda url: red_logo)

        img = Image.new("RGB", (1000, 1000), (0, 0, 0))
        badge_renderer._draw_logo(img, {"url": "x"})
        assert img.getpixel((500, 70)) == (255, 0, 0)
        assert img.getpixel((500, 500)) == (0, 0, 0)

    def test_pastes_logo_at_top_left(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.services import badge_renderer

        red_logo = self._make_logo_png_bytes(color=(255, 0, 0))
        monkeypatch.setattr(badge_renderer, "_fetch_remote_image", lambda url: red_logo)

        img = Image.new("RGB", (1000, 1000), (0, 0, 0))
        badge_renderer._draw_logo(img, {"url": "x", "position": "top-left"})
        assert img.getpixel((100, 70)) == (255, 0, 0)
        assert img.getpixel((900, 70)) == (0, 0, 0)

    def test_pastes_logo_at_top_right(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.services import badge_renderer

        red_logo = self._make_logo_png_bytes(color=(255, 0, 0))
        monkeypatch.setattr(badge_renderer, "_fetch_remote_image", lambda url: red_logo)

        img = Image.new("RGB", (1000, 1000), (0, 0, 0))
        badge_renderer._draw_logo(img, {"url": "x", "position": "top-right"})
        assert img.getpixel((800, 70)) == (255, 0, 0)
        assert img.getpixel((100, 70)) == (0, 0, 0)

    def test_unknown_position_falls_back_to_center(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.services import badge_renderer

        red_logo = self._make_logo_png_bytes(color=(255, 0, 0))
        monkeypatch.setattr(badge_renderer, "_fetch_remote_image", lambda url: red_logo)

        img = Image.new("RGB", (1000, 1000), (0, 0, 0))
        badge_renderer._draw_logo(img, {"url": "x", "position": "bottom-spiral"})
        assert img.getpixel((500, 70)) == (255, 0, 0)

    def test_aspect_ratio_preserved(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.services import badge_renderer

        red_logo = self._make_logo_png_bytes(width=400, height=200, color=(255, 0, 0))
        monkeypatch.setattr(badge_renderer, "_fetch_remote_image", lambda url: red_logo)

        img = Image.new("RGB", (1000, 1000), (0, 0, 0))
        badge_renderer._draw_logo(img, {"url": "x"})
        assert img.getpixel((500, 100)) == (255, 0, 0)
        assert img.getpixel((500, 200)) == (0, 0, 0)

    def test_corrupt_image_bytes_logged_and_skipped(
        self,
        caplog: pytest.LogCaptureFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import logging
        from app.services import badge_renderer

        monkeypatch.setattr(
            badge_renderer, "_fetch_remote_image", lambda url: b"not an image"
        )

        img = Image.new("RGB", (1000, 1000), (0, 0, 0))
        with caplog.at_level(logging.WARNING, logger="app.services.badge_renderer"):
            badge_renderer._draw_logo(img, {"url": "x"})

        assert img.getpixel((500, 70)) == (0, 0, 0)
        assert any("Could not decode logo" in r.message for r in caplog.records)


class TestDrawFields:
    def _base_canvas(self, fields: list[dict]) -> dict:
        return {
            "typography": {"font_family": "DM Sans", "size_px": 42, "weight": "bold"},
            "fields": fields,
        }

    def test_empty_fields_does_nothing(self) -> None:
        from app.services.badge_renderer import _draw_fields, DEFAULT_SPEC

        img = Image.new("RGB", (1000, 1000), (0, 0, 0))
        _draw_fields(img, self._base_canvas([]), {}, None, DEFAULT_SPEC)
        # No fields drawn, image still black
        assert img.getpixel((500, 700)) == (0, 0, 0)

    def test_invisible_fields_are_skipped(self) -> None:
        from app.services.badge_renderer import _draw_fields, DEFAULT_SPEC

        canvas = self._base_canvas(
            [
                {
                    "key": "event_name",
                    "type": "static",
                    "value": "Should Not Appear",
                    "visible": False,
                },
            ]
        )

        img = Image.new("RGB", (1000, 1000), (0, 0, 0))
        _draw_fields(img, canvas, {}, None, DEFAULT_SPEC)
        pixels = {
            img.getpixel((x, y))
            for x in range(0, 1000, 100)
            for y in range(0, 1000, 100)
        }
        assert pixels == {(0, 0, 0)}

    def test_static_field_renders_value(self) -> None:
        from app.services.badge_renderer import _draw_fields, DEFAULT_SPEC

        canvas = self._base_canvas(
            [
                {"key": "event_name", "type": "static", "value": "DevSummit"},
            ]
        )

        img = Image.new("RGB", (1000, 1000), (0, 0, 0))
        _draw_fields(img, canvas, {}, None, DEFAULT_SPEC)
        sample = [
            img.getpixel((x, y))
            for x in range(200, 800, 40)
            for y in range(370, 430, 10)
        ]
        assert any(px != (0, 0, 0) for px in sample)

    def test_participant_name_renders_from_inputs(self) -> None:
        from app.services.badge_renderer import _draw_fields, DEFAULT_SPEC

        canvas = self._base_canvas(
            [
                {"key": "participant_name", "type": "participant_input"},
            ]
        )

        img = Image.new("RGB", (1000, 1000), (0, 0, 0))
        _draw_fields(
            img,
            canvas,
            {"participant_name": "Jane Doe"},
            None,
            DEFAULT_SPEC,
        )

        sample = [
            img.getpixel((x, y))
            for x in range(200, 800, 40)
            for y in range(370, 430, 10)
        ]
        assert any(px != (0, 0, 0) for px in sample)

    def test_missing_participant_input_skipped(self) -> None:
        from app.services.badge_renderer import _draw_fields, DEFAULT_SPEC

        canvas = self._base_canvas(
            [
                {"key": "participant_name", "type": "participant_input"},
            ]
        )

        img = Image.new("RGB", (1000, 1000), (0, 0, 0))
        _draw_fields(img, canvas, {}, None, DEFAULT_SPEC)

        pixels = {
            img.getpixel((x, y))
            for x in range(0, 1000, 100)
            for y in range(0, 1000, 100)
        }
        assert pixels == {(0, 0, 0)}

    def test_participant_upload_skipped_in_commit_3(self) -> None:
        from app.services.badge_renderer import _draw_fields, DEFAULT_SPEC

        canvas = self._base_canvas(
            [
                {"key": "participant_photo", "type": "participant_upload"},
            ]
        )

        img = Image.new("RGB", (1000, 1000), (0, 0, 0))
        _draw_fields(img, canvas, {}, b"fake_photo_bytes", DEFAULT_SPEC)

        pixels = {
            img.getpixel((x, y))
            for x in range(0, 1000, 100)
            for y in range(0, 1000, 100)
        }
        assert pixels == {(0, 0, 0)}

    def test_unknown_field_type_skipped(self) -> None:
        from app.services.badge_renderer import _draw_fields, DEFAULT_SPEC

        canvas = self._base_canvas(
            [
                {"key": "x", "type": "starfield", "value": "Hidden"},
            ]
        )

        img = Image.new("RGB", (1000, 1000), (0, 0, 0))
        _draw_fields(img, canvas, {}, None, DEFAULT_SPEC)

        pixels = {
            img.getpixel((x, y))
            for x in range(0, 1000, 100)
            for y in range(0, 1000, 100)
        }
        assert pixels == {(0, 0, 0)}

    def test_field_order_is_preserved(self) -> None:
        """Two static fields drawn in order should appear stacked top-to-bottom."""
        from app.services.badge_renderer import _draw_fields, DEFAULT_SPEC

        canvas = self._base_canvas(
            [
                {"key": "first", "type": "static", "value": "AAA"},
                {"key": "second", "type": "static", "value": "BBB"},
            ]
        )

        img = Image.new("RGB", (1000, 1000), (0, 0, 0))
        _draw_fields(img, canvas, {}, None, DEFAULT_SPEC)

        def first_text_row(y_start: int, y_end: int) -> int | None:
            for y in range(y_start, y_end):
                for x in range(0, 1000, 5):
                    if img.getpixel((x, y)) != (0, 0, 0):
                        return y
            return None

        first_top = first_text_row(370, 600)
        assert first_top is not None
        second_top = first_text_row(first_top + 30, 700)
        assert second_top is not None
        assert second_top > first_top


class TestRenderBadgeWithText:
    def test_renders_with_participant_name(self) -> None:
        from io import BytesIO

        result = render_badge(
            canvas_data={
                "background": {"type": "solid", "color": "#000000"},
                "fields": [
                    {"key": "participant_name", "type": "participant_input"},
                ],
                "output": {"width_px": 800, "height_px": 1000},
            },
            participant_inputs={"participant_name": "Jane Doe"},
        )

        with Image.open(BytesIO(result)) as img:
            img.load()
            text_pixels = [
                img.getpixel((x, y))
                for x in range(100, 700, 30)
                for y in range(350, 500, 10)
            ]
            assert any(px != (0, 0, 0) for px in text_pixels)

    def test_renders_with_static_and_participant_fields(self) -> None:
        from io import BytesIO

        result = render_badge(
            canvas_data={
                "background": {"type": "solid", "color": "#000000"},
                "fields": [
                    {"key": "event", "type": "static", "value": "DevSummit"},
                    {"key": "participant_name", "type": "participant_input"},
                ],
                "output": {"width_px": 800, "height_px": 1000},
            },
            participant_inputs={"participant_name": "Jane"},
        )
        assert result[:8] == b"\x89PNG\r\n\x1a\n"
