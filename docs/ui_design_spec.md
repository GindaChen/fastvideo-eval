# Evaluation App — UI Design Spec

**Purpose:** This document describes the UI for the WanGame Eval App so it can be handed to a designer or another AI tool to generate the actual interface.

---

## Overview

A focused video evaluation app. One video at a time, rate it, move on. Like Tinder for model evaluation. Designed for speed — an evaluator should process ~20 videos in 5 minutes.

**Platform:** Web app (mobile-friendly)
**Theme:** Dark mode, minimal, fast-loading

---

## Screen 1: Dashboard / Home

**Layout:** Single column, centered

**Elements:**
- Header: "WanGame Eval" + WandB project link
- **Progress bar:** X of Y videos evaluated (segmented by chunk)
- **Chunk selector:** Grid or list of chunks (~20 videos each), showing:
  - Chunk ID
  - Status badge: ✅ Done / 🟡 In Progress / ⬜ Not Started
  - Video count
- **"Start Evaluating" button** → opens next unfinished chunk
- **Stats summary:** Total rated, total remaining, time estimate

---

## Screen 2: Evaluation Card (Core UX)

This is where the evaluator spends 95% of their time.

**Layout:** Full-screen card, vertically stacked

**Top bar:**
- Chunk progress: "Video 3 of 20"
- Mini progress dots (like a carousel indicator)
- Exit / pause button (top-right)

**Video area (60% of screen):**
- Pre-rendered video from WandB (action overlay already baked in)
- Playback controls: play/pause, 1x / 2x / 3x speed toggle
- Video auto-plays on card entry
- Scrub bar at bottom of video

**Info area (below video):**
- Prompt text or label (if available)
- Checkpoint ID
- Action summary (e.g., "W only", "WSD + mouse left")

**Rating area (bottom, fixed):**
- Three large buttons, swipeable:
  - ❌ **Bad** (red, left swipe)
  - ⏭ **Skip** (gray, swipe up)
  - ✅ **Good** (green, right swipe)
- Tapping "Bad" expands → **Issue checklist** (see below)
- Optional: voice annotation button (🎤) for free-form notes

**Animation:** Card swipes out on rating, next card slides in

---

## Screen 2a: Issue Checklist (Expanded on "Bad")

When the evaluator taps ❌ Bad, a bottom sheet expands with common issues:

**Checkboxes (multi-select):**
- [ ] Wrong direction
- [ ] Model didn't move
- [ ] Inconsistent scene (turn + return doesn't match)
- [ ] Visual artifacts / glitching
- [ ] Incorrect speed (too fast / too slow)
- [ ] Unexpected stop
- [ ] Other (free text field)

**Bottom:** "Submit" button → records rating + issues, moves to next video

---

## Screen 3: Chunk Results Summary

Shown after completing a chunk of 20 videos.

**Layout:** Centered card

**Elements:**
- "Chunk #X Complete" header
- Stats: ✅ Good: N, ❌ Bad: N, ⏭ Skipped: N
- Pie chart or bar visualization
- **Most common issues** (aggregated from issue checklists)
- Buttons:
  - "Next Chunk →"
  - "Back to Dashboard"

---

## Screen 4: Results / Inspection View

For reviewing submitted results (SP2 integration).

**Layout:** Table or grid view

**Filters (top bar):**
- Checkpoint selector (dropdown)
- Task category filter (if categorized)
- Rating filter: All / Good / Bad / Skipped
- Evaluator filter (if multi-person)

**Table columns:**
- Video thumbnail (first frame)
- Prompt / action label
- Checkpoint ID
- Rating (✅ / ❌ / ⏭)
- Issues (if bad)
- Evaluator
- Timestamp

**Click row → expands:** Full video playback + all annotation details

---

## Visual Design Notes

**Color palette (dark mode):**
- Background: `#0a0a0f`
- Card surface: `#1a1a2e`
- Accent green (good): `#10B981`
- Accent red (bad): `#EF4444`
- Accent gray (skip): `#6B7280`
- Text primary: `#F9FAFB`
- Text muted: `#9CA3AF`

**Typography:**
- Headings: Inter or SF Pro, bold
- Body: Inter, regular
- Monospace (labels): JetBrains Mono

**Interactions:**
- Swipe gestures on mobile (left = bad, right = good, up = skip)
- Keyboard shortcuts on desktop: ←/A = bad, →/D = good, ↑/W = skip, Space = play/pause
- Haptic feedback on mobile when rating
- Card transition animation: 200ms ease-out slide

**Responsive:**
- Mobile-first (likely used on phone during eval sessions)
- Desktop: video larger, side panel for info instead of stacked

---

## Data Model (for backend reference)

```
Chunk {
  id: string
  checkpoint_id: string
  video_ids: string[]          // ~20 video IDs from WandB
  status: "not_started" | "in_progress" | "done"
  assigned_to: string | null   // optional
}

Rating {                       // append-only
  id: string
  video_id: string
  chunk_id: string
  checkpoint_id: string
  rating: "good" | "bad" | "skip"
  issues: string[]             // from checklist
  voice_note_url: string | null
  evaluator: string
  timestamp: ISO8601
}
```

---

## Prompt for Design Tools

> Design a dark-mode mobile-first web app for video evaluation. The core screen shows one video at a time (auto-playing, pre-rendered with keyboard action overlay). Below the video: action label and checkpoint ID. At the bottom: three large rating buttons — red ❌ Bad (left), gray ⏭ Skip (center), green ✅ Good (right). Swiping works too. When "Bad" is tapped, a bottom sheet slides up with an issue checklist. After rating, the card animates out and the next video slides in. There's a progress bar showing "Video 3 of 20" at the top with dot indicators. The dashboard shows chunks of ~20 videos each with completion status. Use colors: background #0a0a0f, cards #1a1a2e, green #10B981, red #EF4444. Font: Inter. Make it feel fast and minimal — an evaluator should process 20 videos in 5 minutes.
