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
