# World Model Evaluation Pipeline — Summary Report

**Date:** 2026-03-10  
**Project:** WanGame 1.3B — Minecraft World Model  
**WandB:** [wangame_1.3b](https://wandb.ai/kaiqin_kong_ucsd/wangame_1.3b/runs/fif3z1z4?nw=nwuserjunda)

---

## Background

We are training a world model that generates Minecraft gameplay video from a starting frame + action sequence. Training produces multiple checkpoints, and we need a scalable way to determine which checkpoints are best and whether they meet release quality.

The model must handle **23 distinct actions** (movement, mouse look, jump, hotbar selection, sprint, still). Only 9 of these are currently well-evaluated.

---

## Current Evaluation Process

| Step | Method | Limitation |
|---|---|---|
| Automated ranking | Optical flow metric (LPIPS variant) every 500 steps | Unreliable for still/collision; distance-dependent bias |
| Checkpoint selection | Maintain Top-5 + save every 5K steps | Metric errors require manual verification |
| Human review | Elimination-based eyeballing on 32 videos | Ad-hoc prompts, unbalanced coverage, doesn't scale |

**Key metric issue:** Optical flow is our only automatic action-following metric, but it's a reference signal, not ground truth. It's unreliable even with GT video (near vs far objects produce different flow magnitudes for the same action).

**Key human review issue:** 32 prompts were designed ad-hoc without task categorization. Complex scenes are over-covered; simple scenes are under-covered. Evaluating 5 checkpoints × 32 videos with eyeballing is infeasible.

---

## Proposed Solution

### 1. Task-Based Prompt Redesign
- Expand from 32 → ~120 prompts
- Categorize by task group (movement, mouse, sprint, hotbar, etc.)
- Balance across scene difficulty (flat terrain = zero tolerance; complex = some tolerance)
- Split some GT data from training set into validation (currently all validation is non-GT)

### 2. Evaluation App ("Tinder-Style")
- Per-video card: first frame, action overlay, video (2-3x speed), rating, voice annotation
- Category-specific issue checklists
- Stretch: on-demand video generation for ad-hoc testing
- **Key principle:** Evaluate each video independently — never compare two checkpoints side-by-side

### 3. Team-Parallel Evaluation
- 1 person processes ~30 videos in 5 min
- 5 evaluators → full eval in **10–20 min** post-training
- Matches Google's ~30 min turnaround target

---

## Infrastructure

| Component | Location |
|---|---|
| Training & video generation | M2 |
| Validation videos + prompt metadata | WandB |
| Checkpoints | Local / M2 (not in WandB) |

**Gaps:** Need automated post-training video generation pipeline, task tags on WandB, and video streaming to eval App.

---

## Bottlenecks & Ownership

| Task | Owner | Delegatable? |
|---|---|---|
| Prompt redesign & task grouping | Project lead | ❌ Requires domain expertise |
| Prompt categorization | Anyone / agent | ✅ Given the dataset |
| Build eval App | Engineer | ✅ Implementation task |
| Record GT videos (Minecraft) | Anyone | ✅ Low skill, high overhead |
| Scoring rubric | Project lead | ❌ Requires model knowledge |

**Key unblock:** Share the full dataset → others can propose categorization → lead reviews and picks.

---

## Action Items (Priority Order)

1. **Share dataset** and categorize existing 32 prompts by task
2. **Expand to ~120 prompts** with balanced task × difficulty coverage
3. **Split GT data** from training into validation
4. **Automate** checkpoint → prompt → video generation pipeline
5. **Build evaluation App** with team-parallel support
6. **Define scoring rubric** per task with difficulty-adjusted tolerance
7. **Delegate GT video recording** via Minecraft simulator (WorkLab server)
