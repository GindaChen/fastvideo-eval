"""Tests for domain models."""

from __future__ import annotations

from app.wandb_client.models import (
    CheckpointInfo,
    CheckpointSource,
    IngestionResult,
    RunInfo,
    VideoInfo,
    VideoStatus,
)


class TestCheckpointInfo:

    def test_make_id(self):
        assert CheckpointInfo.make_id("run123", 5000) == "run123_step5000"

    def test_frozen(self):
        ckpt = CheckpointInfo(
            checkpoint_id="ckpt1",
            training_step=1000,
            wandb_run_id="run1",
        )
        assert ckpt.source == CheckpointSource.ROUND_NUMBER
        assert ckpt.optical_flow_score is None


class TestVideoInfo:

    def test_make_id(self):
        assert VideoInfo.make_id("ckpt1", "basic_fwd") == "ckpt1_basic_fwd"

    def test_defaults(self):
        v = VideoInfo(
            video_id="v1",
            checkpoint_id="ckpt1",
            prompt_id="test",
            wandb_url="https://example.com/v.mp4",
            training_step=500,
        )
        assert v.has_action_overlay is True
        assert v.duration_frames == 77
        assert v.status == VideoStatus.AVAILABLE
        assert v.local_path is None


class TestRunInfo:

    def test_display_name_uses_name(self):
        r = RunInfo(run_id="abc", name="my-run", state="finished", created_at="2026-01-01")
        assert r.display_name == "my-run"

    def test_display_name_fallback_to_id(self):
        r = RunInfo(run_id="abc123", name="", state="finished", created_at="2026-01-01")
        assert r.display_name == "abc123"


class TestIngestionResult:

    def test_success(self):
        r = IngestionResult(checkpoint_id="c1", run_id="r1", training_step=500)
        assert r.success is True

    def test_failure_with_errors(self):
        r = IngestionResult(
            checkpoint_id="c1", run_id="r1", training_step=500,
            errors=["download failed"],
        )
        assert r.success is False

    def test_failure_with_unavailable(self):
        r = IngestionResult(
            checkpoint_id="c1", run_id="r1", training_step=500,
            videos_unavailable=2,
        )
        assert r.success is False
