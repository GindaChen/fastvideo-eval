# WanGame Eval

**Mission:** Build a scalable, task-based evaluation pipeline for the WanGame 1.3B Minecraft World Model — replacing ad-hoc eyeballing with structured, team-parallel human evaluation that delivers results in under 20 minutes post-training.

## Mission Overview

```mermaid
graph LR
    A[Training completes] --> B[Top-5 checkpoints]
    B --> C[Generate videos<br/>for ~120 prompts]
    C --> D[Upload to WandB<br/>with task tags]
    D --> E[Eval App distributes<br/>to 5 evaluators]
    E --> F[Per-task scores<br/>aggregated]
    F --> G[Checkpoint decision<br/>in < 20 min]
```

## Why This Repo Exists

We train a world model that generates Minecraft gameplay video from a starting frame + action sequence. The model handles 23 distinct action types, but we currently have no scalable way to evaluate checkpoint quality. Our automated metric (optical flow) is unreliable, and manual eyeballing on 32 ad-hoc prompts doesn't cover enough ground.

This repo is the home for everything needed to fix that — from evaluation design to tooling to results.

## Current Status

🟡 **Design phase** — Evaluation architecture is defined (see docs). Implementation has not started.

---

## Subprojects

### SP1: Data Pipeline

**Mission:** Automate the flow from training checkpoint → video generation → WandB → evaluation-ready data.

```mermaid
graph TD
    subgraph Training["Training (M2)"]
        T1[Training loop] -->|every 500 steps| T2[Optical flow eval]
        T2 --> T3[Top-5 checkpoint selection]
        T1 -->|every 5K steps| T4[Round-number checkpoint save]
    end

    subgraph VideoGen["Video Generation"]
        T3 --> V1[Load checkpoint]
        T4 --> V1
        V1 --> V2[Generate videos<br/>for all prompts]
    end

    subgraph WandB["WandB (Source of Truth)"]
        V2 --> W1[Upload videos +<br/>prompt metadata]
        W1 --> W2[Add task/category tags]
        W2 --> W3[Videos ready for<br/>eval App streaming]
    end

    style WandB fill:#1a1a2e,color:#fff
    style Training fill:#16213e,color:#fff
    style VideoGen fill:#0f3460,color:#fff
```

**Key clarification:** Videos are streamed from **WandB**, not M2. WandB is the source of truth — training uploads validation videos with prompt metadata during training. The eval App reads directly from WandB.

**Scope:**
- Automate post-training video generation (checkpoint + prompt set → video batch)
- Add task/category tags to WandB prompt metadata
- Extract evaluation-ready pairs from existing WandB data
- GT video recording via Minecraft simulator (delegatable)

---

### SP2: Evaluation App

**Mission:** A Tinder-style web app for fast, team-parallel human evaluation of generated videos.

```mermaid
graph TD
    subgraph DataSource["Data Source"]
        DS1[WandB API] --> DS2[Stream videos +<br/>prompt metadata]
    end

    subgraph App["Eval App"]
        DS2 --> A1[Video Card UI]
        A1 --> A2[First frame +<br/>action overlay +<br/>video player 2-3x]
        A2 --> A3{Rate}
        A3 -->|Good| A4[Score: ✅]
        A3 -->|Bad| A5[Score: ❌ +<br/>issue checklist]
        A3 -->|Skip| A6[Skip]
        A5 --> A7[Optional: voice<br/>annotation]
    end

    subgraph Team["Team-Parallel"]
        A4 & A5 & A6 --> T1[Aggregate per-task<br/>per-checkpoint]
        T1 --> T2[5 evaluators ×<br/>5 min = 20 min]
    end

    style DataSource fill:#1a1a2e,color:#fff
    style App fill:#0f3460,color:#fff
    style Team fill:#16213e,color:#fff
```

**Scope:**
- Per-video evaluation card: first frame, action key overlay, video at 2-3x, rating controls
- Category-specific issue checklists per task type
- Team-parallel: distribute video slices across 5 evaluators
- Stretch: on-demand video generation (define ad-hoc action sequence → generate → evaluate)
- Key principle: evaluate each video independently, never compare two checkpoints side-by-side

---

### SP3: Scoring & Analysis

**Mission:** Define how per-video ratings become per-task scores and overall checkpoint rankings.

```mermaid
graph TD
    subgraph Input["Raw Ratings"]
        I1[Per-video scores<br/>from eval App]
        I2[Task tags per prompt]
        I3[Scene difficulty labels]
    end

    subgraph Aggregate["Aggregation"]
        I1 & I2 --> S1[Group by task]
        S1 --> S2[Per-task score<br/>per checkpoint]
        I3 --> S3[Apply difficulty<br/>tolerance]
        S2 & S3 --> S4[Weighted task<br/>scores]
    end

    subgraph Output["Decision"]
        S4 --> O1[Checkpoint ranking]
        S4 --> O2[Per-task breakdown:<br/>which tasks regressed?]
        S4 --> O3[Trend over<br/>training runs]
    end

    style Input fill:#1a1a2e,color:#fff
    style Aggregate fill:#0f3460,color:#fff
    style Output fill:#16213e,color:#fff
```

**Scope:**
- Per-task scoring rubrics with difficulty-adjusted tolerance (flat terrain = zero tolerance, complex = some OK)
- Aggregation method: per-task → overall ranking (not just "who wins most videos")
- Results dashboard / trend tracking across training runs
- Comparison with optical flow scores for metric calibration

---

### SP4: Prompt Design & Task Taxonomy

**Mission:** Define what we test and how — categorizing the 23 actions into evaluatable task groups with balanced coverage.

```mermaid
graph TD
    subgraph Actions["23 Actions"]
        A1[Movement<br/>W A S D]
        A2[Mouse<br/>4 directions]
        A3[Jump / Sprint<br/>Hotbar F1-F8]
        A4[Still<br/>no action]
    end

    subgraph TaskGroups["Task Groups"]
        A1 --> T1[Basic Movement]
        A2 --> T2[Camera Control]
        A3 --> T3[Advanced Actions]
        A4 --> T4[Stability]
        T1 & T2 & T3 & T4 --> T5[Combinations]
    end

    subgraph Prompts["~120 Prompts"]
        T1 --> P1[8-10 prompts ×<br/>easy/hard scenes]
        T2 --> P2[8-10 prompts ×<br/>easy/hard scenes]
        T3 --> P3[8-10 prompts ×<br/>easy/hard scenes]
        T4 --> P4[4-6 prompts ×<br/>easy/hard scenes]
        T5 --> P5[Combo prompts]
    end

    style Actions fill:#1a1a2e,color:#fff
    style TaskGroups fill:#0f3460,color:#fff
    style Prompts fill:#16213e,color:#fff
```

**Scope:**
- Categorize existing 32 prompts by task type (delegatable — anyone with the dataset can propose)
- Design task taxonomy for all 23 actions
- Expand from 32 → ~120 prompts with balanced task × scene difficulty coverage
- Codify model behavior expectations (stops at obstacles, no auto-jump, no wall collision)
- Split GT data from training set into validation partition

---

## Documents

| Document | Audience | Description |
|---|---|---|
| [Executive Brief](docs/eval_pipeline_exec_brief.md) | Stakeholders | One-page problem + proposal |
| [Summary Report](docs/eval_pipeline_summary.md) | Team leads | Problem, current state, proposed solution, action items |
| [Full Meeting Notes](docs/eval_pipeline_full.md) | Contributors | Everything discussed, all technical details |
| [Raw Working Notes](docs/meeting_notes_raw.md) | Reference | Structured working notes |
| [Meeting Transcript](docs/meeting_transcript_raw.md) | Archive | Original verbatim meeting transcription (4 segments) |

## Key References

- **WandB Project:** [wangame_1.3b](https://wandb.ai/kaiqin_kong_ucsd/wangame_1.3b/runs/fif3z1z4?nw=nwuserjunda)
- **Model:** 1.3B parameter Minecraft world model
- **Actions:** 23 types (movement, mouse, jump, hotbar F1-F8, sprint, still)
- **Data format:** 77 frames × 23-dim binary vector per prompt
- **Current validation:** 32 prompts × 5 checkpoints = 160 videos per eval round
- **Target validation:** ~120 prompts × 5 checkpoints = 600 videos, evaluated by 5 people in <20 min
