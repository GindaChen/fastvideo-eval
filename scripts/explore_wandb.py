#!/usr/bin/env python3
"""Exploratory script to exercise the WandB integration layer.

Usage:
    # List all runs
    python scripts/explore_wandb.py --list-runs

    # List checkpoints for a specific run
    python scripts/explore_wandb.py --run-id <RUN_ID> --list-checkpoints

    # Fetch videos at a specific step
    python scripts/explore_wandb.py --run-id <RUN_ID> --step <STEP> --fetch-videos

    # Download videos to local cache
    python scripts/explore_wandb.py --run-id <RUN_ID> --step <STEP> --download --cache-dir ./cache

    # Fetch optical flow scores
    python scripts/explore_wandb.py --run-id <RUN_ID> --optical-flow

Environment:
    WANDB_API_KEY must be set.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Add repo root to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.wandb_client.config import WandBConfig, load_config, ConfigError
from app.wandb_client.client import WandBClient
from app.wandb_client.cache import VideoCache


def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(name)-20s  %(levelname)-7s  %(message)s",
        datefmt="%H:%M:%S",
    )


def cmd_list_runs(client: WandBClient, args: argparse.Namespace) -> None:
    runs = client.list_runs()
    print(f"\n{'='*60}")
    print(f"  Runs in {client.project_path}  ({len(runs)} total)")
    print(f"{'='*60}\n")
    for i, run in enumerate(runs, 1):
        print(f"  {i:3d}. {run.display_name:<30s}  id={run.run_id}  state={run.state}")
        if run.tags:
            print(f"       tags: {', '.join(run.tags)}")
    print()


def cmd_list_checkpoints(client: WandBClient, args: argparse.Namespace) -> None:
    if not args.run_id:
        print("Error: --run-id required for --list-checkpoints", file=sys.stderr)
        sys.exit(1)

    checkpoints = client.list_checkpoints(args.run_id)
    print(f"\n{'='*60}")
    print(f"  Checkpoints for run {args.run_id}  ({len(checkpoints)} total)")
    print(f"{'='*60}\n")
    for ckpt in checkpoints:
        flow_str = f"  flow={ckpt.optical_flow_score:.4f}" if ckpt.optical_flow_score else ""
        print(f"  step {ckpt.training_step:>8d}  id={ckpt.checkpoint_id}{flow_str}")
    print()


def cmd_fetch_videos(client: WandBClient, args: argparse.Namespace) -> None:
    if not args.run_id or args.step is None:
        print("Error: --run-id and --step required for --fetch-videos", file=sys.stderr)
        sys.exit(1)

    videos = client.fetch_videos(args.run_id, args.step)
    print(f"\n{'='*60}")
    print(f"  Videos at step {args.step}  ({len(videos)} total)")
    print(f"{'='*60}\n")
    for v in videos:
        print(f"  {v.prompt_id:<35s}  url={v.wandb_url[:60]}...")
    print()


def cmd_download(client: WandBClient, args: argparse.Namespace) -> None:
    if not args.run_id or args.step is None:
        print("Error: --run-id and --step required for --download", file=sys.stderr)
        sys.exit(1)

    cache_dir = args.cache_dir or "./cache"
    cache = VideoCache(cache_dir)
    client_with_cache = WandBClient(client.config, cache=cache)

    result = client_with_cache.ingest_checkpoint(args.run_id, args.step)
    print(f"\n{'='*60}")
    print(f"  Ingestion Result for step {args.step}")
    print(f"{'='*60}\n")
    print(f"  Videos found:       {result.videos_found}")
    print(f"  Already cached:     {result.videos_cached}")
    print(f"  Newly downloaded:   {result.videos_downloaded}")
    print(f"  Unavailable:        {result.videos_unavailable}")
    if result.duration_seconds:
        print(f"  Duration:           {result.duration_seconds:.1f}s")
    if result.errors:
        print(f"\n  Errors:")
        for err in result.errors:
            print(f"    ⚠  {err}")
    print(f"\n  Cache: {cache.video_count()} files, {cache.cache_size_human()}")
    print()


def cmd_optical_flow(client: WandBClient, args: argparse.Namespace) -> None:
    if not args.run_id:
        print("Error: --run-id required for --optical-flow", file=sys.stderr)
        sys.exit(1)

    scores = client.fetch_optical_flow(args.run_id)
    print(f"\n{'='*60}")
    print(f"  Optical Flow Scores for run {args.run_id}  ({len(scores)} steps)")
    print(f"{'='*60}\n")
    for step in sorted(scores.keys()):
        print(f"  step {step:>8d}  score={scores[step]:.6f}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Explore the WandB project for WanGame evaluation",
    )
    parser.add_argument("--config", type=str, default=None, help="Path to config.yaml")
    parser.add_argument("--run-id", type=str, default=None, help="WandB run ID")
    parser.add_argument("--step", type=int, default=None, help="Training step")
    parser.add_argument("--cache-dir", type=str, default=None, help="Video cache directory")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")

    # Commands
    parser.add_argument("--list-runs", action="store_true", help="List all runs")
    parser.add_argument("--list-checkpoints", action="store_true", help="List checkpoints for a run")
    parser.add_argument("--fetch-videos", action="store_true", help="Fetch video URLs at a step")
    parser.add_argument("--download", action="store_true", help="Download videos to cache")
    parser.add_argument("--optical-flow", action="store_true", help="Fetch optical flow scores")

    args = parser.parse_args()
    setup_logging(args.verbose)

    # Load config
    try:
        app_config = load_config(args.config)
    except (ConfigError, FileNotFoundError) as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        print("Hint: copy config.yaml.example to config.yaml and set WANDB_API_KEY", file=sys.stderr)
        sys.exit(1)

    client = WandBClient(app_config.wandb)

    # Dispatch
    if args.list_runs:
        cmd_list_runs(client, args)
    elif args.list_checkpoints:
        cmd_list_checkpoints(client, args)
    elif args.fetch_videos:
        cmd_fetch_videos(client, args)
    elif args.download:
        cmd_download(client, args)
    elif args.optical_flow:
        cmd_optical_flow(client, args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
