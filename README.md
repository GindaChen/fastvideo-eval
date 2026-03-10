# WanGame Eval

**Mission:** Build a scalable, task-based evaluation pipeline for the WanGame 1.3B Minecraft World Model — replacing ad-hoc eyeballing with structured, team-parallel human evaluation that delivers results in under 20 minutes post-training.

## Mission Overview

```mermaid
graph LR
    A[Training runs on M2] -->|every 500 steps| B[Videos generated +<br/>uploaded to WandB]
    B --> C[Human reviews WandB<br/>selects Top-5 checkpoints]
    C --> D[Eval App streams<br/>videos from WandB]
    D --> E[5 evaluators rate<br/>per-task in parallel]
    E --> F[Checkpoint decision<br/>in < 20 min]
```

## Why This Repo Exists

We train a world model that generates Minecraft gameplay video from a starting frame + action sequence. The model handles 23 distinct action types, but we currently have no scalable way to evaluate checkpoint quality. Our automated metric (optical flow) is unreliable, and manual eyeballing on 32 ad-hoc prompts doesn't cover enough ground.

This repo is the home for everything needed to fix that — from evaluation design to tooling to results.

## Current Status

🟡 **Design phase** — Evaluation architecture is defined (see docs). Implementation has not started.

---

## Data Pipeline (✅ Already Working)

The data pipeline is **already in place** and does not require further work:

```mermaid
graph LR
    subgraph M2["M2 Cluster"]
        T1[Training loop] -->|every 500 steps| T2[Generate validation<br/>videos for 32 prompts]
        T2 --> T3[Compute optical<br/>flow scores]
    end

    subgraph WandB["WandB (Source of Truth)"]
        T2 -->|upload| W1[Videos + prompt<br/>metadata stored]
        T3 -->|upload| W2[Optical flow<br/>scores stored]
    end

    subgraph Human["Human Review"]
        W1 & W2 --> H1[Review WandB results]
        H1 --> H2[Select Top-5<br/>checkpoints to keep]
    end

    style M2 fill:#16213e,color:#fff
    style WandB fill:#1a1a2e,color:#fff
    style Human fill:#0f3460,color:#fff
```

**How it works today:**
- Training runs on M2, and **every 500 steps** it automatically generates validation videos for all prompts and computes optical flow scores
- Videos and scores are **uploaded from M2 to WandB** with prompt metadata
- WandB accumulates all validation results across the entire training run
- A human reviews WandB to select the **Top-5 best checkpoints** (based on optical flow + eyeballing)
- Every 5K steps, a round-number checkpoint is also saved

**What remains:** The pipeline produces the data. The remaining work is about what happens *after* the data lands in WandB — better tooling for evaluation (SP1), better scoring (SP2), and better prompt coverage (SP3).

---

## Subprojects

### SP1: Evaluation App

**Mission:** A Tinder-style web app for fast, team-parallel human evaluation of generated videos, streaming directly from WandB.

**Key detail:** Videos from WandB already have the action overlay pre-rendered — the App just plays them as-is (no compositing needed).

```mermaid
graph TD
    subgraph DataSource["Data Source"]
        DS1[WandB API] --> DS2[Stream pre-rendered<br/>videos with action overlay]
    end

    subgraph App["Eval App"]
        DS2 --> A1[Video Card UI]
        A1 --> A2[Play video at 2-3x<br/>overlay already baked in]
        A2 --> A3{Rate}
        A3 -->|Good| A4[Score: ✅]
        A3 -->|Bad| A5[Score: ❌ +<br/>issue checklist]
        A3 -->|Skip| A6[Skip]
        A5 --> A7[Optional: voice<br/>annotation]
    end

    subgraph Team["Category-Based Distribution"]
        A4 & A5 & A6 --> T1[Aggregate per-task<br/>per-checkpoint]
        T1 --> T2[5 evaluators ×<br/>5 min = 20 min]
    end

    style DataSource fill:#1a1a2e,color:#fff
    style App fill:#0f3460,color:#fff
    style Team fill:#16213e,color:#fff
```

**Scope:**
- Per-video card: play pre-rendered WandB video (already has action overlay) at 2-3x, rate good/bad/skip
- Category-specific issue checklists per task type
- **Category-based distribution:** Each evaluator gets an entire task category and reviews all its videos sequentially (e.g., Person A reviews all "basic movement" videos, Person B reviews all "camera control" videos). This avoids context-switching between categories.
- Stretch: on-demand video generation (define ad-hoc action sequence → generate → evaluate)
- Key principle: evaluate each video independently, never compare two checkpoints side-by-side

---

### SP2: Scoring & Analysis

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

### SP3: Prompt Design & Task Taxonomy

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
- **Current validation:** 32 prompts, videos generated every 500 training steps
- **Target validation:** ~120 prompts, evaluated by 5 people in <20 min
