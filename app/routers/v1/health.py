from fastapi import APIRouter
from sqlalchemy import text

from app.dependencies import DBSession

router = APIRouter()


@router.get("/health")
async def health(db: DBSession) -> dict[str, str]:
    await db.execute(text("SELECT 1"))
    return {"status": "ok"}
