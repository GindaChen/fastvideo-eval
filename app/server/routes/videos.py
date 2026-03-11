"""Video proxy and WandB data listing endpoints.

Endpoints:
  GET /api/runs                          — list runs
  GET /api/checkpoints/{run_id}          — list checkpoints for a run
  GET /api/videos/{run_id}/{step}        — list video metadata (captions) for a step
  GET /api/video-proxy/{run_id}/{step}/{index} — download & stream a single video
  POST /api/cache/warm                   — warm cache for selected steps (background)
  GET /api/cache/status/{run_id}         — cache coverage per step
"""

from __future__ import annotations

import hashlib
import os
import logging
import shutil
import threading
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

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
    # wandb file.download() reads from env/netrc, NOT the per-instance api_key.
    # Set the env var so ALL wandb operations use the stored key.
    os.environ["WANDB_API_KEY"] = api_key
    logger.debug("WandB client: key=%s…%s", api_key[:4], api_key[-4:] if len(api_key) > 8 else "****")
    config = WandBConfig(
        project=settings.get("wandb_project", "wangame_1.3b"),
        entity=settings.get("wandb_entity", "kaiqin_kong_ucsd"),
        api_key=api_key,
        default_run_id=settings.get("default_run_id", "fif3z1z4"),
        validation_key=settings.get("validation_key", "validation_videos_40_steps"),
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


class ProbeRequest(BaseModel):
    run_id: str
    entity: Optional[str] = None    # Override entity for this probe
    project: Optional[str] = None   # Override project for this probe


class ProbeResponse(BaseModel):
    run_id: str
    run_name: str
    run_state: str
    video_keys: list[str]
    sample_filenames: list[str]
    mp4_count: int
    sample_captions: list[str]
    caption_format: str
    recommended_key: str
    validation_steps: int
    validation_num_samples: int
    other_video_keys: list[str]


@router.post("/runs/probe", response_model=ProbeResponse)
async def probe_run(body: ProbeRequest, db: Storage = Depends(get_db)):
    """Auto-detect video structure of a WandB run.

    Inspects the run's files, history, and config to discover:
    - Which history key contains validation videos
    - What the MP4 filename pattern looks like
    - What format the captions use
    - Recommended validation_key for configuration
    """
    client = _make_client(db)

    # Allow overriding entity/project for cross-project probing
    if body.entity or body.project:
        config = client.config
        client = WandBClient(WandBConfig(
            project=body.project or config.project,
            entity=body.entity or config.entity,
            api_key=config.api_key,
            default_run_id=config.default_run_id,
            validation_key=config.validation_key,
        ))

    try:
        result = client.probe_run(body.run_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Probe failed: {exc}")

    return ProbeResponse(
        run_id=result.run_id,
        run_name=result.run_name,
        run_state=result.run_state,
        video_keys=result.video_keys,
        sample_filenames=result.sample_filenames,
        mp4_count=result.mp4_count,
        sample_captions=result.sample_captions,
        caption_format=result.caption_format,
        recommended_key=result.recommended_key,
        validation_steps=result.validation_steps,
        validation_num_samples=result.validation_num_samples,
        other_video_keys=result.other_video_keys,
    )


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
    """Non-blocking video proxy with background downloading.

    - Cached → serve file instantly (200)
    - Download in-flight → return 202 JSON with retry_after
    - Not started → kick off background download → return 202
    """

    cached = _cache_path(run_id, step, index, request)

    # ── Serve from cache if file exists and is non-empty ──
    if cached.exists() and cached.stat().st_size > 0:
        return FileResponse(
            path=str(cached),
            media_type="video/mp4",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    # ── Download already in-flight? ──
    tmp = cached.with_suffix(".tmp")
    if tmp.exists():
        return JSONResponse(
            status_code=202,
            content={"status": "downloading", "retry_after": 2},
            headers={"Retry-After": "2"},
        )

    # ── Clean up stale 0-byte files ──
    if cached.exists():
        cached.unlink()

    # ── Start background download ──
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

    # Launch download in a background thread (non-blocking)
    def _bg_download():
        try:
            _download_single_video(db, run_id, video, cached)
            logger.info("Background download complete: %s step %d idx %d", run_id, step, index)
        except Exception as exc:
            logger.error("Background download failed: %s step %d idx %d: %s", run_id, step, index, exc)

    thread = threading.Thread(target=_bg_download, daemon=True)
    thread.start()

    return JSONResponse(
        status_code=202,
        content={"status": "downloading", "retry_after": 3},
        headers={"Retry-After": "3"},
    )


# Per-file download locks: prevent concurrent downloads of the same video
_download_locks: dict[str, threading.Lock] = {}
_download_locks_guard = threading.Lock()


def _get_download_lock(path: str) -> threading.Lock:
    """Get or create a lock for a specific file path."""
    with _download_locks_guard:
        if path not in _download_locks:
            _download_locks[path] = threading.Lock()
        return _download_locks[path]


def _download_single_video(
    db: Storage, run_id: str, video, dest: Path
) -> None:
    """Download one video from WandB and save it to `dest`.

    Atomic: downloads to .tmp, then renames. Per-file locked to
    prevent concurrent downloads of the same video.
    """
    lock = _get_download_lock(str(dest))
    if not lock.acquire(timeout=120):  # wait up to 2min for another download
        # Another thread is downloading — check if done
        if dest.exists() and dest.stat().st_size > 0:
            return
        raise RuntimeError(f"Timeout waiting for download lock: {dest}")

    try:
        # Double-check: another thread may have finished while we waited
        if dest.exists() and dest.stat().st_size > 0:
            return

        client = _make_client(db)
        run = client.api.run(f"{client.project_path}/{run_id}")
        wandb_file = run.file(video.wandb_path)

        dest.parent.mkdir(parents=True, exist_ok=True)

        # Download to a temp directory, then move atomically
        tmp_dir = dest.parent / f".tmp_{dest.stem}"
        tmp_dir.mkdir(parents=True, exist_ok=True)

        # Mark download in-flight with a .tmp sentinel
        tmp_sentinel = dest.with_suffix(".tmp")
        tmp_sentinel.touch()

        try:
            wandb_file.download(root=str(tmp_dir), replace=True)

            # WandB preserves directory structure — find the file
            downloaded = tmp_dir / video.wandb_path
            if not downloaded.exists():
                candidates = list(tmp_dir.rglob("*.mp4"))
                target_name = Path(video.wandb_path).name
                downloaded = next((c for c in candidates if c.name == target_name), None)

            if downloaded and downloaded.exists() and downloaded.stat().st_size > 0:
                # Atomic move to final destination
                shutil.move(str(downloaded), str(dest))
                logger.info("Cached video at %s (%d bytes)", dest, dest.stat().st_size)
            else:
                raise RuntimeError(f"Downloaded file not found or empty for {video.wandb_path}")
        finally:
            # Clean up temp dir and sentinel
            shutil.rmtree(str(tmp_dir), ignore_errors=True)
            if tmp_sentinel.exists():
                tmp_sentinel.unlink()
    finally:
        lock.release()


# --------------------------------------------------------------------------- #
# Cache warming (background bulk download)
# --------------------------------------------------------------------------- #

# Track warm jobs: key = "{run_id}" → progress dict
_warm_jobs: dict[str, dict] = {}


class CacheWarmRequest(BaseModel):
    run_id: str
    steps: list[int] = Field(..., description="Steps to warm")


class CacheWarmResponse(BaseModel):
    status: str
    message: str
    total_videos: int = 0


class CacheStepStatus(BaseModel):
    step: int
    total: int
    cached: int


class CacheStatusResponse(BaseModel):
    run_id: str
    steps: list[CacheStepStatus]
    total_videos: int
    cached_videos: int
    warming: bool
    warm_progress: Optional[dict] = None


def _warm_cache_worker(
    db: Storage, run_id: str, steps: list[int], cache_dir: Path
) -> None:
    """Background worker: download all videos for the given steps."""
    job = _warm_jobs.setdefault(run_id, {})
    job.update({
        "status": "running",
        "steps_total": len(steps),
        "steps_done": 0,
        "videos_total": 0,
        "videos_cached": 0,
        "videos_downloaded": 0,
        "videos_failed": 0,
        "current_step": None,
    })

    for step_idx, step in enumerate(steps):
        job["current_step"] = step
        try:
            client = _make_client(db)
            cache_key = f"{run_id}:{step}"
            videos = _get_cached_videos(cache_key)
            if videos is None:
                videos = client.fetch_videos(run_id, step)
                _set_cached_videos(cache_key, videos)

            job["videos_total"] += len(videos)

            for i, video in enumerate(videos):
                dest = cache_dir / run_id / f"step_{step}" / f"{i:02d}.mp4"
                if dest.exists() and dest.stat().st_size > 0:
                    job["videos_cached"] += 1
                    continue
                try:
                    _download_single_video(db, run_id, video, dest)
                    job["videos_downloaded"] += 1
                except Exception as exc:
                    logger.warning("Warm cache: failed %s step %d idx %d: %s", run_id, step, i, exc)
                    job["videos_failed"] += 1

        except Exception as exc:
            logger.error("Warm cache: step %d failed entirely: %s", step, exc)

        job["steps_done"] = step_idx + 1

    job["status"] = "done"
    job["current_step"] = None
    logger.info(
        "Cache warm complete for %s: %d downloaded, %d cached, %d failed",
        run_id, job["videos_downloaded"], job["videos_cached"], job["videos_failed"],
    )


@router.post("/cache/warm", response_model=CacheWarmResponse)
async def warm_cache(
    body: CacheWarmRequest,
    request: Request,
    db: Storage = Depends(get_db),
):
    """Start downloading all videos for the given steps in the background."""
    run_id = body.run_id
    steps = sorted(body.steps)

    # Check if already running
    existing = _warm_jobs.get(run_id, {})
    if existing.get("status") == "running":
        return CacheWarmResponse(
            status="already_running",
            message=f"Cache warm already in progress: step {existing.get('current_step')}, "
                    f"{existing.get('videos_downloaded', 0)} downloaded so far",
            total_videos=existing.get("videos_total", 0),
        )

    cache_dir = _get_cache_dir(request)
    total_est = len(steps) * 32  # estimate 32 prompts per step

    # Launch in background thread (not asyncio — downloads are blocking)
    thread = threading.Thread(
        target=_warm_cache_worker,
        args=(db, run_id, steps, cache_dir),
        daemon=True,
    )
    thread.start()

    return CacheWarmResponse(
        status="started",
        message=f"Warming cache for {len(steps)} steps ({total_est} estimated videos)",
        total_videos=total_est,
    )


@router.get("/cache/status/{run_id}", response_model=CacheStatusResponse)
async def cache_status(
    run_id: str,
    request: Request,
    db: Storage = Depends(get_db),
):
    """Report how many videos are cached per step."""
    cache_dir = _get_cache_dir(request)
    run_dir = cache_dir / run_id

    step_statuses = []
    total = 0
    cached = 0

    # Scan cached files per step directory
    if run_dir.exists():
        for step_dir in sorted(run_dir.iterdir()):
            if not step_dir.is_dir() or not step_dir.name.startswith("step_"):
                continue
            try:
                step_num = int(step_dir.name.replace("step_", ""))
            except ValueError:
                continue
            mp4s = list(step_dir.glob("*.mp4"))
            cached_count = sum(1 for f in mp4s if f.stat().st_size > 0)
            # Get expected total from metadata cache
            cache_key = f"{run_id}:{step_num}"
            videos = _get_cached_videos(cache_key)
            expected = len(videos) if videos else max(cached_count, 32)
            step_statuses.append(CacheStepStatus(
                step=step_num, total=expected, cached=cached_count,
            ))
            total += expected
            cached += cached_count

    job = _warm_jobs.get(run_id)
    warming = job is not None and job.get("status") == "running"

    return CacheStatusResponse(
        run_id=run_id,
        steps=step_statuses,
        total_videos=total,
        cached_videos=cached,
        warming=warming,
        warm_progress=job if warming else None,
    )
