from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class PhotoUploadData(BaseModel):
    photo_public_id: str


class BadgeJobEnqueueData(BaseModel):
    job_id: str


class BadgeJobResultData(BaseModel):
    badge_id: UUID
    badge_image_url: str
    participant_name: str


class BadgeJobStatusData(BaseModel):
    job_id: str
    job_status: Literal["pending", "processing", "complete", "failed"]
    badge: BadgeJobResultData | None = None
    error: str | None = None
