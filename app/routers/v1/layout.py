from fastapi import APIRouter, Query, status

from app.dependencies import CurrentUser, DBSession
from app.schemas.layout import PaginatedLayouts
from app.schemas.response import SuccessResponse
from app.services.layout import list_layouts

router = APIRouter(prefix="/layouts", tags=["Layouts"])


@router.get(
    "",
    response_model=SuccessResponse[PaginatedLayouts],
    status_code=status.HTTP_200_OK,
)
async def get_layouts(
    session: DBSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Items per page"),
) -> SuccessResponse[PaginatedLayouts]:
    layouts = await list_layouts(session, page, limit)
    return SuccessResponse(message="Layouts retrieved successfully", data=layouts)
    