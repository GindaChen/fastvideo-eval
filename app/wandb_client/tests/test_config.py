"""Tests for config loading and validation."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from app.wandb_client.config import (
    AppConfig,
    ConfigError,
    WandBConfig,
    load_config,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _write_config(tmp_path: Path, data: dict) -> Path:
    config_path = tmp_path / "config.yaml"
    with open(config_path, "w") as f:
        yaml.dump(data, f)
    return config_path


def _minimal_config(**overrides) -> dict:
    """Return a valid minimal config dict."""
    base = {
        "wandb": {
            "project": "test_project",
            "entity": "test_entity",
            "api_key": "test_key_123",
        },
        "scoring": {
            "category_weights": {
                "basic_movement": 0.25,
                "camera_control": 0.20,
                "jump_sprint": 0.15,
                "hotbar": 0.10,
                "stability": 0.15,
                "combinations": 0.15,
            }
        },
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------- #
# Happy path
# --------------------------------------------------------------------------- #

class TestLoadConfig:

    def test_minimal_valid_config(self, tmp_path: Path):
        config_path = _write_config(tmp_path, _minimal_config())
        cfg = load_config(config_path)

        assert isinstance(cfg, AppConfig)
        assert cfg.wandb.project == "test_project"
        assert cfg.wandb.entity == "test_entity"
        assert cfg.wandb.api_key == "test_key_123"

    def test_defaults_are_applied(self, tmp_path: Path):
        config_path = _write_config(tmp_path, _minimal_config())
        cfg = load_config(config_path)

        # Evaluation defaults
        assert cfg.evaluation.chunk_size == 20
        assert cfg.evaluation.default_playback_speed == "2x"

        # Server defaults
        assert cfg.server.port == 8080
        assert cfg.server.database == "eval.db"

        # Backup defaults
        assert cfg.backup.enabled is True
        assert cfg.backup.retention_count == 10

    def test_custom_values_override_defaults(self, tmp_path: Path):
        data = _minimal_config()
        data["evaluation"] = {"chunk_size": 50, "auto_play": False}
        data["server"] = {"port": 9090}
        config_path = _write_config(tmp_path, data)

        cfg = load_config(config_path)
        assert cfg.evaluation.chunk_size == 50
        assert cfg.evaluation.auto_play is False
        assert cfg.server.port == 9090


# --------------------------------------------------------------------------- #
# Environment variable resolution
# --------------------------------------------------------------------------- #

class TestEnvVarResolution:

    def test_env_var_resolved(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("TEST_WANDB_KEY", "resolved_secret")
        data = _minimal_config()
        data["wandb"]["api_key"] = "$TEST_WANDB_KEY"
        config_path = _write_config(tmp_path, data)

        cfg = load_config(config_path)
        assert cfg.wandb.api_key == "resolved_secret"

    def test_missing_env_var_raises(self, tmp_path: Path, monkeypatch):
        monkeypatch.delenv("NONEXISTENT_VAR_12345", raising=False)
        data = _minimal_config()
        data["wandb"]["api_key"] = "$NONEXISTENT_VAR_12345"
        config_path = _write_config(tmp_path, data)

        with pytest.raises(ConfigError, match="NONEXISTENT_VAR_12345"):
            load_config(config_path)


# --------------------------------------------------------------------------- #
# Validation errors
# --------------------------------------------------------------------------- #

class TestConfigValidation:

    def test_missing_wandb_section(self, tmp_path: Path):
        config_path = _write_config(tmp_path, {"scoring": {"category_weights": {
            "a": 1.0,
        }}})
        with pytest.raises(ConfigError, match="wandb"):
            load_config(config_path)

    def test_missing_wandb_project(self, tmp_path: Path):
        data = _minimal_config()
        del data["wandb"]["project"]
        config_path = _write_config(tmp_path, data)
        with pytest.raises(ConfigError, match="project"):
            load_config(config_path)

    def test_weights_not_summing_to_one(self, tmp_path: Path):
        data = _minimal_config()
        data["scoring"]["category_weights"] = {"a": 0.5, "b": 0.3}
        config_path = _write_config(tmp_path, data)
        with pytest.raises(ConfigError, match="sum to 1.0"):
            load_config(config_path)

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/path/config.yaml")
