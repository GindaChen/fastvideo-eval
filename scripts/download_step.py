#!/usr/bin/env python3
"""Download all 36 validation videos for one step, organized by step number.

This demonstrates the full indexing and download pipeline.

Usage:
    python scripts/download_step.py --run-id hp0jdi7n --step 500
    python scripts/download_step.py --run-id hp0jdi7n --step 500 1000 1500  # multiple steps

Output layout (under tmp/videos/):
    tmp/videos/{run_id}/
    ├── index.json               # Full index: step → video files with metadata
    ├── step_0500/
    │   ├── 00_07b22e55.mp4      # Numbered 00-35 for easy browsing
    │   ├── 01_3a8bcf12.mp4
    │   └── ...
    ├── step_1000/
    │   └── ...
    └── step_1500/
        └── ...
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import wandb

PROJECT = "wangame_1.3b"
ENTITY = "kaiqin_kong_ucsd"


def build_index(run, run_id: str) -> dict:
    """Build an index of step → list of video file paths from run files.
    
    Returns dict: {step_int: [{path, hash, size, download_url}, ...]}
    """
    print(f"Building video index for run {run_id}...")
    files = list(run.files())
    video_files = [f for f in files if f.name.endswith(".mp4")]
    print(f"  Found {len(video_files)} video files")

    # Parse the filename pattern: validation_videos_40_steps_{STEP}_{HASH}.mp4
    pattern = re.compile(r"validation_videos_40_steps_(\d+)_([a-f0-9]+)\.mp4$")
    
    index: dict[int, list] = {}
    for vf in video_files:
        filename = vf.name.split("/")[-1]
        m = pattern.match(filename)
        if not m:
            continue
        step = int(m.group(1))
        vid_hash = m.group(2)
        
        if step not in index:
            index[step] = []
        index[step].append({
            "path": vf.name,
            "hash": vid_hash[:12],  # Truncated for display
            "full_hash": vid_hash,
            "size_bytes": vf.size if hasattr(vf, "size") else None,
            "url": vf.url,
        })
    
    # Sort videos within each step by hash for deterministic ordering
    for step in index:
        index[step].sort(key=lambda v: v["hash"])
        # Assign numeric indices (00, 01, ...) for consistent naming
        for i, v in enumerate(index[step]):
            v["index"] = i
    
    print(f"  Indexed {len(index)} steps, {sum(len(v) for v in index.values())} videos")
    return index


def download_video(url: str, dest: Path, timeout: int = 60) -> float:
    """Download a video file. Returns download time in seconds."""
    t0 = time.time()
    resp = requests.get(url, stream=True, timeout=timeout)
    resp.raise_for_status()
    
    tmp = dest.with_suffix(".mp4.tmp")
    with open(tmp, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
    tmp.rename(dest)
    return time.time() - t0


def download_step(index: dict, step: int, base_dir: Path, parallel: int = 4) -> dict:
    """Download all videos for one step.
    
    Returns summary: {step, count, total_bytes, total_seconds, files}
    """
    if step not in index:
        available = sorted(index.keys())
        print(f"  Step {step} not found. Available: {available[:10]}...")
        return {"step": step, "error": "step not found"}
    
    videos = index[step]
    step_dir = base_dir / f"step_{step:04d}"
    step_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\nDownloading step {step}: {len(videos)} videos → {step_dir}")
    
    results = []
    total_bytes = 0
    t0 = time.time()
    
    def _download_one(vid):
        filename = f"{vid['index']:02d}_{vid['hash']}.mp4"
        dest = step_dir / filename
        if dest.exists() and dest.stat().st_size > 0:
            return {"file": filename, "status": "cached", "size": dest.stat().st_size}
        try:
            dt = download_video(vid["url"], dest)
            size = dest.stat().st_size
            return {"file": filename, "status": "downloaded", "size": size, "time": round(dt, 2)}
        except Exception as e:
            return {"file": filename, "status": "error", "error": str(e)}
    
    with ThreadPoolExecutor(max_workers=parallel) as pool:
        futures = {pool.submit(_download_one, v): v for v in videos}
        for i, future in enumerate(as_completed(futures), 1):
            r = future.result()
            results.append(r)
            total_bytes += r.get("size", 0)
            icon = "✅" if r["status"] in ("downloaded", "cached") else "❌"
            print(f"  {icon} [{i:2d}/{len(videos)}] {r['file']} ({r.get('size', 0)//1024}KB) {r['status']}")
    
    total_time = time.time() - t0
    summary = {
        "step": step,
        "count": len(videos),
        "downloaded": sum(1 for r in results if r["status"] == "downloaded"),
        "cached": sum(1 for r in results if r["status"] == "cached"),
        "errors": sum(1 for r in results if r["status"] == "error"),
        "total_bytes": total_bytes,
        "total_mb": round(total_bytes / 1024 / 1024, 1),
        "total_seconds": round(total_time, 1),
        "files": results,
    }
    
    print(f"\n  Done: {summary['downloaded']} downloaded, {summary['cached']} cached, "
          f"{summary['errors']} errors — {summary['total_mb']}MB in {summary['total_seconds']}s")
    return summary


def main():
    parser = argparse.ArgumentParser(description="Download validation videos for a step")
    parser.add_argument("--run-id", required=True, help="WandB run ID")
    parser.add_argument("--step", type=int, nargs="+", required=True, help="Step number(s) to download")
    parser.add_argument("--output", default="tmp/videos", help="Output base directory")
    parser.add_argument("--parallel", type=int, default=4, help="Parallel downloads")
    parser.add_argument("--list-steps", action="store_true", help="Just list available steps, don't download")
    args = parser.parse_args()

    api = wandb.Api()
    run = api.run(f"{ENTITY}/{PROJECT}/{args.run_id}")
    
    # Build the index
    index = build_index(run, args.run_id)
    
    if args.list_steps:
        print(f"\nAvailable steps ({len(index)}):")
        for step in sorted(index.keys()):
            print(f"  step {step:>5d}: {len(index[step])} videos")
        return
    
    base_dir = Path(args.output) / args.run_id
    base_dir.mkdir(parents=True, exist_ok=True)
    
    # Save the full index
    index_path = base_dir / "index.json"
    index_serializable = {
        str(step): [
            {"index": v["index"], "hash": v["hash"], "path": v["path"], "size_bytes": v["size_bytes"]}
            for v in videos
        ]
        for step, videos in sorted(index.items())
    }
    with open(index_path, "w") as f:
        json.dump({
            "run_id": args.run_id,
            "project": f"{ENTITY}/{PROJECT}",
            "total_steps": len(index),
            "videos_per_step": len(next(iter(index.values()))) if index else 0,
            "steps": index_serializable,
        }, f, indent=2)
    print(f"\nIndex saved to {index_path}")
    
    # Download each requested step
    all_summaries = []
    for step in args.step:
        summary = download_step(index, step, base_dir, args.parallel)
        all_summaries.append(summary)
    
    # Print overall summary
    print(f"\n{'='*60}")
    print(f"  Download Summary")
    print(f"{'='*60}")
    total_downloaded = sum(s.get("downloaded", 0) for s in all_summaries)
    total_mb = sum(s.get("total_mb", 0) for s in all_summaries)
    total_time = sum(s.get("total_seconds", 0) for s in all_summaries)
    print(f"  Steps: {[s['step'] for s in all_summaries]}")
    print(f"  Videos downloaded: {total_downloaded}")
    print(f"  Total size: {total_mb} MB")
    print(f"  Total time: {total_time}s")
    print(f"  Output: {base_dir}")
    print()


if __name__ == "__main__":
    main()
