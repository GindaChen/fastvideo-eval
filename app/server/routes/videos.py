"""Video proxy and WandB data listing endpoints.

Endpoints:
  GET /api/runs                          — list runs
  GET /api/checkpoints/{run_id}          — list checkpoints for a run
  GET /api/videos/{run_id}/{step}        — list video metadata (captions) for a step
  GET /api/video-proxy/{run_id}/{step}/{index} — download & stream a single video
"""

from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from app.server.auth import get_db
from app.server.storage import Storage
from app.wandb_client.config import WandBConfig
from app.wandb_client.client import WandBClient
from app.wandb_client.models import PromptInfo

logger = logging.getLogger("wangame.video")

router = APIRouter(prefix="/api", tags=["videos"])

# Default video cache directory (overridable via app.state.video_cache_dir)
CACHE_DIR = Path("video_cache")


def _get_cache_dir(request=None) -> Path:
    """Get the video cache directory, checking app state first."""
    if request and hasattr(request.app.state, "video_cache_dir"):
        return Path(request.app.state.video_cache_dir)
    return CACHE_DIR


# --------------------------------------------------------------------------- #
# Response models
# --------------------------------------------------------------------------- #

class RunItem(BaseModel):
    run_id: str
    name: str
    state: str
    created_at: str


class CheckpointItem(BaseModel):
    checkpoint_id: str
    training_step: int
    video_count: int


class VideoItem(BaseModel):
    index: int
    caption: str
    prompt_id: str
    action_label: str
    category: str
    sha256: str
    size_bytes: int
    wandb_path: str
    proxy_url: str  # URL to stream through our server


# --------------------------------------------------------------------------- #
# Client factory
# --------------------------------------------------------------------------- #

def _make_client(db: Storage) -> WandBClient:
    """Create a WandBClient from stored settings.

    Raises HTTPException 400 if no API key is configured — the key is
    stored server-side via PUT /api/settings, NOT passed per-request.
    """
    settings = db.get_all_settings()
    api_key = settings.get("wandb_api_key", "")
    if not api_key:
        logger.error("No WandB API key in config.json — user must set it via Settings page")
        raise HTTPException(
            status_code=400,
            detail="No WandB API key configured. Go to Settings and enter your key first.",
        )
    logger.debug("WandB client: key=%s…%s", api_key[:4], api_key[-4:] if len(api_key) > 8 else "****")
    config = WandBConfig(
        project=settings.get("wandb_project", "wangame_1.3b"),
        entity=settings.get("wandb_entity", "kaiqin_kong_ucsd"),
        api_key=api_key,
        default_run_id=settings.get("default_run_id", "fif3z1z4"),
    )
    return WandBClient(config)


def _cache_path(run_id: str, step: int, index: int, request=None) -> Path:
    """Local cache path for a video file."""
    cache_dir = _get_cache_dir(request)
    return cache_dir / run_id / f"step_{step}" / f"{index:02d}.mp4"


# --------------------------------------------------------------------------- #
# Metadata cache (avoid re-fetching from WandB on every video request)
# --------------------------------------------------------------------------- #

_video_cache: dict[str, tuple[list, float]] = {}  # key → (videos, timestamp)
CACHE_TTL = 600  # 10 minutes


def _get_cached_videos(key: str):
    """Get videos from memory cache if still fresh."""
    if key in _video_cache:
        videos, ts = _video_cache[key]
        if time.time() - ts < CACHE_TTL:
            return videos
    return None


def _set_cached_videos(key: str, videos: list):
    _video_cache[key] = (videos, time.time())


class MatrixInfo(BaseModel):
    """Matrix dimensions for the evaluation grid."""
    run_id: str
    run_name: str
    run_state: str
    validation_interval: int       # steps between validations
    num_prompts: int               # prompts per step
    last_step: int                 # last training step recorded
    steps: list[int]               # all validation steps
    total_videos: int


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #

@router.get("/matrix/{run_id}", response_model=MatrixInfo)
async def get_matrix(run_id: str, db: Storage = Depends(get_db)):
    """Discover the video matrix dimensions from run config (fast, no file scan).

    Uses run.config for validation_steps + validation_num_samples, and
    run.summary._step to compute the full list of validation steps.
    """
    cache_key = f"matrix:{run_id}"
    cached = _get_cached_videos(cache_key)
    if cached:
        return cached

    client = _make_client(db)
    try:
        run = client._retry_api_call(
            lambda: client.api.run(f"{client.project_path}/{run_id}")
        )
        config = dict(run.config)
        summary = dict(run.summary)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"WandB API error: {exc}")

    val_interval = int(config.get("validation_steps", 500))
    num_prompts = int(config.get("validation_num_samples", 32))
    last_step = int(summary.get("_step", 0))
    run_name = config.get("wandb_run_name", run.name or run_id)
    run_state = getattr(run, "state", "unknown")

    # Compute all validation steps: 0, val_interval, 2*val_interval, ...
    steps = list(range(0, last_step + 1, val_interval))
    total_videos = len(steps) * num_prompts

    result = MatrixInfo(
        run_id=run_id,
        run_name=run_name,
        run_state=run_state,
        validation_interval=val_interval,
        num_prompts=num_prompts,
        last_step=last_step,
        steps=steps,
        total_videos=total_videos,
    )

    _set_cached_videos(cache_key, result)
    return result

@router.get("/runs", response_model=list[RunItem])
async def list_runs(db: Storage = Depends(get_db)):
    """List all runs in the WandB project."""
    client = _make_client(db)
    try:
        runs = client.list_runs()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"WandB API error: {exc}")

    return [
        RunItem(run_id=r.run_id, name=r.name, state=r.state, created_at=r.created_at)
        for r in runs
    ]


@router.get("/checkpoints/{run_id}", response_model=list[CheckpointItem])
async def list_checkpoints(run_id: str, db: Storage = Depends(get_db)):
    """List all checkpoints (steps with videos) for a run."""
    client = _make_client(db)
    try:
        ckpts = client.list_checkpoints(run_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"WandB API error: {exc}")

    return [
        CheckpointItem(
            checkpoint_id=c.checkpoint_id,
            training_step=c.training_step,
            video_count=c.video_count,
        )
        for c in ckpts
    ]


@router.get("/videos/{run_id}/{step}", response_model=list[VideoItem])
async def list_videos(
    run_id: str,
    step: int,
    db: Storage = Depends(get_db),
):
    """List video metadata for a step. No video downloads — just captions + proxy URLs."""
    cache_key = f"{run_id}:{step}"
    videos = _get_cached_videos(cache_key)

    if videos is None:
        client = _make_client(db)
        try:
            videos = client.fetch_videos(run_id, step)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"WandB API error: {exc}")
        _set_cached_videos(cache_key, videos)

    result = []
    for i, v in enumerate(videos):
        prompt = PromptInfo.from_caption(v.caption)
        result.append(VideoItem(
            index=i,
            caption=v.caption,
            prompt_id=v.prompt_id,
            action_label=prompt.action_label,
            category=prompt.category.value,
            sha256=v.sha256,
            size_bytes=v.size_bytes,
            wandb_path=v.wandb_path,
            proxy_url=f"/api/video-proxy/{run_id}/{step}/{i}",
        ))

    return result


@router.get("/video-proxy/{run_id}/{step}/{index}")
async def proxy_video(
    run_id: str,
    step: int,
    index: int,
    request: Request = None,
    db: Storage = Depends(get_db),
):
    """Download a single video from WandB (with local caching) and stream it."""
    cached = _cache_path(run_id, step, index, request)

    # Serve from cache if file exists and is non-empty
    if cached.exists() and cached.stat().st_size > 0:
        return FileResponse(
            path=str(cached),
            media_type="video/mp4",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    # Clean up any stale 0-byte files
    if cached.exists():
        cached.unlink()

    # Get video metadata
    cache_key = f"{run_id}:{step}"
    videos = _get_cached_videos(cache_key)
    if videos is None:
        client = _make_client(db)
        try:
            videos = client.fetch_videos(run_id, step)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"WandB error: {exc}")
        _set_cached_videos(cache_key, videos)

    if index < 0 or index >= len(videos):
        raise HTTPException(status_code=404, detail=f"Video index {index} not found (have {len(videos)})")

    video = videos[index]

    # Download from WandB
    logger.info("Downloading video %d from WandB: %s", index, video.wandb_path)
    try:
        client = _make_client(db)
        run = client.api.run(f"{client.project_path}/{run_id}")
        wandb_file = run.file(video.wandb_path)

        # Create cache directory
        cached.parent.mkdir(parents=True, exist_ok=True)

        # WandB download() preserves the full directory structure
        # e.g. video.wandb_path = "media/videos/validation_..._500_abc123.mp4"
        # → downloads to: cached.parent / "media/videos/validation_..._500_abc123.mp4"
        wandb_file.download(root=str(cached.parent), replace=True)

        # Find the downloaded file — it'll be in a subdirectory
        downloaded = cached.parent / video.wandb_path
        if not downloaded.exists():
            # Fallback: glob for any recently downloaded .mp4
            candidates = list(cached.parent.rglob("*.mp4"))
            # Pick the one matching our wandb_path filename
            target_name = Path(video.wandb_path).name
            downloaded = next((c for c in candidates if c.name == target_name), None)

        if downloaded and downloaded.exists() and downloaded.stat().st_size > 0:
            downloaded.rename(cached)
            logger.info("Cached video %d at %s (%d bytes)", index, cached, cached.stat().st_size)
        else:
            raise RuntimeError(f"Downloaded file not found or empty for {video.wandb_path}")

    except Exception as exc:
        logger.error("Failed to download video %d: %s", index, exc)
        raise HTTPException(status_code=502, detail=f"Download failed: {exc}")

    return FileResponse(
        path=str(cached),
        media_type="video/mp4",
        headers={"Cache-Control": "public, max-age=86400"},
    )
