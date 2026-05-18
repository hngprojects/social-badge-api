from pydantic import BaseModel, HttpUrl


class BadgeGenerateRequest(BaseModel):
    template_id: str
    participant_name: str
    photo_url: HttpUrl


class BadgeGenerateResponse(BaseModel):
    job_id: str
    status: str