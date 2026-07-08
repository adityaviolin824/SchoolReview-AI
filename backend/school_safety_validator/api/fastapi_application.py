"""FastAPI application factory for the School Safety Validator backend."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .inspection_api_routes import cleanup_old_api_runs, router


LOCAL_FRONTEND_ORIGINS = ["http://127.0.0.1:5173", "http://localhost:5173"]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Run lightweight local API startup maintenance."""

    cleanup_old_api_runs()
    yield


def create_app() -> FastAPI:
    """Create the testable FastAPI application."""

    app = FastAPI(
        title="School Safety Validator API",
        version="0.1.0",
        description="Minimal API for staging school inspection images and running the validator pipeline.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=LOCAL_FRONTEND_ORIGINS,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app


app = create_app()
