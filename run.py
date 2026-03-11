#!/usr/bin/env python3
"""WanGame Eval — Start the server.

Usage:
    python run.py              # Default: localhost:8080
    python run.py --port 9090  # Custom port
    python run.py --dev        # Dev mode with auto-reload
"""

import argparse
import logging

import uvicorn

from app.server.main import create_app


def main():
    parser = argparse.ArgumentParser(description="WanGame Eval Server")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host")
    parser.add_argument("--port", type=int, default=8080, help="Bind port")
    parser.add_argument("--db", default="eval.db", help="SQLite database path")
    parser.add_argument("--static", default="app/frontend/public", help="Static files directory")
    parser.add_argument("--dev", action="store_true", help="Enable auto-reload")
    args = parser.parse_args()

    # Logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)-20s %(levelname)-5s %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.dev:
        # Dev mode: use uvicorn reload (needs string app reference)
        uvicorn.run(
            "app.server.main:create_app",
            factory=True,
            host=args.host,
            port=args.port,
            reload=True,
            log_level="info",
        )
    else:
        app = create_app(db_path=args.db, static_dir=args.static)
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
