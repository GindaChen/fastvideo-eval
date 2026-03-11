"""Settings API — WandB API key entry and server configuration.

Endpoints:
  GET  /api/settings       — current settings (api_key masked)
  PUT  /api/settings       — update settings
  POST /api/settings/test  — test WandB connection
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.server.auth import get_db, verify_token
from app.server.storage import Storage

router = APIRouter(prefix="/api/settings", tags=["settings"])


# --------------------------------------------------------------------------- #
# Request / Response models
# --------------------------------------------------------------------------- #

class SettingsResponse(BaseModel):
    wandb_api_key: str  # Masked
    wandb_entity: str
    wandb_project: str
    default_run_id: str
    auth_token_set: bool


class SettingsUpdate(BaseModel):
    wandb_api_key: Optional[str] = None
    wandb_entity: Optional[str] = None
    wandb_project: Optional[str] = None
    default_run_id: Optional[str] = None
    auth_token: Optional[str] = None


class ConnectionTestRequest(BaseModel):
    wandb_api_key: Optional[str] = None  # If empty, use stored key


class ConnectionTestResponse(BaseModel):
    success: bool
    message: str
    runs_found: int = 0


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #

@router.get("", response_model=SettingsResponse)
async def get_settings(db: Storage = Depends(get_db)):
    """Return current settings with API key masked."""
    settings = db.get_all_settings()
    api_key = settings.get("wandb_api_key", "")

    return SettingsResponse(
        wandb_api_key=_mask_key(api_key),
        wandb_entity=settings.get("wandb_entity", ""),
        wandb_project=settings.get("wandb_project", ""),
        default_run_id=settings.get("default_run_id", ""),
        auth_token_set=bool(settings.get("auth_token", "")),
    )


@router.put("", response_model=SettingsResponse)
async def update_settings(
    body: SettingsUpdate,
    db: Storage = Depends(get_db),
):
    """Update server settings."""
    if body.wandb_api_key is not None:
        db.set_setting("wandb_api_key", body.wandb_api_key)
    if body.wandb_entity is not None:
        db.set_setting("wandb_entity", body.wandb_entity)
    if body.wandb_project is not None:
        db.set_setting("wandb_project", body.wandb_project)
    if body.default_run_id is not None:
        db.set_setting("default_run_id", body.default_run_id)
    if body.auth_token is not None:
        db.set_setting("auth_token", body.auth_token)

    return await get_settings(db)


@router.post("/test", response_model=ConnectionTestResponse)
async def test_connection(
    body: ConnectionTestRequest,
    db: Storage = Depends(get_db),
):
    """Test WandB connection with provided or stored credentials."""
    api_key = body.wandb_api_key or db.get_setting("wandb_api_key") or ""
    entity = db.get_setting("wandb_entity") or ""
    project = db.get_setting("wandb_project") or ""
    run_id = db.get_setting("default_run_id") or ""

    if not api_key:
        return ConnectionTestResponse(
            success=False,
            message="No API key provided or stored. Set a key first.",
        )

    try:
        import wandb
        api = wandb.Api(api_key=api_key)
        # Fast check: just validate the key works
        viewer = api.viewer
        msg = f"Authenticated as {viewer}"

        # If we have a run configured, verify it exists (fast single fetch)
        if entity and project and run_id:
            try:
                run = api.run(f"{entity}/{project}/{run_id}")
                msg += f" • Run '{run.name}' ({run.state})"
            except Exception:
                msg += f" • ⚠ Run {run_id} not found in {entity}/{project}"

        return ConnectionTestResponse(success=True, message=msg, runs_found=1)
    except Exception as exc:
        return ConnectionTestResponse(
            success=False,
            message=f"Connection failed: {exc}",
        )


def _mask_key(key: str) -> str:
    """Mask API key: show first 4 and last 4 chars."""
    if len(key) <= 8:
        return "●" * len(key)
    return key[:4] + "●" * (len(key) - 8) + key[-4:]
