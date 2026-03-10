# Evaluation Pipeline — Executive Brief

**Project:** WanGame 1.3B (Minecraft World Model) · 2026-03-10  
**WandB:** [wangame_1.3b](https://wandb.ai/kaiqin_kong_ucsd/wangame_1.3b/runs/fif3z1z4?nw=nwuserjunda)

---

## Problem

We have no scalable way to evaluate checkpoints. The model has 23 action types, but current evaluation covers only 9 via an unreliable automatic metric (optical flow) + manual eyeballing on 32 ad-hoc prompts. This doesn't scale and produces inconsistent results.

## Proposal

1. **Expand validation prompts** from 32 → ~120, categorized by task and scene difficulty
2. **Build an evaluation App** — show one video at a time, rate independently, support 5 parallel evaluators
3. **Target:** Full human eval in **<20 minutes** post-training (matching Google's turnaround)

## Key Bottleneck

The project lead must redesign the prompt set and define per-task scoring rubrics. Prompt categorization and App development can be delegated immediately if the full dataset is shared.

## Immediate Next Steps

1. Share dataset → enable others to categorize prompts
2. Expand & balance the prompt set (~120 prompts)
3. Build team-parallel evaluation App
4. Automate checkpoint → video generation pipeline
