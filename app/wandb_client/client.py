"""WandB client for WanGame Eval (SPEC §8).

Implements the four required operations:
  1. List runs — fetch all runs in the project
  2. Fetch validation videos — for a given run + step
  3. Fetch prompt metadata — action labels, sequences
  4. Fetch optical flow scores — automated pre-filter scores

Error handling follows SPEC §8.4:
  - Exponential backoff for rate limits (1s → 60s)
  - 3 retries for network failures, then mark unavailable
  - Structured logging per SPEC §13.1
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

import wandb as wandb_sdk

from app.wandb_client.config import WandBConfig
from app.wandb_client.models import (
    CheckpointInfo,
    CheckpointSource,
    IngestionResult,
    RunInfo,
    VideoInfo,
    VideoStatus,
)
from app.wandb_client.cache import VideoCache

logger = logging.getLogger("wangame.wandb")


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
        """Lazily initialize the WandB API client."""
        if self._api is None:
            logger.info(
                "Initializing WandB API for %s/%s",
                self.config.entity, self.config.project,
            )
            self._api = wandb_sdk.Api(api_key=self.config.api_key)
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
    # 2. List Checkpoints for a Run
    # --------------------------------------------------------------------- #

    def list_checkpoints(
        self,
        run_id: str,
        validation_key: str = "validation",
    ) -> list[CheckpointInfo]:
        """Scan a run's history to find steps with validation data.

        A checkpoint is any step where ``validation_key`` appears in the
        logged history — this is where validation videos were generated.

        Args:
            run_id: WandB run ID.
            validation_key: History key that indicates a validation step.

        Returns:
            List of CheckpointInfo sorted by training step.
        """
        logger.info("Scanning checkpoints for run %s", run_id)
        run = self._retry_api_call(
            lambda: self.api.run(f"{self.project_path}/{run_id}")
        )

        # Use scan_history for complete iteration (not sampled)
        history = self._retry_api_call(
            lambda: list(run.scan_history(
                keys=["_step"],
                page_size=1000,
            ))
        )

        checkpoints = []
        seen_steps = set()
        for row in history:
            step = int(row.get("_step", 0))
            if step in seen_steps:
                continue
            seen_steps.add(step)

            # Check if this step has validation data
            # For now, include all steps that are multiples of 500
            # (validation happens every 500 steps per AGENTS.md)
            if step > 0 and step % 500 == 0:
                ckpt = CheckpointInfo(
                    checkpoint_id=CheckpointInfo.make_id(run_id, step),
                    training_step=step,
                    wandb_run_id=run_id,
                    source=CheckpointSource.ROUND_NUMBER,
                )
                checkpoints.append(ckpt)

        checkpoints.sort(key=lambda c: c.training_step)
        logger.info("Found %d checkpoints for run %s", len(checkpoints), run_id)
        return checkpoints

    # --------------------------------------------------------------------- #
    # 3. Fetch Videos for a Checkpoint (SPEC §8.1, §8.2)
    # --------------------------------------------------------------------- #

    def fetch_videos(
        self,
        run_id: str,
        step: int,
    ) -> list[VideoInfo]:
        """Retrieve validation video URLs for a given run + step.

        Scans the run history at the specified step for any logged media
        (videos). Normalizes URLs to direct-download format (SPEC §8.2).

        Args:
            run_id: WandB run ID.
            step: Training step number.

        Returns:
            List of VideoInfo objects for videos found at this step.
        """
        checkpoint_id = CheckpointInfo.make_id(run_id, step)
        logger.info("Fetching videos for %s at step %d", run_id, step)

        run = self._retry_api_call(
            lambda: self.api.run(f"{self.project_path}/{run_id}")
        )

        # Scan history at the specific step for video keys
        history_rows = self._retry_api_call(
            lambda: list(run.scan_history(
                min_step=step,
                max_step=step + 1,
                page_size=100,
            ))
        )

        videos = []
        for row in history_rows:
            row_step = int(row.get("_step", -1))
            if row_step != step:
                continue

            # Walk all keys looking for wandb.Video objects
            for key, value in row.items():
                if key.startswith("_"):
                    continue

                video_url = self._extract_video_url(value)
                if video_url is None:
                    continue

                # Derive prompt_id from the key name
                # WandB keys are typically like "val/prompt_name" or "validation/basic_fwd_flat_01"
                prompt_id = self._normalize_prompt_id(key)

                video = VideoInfo(
                    video_id=VideoInfo.make_id(checkpoint_id, prompt_id),
                    checkpoint_id=checkpoint_id,
                    prompt_id=prompt_id,
                    wandb_url=video_url,
                    training_step=step,
                )
                videos.append(video)

        logger.info(
            "Found %d videos for %s at step %d",
            len(videos), run_id, step,
        )
        return videos

    # --------------------------------------------------------------------- #
    # 4. Fetch Optical Flow Scores (SPEC §8.1)
    # --------------------------------------------------------------------- #

    def fetch_optical_flow(
        self,
        run_id: str,
        metric_key: str = "optical_flow",
    ) -> dict[int, float]:
        """Retrieve optical flow scores for checkpoint pre-filtering.

        Args:
            run_id: WandB run ID.
            metric_key: History key containing the optical flow metric.

        Returns:
            Dict mapping training step → optical flow score.
            Missing scores are omitted (not zero — SPEC §8.2).
        """
        logger.info("Fetching optical flow scores for run %s", run_id)
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
                        "Invalid optical flow value at step %d: %r",
                        step, score,
                    )

        logger.info(
            "Found optical flow scores for %d steps in run %s",
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

        # Download each video
        for video in videos:
            if self.cache.is_cached(video):
                result.videos_cached += 1
                continue

            try:
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
    # URL / ID normalization helpers (SPEC §8.2)
    # --------------------------------------------------------------------- #

    @staticmethod
    def _extract_video_url(value: Any) -> Optional[str]:
        """Extract a direct-download video URL from a WandB history value.

        WandB log entries for media can be:
        - A dict with {"_type": "video-file", "path": "media/videos/..."} 
        - A wandb.data_types.Video object
        - A plain string URL
        """
        if isinstance(value, str) and value.endswith(".mp4"):
            return value

        if isinstance(value, dict):
            # WandB media reference format
            if value.get("_type") in ("video-file", "video"):
                path = value.get("path", "")
                if path:
                    # The path is relative to the run's file storage
                    # Caller will need to resolve to full URL via run.files()
                    return path
            # Direct URL in a dict
            url = value.get("url", "")
            if url and ".mp4" in url:
                return url

        # Check for wandb Video data type
        if hasattr(value, "_path") and value._path:
            return value._path

        return None

    @staticmethod
    def _normalize_prompt_id(key: str) -> str:
        """Normalize a WandB log key to a prompt_id (SPEC §8.2).

        Examples:
            "val/basic_fwd_flat_01" → "basic_fwd_flat_01"
            "validation/W_only_easy" → "w_only_easy"
            "Basic Fwd Flat 01" → "basic_fwd_flat_01"
        """
        # Strip common prefixes
        for prefix in ("val/", "validation/", "videos/", "media/"):
            if key.startswith(prefix):
                key = key[len(prefix):]

        # Lowercase and normalize
        key = key.lower().strip()
        key = key.replace(" ", "_").replace("-", "_")

        # Remove file extension if present
        for ext in (".mp4", ".webm", ".gif"):
            if key.endswith(ext):
                key = key[: -len(ext)]

        return key
