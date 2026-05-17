import pytest
import os
from io import BytesIO
from pathlib import Path
from unittest.mock import patch, MagicMock

from services.badges.services.img_service import save_image


class TestSaveImage:
    """Test local image file saving."""

    def test_save_image_creates_file(self, temp_badges_dir, mock_image_buffer):
        """Test that save_image creates a file in the badges directory."""
        with patch("services.badges.services.img_service.BADGE_DIR", temp_badges_dir):
            result = save_image(mock_image_buffer, "test_badge.png")
            
            # Check file was created
            filepath = os.path.join(temp_badges_dir, "test_badge.png")
            assert os.path.exists(filepath)
            assert result == "/badges/test_badge.png"

    def test_save_image_returns_correct_url_path(self, temp_badges_dir, mock_image_buffer):
        """Test that save_image returns the correct URL path."""
        with patch("services.badges.services.img_service.BADGE_DIR", temp_badges_dir):
            result = save_image(mock_image_buffer, "my_badge_123.png")
            assert result == "/badges/my_badge_123.png"

    def test_save_image_writes_content(self, temp_badges_dir, mock_image_buffer):
        """Test that image content is correctly written to file."""
        with patch("services.badges.services.img_service.BADGE_DIR", temp_badges_dir):
            original_content = mock_image_buffer.getvalue()
            save_image(mock_image_buffer, "content_test.png")
            
            filepath = os.path.join(temp_badges_dir, "content_test.png")
            with open(filepath, "rb") as f:
                saved_content = f.read()
            
            assert saved_content == original_content

    def test_save_image_with_different_filenames(self, temp_badges_dir, mock_image_buffer):
        """Test saving multiple images with different filenames."""
        with patch("services.badges.services.img_service.BADGE_DIR", temp_badges_dir):
            filenames = ["badge_001.png", "badge_002.jpg", "certificate_123.png"]
            
            for filename in filenames:
                result = save_image(mock_image_buffer, filename)
                assert result == f"/badges/{filename}"
                assert os.path.exists(os.path.join(temp_badges_dir, filename))

    def test_save_image_handles_buffer_position(self, temp_badges_dir):
        """Test that save_image correctly resets buffer position."""
        buffer = BytesIO()
        test_data = b"test image data"
        buffer.write(test_data)
        buffer.seek(5)  # Move pointer to middle
        
        with patch("services.badges.services.img_service.BADGE_DIR", temp_badges_dir):
            save_image(buffer, "buffer_test.png")
            
            filepath = os.path.join(temp_badges_dir, "buffer_test.png")
            with open(filepath, "rb") as f:
                saved_content = f.read()
            
            # Should have saved all content, not just from position 5
            assert saved_content == test_data

    def test_save_image_creates_directory_if_not_exists(self, tmp_path):
        """Test that save_image creates badges directory if it doesn't exist."""
        badges_dir = tmp_path / "new_badges_dir"
        assert not badges_dir.exists()
        
        buffer = BytesIO(b"test data")
        with patch("services.badges.services.img_service.BADGE_DIR", str(badges_dir)):
            result = save_image(buffer, "new_badge.png")
            
            assert badges_dir.exists()
            assert os.path.exists(badges_dir / "new_badge.png")

    def test_save_image_with_special_characters_in_filename(self, temp_badges_dir, mock_image_buffer):
        """Test saving with special characters in filename."""
        with patch("services.badges.services.img_service.BADGE_DIR", temp_badges_dir):
            # Note: Actual filename sanitization might be needed in production
            result = save_image(mock_image_buffer, "badge_test-123_v2.png")
            filepath = os.path.join(temp_badges_dir, "badge_test-123_v2.png")
            assert os.path.exists(filepath)

    def test_save_image_overwrites_existing_file(self, temp_badges_dir):
        """Test that save_image overwrites existing files with same name."""
        filename = "overwrite_test.png"
        filepath = os.path.join(temp_badges_dir, filename)
        
        # Create initial file
        with open(filepath, "wb") as f:
            f.write(b"old content")
        
        # Save new content
        new_buffer = BytesIO(b"new content data")
        with patch("services.badges.services.img_service.BADGE_DIR", temp_badges_dir):
            save_image(new_buffer, filename)
        
        # Verify new content
        with open(filepath, "rb") as f:
            content = f.read()
        assert content == b"new content data"

    def test_save_image_handles_large_files(self, temp_badges_dir):
        """Test saving large image files."""
        large_buffer = BytesIO()
        # Create 5MB buffer
        large_buffer.write(b"x" * (5 * 1024 * 1024))
        large_buffer.seek(0)
        
        with patch("services.badges.services.img_service.BADGE_DIR", temp_badges_dir):
            result = save_image(large_buffer, "large_badge.png")
            
            filepath = os.path.join(temp_badges_dir, "large_badge.png")
            assert os.path.exists(filepath)
            assert os.path.getsize(filepath) == 5 * 1024 * 1024

    def test_save_image_with_empty_buffer(self, temp_badges_dir):
        """Test saving an empty buffer."""
        empty_buffer = BytesIO()
        
        with patch("services.badges.services.img_service.BADGE_DIR", temp_badges_dir):
            result = save_image(empty_buffer, "empty.png")
            
            filepath = os.path.join(temp_badges_dir, "empty.png")
            assert os.path.exists(filepath)
            assert os.path.getsize(filepath) == 0
