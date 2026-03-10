<!-- SECTION: Problem -->
<!-- SLIDE -->
# WanGame Eval
## Scalable Evaluation for Minecraft World Model

**Goal:** Replace ad-hoc eyeballing with structured, team-parallel human evaluation — results in **< 20 min** post-training.

[WandB Project](https://wandb.ai/kaiqin_kong_ucsd/wangame_1.3b/runs/fif3z1z4?nw=nwuserjunda)

<!-- SLIDE -->
## The Problem

We train a world model that generates Minecraft gameplay video from:
- A **starting frame** (screenshot)
- An **action sequence** (77 frames × 23 actions)

Training produces many checkpoints. We need to answer:

1. **Which checkpoint is better?**
2. **Is it good enough to release?**

<!-- SLIDE -->
## Why It's Hard

**23 distinct actions** — too many to eyeball

| Category | Actions |
|----------|---------|
| Movement | W, A, S, D |
| Mouse | Up, Down, Left, Right |
| Jump | Spacebar |
| Hotbar | F1–F8 |
| Sprint | Shift + W |
| Still | No action |

Only **9 of 23** actions are currently well-evaluated.

<!-- SLIDE -->
## Current Process (Doesn't Scale)

| Step | Method | Problem |
|------|--------|---------|
| Auto ranking | Optical flow every 500 steps | Unreliable metric |
| Selection | Keep Top-5 + save every 5K steps | Metric errors |
| Human review | Eyeball 32 videos | Ad-hoc, unbalanced, slow |

**Optical flow** is an LPIPS variant — our only auto metric, but unreliable for still actions, wall collisions, and distance-dependent scenes.

<!-- SECTION: Architecture -->
<!-- SLIDE -->
## Data Pipeline ✅ Done

Training already handles this:

1. Every **500 steps** → generate validation videos
2. Upload to **WandB** with prompt metadata
3. Human reviews WandB → selects **Top-5 checkpoints**

**WandB is the source of truth.** Videos come pre-rendered with action overlay.

<!-- SLIDE -->
## SP1: Evaluation App

**Tinder-style video rating** — play pre-rendered WandB video, rate good/bad/skip.

- **Chunk-based:** ~20 videos per chunk
- **Single-person first**, scales to team
- **Progress tracking:** which chunks done vs remaining
- **Database:** Append-only writes → no concurrency issues
- **Hosting:** RunPod CPU instance
- **Backups:** 10 rotating, every 5 min

<!-- SLIDE -->
## SP2: Scoring & Analysis

**Aggregate ratings → checkpoint decisions**

- Per-video scores (before task categorization)
- Per-task scores (after SP3 provides categories)
- **Inspection view:** drill into video × checkpoint scores
- Difficulty-adjusted tolerance:
  - Flat terrain → **zero tolerance**
  - Complex terrain → some tolerance OK
- Trend tracking across training runs

<!-- SLIDE -->
## SP3: Prompt Design & Task Taxonomy

**What we test and how**

Current: **32 ad-hoc prompts** (unbalanced, no task tags)

Target: **~120 prompts** organized by:

| Task Group | Examples |
|------------|----------|
| Basic Movement | Forward, back, strafe |
| Camera Control | Mouse look 4 dirs |
| Advanced | Sprint, jump, hotbar |
| Stability | Still (no action) |
| Combinations | Sprint + turn, etc. |

Each group × easy/hard scenes = comprehensive coverage.

<!-- SECTION: Model Knowledge -->
<!-- SLIDE -->
## Model Behavior Rules

One month of training has taught us what to expect:

| Behavior | Model Output |
|----------|-------------|
| Hits obstacle | **Stops** (no auto-jump) |
| Near wall | Stops safely (no collision) |
| Flat terrain | Near-perfect expected |
| Complex terrain | Some hesitation OK |

> Collision data was filtered from training — model never learned to clip through walls.

<!-- SECTION: Next Steps -->
<!-- SLIDE -->
## What's Next

| Priority | Task | Status |
|----------|------|--------|
| 1 | Build eval App (SP1) | 🟡 Design done |
| 2 | Define scoring rubrics (SP2) | 🟡 Needs SP3 |
| 3 | Categorize 32 prompts (SP3) | 🟡 Needs dataset |
| 4 | Expand to ~120 prompts (SP3) | ⬜ Blocked on #3 |

**Key unblock:** Share the full dataset → anyone can propose task categories → lead reviews and picks.

<!-- SLIDE -->
## Key Principles

1. **Evaluate each video independently** — never compare checkpoints side-by-side
2. **Chunk-based work** — claim 20 videos, submit ratings, grab next chunk
3. **Append-only database** — simple, no concurrency issues
4. **40% effort → 80% insight** — don't need 100% coverage to make good decisions

> *"你不能直接比较两个 checkpoint，而只能通过每一个 video 去评价这个 video 本身如何。"*
