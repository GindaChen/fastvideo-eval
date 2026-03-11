
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
        case 'u': case 'U': {
            // Previous cell (left, wrapping to previous row)
            e.preventDefault();
            matrixState.focusCol--;
            if (matrixState.focusCol < 0) {
                matrixState.focusCol = dim.cols - 1;
                matrixState.focusRow = Math.max(0, matrixState.focusRow - 1);
            }
            updateMatrixFocus();
            break;
        }
        case 'o': case 'O': {
            // Next cell (right, wrapping to next row)
            e.preventDefault();
            matrixState.focusCol++;
            if (matrixState.focusCol >= dim.cols) {
                matrixState.focusCol = 0;
                matrixState.focusRow = Math.min(dim.rows - 1, matrixState.focusRow + 1);
            }
            updateMatrixFocus();
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

        // Auto-advance to next cell after a brief flash
        setTimeout(() => {
            const allCells = Array.from(document.querySelectorAll('.matrix-video-cell'));
            const curIdx = allCells.indexOf(cell);
            if (curIdx >= 0 && curIdx < allCells.length - 1) {
                matrixState.focusRow = parseInt(allCells[curIdx + 1].closest('.matrix-row')?.dataset.row || '0');
                matrixState.focusCol = Array.from(allCells[curIdx + 1].closest('.matrix-row')?.querySelectorAll('.matrix-video-cell') || []).indexOf(allCells[curIdx + 1]);
                updateMatrixFocus();
            }
        }, 200);
    } catch (err) {
        toast(`Rating error: ${err.message}`, 'error');
    }
}
