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

### Data Flow
- **WandB is the source of truth** for validation videos and prompt metadata
- Videos are streamed from WandB (not M2) to the eval App
- Checkpoints are stored on M2 (not in WandB)

## Repo Structure

```
wangame-eval/
├── README.md              # Mission, subproject arch diagrams, overview
├── AGENTS.md              # You are here
├── docs/                  # Design documents + meeting transcripts
│   ├── eval_pipeline_exec_brief.md
│   ├── eval_pipeline_summary.md
│   ├── eval_pipeline_full.md
│   ├── meeting_notes_raw.md
│   └── meeting_transcript_raw.md
├── prompts/               # SP4: Validation prompt definitions (TODO)
├── scripts/               # SP1: Pipeline automation scripts (TODO)
└── app/                   # SP2: Evaluation App (TODO)
```

## Subprojects (Priority Order)

| # | Subproject | Goal |
|---|---|---|
| SP1 | **Data Pipeline** | Automate checkpoint → video gen → WandB with task tags |
| SP2 | **Evaluation App** | Tinder-style per-video rating, team-parallel (5 people × 5 min) |
| SP3 | **Scoring & Analysis** | Per-task rubrics, aggregation, trend tracking |
| SP4 | **Prompt Design** | Task taxonomy for 23 actions, expand 32 → ~120 prompts |

## How to Contribute

1. Read [eval_pipeline_summary.md](docs/eval_pipeline_summary.md) for the medium-length overview
2. Check the README for subproject scope — pick one that's unblocked
3. For full technical context, read [eval_pipeline_full.md](docs/eval_pipeline_full.md)

## Key Data Sources

- **WandB:** [wangame_1.3b](https://wandb.ai/kaiqin_kong_ucsd/wangame_1.3b/runs/fif3z1z4?nw=nwuserjunda) — validation videos + prompt metadata (source of truth)
- **Checkpoints:** Stored on M2 cluster
- **Training data:** 1B samples of Minecraft gameplay

## Common Tasks for Agents

- **Categorize prompts:** Given the 32 existing prompts + action lists, classify by task type (SP4)
- **Design new prompts:** Propose ~120 prompts covering all 23 actions × scene difficulties (SP4)
- **Build eval App:** Tinder-style video rating UI with team-parallel support (SP2)
- **Automate pipeline:** checkpoint → video generation → WandB upload with task tags (SP1)
- **Define scoring rubric:** Per-task aggregation with difficulty-adjusted tolerance (SP3)
