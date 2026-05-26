from fastapi import APIRouter

from app.routers.v1 import (
    admin,
    auth,
    badges,
    contact,
    health,
    newsletter,
    platform_templates,
    profile,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(profile.router, prefix="/profile", tags=["profile"])
api_router.include_router(contact.router, prefix="/contact", tags=["contact"])
api_router.include_router(newsletter.router, prefix="/newsletter", tags=["newsletter"])

api_router.include_router(
    platform_templates.router,
    prefix="/templates/platform",
    tags=["platform-templates"],
)
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(badges.router, prefix="/badges", tags=["badges"])
