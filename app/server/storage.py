"""JSONL + JSON file-based storage for WanGame Eval.

Replaces SQLite with simple file-based storage:
  - data/ratings_{evaluator}.jsonl — per-user append-only ratings
  - data/config.json               — server settings (WandB API key, run ID, etc.)

Each evaluator gets their own JSONL file, eliminating concurrent-write issues.
All writes go through helper functions. Human-readable, git-friendly.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Optional

logger = logging.getLogger("wangame.storage")

# Default settings
_DEFAULT_CONFIG = {
    "wandb_api_key": "",
    "wandb_entity": "kaiqin_kong_ucsd",
    "wandb_project": "wangame_1.3b",
    "default_run_id": "fif3z1z4",
    "auth_token": "",
}


class Storage:
    """File-based storage manager.

    Args:
        data_dir: Directory for data files. Created automatically.
    """

    def __init__(self, data_dir: str | Path = "data"):
        self.data_dir = Path(data_dir)
        self._lock = Lock()  # for thread-safe appends
        self._ratings_cache: Optional[list[dict]] = None

    def init(self) -> None:
        """Create data directory and seed config if needed."""
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Seed config.json if it doesn't exist
        config_path = self.data_dir / "config.json"
        if not config_path.exists():
            config_path.write_text(json.dumps(_DEFAULT_CONFIG, indent=2))

        # Migrate legacy single ratings.jsonl → per-user files
        legacy_path = self.data_dir / "ratings.jsonl"
        if legacy_path.exists() and legacy_path.stat().st_size > 0:
            self._migrate_legacy_ratings(legacy_path)

        logger.info("Storage initialized at %s", self.data_dir)

    # ------------------------------------------------------------------ #
    # Settings CRUD
    # ------------------------------------------------------------------ #

    def _config_path(self) -> Path:
        return self.data_dir / "config.json"

    def get_all_settings(self) -> dict[str, str]:
        try:
            return json.loads(self._config_path().read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return dict(_DEFAULT_CONFIG)

    def get_setting(self, key: str) -> Optional[str]:
        settings = self.get_all_settings()
        return settings.get(key)

    def set_setting(self, key: str, value: str) -> None:
        settings = self.get_all_settings()
        settings[key] = value
        self._config_path().write_text(json.dumps(settings, indent=2))

    # ------------------------------------------------------------------ #
    # Ratings (per-user append-only JSONL)
    # ------------------------------------------------------------------ #

    def _ratings_path(self, evaluator: str) -> Path:
        """Per-user ratings file: data/ratings_{evaluator}.jsonl"""
        safe_name = self._safe_evaluator_name(evaluator)
        return self.data_dir / f"ratings_{safe_name}.jsonl"

    @staticmethod
    def _safe_evaluator_name(name: str) -> str:
        """Sanitize evaluator name for use as a filename."""
        import re
        safe = re.sub(r'[^\w\-]', '_', name.strip().lower())
        return safe or "anonymous"

    def _all_ratings_paths(self) -> list[Path]:
        """Glob all per-user ratings files."""
        return sorted(self.data_dir.glob("ratings_*.jsonl"))

    def _invalidate_cache(self):
        self._ratings_cache = None

    def _load_all_ratings(self) -> list[dict[str, Any]]:
        """Load all ratings from all per-user JSONL files. Cached until invalidated."""
        if self._ratings_cache is not None:
            return self._ratings_cache

        ratings = []
        for path in self._all_ratings_paths():
            for line in path.read_text().splitlines():
                line = line.strip()
                if line:
                    try:
                        ratings.append(json.loads(line))
                    except json.JSONDecodeError:
                        logger.warning("Skipping malformed line in %s", path.name)
        self._ratings_cache = ratings
        return ratings

    def _migrate_legacy_ratings(self, legacy_path: Path) -> None:
        """Migrate a single ratings.jsonl into per-user files."""
        logger.info("Migrating legacy ratings.jsonl to per-user files...")
        by_user: dict[str, list[str]] = {}  # evaluator → list of JSON lines
        for line in legacy_path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            evaluator = record.get("evaluator", "anonymous")
            by_user.setdefault(evaluator, []).append(json.dumps(record))

        for evaluator, lines in by_user.items():
            user_path = self._ratings_path(evaluator)
            with open(user_path, "a") as f:
                for l in lines:
                    f.write(l + "\n")
            logger.info("  Migrated %d ratings for '%s'", len(lines), evaluator)

        # Rename legacy file so migration doesn't re-run
        backup = legacy_path.with_suffix(".jsonl.migrated")
        legacy_path.rename(backup)
        logger.info("Legacy ratings.jsonl renamed to %s", backup.name)

    def insert_rating(
        self,
        video_id: str,
        chunk_id: str,
        checkpoint_id: str,
        prompt_id: str,
        rating: str,
        evaluator: str,
        issues: Optional[list[str]] = None,
        free_text: Optional[str] = None,
        voice_note_url: Optional[str] = None,
        playback_speed: Optional[str] = None,
        view_duration_ms: Optional[int] = None,
        supersedes: Optional[str] = None,
        wandb_entity: Optional[str] = None,
        wandb_project: Optional[str] = None,
        wandb_run_id: Optional[str] = None,
    ) -> str:
        """Append a new rating to the evaluator's JSONL file. Returns the generated rating_id."""
        rating_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        record = {
            "rating_id": rating_id,
            "video_id": video_id,
            "chunk_id": chunk_id,
            "checkpoint_id": checkpoint_id,
            "prompt_id": prompt_id,
            "rating": rating,
            "issues": issues,
            "free_text": free_text,
            "voice_note_url": voice_note_url,
            "evaluator": evaluator,
            "playback_speed": playback_speed,
            "view_duration_ms": view_duration_ms,
            "supersedes": supersedes,
            "wandb_entity": wandb_entity,
            "wandb_project": wandb_project,
            "wandb_run_id": wandb_run_id,
            "timestamp": now,
        }

        user_path = self._ratings_path(evaluator)
        with self._lock:
            with open(user_path, "a") as f:
                f.write(json.dumps(record) + "\n")
            self._invalidate_cache()

        logger.info("Rating %s: %s → %s by %s (→ %s)", rating_id, video_id, rating, evaluator, user_path.name)
        return rating_id

    def get_ratings_for_checkpoint(
        self, checkpoint_id: str
    ) -> list[dict[str, Any]]:
        return [
            r for r in self._load_all_ratings()
            if r.get("checkpoint_id") == checkpoint_id
        ]

    def get_ratings_for_video(self, video_id: str) -> list[dict[str, Any]]:
        return [
            r for r in self._load_all_ratings()
            if r.get("video_id") == video_id
        ]

    def get_latest_ratings(
        self, checkpoint_id: str
    ) -> dict[str, dict[str, Any]]:
        """Latest rating per video per evaluator for scoring."""
        ratings = self.get_ratings_for_checkpoint(checkpoint_id)
        # Sort by timestamp descending, deduplicate by (video_id, evaluator)
        ratings.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
        latest: dict[str, dict[str, Any]] = {}
        for r in ratings:
            key = f"{r['video_id']}|{r['evaluator']}"
            if key not in latest:
                latest[key] = r
        return latest

    def get_bad_ratings(self) -> list[dict[str, Any]]:
        """Get all ratings with rating='bad', latest per video."""
        all_ratings = self._load_all_ratings()
        bad = [r for r in all_ratings if r.get("rating") == "bad"]
        # Deduplicate: keep latest per video_id
        bad.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
        seen = set()
        result = []
        for r in bad:
            vid = r.get("video_id", "")
            if vid not in seen:
                seen.add(vid)
                result.append(r)
        return result

    def update_rating_issues(
        self, rating_id: str, issues: list[str], free_text: Optional[str] = None
    ) -> bool:
        """Update issues on a rating by rewriting the per-user JSONL file.

        Searches all per-user files to find the rating, then rewrites that file.
        """
        for path in self._all_ratings_paths():
            lines = path.read_text().splitlines()
            found = False
            new_lines = []

            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    new_lines.append(line)
                    continue

                if record.get("rating_id") == rating_id:
                    record["issues"] = issues
                    if free_text is not None:
                        record["free_text"] = free_text
                    found = True
                new_lines.append(json.dumps(record))

            if found:
                with self._lock:
                    path.write_text("\n".join(new_lines) + "\n")
                    self._invalidate_cache()
                return True

        return False

    # ------------------------------------------------------------------ #
    # Chunks (simple JSON file, rarely used)
    # ------------------------------------------------------------------ #

    def _chunks_path(self) -> Path:
        return self.data_dir / "chunks.json"

    def get_chunks(
        self, checkpoint_id: Optional[str] = None
    ) -> list[dict[str, Any]]:
        path = self._chunks_path()
        if not path.exists():
            return []
        try:
            chunks = json.loads(path.read_text())
        except (json.JSONDecodeError, FileNotFoundError):
            return []
        if checkpoint_id:
            return [c for c in chunks if c.get("checkpoint_id") == checkpoint_id]
        return chunks

    def insert_chunk(
        self,
        chunk_id: str,
        checkpoint_id: str,
        video_ids: list[str],
        task_category: Optional[str] = None,
    ) -> None:
        chunks = self.get_chunks()
        chunks.append({
            "chunk_id": chunk_id,
            "checkpoint_id": checkpoint_id,
            "video_ids": video_ids,
            "task_category": task_category,
            "status": "not_started",
            "assigned_to": None,
            "started_at": None,
            "completed_at": None,
        })
        self._chunks_path().write_text(json.dumps(chunks, indent=2))

    def claim_chunk(self, chunk_id: str, evaluator: str) -> bool:
        chunks = self.get_chunks()
        for c in chunks:
            if c["chunk_id"] == chunk_id:
                if c["status"] not in ("not_started", "passed"):
                    if c.get("assigned_to") != evaluator:
                        return False
                c["status"] = "in_progress"
                c["assigned_to"] = evaluator
                c["started_at"] = datetime.now(timezone.utc).isoformat()
                self._chunks_path().write_text(json.dumps(chunks, indent=2))
                return True
        return False

    def update_chunk_status(self, chunk_id: str, status: str) -> None:
        chunks = self.get_chunks()
        for c in chunks:
            if c["chunk_id"] == chunk_id:
                c["status"] = status
                if status == "done":
                    c["completed_at"] = datetime.now(timezone.utc).isoformat()
                break
        self._chunks_path().write_text(json.dumps(chunks, indent=2))

    # ------------------------------------------------------------------ #
    # Scores (computed on-the-fly, optionally cached in JSON)
    # ------------------------------------------------------------------ #

    def get_latest_score(self, checkpoint_id: str) -> Optional[dict[str, Any]]:
        """Compute score on-the-fly from ratings."""
        latest = self.get_latest_ratings(checkpoint_id)
        if not latest:
            return None

        total_good = sum(1 for r in latest.values() if r["rating"] == "good")
        total_bad = sum(1 for r in latest.values() if r["rating"] == "bad")
        total_skipped = sum(1 for r in latest.values() if r["rating"] == "skip")
        total = total_good + total_bad + total_skipped
        evaluators = set(r["evaluator"] for r in latest.values())

        return {
            "checkpoint_id": checkpoint_id,
            "overall_score": total_good / max(total, 1),
            "per_task_scores": {},
            "total_videos": total,
            "total_good": total_good,
            "total_bad": total_bad,
            "total_skipped": total_skipped,
            "evaluator_count": len(evaluators),
            "computed_at": datetime.now(timezone.utc).isoformat(),
        }

    def insert_score(self, **kwargs) -> str:
        """No-op — scores are computed on-the-fly."""
        return str(uuid.uuid4())
