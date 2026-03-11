# WandB Video Indexing — Reference Documentation

## Key Findings

### ❌ Content Hash ≠ Prompt Identifier

The hash in each filename (e.g., `08b939ee30d7`) is a **content hash of the video pixels**, not a prompt identifier. Since the model generates different output at each training step, the hash changes every step — even for the exact same prompt.

**You cannot match videos across steps by hash.**

### ✅ Positional Index IS the Prompt Identifier

WandB logs all 36 validation videos in a **deterministic order** at each step. The training code iterates through prompts in the same sequence. Therefore:

> **Video index 0 at step 500 = index 0 at step 1000 = same prompt.**

The positional index (0-35) is the stable cross-checkpoint identifier.

---

## File Naming Convention

```
media/videos/validation_videos_40_steps_{STEP}_{CONTENT_HASH}.mp4
                                         ^^^^   ^^^^^^^^^^^^
                                    training     unique per video
                                    step #       (NOT per prompt)
```

## Local Download Layout

```
tmp/videos/{run_id}/
├── index.json                  # Full index: all steps × 36 videos
├── step_0500/
│   ├── 00_{hash}.mp4           ← Prompt #0
│   ├── 01_{hash}.mp4           ← Prompt #1
│   ├── ...
│   └── 35_{hash}.mp4           ← Prompt #35
├── step_1000/
│   ├── 00_{hash}.mp4           ← Same Prompt #0 (different hash!)
│   └── ...
└── step_2000/
    ├── 00_{hash}.mp4           ← Same Prompt #0
    └── ...
```

## Per-Step Stats (run hp0jdi7n)

| Step | Videos | Total Size | Avg Size |
|------|--------|-----------|----------|
| 500  | 36     | 34 MB     | ~950 KB  |
| 1000 | 36     | 23 MB     | ~650 KB  |
| 2000 | 36     | 38 MB     | ~1050 KB |

Full run: 47 steps × 36 videos = 1,692 files, ~950 MB estimated.

## Video Format

- **Codec:** H.264
- **Resolution:** 640×352
- **FPS:** 25
- **Duration:** 3.08 seconds (77 frames)
- **Bitrate:** ~1,100 kbps
- **Already compressed** — no further compression recommended.

## How to Track Prompt Improvement

To compare how one prompt improves across training:

1. Pick an index (e.g., prompt `#09`)
2. Open `step_0500/09_*.mp4`, `step_1000/09_*.mp4`, `step_2000/09_*.mp4`
3. Videos have different hashes but the same positional index

## Scripts

- `scripts/download_step.py` — Batch download with parallel threads
- `tmp/videos/index.html` — Interactive video comparison matrix
