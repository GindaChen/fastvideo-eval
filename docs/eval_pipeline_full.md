# World Model Evaluation Pipeline — Full Meeting Notes

**Date:** 2026-03-10  
**Project:** WanGame 1.3B — Minecraft World Model  
**WandB:** [wangame_1.3b](https://wandb.ai/kaiqin_kong_ucsd/wangame_1.3b/runs/fif3z1z4?nw=nwuserjunda)

---

## 1. Problem Statement

We train a world model that generates Minecraft gameplay videos conditioned on a starting frame and a sequence of player actions. Training produces many checkpoints and a large volume of generated videos. We need to determine:

1. **Which checkpoint is better** (relative comparison across checkpoints)
2. **Whether a given checkpoint meets release quality** (absolute threshold)

Currently, we lack a scalable, systematic evaluation pipeline. The process is heavily manual, relies on partial metrics, and does not cover all action types comprehensively.

---

## 2. Evaluation Dimensions

Evaluating this world model is significantly harder than general video generation (e.g., V6GEN) because it requires not just visual quality but also behavioral correctness.

### 2.1 Video Quality
- Must go beyond simple eyeballing
- Need to distinguish between **simple scenes** (flat terrain, clear sightlines) and **complex scenes** (obstacles, varied terrain, multiple entities)
- Different quality standards apply: flat-terrain movement should be near-perfect, while complex scenes allow some tolerance for minor artifacts

### 2.2 Consistency
- Test whether the model maintains visual coherence through complementary actions
- Example: turn left → return to center — does the scene look the same?
- This involves many sub-dimensions: left/right turns, up/down looks, forward/backward movement, and combinations thereof

### 2.3 Action Following (Hardest Dimension)
- The model must learn to follow **23 distinct actions**, constrained by the dataset
- These 23 actions cannot be reduced — the model must fit all of them
- Eyeballing all 23 action types is infeasible for human evaluation
- Must validate by **task groups**: movement only, mouse only, build only, attack/chase, etc.
- **Time estimate:** A focused, dedicated evaluation session takes ~1 day; a quick checkpoint evaluation run takes ~30 minutes

---

## 3. The 23 Minecraft Actions

| Category | Actions | Count |
|---|---|---|
| Movement | Forward (W), Back (S), Left (A), Right (D) | 4 |
| Mouse Look | Mouse Up, Mouse Down, Mouse Left, Mouse Right | 4 |
| Jump | Spacebar | 1 |
| Hotbar Selection | F1 through F8 (select inventory slots) | 8 |
| Sprint | Shift + Forward (combination key) | 1 |
| Decelerate | (Speed modifiers) | varies |
| Still | No action pressed | 1 |
| **Total** | | **~23** |

**Currently well-evaluated:** Forward, Back, Left, Right, Mouse (4 directions), Still = **9 actions**  
**Not yet systematically evaluated:** Remaining ~14 actions (hotbar, sprint, jump, decelerate, combinations)

---

## 4. Action Data Format

Each validation prompt consists of a **first frame** (a Minecraft screenshot) plus an **action sequence**:

- Raw storage format: **77 frames × 23-dimensional binary vector**
- Each dimension corresponds to one of the 23 possible actions (1 = pressed, 0 = not pressed)
- No explicit timestamps — the frame index IS the timestamp
- There is no text description of the scene; the model input is purely visual + action
- Example labels:
  - "W only" = W pressed for some frames, then released (W + Still)
  - Complex sequences receive shorthand labels: "WSD", "W + mouse left", etc.
- For visualization, active keys are overlaid on the rendered video at each frame

---

## 5. Training Experience & Model Behavior Expectations

One month of training has produced domain knowledge about what the model can and cannot do. This knowledge should be codified for evaluation design:

| Behavior | Expected Model Output |
|---|---|
| Hitting an obstacle | **Stops walking** — does NOT auto-jump over obstacles |
| Walking near a wall | Stops at a safe distance; no wall-clipping or collision artifacts |
| Collision training data | Filtered out — samples with high obstacle-flow were removed from training |
| Flat terrain movement | Should be near-perfect; no stuttering or direction errors |
| Complex terrain movement | Some tolerance for pausing, stopping, or minor hesitation is acceptable |

**Key insight:** When designing evaluation prompts, expectations must match these learned behaviors. For example, the model will never auto-jump, so test prompts should not assume it will. The model's "default obstacle behavior" is to stop.

**Idea for automation:** Distill this expert knowledge into written rules and feed them to a VLM agent. The agent could then auto-filter or auto-score generated videos. **Challenge:** The input is only a first frame + action list (no text description), so the VLM needs strong visual reasoning capability.

---

## 6. Current Training & Checkpoint Flow

1. Run training with a set of hyperparameters
2. **Every 500 steps** → run automated evaluation
3. Use **Optical Flow** as the primary automated metric to rank checkpoints
4. Maintain a rolling **Top-5 best checkpoints** based on this metric
5. **Every 5,000 steps** → always save a round-number checkpoint (regardless of score)
6. Training runs up to ~70K steps maximum

### 6.1 Optical Flow Metric — Deep Dive

The "optical flow" metric is actually an **LPIPS variant** that computes frame-to-frame visual differences between a ground truth video and a generated video.

**How it works:**
- For each frame pair (GT frame_t vs Generated frame_t), compute a perceptual similarity score
- Aggregate across all frames to get a video-level score
- Higher similarity to GT = better checkpoint

**Limitations (even with ground truth):**
- **Distance-dependent error:** Objects near the camera produce larger optical flow magnitudes than distant objects for the same action. This introduces systematic bias — the metric unfairly penalizes or rewards based on scene composition rather than action accuracy
- **Inaccurate for "Still" actions:** When no action is taken, the metric struggles to correctly evaluate
- **Inaccurate for wall collisions:** The stopping behavior doesn't produce the expected flow patterns
- **Scene-dependent:** The same action → different flow in different environments

**Without ground truth:**
- One can construct a *synthetic* expected optical flow from the action list alone
- However, this is unreliable because the expected flow depends on the specific scene geometry (which objects are where, how far they are, etc.)

**Bottom line:** Optical flow is currently the **only automatic metric for action following**, but it serves as a **reference signal to speed up human eyeballing**, not as a ground-truth quality score. It helps narrow down candidates, but cannot make final decisions.

### 6.2 Why Human Eyeballing Is Still Necessary

Because optical flow has known failure modes (still, collisions, distance), the project lead must manually review the Top-5 checkpoints selected by the metric, comparing them against the round-number checkpoints saved every 5K steps. This is the only way to catch metric errors.

---

## 7. Current Validation Setup

- **32 prompts** → each checkpoint generates 32 videos
- Compare across **5 candidate checkpoints** (the Top-5 from optical flow)
- For each of the 32 videos, determine which checkpoint produces the best output
- Aggregate to decide which checkpoint is overall best

### 7.1 Actual Eyeballing Method

The current method is **elimination-based**, not pairwise scoring:

- Watch the 32 videos generated by a checkpoint
- If a video shows a visible problem → **exclude that checkpoint** for that task
- The lead does NOT compare two checkpoints side-by-side and tally +1 / -1 scores
- Instead: find and eliminate clearly bad checkpoints, then pick from the remaining

### 7.2 Problems with Current Setup

1. **32 prompts were ad-hoc** — designed without systematic task coverage in mind
2. **No task tags or categories** on prompts (e.g., "this prompt evaluates walking", "this evaluates sprint")
3. **Unbalanced coverage:** Complex scenes are over-represented; simple scenes (which should be near-perfect) are under-represented
4. **Not comprehensive enough** — likely need **~120 prompts** to properly cover task × difficulty combinations
5. **Eyeballing doesn't scale:** Can realistically compare only ~3 videos per checkpoint pair during a review session, which is statistically insufficient
6. **Context switching is expensive:** Jumping between different action categories during review creates cognitive load and reduces accuracy

---

## 8. Validation Dataset Structure

### 8.1 Two Types of Validation Prompts

| Type | Has Ground Truth? | Source | Optical Flow Usable? |
|---|---|---|---|
| From training set (split) | ✅ Yes | Human Minecraft gameplay recordings | ✅ Reliable (comparative) |
| Custom-designed prompts | ❌ No | Hand-crafted first-frame + action list | ⚠️ Only synthetic flow (unreliable) |

### 8.2 Current Gap

- Validation currently uses **only custom prompts without ground truth** (novel images, not split from training set)
- This means optical flow is unreliable for all current validation prompts
- **Should split some GT data** from the training set into a validation partition

### 8.3 Constructing New Ground Truth Cases

To create validation prompts with ground truth:

| Step | What's Needed |
|---|---|
| 1. Pick a scene (first frame) | Already available from the dataset |
| 2. Define an action sequence | Can be hand-written (e.g., "forward 5 frames, back 5 frames") |
| 3. Record GT video | **Must run Minecraft simulator** — a human plays the exact action sequence and records the output |
| 4. Crop and package as dataset row | Straightforward post-processing |

- **Technical complexity:** Low (conceptually simple—just play Minecraft and record)
- **Practical overhead:** High (someone has to actually sit down and play)
- **Available resource:** The neighboring WorkLab has a Minecraft server
- **Owner:** The project lead prefers to delegate this; it doesn't require domain expertise, just time

The desire to test specific action sequences (e.g., "walk forward 5 steps then backward 5 steps") is a key reason for needing custom GT. Such exact sequences are difficult to find in the existing human-play dataset; finding them takes time, and they might not exist at all.

---

## 9. Proposed Evaluation Architecture

### 9.1 Task-Based Grouping

- Categorize all prompts by task (e.g., "basic forward/back", "mouse look", "sprint", "jump", "hotbar switching")
- Each group gets its own sub-score
- Find a checkpoint that performs well **across all task groups**, not just excels at one
- This replaces the current ad-hoc "look at everything at once" approach

### 9.2 Per-Task Scoring with Scene Difficulty

Within each task group, prompts should span difficulty levels:

- **Easy scene** (flat terrain, open area): Zero tolerance for errors. The model should be perfect here.
- **Complex scene** (obstacles, varied terrain, entities): Some tolerance for minor artifacts, pausing, or hesitation
- The scoring rubric must be adjusted per difficulty tier

### 9.3 Proposed "Tinder-Style" Evaluation App

To enable fast, scalable human evaluation, build a purpose-built app:

**UI Elements per evaluation card:**

| Element | Description |
|---|---|
| Initial image (first frame) | The starting Minecraft scene |
| Action list overlay | Keyboard actions overlaid on the video, showing active keys per frame |
| Generated video | Playable at 1x, 2x, or 3x speed |
| Rating options | Swipe or tap to rate quality (good / bad / skip) |
| Category-specific issues | Checklist of known issues relevant to this task category |
| Voice annotation (optional) | Describe what went wrong via voice input for detailed feedback |

**Action List Display:**
- Currently overlaid directly on the generated video
- 23 possible actions are too many to show simultaneously → overlay shows only active keys at each frame

**On-Demand Video Generation (stretch goal):**
- User defines an ad-hoc action sequence directly in the App
- App sends the first-frame + custom action list to a loaded checkpoint
- Checkpoint generates the video on the fly for immediate evaluation
- This enables testing edge cases without pre-generating the full prompt set

### 9.4 Team-Scale Human Evaluation

With the right tooling, evaluation can be parallelized across team members:

- **Benchmark:** 1 person can process ~30 videos in 5 minutes
- **With 5 evaluators** running the App in parallel → full human eval in **10–20 minutes** post-training
- Google reportedly achieves human evaluation results within 30 minutes of training completion — this approach matches that throughput
- **Key enabler:** Distribute the App to the team after each training run; everyone evaluates their assigned video slice concurrently

### 9.5 Key Design Principle

> **Do NOT directly compare two checkpoints.** Instead, evaluate each video independently on its own merits. Aggregate per-video scores to determine overall checkpoint quality.

Pairwise comparison introduces bias and doesn't scale. Per-video absolute scoring allows independent evaluation and principled aggregation.

---

## 10. Comparison Math

> "Can you help me calculate how many comparisons I actually need to look at?"

**Current scale:**
- 5 checkpoints × 32 videos = **160 videos** per evaluation round

**Target scale (with expanded prompts):**
- 5 checkpoints × ~120 prompts = **~600 videos** per evaluation round
- With 5 evaluators: ~120 videos per person ≈ 20 minutes each

**Open question:** Need a principled aggregation method. Simply counting "who wins the most videos" is insufficient — need per-task aggregation, potentially weighted by task importance.

---

## 11. Infrastructure & Data Pipeline

**WandB Project:** [wangame_1.3b](https://wandb.ai/kaiqin_kong_ucsd/wangame_1.3b/runs/fif3z1z4?nw=nwuserjunda)

| Component | Location | Notes |
|---|---|---|
| Training compute | M2 cluster | Videos generated here during training |
| Video storage | **WandB** | Validation videos uploaded with prompt metadata |
| Checkpoints | Local / M2 | NOT stored in WandB — loaded from filesystem paths |
| Prompt metadata | WandB | Each video is tagged with its generating prompt |

### Pipeline Gaps

1. Videos generated on M2 need to be **streamed to WandB** (or another endpoint) for the eval App to access
2. WandB already stores prompt labels → just need to **wrap with task/category tags** to enable grouped evaluation
3. Post-training video generation pipeline (checkpoint → prompt set → batch video generation) needs to be automated end-to-end

### Desired Pipeline

```
Training completes
    → Top-5 checkpoints identified (optical flow)
    → Each checkpoint generates videos for all ~120 prompts
    → Videos uploaded to WandB with task tags
    → Eval App pulls videos, distributes to 5 evaluators
    → Scores aggregated per-task per-checkpoint
    → Results dashboard available in <30 minutes
```

---

## 12. V6GEN vs World Model Evaluation

| Aspect | V6GEN (Video Generation) | World Model (This Project) |
|---|---|---|
| What matters | "Does it look good?" | Consistency + Action Following + Visual Quality |
| Evaluation method | Eyeballing is often sufficient | Requires structured task-based scoring + automated metrics |
| Difficulty | Lower — visual quality is assessable at a glance | Higher — must verify behavioral correctness across 23 actions |
| Literature | Could do a literary survey and reproduce others' published evaluation scores | Dedicated to another team member, but the project lead has the deepest context |

---

## 13. Bottleneck Analysis: Who Owns What

| Bottleneck | Owner | Notes |
|---|---|---|
| **Redesign validation prompts** | Project lead | Must decide which prompts to add/remove for task coverage |
| **Task categorization of existing prompts** | Anyone with context / agent | Given the dataset, someone else can propose 3 options; lead picks one |
| **Build eval App** | Engineer / agent | Implementation task; not blocked on domain expertise |
| **Define scoring rubric** | Project lead | Requires deep understanding of action semantics and model capabilities |
| **Record GT videos in Minecraft** | Delegatable | Low skill requirement, high time overhead — anyone with Minecraft access can do it |
| **Distill expert knowledge into rules** | Project lead | Needed for potential VLM-based auto-evaluation |

> **Key unblock:** If the full dataset (all prompts + actions) is shared, the task categorization and prompt expansion can be parallelized. The project lead only needs to review and select from proposals — not do the categorization work directly.

---

## 14. Two Immediate Next Steps

1. **Automate the video extraction pipeline** — Build simple infra to extract and pair videos from the 1B-sample dataset so that humans can efficiently verify and annotate them. Convert raw data into evaluation-ready pairs.

2. **Build a comprehensive eval App from the start** — Rather than iterating on a minimal version, invest in building something comprehensive that serves as the long-term reference tool. This includes the Tinder-style UI, task-based grouping, team-parallel evaluation, and ideally on-demand video generation.

---

## 15. Action Items

### Immediate (Unblock evaluation)
- [ ] **Share full dataset** (prompts + action labels) so others can help with categorization
- [ ] **Categorize the 32 existing prompts** by task type — can be proposed by agent/teammate, reviewed by lead
- [ ] **Redesign validation prompts** — add/remove to achieve balanced task × difficulty coverage
- [ ] **Expand prompt set** from 32 → ~120 prompts
- [ ] **Split some GT data from training set** into a validation partition (currently all validation is non-GT)

### Ground Truth Construction
- [ ] **Record GT videos** using Minecraft simulator (WorkLab server available)
- [ ] **Define target action sequences** for GT recording (e.g., "forward 5 steps, back 5 steps")
- [ ] **Delegate recording task** — low skill, high overhead; project lead doesn't want to do it personally

### Pipeline Automation
- [ ] **Automate post-training video generation** (checkpoint + prompt set → video batch)
- [ ] **Add task/category tags** to WandB prompt metadata
- [ ] **Stream M2 videos** to an accessible endpoint for the eval App

### Evaluation App
- [ ] **Build Tinder-style evaluation UI** — show first frame, action overlay, video, rating controls, voice annotation
- [ ] **Support team-parallel evaluation** (5 people × 5 min = full eval under 20 min)
- [ ] **Add category-specific issue checklists** per task type
- [ ] **On-demand video generation** — define ad-hoc action sequence → generate → evaluate
- [ ] **Calculate required evaluation volume** for statistical significance

### Data Pipeline (1B Dataset)
- [ ] **Automate video pair extraction** from the 1B dataset into evaluation-ready format
- [ ] **Build a pair viewer** for efficient human verification

### Scoring & Rubric
- [ ] **Design task grouping** for the 23 actions (e.g., movement, mouse, hotbar, sprint, combat)
- [ ] **Define per-task scoring rubric** with difficulty-adjusted tolerance levels
- [ ] **Balance simple vs complex scenes** in the prompt set
- [ ] **Distill expert knowledge** into written evaluation rules for potential VLM-based auto-evaluation

---

## 16. Key Quotes

> "如果让我专注处理，一天也能搞完。但如果只是运行 evaluate checkpoint 这件事，大概半小时就能扫完并做决定。"

> "你不能直接比较两个 checkpoint，而只能通过每一个 video 去评价这个 video 本身如何。"

> "我的目标是：假设我不能 100% evaluate 完整个 landscape，但我可以通过 40% 的 human effort 大概了解这些 checkpoint 的优劣。"

> "如果你每次 training 结束之后给大家发这个 App，让每个人去处理这些 video，那 Human Evaluation 大约 10 到 20 分钟就能出结果。"

> "事实上我可以 propose 三个方案给你，然后你选一个。只要我知道这个 full dataset 是什么，我就不会 block 你。"
