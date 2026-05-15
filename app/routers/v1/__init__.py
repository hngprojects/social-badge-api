from fastapi import APIRouter

from app.routers.v1 import auth, contact, health, templates

api_router = APIRouter()
<<<<<<< HEAD
=======
api_router.include_router(health.router)
from fastapi import APIRouter

from app.routers.v1 import auth, contact, health, templates

api_router = APIRouter()
>>>>>>> ac4bcfd5d158a6e82dca3f81d5033be11ce6c8c1
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(contact.router, prefix="/contact", tags=["contact"])
api_router.include_router(templates.router, prefix="/templates", tags=["templates"])
