# WanGame Eval — Service Specification

Status: Draft v1
Purpose: Define the complete evaluation pipeline for the WanGame 1.3B Minecraft World Model — from video ingestion through human rating to checkpoint ranking.

---

## 1. Problem Statement

WanGame is a 1.3B-parameter world model that generates Minecraft gameplay video conditioned on a starting frame and a 77-frame action sequence (23-dim binary vector per frame). Training produces many checkpoints. We need to determine:

1. **Which checkpoint is better** (relative comparison across checkpoints)
2. **Whether a given checkpoint meets release quality** (absolute threshold)

The pipeline solves five operational problems:

- It replaces ad-hoc eyeballing with structured, task-based human evaluation.
- It distributes evaluation across a team so 5 evaluators can complete a full round in under 20 minutes.
- It groups prompts by task category so regressions in specific action types are visible.
- It tracks scores across training runs to reveal trends and catch regressions.
- It provides enough observability to audit any individual video rating and understand why a checkpoint was ranked high or low.

Important boundary:

- This pipeline does **not** retrain or fine-tune models. It only evaluates checkpoints that already exist.
- The data pipeline (training → WandB upload) is already working and outside this spec's scope.
- This pipeline begins where WandB data ends: ingestion, human evaluation, scoring, and decision.

---

## 2. Goals and Non-Goals

### 2.1 Goals

- Stream pre-rendered validation videos from WandB into a purpose-built evaluation UI.
- Support single-person sequential evaluation as the primary mode, scaling to multi-person parallel evaluation when needed.
- Rate each video independently (good / bad / skip) — never compare two checkpoints side-by-side.
- Capture structured failure reasons via category-specific issue checklists.
- Aggregate per-video ratings into per-task scores and overall checkpoint rankings.
- Expand prompt coverage from 32 → ~120 prompts with balanced task × scene difficulty.
- Deliver checkpoint decision within 20 minutes of evaluation start.
- Operate with an append-only data model (ratings are inserted, never updated or deleted).
- Run on commodity infrastructure (RunPod CPU instance).

### 2.2 Non-Goals

- Auto-evaluation using VLMs or other AI scoring (stretch goal, not in v1).
- On-demand video generation from the eval UI (stretch goal).
- Replacing the optical flow metric — it remains a pre-filter reference signal.
- Building a general-purpose video annotation platform.
- Real-time streaming from training — videos are batch-uploaded to WandB every 500 steps.
- Pairwise checkpoint comparison UI.

---

## 3. System Overview

### 3.1 Main Components

1. **WandB Ingestion Layer**
   - Fetches validation videos and prompt metadata from the WandB API.
   - Videos already have action overlays pre-rendered (no compositing needed).
   - Indexes videos by checkpoint ID, prompt ID, and training step.

2. **Prompt & Task Registry**
   - Defines the ~120 prompts and their task category tags.
   - Maps each prompt to an action group, scene difficulty, and expected behavior.
   - Provides the issue checklist template for each task category.

3. **Chunk Distributor**
   - Splits a checkpoint's videos into chunks of ~20 videos each.
   - Tracks chunk claim status (not started / in progress / done).
   - Designed for single-person sequential use; scales to parallel claims.

4. **Evaluation App (Frontend)**
   - Tinder-style video card UI for fast rating.
   - Plays pre-rendered WandB videos at 1x / 2x / 3x speed.
   - Three rating actions: Good (✅), Bad (❌ + issue checklist), Skip (⏭).
   - Swipe gestures on mobile, keyboard shortcuts on desktop.
   - Progress tracking per chunk.

5. **Rating Store (Backend)**
   - Append-only database for all ratings.
   - Each rating includes: video ID, chunk ID, checkpoint ID, rating, issues, evaluator, timestamp.
   - Rotating backup: 10 backups, one every 5 minutes, oldest deleted outside retention window.

6. **Scoring Engine**
   - Aggregates per-video ratings into per-task scores per checkpoint.
   - Applies difficulty-adjusted tolerance (flat terrain = zero tolerance, complex = some tolerance).
   - Produces checkpoint ranking and per-task regression breakdown.
   - Compares human scores against optical flow for metric calibration.

7. **Results Dashboard**
   - Inspection view: drill into any video × checkpoint to see the human score and failure reasons.
   - Trend tracking across training runs.
   - Filter by checkpoint, task category, rating, evaluator.

### 3.2 Abstraction Layers

1. **Data Layer** (WandB-facing)
   - WandB API client, video fetching, metadata normalization.

2. **Domain Layer** (evaluation logic)
   - Prompt registry, task taxonomy, scoring rubrics, aggregation rules.

3. **Application Layer** (user-facing)
   - Evaluation card UI, chunk management, progress tracking.

4. **Persistence Layer** (storage)
   - Rating store, backup strategy, chunk state.

5. **Analysis Layer** (decision support)
   - Scoring engine, dashboard, trend visualization.

### 3.3 External Dependencies

- WandB API for video and metadata access.
- RunPod CPU instance for hosting.
- Training pipeline on M2 cluster (upstream, already working).
- Web browser (Chrome/Safari) for evaluation UI.

---

## 4. Core Domain Model

### 4.1 Entities

#### 4.1.1 Action

One of 23 binary inputs the model can receive per frame.

Categories:
- Movement: Forward (W), Back (S), Left (A), Right (D) — 4 actions
- Mouse Look: Up, Down, Left, Right — 4 actions
- Jump: Spacebar — 1 action
- Hotbar: F1 through F8 — 8 actions
- Sprint: Shift+W — 1 action
- Decelerate: speed modifier — varies
- Still: no action — 1 action

#### 4.1.2 Prompt

A validation test case consisting of a first frame and an action sequence.

Fields:
- `prompt_id` (string) — Unique identifier.
- `first_frame` (image) — Starting Minecraft screenshot.
- `action_sequence` (77 × 23 binary matrix) — Per-frame action vector.
- `action_label` (string) — Human-readable shorthand (e.g., "W only", "WSD + mouse left").
- `task_category` (string) — Task group this prompt belongs to (see §4.1.3).
- `scene_difficulty` (enum: `easy` | `hard`) — Flat terrain = easy, obstacles/complex = hard.
- `has_ground_truth` (boolean) — Whether a GT video exists for this prompt.
- `ground_truth_video_url` (string or null) — URL to GT video if available.

#### 4.1.3 Task Category

A grouping of related actions for structured evaluation.

Fields:
- `category_id` (string) — Unique identifier (e.g., `basic_movement`, `camera_control`).
- `name` (string) — Human-readable name.
- `description` (string) — What this category tests.
- `actions` (list of Action) — Which of the 23 actions this category covers.
- `issue_checklist` (list of string) — Category-specific failure modes to check.
- `tolerance` (map: scene_difficulty → tolerance_level) — Expected error tolerance per difficulty.

Defined categories:
| Category | Actions | Example Issue Checklist Items |
|---|---|---|
| Basic Movement | W, A, S, D | Wrong direction, Didn't move, Unexpected stop |
| Camera Control | Mouse Up/Down/Left/Right | Wrong turn direction, Scene inconsistency on return |
| Jump & Sprint | Space, Shift+W | No jump, Wrong height, Speed incorrect |
| Hotbar Selection | F1–F8 | No item switch, Wrong slot |
| Stability | Still (no-op) | Unexpected movement, Visual drift |
| Combinations | Multi-action sequences | Partial execution, Action interference |

#### 4.1.4 Checkpoint

A model snapshot to be evaluated.

Fields:
- `checkpoint_id` (string) — Unique identifier.
- `training_step` (integer) — Step number at which this checkpoint was saved.
- `optical_flow_score` (float or null) — Automated pre-filter score.
- `source` (enum: `top5_metric` | `round_number`) — How this checkpoint was selected.
- `wandb_run_id` (string) — WandB run this checkpoint belongs to.

#### 4.1.5 Video

A generated video for one prompt × one checkpoint.

Fields:
- `video_id` (string) — Unique identifier.
- `checkpoint_id` (string) — Which checkpoint generated this.
- `prompt_id` (string) — Which prompt was used.
- `wandb_url` (string) — URL to fetch the video from WandB.
- `has_action_overlay` (boolean) — Always `true` (pre-rendered).
- `optical_flow_score` (float or null) — Per-video automated metric.
- `training_step` (integer) — Step number for ordering.
- `duration_frames` (integer) — Always 77 for current setup.

#### 4.1.6 Chunk

A batch of ~20 videos assigned for sequential evaluation.

Fields:
- `chunk_id` (string) — Unique identifier.
- `checkpoint_id` (string) — All videos in a chunk come from one checkpoint.
- `video_ids` (list of string) — Ordered list of video IDs (~20).
- `task_category` (string or null) — If chunk is category-specific, the category. Null for mixed chunks.
- `status` (enum: `not_started` | `in_progress` | `done`)
- `assigned_to` (string or null) — Evaluator who claimed this chunk. Null if unclaimed.
- `started_at` (timestamp or null)
- `completed_at` (timestamp or null)

Chunking rules:
- Videos within a chunk should be from the **same task category** when possible, to reduce cognitive context switching.
- If a category has fewer than 20 videos, combine related categories.
- Chunk ordering within a category: easy scenes first, then hard scenes.

#### 4.1.7 Rating

An evaluator's judgment on one video. Append-only — never updated or deleted.

A video may have **multiple ratings over time** (e.g., first skipped, later re-rated as good/bad). The scoring engine always uses the **latest rating** per video per evaluator.

Fields:
- `rating_id` (string) — Unique identifier.
- `video_id` (string) — Which video was rated.
- `chunk_id` (string) — Which chunk this rating belongs to.
- `checkpoint_id` (string) — Denormalized for fast queries.
- `prompt_id` (string) — Denormalized for task-level aggregation.
- `rating` (enum: `good` | `bad` | `skip`)
- `issues` (list of string) — Selected items from the issue checklist (empty if good/skip).
- `free_text` (string or null) — Optional free-form note.
- `voice_note_url` (string or null) — Optional voice annotation URL.
- `evaluator` (string) — Who submitted this rating.
- `timestamp` (ISO 8601)
- `playback_speed` (enum: `1x` | `2x` | `3x`) — Speed at which the evaluator watched.
- `view_duration_ms` (integer) — How long the evaluator spent on this card.
- `supersedes` (string or null) — `rating_id` of the previous rating this replaces, if re-rating.

#### 4.1.7a Video Rating Status

Derived status of a video's evaluation progress. Not stored — computed from the ratings table.

| Status | Meaning | Computed When |
|---|---|---|
| `unrated` | No rating exists | No rows in ratings for this video × evaluator |
| `skipped` | Evaluator skipped, may come back | Latest rating is `skip` |
| `committed` | Final judgment recorded | Latest rating is `good` or `bad` |

Important: `skipped` is a **temporary** state. Skipped videos appear in a dedicated revisit queue so evaluators can return to them after completing their primary chunk.

#### 4.1.8 Evaluation Session

One evaluator's complete evaluation run.

Fields:
- `session_id` (string) — Unique identifier.
- `evaluator` (string)
- `checkpoint_id` (string)
- `chunks_completed` (list of string) — Chunk IDs finished in this session.
- `total_videos_rated` (integer)
- `total_duration_ms` (integer)
- `started_at` (timestamp)
- `ended_at` (timestamp or null)

#### 4.1.9 Checkpoint Score

Aggregated evaluation result for one checkpoint.

Fields:
- `checkpoint_id` (string)
- `overall_score` (float) — Weighted aggregate across all task categories.
- `per_task_scores` (map: category_id → TaskScore)
- `total_videos_rated` (integer)
- `total_good` (integer)
- `total_bad` (integer)
- `total_skipped` (integer)
- `evaluator_count` (integer)
- `computed_at` (timestamp)

#### 4.1.10 Task Score

Per-category score for one checkpoint.

Fields:
- `category_id` (string)
- `score` (float) — Percentage of "good" ratings, adjusted for difficulty tolerance.
- `easy_score` (float) — Score on easy-scene prompts only.
- `hard_score` (float) — Score on hard-scene prompts only.
- `video_count` (integer) — Total videos rated in this category.
- `common_issues` (list of {issue: string, count: integer}) — Top failure modes.
- `regression_flag` (boolean) — True if score dropped vs. previous checkpoint.

### 4.2 Stable Identifiers and Normalization Rules

- **Video ID**: Derived from `<checkpoint_id>_<prompt_id>`. Unique within a training run.
- **Chunk ID**: Derived from `<checkpoint_id>_chunk_<N>` where N is a zero-padded sequence number.
- **Rating ID**: UUID, generated at submission time.
- **Session ID**: `<evaluator>_<checkpoint_id>_<timestamp>`.
- **Category IDs**: Lowercase, underscore-separated (e.g., `basic_movement`, `camera_control`).
- **Evaluator names**: Lowercase, no spaces. Used as-is for filtering and grouping.

---

## 5. Prompt Specification (Task Taxonomy Contract)

### 5.1 Prompt Registry Format

Prompts are defined in a structured file (`prompts/registry.yaml` or equivalent):

```yaml
prompts:
  - prompt_id: "basic_fwd_flat_01"
    action_label: "W only"
    task_category: "basic_movement"
    scene_difficulty: "easy"
    has_ground_truth: false
    action_sequence_file: "prompts/sequences/basic_fwd_flat_01.npy"
    first_frame_file: "prompts/frames/basic_fwd_flat_01.png"
    notes: "Walk forward on flat grass terrain, no obstacles"
```

### 5.2 Coverage Requirements

The prompt registry must satisfy these coverage invariants:

- Every task category has at least 8 prompts.
- Every task category has both `easy` and `hard` scene variants.
- At least 60% of prompts have ground truth videos (target, not required for v1).
- No single task category exceeds 25% of total prompts.
- The `combinations` category covers at least 3 distinct multi-action patterns.

### 5.3 Prompt Expansion Rules

When expanding from 32 → ~120 prompts:

1. Audit existing 32 prompts and assign task category + scene difficulty tags.
2. Identify uncovered action × difficulty combinations.
3. Design new prompts to fill gaps, prioritizing:
   a. Actions with zero coverage (hotbar, sprint, jump)
   b. Easy-scene variants of well-covered actions (currently too few)
   c. Combination actions (multi-key sequences)
4. For each new prompt, record expected model behavior based on known model behavior rules (§5.4).

### 5.4 Model Behavior Rules (Evaluation Ground Truth)

These are codified expectations derived from one month of training observation. Evaluators and scoring rubrics must respect these rules:

| Behavior | Expected Model Output | Evaluation Implication |
|---|---|---|
| Hitting an obstacle | **Stops walking** — never auto-jumps | "Didn't jump over obstacle" is NOT a failure |
| Walking near a wall | Stops at safe distance, no clipping | Wall collision = failure |
| Flat terrain movement | Near-perfect, smooth | Zero tolerance for errors |
| Complex terrain | May pause, hesitate, minor artifacts OK | Adjusted tolerance |
| Still (no action) | Scene should be static, minor drift OK | Large drift = failure |
| Sprint | Faster-than-walk movement | Must be visibly faster than W-only |

---

## 6. Configuration Specification

### 6.1 Application Config

Configuration for the evaluation pipeline, stored in `config.yaml` at repo root:

```yaml
# WandB connection
wandb:
  project: "wangame_1.3b"
  entity: "kaiqin_kong_ucsd"
  api_key: "$WANDB_API_KEY"          # Environment variable indirection

# Evaluation settings
evaluation:
  chunk_size: 20                      # Videos per chunk
  default_playback_speed: "2x"        # Default video speed
  auto_play: true                     # Auto-play video on card entry
  max_evaluators: 10                  # Max concurrent evaluators
  require_all_chunks: false           # Allow partial evaluation submission

# Scoring settings
scoring:
  easy_tolerance: 0.0                 # No tolerance for easy scene errors
  hard_tolerance: 0.15                # 15% tolerance for hard scenes
  min_videos_per_category: 5          # Minimum rated videos before category score is valid
  aggregation_method: "weighted"      # "weighted" | "uniform"
  category_weights:                   # Relative weights per category (sum to 1.0)
    basic_movement: 0.25
    camera_control: 0.20
    jump_sprint: 0.15
    hotbar: 0.10
    stability: 0.15
    combinations: 0.15

# Infrastructure
server:
  host: "0.0.0.0"
  port: 8080
  database: "eval.db"                 # SQLite file path

# Backup
backup:
  enabled: true
  interval_minutes: 5
  retention_count: 10
  backup_dir: "backups/"
```

### 6.2 Environment Variable Resolution

Config values starting with `$` are resolved from environment variables at startup. If the variable is not set, the service must fail with a clear error indicating which variable is missing.

### 6.3 Validation Rules

At startup, the service must validate:
- WandB credentials are present and the project is accessible.
- Database file is writable.
- Backup directory exists or can be created.
- Prompt registry file exists and parses without errors.
- All category weights sum to 1.0 (within floating point tolerance).

---

## 7. Evaluation Workflow State Machine

### 7.1 Evaluation Round States

An evaluation round is the complete evaluation of one set of checkpoints.

```
                    ┌──────────────┐
                    │   Created    │
                    └──────┬───────┘
                           │ checkpoints selected
                    ┌──────▽───────┐
                    │   Ingesting  │  ← fetching videos from WandB
                    └──────┬───────┘
                           │ all videos fetched
                    ┌──────▽───────┐
                    │   Chunked    │  ← videos split into evaluation chunks
                    └──────┬───────┘
                           │ first chunk claimed
                    ┌──────▽───────┐
                    │  Evaluating  │  ← evaluators rating videos
                    └──────┬───────┘
                           │ all chunks complete (no unrated videos remain)
                    ┌──────▽───────┐
                    │   Scoring    │  ← aggregation running
                    └──────┬───────┘
                           │ scores computed
                    ┌──────▽───────┐
                    │  Completed   │  ← results available, Score Review unlocked
                    └──────────────┘
```

Note: A round can move to `Scoring` even if some videos are still `skipped` — the evaluator explicitly triggers scoring when they are satisfied. Skipped videos are excluded from scoring but remain revisitable.

### 7.2 Chunk Lifecycle

```
  not_started  ──claim──►  in_progress  ──all videos rated or skipped──►  passed
                                │                                            │
                                │ (evaluator pauses)                         │ skipped videos revisited
                                ▼                                            ▼
                           in_progress (resumes)                           done (all committed)
```

- A chunk is `passed` when every video has at least one rating (good, bad, or skip).
- A chunk is `done` only when every video is `committed` (good or bad) — no remaining skips.
- Evaluators can re-enter a `passed` chunk to revisit its skipped videos.
- Chunks are never reassigned. If an evaluator abandons a chunk, an admin can manually reset it.

### 7.3 Per-Video Rating Flow

```
  Video displayed (unrated or skipped)
       │
       ├──► Good  ──► Rating stored (committed) ──► Next video
       │
       ├──► Skip  ──► Rating stored (skipped)   ──► Next video
       │                  └──► Video enters Skipped Queue for later revisit
       │
       └──► Bad   ──► Issue checklist shown
                            │
                            └──► Issues selected + Submit ──► Rating stored (committed) ──► Next video
```

### 7.4 Skip Revisit Flow

Skipped videos are **not permanently excluded**. They accumulate in a revisit queue:

```
  Evaluator finishes primary chunk pass
       │
       ▼
  "N skipped videos remaining" prompt shown
       │
       ├──► "Revisit Skipped" ──► Skipped Queue mode
       │         │
       │         └──► Each skipped video shown again
       │                   ├──► Good/Bad  ──► New rating appended (supersedes skip)
       │                   └──► Skip again ──► Remains in queue
       │
       └──► "Finalize as-is" ──► Skipped videos excluded from scoring
```

Key rules:
- Re-rating a skipped video appends a new Rating row (append-only). The `supersedes` field links to the previous skip.
- The scoring engine always uses the **latest** rating per video per evaluator.
- The revisit queue shows the video with its original context (prompt label, checkpoint, action summary) so the evaluator has full context.

---

## 8. WandB Integration Contract

### 8.1 Required Operations

1. **List Runs** — Fetch all runs in the project to identify available checkpoints.
2. **Fetch Validation Videos** — For a given run and step, retrieve all generated validation videos.
3. **Fetch Prompt Metadata** — For each video, retrieve the associated prompt label and action sequence.
4. **Fetch Optical Flow Scores** — Retrieve automated scores for pre-filtering.

### 8.2 Data Normalization

- Video URLs must be resolved to direct-download URLs (not WandB UI links).
- Prompt labels from WandB are normalized to lowercase and mapped to `prompt_id` via the prompt registry.
- Training steps are integers; normalize string representations.
- Optical flow scores are floats; missing scores are represented as `null`, not zero.

### 8.3 Caching Strategy

- Downloaded videos are cached locally to avoid re-fetching during evaluation.
- Cache key: `<checkpoint_id>/<prompt_id>.mp4`.
- Cache invalidation: manual only (videos for a given checkpoint × prompt never change).
- Cache size warning: at 120 prompts × 5 checkpoints, expect ~600 videos per round.

### 8.4 Error Handling

- WandB API rate limits: exponential backoff starting at 1s, max 60s.
- Missing videos (prompt exists in registry but no video in WandB): log warning, mark video as `unavailable`, exclude from chunks.
- Network failures during video fetch: retry 3 times, then mark as `unavailable`.

---

## 9. Evaluation App Specification

The app has two primary modes that correspond to two fundamentally different user intents:

| Mode | Intent | Primary Action |
|---|---|---|
| **Data Operation** | Add or modify evaluation data | Rate videos, revisit skips, commit judgments |
| **Score Review** | Inspect committed data | Browse scores, filter, drill into decisions |

The modes are accessible from the top-level Dashboard via distinct entry points. They share the same underlying data but present it differently.

### 9.1 Mode 1: Data Operation

This is where evaluators **produce data** — rating videos and committing scores.

#### Screen 1a: Dashboard (Data Operation Entry)

- Header with project name and WandB link.
- **Progress overview:** X of Y videos committed (good/bad), Z skipped, W unrated.
- **Chunk grid** showing status badges:
  - ✅ Done (all committed) / 🟡 Passed (all touched, some skips) / 🔵 In Progress / ⬜ Not Started
- **"Start Evaluating" button** → opens next unfinished chunk.
- **"Revisit Skipped" button** → opens the Skipped Queue (cross-chunk view of all skipped videos).
- The dashboard clearly separates "unrated" from "skipped" so the evaluator knows what needs first-pass attention vs. second-pass revisit.

#### Screen 2a: Evaluation Card (Core Rating UX)

Layout: full-screen card, vertically stacked.

- Top: chunk progress ("Video 3 of 20") with dot indicators. Dots colored by status: ● committed, ○ skipped, ◌ unrated.
- Center (60%): video player with play/pause, speed toggle (1x/2x/3x), scrub bar. Auto-plays on entry.
- Below video: prompt label, checkpoint ID, action summary.
- Bottom (fixed): three rating buttons — ❌ Bad (red), ⏭ Skip (gray), ✅ Good (green).
- Tapping Bad → bottom sheet with issue checklist.
- Optional voice annotation button.
- Card animates out on rating, next card slides in.
- **Re-rating indicator:** If the video was previously skipped, show a subtle badge "Previously skipped" so the evaluator has context.

#### Screen 2b: Skipped Queue (Revisit Mode)

A filtered view showing only skipped videos across all chunks.

- Same card UX as Screen 2a, but only skipped videos.
- Sorted by chunk order (so context is preserved).
- Header shows: "Skipped Videos: N remaining".
- Each card shows which chunk it came from.
- Rating a video here appends a new Rating that supersedes the skip.
- Skipping again keeps the video in the queue.
- "Finalize" button at end: confirms that remaining skips should be excluded from scoring.

#### Screen 3a: Chunk Summary

Shown after completing a chunk pass (all videos touched).

- Stats: ✅ Good N, ❌ Bad N, ⏭ Skipped N.
- Most common issues (aggregated from checklists).
- **If skips remain:** "You skipped N videos. Revisit now or come back later."
- Buttons: "Next Chunk →", "Revisit Skipped", "Back to Dashboard".

### 9.2 Mode 2: Score Review

This is where users **inspect committed data** — read-only, no modifications.

#### Screen 1b: Score Review Entry

- **Checkpoint selector** (dropdown or tabs): pick which checkpoint(s) to review.
- **Summary cards** per checkpoint: overall score, per-task breakdown, total videos rated.
- **Quick comparison table:** checkpoints side-by-side showing per-task scores (this is *score* comparison, not video comparison — consistent with the "no pairwise video comparison" principle).

#### Screen 4a: Per-Checkpoint Detail View

- **Per-task score bars** with color coding (green = strong, yellow = OK, red = regression).
- **Regression flags** highlighted with ⚠️ badges.
- **Drill-down by task category:** click a category → see all videos in that category with their ratings.

#### Screen 4b: Per-Video Inspection

- **Filterable table** with columns:
  - Video thumbnail (first frame)
  - Prompt / action label
  - Task category
  - Checkpoint ID
  - Rating (✅ / ❌ / ⏭) — shows the **latest** rating
  - Rating history (if re-rated: shows all ratings with timestamps)
  - Issues (if bad)
  - Evaluator
  - Timestamp
- **Filters (top bar):** checkpoint, task category, rating, evaluator, scene difficulty.
- **Click row → expands:** full video playback + all annotation details + rating history.
- **Export:** Download filtered results as CSV.

#### Screen 4c: Trend View

- Line charts showing per-task scores across checkpoints (x-axis = training step).
- Optical flow score overlaid for calibration comparison.
- Highlights regressions and improvements.

### 9.3 Interaction Model

| Platform | Good | Bad | Skip | Play/Pause |
|---|---|---|---|---|
| Mobile | Swipe right | Swipe left | Swipe up | Tap video |
| Desktop | → or D | ← or A | ↑ or W | Space |

Additional shortcuts (Data Operation mode only):
| Key | Action |
|---|---|
| R | Replay current video from start |
| 1 / 2 / 3 | Set playback speed |
| Tab | Toggle between Data Operation and Score Review |

### 9.4 Performance Requirements

- Video must begin playing within 500ms of card display.
- Card transition animation: 200ms ease-out.
- Target throughput: ~20 videos rated in 5 minutes per evaluator.
- Offline resilience: ratings are locally buffered and synced on reconnect.
- Score Review mode: table loads within 1s for up to 600 videos.

---

## 10. Scoring Specification

### 10.1 Per-Video Score Resolution

Since a video may have multiple ratings (e.g., skip → later good), the scoring engine resolves to the **latest rating per video per evaluator** by timestamp.

| Resolved Rating | Numeric Value | Treatment |
|---|---|---|
| Good | 1.0 | Included in aggregation |
| Bad | 0.0 | Included in aggregation |
| Skip (never re-rated) | — | Excluded from aggregation, counted separately |

### 10.2 Per-Task Score Computation

For each task category `c` and checkpoint `k`:

```
raw_score(c, k) = count(good) / count(good + bad)    // skip excluded

easy_score(c, k) = raw_score over easy-scene videos only
hard_score(c, k) = raw_score over hard-scene videos only

adjusted_score(c, k) = easy_score(c, k) * (1.0 - easy_tolerance)
                      + hard_score(c, k) * (1.0 - hard_tolerance)
```

If `count(good + bad)` < `min_videos_per_category`, the score is marked as `insufficient_data` and excluded from the overall ranking with a warning.

### 10.3 Overall Checkpoint Score

```
overall_score(k) = Σ (category_weight[c] × adjusted_score(c, k))  for all categories c
```

### 10.4 Ranking and Decision

- Checkpoints are ranked by `overall_score` descending.
- Regression detection: if `adjusted_score(c, k)` drops by more than 10% compared to the previous checkpoint's score for the same category, flag as regression.
- Decision output: ranked list with per-task breakdown, regression flags, and comparison to optical flow pre-filter ranking.

### 10.5 Optical Flow Calibration

For each evaluation round, compute the Spearman rank correlation between:
- Human-derived checkpoint ranking (from §10.4)
- Optical-flow-derived checkpoint ranking

Report this correlation to track whether the automated metric is improving or degrading as the model evolves.

---

## 11. Data Persistence and Safety

### 11.1 Write Protocol

- All ratings are **append-only**. No UPDATE or DELETE operations on the ratings table.
- Chunk status transitions are monotonic: `not_started → in_progress → done`. No backward transitions except manual admin reset.
- Computed scores are versioned with timestamps. Re-computation appends a new score record.

### 11.2 Database Schema (SQLite)

```sql
CREATE TABLE ratings (
    rating_id       TEXT PRIMARY KEY,
    video_id        TEXT NOT NULL,
    chunk_id        TEXT NOT NULL,
    checkpoint_id   TEXT NOT NULL,
    prompt_id       TEXT NOT NULL,
    rating          TEXT NOT NULL CHECK(rating IN ('good', 'bad', 'skip')),
    issues          TEXT,          -- JSON array of strings
    free_text       TEXT,
    voice_note_url  TEXT,
    evaluator       TEXT NOT NULL,
    playback_speed  TEXT CHECK(playback_speed IN ('1x', '2x', '3x')),
    view_duration_ms INTEGER,
    supersedes      TEXT,          -- rating_id of previous rating if re-rating a skip
    timestamp       TEXT NOT NULL   -- ISO 8601
);

CREATE TABLE chunks (
    chunk_id        TEXT PRIMARY KEY,
    checkpoint_id   TEXT NOT NULL,
    video_ids       TEXT NOT NULL,  -- JSON array of strings
    task_category   TEXT,
    status          TEXT NOT NULL DEFAULT 'not_started'
                    CHECK(status IN ('not_started', 'in_progress', 'passed', 'done')),
    assigned_to     TEXT,
    started_at      TEXT,
    completed_at    TEXT
);

CREATE TABLE checkpoint_scores (
    score_id        TEXT PRIMARY KEY,
    checkpoint_id   TEXT NOT NULL,
    overall_score   REAL NOT NULL,
    per_task_scores TEXT NOT NULL,  -- JSON map
    total_videos    INTEGER NOT NULL,
    total_good      INTEGER NOT NULL,
    total_bad       INTEGER NOT NULL,
    total_skipped   INTEGER NOT NULL,
    evaluator_count INTEGER NOT NULL,
    computed_at     TEXT NOT NULL
);

CREATE INDEX idx_ratings_checkpoint ON ratings(checkpoint_id);
CREATE INDEX idx_ratings_prompt ON ratings(prompt_id);
CREATE INDEX idx_ratings_evaluator ON ratings(evaluator);
CREATE INDEX idx_chunks_checkpoint ON chunks(checkpoint_id);
CREATE INDEX idx_chunks_status ON chunks(status);
```

### 11.3 Backup Strategy

- Rotating backups of the SQLite database file.
- Backup interval: every 5 minutes (configurable).
- Retention: keep the 10 most recent backups.
- Backup naming: `eval_backup_<ISO8601_timestamp>.db`.
- On startup, verify the most recent backup is readable.

### 11.4 Recovery

- On crash recovery, the service restarts from the SQLite state. No separate recovery log needed.
- Chunk status is derived from rating count vs. video count if metadata is inconsistent.
- Incomplete chunks (evaluator abandoned) are detectable by `status = in_progress` with no new ratings for > 30 minutes.

---

## 12. Infrastructure and Deployment

### 12.1 Hosting

- **Target platform:** RunPod CPU instance.
- **Components:** Single process serving both the API and static frontend.
- **Database:** SQLite file on attached storage.
- **Video cache:** Local directory on attached storage.

### 12.2 API Endpoints

**Data Operation endpoints:**

| Method | Path | Description |
|---|---|---|
| GET | `/api/dashboard` | Current evaluation round status, chunk overview with skip counts |
| GET | `/api/chunks` | List chunks with status and assignment info |
| POST | `/api/chunks/:id/claim` | Claim a chunk for evaluation |
| GET | `/api/chunks/:id/videos` | Get videos for a chunk (ordered), with per-video rating status |
| POST | `/api/ratings` | Submit a rating (append-only, may supersede a previous skip) |
| GET | `/api/skipped` | List all skipped videos across chunks (for revisit queue) |
| POST | `/api/rounds` | Start a new evaluation round (admin) |
| GET | `/api/health` | Service health check |

**Score Review endpoints:**

| Method | Path | Description |
|---|---|---|
| GET | `/api/results` | Aggregated scores across all checkpoints |
| GET | `/api/results/:checkpoint_id` | Per-checkpoint detailed breakdown with per-task scores |
| GET | `/api/results/:checkpoint_id/videos` | Per-video ratings for a checkpoint (filterable by category, rating, evaluator) |
| GET | `/api/results/:checkpoint_id/trend` | Score trend across training steps |
| GET | `/api/ratings/:video_id/history` | Full rating history for a video (all appended ratings) |
| GET | `/api/results/export` | Export filtered results as CSV |

### 12.3 Authentication

- v1: Simple shared token in `Authorization: Bearer <token>` header.
- Evaluator identity is self-reported in the `evaluator` field.
- No role-based access control in v1 — all authenticated users have full access.

---

## 13. Logging and Observability

### 13.1 Structured Logs

Every log entry includes:
- `timestamp` (ISO 8601)
- `level` (debug / info / warn / error)
- `component` (ingestion / evaluation / scoring / api)
- `event` (e.g., `rating_submitted`, `chunk_claimed`, `score_computed`)

### 13.2 Key Metrics

| Metric | Purpose |
|---|---|
| Ratings per minute per evaluator | Track evaluation speed |
| Chunk completion time | Identify slow chunks or confused evaluators |
| Issue frequency by category | Surface systematic model failures |
| Score variance across evaluators | Detect inconsistent evaluators |
| Good/Bad ratio per category | Quick model capability overview |
| Optical flow vs. human rank correlation | Metric calibration tracking |

### 13.3 Alerts

- If an evaluation round has been in `Evaluating` state for > 60 minutes, warn.
- If a chunk has been `in_progress` for > 30 minutes with no new ratings, warn.
- If backup fails, error.

---

## 14. Test and Validation Matrix

### 14.1 Prompt Registry

- [ ] Registry file parses without errors.
- [ ] All prompts have valid task category and scene difficulty.
- [ ] Coverage invariants (§5.2) are satisfied.
- [ ] Action sequence files exist and have correct dimensions (77 × 23).

### 14.2 WandB Integration

- [ ] Can authenticate and list runs.
- [ ] Can fetch videos for a known checkpoint and step.
- [ ] Missing videos are handled gracefully (logged, excluded from chunks).
- [ ] Rate limiting triggers backoff correctly.

### 14.3 Chunking

- [ ] Videos are split into chunks of configured size.
- [ ] Chunks group same-category videos together when possible.
- [ ] Easy scenes sort before hard scenes within a chunk.
- [ ] Chunk claiming prevents double-assignment.

### 14.4 Rating Submission

- [ ] Good/Bad/Skip ratings are stored correctly.
- [ ] Bad ratings include at least one issue from the checklist.
- [ ] Ratings are append-only — no existing ratings are modified.
- [ ] Re-rating a skipped video appends a new row with `supersedes` pointing to the previous rating.
- [ ] Chunk status transitions correctly (not_started → in_progress → passed → done).
- [ ] View duration and playback speed are recorded.
- [ ] Skipped videos appear in the revisit queue.

### 14.5 Scoring

- [ ] Scoring resolves to the **latest** rating per video per evaluator.
- [ ] Re-rated (skip → good/bad) videos are included in aggregation.
- [ ] Videos with only skip ratings are excluded from aggregation but counted separately.
- [ ] Per-task scores compute correctly with tolerance adjustment.
- [ ] Categories with insufficient data are flagged, not silently zero.
- [ ] Overall checkpoint ranking matches manual calculation.
- [ ] Regression detection fires when score drops > 10%.
- [ ] Optical flow correlation computes correctly.

### 14.6 Backup and Recovery

- [ ] Backups are created on schedule.
- [ ] Old backups are rotated correctly.
- [ ] Service recovers from crash with consistent state.
- [ ] Abandoned chunks are detectable.

### 14.7 Frontend — Data Operation Mode

- [ ] Video plays within 500ms of card display.
- [ ] Keyboard shortcuts work on desktop.
- [ ] Swipe gestures work on mobile.
- [ ] Issue checklist appears on Bad rating.
- [ ] Progress tracking updates correctly (distinguishes unrated / skipped / committed).
- [ ] Offline rating buffer syncs on reconnect.
- [ ] Skipped Queue shows all skipped videos across chunks.
- [ ] Re-rating from Skipped Queue works correctly.
- [ ] "Previously skipped" badge appears on re-visited videos.

### 14.8 Frontend — Score Review Mode

- [ ] Checkpoint summary cards load correctly.
- [ ] Per-task score bars render with correct values.
- [ ] Regression flags appear when score drops > 10%.
- [ ] Per-video inspection table is filterable.
- [ ] Rating history displays all appended ratings for a video.
- [ ] CSV export includes all filtered data.
- [ ] Trend view shows scores across training steps.

---

## 15. Implementation Checklist (Definition of Done)

### 15.1 Required for v1

- [ ] Prompt registry with all 32 existing prompts categorized.
- [ ] WandB ingestion layer fetching videos and metadata.
- [ ] Chunk distributor splitting videos into evaluation chunks.
- [ ] Evaluation card UI with video playback, rating, and issue checklist.
- [ ] Append-only rating store with SQLite backend.
- [ ] Chunk claiming and progress tracking.
- [ ] Dashboard with chunk overview and progress bar.
- [ ] Scoring engine with per-task aggregation and checkpoint ranking.
- [ ] Results inspection view with filters.
- [ ] Rotating backup strategy.
- [ ] Structured logging.
- [ ] Deployable on RunPod CPU instance.

### 15.2 Required for v2 (Post-Launch)

- [ ] Prompt expansion from 32 → ~120 prompts.
- [ ] Ground truth video recording for new prompts.
- [ ] Voice annotation support.
- [ ] Trend tracking across multiple evaluation rounds.
- [ ] Optical flow calibration reporting.
- [ ] Multi-evaluator consistency analysis.

### 15.3 Stretch Goals (Not Required)

- [ ] On-demand video generation from the eval UI.
- [ ] VLM-based auto-evaluation using codified model behavior rules.
- [ ] Real-time WandB webhook integration (instead of polling).
- [ ] Export results to WandB as custom charts.
