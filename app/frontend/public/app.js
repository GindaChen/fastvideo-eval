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
    prefetchCount: parseInt(localStorage.getItem('prefetchCount')) || 8,
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

    // Group by step to batch-fetch metadata
    const stepGroups = {};
    for (const { step, promptIdx } of chunk) {
        if (!stepGroups[step]) stepGroups[step] = [];
        stepGroups[step].push(promptIdx);
    }

    showEvalSetup(`<div class="eval-empty-inner">
        <div class="eval-empty-msg">Loading chunk ${Math.floor(state.cursor / state.chunkSize) + 1}...</div>
        <div class="eval-spinner"></div>
    </div>`);

    // Fetch metadata for each step in the chunk (in parallel)
    const videoMap = {}; // `${step}:${idx}` → video data
    try {
        const fetches = Object.keys(stepGroups).map(async step => {
            const videos = await api(`/api/videos/${state.runId}/${step}`);
            videos.forEach(v => { videoMap[`${step}:${v.index}`] = v; });
        });
        await Promise.all(fetches);
    } catch (err) {
        showEvalSetup(`<div class="eval-empty-msg">Failed to load: ${err.message}</div>`);
        return;
    }

    // Build the chunk's video list in sequence order
    state.currentVideos = [];
    for (const { step, promptIdx } of chunk) {
        const v = videoMap[`${step}:${promptIdx}`];
        if (v) {
            state.currentVideos.push({ ...v, _step: step });
        }
    }

    if (state.currentVideos.length === 0) {
        // Skip to next chunk if nothing found
        state.cursor += state.chunkSize;
        loadNextChunk();
        return;
    }

    state.currentVideoIdx = 0;
    toast(`Chunk loaded: ${state.currentVideos.length} videos`, 'success');
    showEvalUI();
    renderEvalCard();
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
    // Show loading state
    overlay.classList.add('show');
    overlay.querySelector('.eval-overlay-icon').textContent = '⏳';
    videoEl.src = video.proxy_url || `/api/video-proxy/${state.runId}/${step}/${video.index}`;
    videoEl.playbackRate = state.playbackSpeed;
    videoEl.load();
    videoEl.oncanplay = () => {
        overlay.classList.remove('show');
        overlay.querySelector('.eval-overlay-icon').textContent = '▶';
    };
    videoEl.play().catch(() => { });

    // Time/frame badge
    const badge = document.getElementById('time-badge');
    const fps = 30; // assumed
    const fmt = s => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
    videoEl.ontimeupdate = () => {
        const t = videoEl.currentTime, d = videoEl.duration || 0;
        badge.textContent = `${fmt(t)} / ${fmt(d)} • F${Math.floor(t * fps)}/${Math.floor(d * fps)}`;
    };

    // Prefetch next 3
    prefetchAhead(state.currentVideoIdx + 1, state.prefetchCount);

    // Meta
    document.getElementById('eval-caption').textContent = video.caption || video.prompt_id;
    document.getElementById('eval-category').textContent = video.action_label || video.category || '';
    document.getElementById('eval-step').textContent = `Step ${step}`;
    document.getElementById('speed-badge').textContent = `${state.playbackSpeed}×`;
}

function prefetchAhead(startIdx, count) {
    for (let i = startIdx; i < Math.min(startIdx + count, state.currentVideos.length); i++) {
        const v = state.currentVideos[i];
        if (v && !v._prefetched) {
            v._prefetched = true;
            const step = v._step || 0;
            fetch(v.proxy_url || `/api/video-proxy/${state.runId}/${step}/${v.index}`).catch(() => { });
        }
    }
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
    if (state.currentPage !== 'evaluate') return;
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return;

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
    { key: 'wrong_direction', label: 'Wrong direction' },
    { key: 'no_movement', label: 'No movement' },
    { key: 'jittery', label: 'Jittery / unstable' },
    { key: 'visual_artifacts', label: 'Visual artifacts' },
    { key: 'wrong_action', label: 'Wrong action' },
    { key: 'partial_action', label: 'Incomplete action' },
    { key: 'camera_wrong', label: 'Camera issue' },
];

async function loadReview() {
    const container = document.getElementById('review-content');
    const subtitle = document.getElementById('review-subtitle');
    container.innerHTML = '<div class="empty-state">Loading bad ratings...</div>';

    try {
        const ratings = await api('/api/ratings/bad');
        if (ratings.length === 0) {
            container.innerHTML = '<div class="empty-state">No bad-rated videos yet. Rate some videos as bad first.</div>';
            subtitle.textContent = '0 videos to review';
            return;
        }

        const needsReview = ratings.filter(r => !r.issues || r.issues.length === 0);
        const reviewed = ratings.filter(r => r.issues && r.issues.length > 0);
        subtitle.textContent = `${needsReview.length} needs review • ${reviewed.length} already tagged • ${ratings.length} total`;

        container.innerHTML = ratings.map((r, idx) => {
            const vid = r.video_id;
            const ckpt = r.checkpoint_id || '';
            const step = ckpt.split('_step')[1] || '?';
            const issues = r.issues || [];
            const freeText = r.free_text || '';
            const hasIssues = issues.length > 0;

            // Merge custom tags from existing issues that aren't in ISSUE_TAGS
            const knownKeys = ISSUE_TAGS.map(t => t.key);
            const customTags = issues.filter(t => !knownKeys.includes(t) && t !== 'other');

            const tagButtons = ISSUE_TAGS.map(t =>
                `<button class="issue-tag ${issues.includes(t.key) ? 'active' : ''}"
                         data-key="${t.key}" onclick="toggleIssueTag(${idx}, '${t.key}', this)">${t.label}</button>`
            ).join('');

            const customButtons = customTags.map(t =>
                `<button class="issue-tag active"
                         data-key="${t}" onclick="toggleIssueTag(${idx}, '${t}', this)">${t}</button>`
            ).join('');

            // Extract prompt index from video_id (format: promptId_step...)
            const promptLabel = r.prompt_id || vid;

            return `
                <div class="review-card ${hasIssues ? 'reviewed' : 'needs-review'}" id="review-${idx}" data-rating-id="${r.rating_id}">
                    <div class="review-header">
                        <span class="review-label">${hasIssues ? '✅' : '⚠️'} ${promptLabel}</span>
                        <span class="review-step">Step ${step}</span>
                    </div>
                    <div class="review-body">
                        <video class="review-video" playsinline muted loop preload="none"
                               src="/api/video-proxy/${state.runId}/${step}/${r.prompt_id || 0}"
                               onclick="this.paused?this.play():this.pause()"></video>
                        <div class="review-tags">
                            <div class="tag-row">${tagButtons}${customButtons}</div>
                            <div class="review-other-row">
                                <input type="text" class="form-input review-freetext" id="freetext-${idx}"
                                       placeholder="Other reason..." value="${freeText}">
                                <button class="btn btn-sm btn-primary" onclick="saveReviewIssues(${idx})">Save</button>
                            </div>
                        </div>
                    </div>
                </div>`;
        }).join('');

        // Store ratings data for save
        window._reviewRatings = ratings;
    } catch (err) {
        container.innerHTML = `<div class="empty-state">Error: ${err.message}</div>`;
    }
}

function toggleIssueTag(idx, key, btn) {
    btn.classList.toggle('active');
}

async function saveReviewIssues(idx) {
    const r = window._reviewRatings[idx];
    if (!r) return;

    const card = document.getElementById(`review-${idx}`);
    const activeTags = [...card.querySelectorAll('.issue-tag.active')].map(b => b.dataset.key);
    const freeText = document.getElementById(`freetext-${idx}`).value.trim();

    // If freeText is non-empty and there's no 'other' tag, add it  
    if (freeText && !activeTags.includes('other')) activeTags.push('other');

    try {
        await api(`/api/ratings/${r.rating_id}/issues`, {
            method: 'PATCH',
            body: JSON.stringify({ issues: activeTags, free_text: freeText || null }),
        });
        card.classList.remove('needs-review');
        card.classList.add('reviewed');
        card.querySelector('.review-label').innerHTML = `✅ ${r.prompt_id || r.video_id}`;
        toast('Issues saved', 'success');
    } catch (err) {
        toast(`Error: ${err.message}`, 'error');
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

// Init
document.addEventListener('DOMContentLoaded', loadDashboard);
if (document.readyState !== 'loading') loadDashboard();
