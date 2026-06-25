from fastapi import APIRouter
from sqlalchemy import text

from app.dependencies import DBSession

router = APIRouter()


@router.get("/health")
async def health(db: DBSession) -> dict[str, str]:
    """
    Performs a system health check to verify database connectivity.

    Validates that both the application server and the database session are fully functional by executing a minimal test query (`SELECT 1`). This is a public endpoint that requires no active authentication token or role, and it is not rate-limited to allow continuous monitoring checks.
    """
    await db.execute(text("SELECT 1"))
    return {"status": "ok"}
