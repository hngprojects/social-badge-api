from typing import Literal
from uuid import UUID

from pydantic import BaseModel, model_validator


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

    @model_validator(mode="after")
    def _validate_status_fields(self) -> "BadgeJobStatusData":
        if self.job_status == "complete" and self.badge is None:
            raise ValueError("badge must be set when job_status is 'complete'")
        if self.job_status == "failed" and self.error is None:
            raise ValueError("error must be set when job_status is 'failed'")
        if self.job_status in {"pending", "processing"}:
            if self.badge is not None:
                raise ValueError(
                    f"badge must be None when job_status is '{self.job_status}'"
                )
            if self.error is not None:
                raise ValueError(
                    f"error must be None when job_status is '{self.job_status}'"
                )
        return self
