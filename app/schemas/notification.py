from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotificationPreferencesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    email_template_published: bool
    email_new_signin: bool
    updated_at: datetime | None = None


class UpdateNotificationPreferencesRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    email_template_published: bool | None = None
    email_new_signin: bool | None = None
