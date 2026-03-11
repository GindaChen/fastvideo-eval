"""Tests for the backend API server."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.server.main import create_app
from app.server.database import Database


@pytest.fixture
def app():
    """Create a test app with in-memory database."""
    application = create_app(db_path=":memory:")
    # Trigger startup manually for sync test client
    application.state.db.init()
    return application


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def db(app):
    return app.state.db


# --------------------------------------------------------------------------- #
# Health
# --------------------------------------------------------------------------- #

class TestHealth:

    def test_health_ok(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert data["database"] == "ok"
        assert data["version"] == "0.1.0"


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #

class TestSettings:

    def test_get_default_settings(self, client):
        r = client.get("/api/settings")
        assert r.status_code == 200
        data = r.json()
        assert data["wandb_entity"] == "kaiqin_kong_ucsd"
        assert data["wandb_project"] == "wangame_1.3b"
        assert data["default_run_id"] == "fif3z1z4"
        assert data["auth_token_set"] is False

    def test_update_api_key(self, client):
        r = client.put("/api/settings", json={
            "wandb_api_key": "test_key_123456789",
        })
        assert r.status_code == 200
        data = r.json()
        # Key should be masked
        assert "●" in data["wandb_api_key"]
        assert data["wandb_api_key"].startswith("test")
        assert data["wandb_api_key"].endswith("6789")

    def test_update_run_id(self, client):
        r = client.put("/api/settings", json={"default_run_id": "new_run"})
        assert r.status_code == 200
        assert r.json()["default_run_id"] == "new_run"


# --------------------------------------------------------------------------- #
# Database
# --------------------------------------------------------------------------- #

class TestDatabase:

    def test_settings_roundtrip(self, db):
        db.set_setting("test_key", "test_value")
        assert db.get_setting("test_key") == "test_value"

    def test_insert_rating(self, db):
        rid = db.insert_rating(
            video_id="v1", chunk_id="c1", checkpoint_id="ckpt1",
            prompt_id="p1", rating="good", evaluator="alice",
        )
        assert rid is not None
        ratings = db.get_ratings_for_video("v1")
        assert len(ratings) == 1
        assert ratings[0]["rating"] == "good"

    def test_ratings_append_only(self, db):
        db.insert_rating(
            video_id="v1", chunk_id="c1", checkpoint_id="ckpt1",
            prompt_id="p1", rating="skip", evaluator="alice",
        )
        db.insert_rating(
            video_id="v1", chunk_id="c1", checkpoint_id="ckpt1",
            prompt_id="p1", rating="good", evaluator="alice",
        )
        ratings = db.get_ratings_for_video("v1")
        assert len(ratings) == 2  # Both preserved

    def test_latest_ratings_deduplication(self, db):
        db.insert_rating(
            video_id="v1", chunk_id="c1", checkpoint_id="ckpt1",
            prompt_id="p1", rating="skip", evaluator="alice",
        )
        db.insert_rating(
            video_id="v1", chunk_id="c1", checkpoint_id="ckpt1",
            prompt_id="p1", rating="good", evaluator="alice",
        )
        latest = db.get_latest_ratings("ckpt1")
        # Should have only one entry for v1|alice, the latest one
        assert len(latest) == 1
        key = "v1|alice"
        assert latest[key]["rating"] == "good"

    def test_chunks(self, db):
        db.insert_chunk("c1", "ckpt1", ["v1", "v2", "v3"], "basic_movement")
        chunks = db.get_chunks("ckpt1")
        assert len(chunks) == 1
        assert chunks[0]["video_ids"] == ["v1", "v2", "v3"]
        assert chunks[0]["status"] == "not_started"

    def test_claim_chunk(self, db):
        db.insert_chunk("c1", "ckpt1", ["v1", "v2"])
        assert db.claim_chunk("c1", "alice") is True
        chunks = db.get_chunks()
        assert chunks[0]["status"] == "in_progress"
        assert chunks[0]["assigned_to"] == "alice"


# --------------------------------------------------------------------------- #
# Rating submission via API
# --------------------------------------------------------------------------- #

class TestRatingAPI:

    def test_submit_good_rating(self, client, db):
        r = client.post("/api/ratings", json={
            "video_id": "v1",
            "chunk_id": "c1",
            "checkpoint_id": "ckpt1",
            "prompt_id": "p1",
            "rating": "good",
            "evaluator": "alice",
        })
        assert r.status_code == 200
        assert r.json()["status"] == "stored"

    def test_bad_rating_requires_issues(self, client):
        r = client.post("/api/ratings", json={
            "video_id": "v1",
            "chunk_id": "c1",
            "checkpoint_id": "ckpt1",
            "prompt_id": "p1",
            "rating": "bad",
            "evaluator": "alice",
        })
        assert r.status_code == 422

    def test_bad_rating_with_issues(self, client):
        r = client.post("/api/ratings", json={
            "video_id": "v1",
            "chunk_id": "c1",
            "checkpoint_id": "ckpt1",
            "prompt_id": "p1",
            "rating": "bad",
            "evaluator": "alice",
            "issues": ["wrong_direction", "unexpected_stop"],
        })
        assert r.status_code == 200

    def test_invalid_rating_value(self, client):
        r = client.post("/api/ratings", json={
            "video_id": "v1",
            "chunk_id": "c1",
            "checkpoint_id": "ckpt1",
            "prompt_id": "p1",
            "rating": "maybe",
            "evaluator": "alice",
        })
        assert r.status_code == 422


# --------------------------------------------------------------------------- #
# Dashboard
# --------------------------------------------------------------------------- #

class TestDashboard:

    def test_empty_dashboard(self, client):
        r = client.get("/api/dashboard")
        assert r.status_code == 200
        data = r.json()
        assert data["total_chunks"] == 0
        assert data["total_videos"] == 0

    def test_dashboard_with_data(self, client, db):
        db.insert_chunk("c1", "ckpt1", ["v1", "v2", "v3"])
        db.insert_rating(
            video_id="v1", chunk_id="c1", checkpoint_id="ckpt1",
            prompt_id="p1", rating="good", evaluator="alice",
        )
        db.insert_rating(
            video_id="v2", chunk_id="c1", checkpoint_id="ckpt1",
            prompt_id="p2", rating="skip", evaluator="alice",
        )
        r = client.get("/api/dashboard?checkpoint_id=ckpt1")
        data = r.json()
        assert data["total_chunks"] == 1
        assert data["total_videos"] == 3
        assert data["videos_committed"] == 1
        assert data["videos_skipped"] == 1
        assert data["videos_unrated"] == 1


# --------------------------------------------------------------------------- #
# Results
# --------------------------------------------------------------------------- #

class TestResults:

    def test_checkpoint_detail_live(self, client, db):
        db.insert_rating(
            video_id="v1", chunk_id="c1", checkpoint_id="ckpt1",
            prompt_id="p1", rating="good", evaluator="alice",
        )
        db.insert_rating(
            video_id="v2", chunk_id="c1", checkpoint_id="ckpt1",
            prompt_id="p2", rating="bad", evaluator="alice",
            issues=["wrong_direction"],
        )
        r = client.get("/api/results/ckpt1")
        assert r.status_code == 200
        data = r.json()
        assert data["total_good"] == 1
        assert data["total_bad"] == 1
        assert data["overall_score"] == 0.5
