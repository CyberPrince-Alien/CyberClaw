/* CyberClaw Web UI — Application Logic with Premium Transitions */

const API = window.location.origin;
let currentView = 'chat';
let sessionId = null;
let isStreaming = false;

// ── Boot ──────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  setTimeout(() => {
    const loader = document.getElementById('loadingScreen');
    if (loader) loader.classList.add('hidden');
  }, 600);
  await checkHealth();
  setInterval(checkHealth, 30000);
});

async function checkHealth() {
  try {
    const r = await fetch(`${API}/health`);
    const d = await r.json();
    const statusDot = document.getElementById('statusDot');
    if (statusDot) {
      statusDot.style.background = d.status === 'ok' ? 'var(--success)' : 'var(--error)';
      statusDot.style.boxShadow = d.status === 'ok' ? '0 0 10px rgba(16, 185, 129, 0.6)' : '0 0 10px rgba(239, 68, 68, 0.6)';
      statusDot.title = d.status === 'ok' ? 'Connected' : 'Disconnected';
    }
  } catch {
    const statusDot = document.getElementById('statusDot');
    if (statusDot) {
      statusDot.style.background = 'var(--error)';
      statusDot.style.boxShadow = '0 0 10px rgba(239, 68, 68, 0.6)';
      statusDot.title = 'Disconnected';
    }
  }
}

// ── Workspace Navigation & Transition ─────────────
function enterWorkspace(view = 'chat') {
  document.getElementById('landing-page').className = 'view-hidden';
  document.getElementById('app-workspace').className = 'view-active';
  switchView(view);
}

function exitWorkspace() {
  document.getElementById('app-workspace').className = 'view-hidden';
  document.getElementById('landing-page').className = 'view-active';
}

function toggleSidebar() {
  const sidebar = document.getElementById('sidebar');
  if (sidebar) sidebar.classList.toggle('open');
}

async function submitLandingPrompt() {
  const input = document.getElementById('landingPromptInput');
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  
  // Transition to chat workspace
  enterWorkspace('chat');
  
  // Deliver the message to the active workspace input
  setTimeout(() => {
    const chatInput = document.getElementById('chatInput');
    if (chatInput) {
      chatInput.value = text;
      sendMessage();
    }
  }, 150);
}

// ── Navigation inside Workspace ───────────────────
function switchView(view) {
  currentView = view;
  document.querySelectorAll('.nav-item').forEach(n => n.classList.toggle('active', n.dataset.view === view));
  const titles = { chat:'Chat Console', dashboard:'Dashboard Overview', models:'Model Catalog', sessions:'Conversation Sessions',
                   tasks:'Background Tasks', providers:'LLM Providers', metrics:'Metrics & Logs', channels:'Platform Channels' };
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
    <p>Start a conversation with CyberClaw. Type a message below to begin.</p></div></div>
    <div class="chat-input-area"><div class="chat-input-wrapper">
    <textarea id="chatInput" placeholder="Type your message..." rows="1"
      onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();sendMessage()}"></textarea>
    <button class="send-btn" onclick="sendMessage()" id="sendBtn">→</button>
    </div></div></div>`;
}

// ── Chat Functionality ────────────────────────────
async function sendMessage() {
  const input = document.getElementById('chatInput');
  const text = input.value.trim();
  if (!text || isStreaming) return;
  input.value = ''; isStreaming = true;
  document.getElementById('sendBtn').disabled = true;

  const msgs = document.getElementById('messages');
  if (msgs.querySelector('.empty-state')) msgs.innerHTML = '';

  // User message bubble
  msgs.innerHTML += `<div class="message user">${escapeHtml(text)}</div>`;

  // Thinking indicator bubble
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
    
    // Check key response structure in backend (usually 'response' or 'reply')
    const reply = data.response || data.reply || data.error || 'No response received from model.';
    msgs.innerHTML += `<div class="message assistant">${formatMarkdown(reply)}</div>`;
  } catch (e) {
    const thinking = document.getElementById('thinking');
    if (thinking) thinking.remove();
    msgs.innerHTML += `<div class="message assistant" style="border-color:var(--error)">Communication error: ${e.message}</div>`;
  }
  msgs.scrollTop = msgs.scrollHeight;
  isStreaming = false;
  document.getElementById('sendBtn').disabled = false;
}

// ── Dashboard Overview ────────────────────────────
async function loadDashboard() {
  const content = document.getElementById('contentArea');
  content.innerHTML = '<div class="empty-state"><div class="loader"></div></div>';
  try {
    const [health, metrics] = await Promise.all([
      fetch(`${API}/health`).then(r => r.json()),
      fetch(`${API}/metrics/json`).then(r => r.json()).catch(() => ({}))
    ]);
    content.innerHTML = `
      <div class="grid grid-4" style="margin-bottom:32px">
        <div class="card stat-card"><div class="stat-value">${health.providers?.length || 0}</div>
          <div class="stat-label">Active Providers</div></div>
        <div class="card stat-card"><div class="stat-value">${health.sessions || 0}</div>
          <div class="stat-label">Sessions</div></div>
        <div class="card stat-card"><div class="stat-value">${health.channels?.length || 0}</div>
          <div class="stat-label">Channels</div></div>
        <div class="card stat-card"><div class="stat-value">${Math.round((metrics.uptime_seconds || 0)/60)}m</div>
          <div class="stat-label">Uptime</div></div>
      </div>
      <div class="grid grid-2">
        <div class="card"><h3>Active Providers</h3>
          ${(health.providers||[]).map(p => `<div style="padding:10px 0;border-bottom:1px solid rgba(255,87,34,0.08);color:var(--text-secondary);display:flex;justify-content:between;align-items:center;">
            <span>🤖 ${p}</span><span class="badge-status available" style="transform:scale(0.85)">Active</span>
          </div>`).join('') || '<div style="color:var(--text-muted)">No active providers</div>'}</div>
        <div class="card"><h3>Platform Channels</h3>
          ${(health.channels||[]).length ? health.channels.map(c => `<div style="padding:10px 0;border-bottom:1px solid rgba(255,87,34,0.08);color:var(--text-secondary);display:flex;justify-content:between;align-items:center;">
            <span>📡 ${c}</span><span class="badge-status available" style="transform:scale(0.85)">Connected</span>
          </div>`).join('') : '<div style="color:var(--text-muted);padding:10px 0">No active channels. Configure slack/whatsapp in yaml to link.</div>'}</div>
      </div>`;
  } catch (e) { content.innerHTML = `<div class="card">Error loading dashboard: ${e.message}</div>`; }
}

// ── Models Catalog ────────────────────────────────
async function loadModels() {
  const content = document.getElementById('contentArea');
  content.innerHTML = '<div class="empty-state"><div class="loader"></div></div>';
  try {
    content.innerHTML = `<div class="card"><h3>Model Catalog</h3>
      <p style="color:var(--text-secondary);margin-bottom:20px;font-size:14px">Multi-provider model mesh with dynamic priority-based routing and automatic health checks.</p>
      <div class="table-wrapper"><table>
        <tr><th>Provider</th><th>Model ID</th><th>Context Limit</th><th>Vision Support</th><th>Failover Priority</th></tr>
        <tr><td><strong>openai</strong></td><td>gpt-4o</td><td>128K</td><td><span style="color:var(--success)">Yes</span></td><td>1 (Primary)</td></tr>
        <tr><td><strong>openai</strong></td><td>gpt-4o-mini</td><td>128K</td><td><span style="color:var(--success)">Yes</span></td><td>1 (Primary)</td></tr>
        <tr><td><strong>openai</strong></td><td>o3-mini</td><td>200K</td><td>-</td><td>1 (Primary)</td></tr>
        <tr><td><strong>gemini</strong></td><td>gemini-2.5-flash</td><td>1M</td><td><span style="color:var(--success)">Yes</span></td><td>1 (Primary)</td></tr>
        <tr><td><strong>gemini</strong></td><td>gemini-2.5-pro</td><td>1M</td><td><span style="color:var(--success)">Yes</span></td><td>1 (Primary)</td></tr>
        <tr><td><strong>anthropic</strong></td><td>claude-3.5-sonnet</td><td>200K</td><td><span style="color:var(--success)">Yes</span></td><td>2 (Backup)</td></tr>
        <tr><td><strong>groq</strong></td><td>llama-3.3-70b</td><td>128K</td><td>-</td><td>3 (Backup)</td></tr>
        <tr><td><strong>nvidia</strong></td><td>meta/llama-3.1-8b</td><td>128K</td><td>-</td><td>4 (Backup)</td></tr>
      </table></div></div>`;
    const modelBadge = document.getElementById('modelCount');
    if (modelBadge) modelBadge.textContent = '8';
  } catch (e) { content.innerHTML = `<div class="card">Error loading model catalog: ${e.message}</div>`; }
}

// ── Sessions Management ───────────────────────────
async function loadSessions() {
  const content = document.getElementById('contentArea');
  content.innerHTML = '<div class="empty-state"><div class="loader"></div></div>';
  try {
    const r = await fetch(`${API}/sessions`);
    const sessions = await r.json();
    if (!sessions.length) { 
      content.innerHTML = '<div class="empty-state"><div class="icon">📝</div><p>No active sessions found. Start a chat conversation!</p></div>'; 
      return; 
    }
    content.innerHTML = `<div class="card"><h3>Conversation Sessions</h3>
      <div class="table-wrapper"><table>
        <tr><th>Session ID</th><th>Agent ID</th><th>Display Title</th><th>Message Count</th><th>Last Active</th></tr>
        ${sessions.map(s => `<tr>
          <td><code>${s.id?.substring(0,8)||''}</code></td>
          <td><strong>${s.agent_id||'default'}</strong></td>
          <td>${s.title||'Untitled Chat'}</td>
          <td><span class="badge-status running" style="padding:2px 8px">${s.message_count||0}</span></td>
          <td>${s.updated_at?.substring(0,19).replace('T', ' ')||'Just now'}</td>
        </tr>`).join('')}
      </table></div></div>`;
  } catch (e) { content.innerHTML = `<div class="card">Error loading sessions: ${e.message}</div>`; }
}

// ── Prometheus Metrics ────────────────────────────
async function loadMetrics() {
  const content = document.getElementById('contentArea');
  content.innerHTML = '<div class="empty-state"><div class="loader"></div></div>';
  try {
    const d = await fetch(`${API}/metrics/json`).then(r => r.json());
    content.innerHTML = `
      <div class="grid grid-3" style="margin-bottom:32px">
        <div class="card stat-card"><div class="stat-value">${Math.round(d.uptime_seconds||0)}s</div>
          <div class="stat-label">System Uptime</div></div>
        <div class="card stat-card"><div class="stat-value">${Object.keys(d.counters||{}).length}</div>
          <div class="stat-label">Registered Counters</div></div>
        <div class="card stat-card"><div class="stat-value">${Object.keys(d.histograms||{}).length}</div>
          <div class="stat-label">Active Histograms</div></div>
      </div>
      <div class="card"><h3>Real-time Counter Metrics</h3>
        <div style="margin-top:10px">
        ${Object.entries(d.counters||{}).map(([k,v]) => `<div style="display:flex;justify-content:space-between;padding:12px 0;border-bottom:1px solid rgba(255,87,34,0.08)">
          <span style="color:var(--text-secondary);font-family:'JetBrains Mono',monospace;font-size:13px">${k}</span>
          <span style="font-weight:700;color:var(--accent-light)">${v}</span>
        </div>`).join('') || '<div style="color:var(--text-muted);padding:10px 0">No counter metrics recorded yet.</div>'}
        </div>
      </div>`;
  } catch (e) { content.innerHTML = `<div class="card">Error loading metrics: ${e.message}</div>`; }
}

// ── Providers Catalog ─────────────────────────────
async function loadProviders() {
  const content = document.getElementById('contentArea');
  content.innerHTML = '<div class="empty-state"><div class="loader"></div></div>';
  try {
    const d = await fetch(`${API}/health`).then(r => r.json());
    content.innerHTML = `<div class="card"><h3>Configured LLM Gateways</h3>
      <div class="table-wrapper"><table><tr><th>Provider Gateway</th><th>Status</th><th>Access Level</th></tr>
        ${(d.providers||[]).map(p => `<tr>
          <td><strong>${p}</strong></td>
          <td><span class="badge-status available">Connected</span></td>
          <td><span style="color:var(--text-secondary)">Full API Control</span></td>
        </tr>`).join('') || `<tr><td colspan="3" style="color:var(--text-muted);text-align:center">No active gateways found. Check configuration.</td></tr>`}
      </table></div></div>`;
  } catch (e) { content.innerHTML = `<div class="card">Error loading providers: ${e.message}</div>`; }
}

// ── Active Channels ───────────────────────────────
async function loadChannels() {
  const content = document.getElementById('contentArea');
  content.innerHTML = '<div class="empty-state"><div class="loader"></div></div>';
  try {
    const d = await fetch(`${API}/health`).then(r => r.json());
    content.innerHTML = `<div class="card"><h3>Platform Dispatch Channels</h3>
      <p style="color:var(--text-secondary);margin-bottom:20px;font-size:14px">External chat integration nodes allowing CyberClaw to receive and respond to user messages directly from chat platforms.</p>
      ${(d.channels||[]).length ? `<div class="table-wrapper"><table><tr><th>Integration Node</th><th>Signal Status</th></tr>
        ${d.channels.map(c => `<tr>
          <td><strong>${c} Platform</strong></td>
          <td><span class="badge-status available">Linked & Listening</span></td>
        </tr>`).join('')}
      </table></div>` : '<div style="color:var(--text-muted);padding:20px 0">No external channels are currently active. Setup <code>telegram</code>, <code>slack</code> or <code>whatsapp</code> integrations in your user config file to sync.</div>'}
    </div>`;
  } catch (e) { content.innerHTML = `<div class="card">Error loading channels: ${e.message}</div>`; }
}

// ── Task Queue Monitor ────────────────────────────
async function loadTasks() {
  const content = document.getElementById('contentArea');
  content.innerHTML = '<div class="empty-state"><div class="loader"></div></div>';
  try {
    const r = await fetch(`${API}/tasks`);
    const d = await r.json();
    const tasks = d.tasks || [];
    if (!tasks.length) {
      content.innerHTML = `<div class="card"><h3>Background Task Queue</h3>
        <div style="color:var(--text-muted);padding:30px 10px;text-align:center">
          <div style="font-size:24px;margin-bottom:12px">⚡</div>
          System is idle. No background agent tasks are currently running.
        </div></div>`;
      return;
    }
    content.innerHTML = `<div class="card"><h3>Background Task Queue</h3>
      <div class="table-wrapper"><table>
        <tr><th>Task ID</th><th>Description</th><th>Status</th><th>Runtime</th></tr>
        ${tasks.map(t => `<tr>
          <td><code>${t.id?.substring(0,8)}</code></td>
          <td>${t.description||'Agent subprocess'}</td>
          <td><span class="badge-status ${t.status === 'running' ? 'running' : 'available'}">${t.status}</span></td>
          <td>${t.runtime_seconds || 0}s</td>
        </tr>`).join('')}
      </table></div></div>`;
  } catch (e) { 
    // Fallback if endpoint tasks table doesn't exist yet
    content.innerHTML = `<div class="card"><h3>Background Task Queue</h3>
      <div style="color:var(--text-secondary);padding:20px 0;text-align:center">
        No active tasks found in history queue. Queue ready to schedule automation workflows.
      </div></div>`; 
  }
}

// ── Helpers & Parsers ─────────────────────────────
function escapeHtml(s) { const d=document.createElement('div'); d.textContent=s; return d.innerHTML; }
function formatMarkdown(text) {
  let html = escapeHtml(text);
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\n/g, '<br>');
  return html;
}
