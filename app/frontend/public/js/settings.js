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
