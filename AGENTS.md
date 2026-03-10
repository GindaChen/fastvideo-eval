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

### Data Flow (Already Working)
- Training on M2 generates validation videos **every 500 steps** and uploads to WandB
- **WandB is the source of truth** — videos + prompt metadata + optical flow scores
- Human reviews WandB to select **Top-5 checkpoints**
- The data pipeline is **already done** — remaining work is evaluation tooling

## Repo Structure

```
wangame-eval/
├── README.md              # Mission, data pipeline diagram, subproject arch diagrams
├── AGENTS.md              # You are here
├── docs/                  # Design documents + meeting transcripts
│   ├── eval_pipeline_exec_brief.md
│   ├── eval_pipeline_summary.md
│   ├── eval_pipeline_full.md
│   ├── meeting_notes_raw.md
│   └── meeting_transcript_raw.md
├── prompts/               # SP3: Validation prompt definitions (TODO)
├── scripts/               # Scoring scripts (TODO)
└── app/                   # SP1: Evaluation App (TODO)
```

## Subprojects (Priority Order)

| # | Subproject | Status | Goal |
|---|---|---|---|
| — | **Data Pipeline** | ✅ Done | Training uploads videos to WandB every 500 steps |
| SP1 | **Evaluation App** | 🟡 Design | Tinder-style per-video rating, team-parallel (5 people × 5 min) |
| SP2 | **Scoring & Analysis** | 🟡 Design | Per-task rubrics, aggregation, trend tracking |
| SP3 | **Prompt Design** | 🟡 Design | Task taxonomy for 23 actions, expand 32 → ~120 prompts |

## How to Contribute

1. Read [eval_pipeline_summary.md](docs/eval_pipeline_summary.md) for the medium-length overview
2. Check the README for subproject scope — pick one that's unblocked
3. For full technical context, read [eval_pipeline_full.md](docs/eval_pipeline_full.md)

## Key Data Sources

- **WandB:** [wangame_1.3b](https://wandb.ai/kaiqin_kong_ucsd/wangame_1.3b/runs/fif3z1z4?nw=nwuserjunda) — validation videos + prompt metadata (source of truth, updated every 500 training steps)
- **Checkpoints:** Stored on M2 cluster
- **Training data:** 1B samples of Minecraft gameplay

## Common Tasks for Agents

- **Build eval App:** Tinder-style video rating UI streaming from WandB, team-parallel support (SP1)
- **Define scoring rubric:** Per-task aggregation with difficulty-adjusted tolerance (SP2)
- **Categorize prompts:** Given the 32 existing prompts + action lists, classify by task type (SP3)
- **Design new prompts:** Propose ~120 prompts covering all 23 actions × scene difficulties (SP3)
