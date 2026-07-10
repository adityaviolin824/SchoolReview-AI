"""FastAPI application factory for the SchoolReview AI backend."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from school_safety_validator.inspection_runtime_settings import BACKEND_ROOT

from .inspection_api_routes import cleanup_old_api_runs, router


LOCAL_FRONTEND_ORIGINS = ["http://127.0.0.1:5173", "http://localhost:5173"]
FRONTEND_DIST_DIR = BACKEND_ROOT / "static" / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Run lightweight local API startup maintenance."""

    cleanup_old_api_runs()
    yield


def create_app() -> FastAPI:
    """Create the testable FastAPI application."""

    app = FastAPI(
        title="SchoolReview AI API",
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
    mount_frontend(app, FRONTEND_DIST_DIR)
    return app


def mount_frontend(app: FastAPI, frontend_dist_dir: Path) -> None:
    """Serve the compiled Vite frontend when it is bundled with the backend."""

    if not (frontend_dist_dir / "index.html").is_file():
        return
    app.mount("/", StaticFiles(directory=frontend_dist_dir, html=True), name="frontend")


app = create_app()
