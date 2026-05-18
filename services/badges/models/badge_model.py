from datetime import datetime, timezone
import uuid

from services.badges.enums.job_status import JobStatus
from sqlalchemy import Column, String, DateTime, Text, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID

from services.badges.db.base import Base


class BadgeGenerationJob(Base):
    __tablename__ = "badge_generation_jobs"
    __table_args__ = {"extend_existing": True}

    job_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id = Column(String, nullable=False, index=True)
    participant_name = Column(String(200), nullable=False)
    participant_photo_url = Column(Text, nullable=False)
    status = Column(
        SQLEnum(JobStatus),
        nullable=False,
        default=JobStatus.QUEUED
    )
    badge_image_url = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)