# Agent Onboarding

Welcome, agent. This repo contains the evaluation pipeline design and tooling for the **WanGame 1.3B Minecraft World Model**.

## Quick Context

- We train a world model that generates Minecraft gameplay video given a first frame + 77-frame action sequence (23-dim binary vector per frame)
- Training produces many checkpoints; we need to evaluate which ones are best
- Current evaluation is manual and doesn't scale — this repo fixes that

## What You Need to Know

### The 23 Actions
Movement (WASD), Mouse (4 dirs), Jump (space), Hotbar (F1-F8), Sprint (Shift+W), Still (no-op). Stored as 77×23 binary matrices.

### Evaluation Dimensions
1. **Video Quality** — visual fidelity, simple vs complex scenes
2. **Consistency** — turn left then right, does the scene match?
3. **Action Following** — does the model execute the requested action correctly?

### Current Automated Metric
Optical flow (LPIPS variant comparing GT vs generated video). It's our only auto metric but is **unreliable** — use as a reference signal, not ground truth.

### Model Behavior Rules
- Model stops at obstacles (never auto-jumps)
- Model stops near walls (no collision)
- Flat terrain = near-perfect expected; complex terrain = some tolerance OK

## Repo Structure

```
wangame-eval/
├── README.md              # Mission and overview
├── AGENTS.md              # You are here
├── docs/                  # Design documents
│   ├── eval_pipeline_exec_brief.md
│   ├── eval_pipeline_summary.md
│   ├── eval_pipeline_full.md
│   └── meeting_notes_raw.md
├── prompts/               # Validation prompt definitions (TODO)
├── scripts/               # Automation scripts (TODO)
└── app/                   # Evaluation App (TODO)
```

## How to Contribute

1. Read [eval_pipeline_summary.md](docs/eval_pipeline_summary.md) for the medium-length overview
2. Check the action items in that doc — pick one that's unblocked
3. For full technical context, read [eval_pipeline_full.md](docs/eval_pipeline_full.md)

## Key Data Sources

- **WandB:** [wangame_1.3b](https://wandb.ai/kaiqin_kong_ucsd/wangame_1.3b/runs/fif3z1z4?nw=nwuserjunda) — validation videos + prompt metadata
- **Checkpoints:** Stored on M2 cluster (not in WandB)
- **Training data:** 1B samples of Minecraft gameplay

## Common Tasks for Agents

- **Categorize prompts:** Given the 32 existing prompts + action lists, classify by task type
- **Design new prompts:** Propose ~120 prompts covering all 23 actions × scene difficulties
- **Build eval App:** Tinder-style video rating UI with team-parallel support
- **Automate pipeline:** checkpoint path → video generation → WandB upload with task tags
