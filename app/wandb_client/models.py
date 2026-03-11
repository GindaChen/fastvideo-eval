"""Domain models for the WandB integration layer.

Maps to SPEC §4.1 entities that the ingestion layer touches.
These are plain dataclasses — no ORM, no persistence logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class CheckpointSource(str, Enum):
    """How a checkpoint was selected for evaluation (SPEC §4.1.4)."""
    TOP5_METRIC = "top5_metric"
    ROUND_NUMBER = "round_number"


class VideoStatus(str, Enum):
    """Whether a video is available for evaluation."""
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"  # Missing from WandB or failed to download


@dataclass(frozen=True)
class RunInfo:
    """A WandB run in the wangame project.

    Represents one training run that may contain many checkpoints.
    """
    run_id: str
    name: str
    state: str  # "running", "finished", "crashed", etc.
    created_at: str  # ISO 8601
    config: dict = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        return self.name or self.run_id


@dataclass(frozen=True)
class CheckpointInfo:
    """A model checkpoint to be evaluated (SPEC §4.1.4).

    Derived from scanning a WandB run's history for validation steps.
    """
    checkpoint_id: str
    training_step: int
    wandb_run_id: str
    optical_flow_score: Optional[float] = None
    source: CheckpointSource = CheckpointSource.ROUND_NUMBER

    @staticmethod
    def make_id(run_id: str, step: int) -> str:
        """Deterministic checkpoint ID from run + step."""
        return f"{run_id}_step{step}"


@dataclass(frozen=True)
class VideoInfo:
    """A generated video for one prompt × one checkpoint (SPEC §4.1.5).

    Videos have pre-rendered action overlays (no compositing needed).
    """
    video_id: str
    checkpoint_id: str
    prompt_id: str
    wandb_url: str
    training_step: int
    has_action_overlay: bool = True
    optical_flow_score: Optional[float] = None
    duration_frames: int = 77
    local_path: Optional[str] = None
    status: VideoStatus = VideoStatus.AVAILABLE

    @staticmethod
    def make_id(checkpoint_id: str, prompt_id: str) -> str:
        """Deterministic video ID (SPEC §4.2)."""
        return f"{checkpoint_id}_{prompt_id}"


@dataclass
class IngestionResult:
    """Summary of a video ingestion operation.

    Returned by WandBClient.ingest_checkpoint() to report what happened.
    """
    checkpoint_id: str
    run_id: str
    training_step: int
    videos_found: int = 0
    videos_cached: int = 0
    videos_downloaded: int = 0
    videos_unavailable: int = 0
    errors: list[str] = field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    @property
    def success(self) -> bool:
        return len(self.errors) == 0 and self.videos_unavailable == 0

    @property
    def duration_seconds(self) -> Optional[float]:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None
