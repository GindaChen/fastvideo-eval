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
        document.getElementById('sidebar').classList.remove('open');
        document.getElementById('sidebar-backdrop').classList.remove('show');
    });
});

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
        case 'ArrowLeft': case 'a': case 'A': case 'q': case 'Q': case 'u': case 'U': goBack(); break;
        case 'ArrowRight': case 'd': case 'D': case 'e': case 'E': case 'o': case 'O': goForward(); break;
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


// Init
document.addEventListener('DOMContentLoaded', loadDashboard);
if (document.readyState !== 'loading') loadDashboard();

