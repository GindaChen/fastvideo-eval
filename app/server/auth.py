"""Simple Bearer token authentication (SPEC §12.3).

v1: shared token, no role-based access. Optional bypass for local dev.
"""

from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.server.database import Database

_bearer = HTTPBearer(auto_error=False)


def get_db(request: Request) -> Database:
    """FastAPI dependency: get the Database instance from app state."""
    return request.app.state.db


async def verify_token(
    request: Request,
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> str:
    """Validate Bearer token. Returns evaluator name or 'anonymous'.

    If no auth_token is configured in settings, auth is bypassed
    (local dev mode).
    """
    db: Database = request.app.state.db
    configured_token = db.get_setting("auth_token")

    # No token configured → bypass auth (local dev)
    if not configured_token:
        return "anonymous"

    if creds is None or creds.credentials != configured_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing auth token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Use evaluator name from header if provided, else "evaluator"
    evaluator = request.headers.get("X-Evaluator", "evaluator")
    return evaluator
