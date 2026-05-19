from fastapi import APIRouter

from app.routers.v1 import admin, auth, contact, health, templates

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(contact.router, prefix="/contact", tags=["contact"])
api_router.include_router(templates.router, prefix="/templates", tags=["templates"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
