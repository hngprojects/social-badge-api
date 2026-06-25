from typing import Literal

from pydantic import BaseModel


class SuccessResponse[DataT](BaseModel):
    """Generic schema representing a successful API response, enclosing a success
    status, a descriptive message, and an optional custom data payload of type DataT."""

    status: Literal["success"] = "success"
    message: str
    data: DataT | None = None


class ErrorResponse(BaseModel):
    """Schema representing an unsuccessful API response, containing an error status flag
    and a descriptive message explaining the reason for the failure."""

    status: Literal["error"] = "error"
    message: str
