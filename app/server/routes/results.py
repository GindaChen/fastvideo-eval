"""Score Review endpoints (SPEC §12.2).

Endpoints:
  GET /api/results                         — aggregated scores
  GET /api/results/{checkpoint_id}         — per-checkpoint breakdown
  GET /api/results/{checkpoint_id}/videos  — per-video ratings (filterable)
  GET /api/results/export                  — CSV export
"""

from __future__ import annotations

import csv
import io
import json
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.server.auth import get_db
from app.server.database import Database

router = APIRouter(prefix="/api/results", tags=["results"])


# --------------------------------------------------------------------------- #
# Response models
# --------------------------------------------------------------------------- #

class ScoreSummary(BaseModel):
    checkpoint_id: str
    overall_score: float
    total_videos: int
    total_good: int
    total_bad: int
    total_skipped: int
    evaluator_count: int
    computed_at: str


class CheckpointDetail(BaseModel):
    checkpoint_id: str
    overall_score: float
    per_task_scores: dict
    total_videos: int
    total_good: int
    total_bad: int
    total_skipped: int
    evaluator_count: int
    computed_at: str


class VideoRating(BaseModel):
    video_id: str
    prompt_id: str
    rating: str
    issues: Optional[list[str]]
    evaluator: str
    playback_speed: Optional[str]
    view_duration_ms: Optional[int]
    timestamp: str


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #

@router.get("", response_model=list[ScoreSummary])
async def list_scores(db: Database = Depends(get_db)):
    """Aggregated scores across all checkpoints."""
    with db.conn() as c:
        rows = c.execute(
            """SELECT DISTINCT checkpoint_id FROM checkpoint_scores
               ORDER BY checkpoint_id"""
        ).fetchall()

    result = []
    for row in rows:
        score = db.get_latest_score(row["checkpoint_id"])
        if score:
            result.append(ScoreSummary(**{
                k: score[k] for k in ScoreSummary.model_fields
            }))
    return result


@router.get("/export")
async def export_csv(
    checkpoint_id: Optional[str] = None,
    category: Optional[str] = None,
    rating: Optional[str] = None,
    db: Database = Depends(get_db),
):
    """Export filtered ratings as CSV."""
    with db.conn() as c:
        query = "SELECT * FROM ratings WHERE 1=1"
        params: list = []

        if checkpoint_id:
            query += " AND checkpoint_id = ?"
            params.append(checkpoint_id)
        if rating:
            query += " AND rating = ?"
            params.append(rating)

        query += " ORDER BY timestamp"
        rows = c.execute(query, params).fetchall()

    # Build CSV
    output = io.StringIO()
    if rows:
        writer = csv.DictWriter(output, fieldnames=rows[0].keys())
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=ratings_export.csv"},
    )


@router.get("/{checkpoint_id}", response_model=CheckpointDetail)
async def checkpoint_detail(
    checkpoint_id: str,
    db: Database = Depends(get_db),
):
    """Per-checkpoint detailed breakdown with per-task scores."""
    score = db.get_latest_score(checkpoint_id)
    if not score:
        # Compute from raw ratings if no cached score exists
        latest = db.get_latest_ratings(checkpoint_id)
        total = len(latest)
        good = sum(1 for r in latest.values() if r["rating"] == "good")
        bad = sum(1 for r in latest.values() if r["rating"] == "bad")
        skipped = sum(1 for r in latest.values() if r["rating"] == "skip")
        evaluators = len(set(r["evaluator"] for r in latest.values()))

        return CheckpointDetail(
            checkpoint_id=checkpoint_id,
            overall_score=good / (good + bad) if (good + bad) > 0 else 0.0,
            per_task_scores={},
            total_videos=total,
            total_good=good,
            total_bad=bad,
            total_skipped=skipped,
            evaluator_count=evaluators,
            computed_at="live",
        )

    return CheckpointDetail(**{
        k: score[k] for k in CheckpointDetail.model_fields
    })


@router.get("/{checkpoint_id}/videos", response_model=list[VideoRating])
async def checkpoint_videos(
    checkpoint_id: str,
    category: Optional[str] = None,
    rating_filter: Optional[str] = Query(None, alias="rating"),
    evaluator: Optional[str] = None,
    db: Database = Depends(get_db),
):
    """Per-video ratings for a checkpoint (filterable)."""
    ratings = db.get_ratings_for_checkpoint(checkpoint_id)

    result = []
    for r in ratings:
        if rating_filter and r["rating"] != rating_filter:
            continue
        if evaluator and r["evaluator"] != evaluator:
            continue

        issues = json.loads(r["issues"]) if r["issues"] else None

        result.append(VideoRating(
            video_id=r["video_id"],
            prompt_id=r["prompt_id"],
            rating=r["rating"],
            issues=issues,
            evaluator=r["evaluator"],
            playback_speed=r.get("playback_speed"),
            view_duration_ms=r.get("view_duration_ms"),
            timestamp=r["timestamp"],
        ))

    return result
