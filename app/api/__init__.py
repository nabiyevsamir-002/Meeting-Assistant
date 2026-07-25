"""API router-lərinin birləşdirilməsi."""
from fastapi import APIRouter

from app.api import auth, health, ingest, meetings, memory_api

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/api/auth", tags=["auth"])
api_router.include_router(ingest.router, prefix="/api/ingest", tags=["ingest"])
api_router.include_router(meetings.router, prefix="/api/meetings", tags=["meetings"])
api_router.include_router(memory_api.router, prefix="/api/memory", tags=["memory"])
