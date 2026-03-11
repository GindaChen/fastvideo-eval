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
