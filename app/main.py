import logging

from fastapi import FastAPI, Request

from app.core.config import settings
from app.routers.v1 import api_router

logger = logging.getLogger(__name__)


app = FastAPI(title=settings.PROJECT_NAME)
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/")
def root(request: Request) -> dict[str, str]:
    return {"message": f"{settings.PROJECT_NAME} is running"}
