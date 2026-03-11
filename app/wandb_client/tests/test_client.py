"""Tests for WandB client — normalization helpers and mocked API calls."""

from __future__ import annotations

from app.wandb_client.client import WandBClient


class TestNormalizePromptId:

    def test_strip_val_prefix(self):
        assert WandBClient._normalize_prompt_id("val/basic_fwd_flat_01") == "basic_fwd_flat_01"

    def test_strip_validation_prefix(self):
        assert WandBClient._normalize_prompt_id("validation/W_only_easy") == "w_only_easy"

    def test_strip_videos_prefix(self):
        assert WandBClient._normalize_prompt_id("videos/test_prompt") == "test_prompt"

    def test_spaces_to_underscores(self):
        assert WandBClient._normalize_prompt_id("Basic Fwd Flat 01") == "basic_fwd_flat_01"

    def test_hyphens_to_underscores(self):
        assert WandBClient._normalize_prompt_id("basic-fwd-flat-01") == "basic_fwd_flat_01"

    def test_strip_mp4_extension(self):
        assert WandBClient._normalize_prompt_id("prompt_name.mp4") == "prompt_name"

    def test_lowercase(self):
        assert WandBClient._normalize_prompt_id("MyPrompt") == "myprompt"

    def test_combined_normalization(self):
        assert WandBClient._normalize_prompt_id("val/W Only Easy.mp4") == "w_only_easy"


class TestExtractVideoUrl:

    def test_plain_mp4_url(self):
        assert WandBClient._extract_video_url("https://cdn.wandb.ai/v.mp4") == "https://cdn.wandb.ai/v.mp4"

    def test_non_mp4_string_returns_none(self):
        assert WandBClient._extract_video_url("just a string") is None

    def test_dict_video_file_type(self):
        val = {"_type": "video-file", "path": "media/videos/step_500.mp4"}
        assert WandBClient._extract_video_url(val) == "media/videos/step_500.mp4"

    def test_dict_with_url(self):
        val = {"url": "https://example.com/video.mp4"}
        assert WandBClient._extract_video_url(val) == "https://example.com/video.mp4"

    def test_dict_without_video_returns_none(self):
        val = {"_type": "table", "data": []}
        assert WandBClient._extract_video_url(val) is None

    def test_none_input(self):
        assert WandBClient._extract_video_url(None) is None

    def test_integer_input(self):
        assert WandBClient._extract_video_url(42) is None
