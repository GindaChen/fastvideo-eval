"""Configuration loader for WanGame Eval (SPEC §6).

Loads config.yaml, resolves $ENV_VAR references, and validates required fields.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class ConfigError(Exception):
    """Raised when configuration is invalid or incomplete."""


# --------------------------------------------------------------------------- #
# Typed config sections
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class WandBConfig:
    """WandB connection settings (SPEC §6.1 wandb section)."""
    project: str
    entity: str
    api_key: str = ""  # Empty = fall back to ~/.netrc
    default_run_id: str = ""  # Pre-configured run for convenience
    validation_key: str = "validation_videos_40_steps"


@dataclass(frozen=True)
class EvaluationConfig:
    """Evaluation settings (SPEC §6.1 evaluation section)."""
    chunk_size: int = 20
    default_playback_speed: str = "2x"
    auto_play: bool = True
    max_evaluators: int = 10
    require_all_chunks: bool = False


@dataclass(frozen=True)
class ScoringConfig:
    """Scoring settings (SPEC §6.1 scoring section)."""
    easy_tolerance: float = 0.0
    hard_tolerance: float = 0.15
    min_videos_per_category: int = 5
    aggregation_method: str = "weighted"
    category_weights: dict[str, float] = field(default_factory=lambda: {
        "basic_movement": 0.25,
        "camera_control": 0.20,
        "jump_sprint": 0.15,
        "hotbar": 0.10,
        "stability": 0.15,
        "combinations": 0.15,
    })


@dataclass(frozen=True)
class ServerConfig:
    """Server settings (SPEC §6.1 server section)."""
    host: str = "0.0.0.0"
    port: int = 8080
    database: str = "eval.db"


@dataclass(frozen=True)
class BackupConfig:
    """Backup settings (SPEC §6.1 backup section)."""
    enabled: bool = True
    interval_minutes: int = 5
    retention_count: int = 10
    backup_dir: str = "backups/"


@dataclass
class AppConfig:
    """Top-level application config — aggregates all sections."""
    wandb: WandBConfig
    evaluation: EvaluationConfig
    scoring: ScoringConfig
    server: ServerConfig
    backup: BackupConfig


# --------------------------------------------------------------------------- #
# Environment variable resolution
# --------------------------------------------------------------------------- #

_ENV_PATTERN = re.compile(r"^\$([A-Za-z_][A-Za-z0-9_]*)$")


def _resolve_env_vars(data: Any) -> Any:
    """Recursively resolve $ENV_VAR references in config values (SPEC §6.2)."""
    if isinstance(data, str):
        m = _ENV_PATTERN.match(data)
        if m:
            var_name = m.group(1)
            value = os.environ.get(var_name)
            if value is None:
                raise ConfigError(
                    f"Environment variable ${var_name} is required but not set"
                )
            return value
        return data
    elif isinstance(data, dict):
        return {k: _resolve_env_vars(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [_resolve_env_vars(item) for item in data]
    return data


# --------------------------------------------------------------------------- #
# Config loading & validation
# --------------------------------------------------------------------------- #

def _validate_weights(weights: dict[str, float]) -> None:
    """SPEC §6.3: category weights must sum to 1.0."""
    total = sum(weights.values())
    if abs(total - 1.0) > 1e-6:
        raise ConfigError(
            f"Category weights must sum to 1.0, got {total:.6f}"
        )


def load_config(config_path: str | Path | None = None) -> AppConfig:
    """Load, resolve, and validate the application config.

    Args:
        config_path: Path to config.yaml. Defaults to repo-root config.yaml.

    Returns:
        Fully validated AppConfig instance.

    Raises:
        ConfigError: If config is missing, invalid, or env vars are unset.
        FileNotFoundError: If config file doesn't exist.
    """
    if config_path is None:
        config_path = Path(__file__).resolve().parents[2] / "config.yaml"
    else:
        config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path) as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ConfigError(f"Config must be a YAML mapping, got {type(raw).__name__}")

    # Resolve all $ENV references
    resolved = _resolve_env_vars(raw)

    # Build typed sections with defaults for missing optional sections
    wandb_section = resolved.get("wandb", {})
    if not wandb_section:
        raise ConfigError("Missing required 'wandb' section in config")

    for key in ("project", "entity"):
        if key not in wandb_section:
            raise ConfigError(f"Missing required wandb.{key} in config")

    wandb_cfg = WandBConfig(
        project=wandb_section["project"],
        entity=wandb_section["entity"],
        api_key=wandb_section.get("api_key", ""),
        default_run_id=wandb_section.get("default_run_id", ""),
        validation_key=wandb_section.get("validation_key", "validation_videos_40_steps"),
    )

    eval_section = resolved.get("evaluation", {})
    eval_cfg = EvaluationConfig(**{
        k: v for k, v in eval_section.items()
        if k in EvaluationConfig.__dataclass_fields__
    })

    scoring_section = resolved.get("scoring", {})
    scoring_cfg = ScoringConfig(**{
        k: v for k, v in scoring_section.items()
        if k in ScoringConfig.__dataclass_fields__
    })

    _validate_weights(scoring_cfg.category_weights)

    server_section = resolved.get("server", {})
    server_cfg = ServerConfig(**{
        k: v for k, v in server_section.items()
        if k in ServerConfig.__dataclass_fields__
    })

    backup_section = resolved.get("backup", {})
    backup_cfg = BackupConfig(**{
        k: v for k, v in backup_section.items()
        if k in BackupConfig.__dataclass_fields__
    })

    return AppConfig(
        wandb=wandb_cfg,
        evaluation=eval_cfg,
        scoring=scoring_cfg,
        server=server_cfg,
        backup=backup_cfg,
    )
