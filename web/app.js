const API = 'http://127.0.0.1:4321';

const tabs = document.querySelectorAll('[data-tab]');
tabs.forEach(tab => {
  tab.addEventListener('click', () => {
    tabs.forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById(`tab-${tab.dataset.tab}`).classList.add('active');
  });
});

async function loadStats() {
  try {
    const [statsRes] = await Promise.all([
      fetch(`${API}/v1/stats`),
    ]);
    const stats = await statsRes.json();
    const grid = document.getElementById('stats-grid');
    grid.innerHTML = `
      <div class="stat-card"><div class="label">Memories</div><div class="value">${stats.total}</div></div>
      <div class="stat-card"><div class="label">Usage</div><div class="value ${stats.usagePercent > 80 ? 'red' : stats.usagePercent > 50 ? 'yellow' : 'green'}">${stats.usagePercent}%</div></div>
      <div class="stat-card"><div class="label">Keys</div><div class="value">${stats.uniqueKeys}</div></div>
      <div class="stat-card"><div class="label">Tags</div><div class="value">${stats.uniqueTags}</div></div>
      <div class="stat-card"><div class="label">Max</div><div class="value">${stats.max}</div></div>
    `;
  } catch (e) {
    document.getElementById('stats-grid').innerHTML = '<p>Cannot connect to MCP server. Ensure it\'s running.</p>';
  }
}

async function loadMemories() {
  try {
    const res = await fetch(`${API}/v1/memories?limit=20`);
    const memories = await res.json();
    const list = document.getElementById('memories-list');
    list.innerHTML = memories.map(m => `
      <div class="memory-item">
        <div class="key">${m.key}</div>
        <div class="content">${m.content.slice(0, 200)}</div>
        <div class="meta">${new Date(m.createdAt).toLocaleString()} | tags: ${(m.tags || []).join(', ') || 'none'}</div>
      </div>
    `).join('') || '<p>No memories yet.</p>';
  } catch { loadMemories(); }
}

async function loadGoals() {
  try {
    const res = await fetch(`${API}/v1/agents`);
    const data = await res.json();
    document.getElementById('goals-list').innerHTML = `
      <div class="stat-card"><div class="label">Uptime</div><div class="value">${Math.round(data.uptime)}s</div></div>
      <div class="stat-card"><div class="label">Active Goals</div><div class="value">${data.goals}</div></div>
    `;
  } catch {}
}

async function loadPeers() {
  document.getElementById('peers-list').innerHTML = '<p>Connect to the MCP server via the federation tab on the main interface.</p>';
}

async function loadLogs() {
  try {
    const res = await fetch(`${API}/v1/logs?limit=50`);
    const logs = await res.json();
    const viewer = document.getElementById('log-viewer');
    viewer.textContent = logs.map(e =>
      `[${e.timestamp}] [${e.level}] ${e.component}: ${e.message}`
    ).join('\n') || '[No logs]';
  } catch {}
}

loadStats();
loadMemories();
loadGoals();
loadPeers();
loadLogs();

setInterval(loadStats, 5000);
setInterval(loadMemories, 10000);
setInterval(loadLogs, 15000);
