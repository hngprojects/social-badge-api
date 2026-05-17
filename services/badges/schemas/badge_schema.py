from pydantic import BaseModel


class BadgeGenerateRequest(BaseModel):
    template_id: str
    participant_name: str
    photo_url: str


class BadgeGenerateResponse(BaseModel):
    job_id: str
    status: str