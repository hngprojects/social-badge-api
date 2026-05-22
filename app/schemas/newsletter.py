from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class NewsletterSubscribeRequest(BaseModel):
    email: EmailStr = Field(..., description="Email address to subscribe.")


class NewsletterUnsubscribeRequest(BaseModel):
    token: str = Field(
        ..., description=("Unsubscribe token from the confirmation email.")
    )


class NewsletterSubscribeResponse(BaseModel):
    email: str
    subscribed_at: datetime
