/* ================================================================
   WanGame Eval — Application Logic
   Matrix-based chunk evaluation with progressive video proxy
   ================================================================ */

const API = window.location.origin;

// --------------------------------------------------------------------------
// State
// --------------------------------------------------------------------------
const state = {
    currentPage: 'dashboard',
    evaluator: localStorage.getItem('evaluator') || 'evaluator',
    playbackSpeed: parseFloat(localStorage.getItem('playbackSpeed')) || 2,
    settings: null,
    runId: '',
    // Matrix
    matrix: null,  // { steps, num_prompts, total_videos, ... }
    // Chunk evaluation
    sequence: [],     // [{step, promptIdx}, ...] — the full ordered list
    chunkSize: parseInt(localStorage.getItem('chunkSize')) || 50,
    prefetchCount: parseInt(localStorage.getItem('prefetchCount')) || 4,
    sortOrder: localStorage.getItem('sortOrder') || 'step_first', // or 'prompt_first'
    cursor: 0,        // position in sequence
    currentVideos: [], // loaded video metadata for current chunk
    currentVideoIdx: 0,
};

// --------------------------------------------------------------------------
// Router
// --------------------------------------------------------------------------
const router = {
    navigate(page) {
        document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
        document.querySelectorAll('.sidebar-link').forEach(l => l.classList.remove('active'));
        const el = document.getElementById(`page-${page}`);
        if (el) {
            el.classList.add('active');
            state.currentPage = page;
            const link = document.querySelector(`[data-page="${page}"]`);
            if (link) link.classList.add('active');
            if (page === 'dashboard') loadDashboard();
            if (page === 'settings') loadSettings();
            if (page === 'results') loadResults();
            if (page === 'evaluate') initEvaluate();
            if (page === 'review') loadReview();
            if (page === 'matrix') loadMatrix();
        }
    }
};


// --------------------------------------------------------------------------
// API helpers
// --------------------------------------------------------------------------
async function api(path, opts = {}) {
    const res = await fetch(`${API}${path}`, { headers: { 'Content-Type': 'application/json' }, ...opts });
    if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
    return res.json();
}

function toast(msg, type = 'info') {
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.textContent = msg;
    document.getElementById('toast-container').appendChild(el);
    setTimeout(() => el.remove(), 3000);
}

function toggleSidebar() {
    document.getElementById('sidebar').classList.toggle('open');
    document.getElementById('sidebar-backdrop').classList.toggle('show');
}

// Close sidebar when navigating
document.querySelectorAll('.sidebar-link').forEach(link => {
    link.addEventListener('click', e => {
        e.preventDefault();
        const page = link.dataset.page;
        if (page) router.navigate(page);
        // Close the drawer after navigating
        document.getElementById('sidebar').classList.remove('open');
        document.getElementById('sidebar-backdrop').classList.remove('show');
    });
});
async function loadDashboard() {
    // Use localStorage settings first
    const local = getLocalSettings();
    state.settings = local;
    state.runId = local.default_run_id;
    document.getElementById('dash-project-info').textContent =
        `${local.wandb_entity}/${local.wandb_project} • Run: ${local.default_run_id || '(not set)'}`;

    let totalVideos = 0;
    let committed = 0, skipped = 0;

    // Fetch real total from matrix dimensions
    if (state.runId) {
        try {
            const m = await api(`/api/matrix/${state.runId}`);
            totalVideos = m.total_videos || 0;
        } catch { }
    }

    // Fetch rating counts from DB
    try {
        const dash = await api('/api/dashboard');
        committed = dash.videos_committed || 0;
        skipped = dash.videos_skipped || 0;
        if (!totalVideos) totalVideos = dash.total_videos || 0;
    } catch { }

    const unrated = Math.max(0, totalVideos - committed - skipped);
    document.getElementById('stat-committed').textContent = committed;
    document.getElementById('stat-skipped').textContent = skipped;
    document.getElementById('stat-unrated').textContent = unrated;
    document.getElementById('stat-total').textContent = totalVideos.toLocaleString();
    const t = totalVideos || 1;
    document.getElementById('bar-committed').style.width = `${(committed / t * 100)}%`;
    document.getElementById('bar-skipped').style.width = `${(skipped / t * 100)}%`;
    document.getElementById('bar-unrated').style.width = `${(unrated / t * 100)}%`;
}

// --------------------------------------------------------------------------
// Evaluate — Matrix overview + chunk sequencing
// --------------------------------------------------------------------------
async function initEvaluate() {
    // If we're mid-evaluation, show current card
    if (state.currentVideos.length > 0 && state.currentVideoIdx < state.currentVideos.length) {
        showEvalUI();
        renderEvalCard();
        return;
    }

    if (!state.runId) {
        const local = getLocalSettings();
        state.runId = local.default_run_id;
        state.settings = local;
    }

    if (!state.runId) {
        showEvalSetup('<p>No run configured. Go to <strong>Settings</strong> first.</p><button class="btn btn-primary" onclick="router.navigate(\'settings\')">Settings</button>');
        return;
    }

    // Fetch matrix dimensions (fast — from run.config)
    showEvalSetup('<div class="eval-empty-msg">Loading matrix...</div><div class="eval-spinner"></div>');

    try {
        const m = await api(`/api/matrix/${state.runId}`);
        state.matrix = m;
        showMatrixOverview(m);
    } catch (err) {
        showEvalSetup(`<p class="eval-empty-msg">Failed: ${err.message}</p><button class="btn btn-primary" onclick="router.navigate('settings')">Settings</button>`);
    }
}

function showMatrixOverview(m) {
    const sortChecked = state.sortOrder === 'prompt_first' ? 'checked' : '';
    showEvalSetup(`
        <div class="matrix-overview">
            <h2>🎮 ${m.run_name}</h2>
            <p class="subtitle">Run: ${m.run_id} • ${m.run_state}</p>

            <div class="matrix-stats">
                <div class="matrix-stat">
                    <div class="matrix-stat-value">${m.steps.length}</div>
                    <div class="matrix-stat-label">Steps</div>
                </div>
                <div class="matrix-stat">
                    <div class="matrix-stat-value">×</div>
                    <div class="matrix-stat-label">&nbsp;</div>
                </div>
                <div class="matrix-stat">
                    <div class="matrix-stat-value">${m.num_prompts}</div>
                    <div class="matrix-stat-label">Prompts</div>
                </div>
                <div class="matrix-stat">
                    <div class="matrix-stat-value">=</div>
                    <div class="matrix-stat-label">&nbsp;</div>
                </div>
                <div class="matrix-stat accent">
                    <div class="matrix-stat-value">${m.total_videos.toLocaleString()}</div>
                    <div class="matrix-stat-label">Videos</div>
                </div>
            </div>

            <div class="matrix-info">
                Steps: ${m.steps[0]} → ${m.steps[m.steps.length - 1]} (every ${m.validation_interval})
            </div>

            <div class="chunk-config">
                <h3>Chunk Settings</h3>

                <div class="config-row">
                    <label>Sort order</label>
                    <div class="toggle-group">
                        <button class="toggle-btn ${state.sortOrder === 'step_first' ? 'active' : ''}"
                                onclick="setSortOrder('step_first')">
                            Step → Prompt
                            <span class="toggle-desc">All prompts at step 500, then step 1000…</span>
                        </button>
                        <button class="toggle-btn ${state.sortOrder === 'prompt_first' ? 'active' : ''}"
                                onclick="setSortOrder('prompt_first')">
                            Prompt → Step
                            <span class="toggle-desc">Prompt 0 across all steps, then prompt 1…</span>
                        </button>
                    </div>
                </div>

                <div class="config-row">
                    <label>Chunk size</label>
                    <div class="chunk-sizes">
                        ${[20, 50, 100, 200].map(n =>
        `<button class="size-btn ${state.chunkSize === n ? 'active' : ''}"
                                     onclick="setChunkSize(${n})">${n}</button>`
    ).join('')}
                        <input type="number" class="form-input size-custom" placeholder="Custom"
                               value="${![20, 50, 100, 200].includes(state.chunkSize) ? state.chunkSize : ''}"
                               onchange="if(this.value>0)setChunkSize(parseInt(this.value))">
                    </div>
                </div>

                <div class="config-row">
                    <label>Prefetch ahead</label>
                    <div class="chunk-sizes">
                        ${[4, 8, 16, 32].map(n =>
        `<button class="size-btn ${state.prefetchCount === n ? 'active' : ''}"
                                     onclick="setPrefetchCount(${n})">${n}</button>`
    ).join('')}
                    </div>
                </div>

                <div class="config-row">
                    <label>Start from step</label>
                    <div class="step-custom-row">
                        <select id="start-step" class="form-input">
                            <option value="0">Beginning (step 0)</option>
                            ${m.steps.filter(s => s > 0).map(s =>
        `<option value="${s}">Step ${s}</option>`
    ).join('')}
                        </select>
                    </div>
                </div>
            </div>

            <button class="btn btn-primary btn-lg" onclick="startChunkedEval()" style="margin-top:20px;width:100%">
                ▶ Start Evaluating
            </button>
        </div>
    `);
}

function setSortOrder(order) {
    state.sortOrder = order;
    localStorage.setItem('sortOrder', order);
    if (state.matrix) showMatrixOverview(state.matrix);
}

function setChunkSize(n) {
    state.chunkSize = n;
    localStorage.setItem('chunkSize', n);
    if (state.matrix) showMatrixOverview(state.matrix);
}

function setPrefetchCount(n) {
    state.prefetchCount = n;
    localStorage.setItem('prefetchCount', n);
    if (state.matrix) showMatrixOverview(state.matrix);
}

// --------------------------------------------------------------------------
// Build sequence & start chunked evaluation
// --------------------------------------------------------------------------
function startChunkedEval() {
    const m = state.matrix;
    if (!m) return;

    const startStep = parseInt(document.getElementById('start-step').value) || 0;

    // Build the full sequence of (step, promptIdx) pairs
    state.sequence = [];

    if (state.sortOrder === 'step_first') {
        // (step, prompt): all prompts at step 500, then all prompts at step 1000, ...
        for (const step of m.steps) {
            if (step < startStep) continue;
            for (let p = 0; p < m.num_prompts; p++) {
                state.sequence.push({ step, promptIdx: p });
            }
        }
    } else {
        // (prompt, step): prompt 0 at step 500, prompt 0 at step 1000, ..., then prompt 1, ...
        for (let p = 0; p < m.num_prompts; p++) {
            for (const step of m.steps) {
                if (step < startStep) continue;
                state.sequence.push({ step, promptIdx: p });
            }
        }
    }

    state.cursor = 0;
    loadNextChunk();
}

async function loadNextChunk() {
    const chunk = state.sequence.slice(state.cursor, state.cursor + state.chunkSize);
    if (chunk.length === 0) {
        showChunkDone();
        return;
    }

    // Group by step
    const stepGroups = {};
    for (const { step, promptIdx } of chunk) {
        if (!stepGroups[step]) stepGroups[step] = [];
        stepGroups[step].push(promptIdx);
    }
    const stepKeys = Object.keys(stepGroups);

    showEvalSetup(`<div class="eval-empty-inner">
        <div class="eval-empty-msg">Loading chunk ${Math.floor(state.cursor / state.chunkSize) + 1}...</div>
        <div class="eval-spinner"></div>
    </div>`);

    // Fetch FIRST step's metadata immediately so we can show the first video fast
    const videoMap = {};
    try {
        const firstStep = stepKeys[0];
        const videos = await api(`/api/videos/${state.runId}/${firstStep}`);
        videos.forEach(v => { videoMap[`${firstStep}:${v.index}`] = v; });
    } catch (err) {
        showEvalSetup(`<div class="eval-empty-msg">Failed to load: ${err.message}</div>`);
        return;
    }

    // Build partial video list from first step, show immediately
    state.currentVideos = [];
    for (const { step, promptIdx } of chunk) {
        const v = videoMap[`${step}:${promptIdx}`];
        if (v) {
            state.currentVideos.push({ ...v, _step: step });
        } else {
            // Placeholder for videos whose metadata hasn't loaded yet
            state.currentVideos.push({ _step: step, _promptIdx: promptIdx, _pending: true });
        }
    }

    state.currentVideoIdx = 0;
    toast(`Chunk loaded: ${state.currentVideos.filter(v => !v._pending).length} ready, ${state.currentVideos.filter(v => v._pending).length} loading...`, 'success');
    showEvalUI();
    renderEvalCard();

    // Fetch remaining steps' metadata in background (one at a time, not parallel)
    for (let i = 1; i < stepKeys.length; i++) {
        const step = stepKeys[i];
        try {
            const videos = await api(`/api/videos/${state.runId}/${step}`);
            videos.forEach(v => { videoMap[`${step}:${v.index}`] = v; });
            // Update placeholders in currentVideos
            for (let j = 0; j < state.currentVideos.length; j++) {
                const cv = state.currentVideos[j];
                if (cv._pending) {
                    const real = videoMap[`${cv._step}:${cv._promptIdx}`];
                    if (real) {
                        state.currentVideos[j] = { ...real, _step: cv._step };
                    }
                }
            }
        } catch { /* non-critical */ }
    }
}

// --------------------------------------------------------------------------
// Evaluate UI rendering
// --------------------------------------------------------------------------
function showEvalSetup(html) {
    document.getElementById('eval-empty').classList.remove('hidden');
    document.getElementById('eval-content').classList.add('hidden');
    document.getElementById('eval-empty').innerHTML = html;
}

function showEvalUI() {
    document.getElementById('eval-empty').classList.add('hidden');
    document.getElementById('eval-content').classList.remove('hidden');
}

function renderEvalCard() {
    const video = state.currentVideos[state.currentVideoIdx];
    if (!video) {
        showChunkSummary();
        return;
    }

    // If this video's metadata hasn't loaded yet, skip to next available
    if (video._pending) {
        toast('Video still loading, skipping...', 'info');
        if (state.currentVideoIdx < state.currentVideos.length - 1) {
            state.currentVideoIdx++;
            renderEvalCard();
        }
        return;
    }

    showEvalUI();
    const step = video._step || state.sequence[state.cursor + state.currentVideoIdx]?.step || 0;

    // Global progress
    const globalPos = state.cursor + state.currentVideoIdx + 1;
    const chunkNum = Math.floor(state.cursor / state.chunkSize) + 1;
    document.getElementById('eval-chunk-label').textContent =
        `Chunk ${chunkNum} • Video ${state.currentVideoIdx + 1}/${state.currentVideos.length} (${globalPos}/${state.sequence.length} total)`;

    // Dots
    const dotsEl = document.getElementById('eval-dots');
    if (state.currentVideos.length <= 50) {
        dotsEl.innerHTML = state.currentVideos.map((v, i) => {
            let cls = 'eval-dot';
            if (i === state.currentVideoIdx) cls += ' active';
            else if (v._rated === 'good' || v._rated === 'bad') cls += ' committed';
            else if (v._rated === 'skip') cls += ' skipped';
            return `<div class="${cls}"></div>`;
        }).join('');
    } else { dotsEl.innerHTML = ''; }

    // Card animation
    const card = document.getElementById('eval-card');
    card.classList.remove('swiping-left', 'swiping-right', 'swiping-up');
    card.classList.add('entering');
    setTimeout(() => card.classList.remove('entering'), 150);

    // Restore saved size and speed
    const savedSize = parseInt(localStorage.getItem('videoSize'));
    if (savedSize) setVideoSize(savedSize);

    // Video URL — via proxy
    const videoEl = document.getElementById('eval-video');
    const overlay = document.getElementById('eval-overlay');
    // Show loading state initially
    overlay.classList.add('show');
    overlay.querySelector('.eval-overlay-icon').textContent = '⏳';
    videoEl.src = video.proxy_url || `/api/video-proxy/${state.runId}/${step}/${video.index}`;
    videoEl.load();

    // If video is already cached, it'll be ready almost instantly
    const checkReady = () => {
        if (videoEl.readyState >= 3) {
            overlay.classList.remove('show');
            overlay.querySelector('.eval-overlay-icon').textContent = '▶';
        }
    };
    videoEl.oncanplay = () => {
        overlay.classList.remove('show');
        overlay.querySelector('.eval-overlay-icon').textContent = '▶';
        // Set speed AFTER load — browser resets playbackRate on load()
        videoEl.playbackRate = state.playbackSpeed;
    };
    // Check immediately in case already cached
    setTimeout(() => { checkReady(); videoEl.playbackRate = state.playbackSpeed; }, 50);
    videoEl.play().catch(() => { });

    // Time/frame badge
    const badge = document.getElementById('time-badge');
    const fps = 30; // assumed
    const fmt = s => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
    videoEl.ontimeupdate = () => {
        const t = videoEl.currentTime, d = videoEl.duration || 0;
        badge.textContent = `${fmt(t)} / ${fmt(d)} • F${Math.floor(t * fps)}/${Math.floor(d * fps)}`;
    };

    // Sequential prefetch — limited window
    prefetchSequential(state.currentVideoIdx + 1);

    // Meta
    document.getElementById('eval-caption').textContent = video.caption || video.prompt_id;
    document.getElementById('eval-category').textContent = video.action_label || video.category || '';
    document.getElementById('eval-step').textContent = `Step ${step}`;
    document.getElementById('speed-badge').textContent = `${state.playbackSpeed}×`;
    // Sync speed slider
    const sSlider = document.getElementById('speed-slider');
    if (sSlider) sSlider.value = state.playbackSpeed;
}

// Sequential prefetch: fetch one video at a time, limited to prefetchCount
let _prefetchRunning = false;
async function prefetchSequential(startIdx) {
    if (_prefetchRunning) return; // already prefetching
    _prefetchRunning = true;
    const limit = startIdx + state.prefetchCount;
    for (let i = startIdx; i < Math.min(limit, state.currentVideos.length); i++) {
        const v = state.currentVideos[i];
        if (v && !v._prefetched && !v._pending) {
            v._prefetched = true;
            const step = v._step || 0;
            try {
                await fetch(v.proxy_url || `/api/video-proxy/${state.runId}/${step}/${v.index}`);
            } catch { }
        }
    }
    _prefetchRunning = false;
}

function showChunkSummary() {
    const good = state.currentVideos.filter(v => v._rated === 'good').length;
    const bad = state.currentVideos.filter(v => v._rated === 'bad').length;
    const skip = state.currentVideos.filter(v => v._rated === 'skip').length;
    const remaining = state.sequence.length - (state.cursor + state.chunkSize);

    showEvalSetup(`
        <div class="eval-empty-inner">
            <h2>✅ Chunk Complete!</h2>
            <div class="eval-summary-stats">
                <span class="eval-stat good">✅ ${good}</span>
                <span class="eval-stat bad">❌ ${bad}</span>
                <span class="eval-stat skip">⏭ ${skip}</span>
            </div>
            <p class="subtitle" style="margin-top:12px">${remaining > 0 ? `${remaining.toLocaleString()} videos remaining` : 'All done!'}</p>
            <div style="display:flex;gap:10px;margin-top:20px;justify-content:center">
                ${remaining > 0 ? '<button class="btn btn-primary" onclick="advanceToNextChunk()">Next Chunk →</button>' : ''}
                <button class="btn btn-secondary" onclick="restartEval()">Back to Matrix</button>
            </div>
        </div>
    `);
}

function showChunkDone() {
    showEvalSetup(`
        <div class="eval-empty-inner">
            <h2>🎉 All Done!</h2>
            <p class="subtitle">You've evaluated all ${state.sequence.length.toLocaleString()} videos in the sequence.</p>
            <button class="btn btn-primary" onclick="router.navigate('dashboard')">Dashboard</button>
        </div>
    `);
}

function advanceToNextChunk() {
    state.cursor += state.chunkSize;
    loadNextChunk();
}

function restartEval() {
    state.currentVideos = [];
    state.currentVideoIdx = 0;
    state.cursor = 0;
    state.sequence = [];
    initEvaluate();
}

// Video toggle
document.getElementById('eval-video')?.addEventListener('click', () => {
    const v = document.getElementById('eval-video');
    const o = document.getElementById('eval-overlay');
    if (v.paused) { v.play(); o.classList.remove('show'); }
    else { v.pause(); o.classList.add('show'); }
});

// --------------------------------------------------------------------------
// Rating submission
// --------------------------------------------------------------------------
function flashBtn(id) {
    const btn = document.getElementById(id);
    if (!btn) return;
    btn.classList.add('pressed');
    setTimeout(() => btn.classList.remove('pressed'), 120);
}

function submitRating(rating) {
    if (state.currentVideos.length === 0) return;
    doSubmitRating(rating, []);
}

async function doSubmitRating(rating, issues = [], freeText = '') {
    const video = state.currentVideos[state.currentVideoIdx];
    if (!video) return;

    const card = document.getElementById('eval-card');
    if (rating === 'bad') card.classList.add('swiping-left');
    else if (rating === 'good') card.classList.add('swiping-right');
    else card.classList.add('swiping-up');

    video._rated = rating;
    const step = video._step || 0;

    try {
        await api('/api/ratings', {
            method: 'POST',
            body: JSON.stringify({
                video_id: `${video.prompt_id}_step${step}`,
                chunk_id: `chunk_${state.cursor}_${state.chunkSize}`,
                checkpoint_id: `${state.runId}_step${step}`,
                prompt_id: video.prompt_id || video.caption,
                rating,
                evaluator: state.evaluator,
                issues: issues.length > 0 ? issues : undefined,
                free_text: freeText || undefined,
                playback_speed: `${state.playbackSpeed}x`,
            }),
        });
    } catch {
        const buf = JSON.parse(localStorage.getItem('rating_buffer') || '[]');
        buf.push({ video, rating, issues, freeText, ts: new Date().toISOString() });
        localStorage.setItem('rating_buffer', JSON.stringify(buf));
    }

    setTimeout(() => { state.currentVideoIdx++; renderEvalCard(); }, 120);
}

// --------------------------------------------------------------------------
// Navigation: back / forward
// --------------------------------------------------------------------------
function goBack() {
    if (state.currentVideoIdx > 0) {
        state.currentVideoIdx--;
        renderEvalCard();
    }
}

function goForward() {
    if (state.currentVideoIdx < state.currentVideos.length - 1) {
        state.currentVideoIdx++;
        renderEvalCard();
    }
}

// --------------------------------------------------------------------------
// Speed + video size
// --------------------------------------------------------------------------
function setSpeed(speed) {
    state.playbackSpeed = speed;
    localStorage.setItem('playbackSpeed', speed);
    const v = document.getElementById('eval-video');
    if (v) v.playbackRate = speed;
    document.getElementById('speed-badge').textContent = `${speed}×`;
    const slider = document.getElementById('speed-slider');
    if (slider) slider.value = speed;
}

function setVideoSize(pct) {
    const container = document.getElementById('eval-card-container');
    if (container) {
        container.style.maxWidth = pct >= 100 ? 'none' : `${pct}vw`;
    }
    localStorage.setItem('videoSize', pct);
    document.getElementById('size-badge').textContent = `${pct}%`;
    const slider = document.getElementById('size-slider');
    if (slider) slider.value = pct;
}

// --------------------------------------------------------------------------
// Keyboard shortcuts
// --------------------------------------------------------------------------
document.addEventListener('keydown', e => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return;

    // Matrix page keyboard handling
    if (state.currentPage === 'matrix') {
        handleMatrixKey(e);
        return;
    }

    // Review/tagger keyboard handling
    if (state.currentPage === 'review') {
        const tagger = document.getElementById('review-tagger');
        if (tagger && !tagger.classList.contains('hidden')) {
            handleTaggerKey(e);
        }
        return;
    }

    if (state.currentPage !== 'evaluate') return;

    switch (e.key) {
        case 'l': case 'L': flashBtn('btn-good'); submitRating('good'); break;
        case 'j': case 'J': flashBtn('btn-bad'); submitRating('bad'); break;
        case 'k': case 'K': flashBtn('btn-skip'); submitRating('skip'); break;
        case 'ArrowLeft': case 'a': case 'A': case 'q': case 'Q': goBack(); break;
        case 'ArrowRight': case 'd': case 'D': case 'e': case 'E': goForward(); break;
        case 'Escape': restartEval(); break;
        case 'r': case 'R':
            document.getElementById('eval-video').currentTime = 0;
            document.getElementById('eval-video').play();
            break;
        case '1': setSpeed(1); break;
        case '2': setSpeed(2); break;
        case '3': setSpeed(3); break;
        case '4': setSpeed(4); break;
        case ' ':
            e.preventDefault();
            const v = document.getElementById('eval-video');
            v.paused ? v.play() : v.pause();
            break;
    }
});

// --------------------------------------------------------------------------
// Settings — localStorage-first, synced to server
// --------------------------------------------------------------------------
function getLocalSettings() {
    return {
        wandb_api_key: localStorage.getItem('wandb_api_key') || '',
        wandb_entity: localStorage.getItem('wandb_entity') || 'kaiqin_kong_ucsd',
        wandb_project: localStorage.getItem('wandb_project') || 'wangame_1.3b',
        default_run_id: localStorage.getItem('default_run_id') || 'fif3z1z4',
    };
}

function saveLocalSettings(settings) {
    for (const [k, v] of Object.entries(settings)) {
        if (v) localStorage.setItem(k, v);
    }
    state.settings = { ...state.settings, ...settings };
    state.runId = settings.default_run_id || state.runId;
}

async function loadSettings() {
    // Load from localStorage first
    const local = getLocalSettings();
    state.settings = local;
    state.runId = local.default_run_id;

    const keyInput = document.getElementById('setting-api-key');
    keyInput.value = local.wandb_api_key || '';
    document.getElementById('setting-entity').value = local.wandb_entity;
    document.getElementById('setting-project').value = local.wandb_project;
    document.getElementById('setting-run-id').value = local.default_run_id;
    document.getElementById('setting-evaluator').value = state.evaluator;
    // Auto-save evaluator name on change
    document.getElementById('setting-evaluator').oninput = (e) => {
        state.evaluator = e.target.value || 'evaluator';
        localStorage.setItem('evaluator', state.evaluator);
    };

    // Sync from server in background (won't override localStorage)
    try {
        const s = await api('/api/settings');
        // Only fill empty fields from server
        if (!local.wandb_api_key && s.wandb_api_key) {
            localStorage.setItem('wandb_api_key', s.wandb_api_key);
            document.getElementById('setting-api-key').placeholder = '••••••••';
        }
    } catch { }

    try {
        const h = await api('/api/health');
        document.getElementById('server-health').textContent =
            `Status: ${h.status} • DB: ${h.database} • Version: ${h.version}`;
    } catch (err) {
        document.getElementById('server-health').textContent = `Error: ${err.message}`;
    }
}

async function saveSettings() {
    const settings = {};
    const key = document.getElementById('setting-api-key').value;
    if (key) settings.wandb_api_key = key;
    settings.wandb_entity = document.getElementById('setting-entity').value;
    settings.wandb_project = document.getElementById('setting-project').value;
    settings.default_run_id = document.getElementById('setting-run-id').value;

    state.evaluator = document.getElementById('setting-evaluator').value || 'evaluator';
    localStorage.setItem('evaluator', state.evaluator);

    // Save to localStorage first (instant)
    saveLocalSettings(settings);
    toast('Settings saved', 'success');

    // Sync to server in background
    try {
        await api('/api/settings', { method: 'PUT', body: JSON.stringify(settings) });
    } catch (err) {
        toast(`Server sync: ${err.message}`, 'error');
    }
}

async function testConnection() {
    const el = document.getElementById('settings-status');
    el.className = 'settings-status'; el.textContent = 'Testing...';
    try {
        const key = document.getElementById('setting-api-key').value || localStorage.getItem('wandb_api_key') || undefined;
        const r = await api('/api/settings/test', { method: 'POST', body: JSON.stringify({ wandb_api_key: key }) });
        el.className = `settings-status ${r.success ? 'success' : 'error'}`;
        el.textContent = r.message + (r.runs_found ? ` (${r.runs_found} runs)` : '');
    } catch (err) { el.className = 'settings-status error'; el.textContent = `Error: ${err.message}`; }
}

function toggleKeyVisibility() {
    const i = document.getElementById('setting-api-key');
    i.type = i.type === 'password' ? 'text' : 'password';
}

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
        const step = ckpt.replace('step_', '') || '?';
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
                           src="/api/video-proxy/${state.runId}/${step}/${r.prompt_id || 0}"
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
    const step = ckpt.replace('step_', '') || '0';
    const videoEl = document.getElementById('tagger-video');
    videoEl.src = `/api/video-proxy/${state.runId}/${step}/${r.prompt_id || 0}`;
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

// --------------------------------------------------------------------------
// Results
// --------------------------------------------------------------------------
async function loadResults() {
    const c = document.getElementById('results-container');
    try {
        const scores = await api('/api/results');
        if (scores.length === 0) { c.innerHTML = '<div class="empty-state">No scores computed yet.</div>'; return; }
        c.innerHTML = scores.map(s => {
            const pct = Math.round(s.overall_score * 100);
            const cls = pct >= 70 ? 'high' : pct >= 40 ? 'mid' : 'low';
            const clr = pct >= 70 ? 'var(--good)' : pct >= 40 ? 'var(--warn)' : 'var(--bad)';
            return `<div class="result-card"><h3>${s.checkpoint_id}</h3>
                <div class="result-score ${cls}">${pct}%</div>
                <div class="result-bar"><div class="result-bar-fill" style="width:${pct}%;background:${clr}"></div></div>
                <div class="result-stats"><span>✅ ${s.total_good}</span> <span>❌ ${s.total_bad}</span>
                <span>⏭ ${s.total_skipped}</span> <span>👤 ${s.evaluator_count}</span></div></div>`;
        }).join('');
    } catch (err) { c.innerHTML = `<div class="empty-state">Error: ${err.message}</div>`; }
}

async function loadSkippedQueue() {
    try {
        const s = await api('/api/skipped');
        toast(s.length ? `${s.length} skipped videos` : 'No skipped videos', 'info');
    } catch (err) { toast(`Error: ${err.message}`, 'error'); }
}

// --------------------------------------------------------------------------
// Matrix — video comparison grid
// --------------------------------------------------------------------------
const MATRIX_CATEGORIES = [
    { name: 'Single Key', color: '#3fb950', indices: [0, 1, 2, 3] },
    { name: 'Camera', color: '#d29922', indices: [4, 5, 6, 7] },
    { name: 'Random', color: '#58a6ff', indices: [8, 9, 10, 11] },
    { name: 'Combined', color: '#bc8cff', indices: [12, 13, 14, 15] },
    { name: 'Simultaneous', color: '#bc8cff', indices: [16, 17, 18, 19] },
    { name: 'Multi-key', color: '#bc8cff', indices: [20, 21] },
    { name: 'Still', color: '#8b949e', indices: [22, 23] },
    { name: 'Alt Frame', color: '#bc8cff', indices: [24, 25] },
    { name: 'Training', color: '#f0883e', indices: [26, 27] },
    { name: 'Doom', color: '#f85149', indices: [28, 29, 30, 31] },
];

const matrixState = {
    steps: [],
    selectedSteps: new Set(),
    selectedCats: new Set(['Single Key']),
    numPrompts: 32,
    speed: 1,
    videoMetaCache: {}, // step → videoList
};

async function loadMatrix() {
    if (!state.runId) {
        const local = getLocalSettings();
        state.runId = local.default_run_id;
    }
    if (!state.runId) {
        document.getElementById('matrix-grid').innerHTML = '<div class="empty-state">No run configured. Go to Settings first.</div>';
        return;
    }

    // Fetch matrix dimensions
    try {
        const m = await api(`/api/matrix/${state.runId}`);
        matrixState.steps = m.steps;
        matrixState.numPrompts = m.num_prompts;
        document.getElementById('matrix-subtitle').textContent = `${m.run_name} • ${m.steps.length} steps × ${m.num_prompts} prompts = ${m.total_videos.toLocaleString()} videos`;

        // Default: pick last 3 steps, Single Key category
        matrixState.selectedSteps = new Set(m.steps.slice(-3));
        renderMatrixFilters();
        renderMatrixGrid();
    } catch (err) {
        document.getElementById('matrix-grid').innerHTML = `<div class="empty-state">Error: ${err.message}</div>`;
    }
}

function renderMatrixFilters() {
    const stepCont = document.getElementById('matrix-step-btns');
    // Top-K shortcuts
    let html = `<div style="display:flex;gap:4px;margin-bottom:6px">`;
    for (const k of [3, 5, 10, 20, 'All']) {
        html += `<button class="btn btn-sm" onclick="matrixTopK(${k === 'All' ? 0 : k})">${k === 'All' ? 'All' : `Last ${k}`}</button>`;
    }
    html += `</div><div style="display:flex;gap:3px;flex-wrap:wrap">`;
    for (const step of matrixState.steps) {
        const active = matrixState.selectedSteps.has(step) ? 'active' : '';
        html += `<button class="matrix-step-chip ${active}" data-step="${step}" onclick="matrixToggleStep(${step}, event)">${step}</button>`;
    }
    html += `</div>`;
    stepCont.innerHTML = html;

    // Category filters
    const catCont = document.getElementById('matrix-cat-btns');
    catCont.innerHTML = MATRIX_CATEGORIES.map(c => {
        const active = matrixState.selectedCats.has(c.name) ? 'active' : '';
        return `<button class="matrix-cat-chip ${active}" style="--cat-color:${c.color}" onclick="matrixToggleCat('${c.name}', this)">${c.name}</button>`;
    }).join('');
}

function matrixTopK(k) {
    if (k === 0) {
        matrixState.selectedSteps = new Set(matrixState.steps);
    } else {
        matrixState.selectedSteps = new Set(matrixState.steps.slice(-k));
    }
    renderMatrixFilters();
    renderMatrixGrid();
}

function matrixToggleStep(step, e) {
    if (e && e.shiftKey) {
        // Solo this step
        matrixState.selectedSteps = new Set([step]);
    } else {
        if (matrixState.selectedSteps.has(step)) matrixState.selectedSteps.delete(step);
        else matrixState.selectedSteps.add(step);
    }
    renderMatrixFilters();
    renderMatrixGrid();
}

function matrixToggleCat(name, btn) {
    if (matrixState.selectedCats.has(name)) matrixState.selectedCats.delete(name);
    else matrixState.selectedCats.add(name);
    btn.classList.toggle('active');
    renderMatrixGrid();
}

function renderMatrixGrid() {
    const grid = document.getElementById('matrix-grid');
    const steps = matrixState.steps.filter(s => matrixState.selectedSteps.has(s)).sort((a, b) => a - b);
    if (steps.length === 0) {
        grid.innerHTML = '<div class="empty-state">Select at least one step above.</div>';
        return;
    }

    // Determine which prompt indices to show
    let visibleIndices = [];
    for (const cat of MATRIX_CATEGORIES) {
        if (matrixState.selectedCats.has(cat.name)) {
            visibleIndices.push(...cat.indices);
        }
    }
    visibleIndices = visibleIndices.filter(i => i < matrixState.numPrompts).sort((a, b) => a - b);

    const cols = steps.length;
    const colTemplate = `200px repeat(${cols}, 1fr)`;

    // Header row
    let html = `<div class="matrix-header-row" style="grid-template-columns:${colTemplate}">`;
    html += `<div class="matrix-corner">Prompt</div>`;
    for (const step of steps) {
        html += `<div class="matrix-col-header">Step ${step}</div>`;
    }
    html += `</div>`;

    // Group by category
    let currentCat = null;
    for (const idx of visibleIndices) {
        const cat = MATRIX_CATEGORIES.find(c => c.indices.includes(idx));
        if (cat && cat.name !== currentCat) {
            currentCat = cat.name;
            html += `<div class="matrix-cat-divider" style="color:${cat.color}">${cat.name}</div>`;
        }

        html += `<div class="matrix-row" data-row="${idx}" style="grid-template-columns:${colTemplate}">`;
        html += `<div class="matrix-prompt-label">
            <span class="matrix-prompt-idx">${String(idx).padStart(2, '0')}</span>
            <span class="matrix-row-controls">
                <button onclick="matrixRowPlay(${idx})" title="Play row">▶</button>
                <button onclick="matrixRowPause(${idx})" title="Pause row">⏸</button>
                <button onclick="matrixRowReplay(${idx})" title="Replay row">🔄</button>
            </span>
        </div>`;

        for (const step of steps) {
            const proxyUrl = `/api/video-proxy/${state.runId}/${step}/${idx}`;
            html += `<div class="matrix-video-cell" data-url="${proxyUrl}">
                <video preload="none" muted loop playsinline data-proxy="${proxyUrl}"
                       onclick="this.paused?this.play():this.pause()"></video>
                <span class="matrix-size-tag">S${step}</span>
            </div>`;
        }
        html += `</div>`;
    }

    grid.innerHTML = html;

    // Lazy-load videos and auto-play as they scroll into view
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(e => {
            if (e.isIntersecting) {
                const video = e.target.querySelector('video');
                if (video && !video.src) {
                    video.src = video.dataset.proxy;
                    video.preload = 'auto';
                    video.addEventListener('loadeddata', () => {
                        video.playbackRate = matrixState.speed;
                        video.play().catch(() => { });
                    }, { once: true });
                }
                observer.unobserve(e.target);
            }
        });
    }, { rootMargin: '500px' });

    grid.querySelectorAll('.matrix-video-cell').forEach(cell => observer.observe(cell));

    // Click-to-focus: clicking a cell sets keyboard focus to it
    const rows = grid.querySelectorAll('.matrix-row');
    rows.forEach((row, ri) => {
        const cells = row.querySelectorAll('.matrix-video-cell');
        cells.forEach((cell, ci) => {
            cell.addEventListener('click', () => {
                matrixState.focusRow = ri;
                matrixState.focusCol = ci;
                updateMatrixFocus();
            });
        });
    });
}

function matrixPlayAll() { document.querySelectorAll('#matrix-grid video').forEach(v => { if (v.src) v.play(); }); }
function matrixPauseAll() { document.querySelectorAll('#matrix-grid video').forEach(v => v.pause()); }
function matrixReplayAll() { document.querySelectorAll('#matrix-grid video').forEach(v => { if (v.src) { v.currentTime = 0; v.play(); } }); }
function matrixToggleSpeed() {
    matrixState.speed = matrixState.speed === 1 ? 2 : matrixState.speed === 2 ? 4 : matrixState.speed === 4 ? 0.5 : 1;
    document.querySelectorAll('#matrix-grid video').forEach(v => v.playbackRate = matrixState.speed);
    document.getElementById('matrix-speed-btn').textContent = `${matrixState.speed}× Speed`;
}

function _rowVideos(idx) { return document.querySelectorAll(`.matrix-row[data-row="${idx}"] video`); }
function matrixRowPlay(idx) { _rowVideos(idx).forEach(v => { if (v.src) { v.playbackRate = matrixState.speed; v.play(); } }); }
function matrixRowPause(idx) { _rowVideos(idx).forEach(v => v.pause()); }
function matrixRowReplay(idx) { _rowVideos(idx).forEach(v => { if (v.src) { v.currentTime = 0; v.playbackRate = matrixState.speed; v.play(); } }); }

// --------------------------------------------------------------------------
// Matrix keyboard navigation and rating
// --------------------------------------------------------------------------
// Focus is tracked as (rowIndex in visibleIndices, colIndex in selected steps)
matrixState.focusRow = 0;
matrixState.focusCol = 0;

function getMatrixCells() {
    return document.querySelectorAll('#matrix-grid .matrix-video-cell');
}

function getMatrixDimensions() {
    const rows = document.querySelectorAll('#matrix-grid .matrix-row');
    if (rows.length === 0) return { rows: 0, cols: 0 };
    const cols = rows[0].querySelectorAll('.matrix-video-cell').length;
    return { rows: rows.length, cols };
}

function getFocusedCell() {
    const rows = document.querySelectorAll('#matrix-grid .matrix-row');
    if (matrixState.focusRow >= rows.length) return null;
    const cells = rows[matrixState.focusRow].querySelectorAll('.matrix-video-cell');
    if (matrixState.focusCol >= cells.length) return null;
    return cells[matrixState.focusCol];
}

function updateMatrixFocus() {
    // Clear all focus
    document.querySelectorAll('.matrix-video-cell.focused').forEach(c => c.classList.remove('focused'));
    const cell = getFocusedCell();
    if (cell) {
        cell.classList.add('focused');
        cell.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
        // Ensure the video is loaded
        const video = cell.querySelector('video');
        if (video && !video.src && video.dataset.proxy) {
            video.src = video.dataset.proxy;
            video.preload = 'auto';
        }
    }
}

function handleMatrixKey(e) {
    const dim = getMatrixDimensions();
    if (dim.rows === 0) return;

    switch (e.key) {
        case 'ArrowUp':
            e.preventDefault();
            matrixState.focusRow = Math.max(0, matrixState.focusRow - 1);
            updateMatrixFocus();
            break;
        case 'ArrowDown':
            e.preventDefault();
            matrixState.focusRow = Math.min(dim.rows - 1, matrixState.focusRow + 1);
            updateMatrixFocus();
            break;
        case 'ArrowLeft':
            e.preventDefault();
            matrixState.focusCol = Math.max(0, matrixState.focusCol - 1);
            updateMatrixFocus();
            break;
        case 'ArrowRight':
            e.preventDefault();
            matrixState.focusCol = Math.min(dim.cols - 1, matrixState.focusCol + 1);
            updateMatrixFocus();
            break;
        case 'Tab':
            e.preventDefault();
            matrixState.focusCol++;
            if (matrixState.focusCol >= dim.cols) {
                matrixState.focusCol = 0;
                matrixState.focusRow = (matrixState.focusRow + 1) % dim.rows;
            }
            updateMatrixFocus();
            break;
        case 'l': case 'L':
            matrixRateFocused('good');
            break;
        case 'j': case 'J':
            matrixRateFocused('bad');
            break;
        case 'k': case 'K':
            matrixRateFocused('skip');
            break;
        case ' ': {
            e.preventDefault();
            const cell = getFocusedCell();
            if (cell) {
                const vid = cell.querySelector('video');
                if (vid && vid.src) vid.paused ? vid.play() : vid.pause();
            }
            break;
        }
        case 'r': case 'R': {
            const cell = getFocusedCell();
            if (cell) {
                const vid = cell.querySelector('video');
                if (vid && vid.src) { vid.currentTime = 0; vid.play(); }
            }
            break;
        }
    }
}

async function matrixRateFocused(rating) {
    const cell = getFocusedCell();
    if (!cell) return;

    // Extract step and index from the video proxy URL
    const video = cell.querySelector('video');
    const url = video?.dataset?.proxy || cell.dataset.url;
    if (!url) return;

    // URL format: /api/video-proxy/{run_id}/{step}/{index}
    const parts = url.split('/');
    const videoIndex = parseInt(parts[parts.length - 1]);
    const step = parseInt(parts[parts.length - 2]);
    const runId = parts[parts.length - 3];

    const evaluator = localStorage.getItem('evaluator') || document.getElementById('setting-evaluator')?.value || 'evaluator';

    try {
        await api('/api/ratings', {
            method: 'POST',
            body: JSON.stringify({
                run_id: runId,
                checkpoint_id: `step_${step}`,
                video_id: `${runId}/${step}/${videoIndex}`,
                prompt_id: `prompt_${String(videoIndex).padStart(2, '0')}`,
                evaluator: evaluator,
                rating: rating,
                issues: [],
            }),
        });

        // Show rating badge on the cell
        const badge = rating === 'good' ? '✅' : rating === 'bad' ? '❌' : '⏭';
        const cls = rating === 'good' ? 'good' : rating === 'bad' ? 'bad' : 'skip';
        let overlay = cell.querySelector('.matrix-rating-badge');
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.className = 'matrix-rating-badge';
            cell.appendChild(overlay);
        }
        overlay.textContent = badge;
        overlay.className = `matrix-rating-badge ${cls}`;

        toast(`Rated ${rating}`, 'success');
    } catch (err) {
        toast(`Rating error: ${err.message}`, 'error');
    }
}

// Init
document.addEventListener('DOMContentLoaded', loadDashboard);
if (document.readyState !== 'loading') loadDashboard();

