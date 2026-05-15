from pydantic import BaseModel


class SuccessResponse[DataT](BaseModel):
    status: str = "success"
    message: str
    data: DataT | None = None


class ErrorResponse(BaseModel):
    status: str = "error"
    message: str
