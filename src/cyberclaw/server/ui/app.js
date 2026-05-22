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
                   tasks:'Background Tasks', providers:'Settings & Providers', metrics:'Metrics & Logs', channels:'Platform Channels' };
  document.getElementById('viewTitle').textContent = titles[view] || view;
  const content = document.getElementById('contentArea');
  
  if (view === 'chat') {
    content.innerHTML = getChatHTML();
    populateChatModelSelect();
    return;
  }
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
    <div class="chat-header-bar">
      <div class="model-select-container">
        <label for="chatModelSelect"><span class="icon">🤖</span> Active Model:</label>
        <select id="chatModelSelect" onchange="onChatModelChange()">
          <option value="">Loading models...</option>
        </select>
      </div>
      <div class="chat-actions">
        <button class="btn btn-secondary" style="padding: 6px 14px; font-size: 12px; border-radius: 8px;" onclick="clearChat()">🧹 Clear Chat</button>
      </div>
    </div>
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
        <tr><td><strong>ollama</strong></td><td>llama3</td><td>8K</td><td>-</td><td>8 (Local Backup)</td></tr>
        <tr><td><strong>ollama</strong></td><td>mistral</td><td>8K</td><td>-</td><td>8 (Local Backup)</td></tr>
        <tr><td><strong>ollama</strong></td><td>phi3</td><td>8K</td><td>-</td><td>8 (Local Backup)</td></tr>
      </table></div></div>`;
    const modelBadge = document.getElementById('modelCount');
    if (modelBadge) modelBadge.textContent = '11';
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
    const r = await fetch(`${API}/config`);
    const config = await r.json();
    window.currentConfig = config;

    const llm = config.llm || {};
    const providersList = llm.providers || [];

    let html = `
      <div class="card settings-section-card" style="margin-bottom: 24px;">
        <div class="settings-section-header">
          <h4>⚙️ Global Settings</h4>
          <p>Global LLM routing parameters, temperature control, and fallback settings.</p>
        </div>
        <form id="globalSettingsForm" onsubmit="saveGlobalSettings(event)">
          <div class="form-grid">
            <div class="form-group">
              <label class="form-label">Default LLM Provider</label>
              <select id="setting-default-provider" class="form-input">
                <option value="gemini" ${llm.default_provider === 'gemini' ? 'selected' : ''}>gemini</option>
                <option value="openai" ${llm.default_provider === 'openai' ? 'selected' : ''}>openai</option>
                <option value="groq" ${llm.default_provider === 'groq' ? 'selected' : ''}>groq</option>
                <option value="openrouter" ${llm.default_provider === 'openrouter' ? 'selected' : ''}>openrouter</option>
                <option value="nvidia" ${llm.default_provider === 'nvidia' ? 'selected' : ''}>nvidia</option>
                <option value="ollama" ${llm.default_provider === 'ollama' ? 'selected' : ''}>ollama</option>
              </select>
            </div>
            
            <div class="form-group">
              <label class="form-label">Temperature (Creativity)</label>
              <div class="range-slider-container" style="padding-top: 10px;">
                <input type="range" id="setting-temperature" min="0" max="2" step="0.1" value="${llm.temperature ?? 0.7}" oninput="document.getElementById('temp-val').textContent=this.value">
                <span class="range-value" id="temp-val">${llm.temperature ?? 0.7}</span>
              </div>
            </div>

            <div class="form-group">
              <label class="form-label">Max Token Limit</label>
              <input type="number" id="setting-max-tokens" class="form-input" value="${llm.max_tokens ?? 2048}">
            </div>

            <div class="form-group">
              <label class="form-label">Failover & Fallbacks</label>
              <div class="toggle-switch-container">
                <div class="toggle-info">
                  <span class="toggle-title">Enable Failover</span>
                  <span class="toggle-desc">Auto fallback if API error occurs</span>
                </div>
                <label class="switch">
                  <input type="checkbox" id="setting-failover" ${llm.enable_failover !== false ? 'checked' : ''}>
                  <span class="slider-toggle"></span>
                </label>
              </div>
            </div>
          </div>

          <div class="save-section">
            <button class="btn btn-primary" type="submit">Save Global Settings</button>
          </div>
        </form>
      </div>

      <div class="settings-section-header" style="margin-top: 40px; margin-bottom: 24px;">
        <h4>🔌 Configured LLM Gateways</h4>
        <p>Manage individual API keys, default models, priority weights, and active states for each provider gateway.</p>
      </div>
    `;

    const supportedProviderIds = ['gemini', 'groq', 'openai', 'openrouter', 'nvidia', 'ollama'];
    
    supportedProviderIds.forEach(pId => {
      const pConfig = providersList.find(p => p.id === pId) || {
        id: pId,
        model: pId === 'gemini' ? 'gemini-2.5-flash' : pId === 'openai' ? 'gpt-4' : pId === 'groq' ? 'llama-3.3-70b-versatile' : pId === 'openrouter' ? 'openai/gpt-4o-mini' : pId === 'nvidia' ? 'meta/llama-3.1-8b-instruct' : 'llama3',
        api_key: pId === 'ollama' ? 'ollama' : '',
        api_base: pId === 'ollama' ? 'http://localhost:11434' : '',
        priority: pId === 'ollama' ? 8 : 1,
        enabled: false
      };

      html += `
        <div class="card provider-config-box">
          <div class="provider-badge">${pId}</div>
          <form onsubmit="saveProviderSettings(event, '${pId}')">
            <div class="form-grid">
              <div class="form-group">
                <label class="form-label">API Key</label>
                <input type="password" id="key-${pId}" class="form-input" placeholder="${pConfig.api_key ? '***REDACTED***' : 'Enter API Key...'}" value="${pConfig.api_key ? '***REDACTED***' : ''}">
              </div>

              <div class="form-group">
                <label class="form-label">Active Model</label>
                <input type="text" id="model-${pId}" class="form-input" value="${pConfig.model || ''}">
              </div>

              <div class="form-group">
                <label class="form-label">API Base URL</label>
                <input type="text" id="base-${pId}" class="form-input" placeholder="${pId === 'ollama' ? 'http://localhost:11434' : 'e.g. https://api.openai.com/v1'}" value="${pConfig.api_base || ''}">
              </div>

              <div class="form-group">
                <label class="form-label">Priority Weight</label>
                <input type="number" id="priority-${pId}" class="form-input" min="1" max="100" value="${pConfig.priority ?? 1}">
              </div>

              <div class="form-group">
                <label class="form-label">Gateway Status</label>
                <div class="toggle-switch-container">
                  <div class="toggle-info">
                    <span class="toggle-title">Enable Provider</span>
                    <span class="toggle-desc">Include in circuit-breaker failover mesh</span>
                  </div>
                  <label class="switch">
                    <input type="checkbox" id="enabled-${pId}" ${pConfig.enabled ? 'checked' : ''}>
                    <span class="slider-toggle"></span>
                  </label>
                </div>
              </div>
            </div>

            <div class="save-section">
              <button class="btn btn-secondary" style="padding: 8px 18px; font-size: 13px;" type="submit">Save ${pId} Config</button>
            </div>
          </form>
        </div>
      `;
    });

    content.innerHTML = html;
  } catch (e) {
    content.innerHTML = `<div class="card">Error loading settings: ${e.message}</div>`;
  }
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

// ── Advanced Dynamic Settings & Toast Handlers ──
window.modelCatalog = null;
window.currentConfig = null;

async function populateChatModelSelect() {
  const select = document.getElementById('chatModelSelect');
  if (!select) return;

  try {
    if (!window.modelCatalog) {
      const r = await fetch(`${API}/models`);
      window.modelCatalog = await r.json();
    }
    
    const rc = await fetch(`${API}/config`);
    const config = await rc.json();
    window.currentConfig = config;

    const defaultProvider = config.llm?.default_provider || '';
    
    select.innerHTML = '';
    
    const modelList = window.modelCatalog.models || [];
    
    // Group models by provider
    const grouped = {};
    modelList.forEach(m => {
      if (!grouped[m.provider]) {
        grouped[m.provider] = [];
      }
      grouped[m.provider].push(m);
    });
    
    let optionsHtml = '';
    
    Object.entries(grouped).forEach(([providerId, models]) => {
      const activeProviderEntry = (config.llm?.providers || []).find(p => p.id === providerId);
      const activeModel = activeProviderEntry?.model || '';
      const providerEnabled = activeProviderEntry ? activeProviderEntry.enabled === true : false;
      const providerLabel = providerEnabled ? providerId : `${providerId} (Disabled)`;

      models.forEach(m => {
        const value = `${providerId}:${m.model}`;
        const isDefault = (providerId === defaultProvider && m.model === activeModel);
        const selectedAttr = isDefault ? 'selected' : '';
        optionsHtml += `<option value="${value}" ${selectedAttr}>${providerLabel} - ${m.label || m.model}</option>`;
      });
    });
    
    select.innerHTML = optionsHtml;
  } catch (e) {
    select.innerHTML = `<option value="">Error loading models</option>`;
    console.error("Error populating models:", e);
  }
}

async function onChatModelChange() {
  const select = document.getElementById('chatModelSelect');
  if (!select) return;
  
  const val = select.value;
  if (!val) return;
  
  const [providerId, modelId] = val.split(':');
  showToast(`Switching active model to ${modelId}...`, 'info');
  
  try {
    const r = await fetch(`${API}/config/update_provider`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        provider_id: providerId,
        model: modelId,
        enabled: true,
        is_default: true
      })
    });
    
    const d = await r.json();
    if (d.status === 'ok') {
      showToast(`Model successfully switched to ${modelId}!`, 'success');
      const rc = await fetch(`${API}/config`);
      window.currentConfig = await rc.json();
    } else {
      showToast(`Failed to switch model: ${d.error || 'Unknown error'}`, 'error');
    }
  } catch (e) {
    showToast(`Error switching model: ${e.message}`, 'error');
  }
}

function clearChat() {
  const msgs = document.getElementById('messages');
  if (msgs) {
    msgs.innerHTML = `<div class="empty-state"><div class="icon">🤖</div>
    <p>Start a conversation with CyberClaw. Type a message below to begin.</p></div>`;
    showToast('Chat history cleared.', 'success');
  }
}

async function saveGlobalSettings(e) {
  e.preventDefault();
  const defaultProvider = document.getElementById('setting-default-provider').value;
  const temperature = parseFloat(document.getElementById('setting-temperature').value);
  const maxTokens = parseInt(document.getElementById('setting-max-tokens').value);
  const failover = document.getElementById('setting-failover').checked;

  showToast('Saving global settings...', 'info');

  try {
    await Promise.all([
      fetch(`${API}/config/set`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: 'llm.default_provider', value: defaultProvider })
      }),
      fetch(`${API}/config/set`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: 'llm.temperature', value: temperature.toString() })
      }),
      fetch(`${API}/config/set`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: 'llm.max_tokens', value: maxTokens.toString() })
      }),
      fetch(`${API}/config/set`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: 'llm.enable_failover', value: failover.toString() })
      })
    ]);

    showToast('Global settings saved successfully!', 'success');
  } catch (err) {
    showToast(`Error saving global settings: ${err.message}`, 'error');
  }
}

async function saveProviderSettings(e, providerId) {
  e.preventDefault();
  const apiKey = document.getElementById(`key-${providerId}`).value.trim();
  const model = document.getElementById(`model-${providerId}`).value.trim();
  const apiBase = document.getElementById(`base-${providerId}`).value.trim();
  const priority = parseInt(document.getElementById(`priority-${providerId}`).value);
  const enabled = document.getElementById(`enabled-${providerId}`).checked;

  showToast(`Saving ${providerId} settings...`, 'info');

  try {
    const body = {
      provider_id: providerId,
      model: model,
      api_base: apiBase,
      priority: priority,
      enabled: enabled
    };
    
    if (apiKey && apiKey !== '***REDACTED***') {
      body.api_key = apiKey;
    }

    const r = await fetch(`${API}/config/update_provider`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });

    const d = await r.json();
    if (d.status === 'ok') {
      showToast(`${providerId} configuration saved successfully!`, 'success');
    } else {
      showToast(`Error saving provider: ${d.error || 'Unknown error'}`, 'error');
    }
  } catch (err) {
    showToast(`Error saving provider settings: ${err.message}`, 'error');
  }
}

function showToast(message, type = 'success') {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  
  const icon = type === 'success' ? '✅' : type === 'error' ? '❌' : 'ℹ️';
  toast.innerHTML = `<span class="toast-icon">${icon}</span><span class="toast-message">${message}</span>`;
  
  container.appendChild(toast);
  
  requestAnimationFrame(() => {
    toast.classList.add('show');
  });

  setTimeout(() => {
    toast.classList.remove('show');
    toast.addEventListener('transitionend', () => {
      toast.remove();
    });
  }, 4000);
}
