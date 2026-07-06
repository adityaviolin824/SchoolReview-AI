"""FastAPI application factory for the School Safety Validator backend."""

from __future__ import annotations

from fastapi import FastAPI

from .inspection_api_routes import router


def create_app() -> FastAPI:
    """Create the testable FastAPI application."""

    app = FastAPI(
        title="School Safety Validator API",
        version="0.1.0",
        description="Minimal API for staging school inspection images and running the validator pipeline.",
    )
    app.include_router(router)
    return app


app = create_app()
