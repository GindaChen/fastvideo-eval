# WanGame Eval

**Mission:** Build a scalable, task-based evaluation pipeline for the WanGame 1.3B Minecraft World Model — replacing ad-hoc eyeballing with structured, team-parallel human evaluation that delivers results in under 20 minutes post-training.

## Why This Repo Exists

We train a world model that generates Minecraft gameplay video from a starting frame + action sequence. The model handles 23 distinct action types, but we currently have no scalable way to evaluate checkpoint quality. Our automated metric (optical flow) is unreliable, and manual eyeballing on 32 ad-hoc prompts doesn't cover enough ground.

This repo is the home for:
1. **Evaluation design** — task taxonomy, prompt sets, scoring rubrics
2. **Evaluation tooling** — the human eval App, automation scripts, data pipeline
3. **Results & analysis** — checkpoint comparisons, per-task scores, trend tracking

## Current Status

🟡 **Design phase** — Evaluation architecture is defined (see docs). Implementation has not started.

## Documents

| Document | Audience | Description |
|---|---|---|
| [Executive Brief](docs/eval_pipeline_exec_brief.md) | Stakeholders | One-page problem + proposal |
| [Summary Report](docs/eval_pipeline_summary.md) | Team leads | Problem, current state, proposed solution, action items |
| [Full Meeting Notes](docs/eval_pipeline_full.md) | Contributors | Everything discussed, all technical details |
| [Raw Working Notes](docs/meeting_notes_raw.md) | Reference | Incrementally captured meeting transcript |

## Key References

- **WandB Project:** [wangame_1.3b](https://wandb.ai/kaiqin_kong_ucsd/wangame_1.3b/runs/fif3z1z4?nw=nwuserjunda)
- **Model:** 1.3B parameter Minecraft world model
- **Actions:** 23 types (movement, mouse, jump, hotbar F1-F8, sprint, still)
- **Current validation:** 32 prompts × 5 checkpoints = 160 videos per eval round
- **Target validation:** ~120 prompts × 5 checkpoints = 600 videos, evaluated by 5 people in <20 min

## Roadmap

1. **Prompt design** — Categorize existing 32 prompts, expand to ~120 with balanced task × difficulty coverage
2. **Data pipeline** — Automate checkpoint → prompt set → video batch generation
3. **Eval App** — Tinder-style UI for fast per-video rating with team-parallel support
4. **Scoring framework** — Per-task rubrics with difficulty-adjusted tolerance
5. **GT construction** — Record ground truth videos via Minecraft simulator
