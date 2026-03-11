"""FastAPI application factory for WanGame Eval.

Creates the app, mounts routers, initializes database on startup,
and serves static frontend files.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.server.database import Database
from app.server.routes import settings, videos, data_ops, results

logger = logging.getLogger("wangame.server")


def create_app(
    db_path: str = "eval.db",
    static_dir: str | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        db_path: Path to SQLite database file. Use ":memory:" for tests.
        static_dir: Path to static frontend files. None to skip mounting.
    """
    app = FastAPI(
        title="WanGame Eval API",
        description="Evaluation pipeline for the WanGame 1.3B World Model",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS for local dev
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Database
    db = Database(db_path)
    app.state.db = db

    @app.on_event("startup")
    async def startup():
        db.init()
        logger.info("WanGame Eval API started (db=%s)", db_path)

    # API routers
    app.include_router(settings.router)
    app.include_router(videos.router)
    app.include_router(data_ops.router)
    app.include_router(results.router)

    # Static files (PWA frontend) — mount last so API routes take priority
    if static_dir:
        static_path = Path(static_dir)
        if static_path.exists():
            app.mount("/", StaticFiles(directory=str(static_path), html=True), name="static")
            logger.info("Serving static files from %s", static_path)

    return app
