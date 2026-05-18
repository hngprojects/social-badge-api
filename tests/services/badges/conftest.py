import pytest
import uuid
from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock, patch
from io import BytesIO

from services.badges.models.badge_model import BadgeGenerationJob
from services.badges.enums.job_status import JobStatus

# Try to import PIL for image creation
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    Image = None


@pytest.fixture
def mock_db_session():
    """Mock SQLAlchemy session for database operations."""
    session = MagicMock()
    return session


@pytest.fixture
def mock_redis_connection():
    """Mock Redis connection."""
    redis = MagicMock()
    redis.ping.return_value = True
    return redis


@pytest.fixture
def mock_queue():
    """Mock RQ Queue."""
    queue = MagicMock()
    queue.enqueue = MagicMock(return_value=MagicMock(id="test-job-id"))
    return queue


@pytest.fixture
def sample_job():
    """Create a sample BadgeGenerationJob for testing."""
    return BadgeGenerationJob(
        job_id=uuid.uuid4(),
        template_id="template_001",
        participant_name="John Doe",
        participant_photo_url="https://example.com/profile.jpg",
        status=JobStatus.QUEUED,
        badge_image_url=None,
        error_message=None,
        created_at=datetime.now(timezone.utc),
        completed_at=None
    )


@pytest.fixture
def sample_job_completed():
    """Create a completed sample badge job."""
    job = BadgeGenerationJob(
        job_id=uuid.uuid4(),
        template_id="template_001",
        participant_name="Jane Smith",
        participant_photo_url="https://example.com/profile2.jpg",
        status=JobStatus.COMPLETED,
        badge_image_url="/badges/badge_12345.png",
        error_message=None,
        created_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc)
    )
    return job


@pytest.fixture
def sample_job_failed():
    """Create a failed sample badge job."""
    return BadgeGenerationJob(
        job_id=uuid.uuid4(),
        template_id="template_001",
        participant_name="Bob Johnson",
        participant_photo_url="https://example.com/profile3.jpg",
        status=JobStatus.FAILED,
        badge_image_url=None,
        error_message="Failed to fetch profile image",
        created_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc)
    )


@pytest.fixture
def mock_image_buffer():
    """Create a mock image buffer (BytesIO)."""
    buffer = BytesIO()
    # Simulate a minimal PNG header
    buffer.write(b'\x89PNG\r\n\x1a\n' + b'\x00' * 100)
    buffer.seek(0)
    return buffer


@pytest.fixture
def mock_httpx_response():
    """Mock successful HTTPX response with image data."""
    response = MagicMock()
    response.status_code = 200
    response.content = b'\x89PNG\r\n\x1a\n' + b'\x00' * 1000
    return response


@pytest.fixture
def badge_generate_request_payload():
    """Sample badge generation request payload."""
    return {
        "template_id": "template_001",
        "participant_name": "Alice Wonder",
        "photo_url": "https://example.com/alice.jpg"
    }


@pytest.fixture
def temp_badges_dir(tmp_path):
    """Create temporary badges directory for file I/O tests."""
    badges_dir = tmp_path / "badges"
    badges_dir.mkdir()
    return str(badges_dir)


# Add a fixture for PIL Image if available
if PIL_AVAILABLE:
    @pytest.fixture
    def sample_pil_image():
        """Create a sample PIL Image for testing."""
        img = Image.new("RGB", (100, 100), color="blue")
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        return img

    @pytest.fixture
    def sample_png_bytes():
        """Create a minimal valid PNG image bytes."""
        img = Image.new("RGB", (100, 100), color="blue")
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer.getvalue()
