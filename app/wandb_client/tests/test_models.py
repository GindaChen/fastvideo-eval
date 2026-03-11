"""Tests for domain models — including the new PromptInfo caption parser."""

from __future__ import annotations

from app.wandb_client.models import (
    ActionCategory,
    CheckpointInfo,
    CheckpointSource,
    IngestionResult,
    PromptInfo,
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
        assert ckpt.video_count == 32


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
        assert v.caption == ""
        assert v.sha256 == ""
        assert v.action_label == ""
        assert v.size_bytes == 0

    def test_with_caption_fields(self):
        v = VideoInfo(
            video_id="v1",
            checkpoint_id="ckpt1",
            prompt_id="val_00_w",
            wandb_url="",
            training_step=500,
            caption="00 Val-00: W",
            sha256="1865ff9a7e9e69163fae",
            action_label="W",
            wandb_path="media/videos/validation_videos_40_steps_500_1865ff9a7e9e.mp4",
            size_bytes=298869,
        )
        assert v.caption == "00 Val-00: W"
        assert v.sha256 == "1865ff9a7e9e69163fae"
        assert v.action_label == "W"
        assert v.size_bytes == 298869


class TestRunInfo:

    def test_display_name_uses_name(self):
        r = RunInfo(run_id="abc", name="my-run", state="finished", created_at="2026-01-01")
        assert r.display_name == "my-run"

    def test_display_name_fallback_to_id(self):
        r = RunInfo(run_id="abc123", name="", state="finished", created_at="2026-01-01")
        assert r.display_name == "abc123"


class TestPromptInfoFromCaption:

    def test_single_key_w(self):
        p = PromptInfo.from_caption("00 Val-00: W")
        assert p.index == 0
        assert p.label == "Val-00"
        assert p.action_label == "W"
        assert p.category == ActionCategory.SINGLE_KEY
        assert p.source == "Val"
        assert p.prompt_id == "val_00_w"

    def test_single_camera_u(self):
        p = PromptInfo.from_caption("04 Val-04: u")
        assert p.index == 4
        assert p.action_label == "u"
        assert p.category == ActionCategory.SINGLE_CAMERA

    def test_key_rand(self):
        p = PromptInfo.from_caption("08 Val-00: key rand")
        assert p.index == 8
        assert p.action_label == "key rand"
        assert p.category == ActionCategory.RANDOM_KEY

    def test_camera_rand(self):
        p = PromptInfo.from_caption("10 Val-02: camera rand")
        assert p.category == ActionCategory.RANDOM_CAMERA

    def test_combined_excl(self):
        p = PromptInfo.from_caption("12 Val-00: key+camera excl rand")
        assert p.category == ActionCategory.COMBINED_EXCL

    def test_combined(self):
        p = PromptInfo.from_caption("14 Val-02: key+camera rand")
        assert p.category == ActionCategory.COMBINED

    def test_simultaneous(self):
        p = PromptInfo.from_caption("16 Val-04: (simultaneous) key rand")
        assert p.category == ActionCategory.SIMULTANEOUS

    def test_multi_key(self):
        p = PromptInfo.from_caption("20 Val-08: W+A")
        assert p.action_label == "W+A"
        assert p.category == ActionCategory.MULTI_KEY

    def test_still(self):
        p = PromptInfo.from_caption("22 Val-08: Still")
        assert p.category == ActionCategory.STILL

    def test_frame4(self):
        p = PromptInfo.from_caption("24 Val-06: key+camera excl rand Frame 4")
        assert p.category == ActionCategory.ALT_FRAME

    def test_training(self):
        p = PromptInfo.from_caption("26 Train-00")
        assert p.index == 26
        assert p.label == "Train-00"
        assert p.action_label == ""
        assert p.category == ActionCategory.TRAINING
        assert p.source == "Train"

    def test_doom(self):
        p = PromptInfo.from_caption("28 Doom-00: W")
        assert p.index == 28
        assert p.action_label == "W"
        assert p.category == ActionCategory.DOOM
        assert p.source == "Doom"

    def test_doom_combined(self):
        p = PromptInfo.from_caption("31 Doom-03: key+camera excl rand")
        assert p.category == ActionCategory.DOOM

    def test_unparseable_fallback(self):
        p = PromptInfo.from_caption("weird format")
        assert p.index == 0
        assert p.caption == "weird format"
        assert p.prompt_id == "weird_format"


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
