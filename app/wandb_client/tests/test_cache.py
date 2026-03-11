"""Tests for video cache logic."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from app.wandb_client.cache import VideoCache, CacheError
from app.wandb_client.models import VideoInfo, VideoStatus


def _make_video(**overrides) -> VideoInfo:
    defaults = dict(
        video_id="ckpt1_basic_fwd",
        checkpoint_id="ckpt1",
        prompt_id="basic_fwd",
        wandb_url="https://example.com/video.mp4",
        training_step=500,
    )
    defaults.update(overrides)
    return VideoInfo(**defaults)


class TestCachePaths:

    def test_is_cached_false_initially(self, tmp_path: Path):
        cache = VideoCache(tmp_path / "cache")
        video = _make_video()
        assert cache.is_cached(video) is False
        assert cache.local_path(video) is None

    def test_is_cached_true_after_file_exists(self, tmp_path: Path):
        cache = VideoCache(tmp_path / "cache")
        video = _make_video()

        # Simulate a cached file
        dest = tmp_path / "cache" / "ckpt1" / "basic_fwd.mp4"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"fake video data")

        assert cache.is_cached(video) is True
        assert cache.local_path(video) == dest

    def test_empty_file_not_considered_cached(self, tmp_path: Path):
        cache = VideoCache(tmp_path / "cache")
        video = _make_video()

        dest = tmp_path / "cache" / "ckpt1" / "basic_fwd.mp4"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"")  # Empty file

        assert cache.is_cached(video) is False


class TestCacheDownload:

    def test_unavailable_video_raises(self, tmp_path: Path):
        cache = VideoCache(tmp_path / "cache")
        video = _make_video(status=VideoStatus.UNAVAILABLE)

        with pytest.raises(CacheError, match="unavailable"):
            cache.get_or_download(video)

    def test_no_url_raises(self, tmp_path: Path):
        cache = VideoCache(tmp_path / "cache")
        video = _make_video(wandb_url="")

        with pytest.raises(CacheError, match="no WandB URL"):
            cache.get_or_download(video)


class TestCacheManagement:

    def test_cache_size_empty(self, tmp_path: Path):
        cache = VideoCache(tmp_path / "cache")
        assert cache.cache_size_bytes() == 0
        assert cache.video_count() == 0

    def test_cache_size_with_files(self, tmp_path: Path):
        cache = VideoCache(tmp_path / "cache")

        # Create some fake cached files
        for i in range(3):
            f = tmp_path / "cache" / "ckpt1" / f"vid_{i}.mp4"
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(b"x" * 100)

        assert cache.video_count() == 3
        assert cache.cache_size_bytes() == 300

    def test_clear_checkpoint(self, tmp_path: Path):
        cache = VideoCache(tmp_path / "cache")

        # Create files in two checkpoints
        for ckpt in ("ckpt1", "ckpt2"):
            f = tmp_path / "cache" / ckpt / "vid.mp4"
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(b"x")

        deleted = cache.clear_checkpoint("ckpt1")
        assert deleted == 1
        assert cache.video_count() == 1  # ckpt2 still there

    def test_clear_all(self, tmp_path: Path):
        cache = VideoCache(tmp_path / "cache")

        for i in range(5):
            f = tmp_path / "cache" / f"ckpt{i}" / "vid.mp4"
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(b"x")

        deleted = cache.clear_all()
        assert deleted == 5
        assert cache.video_count() == 0


class TestCacheSizeHuman:

    def test_bytes(self, tmp_path: Path):
        cache = VideoCache(tmp_path / "cache")
        f = tmp_path / "cache" / "ckpt" / "v.mp4"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"x" * 500)
        assert "B" in cache.cache_size_human()

    def test_megabytes(self, tmp_path: Path):
        cache = VideoCache(tmp_path / "cache")
        f = tmp_path / "cache" / "ckpt" / "v.mp4"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"x" * (2 * 1024 * 1024))
        assert "MB" in cache.cache_size_human()
