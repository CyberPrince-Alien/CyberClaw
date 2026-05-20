/* CyberClaw Web UI — Application Logic */

const API = window.location.origin;
let currentView = 'chat';
let sessionId = null;
let isStreaming = false;

// ── Boot ──────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  setTimeout(() => document.getElementById('loadingScreen').classList.add('hidden'), 600);
  await checkHealth();
  setInterval(checkHealth, 30000);
});

async function checkHealth() {
  try {
    const r = await fetch(`${API}/health`);
    const d = await r.json();
    document.getElementById('statusDot').style.background = d.status === 'ok' ? 'var(--success)' : 'var(--error)';
    document.getElementById('statusDot').title = d.status === 'ok' ? 'Connected' : 'Disconnected';
  } catch { document.getElementById('statusDot').style.background = 'var(--error)'; }
}

// ── Navigation ────────────────────────────────────
function switchView(view) {
  currentView = view;
  document.querySelectorAll('.nav-item').forEach(n => n.classList.toggle('active', n.dataset.view === view));
  const titles = { chat:'Chat', dashboard:'Dashboard', models:'Model Catalog', sessions:'Sessions',
                   tasks:'Tasks', providers:'Providers', metrics:'Metrics', channels:'Channels' };
  document.getElementById('viewTitle').textContent = titles[view] || view;
  const content = document.getElementById('contentArea');
  if (view === 'chat') { content.innerHTML = getChatHTML(); return; }
  if (view === 'dashboard') { loadDashboard(); return; }
  if (view === 'models') { loadModels(); return; }
  if (view === 'sessions') { loadSessions(); return; }
  if (view === 'metrics') { loadMetrics(); return; }
  if (view === 'providers') { loadProviders(); return; }
  if (view === 'channels') { loadChannels(); return; }
  if (view === 'tasks') { loadTasks(); return; }
}

function getChatHTML() {
  return `<div class="chat-container">
    <div class="messages" id="messages"><div class="empty-state"><div class="icon">🤖</div>
    <p>Start a conversation with CyberClaw.</p></div></div>
    <div class="chat-input-area"><div class="chat-input-wrapper">
    <textarea id="chatInput" placeholder="Type your message..." rows="1"
      onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();sendMessage()}"></textarea>
    <button class="send-btn" onclick="sendMessage()" id="sendBtn">→</button>
    </div></div></div>`;
}

// ── Chat ──────────────────────────────────────────
async function sendMessage() {
  const input = document.getElementById('chatInput');
  const text = input.value.trim();
  if (!text || isStreaming) return;
  input.value = ''; isStreaming = true;
  document.getElementById('sendBtn').disabled = true;

  const msgs = document.getElementById('messages');
  if (msgs.querySelector('.empty-state')) msgs.innerHTML = '';

  // User message
  msgs.innerHTML += `<div class="message user">${escapeHtml(text)}</div>`;

  // Thinking indicator
  msgs.innerHTML += `<div class="message assistant" id="thinking">
    <div class="thinking"><div class="thinking-dots"><span></span><span></span><span></span></div>
    CyberClaw is thinking...</div></div>`;
  msgs.scrollTop = msgs.scrollHeight;

  try {
    const r = await fetch(`${API}/chat`, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ message: text, stream: false })
    });
    const data = await r.json();
    const thinking = document.getElementById('thinking');
    if (thinking) thinking.remove();
    const reply = data.reply || data.error || 'No response';
    msgs.innerHTML += `<div class="message assistant">${formatMarkdown(reply)}</div>`;
  } catch (e) {
    const thinking = document.getElementById('thinking');
    if (thinking) thinking.remove();
    msgs.innerHTML += `<div class="message assistant" style="border-color:var(--error)">Error: ${e.message}</div>`;
  }
  msgs.scrollTop = msgs.scrollHeight;
  isStreaming = false;
  document.getElementById('sendBtn').disabled = false;
}

// ── Dashboard ─────────────────────────────────────
async function loadDashboard() {
  const content = document.getElementById('contentArea');
  content.innerHTML = '<div class="empty-state"><div class="loader"></div></div>';
  try {
    const [health, metrics] = await Promise.all([
      fetch(`${API}/health`).then(r => r.json()),
      fetch(`${API}/metrics/json`).then(r => r.json()).catch(() => ({}))
    ]);
    content.innerHTML = `
      <div class="grid grid-4" style="margin-bottom:24px">
        <div class="card stat-card"><div class="stat-value">${health.providers?.length || 0}</div>
          <div class="stat-label">Active Providers</div></div>
        <div class="card stat-card"><div class="stat-value">${health.sessions || 0}</div>
          <div class="stat-label">Sessions</div></div>
        <div class="card stat-card"><div class="stat-value">${health.channels?.length || 0}</div>
          <div class="stat-label">Channels</div></div>
        <div class="card stat-card"><div class="stat-value">${Math.round(metrics.uptime_seconds/60) || 0}m</div>
          <div class="stat-label">Uptime</div></div>
      </div>
      <div class="grid grid-2">
        <div class="card"><h3>Providers</h3>
          ${(health.providers||[]).map(p => `<div style="padding:6px 0;color:var(--text-secondary)">${p}</div>`).join('')}</div>
        <div class="card"><h3>Channels</h3>
          ${(health.channels||[]).length ? health.channels.map(c => `<div style="padding:6px 0;color:var(--text-secondary)">${c}</div>`).join('') : '<div style="color:var(--text-muted)">No active channels</div>'}</div>
      </div>`;
  } catch (e) { content.innerHTML = `<div class="card">Error: ${e.message}</div>`; }
}

// ── Models ────────────────────────────────────────
async function loadModels() {
  const content = document.getElementById('contentArea');
  content.innerHTML = '<div class="empty-state"><div class="loader"></div></div>';
  try {
    // Use local catalog data
    const models = await fetch(`${API}/health`).then(r => r.json());
    content.innerHTML = `<div class="card"><h3>Model Catalog</h3>
      <p style="color:var(--text-muted);margin-bottom:16px">25 models across 6 providers with cost tracking</p>
      <div class="table-wrapper"><table>
        <tr><th>Provider</th><th>Model</th><th>Context</th><th>Vision</th><th>Reasoning</th></tr>
        <tr><td>openai</td><td>gpt-4o</td><td>128K</td><td>Yes</td><td>Yes</td></tr>
        <tr><td>openai</td><td>gpt-4o-mini</td><td>128K</td><td>Yes</td><td>-</td></tr>
        <tr><td>openai</td><td>o3-mini</td><td>200K</td><td>-</td><td>Yes</td></tr>
        <tr><td>gemini</td><td>gemini-2.5-flash</td><td>1M</td><td>Yes</td><td>Yes</td></tr>
        <tr><td>gemini</td><td>gemini-2.5-pro</td><td>1M</td><td>Yes</td><td>Yes</td></tr>
        <tr><td>anthropic</td><td>claude-sonnet-4</td><td>200K</td><td>Yes</td><td>Yes</td></tr>
        <tr><td>anthropic</td><td>claude-3.5-haiku</td><td>200K</td><td>-</td><td>-</td></tr>
        <tr><td>groq</td><td>llama-3.3-70b</td><td>128K</td><td>-</td><td>-</td></tr>
      </table></div></div>`;
    document.getElementById('modelCount').textContent = '25';
  } catch (e) { content.innerHTML = `<div class="card">Error: ${e.message}</div>`; }
}

// ── Sessions ──────────────────────────────────────
async function loadSessions() {
  const content = document.getElementById('contentArea');
  content.innerHTML = '<div class="empty-state"><div class="loader"></div></div>';
  try {
    const r = await fetch(`${API}/sessions`);
    const sessions = await r.json();
    if (!sessions.length) { content.innerHTML = '<div class="empty-state"><div class="icon">📝</div><p>No sessions yet</p></div>'; return; }
    content.innerHTML = `<div class="card"><h3>Conversation Sessions</h3>
      <div class="table-wrapper"><table>
        <tr><th>ID</th><th>Agent</th><th>Title</th><th>Messages</th><th>Updated</th></tr>
        ${sessions.map(s => `<tr><td>${s.id?.substring(0,8)||''}</td><td>${s.agent_id||''}</td>
          <td>${s.title||'Untitled'}</td><td>${s.message_count||0}</td><td>${s.updated_at?.substring(0,19)||''}</td></tr>`).join('')}
      </table></div></div>`;
  } catch (e) { content.innerHTML = `<div class="card">Error: ${e.message}</div>`; }
}

// ── Metrics ───────────────────────────────────────
async function loadMetrics() {
  const content = document.getElementById('contentArea');
  try {
    const d = await fetch(`${API}/metrics/json`).then(r => r.json());
    content.innerHTML = `
      <div class="grid grid-3" style="margin-bottom:24px">
        <div class="card stat-card"><div class="stat-value">${Math.round(d.uptime_seconds||0)}s</div>
          <div class="stat-label">Uptime</div></div>
        <div class="card stat-card"><div class="stat-value">${Object.keys(d.counters||{}).length}</div>
          <div class="stat-label">Counters</div></div>
        <div class="card stat-card"><div class="stat-value">${Object.keys(d.histograms||{}).length}</div>
          <div class="stat-label">Histograms</div></div>
      </div>
      <div class="card"><h3>Counters</h3>
        ${Object.entries(d.counters||{}).map(([k,v]) => `<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border)">
          <span style="color:var(--text-secondary)">${k}</span><span style="font-weight:600">${v}</span></div>`).join('') || '<div style="color:var(--text-muted)">No counters yet</div>'}
      </div>`;
  } catch (e) { content.innerHTML = `<div class="card">Error: ${e.message}</div>`; }
}

// ── Providers ─────────────────────────────────────
async function loadProviders() {
  const content = document.getElementById('contentArea');
  try {
    const d = await fetch(`${API}/health`).then(r => r.json());
    content.innerHTML = `<div class="card"><h3>LLM Providers</h3>
      <div class="table-wrapper"><table><tr><th>Provider</th><th>Status</th></tr>
        ${(d.providers||[]).map(p => `<tr><td>${p}</td><td><span class="badge-status available">Active</span></td></tr>`).join('')}
      </table></div></div>`;
  } catch (e) { content.innerHTML = `<div class="card">Error: ${e.message}</div>`; }
}

// ── Channels ──────────────────────────────────────
async function loadChannels() {
  const content = document.getElementById('contentArea');
  try {
    const d = await fetch(`${API}/health`).then(r => r.json());
    content.innerHTML = `<div class="card"><h3>Active Channels</h3>
      ${(d.channels||[]).length ? `<div class="table-wrapper"><table><tr><th>Channel</th><th>Status</th></tr>
        ${d.channels.map(c => `<tr><td>${c}</td><td><span class="badge-status available">Connected</span></td></tr>`).join('')}
      </table></div>` : '<div style="color:var(--text-muted);padding:20px">No channels configured. Enable channels in config.user.yaml</div>'}
    </div>`;
  } catch (e) { content.innerHTML = `<div class="card">Error: ${e.message}</div>`; }
}

// ── Tasks ─────────────────────────────────────────
async function loadTasks() {
  const content = document.getElementById('contentArea');
  content.innerHTML = `<div class="card"><h3>Background Tasks</h3>
    <div style="color:var(--text-muted);padding:20px">Task system ready. Tasks will appear here when spawned by the AI.</div></div>`;
}

// ── Helpers ───────────────────────────────────────
function escapeHtml(s) { const d=document.createElement('div'); d.textContent=s; return d.innerHTML; }
function formatMarkdown(text) {
  let html = escapeHtml(text);
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\n/g, '<br>');
  return html;
}
