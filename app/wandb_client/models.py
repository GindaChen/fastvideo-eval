"""Domain models for the WandB integration layer.

Maps to SPEC §4.1 entities that the ingestion layer touches.
These are plain dataclasses — no ORM, no persistence logic.

Updated to match verified WandB data structure from run fif3z1z4:
- Captions are the prompt identifiers (e.g., "00 Val-00: W")
- SHA256 content hash maps to filename (sha256[:20] = filename suffix)
- 32 videos per step, logged every 500 steps
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class CheckpointSource(str, Enum):
    """How a checkpoint was selected for evaluation (SPEC §4.1.4)."""
    TOP5_METRIC = "top5_metric"
    ROUND_NUMBER = "round_number"


class ActionCategory(str, Enum):
    """Prompt action categories discovered from WandB captions."""
    SINGLE_KEY = "single_key"          # W, S, A, D
    SINGLE_CAMERA = "single_camera"    # u, d, l, r
    RANDOM_KEY = "random_key"          # key rand
    RANDOM_CAMERA = "random_camera"    # camera rand
    COMBINED_EXCL = "combined_excl"    # key+camera excl rand
    COMBINED = "combined"              # key+camera rand
    SIMULTANEOUS = "simultaneous"      # (simultaneous) *
    MULTI_KEY = "multi_key"            # W+A, S+u
    STILL = "still"                    # Still
    ALT_FRAME = "alt_frame"            # Frame 4
    TRAINING = "training"              # Train-*
    DOOM = "doom"                      # Doom-*


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

    Derived from scanning a WandB run's file listing for validation steps.
    """
    checkpoint_id: str
    training_step: int
    wandb_run_id: str
    video_count: int = 32
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

    The caption field (e.g., "00 Val-00: W") is the primary prompt
    identifier from WandB. The sha256 is a content hash that maps
    to the filename: sha256[:20] = filename suffix.
    """
    video_id: str
    checkpoint_id: str
    prompt_id: str
    wandb_url: str
    training_step: int
    caption: str = ""             # WandB caption (e.g., "00 Val-00: W")
    sha256: str = ""              # Content hash — changes every step
    action_label: str = ""        # Parsed action (e.g., "W", "key rand")
    wandb_path: str = ""          # File path in WandB (media/videos/...)
    size_bytes: int = 0           # File size from WandB
    has_action_overlay: bool = True
    optical_flow_score: Optional[float] = None
    duration_frames: int = 77
    local_path: Optional[str] = None
    status: VideoStatus = VideoStatus.AVAILABLE

    @staticmethod
    def make_id(checkpoint_id: str, prompt_id: str) -> str:
        """Deterministic video ID (SPEC §4.2)."""
        return f"{checkpoint_id}_{prompt_id}"


@dataclass(frozen=True)
class PromptInfo:
    """Parsed prompt metadata from a WandB video caption.

    Captions have format: "NN Label: Action" where:
    - NN is the index (00-31)
    - Label is like "Val-00", "Train-00", "Doom-00"
    - Action is the input description (W, S, key rand, etc.)
    """
    index: int               # 0-31
    caption: str             # Full caption string
    prompt_id: str           # Normalized ID (e.g., "val_00_w")
    label: str               # e.g., "Val-00", "Train-01", "Doom-02"
    action_label: str        # e.g., "W", "key rand", "camera rand"
    category: ActionCategory
    source: str = ""         # "Val", "Train", or "Doom"

    @staticmethod
    def from_caption(caption: str) -> PromptInfo:
        """Parse a WandB video caption into structured prompt info.

        Examples:
            "00 Val-00: W"         → PromptInfo(index=0, action="W", ...)
            "08 Val-00: key rand"  → PromptInfo(index=8, action="key rand", ...)
            "26 Train-00"          → PromptInfo(index=26, action="", label="Train-00")
            "28 Doom-00: W"        → PromptInfo(index=28, action="W", ...)
        """
        # Parse: "NN Label" or "NN Label: Action"
        m = re.match(r"^(\d+)\s+(.+?)(?::\s*(.+))?$", caption)
        if not m:
            return PromptInfo(
                index=0, caption=caption, prompt_id=caption.lower().replace(" ", "_"),
                label=caption, action_label="", category=ActionCategory.SINGLE_KEY,
            )

        index = int(m.group(1))
        label = m.group(2).strip()
        action = (m.group(3) or "").strip()

        # Determine source
        source = "Val"
        if label.startswith("Train"):
            source = "Train"
        elif label.startswith("Doom"):
            source = "Doom"

        # Determine category
        category = _classify_action(action, label)

        # Build normalized prompt_id
        prompt_id = label.lower().replace("-", "_")
        if action:
            action_slug = action.lower().replace(" ", "_").replace("+", "_")
            action_slug = re.sub(r"[^a-z0-9_]", "", action_slug)
            prompt_id = f"{prompt_id}_{action_slug}"

        return PromptInfo(
            index=index,
            caption=caption,
            prompt_id=prompt_id,
            label=label,
            action_label=action,
            category=category,
            source=source,
        )


def _classify_action(action: str, label: str) -> ActionCategory:
    """Classify a caption's action into an ActionCategory."""
    al = action.lower()
    ll = label.lower()

    if ll.startswith("train"):
        return ActionCategory.TRAINING
    if ll.startswith("doom"):
        return ActionCategory.DOOM
    if "still" in al:
        return ActionCategory.STILL
    if "frame" in al:
        return ActionCategory.ALT_FRAME
    if "simultaneous" in al:
        return ActionCategory.SIMULTANEOUS
    if "key+camera excl" in al:
        return ActionCategory.COMBINED_EXCL
    if "key+camera" in al:
        return ActionCategory.COMBINED
    if "camera rand" in al:
        return ActionCategory.RANDOM_CAMERA
    if "key rand" in al:
        return ActionCategory.RANDOM_KEY
    # Multi-key combos like "W+A", "S+u"
    if "+" in action:
        return ActionCategory.MULTI_KEY
    # Single actions: W, S, A, D are keys; u, d, l, r are camera
    if action in ("u", "d", "l", "r"):
        return ActionCategory.SINGLE_CAMERA
    return ActionCategory.SINGLE_KEY


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
