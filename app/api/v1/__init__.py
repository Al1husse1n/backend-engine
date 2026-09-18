from fastapi import APIRouter

from app.api.v1.events import router as events_router
from app.api.v1.health import router as health_router
from app.api.v1.query import router as query_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router)
api_router.include_router(events_router)
api_router.include_router(query_router)
