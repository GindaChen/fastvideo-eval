"""WandB client for WanGame Eval (SPEC §8).

Implements the core operations:
  1. List runs — fetch all runs in the project
  2. List checkpoints — find steps with validation videos (via file listing)
  3. Fetch videos — retrieve caption-indexed video entries for a step
  4. Fetch optical flow — automated pre-filter scores

Data structure (verified on run fif3z1z4 / MC_long_run):
  - Videos logged as `validation_videos_40_steps` at every 500 steps
  - Each entry is a dict of 32 video-file objects with captions
  - Captions like "00 Val-00: W" are the prompt identifiers
  - SHA256 content hash maps to filename: sha256[:20] = filename suffix
  - Hash changes every step (content hash, NOT prompt ID)

Error handling follows SPEC §8.4:
  - Exponential backoff for rate limits (1s → 60s)
  - 3 retries for network failures, then mark unavailable
  - Structured logging per SPEC §13.1
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Optional

import wandb as wandb_sdk

from app.wandb_client.config import WandBConfig
from app.wandb_client.models import (
    CheckpointInfo,
    CheckpointSource,
    IngestionResult,
    PromptInfo,
    RunInfo,
    VideoInfo,
    VideoStatus,
)
from app.wandb_client.cache import VideoCache

logger = logging.getLogger("wangame.wandb")

# Regex page for parsing video filenames
_STEP_PATTERN = re.compile(
    r"validation_videos_40_steps_(\d+)_([a-f0-9]+)\.mp4$"
)


class WandBClientError(Exception):
    """Raised on unrecoverable WandB API errors."""


class WandBClient:
    """Client for the WandB integration layer.

    Wraps the wandb public API with retry logic, structured logging,
    and domain-specific data normalization.

    Args:
        config: WandB connection configuration.
        cache: Optional VideoCache for local video storage.
    """

    def __init__(self, config: WandBConfig, cache: Optional[VideoCache] = None):
        self.config = config
        self.cache = cache
        self._api: Optional[wandb_sdk.Api] = None

    # --------------------------------------------------------------------- #
    # API initialization (lazy)
    # --------------------------------------------------------------------- #

    @property
    def api(self) -> wandb_sdk.Api:
        """Lazily initialize the WandB API client.

        Uses api_key from config if provided, otherwise falls back
        to ~/.netrc authentication.
        """
        if self._api is None:
            logger.info(
                "Initializing WandB API for %s/%s",
                self.config.entity, self.config.project,
            )
            kwargs: dict[str, Any] = {}
            if self.config.api_key:
                kwargs["api_key"] = self.config.api_key
            # If no api_key, wandb.Api() will use ~/.netrc automatically
            self._api = wandb_sdk.Api(**kwargs)
        return self._api

    @property
    def project_path(self) -> str:
        return f"{self.config.entity}/{self.config.project}"

    # --------------------------------------------------------------------- #
    # 1. List Runs (SPEC §8.1)
    # --------------------------------------------------------------------- #

    def list_runs(
        self,
        filters: Optional[dict[str, Any]] = None,
        order: str = "-created_at",
    ) -> list[RunInfo]:
        """Fetch all runs in the WandB project.

        Args:
            filters: MongoDB-style filter dict for wandb API.
            order: Sort order (default: newest first).

        Returns:
            List of RunInfo objects.
        """
        logger.info("Listing runs in %s", self.project_path)
        runs = self._retry_api_call(
            lambda: list(self.api.runs(
                path=self.project_path,
                filters=filters or {},
                order=order,
            ))
        )

        result = []
        for run in runs:
            info = RunInfo(
                run_id=run.id,
                name=run.name or "",
                state=run.state or "unknown",
                created_at=getattr(run, "createdAt", ""),
                config=dict(run.config) if run.config else {},
                tags=list(run.tags) if run.tags else [],
            )
            result.append(info)

        logger.info("Found %d runs", len(result))
        return result

    # --------------------------------------------------------------------- #
    # 2. List Checkpoints for a Run (via file listing — fast)
    # --------------------------------------------------------------------- #

    def list_checkpoints(
        self,
        run_id: str,
    ) -> list[CheckpointInfo]:
        """Find all steps with validation videos by scanning file names.

        Uses run.files() instead of scan_history for speed — the file
        listing is much faster on large runs (81k+ steps).

        Args:
            run_id: WandB run ID.

        Returns:
            List of CheckpointInfo sorted by training step.
        """
        logger.info("Scanning checkpoints for run %s (via file listing)", run_id)
        run = self._retry_api_call(
            lambda: self.api.run(f"{self.project_path}/{run_id}")
        )

        files = self._retry_api_call(lambda: list(run.files()))

        # Group video files by step number
        step_counts: dict[int, int] = {}
        for f in files:
            if not f.name.endswith(".mp4"):
                continue
            m = _STEP_PATTERN.search(f.name)
            if m:
                step = int(m.group(1))
                step_counts[step] = step_counts.get(step, 0) + 1

        checkpoints = [
            CheckpointInfo(
                checkpoint_id=CheckpointInfo.make_id(run_id, step),
                training_step=step,
                wandb_run_id=run_id,
                video_count=count,
                source=CheckpointSource.ROUND_NUMBER,
            )
            for step, count in step_counts.items()
        ]

        checkpoints.sort(key=lambda c: c.training_step)
        logger.info(
            "Found %d checkpoints for run %s (%d total videos)",
            len(checkpoints), run_id, sum(step_counts.values()),
        )
        return checkpoints

    # --------------------------------------------------------------------- #
    # 3. Fetch Videos for a Checkpoint (caption-based — SPEC §8.1, §8.2)
    # --------------------------------------------------------------------- #

    def fetch_videos(
        self,
        run_id: str,
        step: int,
    ) -> list[VideoInfo]:
        """Retrieve validation videos for a given run + step.

        Scans the run history at the specified step for the
        `validation_videos_40_steps` entry, which contains a dict of
        32 video-file objects. Each has a caption (prompt ID), sha256
        (content hash), path (WandB filename), and size.

        Args:
            run_id: WandB run ID.
            step: Training step number.

        Returns:
            List of VideoInfo objects sorted by caption index.
        """
        checkpoint_id = CheckpointInfo.make_id(run_id, step)
        logger.info("Fetching videos for %s at step %d", run_id, step)

        run = self._retry_api_call(
            lambda: self.api.run(f"{self.project_path}/{run_id}")
        )

        # Scan history at the specific step for the validation key
        validation_key = self.config.validation_key
        history_rows = self._retry_api_call(
            lambda: list(run.scan_history(
                min_step=step - 1,
                max_step=step + 1,
                keys=["_step", validation_key],
                page_size=10,
            ))
        )

        videos: list[VideoInfo] = []
        for row in history_rows:
            row_step = int(row.get("_step", -1))
            if row_step != step:
                continue

            val = row.get(validation_key)
            if val is None:
                continue

            # Extract video-file entries from the validation dict
            raw_videos = self._extract_video_entries(val)

            for entry in raw_videos:
                caption = entry.get("caption", "")
                sha256 = entry.get("sha256", "")
                path = entry.get("path", "")
                size = entry.get("size")

                # Parse caption into structured prompt info
                prompt = PromptInfo.from_caption(caption)

                # Build the video URL from the file path
                # The URL will be resolved via run.file(path).url at download time
                video = VideoInfo(
                    video_id=VideoInfo.make_id(checkpoint_id, prompt.prompt_id),
                    checkpoint_id=checkpoint_id,
                    prompt_id=prompt.prompt_id,
                    wandb_url="",  # Resolved lazily via wandb_path
                    wandb_path=path,
                    training_step=step,
                    caption=caption,
                    sha256=sha256,
                    action_label=prompt.action_label,
                    size_bytes=int(size) if size else 0,
                )
                videos.append(video)

            break  # Found the step, no need to continue

        # Sort by caption index (parsed from the "NN" prefix)
        videos.sort(key=lambda v: _caption_sort_key(v.caption))

        logger.info(
            "Found %d videos for %s at step %d",
            len(videos), run_id, step,
        )
        return videos

    def fetch_captions(
        self,
        run_id: str,
        step: int,
    ) -> list[PromptInfo]:
        """Fetch the ordered list of prompt captions for a step.

        Convenience wrapper: calls fetch_videos() and extracts the
        caption metadata for each video.

        Args:
            run_id: WandB run ID.
            step: Training step number.

        Returns:
            List of PromptInfo objects sorted by caption index.
        """
        videos = self.fetch_videos(run_id, step)
        return [PromptInfo.from_caption(v.caption) for v in videos]

    # --------------------------------------------------------------------- #
    # 4. Fetch Optical Flow Scores (SPEC §8.1)
    # --------------------------------------------------------------------- #

    def fetch_optical_flow(
        self,
        run_id: str,
        metric_key: str = "metrics/mf_angle_err_mean",
    ) -> dict[int, float]:
        """Retrieve optical flow / metric scores for checkpoint pre-filtering.

        Args:
            run_id: WandB run ID.
            metric_key: History key containing the metric.

        Returns:
            Dict mapping training step → score.
            Missing scores are omitted (not zero — SPEC §8.2).
        """
        logger.info("Fetching metrics ('%s') for run %s", metric_key, run_id)
        run = self._retry_api_call(
            lambda: self.api.run(f"{self.project_path}/{run_id}")
        )

        history = self._retry_api_call(
            lambda: list(run.scan_history(
                keys=["_step", metric_key],
                page_size=1000,
            ))
        )

        scores = {}
        for row in history:
            step = int(row.get("_step", 0))
            score = row.get(metric_key)
            if score is not None:
                try:
                    scores[step] = float(score)
                except (TypeError, ValueError):
                    logger.warning(
                        "Invalid metric value at step %d: %r",
                        step, score,
                    )

        logger.info(
            "Found metric scores for %d steps in run %s",
            len(scores), run_id,
        )
        return scores

    # --------------------------------------------------------------------- #
    # Ingestion — high-level operation combining fetch + cache
    # --------------------------------------------------------------------- #

    def ingest_checkpoint(
        self,
        run_id: str,
        step: int,
    ) -> IngestionResult:
        """Ingest all validation videos for one checkpoint.

        Fetches video metadata from WandB, downloads them to the local
        cache, and returns a summary of the operation.

        Args:
            run_id: WandB run ID.
            step: Training step number.

        Returns:
            IngestionResult summarizing what happened.

        Raises:
            WandBClientError: If the client has no cache configured.
        """
        if self.cache is None:
            raise WandBClientError(
                "Cannot ingest videos without a configured VideoCache"
            )

        checkpoint_id = CheckpointInfo.make_id(run_id, step)
        result = IngestionResult(
            checkpoint_id=checkpoint_id,
            run_id=run_id,
            training_step=step,
            started_at=datetime.now(timezone.utc),
        )

        logger.info(
            "Ingesting checkpoint %s (run=%s, step=%d)",
            checkpoint_id, run_id, step,
        )

        # Fetch video metadata
        try:
            videos = self.fetch_videos(run_id, step)
        except Exception as exc:
            result.errors.append(f"Failed to fetch video list: {exc}")
            result.completed_at = datetime.now(timezone.utc)
            return result

        result.videos_found = len(videos)

        # Resolve URLs and download each video
        run = self._retry_api_call(
            lambda: self.api.run(f"{self.project_path}/{run_id}")
        )

        for video in videos:
            if self.cache.is_cached(video):
                result.videos_cached += 1
                continue

            try:
                # Resolve the WandB path to a download URL
                if video.wandb_path and not video.wandb_url:
                    try:
                        f = run.file(video.wandb_path)
                        url = f.url
                    except Exception:
                        url = video.wandb_url
                    # Create a new VideoInfo with resolved URL
                    video = VideoInfo(
                        video_id=video.video_id,
                        checkpoint_id=video.checkpoint_id,
                        prompt_id=video.prompt_id,
                        wandb_url=url,
                        wandb_path=video.wandb_path,
                        training_step=video.training_step,
                        caption=video.caption,
                        sha256=video.sha256,
                        action_label=video.action_label,
                        size_bytes=video.size_bytes,
                    )

                self.cache.get_or_download(video)
                result.videos_downloaded += 1
            except Exception as exc:
                result.videos_unavailable += 1
                result.errors.append(
                    f"Failed to download {video.video_id}: {exc}"
                )
                logger.warning(
                    "Video %s marked unavailable: %s",
                    video.video_id, exc,
                )

        result.completed_at = datetime.now(timezone.utc)
        logger.info(
            "Ingestion complete: %d found, %d cached, %d downloaded, %d unavailable",
            result.videos_found, result.videos_cached,
            result.videos_downloaded, result.videos_unavailable,
        )
        return result

    # --------------------------------------------------------------------- #
    # Retry logic (SPEC §8.4)
    # --------------------------------------------------------------------- #

    def _retry_api_call(
        self,
        fn: Any,
        max_retries: int = 5,
        initial_backoff: float = 1.0,
        max_backoff: float = 60.0,
    ) -> Any:
        """Execute a WandB API call with exponential backoff.

        Retries on rate limit (429) and transient network errors.
        """
        backoff = initial_backoff
        last_error: Optional[Exception] = None

        for attempt in range(1, max_retries + 1):
            try:
                return fn()
            except Exception as exc:
                last_error = exc
                exc_str = str(exc).lower()

                # Check for rate limiting or transient errors
                is_retryable = any(
                    indicator in exc_str
                    for indicator in ("429", "rate limit", "timeout", "connection")
                )

                if not is_retryable or attempt == max_retries:
                    logger.error(
                        "API call failed (attempt %d/%d, not retryable): %s",
                        attempt, max_retries, exc,
                    )
                    raise

                logger.warning(
                    "API call failed (attempt %d/%d), retrying in %.1fs: %s",
                    attempt, max_retries, backoff, exc,
                )
                time.sleep(backoff)
                backoff = min(backoff * 2, max_backoff)

        # Should not reach here, but just in case
        raise last_error  # type: ignore[misc]

    # --------------------------------------------------------------------- #
    # Video entry extraction helpers
    # --------------------------------------------------------------------- #

    @staticmethod
    def _extract_video_entries(val: Any) -> list[dict]:
        """Extract video-file entries from a WandB validation log entry.

        The `validation_videos_40_steps` value is a dict that can contain:
        - Direct video-file dicts as values
        - Lists of video-file dicts
        - Nested structures

        Returns a flat list of dicts with _type="video-file".
        """
        entries: list[dict] = []

        if not isinstance(val, dict):
            return entries

        for key, item in val.items():
            if isinstance(item, list):
                for entry in item:
                    if isinstance(entry, dict) and entry.get("_type") == "video-file":
                        entries.append(entry)
            elif isinstance(item, dict) and item.get("_type") == "video-file":
                entries.append(item)

        return entries


def _caption_sort_key(caption: str) -> int:
    """Extract the numeric index from a caption for sorting.

    "00 Val-00: W" → 0, "31 Doom-03: key+camera excl rand" → 31
    """
    m = re.match(r"^(\d+)", caption)
    return int(m.group(1)) if m else 999
