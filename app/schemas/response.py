from typing import Literal

from pydantic import BaseModel


class SuccessResponse[DataT](BaseModel):
    status: Literal["success"] = "success"
    message: str
    data: DataT | None = None


class ErrorResponse(BaseModel):
    status: Literal["error"] = "error"
    message: str
