import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from services.badges.routes.badges import router as badge_router

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(badge_router)

# create badges directory if it doesn't exist
os.makedirs("badges", exist_ok=True)

# serve local badge files
app.mount("/badges", StaticFiles(directory="badges"), name="badges")