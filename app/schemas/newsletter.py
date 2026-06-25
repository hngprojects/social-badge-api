from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class NewsletterSubscribeRequest(BaseModel):
    """Data transfer object representing a request to subscribe a new email address to
    the newsletter, validating that the input is a properly formatted email address."""

    email: EmailStr = Field(..., description="Email address to subscribe.")


class NewsletterUnsubscribeRequest(BaseModel):
    """Data transfer object representing a request to unsubscribe from the newsletter,
    requiring a unique unsubscribe token sent in the newsletter emails."""

    token: str = Field(
        ..., description=("Unsubscribe token from the confirmation email.")
    )


class NewsletterSubscribeResponse(BaseModel):
    """Data transfer object representing a successful newsletter subscription,
    confirming the subscribed email address and the exact timestamp of subscription."""

    email: str
    subscribed_at: datetime
