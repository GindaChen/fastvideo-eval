# WanGame Eval

Evaluation pipeline for the **WanGame 1.3B Minecraft World Model**.

**WandB:** [wangame_1.3b](https://wandb.ai/kaiqin_kong_ucsd/wangame_1.3b/runs/fif3z1z4?nw=nwuserjunda)

---

## Documents

| Document | Description |
|---|---|
| [Executive Brief](docs/eval_pipeline_exec_brief.md) | One-page summary for stakeholders |
| [Summary Report](docs/eval_pipeline_summary.md) | Medium-length overview of the evaluation pipeline |
| [Full Meeting Notes](docs/eval_pipeline_full.md) | Comprehensive meeting notes with all details |
| [Raw Working Notes](docs/meeting_notes_raw.md) | Incrementally captured meeting notes (working document) |

---

## Quick Context

- **Model:** Generates Minecraft gameplay video from a starting frame + 77-frame action sequence
- **Actions:** 23 distinct actions (movement, mouse, jump, hotbar, sprint, still)
- **Current eval:** Optical flow metric (unreliable) + manual eyeballing on 32 ad-hoc prompts
- **Target:** Task-based evaluation with ~120 categorized prompts, team-parallel human eval in <20 min

## Key Next Steps

1. Share dataset → categorize prompts by task
2. Expand prompt set (32 → ~120) with balanced coverage
3. Build team-parallel evaluation App
4. Automate checkpoint → video generation pipeline
