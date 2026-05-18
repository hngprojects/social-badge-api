import pytest
from pydantic import ValidationError

from services.badges.schemas.badge_schema import BadgeGenerateRequest, BadgeGenerateResponse


class TestBadgeGenerateRequest:
    """Test BadgeGenerateRequest schema validation."""

    def test_valid_request(self):
        """Test valid badge generation request."""
        payload = {
            "template_id": "template_001",
            "participant_name": "John Doe",
            "photo_url": "https://example.com/photo.jpg"
        }
        request = BadgeGenerateRequest(**payload)
        assert request.template_id == "template_001"
        assert request.participant_name == "John Doe"
        assert str(request.photo_url) == "https://example.com/photo.jpg"

    def test_missing_template_id(self):
        """Test validation fails when template_id is missing."""
        payload = {
            "participant_name": "John Doe",
            "photo_url": "https://example.com/photo.jpg"
        }
        with pytest.raises(ValidationError) as exc_info:
            BadgeGenerateRequest(**payload)
        assert "template_id" in str(exc_info.value)

    def test_missing_participant_name(self):
        """Test validation fails when participant_name is missing."""
        payload = {
            "template_id": "template_001",
            "photo_url": "https://example.com/photo.jpg"
        }
        with pytest.raises(ValidationError) as exc_info:
            BadgeGenerateRequest(**payload)
        assert "participant_name" in str(exc_info.value)

    def test_missing_photo_url(self):
        """Test validation fails when photo_url is missing."""
        payload = {
            "template_id": "template_001",
            "participant_name": "John Doe"
        }
        with pytest.raises(ValidationError) as exc_info:
            BadgeGenerateRequest(**payload)
        assert "photo_url" in str(exc_info.value)

    def test_empty_template_id(self):
        """Test validation with empty template_id."""
        payload = {
            "template_id": "",
            "participant_name": "John Doe",
            "photo_url": "https://example.com/photo.jpg"
        }
        # Pydantic allows empty strings by default; adjust if stricter validation needed
        request = BadgeGenerateRequest(**payload)
        assert request.template_id == ""

    def test_very_long_participant_name(self):
        """Test with very long participant name."""
        payload = {
            "template_id": "template_001",
            "participant_name": "A" * 500,  # Very long name
            "photo_url": "https://example.com/photo.jpg"
        }
        request = BadgeGenerateRequest(**payload)
        assert len(request.participant_name) == 500

    def test_invalid_url_format(self):
        """Test that invalid URL format is rejected by schema validation."""
        payload = {
            "template_id": "template_001",
            "participant_name": "John Doe",
            "photo_url": "not-a-valid-url"
        }
        # Schema now enforces URL validation
        with pytest.raises(ValidationError) as exc_info:
            BadgeGenerateRequest(**payload)
        assert "photo_url" in str(exc_info.value)

    def test_extra_fields_ignored(self):
        """Test that extra fields are ignored by default."""
        payload = {
            "template_id": "template_001",
            "participant_name": "John Doe",
            "photo_url": "https://example.com/photo.jpg",
            "extra_field": "should be ignored"
        }
        request = BadgeGenerateRequest(**payload)
        assert not hasattr(request, "extra_field")


class TestBadgeGenerateResponse:
    """Test BadgeGenerateResponse schema."""

    def test_valid_response(self):
        """Test valid badge generation response."""
        response_data = {
            "job_id": "550e8400-e29b-41d4-a716-446655440000",
            "status": "queued"
        }
        response = BadgeGenerateResponse(**response_data)
        assert response.job_id == "550e8400-e29b-41d4-a716-446655440000"
        assert response.status == "queued"

    def test_missing_job_id(self):
        """Test validation fails when job_id is missing."""
        response_data = {
            "status": "queued"
        }
        with pytest.raises(ValidationError):
            BadgeGenerateResponse(**response_data)

    def test_missing_status(self):
        """Test validation fails when status is missing."""
        response_data = {
            "job_id": "550e8400-e29b-41d4-a716-446655440000"
        }
        with pytest.raises(ValidationError):
            BadgeGenerateResponse(**response_data)

    def test_all_valid_statuses(self):
        """Test response with all valid status values."""
        valid_statuses = ["queued", "processing", "completed", "failed"]
        for status in valid_statuses:
            response_data = {
                "job_id": "550e8400-e29b-41d4-a716-446655440000",
                "status": status
            }
            response = BadgeGenerateResponse(**response_data)
            assert response.status == status
