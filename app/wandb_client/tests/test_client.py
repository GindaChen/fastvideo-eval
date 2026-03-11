"""Tests for WandB client — video entry extraction and caption sorting."""

from __future__ import annotations

from app.wandb_client.client import WandBClient, _caption_sort_key


class TestExtractVideoEntries:

    def test_extracts_from_list_values(self):
        val = {
            "videos": [
                {"_type": "video-file", "caption": "00 Val-00: W", "sha256": "abc", "path": "media/v1.mp4"},
                {"_type": "video-file", "caption": "01 Val-01: S", "sha256": "def", "path": "media/v2.mp4"},
            ]
        }
        entries = WandBClient._extract_video_entries(val)
        assert len(entries) == 2
        assert entries[0]["caption"] == "00 Val-00: W"
        assert entries[1]["caption"] == "01 Val-01: S"

    def test_extracts_from_direct_dict_values(self):
        val = {
            "0": {"_type": "video-file", "caption": "00 Val-00: W", "sha256": "abc"},
            "1": {"_type": "video-file", "caption": "01 Val-01: S", "sha256": "def"},
        }
        entries = WandBClient._extract_video_entries(val)
        assert len(entries) == 2

    def test_ignores_non_video_entries(self):
        val = {
            "_type": "videos",
            "count": 32,
            "0": {"_type": "video-file", "caption": "00 Val-00: W", "sha256": "abc"},
        }
        entries = WandBClient._extract_video_entries(val)
        assert len(entries) == 1
        assert entries[0]["caption"] == "00 Val-00: W"

    def test_empty_dict(self):
        assert WandBClient._extract_video_entries({}) == []

    def test_non_dict_returns_empty(self):
        assert WandBClient._extract_video_entries("not a dict") == []
        assert WandBClient._extract_video_entries(42) == []
        assert WandBClient._extract_video_entries(None) == []


class TestCaptionSortKey:

    def test_basic_caption(self):
        assert _caption_sort_key("00 Val-00: W") == 0
        assert _caption_sort_key("31 Doom-03: key+camera excl rand") == 31

    def test_two_digit_index(self):
        assert _caption_sort_key("08 Val-00: key rand") == 8
        assert _caption_sort_key("16 Val-04: (simultaneous) key rand") == 16

    def test_non_numeric_prefix(self):
        assert _caption_sort_key("unknown caption") == 999

    def test_empty_string(self):
        assert _caption_sort_key("") == 999
