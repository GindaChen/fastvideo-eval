"""Local video cache for WanGame Eval (SPEC §8.3).

Cache layout:  <cache_dir>/<checkpoint_id>/<prompt_id>.mp4
Videos are immutable per checkpoint × prompt — no auto-invalidation.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Optional

import requests

from app.wandb_client.models import VideoInfo, VideoStatus

logger = logging.getLogger("wangame.cache")


class CacheError(Exception):
    """Raised on cache I/O failures."""


class VideoCache:
    """Manages local copies of WandB validation videos.

    Args:
        cache_dir: Root directory for cached videos.
        timeout: HTTP download timeout in seconds.
    """

    def __init__(self, cache_dir: str | Path, timeout: int = 120):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout

    # --------------------------------------------------------------------- #
    # Path helpers
    # --------------------------------------------------------------------- #

    def _video_path(self, video: VideoInfo) -> Path:
        """Cache key: <checkpoint_id>/<prompt_id>.mp4 (SPEC §8.3)."""
        return self.cache_dir / video.checkpoint_id / f"{video.prompt_id}.mp4"

    def is_cached(self, video: VideoInfo) -> bool:
        """Check if a video is already downloaded."""
        path = self._video_path(video)
        return path.exists() and path.stat().st_size > 0

    def local_path(self, video: VideoInfo) -> Optional[Path]:
        """Return local path if cached, else None."""
        path = self._video_path(video)
        if path.exists() and path.stat().st_size > 0:
            return path
        return None

    # --------------------------------------------------------------------- #
    # Download
    # --------------------------------------------------------------------- #

    def get_or_download(
        self,
        video: VideoInfo,
        max_retries: int = 3,
    ) -> Path:
        """Return local path, downloading from WandB if necessary.

        Args:
            video: VideoInfo with a valid wandb_url.
            max_retries: Number of download attempts (SPEC §8.4).

        Returns:
            Path to the local .mp4 file.

        Raises:
            CacheError: If download fails after all retries.
        """
        # Fast path — already cached
        cached = self.local_path(video)
        if cached is not None:
            logger.debug("Cache hit: %s", cached)
            return cached

        if video.status == VideoStatus.UNAVAILABLE:
            raise CacheError(f"Video {video.video_id} is marked unavailable")

        if not video.wandb_url:
            raise CacheError(f"Video {video.video_id} has no WandB URL")

        dest = self._video_path(video)
        dest.parent.mkdir(parents=True, exist_ok=True)

        last_error: Optional[Exception] = None
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(
                    "Downloading video %s (attempt %d/%d)",
                    video.video_id, attempt, max_retries,
                )
                self._download_file(video.wandb_url, dest)
                logger.info("Cached video %s → %s", video.video_id, dest)
                return dest
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Download attempt %d failed for %s: %s",
                    attempt, video.video_id, exc,
                )
                # Clean up partial downloads
                if dest.exists():
                    dest.unlink()

        raise CacheError(
            f"Failed to download {video.video_id} after {max_retries} attempts: "
            f"{last_error}"
        )

    def _download_file(self, url: str, dest: Path) -> None:
        """Stream-download a file to disk."""
        resp = requests.get(url, stream=True, timeout=self.timeout)
        resp.raise_for_status()

        tmp_dest = dest.with_suffix(".mp4.tmp")
        try:
            with open(tmp_dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            # Atomic-ish rename
            tmp_dest.rename(dest)
        except Exception:
            if tmp_dest.exists():
                tmp_dest.unlink()
            raise

    # --------------------------------------------------------------------- #
    # Cache management
    # --------------------------------------------------------------------- #

    def cache_size_bytes(self) -> int:
        """Total size of all cached files in bytes."""
        total = 0
        for path in self.cache_dir.rglob("*.mp4"):
            total += path.stat().st_size
        return total

    def cache_size_human(self) -> str:
        """Human-readable cache size."""
        size = self.cache_size_bytes()
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    def video_count(self) -> int:
        """Number of cached video files."""
        return len(list(self.cache_dir.rglob("*.mp4")))

    def clear_checkpoint(self, checkpoint_id: str) -> int:
        """Remove all cached videos for a checkpoint.

        Returns:
            Number of files deleted.
        """
        ckpt_dir = self.cache_dir / checkpoint_id
        if not ckpt_dir.exists():
            return 0
        count = len(list(ckpt_dir.glob("*.mp4")))
        shutil.rmtree(ckpt_dir)
        logger.info("Cleared cache for checkpoint %s (%d files)", checkpoint_id, count)
        return count

    def clear_all(self) -> int:
        """Remove all cached videos.

        Returns:
            Number of files deleted.
        """
        count = self.video_count()
        if self.cache_dir.exists():
            shutil.rmtree(self.cache_dir)
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Cleared entire cache (%d files)", count)
        return count
