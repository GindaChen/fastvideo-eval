
// --------------------------------------------------------------------------
// Review bad videos — assign reasons
// --------------------------------------------------------------------------
const ISSUE_TAGS = [
    { key: 'wrong_direction', label: '1 Wrong direction' },
    { key: 'no_movement', label: '2 No movement' },
    { key: 'jittery', label: '3 Jittery / unstable' },
    { key: 'visual_artifacts', label: '4 Visual artifacts' },
    { key: 'wrong_action', label: '5 Wrong action' },
    { key: 'partial_action', label: '6 Incomplete action' },
    { key: 'camera_wrong', label: '7 Camera issue' },
    { key: 'low_quality', label: '8 Low quality' },
    { key: 'other', label: '9 Other' },
];

let _reviewRatings = [];
let _reviewFilter = 'bad'; // default filter

async function loadReview() {
    const container = document.getElementById('review-content');
    const subtitle = document.getElementById('review-subtitle');
    container.innerHTML = '<div class="empty-state">Loading ratings...</div>';

    try {
        const ratings = await api('/api/ratings/bad');
        _reviewRatings = ratings;

        // Count by type
        const counts = { all: ratings.length, bad: 0, good: 0, skip: 0 };
        ratings.forEach(r => { if (counts[r.rating]) counts[r.rating]++; else counts.bad++; });
        // Since this endpoint returns bad only, all are bad
        counts.bad = ratings.length;

        subtitle.textContent = `${ratings.length} rated videos`;

        // Filter tabs
        const tabCont = document.getElementById('review-filter-tabs');
        tabCont.innerHTML = ['all', 'bad'].map(f => {
            const active = f === _reviewFilter ? 'active' : '';
            const label = f === 'all' ? `All (${counts.all})` : `Bad (${counts.bad})`;
            return `<button class="btn btn-sm ${active}" onclick="setReviewFilter('${f}')">${label}</button>`;
        }).join('');

        // Show/hide tagging button
        const untagged = ratings.filter(r => !r.issues || r.issues.length === 0);
        document.getElementById('btn-start-tagging').textContent = `🏷️ Tag Bad Videos (${untagged.length} untagged)`;

        renderReviewGrid(ratings);
    } catch (err) {
        container.innerHTML = `<div class="empty-state">Error: ${err.message}</div>`;
    }
}

function setReviewFilter(f) {
    _reviewFilter = f;
    loadReview();
}

function renderReviewGrid(ratings) {
    const container = document.getElementById('review-content');
    if (ratings.length === 0) {
        container.innerHTML = '<div class="empty-state">No rated videos yet.</div>';
        return;
    }

    container.innerHTML = ratings.map((r, idx) => {
        const ckpt = r.checkpoint_id || '';
        const stepMatch = ckpt.match(/step(\d+)/);
        const step = stepMatch ? stepMatch[1] : '0';
        const idxMatch = (r.prompt_id || '').match(/(?:val|doom)_(\d+)/);
        const vidIdx = idxMatch ? parseInt(idxMatch[1]) : 0;
        const issues = r.issues || [];
        const hasIssues = issues.length > 0;
        const promptLabel = r.prompt_id || r.video_id;

        const tagBadges = issues.map(key => {
            const tag = ISSUE_TAGS.find(t => t.key === key);
            return `<span class="issue-badge">${tag ? tag.label : key}</span>`;
        }).join('');

        return `
            <div class="review-card ${hasIssues ? 'reviewed' : 'needs-review'}">
                <div class="review-header">
                    <span class="review-label">${hasIssues ? '✅' : '⚠️'} ${promptLabel}</span>
                    <span class="review-step">Step ${step}</span>
                </div>
                <div class="review-body">
                    <video class="review-video" playsinline muted loop preload="none"
                           src="/api/video-proxy/${state.runId}/${step}/${vidIdx}"
                           onclick="this.paused?this.play():this.pause()"></video>
                    <div class="review-tags-summary">${tagBadges || '<span class="text-muted">No reasons tagged</span>'}</div>
                </div>
            </div>`;
    }).join('');
}

// --------------------------------------------------------------------------
// Reason Tagger (card-based, like Evaluate)
// --------------------------------------------------------------------------
const taggerState = {
    ratings: [],      // bad ratings to tag
    currentIdx: 0,
    selectedReasons: new Set(),
};

function startReasonTagger() {
    const untagged = _reviewRatings.filter(r => !r.issues || r.issues.length === 0);
    if (untagged.length === 0) {
        toast('All bad videos already tagged!', 'info');
        return;
    }
    taggerState.ratings = untagged;
    taggerState.currentIdx = 0;

    document.getElementById('review-overview').classList.add('hidden');
    document.getElementById('review-tagger').classList.remove('hidden');

    renderTaggerCard();
}

function exitReasonTagger() {
    document.getElementById('review-tagger').classList.add('hidden');
    document.getElementById('review-overview').classList.remove('hidden');
    loadReview(); // refresh overview
}

function renderTaggerCard() {
    const r = taggerState.ratings[taggerState.currentIdx];
    if (!r) {
        toast('All done tagging!', 'success');
        exitReasonTagger();
        return;
    }

    taggerState.selectedReasons = new Set(r.issues || []);

    // Label
    document.getElementById('tagger-label').textContent =
        `Video ${taggerState.currentIdx + 1}/${taggerState.ratings.length}`;

    // Dots
    const dotsEl = document.getElementById('tagger-dots');
    if (taggerState.ratings.length <= 50) {
        dotsEl.innerHTML = taggerState.ratings.map((_, i) => {
            let cls = 'eval-dot';
            if (i === taggerState.currentIdx) cls += ' active';
            else if (_.issues && _.issues.length > 0) cls += ' committed';
            return `<div class="${cls}"></div>`;
        }).join('');
    }

    // Video
    const ckpt = r.checkpoint_id || '';
    const stepMatch = ckpt.match(/step(\d+)/);
    const step = stepMatch ? stepMatch[1] : '0';
    const idxMatch = (r.prompt_id || '').match(/(?:val|doom)_(\d+)/);
    const vidIdx = idxMatch ? parseInt(idxMatch[1]) : 0;
    const videoEl = document.getElementById('tagger-video');
    videoEl.src = `/api/video-proxy/${state.runId}/${step}/${vidIdx}`;
    videoEl.load();
    videoEl.oncanplay = () => { videoEl.playbackRate = state.playbackSpeed; };
    videoEl.play().catch(() => { });

    // Meta
    document.getElementById('tagger-caption').textContent = r.prompt_id || r.video_id;
    document.getElementById('tagger-step').textContent = `Step ${step}`;

    // Reason buttons (numbered 1-9)
    const reasonsEl = document.getElementById('tagger-reasons');
    reasonsEl.innerHTML = ISSUE_TAGS.map((t, i) => {
        const num = i + 1;
        const active = taggerState.selectedReasons.has(t.key) ? 'active' : '';
        return `<button class="tagger-reason-btn ${active}" data-key="${t.key}"
                    onclick="toggleTaggerReason('${t.key}', this)">${t.label}</button>`;
    }).join('');

    // Clear freetext
    document.getElementById('tagger-freetext').value = r.free_text || '';
}

function toggleTaggerReason(key, btn) {
    if (taggerState.selectedReasons.has(key)) {
        taggerState.selectedReasons.delete(key);
        if (btn) btn.classList.remove('active');
    } else {
        taggerState.selectedReasons.add(key);
        if (btn) btn.classList.add('active');
    }
}

async function taggerSave() {
    const r = taggerState.ratings[taggerState.currentIdx];
    if (!r) return;

    const issues = [...taggerState.selectedReasons];
    const freeText = document.getElementById('tagger-freetext').value.trim();
    if (freeText && !issues.includes('other')) issues.push('other');

    try {
        await api(`/api/ratings/${r.rating_id}/issues`, {
            method: 'PATCH',
            body: JSON.stringify({ issues, free_text: freeText || null }),
        });
        r.issues = issues;
        r.free_text = freeText;
        toast('Saved!', 'success');
        taggerState.currentIdx++;
        renderTaggerCard();
    } catch (err) {
        toast(`Error: ${err.message}`, 'error');
    }
}

function taggerSkip() {
    taggerState.currentIdx++;
    renderTaggerCard();
}

function taggerPrev() {
    if (taggerState.currentIdx > 0) {
        taggerState.currentIdx--;
        renderTaggerCard();
    }
}

function taggerNext() {
    if (taggerState.currentIdx < taggerState.ratings.length - 1) {
        taggerState.currentIdx++;
        renderTaggerCard();
    }
}

function handleTaggerKey(e) {
    // Number keys 1-9 toggle reasons
    const num = parseInt(e.key);
    if (num >= 1 && num <= ISSUE_TAGS.length) {
        e.preventDefault();
        const tag = ISSUE_TAGS[num - 1];
        const btn = document.querySelector(`.tagger-reason-btn[data-key="${tag.key}"]`);
        toggleTaggerReason(tag.key, btn);
        return;
    }

    switch (e.key) {
        case 'Enter':
        case ' ':
            e.preventDefault();
            taggerSave();
            break;
        case 'k': case 'K':
            taggerSkip();
            break;
        case 'ArrowLeft':
            e.preventDefault();
            taggerPrev();
            break;
        case 'ArrowRight':
            e.preventDefault();
            taggerNext();
            break;
        case 'Escape':
            exitReasonTagger();
            break;
        case 'r': case 'R': {
            const vid = document.getElementById('tagger-video');
            if (vid) { vid.currentTime = 0; vid.play(); }
            break;
        }
    }
}
