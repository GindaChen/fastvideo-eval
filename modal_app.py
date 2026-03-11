"""WanGame Eval — Modal deployment.

Deploy:
    modal deploy modal_app.py

Dev (hot-reload):
    modal serve modal_app.py

No Modal Secrets needed — the WandB API key is entered by users via the
Settings page and stored in the persistent data Volume.
"""

import modal

# ---------------------------------------------------------------------------
# Image
# ---------------------------------------------------------------------------
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "fastapi>=0.104",
        "uvicorn[standard]>=0.24",
        "wandb>=0.16",
        "pyyaml>=6.0",
        "requests>=2.31",
        "python-multipart>=0.0.6",
    )
    .add_local_dir("app", remote_path="/root/app")
    .add_local_file("run.py", remote_path="/root/run.py")
)

# ---------------------------------------------------------------------------
# Volumes — persistent storage across container restarts
# ---------------------------------------------------------------------------
data_volume = modal.Volume.from_name("wangame-eval-data", create_if_missing=True)
video_cache_volume = modal.Volume.from_name("wangame-eval-video-cache", create_if_missing=True)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = modal.App(
    name="wangame-eval",
    image=image,
)


@app.function(
    # Keep one container warm — for a 5-person team, one container with
    # 15 concurrent inputs is sufficient. This means the threading.Lock
    # in Storage protects all writes (no multi-container contention).
    keep_warm=1,
    allow_concurrent_inputs=15,
    # Volumes — persistent across restarts
    volumes={
        "/root/data": data_volume,
        "/root/video_cache": video_cache_volume,
    },
    timeout=600,
)
@modal.asgi_app()
def web():
    """Serve the FastAPI app."""
    import sys
    import logging

    sys.path.insert(0, "/root")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)-20s %(levelname)-5s %(message)s",
        datefmt="%H:%M:%S",
    )

    from app.server.main import create_app

    application = create_app(
        data_dir="/root/data",
        static_dir="/root/app/frontend/public",
    )

    # Point video cache to the Volume mount
    application.state.video_cache_dir = "/root/video_cache"

    # Initialize storage (creates data dir, seeds config, migrates legacy files)
    application.state.db.init()

    return application
