<!-- SECTION: Overview -->
<!-- SLIDE -->
# WandB Integration — Live Test Report
## `kaiqin_kong_ucsd/wangame_1.3b`

**Date:** 2026-03-10 &nbsp;|&nbsp; **All 7 tests passed** ✅

> This report documents live integration tests of the `app/wandb_client` package against the real WandB project. All API calls hit production WandB — no mocks.

<!-- SECTION: Test Results -->
<!-- SLIDE -->
## Test Results Summary

| # | Test | Status | Time |
|---|------|--------|------|
| 1 | API Initialization | ✅ Pass | — |
| 2 | List Runs | ✅ Pass | ~2s |
| 3 | Fetch Run Details | ✅ Pass | 303ms |
| 4 | Scan History | ✅ Pass | 17.9s |
| 5 | Fetch Media at Step | ✅ Pass | — |
| 6 | List Run Files | ✅ Pass | 7.8s |
| 7 | List Artifacts | ✅ Pass | 459ms |

All 7/7 passed, 0 failed.

<!-- SLIDE -->
## T1: API Initialization

**Status:** ✅ Pass

- Default entity resolved: `jundachen`
- API key read from `~/.netrc` (WandB's default auth)
- The `wandb.Api()` client initializes without requiring `$WANDB_API_KEY` env var — it falls back to netrc

> **Finding:** Our `WandBConfig` needs a fallback path for netrc-based auth, not just `$WANDB_API_KEY`.

<!-- SLIDE -->
## T2: List Runs

**Status:** ✅ Pass

Found **10 runs** in project:

| # | Name | State | Created |
|---|------|-------|---------|
| 1 | `MC_clean_action_bs256` | crashed | 2026-02-05 |
| 2 | `mc_4action_bs128` | crashed | 2026-02-05 |
| 3 | `test MC prompt` | finished | 2026-02-06 |
| 4 | `MC_Still_W_only_bs64_empty_prompt` | crashed | 2026-02-06 |
| 5 | `MC_Still_W_only_bs32_with_warmup` | crashed | 2026-02-06 |
| 6 | `MC_WASD_bs32` | crashed | 2026-02-06 |
| 7 | `MC_WASD_bs32_lr_1e-5` | finished | 2026-02-07 |
| 8 | `MC_wsad_random_lr_1e-5` | crashed | 2026-02-08 |
| 9 | `MC_camera_left/right_lr_1e-5` | crashed | 2026-02-08 |
| 10 | `MC_random_lr_1e-5 (wrong data path)` | crashed | 2026-02-08 |

> Most runs are early experiments.  2 `finished`, 8 `crashed`.

<!-- SLIDE -->
## T3: Fetch Run Details

**Run:** `MC_clean_action_bs256` (hp0jdi7n) — **303ms**

### Summary Keys (23 total)

Training metrics: `train_loss`, `grad_norm`, `learning_rate`, `step_time`, `avg_step_time`

Timing keys: `timing/forward_backward`, `timing/optimizer_step`, `timing/clip_grad_norm`, `timing/normalize_input`, `timing/reduce_loss`, `timing/prepare_dit_inputs`

Model config: `hidden_dim`, `ffn_dim`, `num_layers`, `batch_size`, `context_len`, `dit_seq_len`

### Config Keys (15+)

`mode`, `seed`, `betas`, `sp_size`, `tp_size`, `use_ema`, `STA_mode`, `lr_power`, `num_gpus`, `revision`, `scale_lr`, `trackers`, `data_path`, `ema_decay`, `logit_std`

<!-- SLIDE -->
## T4: Scan History

**4,700 rows scanned** in **17.9 seconds**

### All History Keys

```
_runtime, _step, _timestamp,
avg_step_time, batch_size, context_len, dit_seq_len,
ffn_dim, grad_norm, hidden_dim, learning_rate,
num_layers, step_time,
timing/clip_grad_norm, timing/forward_backward,
timing/normalize_input, timing/optimizer_step,
timing/prepare_dit_inputs, timing/reduce_loss,
train_loss, validation_videos_40_steps, vsa_sparsity
```

### 🔑 Key Finding: Video Key

The validation video key is **`validation_videos_40_steps`** — videos are logged **every 40 steps**, not every 500.

> **Action Required:** Update our `list_checkpoints()` to detect the actual validation frequency from the history keys, not hardcode 500.

<!-- SLIDE -->
## T5: Fetch Media at Step

Examined the history row format for `validation_videos_40_steps`:

Videos are logged as **WandB media objects** embedded in history rows. The `_type` field in each dict reveals the media format:

```json
{
  "_type": "video-file",
  "path": "media/videos/validation_videos_40_steps_0_<hash>.mp4"
}
```

> **Finding:** Videos use the WandB `video-file` type, matching our `_extract_video_url()` handler.

<!-- SLIDE -->
## T6: List Run Files

**1,696 total files** — **1,692 video files** 🎬

All video files follow the pattern:
```
media/videos/validation_videos_40_steps_0_<sha>.mp4
```

File naming convention:
- `validation_videos_40_steps` — the log key
- `_0_` — likely the index within a logged batch
- `<sha>` — content hash

> **Finding:** Each run can have 1,000+ video files. Our cache system needs to handle this scale efficiently. At ~1.5MB per video, that's ~2.5GB per run.

<!-- SLIDE -->
## T7: List Artifacts

Only **1 artifact** found: `run-hp0jdi7n-history:v0` (type: `wandb-history`)

- No video artifacts logged — videos are stored as **run files**, not artifacts
- This means we fetch videos via `run.files()` or resolve URLs from history rows, not via the Artifacts API

> **Finding:** Our video fetching path should use `run.file(path).download()` to get direct download URLs.

<!-- SECTION: Normalization Tests -->
<!-- SLIDE -->
## Prompt ID Normalization

All 4 test cases passed ✅

| Input | Expected | Got | → |
|-------|----------|-----|---|
| `val/basic_fwd_flat_01` | `basic_fwd_flat_01` | `basic_fwd_flat_01` | ✅ |
| `validation/W_only_easy` | `w_only_easy` | `w_only_easy` | ✅ |
| `videos/test.mp4` | `test` | `test` | ✅ |
| `Basic Fwd Flat 01` | `basic_fwd_flat_01` | `basic_fwd_flat_01` | ✅ |

<!-- SECTION: Action Items -->
<!-- SLIDE -->
## Findings & Action Items

### Must Fix

1. **Validation frequency** — Not every 500 steps. Actual key is `validation_videos_40_steps`. Our `list_checkpoints()` should detect this from history keys dynamically.
2. **Auth fallback** — `WandBConfig` should support `~/.netrc` auth in addition to `$WANDB_API_KEY`.
3. **Video URL resolution** — Videos are run files. Use `run.file(path).url` for direct download links.

### Observations

4. **Scale** — 1,692 videos in one run. Cache system should support incremental downloads.
5. **Run naming** — Run names encode experiment info (`MC_WASD_bs32_lr_1e-5`). Consider auto-parsing action groups and learning rates.
6. **Most runs crashed** — 8/10. Only `finished` runs should be candidates for full evaluation.

<!-- SLIDE -->
## Architecture Validation

```
SPEC §8.1 ───── Required Operations ─────── Status
  1. List Runs                                ✅ Works
  2. Fetch Validation Videos                  ⚠️ Key name differs
  3. Fetch Prompt Metadata                    🔲 Needs schema mapping
  4. Fetch Optical Flow Scores                🔲 Key not yet identified
```

```
SPEC §8.2 ───── Data Normalization ──────── Status
  Video URLs → direct download               ⚠️ Need run.file().url
  Prompt labels → prompt_id                   ✅ Normalization works
  Training steps → integers                   ✅ Works
  Optical flow → float | null                 🔲 Key not yet identified
```

The integration layer foundation is solid. Next step: adapt to the actual WandB schema discovered in these tests.
