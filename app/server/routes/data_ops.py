"""Data Operation endpoints (SPEC §12.2).

Endpoints:
  GET  /api/dashboard           — evaluation round status
  GET  /api/chunks              — list chunks with status
  POST /api/chunks/{id}/claim   — claim a chunk
  GET  /api/chunks/{id}/videos  — videos for a chunk with rating status
  POST /api/ratings             — submit a rating (append-only)
  GET  /api/skipped             — all skipped videos for revisit queue
  GET  /api/health              — service health check
"""

from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.server.auth import get_db, verify_token
from app.server.storage import Storage

router = APIRouter(prefix="/api", tags=["data-ops"])


# --------------------------------------------------------------------------- #
# Request / Response models
# --------------------------------------------------------------------------- #

class DashboardResponse(BaseModel):
    total_chunks: int
    chunks_done: int
    chunks_in_progress: int
    chunks_not_started: int
    total_videos: int
    videos_committed: int  # good + bad
    videos_skipped: int
    videos_unrated: int


class ChunkResponse(BaseModel):
    chunk_id: str
    checkpoint_id: str
    video_ids: list[str]
    task_category: Optional[str]
    status: str
    assigned_to: Optional[str]
    started_at: Optional[str]
    completed_at: Optional[str]


class ClaimRequest(BaseModel):
    evaluator: str


class RatingRequest(BaseModel):
    video_id: str
    chunk_id: str = ""
    checkpoint_id: str
    prompt_id: str
    rating: str  # good | bad | skip
    evaluator: str
    issues: Optional[list[str]] = None
    free_text: Optional[str] = None
    playback_speed: Optional[str] = None
    view_duration_ms: Optional[int] = None
    supersedes: Optional[str] = None


class RatingResponse(BaseModel):
    rating_id: str
    status: str


class VideoRatingStatus(BaseModel):
    video_id: str
    latest_rating: Optional[str]  # good | bad | skip | None
    rating_count: int


class HealthResponse(BaseModel):
    status: str
    database: str
    version: str = "0.1.0"


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #

@router.get("/health", response_model=HealthResponse)
async def health(db: Storage = Depends(get_db)):
    """Service health check."""
    return HealthResponse(status="ok", database="ok")


@router.get("/dashboard", response_model=DashboardResponse)
async def dashboard(
    checkpoint_id: Optional[str] = None,
    db: Storage = Depends(get_db),
):
    """Get evaluation round status."""
    chunks = db.get_chunks(checkpoint_id)

    total_chunks = len(chunks)
    chunks_done = sum(1 for c in chunks if c["status"] == "done")
    chunks_in_progress = sum(1 for c in chunks if c["status"] == "in_progress")
    chunks_not_started = sum(1 for c in chunks if c["status"] == "not_started")

    # Collect all video IDs
    all_video_ids = set()
    for c in chunks:
        all_video_ids.update(c["video_ids"])

    total_videos = len(all_video_ids)

    # Get ratings to compute status
    rated_videos: dict[str, str] = {}  # video_id → latest rating
    if chunks:
        ckpt = chunks[0]["checkpoint_id"]
        latest = db.get_latest_ratings(ckpt)
        for key, r in latest.items():
            vid = r["video_id"]
            if vid not in rated_videos:
                rated_videos[vid] = r["rating"]

    committed = sum(1 for r in rated_videos.values() if r in ("good", "bad"))
    skipped = sum(1 for r in rated_videos.values() if r == "skip")
    unrated = total_videos - committed - skipped

    return DashboardResponse(
        total_chunks=total_chunks,
        chunks_done=chunks_done,
        chunks_in_progress=chunks_in_progress,
        chunks_not_started=chunks_not_started,
        total_videos=total_videos,
        videos_committed=committed,
        videos_skipped=skipped,
        videos_unrated=unrated,
    )


@router.get("/chunks", response_model=list[ChunkResponse])
async def list_chunks(
    checkpoint_id: Optional[str] = None,
    db: Storage = Depends(get_db),
):
    """List evaluation chunks."""
    chunks = db.get_chunks(checkpoint_id)
    return [ChunkResponse(**c) for c in chunks]


@router.post("/chunks/{chunk_id}/claim")
async def claim_chunk(
    chunk_id: str,
    body: ClaimRequest,
    db: Storage = Depends(get_db),
):
    """Claim a chunk for evaluation."""
    ok = db.claim_chunk(chunk_id, body.evaluator)
    if not ok:
        raise HTTPException(
            status_code=409,
            detail="Chunk already claimed or does not exist",
        )
    return {"status": "claimed", "chunk_id": chunk_id, "evaluator": body.evaluator}


@router.get("/chunks/{chunk_id}/videos", response_model=list[VideoRatingStatus])
async def chunk_videos(
    chunk_id: str,
    db: Storage = Depends(get_db),
):
    """Get videos for a chunk with per-video rating status."""
    chunks = db.get_chunks()
    chunk = next((c for c in chunks if c["chunk_id"] == chunk_id), None)
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found")

    video_ids = chunk["video_ids"]

    # Get latest ratings for these videos
    ckpt = chunk["checkpoint_id"]
    latest = db.get_latest_ratings(ckpt)

    result = []
    for vid in video_ids:
        # Find latest rating for this video (any evaluator)
        matching = [
            r for key, r in latest.items()
            if r["video_id"] == vid
        ]
        rating = matching[0]["rating"] if matching else None
        count = len(matching)
        result.append(VideoRatingStatus(
            video_id=vid,
            latest_rating=rating,
            rating_count=count,
        ))

    return result


@router.post("/ratings", response_model=RatingResponse)
async def submit_rating(
    body: RatingRequest,
    db: Storage = Depends(get_db),
):
    """Submit a video rating (append-only)."""
    if body.rating not in ("good", "bad", "skip"):
        raise HTTPException(
            status_code=422,
            detail="Rating must be 'good', 'bad', or 'skip'",
        )

    rating_id = db.insert_rating(
        video_id=body.video_id,
        chunk_id=body.chunk_id,
        checkpoint_id=body.checkpoint_id,
        prompt_id=body.prompt_id,
        rating=body.rating,
        evaluator=body.evaluator,
        issues=body.issues,
        free_text=body.free_text,
        playback_speed=body.playback_speed,
        view_duration_ms=body.view_duration_ms,
        supersedes=body.supersedes,
    )

    return RatingResponse(rating_id=rating_id, status="stored")


@router.get("/skipped", response_model=list[VideoRatingStatus])
async def skipped_videos(
    checkpoint_id: Optional[str] = None,
    db: Storage = Depends(get_db),
):
    """List all skipped videos for the revisit queue."""
    if not checkpoint_id:
        # Use first checkpoint found
        chunks = db.get_chunks()
        if not chunks:
            return []
        checkpoint_id = chunks[0]["checkpoint_id"]

    latest = db.get_latest_ratings(checkpoint_id)

    skipped = [
        VideoRatingStatus(
            video_id=r["video_id"],
            latest_rating="skip",
            rating_count=1,
        )
        for r in latest.values()
        if r["rating"] == "skip"
    ]
    return skipped


# --------------------------------------------------------------------------- #
# Review: bad ratings with issue management
# --------------------------------------------------------------------------- #

class UpdateIssuesRequest(BaseModel):
    issues: list[str]
    free_text: Optional[str] = None


@router.get("/ratings/bad")
async def bad_ratings(
    db: Storage = Depends(get_db),
):
    """List all bad-rated videos (latest per video)."""
    return db.get_bad_ratings()


@router.patch("/ratings/{rating_id}/issues")
async def update_rating_issues(
    rating_id: str,
    body: UpdateIssuesRequest,
    db: Storage = Depends(get_db),
):
    """Update issues and free_text on an existing rating."""
    found = db.update_rating_issues(rating_id, body.issues, body.free_text)
    if not found:
        raise HTTPException(status_code=404, detail="Rating not found")
    return {"status": "updated", "rating_id": rating_id}
