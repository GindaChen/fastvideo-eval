# World Model Evaluation Pipeline — Meeting Notes

**Date:** 2026-03-10

---

## Problem Statement

Training produces many checkpoints and a large volume of generated videos. We need to determine:
1. **Which checkpoint is better** (relative comparison)
2. **Whether a checkpoint meets release quality** (absolute threshold)

---

## Evaluation Dimensions

### 1. Video Quality
- Not just simple eyeballing
- Must distinguish between **simple scenes** vs **complex scenes**

### 2. Consistency
- Test turn-and-return behavior (e.g., turn left → return, turn right → return, look up → return)
- Many sub-dimensions involved

### 3. Action Following (Hardest)
- 23 distinct actions (constrained by dataset — cannot reduce, must fit)
- Eyeballing 23 actions is infeasible → must validate by **task groups**:
  - (a) Movement only
  - (b) Mouse only
  - (c) Build only
  - (d) Attack / Chase
- **Time estimate:** Focused evaluation takes ~1 day; running checkpoint evaluation takes ~30 min

---

## The 23 Actions (Minecraft)

| Category | Actions |
|---|---|
| Movement | Forward, Back, Left, Right |
| Mouse | 4 directional mouse movements |
| Jump | Spacebar |
| Hotbar | F1–F8 (select item in hotbar) |
| Sprint | Shift + Forward (combo key) |
| Still | No action |

**Currently well-evaluated:** Forward, Back, Left, Right, Mouse (4 dirs), Still = **9 actions**
**Not yet evaluated:** Remaining ~14 actions

---

## Training Experience & Model Behavior Expectations

One month of training has yielded domain knowledge that should be distilled and codified:

| Behavior | Expected Model Output |
|---|---|
| Hitting obstacle | **Stops** (does NOT auto-jump) |
| Near wall | Stops at safe distance; no wall collision |
| Collision data | Filtered out — high-obstacle-flow samples removed from training |
| Flat terrain movement | Should be near-perfect |
| Complex terrain | Some tolerance for stopping/hesitation |

> **Idea:** Distill this expert knowledge into written rules → feed to a VLM agent to auto-filter/select prompts and evaluate videos. Challenge: input is only **first frame + action list** (no text description), so the VLM needs visual understanding capability.

---

## Current Training & Checkpoint Flow

1. Run training with a set of parameters
2. **Every 500 steps** → run evaluation
3. Use **Optical Flow** as the primary automated metric to select the best checkpoints
4. Maintain a rolling **Top-5 best checkpoints** based on this metric
5. **Every 5,000 steps** → always save a round-number checkpoint
6. Train up to ~70K steps max

### Optical Flow Metric — Deep Dive

- Technically an **LPIPS variant** that considers frame-to-frame diffs between GT video and generated video
- Requires a GT video to compute → cannot be used for prompts without GT
- **Unreliable even WITH GT:** Object distance to camera affects flow magnitude — near objects produce larger flow than far objects for the same action, introducing systematic error
- **Unreliable without GT:** Synthetic optical flow from action list alone is inaccurate (scene/object-position dependent)
- Currently the **only automatic metric for action following** — nothing better available yet
- Primary role in validation: **reference signal to speed up eyeballing**, not a ground-truth score

### Why Eyeballing Is Still Needed

Optical Flow is **not fully accurate**:
- Inaccurate for **Still** (no-action) scores
- Inaccurate for **wall collision** scores
- Scene-dependent: same action → different flow in different environments

→ Must manually compare best-metric checkpoints against the 5K-step round-number checkpoints

---

## Current Validation Setup

- **32 prompts** → each checkpoint generates 32 videos
- Compare against **5 other checkpoints**
- For each of the 32 videos, determine which checkpoint is best
- Aggregate to decide overall best checkpoint

### Actual Eyeballing Method (Clarification)

> The method is **elimination-based**, not pairwise scoring.

- Watch the 32 videos for a checkpoint
- If a video has a visible problem → **exclude that checkpoint** for that task
- NOT: compare two checkpoints side-by-side and tally +1/-1 scores

### Problems with Current Setup

1. **32 prompts were ad-hoc** (not designed with task coverage in mind)
2. **No task tags/categories** on prompts (e.g., "evaluate walking", "evaluate sprint")
3. **Unbalanced coverage:** Complex scenes over-represented, simple scenes under-represented
4. **Not comprehensive** enough — likely need **~120 prompts** to cover all tasks properly
5. **Eyeballing doesn't scale:** Can realistically compare ~3 videos per checkpoint pair, which is insufficient

---

## Action Data Format

- Raw storage: **77 frames × 23-dim binary vector** (one vector per frame)
- Each dimension = one of the 23 possible actions (1 = pressed, 0 = not pressed)
- No explicit timestamps — frame index IS the timestamp
- Example: "W only" = W pressed for some frames, then released (W + Still)
- Complex sequences labeled shorthand: "WSD", "W + mouse left", etc.
- Overlay rendering: at each frame, show which keys are active

---

## Two Key Next Steps

1. **Automate video extraction pipeline** — From the 1B dataset, extract and pair videos so humans can efficiently verify them. Simple infra to convert raw data into evaluation-ready pairs.
2. **Build comprehensive eval App from the start** — Rather than iterating on a minimal version, build something comprehensive that can serve as the long-term reference tool.

---

## Desired Evaluation Architecture

### Task-Based Grouping
- Categorize all prompts by task (e.g., "basic movement", "sprint", "mouse look")
- Each group gets its own score
- Find a checkpoint that performs well **across all task groups**

### Per-Task Scoring with Scene Difficulty
- **Easy scene** (flat terrain): Zero tolerance for errors
- **Complex scene** (obstacles, auto-jump): Some tolerance acceptable
- Different standards for different scene difficulties within each task

### Proposed "Tinder-Style" Evaluation App

**UI Elements per evaluation card:**

| Element | Description |
|---|---|
| Initial image (first frame) | The starting scene |
| Action list overlay | Keyboard actions overlaid on video (current approach) |
| Generated video | Playable at 2x–3x speed |
| Rating options | Swipe/tap to judge quality |
| Category-specific issues | Checklist of known issues for this task category |
| Voice annotation (optional) | Describe what went wrong via voice input |

**Action List Display:**
- Currently overlaid directly on the generated video
- 23 actions are hard to show all at once → overlay shows active keys at each frame

**On-Demand Video Generation (stretch goal):**
- User defines an ad-hoc action sequence in the App
- App sends first-frame + action list to a checkpoint
- Generates video on the fly for immediate evaluation
- Enables testing edge cases without pre-generating everything

### Team-Scale Human Evaluation

- **Benchmark:** 1 person can process ~30 videos in 5 minutes
- **With 5 evaluators** running in parallel via the App → full human eval in **10–20 minutes**
- Google reportedly gets human eval results within 30 min of training completion — this approach matches that
- Key enabler: distribute the App to the team post-training, everyone evaluates their assigned slice concurrently

### Key Design Insight
> **Do NOT directly compare two checkpoints.** Instead, evaluate each video independently on its own merit. Aggregate per-video scores to determine checkpoint quality.

---

## Comparison Math (TODO)

> "Can you help me calculate how many comparisons I actually need to look at?"

- 5 checkpoints × 32 videos = 160 videos currently
- With ~120 prompts: 5 × 120 = 600 videos
- Need a principled aggregation method (not just "who wins the most videos")

---

## Infrastructure & Data Pipeline

**WandB Project:** [wangame_1.3b](https://wandb.ai/kaiqin_kong_ucsd/wangame_1.3b/runs/fif3z1z4?nw=nwuserjunda)

| Component | Location | Notes |
|---|---|---|
| Training compute | M2 | Videos generated here first |
| Video storage | **WandB** | Validation videos uploaded with prompt metadata |
| Checkpoints | Local / M2 | NOT on WandB — must load from checkpoint path |
| Prompt metadata | WandB | Each video tagged with its prompt |

### Pipeline Gap
- Videos on M2 need to be **streamed to WandB** (or another endpoint) for the eval App
- WandB already has prompt labels → just need to **wrap with task/category tags** to enable grouped evaluation
- Post-training video generation pipeline (checkpoint → prompts → videos) needs to be automated

---

## Validation Dataset Structure

### Two types of validation prompts

| Type | Has Ground Truth? | Source | Optical Flow usable? |
|---|---|---|---|
| From training set (split) | ✅ Yes | Human gameplay recordings | ✅ Yes |
| Custom-designed prompts | ❌ No | Hand-crafted first-frame + action list | ⚠️ Only synthetic (unreliable) |

### Current gap
- Validation currently uses **custom prompts without GT** (novel images, not split from training)
- This means optical flow is unreliable for these prompts
- **Should split some GT data** from training set into validation

### Constructing New GT Cases

| Step | What's needed |
|---|---|
| 1. Pick a scene (first frame) | Already have these |
| 2. Define an action sequence | Can be hand-written |
| 3. Record GT video | **Must run Minecraft simulator** and have a human play the sequence |
| 4. Crop and package as dataset row | Straightforward |

- **Complexity:** Low (conceptually simple)
- **Overhead:** High (need someone to actually play Minecraft and record)
- **Resource:** WorkLab has a Minecraft server available
- **Owner:** Project lead doesn't want to do this personally → needs delegation

---

## V6GEN vs World Model Evaluation

| Aspect | V6GEN | World Model |
|---|---|---|
| Evaluation | Eyeballing "looks good" is sufficient | Needs **Consistency + Action Following** |
| Approach | Visual quality check | Task-based scoring + automated metrics |
| Literature | Could do a literary survey + reproduce others' scores | Dedicated to another team member, but project lead has deepest context |

---

## Bottleneck Analysis: Who Owns What

| Bottleneck | Owner | Notes |
|---|---|---|
| **Redesign validation prompts** | Project lead (you) | Must decide which prompts to add/remove for task coverage |
| **Task categorization of existing prompts** | Anyone with context / agent | Given the dataset, someone else can propose 3 options for you to pick |
| **Build eval App** | Engineer / agent | Implementation task, not blocked on domain expertise |
| **Define scoring rubric** | Project lead | Requires deep understanding of action semantics |
| **Record GT videos in Minecraft** | Delegatable | Low skill, high overhead — anyone with Minecraft access can do it |
| **Distill expert knowledge into rules** | Project lead | Needed for VLM-based auto-evaluation |

> **Key unblock:** If the full dataset (all prompts + actions) is shared, the task categorization and prompt expansion can be done by others. Project lead reviews and selects from proposals.

---

## Near-Term Action Items

### Immediate (Unblock evaluation)
- [ ] **Share full dataset** (prompts + action labels) so others can help with categorization
- [ ] **Categorize the 32 existing prompts** by task type — can be proposed by agent/teammate, reviewed by lead
- [ ] **Redesign validation prompts** — add/remove to achieve balanced task coverage
- [ ] **Expand prompt set** from 32 → ~120
- [ ] **Split some GT data from training set** into validation set (currently all validation is non-GT)

### Ground Truth Construction
- [ ] **Record GT videos** using Minecraft simulator (WorkLab server available)
- [ ] **Define target action sequences** for GT recording (e.g., "forward 5 steps, back 5 steps")
- [ ] **Delegate recording task** — low skill, high overhead, project lead doesn't want to do it personally

### Pipeline
- [ ] **Automate post-training video generation** (checkpoint + prompt set → video batch)
- [ ] **Add task/category tags** to WandB prompt metadata
- [ ] **Stream M2 videos** to accessible endpoint for eval App

### Evaluation App
- [ ] **Build Tinder-style evaluation UI** — show first frame, action overlay, video, rating, voice annotation
- [ ] **Support team-parallel evaluation** (5 people × 5 min = full eval)
- [ ] **Add category-specific issue checklists** per task type
- [ ] **On-demand video generation** — define ad-hoc action sequence → generate → evaluate
- [ ] **Calculate required comparison count** for statistical significance

### Data Pipeline (1B Dataset)
- [ ] **Automate video pair extraction** from 1B dataset into evaluation-ready format
- [ ] **Build pair viewer** for efficient human verification

### Scoring & Rubric
- [ ] **Design task grouping** for the 23 actions
- [ ] **Define per-task scoring rubric** with difficulty-adjusted tolerance
- [ ] **Balance simple vs complex scenes** in prompt set
- [ ] **Distill expert knowledge** into written evaluation rules for potential VLM-based auto-eval

---

## Key Quotes

> "如果让我专注处理，一天也能搞完。但如果只是运行 evaluate checkpoint 这件事，大概半小时就能扫完并做决定。"

> "你不能直接比较两个 checkpoint，而只能通过每一个 video 去评价这个 video 本身如何。"

> "我的目标是：假设我不能 100% evaluate 完整个 landscape，但我可以通过 40% 的 human effort 大概了解这些 checkpoint 的优劣。"

> "如果你每次 training 结束之后给大家发这个 App，让每个人去处理这些 video，那 Human Evaluation 大约 10 到 20 分钟就能出结果。"

> "事实上我可以 propose 三个方案给你，然后你选一个。只要我知道这个 full dataset 是什么，我就不会 block 你。"
