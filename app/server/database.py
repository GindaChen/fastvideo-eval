"""SQLite database for WanGame Eval (SPEC §11).

Schema covers:
  - ratings (append-only)
  - chunks (status tracking)
  - checkpoint_scores (versioned aggregates)
  - settings (server-side config: WandB API key, run ID)

All writes go through helper functions. No raw SQL in route handlers.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("wangame.db")

# --------------------------------------------------------------------------- #
# Schema
# --------------------------------------------------------------------------- #

_SCHEMA = """
-- Ratings: append-only (SPEC §11.1)
CREATE TABLE IF NOT EXISTS ratings (
    rating_id       TEXT PRIMARY KEY,
    video_id        TEXT NOT NULL,
    chunk_id        TEXT NOT NULL,
    checkpoint_id   TEXT NOT NULL,
    prompt_id       TEXT NOT NULL,
    rating          TEXT NOT NULL CHECK(rating IN ('good', 'bad', 'skip')),
    issues          TEXT,          -- JSON array of strings
    free_text       TEXT,
    voice_note_url  TEXT,
    evaluator       TEXT NOT NULL,
    playback_speed  TEXT,
    view_duration_ms INTEGER,
    supersedes      TEXT,          -- rating_id of previous rating
    timestamp       TEXT NOT NULL   -- ISO 8601
);

-- Chunks: evaluation batches
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id        TEXT PRIMARY KEY,
    checkpoint_id   TEXT NOT NULL,
    video_ids       TEXT NOT NULL,  -- JSON array of strings
    task_category   TEXT,
    status          TEXT NOT NULL DEFAULT 'not_started'
                    CHECK(status IN ('not_started', 'in_progress', 'passed', 'done')),
    assigned_to     TEXT,
    started_at      TEXT,
    completed_at    TEXT
);

-- Checkpoint scores: versioned aggregates
CREATE TABLE IF NOT EXISTS checkpoint_scores (
    score_id        TEXT PRIMARY KEY,
    checkpoint_id   TEXT NOT NULL,
    overall_score   REAL NOT NULL,
    per_task_scores TEXT NOT NULL,  -- JSON map
    total_videos    INTEGER NOT NULL,
    total_good      INTEGER NOT NULL,
    total_bad       INTEGER NOT NULL,
    total_skipped   INTEGER NOT NULL,
    evaluator_count INTEGER NOT NULL,
    computed_at     TEXT NOT NULL
);

-- Server settings (WandB API key, default run, etc.)
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Indices (SPEC §11.2)
CREATE INDEX IF NOT EXISTS idx_ratings_checkpoint ON ratings(checkpoint_id);
CREATE INDEX IF NOT EXISTS idx_ratings_prompt ON ratings(prompt_id);
CREATE INDEX IF NOT EXISTS idx_ratings_evaluator ON ratings(evaluator);
CREATE INDEX IF NOT EXISTS idx_ratings_video ON ratings(video_id);
CREATE INDEX IF NOT EXISTS idx_chunks_checkpoint ON chunks(checkpoint_id);
CREATE INDEX IF NOT EXISTS idx_chunks_status ON chunks(status);
"""


# --------------------------------------------------------------------------- #
# Database connection
# --------------------------------------------------------------------------- #

class Database:
    """SQLite database manager.

    Args:
        db_path: Path to SQLite file. Use ":memory:" for tests.
    """

    def __init__(self, db_path: str | Path = "eval.db"):
        self.db_path = str(db_path)
        self._initialized = False
        self._shared_conn: Optional[sqlite3.Connection] = None
        # For :memory: dbs, keep one shared connection so tables persist
        if self.db_path == ":memory:":
            self._shared_conn = sqlite3.connect(
                ":memory:", check_same_thread=False
            )
            self._shared_conn.row_factory = sqlite3.Row
            self._shared_conn.execute("PRAGMA journal_mode=WAL")
            self._shared_conn.execute("PRAGMA foreign_keys=ON")

    def init(self) -> None:
        """Create tables and indices if they don't exist."""
        with self.conn() as c:
            c.executescript(_SCHEMA)
            # Seed default settings
            c.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                ("wandb_api_key", ""),
            )
            c.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                ("wandb_entity", "kaiqin_kong_ucsd"),
            )
            c.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                ("wandb_project", "wangame_1.3b"),
            )
            c.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                ("default_run_id", "fif3z1z4"),
            )
            c.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                ("auth_token", ""),
            )
        self._initialized = True
        logger.info("Database initialized at %s", self.db_path)

    @contextmanager
    def conn(self):
        """Yield a SQLite connection with WAL mode and foreign keys."""
        if self._shared_conn is not None:
            # In-memory DB: reuse the shared connection
            try:
                yield self._shared_conn
                self._shared_conn.commit()
            except Exception:
                self._shared_conn.rollback()
                raise
        else:
            c = sqlite3.connect(self.db_path)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA foreign_keys=ON")
            try:
                yield c
                c.commit()
            except Exception:
                c.rollback()
                raise
            finally:
                c.close()

    # ------------------------------------------------------------------ #
    # Settings CRUD
    # ------------------------------------------------------------------ #

    def get_setting(self, key: str) -> Optional[str]:
        with self.conn() as c:
            row = c.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
            return row["value"] if row else None

    def set_setting(self, key: str, value: str) -> None:
        with self.conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )

    def get_all_settings(self) -> dict[str, str]:
        with self.conn() as c:
            rows = c.execute("SELECT key, value FROM settings").fetchall()
            return {r["key"]: r["value"] for r in rows}

    # ------------------------------------------------------------------ #
    # Ratings (append-only — SPEC §11.1)
    # ------------------------------------------------------------------ #

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
    ) -> str:
        """Insert a new rating. Returns the generated rating_id."""
        rating_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        with self.conn() as c:
            c.execute(
                """INSERT INTO ratings (
                    rating_id, video_id, chunk_id, checkpoint_id, prompt_id,
                    rating, issues, free_text, voice_note_url, evaluator,
                    playback_speed, view_duration_ms, supersedes, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    rating_id, video_id, chunk_id, checkpoint_id, prompt_id,
                    rating, json.dumps(issues) if issues else None,
                    free_text, voice_note_url, evaluator,
                    playback_speed, view_duration_ms, supersedes, now,
                ),
            )

        logger.info(
            "Rating %s: %s → %s by %s", rating_id, video_id, rating, evaluator
        )
        return rating_id

    def get_ratings_for_checkpoint(
        self, checkpoint_id: str
    ) -> list[dict[str, Any]]:
        with self.conn() as c:
            rows = c.execute(
                "SELECT * FROM ratings WHERE checkpoint_id = ? ORDER BY timestamp",
                (checkpoint_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_ratings_for_video(self, video_id: str) -> list[dict[str, Any]]:
        with self.conn() as c:
            rows = c.execute(
                "SELECT * FROM ratings WHERE video_id = ? ORDER BY timestamp",
                (video_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_latest_ratings(
        self, checkpoint_id: str
    ) -> dict[str, dict[str, Any]]:
        """Latest rating per video per evaluator for scoring."""
        with self.conn() as c:
            rows = c.execute(
                """SELECT * FROM ratings
                   WHERE checkpoint_id = ?
                   ORDER BY timestamp DESC""",
                (checkpoint_id,),
            ).fetchall()

        # Deduplicate: keep latest per (video_id, evaluator)
        latest: dict[str, dict[str, Any]] = {}
        for r in rows:
            key = f"{r['video_id']}|{r['evaluator']}"
            if key not in latest:
                latest[key] = dict(r)
        return latest

    # ------------------------------------------------------------------ #
    # Chunks
    # ------------------------------------------------------------------ #

    def insert_chunk(
        self,
        chunk_id: str,
        checkpoint_id: str,
        video_ids: list[str],
        task_category: Optional[str] = None,
    ) -> None:
        with self.conn() as c:
            c.execute(
                """INSERT INTO chunks
                   (chunk_id, checkpoint_id, video_ids, task_category)
                   VALUES (?, ?, ?, ?)""",
                (chunk_id, checkpoint_id, json.dumps(video_ids), task_category),
            )

    def get_chunks(
        self, checkpoint_id: Optional[str] = None
    ) -> list[dict[str, Any]]:
        with self.conn() as c:
            if checkpoint_id:
                rows = c.execute(
                    "SELECT * FROM chunks WHERE checkpoint_id = ?",
                    (checkpoint_id,),
                ).fetchall()
            else:
                rows = c.execute("SELECT * FROM chunks").fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d["video_ids"] = json.loads(d["video_ids"])
                result.append(d)
            return result

    def claim_chunk(self, chunk_id: str, evaluator: str) -> bool:
        """Claim a chunk. Returns False if already claimed."""
        now = datetime.now(timezone.utc).isoformat()
        with self.conn() as c:
            row = c.execute(
                "SELECT status, assigned_to FROM chunks WHERE chunk_id = ?",
                (chunk_id,),
            ).fetchone()
            if not row:
                return False
            if row["status"] not in ("not_started", "passed"):
                if row["assigned_to"] != evaluator:
                    return False
            c.execute(
                """UPDATE chunks
                   SET status = 'in_progress', assigned_to = ?, started_at = ?
                   WHERE chunk_id = ?""",
                (evaluator, now, chunk_id),
            )
        return True

    def update_chunk_status(self, chunk_id: str, status: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.conn() as c:
            updates = {"status": status}
            if status == "done":
                c.execute(
                    "UPDATE chunks SET status = ?, completed_at = ? WHERE chunk_id = ?",
                    (status, now, chunk_id),
                )
            else:
                c.execute(
                    "UPDATE chunks SET status = ? WHERE chunk_id = ?",
                    (status, chunk_id),
                )

    # ------------------------------------------------------------------ #
    # Scores
    # ------------------------------------------------------------------ #

    def insert_score(
        self,
        checkpoint_id: str,
        overall_score: float,
        per_task_scores: dict,
        total_videos: int,
        total_good: int,
        total_bad: int,
        total_skipped: int,
        evaluator_count: int,
    ) -> str:
        score_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with self.conn() as c:
            c.execute(
                """INSERT INTO checkpoint_scores
                   (score_id, checkpoint_id, overall_score, per_task_scores,
                    total_videos, total_good, total_bad, total_skipped,
                    evaluator_count, computed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    score_id, checkpoint_id, overall_score,
                    json.dumps(per_task_scores),
                    total_videos, total_good, total_bad, total_skipped,
                    evaluator_count, now,
                ),
            )
        return score_id

    def get_latest_score(
        self, checkpoint_id: str
    ) -> Optional[dict[str, Any]]:
        with self.conn() as c:
            row = c.execute(
                """SELECT * FROM checkpoint_scores
                   WHERE checkpoint_id = ?
                   ORDER BY computed_at DESC LIMIT 1""",
                (checkpoint_id,),
            ).fetchone()
            if not row:
                return None
            d = dict(row)
            d["per_task_scores"] = json.loads(d["per_task_scores"])
            return d
