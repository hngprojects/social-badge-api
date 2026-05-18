import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI
from unittest.mock import patch, MagicMock
import uuid

from services.badges.enums.job_status import JobStatus
from services.badges.routes.badges import router


# Create a test FastAPI app with the badges router
def create_test_app():
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client():
    """Provide TestClient for route testing."""
    app = create_test_app()
    return TestClient(app)


class TestBadgeRoutes:
    """Test badge generation routes."""

    @patch("services.badges.routes.badges.SessionLocal")
    @patch("services.badges.routes.badges.badge_queue")
    def test_generate_badge_creates_job(self, mock_queue, mock_session_factory, client):
        """Test that generate_badge endpoint creates and saves a job."""
        job_id = uuid.uuid4()
        mock_db = MagicMock()
        mock_session_factory.return_value = mock_db
        mock_queue.enqueue = MagicMock()
        
        # Mock the job object that will be added/committed/refreshed
        def refresh_side_effect(job):
            job.job_id = job_id
            job.status = JobStatus.QUEUED
        
        mock_db.refresh.side_effect = refresh_side_effect
        
        payload = {
            "template_id": "template_001",
            "participant_name": "John Doe",
            "photo_url": "https://example.com/photo.jpg"
        }
        
        # Call the route via TestClient
        response = client.post("/badges/generate", json=payload)
        
        # Verify HTTP response
        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data
        assert "status" in data
        assert data["status"] == "queued"
        
        # Verify mock interactions
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()
        mock_db.close.assert_called_once()

    @patch("services.badges.routes.badges.SessionLocal")
    @patch("services.badges.routes.badges.badge_queue")
    def test_generate_badge_enqueues_job(self, mock_queue, mock_session_factory, client):
        """Test that generate_badge enqueues the job for processing."""
        job_id = uuid.uuid4()
        mock_db = MagicMock()
        mock_session_factory.return_value = mock_db
        
        def refresh_side_effect(job):
            job.job_id = job_id
            job.status = JobStatus.QUEUED
        
        mock_db.refresh.side_effect = refresh_side_effect
        
        payload = {
            "template_id": "template_001",
            "participant_name": "Jane Doe",
            "photo_url": "https://example.com/jane.jpg"
        }
        
        response = client.post("/badges/generate", json=payload)
        
        assert response.status_code == 200
        # Verify enqueue was called with the job ID
        mock_queue.enqueue.assert_called_once()
        call_args = mock_queue.enqueue.call_args
        assert str(job_id) in str(call_args)

    @patch("services.badges.routes.badges.SessionLocal")
    @patch("services.badges.routes.badges.badge_queue")
    def test_generate_badge_returns_job_id_and_status(self, mock_queue, mock_session_factory, client):
        """Test that generate_badge returns job_id and status in response."""
        job_id = uuid.uuid4()
        mock_db = MagicMock()
        mock_session_factory.return_value = mock_db
        
        def refresh_side_effect(job):
            job.job_id = job_id
            job.status = JobStatus.QUEUED
        
        mock_db.refresh.side_effect = refresh_side_effect
        
        payload = {
            "template_id": "cert_001",
            "participant_name": "Alice Smith",
            "photo_url": "https://example.com/alice.jpg"
        }
        
        response = client.post("/badges/generate", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data
        assert "status" in data
        assert data["status"] == "queued"
        assert len(data["job_id"]) > 0

    @patch("services.badges.routes.badges.SessionLocal")
    def test_get_job_returns_job_details(self, mock_session_factory, client):
        """Test that get_job returns complete job details."""
        job_id = uuid.uuid4()
        mock_db = MagicMock()
        mock_session_factory.return_value = mock_db
        
        # Mock the job object returned from query
        job = MagicMock()
        job.job_id = job_id
        job.status = JobStatus.COMPLETED
        job.badge_image_url = "/badges/badge_123.png"
        job.error_message = None
        
        mock_db.query.return_value.filter.return_value.first.return_value = job
        
        response = client.get(f"/badges/jobs/{str(job_id)}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == str(job_id)
        assert data["status"] == "completed"
        assert "/badges/badge_123.png" in data["badge_image_url"]
        
        # Verify query was called with correct filter
        mock_db.query.assert_called_once()
        mock_db.close.assert_called_once()

    @patch("services.badges.routes.badges.SessionLocal")
    def test_get_job_not_found_returns_error(self, mock_session_factory, client):
        """Test that get_job returns error for non-existent job."""
        mock_db = MagicMock()
        mock_session_factory.return_value = mock_db
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        job_id = uuid.uuid4()
        response = client.get(f"/badges/jobs/{str(job_id)}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["error"] == "not found"
        mock_db.close.assert_called_once()

    @patch("services.badges.routes.badges.SessionLocal")
    def test_get_job_with_failed_status(self, mock_session_factory, client):
        """Test get_job with failed status includes error message."""
        job_id = uuid.uuid4()
        mock_db = MagicMock()
        mock_session_factory.return_value = mock_db
        
        job = MagicMock()
        job.job_id = job_id
        job.status = JobStatus.FAILED
        job.badge_image_url = None
        job.error_message = "Failed to fetch profile image"
        
        mock_db.query.return_value.filter.return_value.first.return_value = job
        
        response = client.get(f"/badges/jobs/{str(job_id)}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert data["error_message"] == "Failed to fetch profile image"

    def test_badge_router_exists(self):
        """Test that badge router is defined."""
        assert router is not None
        assert hasattr(router, "routes")

    def test_badge_routes_count(self):
        """Test that router has expected routes."""
        # The router should have at least 2 routes (generate and get_job)
        assert len(router.routes) >= 2

    def test_generate_badge_route_is_post(self):
        """Test that generate badge route uses POST method."""
        post_routes = [r for r in router.routes if "POST" in str(r.methods)]
        assert len(post_routes) > 0

    def test_get_job_route_is_get(self):
        """Test that get job route uses GET method."""
        get_routes = [r for r in router.routes if "GET" in str(r.methods)]
        assert len(get_routes) > 0


class TestBadgeRoutesErrorHandling:
    """Test error handling in badge routes."""

    @pytest.fixture
    def client(self):
        """Provide TestClient for error handling tests."""
        app = create_test_app()
        return TestClient(app)

    def test_generate_badge_with_invalid_payload(self, client):
        """Test generate_badge with invalid request payload."""
        payload = {
            "template_id": "template_001"
            # Missing participant_name and photo_url
        }
        
        # Pydantic validation should catch this and return 422
        response = client.post("/badges/generate", json=payload)
        assert response.status_code == 422  # Unprocessable Entity

    @patch("services.badges.routes.badges.SessionLocal")
    @patch("services.badges.routes.badges.badge_queue")
    def test_generate_badge_closes_db_session(self, mock_queue, mock_session_factory, client):
        """Test that generate_badge properly closes database session."""
        mock_db = MagicMock()
        mock_session_factory.return_value = mock_db
        
        def refresh_side_effect(job):
            job.job_id = uuid.uuid4()
            job.status = JobStatus.QUEUED
        
        mock_db.refresh.side_effect = refresh_side_effect
        
        payload = {
            "template_id": "template_001",
            "participant_name": "Test User",
            "photo_url": "https://example.com/photo.jpg"
        }
        
        response = client.post("/badges/generate", json=payload)
        
        assert response.status_code == 200
        # Verify db.close() was called
        mock_db.close.assert_called_once()

    @patch("services.badges.routes.badges.SessionLocal")
    def test_get_job_database_query_filters_by_id(self, mock_session_factory, client):
        """Test that get_job queries database with correct job_id filter."""
        job_id = uuid.uuid4()
        mock_db = MagicMock()
        mock_session_factory.return_value = mock_db
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        response = client.get(f"/badges/jobs/{str(job_id)}")
        
        # Verify query was called
        mock_db.query.assert_called_once()
        # Verify filter was called (for job_id matching)
        mock_db.query.return_value.filter.assert_called_once()
        mock_db.close.assert_called_once()


class TestBadgeRoutesIntegration:
    """Integration tests for badge routes."""

    @pytest.fixture
    def client(self):
        """Provide TestClient for integration tests."""
        app = create_test_app()
        return TestClient(app)

    @patch("services.badges.routes.badges.SessionLocal")
    @patch("services.badges.routes.badges.badge_queue")
    def test_generate_then_get_job(self, mock_queue, mock_session_factory, client):
        """Test complete flow: generate badge then check status."""
        job_id = uuid.uuid4()
        mock_db = MagicMock()
        mock_session_factory.return_value = mock_db
        
        # Setup refresh for generate_badge
        def refresh_side_effect(job):
            job.job_id = job_id
            job.status = JobStatus.QUEUED
        
        mock_db.refresh.side_effect = refresh_side_effect
        
        # Generate badge
        generate_payload = {
            "template_id": "template_001",
            "participant_name": "Test User",
            "photo_url": "https://example.com/photo.jpg"
        }
        
        generate_response = client.post("/badges/generate", json=generate_payload)
        assert generate_response.status_code == 200
        generated_job_id = generate_response.json()["job_id"]
        
        # Setup query for get_job
        job = MagicMock()
        job.job_id = uuid.UUID(generated_job_id)
        job.status = JobStatus.QUEUED
        job.badge_image_url = None
        job.error_message = None
        
        mock_db.query.return_value.filter.return_value.first.return_value = job
        
        # Get job status
        get_response = client.get(f"/badges/jobs/{generated_job_id}")
        assert get_response.status_code == 200
        job_data = get_response.json()
        assert job_data["status"] == "queued"

    @patch("services.badges.routes.badges.SessionLocal")
    @patch("services.badges.routes.badges.badge_queue")
    def test_generate_multiple_badges_different_users(self, mock_queue, mock_session_factory, client):
        """Test handling multiple concurrent badge generation requests."""
        mock_db = MagicMock()
        mock_session_factory.return_value = mock_db
        
        job_ids = [uuid.uuid4() for _ in range(3)]
        
        generated_ids = []
        for i, job_id in enumerate(job_ids):
            def refresh_side_effect(job, jid=job_id):
                job.job_id = jid
                job.status = JobStatus.QUEUED
            
            mock_db.refresh.side_effect = refresh_side_effect
            
            payload = {
                "template_id": f"template_{i:03d}",
                "participant_name": f"User {i}",
                "photo_url": f"https://example.com/user{i}.jpg"
            }
            
            response = client.post("/badges/generate", json=payload)
            assert response.status_code == 200
            generated_ids.append(response.json()["job_id"])
        
        # Verify all generated IDs are unique
        assert len(set(generated_ids)) == len(generated_ids)
        assert len(generated_ids) == 3
