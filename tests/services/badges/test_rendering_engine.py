import pytest
from io import BytesIO
from unittest.mock import patch, MagicMock
from PIL import Image
from services.badges.rendering.engine import render_badge


class TestRenderBadge:
    """Test badge rendering engine."""

    @pytest.fixture
    def sample_png_bytes(self):
        """Create a minimal valid PNG image."""
        img = Image.new("RGB", (100, 100), color="blue")
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer.getvalue()

    def test_render_badge_returns_bytesio(self, sample_png_bytes):
        """Test that render_badge returns a BytesIO object."""
        with patch("services.badges.rendering.engine.httpx.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = sample_png_bytes
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response
            
            result = render_badge("https://example.com/profile.jpg")
            
            assert isinstance(result, BytesIO)
            assert result.tell() == 0  # Should be at start of buffer

    def test_render_badge_fetches_profile_image(self, sample_png_bytes):
        """Test that render_badge fetches the profile image from URL."""
        with patch("services.badges.rendering.engine.httpx.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = sample_png_bytes
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response
            
            url = "https://example.com/alice.jpg"
            render_badge(url)
            
            mock_get.assert_called_once()
            args, kwargs = mock_get.call_args
            assert args[0] == url
            assert kwargs.get("timeout") == 5

    def test_render_badge_with_invalid_url_raises_error(self):
        """Test that invalid/unreachable URL raises an error."""
        with patch("services.badges.rendering.engine.httpx.get") as mock_get:
            mock_get.side_effect = Exception("Connection failed")
            
            with pytest.raises(Exception):
                render_badge("https://invalid-url-that-does-not-exist.com/photo.jpg")

    def test_render_badge_handles_http_error(self, sample_png_bytes):
        """Test handling of HTTP errors (4xx, 5xx)."""
        with patch("services.badges.rendering.engine.httpx.get") as mock_get:
            mock_response = MagicMock()
            mock_response.raise_for_status.side_effect = Exception("HTTP 404")
            mock_get.return_value = mock_response
            
            with pytest.raises(Exception):
                render_badge("https://example.com/notfound.jpg")

    def test_render_badge_output_is_png_format(self, sample_png_bytes):
        """Test that rendered output is valid PNG format."""
        with patch("services.badges.rendering.engine.httpx.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = sample_png_bytes
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response
            
            result = render_badge("https://example.com/profile.jpg")
            result.seek(0)
            
            # Check PNG magic bytes
            png_header = result.read(8)
            assert png_header == b'\x89PNG\r\n\x1a\n'

    def test_render_badge_creates_square_image(self, sample_png_bytes):
        """Test that rendered badge is 1080x1080 pixels."""
        with patch("services.badges.rendering.engine.httpx.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = sample_png_bytes
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response
            
            result = render_badge("https://example.com/profile.jpg")
            result.seek(0)
            
            rendered_img = Image.open(result)
            assert rendered_img.size == (1080, 1080)

    def test_render_badge_with_multiple_image_formats(self, sample_png_bytes):
        """Test rendering with different image format inputs."""
        # Create JPEG image
        jpg_img = Image.new("RGB", (100, 100), color="red")
        jpg_buffer = BytesIO()
        jpg_img.save(jpg_buffer, format="JPEG")
        jpg_bytes = jpg_buffer.getvalue()
        
        with patch("services.badges.rendering.engine.httpx.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = jpg_bytes
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response
            
            result = render_badge("https://example.com/profile.jpg")
            assert isinstance(result, BytesIO)

    def test_render_badge_timeout_configuration(self, sample_png_bytes):
        """Test that render_badge uses correct timeout."""
        with patch("services.badges.rendering.engine.httpx.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = sample_png_bytes
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response
            
            render_badge("https://example.com/profile.jpg")
            
            _, kwargs = mock_get.call_args
            assert kwargs["timeout"] == 5

    def test_render_badge_buffer_is_seekable(self, sample_png_bytes):
        """Test that returned buffer is seekable."""
        with patch("services.badges.rendering.engine.httpx.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = sample_png_bytes
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response
            
            result = render_badge("https://example.com/profile.jpg")
            
            # Test seeking
            result.seek(0)
            result.seek(100)
            result.seek(0)
            assert result.tell() == 0

    def test_render_badge_with_special_characters_in_url(self, sample_png_bytes):
        """Test rendering with special characters in profile URL."""
        with patch("services.badges.rendering.engine.httpx.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = sample_png_bytes
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response
            
            url = "https://example.com/profile?size=300&format=jpg&v=2"
            result = render_badge(url)
            
            assert isinstance(result, BytesIO)
            mock_get.assert_called_once()

    def test_render_badge_handles_timeout_error(self):
        """Test handling of request timeout."""
        with patch("services.badges.rendering.engine.httpx.get") as mock_get:
            mock_get.side_effect = TimeoutError("Request timed out")
            
            # The engine catches exceptions and re-raises as RuntimeError
            with pytest.raises(RuntimeError) as exc_info:
                render_badge("https://example.com/very-slow-server.jpg")
            assert "Failed to download or process profile image" in str(exc_info.value)
