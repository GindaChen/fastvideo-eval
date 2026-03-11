"""FastAPI application factory for WanGame Eval.

Creates the app, mounts routers, initializes storage on startup,
and serves static frontend files.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.server.storage import Storage
from app.server.routes import settings, videos, data_ops, results

logger = logging.getLogger("wangame.server")


def create_app(
    data_dir: str = "data",
    static_dir: str | None = None,
    # Legacy compat: accept db_path but ignore it
    db_path: str | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        data_dir: Path to data directory for JSONL/JSON storage.
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

    # Storage (JSONL + JSON files)
    store = Storage(data_dir)
    app.state.db = store  # keep as .db for route handler compat

    @app.on_event("startup")
    async def startup():
        store.init()
        logger.info("WanGame Eval API started (data_dir=%s)", data_dir)

    # API routers
    app.include_router(settings.router)
    app.include_router(videos.router)
    app.include_router(data_ops.router)
    app.include_router(results.router)

    # Static files (PWA frontend) — mount last so API routes take priority
    if static_dir:
        static_path = Path(static_dir)
        if static_path.exists():
            # SPA catch-all: serve index.html for non-API, non-file paths
            # This lets users bookmark /matrix, /video-matrix, etc.
            from fastapi.responses import FileResponse

            page_aliases = {
                "matrix", "video-matrix", "dashboard", "evaluate",
                "review", "results", "settings",
            }

            @app.get("/{path:path}")
            async def spa_fallback(path: str):
                # Only catch known page routes; let everything else fall through
                first_segment = path.split("/")[0] if path else ""
                if first_segment in page_aliases:
                    return FileResponse(str(static_path / "index.html"))
                # For unknown paths, try as static file (handled by mount below)
                # or return 404
                file_path = static_path / path
                if file_path.exists() and file_path.is_file():
                    return FileResponse(str(file_path))
                return FileResponse(str(static_path / "index.html"))

            app.mount("/", StaticFiles(directory=str(static_path), html=True), name="static")
            logger.info("Serving static files from %s", static_path)

    return app
