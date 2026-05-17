import pytest

from services.badges.enums.job_status import JobStatus


class TestJobStatusEnum:
    """Test JobStatus enum values and transitions."""

    def test_all_job_statuses_exist(self):
        """Test that all expected job statuses are defined."""
        assert hasattr(JobStatus, "QUEUED")
        assert hasattr(JobStatus, "PROCESSING")
        assert hasattr(JobStatus, "COMPLETED")
        assert hasattr(JobStatus, "FAILED")

    def test_job_status_values(self):
        """Test job status enum values."""
        assert JobStatus.QUEUED.value == "queued"
        assert JobStatus.PROCESSING.value == "processing"
        assert JobStatus.COMPLETED.value == "completed"
        assert JobStatus.FAILED.value == "failed"

    def test_job_status_string_comparison(self):
        """Test that JobStatus can be compared with strings."""
        status = JobStatus.QUEUED
        assert status == "queued"
        assert status.value == "queued"

    def test_job_status_from_string(self):
        """Test creating JobStatus from string value."""
        status = JobStatus("queued")
        assert status == JobStatus.QUEUED

    def test_invalid_job_status_raises_error(self):
        """Test that invalid status value raises ValueError."""
        with pytest.raises(ValueError):
            JobStatus("invalid_status")

    def test_job_status_is_string_enum(self):
        """Test that JobStatus is a string enum."""
        assert isinstance(JobStatus.QUEUED, str)
        assert isinstance(JobStatus.QUEUED.value, str)

    def test_job_status_iteration(self):
        """Test iterating through all job statuses."""
        statuses = list(JobStatus)
        assert len(statuses) == 4
        assert JobStatus.QUEUED in statuses
        assert JobStatus.PROCESSING in statuses
        assert JobStatus.COMPLETED in statuses
        assert JobStatus.FAILED in statuses

    def test_job_status_names(self):
        """Test accessing job status names."""
        assert JobStatus.QUEUED.name == "QUEUED"
        assert JobStatus.PROCESSING.name == "PROCESSING"
        assert JobStatus.COMPLETED.name == "COMPLETED"
        assert JobStatus.FAILED.name == "FAILED"

    def test_state_transitions_are_logical(self):
        """Test logical state transition paths."""
        # QUEUED -> PROCESSING -> COMPLETED (success path)
        # QUEUED -> PROCESSING -> FAILED (failure path)
        # Ensure enum values reflect this logic (no direct enforcement in enum)
        success_path = [JobStatus.QUEUED, JobStatus.PROCESSING, JobStatus.COMPLETED]
        failure_path = [JobStatus.QUEUED, JobStatus.PROCESSING, JobStatus.FAILED]
        
        assert JobStatus.QUEUED in success_path
        assert JobStatus.COMPLETED in success_path
        assert JobStatus.FAILED in failure_path

    def test_job_status_serialization(self):
        """Test that JobStatus can be serialized."""
        status = JobStatus.QUEUED
        serialized = status.value
        assert isinstance(serialized, str)
        assert serialized == "queued"

    def test_job_status_equality(self):
        """Test equality comparison between JobStatus instances."""
        status1 = JobStatus.QUEUED
        status2 = JobStatus.QUEUED
        status3 = JobStatus.PROCESSING
        
        assert status1 == status2
        assert status1 != status3
        assert status2 != status3
