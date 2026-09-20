from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import engine

from app.api.v1 import api_router
from app.config import settings
from app.db import Base, init_db
from app.errors import (
    AppError,
    NeedsClarification,
    app_error_handler,
    clarification_handler,
    request_validation_handler,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Voice-First Business Assistant Backend",
    description="Source of truth for structured business events.",
    version="0.1.0",
    lifespan=lifespan,
)

_cors_origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
_allow_all_origins = _cors_origins == ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if _allow_all_origins else _cors_origins,
    allow_credentials=not _allow_all_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(NeedsClarification, clarification_handler)
app.add_exception_handler(RequestValidationError, request_validation_handler)
app.include_router(api_router)



# Include Router
app.include_router(api_router, prefix=settings.API_V1_STR)



@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": "backend-engine",
        "docs": "/docs",
        "health": "/api/v1/health",
    }
