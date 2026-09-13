const API_BASE = window.location.origin;
let WS_URL = '';
if (window.location.protocol === 'https:') {
  WS_URL = `wss://${window.location.host}/ws`;
} else {
  WS_URL = `ws://${window.location.host}/ws`;
}

let socket = null;
let currentTaskId = null;
let reconnectTimer = null;

const messagesEl = document.getElementById('messages');
const chatInput = document.getElementById('chat-input');
const sendBtn = document.getElementById('send-btn');
const attachBtn = document.getElementById('attach-btn');
const chatFileInput = document.getElementById('chat-file-input');
const fileChipsEl = document.getElementById('file-chips');
const statusBadge = document.getElementById('status-badge');
const connectionDot = document.querySelector('#connection-indicator .dot');
const connectionText = document.querySelector('#connection-indicator');
const workflowSteps = document.querySelectorAll('.step');
const taskIdEl = document.getElementById('task-id');
const taskStatusEl = document.getElementById('task-status');
const taskWorkspaceEl = document.getElementById('task-workspace');
const chatTaskEl = document.getElementById('chat-task');
const fileListEl = document.getElementById('file-list');
const logListEl = document.getElementById('log-list');
const testOutputEl = document.getElementById('test-output');
const ragFileInput = document.getElementById('rag-file-input');
const ragUploadBtn = document.getElementById('rag-upload-btn');
const ragIndexBtn = document.getElementById('rag-index-btn');
const ragStatusEl = document.getElementById('rag-status');
const ragFileListEl = document.getElementById('rag-file-list');
const projectListEl = document.getElementById('project-list');
const projectDetailEl = document.getElementById('project-detail');
const projectBackBtn = document.getElementById('project-back-btn');
const projectDetailTitleEl = document.getElementById('project-detail-title');
const projectDetailRequestEl = document.getElementById('project-detail-request');
const projectDetailFilesEl = document.getElementById('project-detail-files');
const projectDetailContentEl = document.getElementById('project-detail-content');
const projectDetailMemoryEl = document.getElementById('project-detail-memory');
const projectDetailToolsEl = document.getElementById('project-detail-tools');
let edaTools = [];

function switchView(view) {
  document.querySelectorAll('.page').forEach((v) => v.classList.remove('active'));
  const target = document.getElementById(`page-${view}`);
  if (target) target.classList.add('active');
  document.querySelectorAll('.nav-item').forEach((b) => {
    b.classList.toggle('active', b.dataset.view === view);
  });
  if (view === 'rag') loadRagFiles();
  if (view === 'projects') loadProjects();
}

document.querySelectorAll('.nav-item').forEach((btn) => {
  btn.addEventListener('click', () => switchView(btn.dataset.view));
});

function connect() {
  if (socket && socket.readyState === WebSocket.OPEN) return;

  try {
    socket = new WebSocket(WS_URL);
  } catch (e) {
    setOffline();
    scheduleReconnect();
    return;
  }

  socket.onopen = () => {
    setOnline();
    clearTimeout(reconnectTimer);
    addSystemMessage('Connected to server');
    fetchTaskList();
  };

  socket.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      handleServerMessage(msg);
    } catch (e) {
      console.warn('Invalid message:', event.data);
    }
  };

  socket.onerror = () => {
    setOffline();
  };

  socket.onclose = () => {
    setOffline();
    addSystemMessage('Connection lost — retrying...');
    scheduleReconnect();
  };
}

function scheduleReconnect() {
  clearTimeout(reconnectTimer);
  reconnectTimer = setTimeout(connect, 3000);
}

function setOnline() {
  connectionDot.className = 'dot online';
  connectionText.innerHTML = '<span class="dot online"></span> Connected';
}

function setOffline() {
  connectionDot.className = 'dot offline';
  connectionText.innerHTML = '<span class="dot offline"></span> Disconnected';
}

function sendWS(data) {
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify(data));
  } else {
    addSystemMessage('Cannot send — not connected');
  }
}

function handleServerMessage(msg) {
  const eventType = msg.event_type || msg.type;
  const payload = msg.payload || msg.data || {};
  const message = payload.message || payload.status || '';
  const agent = payload.agent || 'Supervisor';

  switch (eventType) {
    case 'TASK_CREATED':
      currentTaskId = msg.task_id || payload.task_id;
      taskIdEl.textContent = currentTaskId || '—';
      chatTaskEl.textContent = currentTaskId || '—';
      setBadge('active', 'Active');
      addSystemMessage(`Task created: ${currentTaskId}`);
      updateWorkflow(eventType);
      break;

    case 'STATE_CHANGED':
      updateWorkflow(payload.to);
      taskStatusEl.textContent = payload.to;
      setBadgeFromStatus(payload.to);
      break;

    case 'ANALYSIS_STARTED':
    case 'ANALYSIS_FINISHED':
    case 'RAG_STARTED':
    case 'RAG_FINISHED':
    case 'ARTIFACT_GENERATION_STARTED':
    case 'ARTIFACT_GENERATION_FINISHED':
    case 'FILES_CREATED':
    case 'WORKSPACE_READY':
    case 'AGENT_STARTED':
    case 'AGENT_FINISHED':
    case 'VALIDATION_STARTED':
    case 'VALIDATION_FINISHED':
    case 'TEST_STARTED':
    case 'TEST_PASSED':
    case 'SYNTHESIS_STARTED':
    case 'SYNTHESIS_FINISHED':
    case 'FLASH_STARTED':
    case 'FLASH_FINISHED':
    case 'ARCHITECTURE_CREATED':
    case 'ARCHITECTURE_FAILED':
    case 'IMPLEMENTATION_STARTED':
    case 'IMPLEMENTATION_COMPLETED':
    case 'IMPLEMENTATION_FAILED':
    case 'STATIC_CHECK_STARTED':
    case 'STATIC_CHECK_PASSED':
    case 'STATIC_CHECK_FAILED':
    case 'SIMULATION_STARTED':
    case 'SIMULATION_PASSED':
    case 'SIMULATION_FAILED':
    case 'DEBUG_STARTED':
    case 'DEBUG_COMPLETED':
    case 'REPAIR_ASSIGNED':
    case 'REPAIR_COMPLETED':
    case 'REPAIR_FAILED':
    case 'NO_PROGRESS':
    case 'IDENTICAL_ERROR':
      addLogEntry('info', eventType + (message ? ': ' + message : ''));
      if (eventType === 'AGENT_FINISHED' && (payload.stdout || payload.stderr)) {
        addAgentMessageWithLabel(agent, formatAgentOutput(payload));
      } else {
        addAgentMessageWithLabel(agent, message || formatEventPayload(eventType, payload));
      }
      break;

    case 'OPENCODE_STARTED':
      addLogEntry('info', `${agent}: OpenCode gestartet`);
      addAgentMessageWithLabel(agent, 'OpenCode gestartet' + (payload.module ? ` für ${payload.module}` : ''));
      break;

    case 'OPENCODE_COMPLETED':
      addLogEntry('info', `${agent}: OpenCode abgeschlossen`);
      addAgentMessageWithLabel(agent, formatAgentOutput(payload, 'OpenCode abgeschlossen'));
      break;

    case 'OPENCODE_FAILED':
      addLogEntry('error', `${agent}: OpenCode fehlgeschlagen`);
      addAgentMessageWithLabel(agent, formatAgentOutput(payload, 'OpenCode fehlgeschlagen'));
      break;

    case 'TEST_FAILED':
    case 'REPAIR_STARTED':
      addLogEntry('event', eventType + (message ? ': ' + message : ''));
      addAgentMessageWithLabel(agent, `Event: ${eventType} — ${message || ''}`);
      if (payload.stderr) {
        testOutputEl.textContent += `\n[ERROR] ${payload.stderr.substring(0, 500)}`;
      }
      break;

    case 'REPAIR_FINISHED':
      addLogEntry('event', eventType + (message ? ': ' + message : ''));
      break;

    case 'APPROVAL_REQUESTED':
      handleApprovalRequested(payload);
      break;

    case 'APPROVAL_GRANTED':
      addLogEntry('info', 'User approved bitstream for flashing');
      addAgentMessage('User approved. Starting flash...');
      break;

    case 'APPROVAL_REJECTED':
      addLogEntry('warning', 'User rejected bitstream: ' + (payload.feedback || 'No feedback'));
      addAgentMessage('User rejected: ' + (payload.feedback || 'No feedback provided'));
      break;

    case 'TASK_COMPLETED':
      updateWorkflow('COMPLETED');
      taskStatusEl.textContent = 'COMPLETED';
      setBadge('active', 'Completed');
      addLogEntry('done', 'Task completed successfully');
      addAgentMessage('Task completed successfully');
      if (payload.files) updateFiles(payload);
      if (payload.workspace) taskWorkspaceEl.textContent = payload.workspace;
      break;

    case 'TASK_FAILED':
      updateWorkflow('FAILED');
      taskStatusEl.textContent = 'FAILED';
      setBadge('error', 'Failed');
      addLogEntry('error', payload.error || 'Task failed');
      addAgentMessage(`Task failed: ${payload.error || ''}`);
      break;

    case 'CHAT_RESPONSE':
      if (payload.type === 'error') {
        addAgentMessage(payload.answer || payload.error || 'Fehler');
        setBadge('error', 'Failed');
      } else if (payload.type === 'question' || payload.answer) {
        if (payload.project_id) {
          currentTaskId = payload.project_id;
          taskIdEl.textContent = payload.project_id;
          chatTaskEl.textContent = payload.project_id;
        }
        addAgentMessage(payload.answer || '');
        setBadge('', 'Idle');
      } else if (payload.status === 'QUEUED') {
        if (payload.type === 'resume') {
          addSystemMessage(`Fortsetzung des Projekts: ${payload.task_id || payload.project_id || ''}`);
        } else {
          addSystemMessage('Neues Projekt wird erstellt...');
        }
        if (payload.task_id) {
          currentTaskId = payload.task_id;
          taskIdEl.textContent = payload.task_id;
          taskStatusEl.textContent = 'QUEUED';
          chatTaskEl.textContent = payload.task_id;
          setBadge('active', 'Queued');
        }
      } else {
        if (payload.type === 'resume') {
          addSystemMessage(`Fortsetzung des Projekts: ${payload.task_id || payload.project_id || ''}`);
        }
        if (payload.task_id) {
          currentTaskId = payload.task_id;
          taskIdEl.textContent = payload.task_id;
          taskStatusEl.textContent = payload.status;
          chatTaskEl.textContent = payload.task_id;
          setBadgeFromStatus(payload.status);
          updateWorkflow(payload.status);
        }
      }
      break;

    default:
      if (eventType && eventType.startsWith('LOG_')) {
        addLogEntry('info', message);
      }
  }
}

function handleApprovalRequested(payload) {
  const bitstreamPath = payload.bitstream_path || 'unknown';
  const vhdlCode = payload.vhdl_code || '';
  const flashError = payload.flash_error || '';
  
  updateWorkflow('AWAITING_APPROVAL');
  taskStatusEl.textContent = 'AWAITING_APPROVAL';
  setBadge('warning', 'Awaiting Approval');
  
  let msg = `Bitstream bereit zum Flashen: ${bitstreamPath}`;
  if (flashError) {
    msg += `\n\n⚠️ Vorheriger Flash-Versuch fehlgeschlagen: ${flashError}`;
    msg += `\nBitte Board-Verbindung prüfen und erneut versuchen.`;
  }
  addLogEntry('warning', msg);
  addAgentMessage(msg);
  
  // Freigabe-UI anzeigen (Button im Chat-Bereich)
  showApprovalButtons(payload);
}

function showApprovalButtons(payload) {
  const bitstreamPath = payload.bitstream_path || '';
  const vhdlCode = payload.vhdl_code || '';
  
  // Entferne evtl. vorhandene Freigabe-Buttons
  const existing = document.getElementById('approval-buttons');
  if (existing) existing.remove();
  
  const btnContainer = document.createElement('div');
  btnContainer.id = 'approval-buttons';
  btnContainer.style.cssText = 'margin-top: 10px; padding: 10px; background: #fff3cd; border: 1px solid #ffc107; border-radius: 4px;';
  
  const info = document.createElement('div');
  info.style.cssText = 'margin-bottom: 10px; font-size: 0.9em;';
  info.innerHTML = `<strong>Bitstream:</strong> ${escapeHtml(bitstreamPath)}`;
  btnContainer.appendChild(info);
  
  if (vhdlCode) {
    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'btn-small';
    toggle.textContent = 'VHDL-Code anzeigen';
    toggle.onclick = () => showVhdlModal(vhdlCode);
    btnContainer.appendChild(toggle);
  }
  
  const btnRow = document.createElement('div');
  btnRow.style.cssText = 'display: flex; gap: 10px; margin-top: 10px;';
  
  const approveBtn = document.createElement('button');
  approveBtn.type = 'button';
  approveBtn.className = 'btn';
  approveBtn.style.background = '#28a745';
  approveBtn.textContent = '✓ Freigeben & Flashen';
  approveBtn.onclick = () => sendApproval(true, '');
  btnRow.appendChild(approveBtn);
  
  const rejectBtn = document.createElement('button');
  rejectBtn.type = 'button';
  rejectBtn.className = 'btn danger';
  rejectBtn.textContent = '✕ Ablehnen (Reparatur)';
  rejectBtn.onclick = () => {
    const feedback = prompt('Feedback für Reparatur (optional):');
    if (feedback !== null) sendApproval(false, feedback);
  };
  btnRow.appendChild(rejectBtn);
  
  btnContainer.appendChild(btnRow);
  messagesEl.appendChild(btnContainer);
  scrollChat();
}

function sendApproval(approve, feedback) {
  if (!currentTaskId) return;
  
  const endpoint = approve ? '/api/projects/' + currentTaskId + '/approve' 
                           : '/api/projects/' + currentTaskId + '/reject';
  
  fetch(`${API_BASE}${endpoint}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ feedback }),
  }).then(res => res.json()).then(data => {
    if (data.error) {
      addAgentMessage(`Fehler: ${data.error}`);
    } else {
      const btnContainer = document.getElementById('approval-buttons');
      if (btnContainer) btnContainer.remove();
      addSystemMessage(approve ? 'Freigabe gesendet — Flash wird gestartet' : 'Abgelehnt — Reparatur wird angestoßen');
    }
  }).catch(e => {
    addAgentMessage(`Fehler bei Freigabe: ${e}`);
  });
}

function showVhdlModal(code) {
  // Einfaches Modal für VHDL-Code
  const modal = document.createElement('div');
  modal.style.cssText = 'position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); z-index: 1000; display: flex; align-items: center; justify-content: center;';
  modal.innerHTML = `
    <div style="background: #1e1e1e; color: #d4d4d4; width: 80%; height: 80%; border-radius: 8px; padding: 20px; overflow: auto; font-family: monospace; font-size: 13px; position: relative;">
      <div style="position: absolute; top: 10px; right: 15px; cursor: pointer; font-size: 24px;">&times;</div>
      <pre style="white-space: pre-wrap; word-wrap: break-word;">${escapeHtml(code)}</pre>
    </div>
  `;
  modal.querySelector('div').onclick = (e) => e.stopPropagation();
  modal.onclick = () => modal.remove();
  document.body.appendChild(modal);
}

async function fetchTaskList() {
  try {
    const res = await fetch(`${API_BASE}/api/tasks`);
    if (!res.ok) return;
    const tasks = await res.json();
    const completed = tasks.completed || [];
    if (completed.length > 0) {
      const latest = completed[completed.length - 1];
      currentTaskId = latest.task_id;
      taskIdEl.textContent = latest.task_id;
      chatTaskEl.textContent = latest.task_id;
      taskStatusEl.textContent = latest.status;
      setBadgeFromStatus(latest.status);
      updateWorkflow(latest.status);
      if (latest.generated_files?.length) {
        renderFiles(latest.generated_files);
      }
    }
  } catch (e) {
  }
}

async function sendTask(request, files) {
  setBadge('active', 'Processing');
  sendBtn.disabled = true;

  try {
    let res;
    if (files && files.length) {
      const fd = new FormData();
      for (const f of files) fd.append('files', f);
      fd.append('user_request', request);
      fd.append('domain', 'vhdl');
      if (currentTaskId) fd.append('current_project', currentTaskId);
      res = await fetch(`${API_BASE}/api/chat/upload`, {
        method: 'POST',
        body: fd,
      });
    } else {
      res = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_request: request,
          domain: 'vhdl',
          current_project: currentTaskId || null,
        }),
      });
    }
    const result = await res.json();
    if (result.error) {
      addAgentMessage(`Fehler: ${result.error}`);
      setBadge('error', 'Failed');
      return;
    }
    if (result.type === 'question' || result.answer) {
      currentTaskId = result.project_id || currentTaskId;
      if (result.project_id) {
        taskIdEl.textContent = result.project_id;
        chatTaskEl.textContent = result.project_id;
      }
      addAgentMessage(result.answer || result.message || '');
      setBadge('', 'Idle');
      return;
    }
    if (result.status === 'QUEUED') {
      if (result.type === 'resume') {
        addSystemMessage(`Fortsetzung des Projekts: ${result.task_id || result.project_id || ''}`);
      } else {
        addSystemMessage('Neues Projekt wird erstellt...');
      }
    }
    if (result.task_id) {
      currentTaskId = result.task_id;
      taskIdEl.textContent = result.task_id;
      taskStatusEl.textContent = result.status;
      chatTaskEl.textContent = result.task_id;
    }
  } catch (e) {
    if (files && files.length) {
      addAgentMessage(`Fehler beim Hochladen: ${e}`);
      setBadge('error', 'Failed');
    } else {
      sendWS({ action: 'chat', request, current_project: currentTaskId || null });
      addSystemMessage('Sent task via WebSocket');
    }
  } finally {
    sendBtn.disabled = false;
  }
}

function updateWorkflow(activeStatus) {
  let found = false;
  workflowSteps.forEach((step) => {
    const s = step.dataset.step;
    if (s === activeStatus) {
      step.className = 'step active';
      found = true;
    } else if (!found && s !== 'FAILED') {
      step.className = 'step done';
    } else {
      step.className = 'step';
      if (activeStatus === 'FAILED' && s === 'FAILED') {
        step.className = 'step failed';
      }
    }
  });
}

function setBadge(cls, text) {
  statusBadge.className = `badge ${cls}`;
  statusBadge.textContent = text;
}

function setBadgeFromStatus(status) {
  if (status === 'COMPLETED') setBadge('active', 'Completed');
  else if (status === 'FLASHED') setBadge('active', 'Flashed');
  else if (status === 'AWAITING_APPROVAL') setBadge('warning', 'Awaiting Approval');
  else if (status === 'FLASHING') setBadge('active', 'Flashing');
  else if (status === 'SYNTHESIZING') setBadge('active', 'Synthesizing');
  else if (['ANALYZING','RAG_SEARCH','GENERATING_ARTIFACTS','WORKSPACE_READY','RUNNING_AGENT','TESTING','REPAIRING','VALIDATING'].includes(status))
    setBadge('active', status);
  else setBadge('', 'Idle');
}

function addUserMessage(text) {
  const el = document.createElement('div');
  el.className = 'message user';
  el.innerHTML = `<div class="msg-label">User</div><div class="msg-text">${escapeHtml(text)}</div><span class="timestamp">${now()}</span>`;
  messagesEl.appendChild(el);
  scrollChat();
}

function addAgentMessage(text) {
  addAgentMessageWithLabel('AI Engineer', text);
}

function addAgentMessageWithLabel(agent, text) {
  const el = document.createElement('div');
  el.className = 'message agent';
  el.innerHTML = `<div class="msg-label">${escapeHtml(agent)}</div><div class="msg-text">${escapeHtml(text)}</div><span class="timestamp">${now()}</span>`;
  messagesEl.appendChild(el);
  scrollChat();
}

function formatAgentOutput(payload, prefix = '') {
  const parts = [];
  if (prefix) parts.push(prefix);
  if (payload.stdout) parts.push(`Ausgabe:\n${payload.stdout}`);
  if (payload.stderr) parts.push(`Fehlerausgabe:\n${payload.stderr}`);
  if (payload.error && !payload.stderr) parts.push(`Fehler:\n${payload.error}`);
  return parts.join('\n\n') || prefix || 'Keine Ausgabe';
}

function formatEventPayload(eventType, payload) {
  const details = [];
  if (payload.module) details.push(`Modul: ${payload.module}`);
  if (payload.stage) details.push(`Phase: ${payload.stage}`);
  if (payload.failures?.length) details.push(`Fehler: ${payload.failures.join('\n')}`);
  if (payload.error) details.push(`Fehler: ${payload.error}`);
  if (payload.diagnosis) details.push(`Diagnose: ${JSON.stringify(payload.diagnosis, null, 2)}`);
  return details.length ? `${eventType}\n${details.join('\n')}` : `Event: ${eventType}`;
}

function addSystemMessage(text) {
  const el = document.createElement('div');
  el.className = 'message system';
  el.textContent = `— ${text} —`;
  messagesEl.appendChild(el);
  scrollChat();
}

function scrollChat() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function addLogEntry(type, message) {
  const el = document.createElement('div');
  el.className = 'log-entry';
  el.innerHTML = `<span class="log-time">${now()}</span> [<span class="log-type ${type === 'error' ? 'error' : type === 'done' ? 'done' : type === 'event' ? 'event' : 'info'}">${type}</span>] ${escapeHtml(message)}`;
  logListEl.appendChild(el);
  logListEl.scrollTop = logListEl.scrollHeight;
}

function renderFiles(files) {
  fileListEl.innerHTML = '';
  files.forEach((f) => {
    const li = document.createElement('li');
    li.textContent = f;
    li.title = 'Click to view (future)';
    fileListEl.appendChild(li);
  });
}

function updateFiles(data) {
  const files = data.files || data.generated_files || [];
  if (files.length) {
    renderFiles(files);
  }
}

function now() {
  return new Date().toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function escapeHtml(str) {
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}

function handleSend() {
  const text = chatInput.value.trim();
  const files = selectedFiles.slice();
  if (!text && !files.length) return;

  const fileNote = files.length
    ? `\n\n📎 Angehängte Dateien: ${files.map((f) => f.name).join(', ')}`
    : '';
  addUserMessage(text + fileNote);
  chatInput.value = '';

  selectedFiles = [];
  renderFileChips();

  sendTask(text, files);
}

sendBtn.addEventListener('click', handleSend);
chatInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    handleSend();
  }
});

// ── Datei-Upload ──
let selectedFiles = [];

attachBtn.addEventListener('click', () => chatFileInput.click());

chatFileInput.addEventListener('change', () => {
  for (const f of chatFileInput.files) {
    if (selectedFiles.some((s) => s.name === f.name && s.size === f.size)) continue;
    selectedFiles.push(f);
  }
  chatFileInput.value = '';
  renderFileChips();
});

function renderFileChips() {
  fileChipsEl.innerHTML = '';
  selectedFiles.forEach((f, i) => {
    const chip = document.createElement('span');
    chip.className = 'file-chip';
    chip.title = f.name;
    chip.appendChild(document.createTextNode(`${f.name} (${formatBytes(f.size)})`));

    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'chip-remove';
    remove.textContent = '✕';
    remove.title = 'Entfernen';
    remove.addEventListener('click', () => {
      selectedFiles.splice(i, 1);
      renderFileChips();
    });
    chip.appendChild(remove);
    fileChipsEl.appendChild(chip);
  });
}

// ── RAG View ──
function setRagStatus(message, type) {
  ragStatusEl.textContent = message;
  ragStatusEl.className = `rag-status ${type || ''}`;
}

async function loadRagFiles() {
  try {
    const res = await fetch(`${API_BASE}/api/rag/files`);
    const data = await res.json();
    renderRagFiles(data.files || []);
  } catch (e) {
    ragFileListEl.innerHTML = '<li class="empty">Dateiliste nicht verfügbar</li>';
  }
}

function renderRagFiles(files) {
  ragFileListEl.innerHTML = '';
  if (!files.length) {
    ragFileListEl.innerHTML = '<li class="empty">Noch keine Dateien hinterlegt</li>';
    return;
  }
  files.forEach((f) => {
    const li = document.createElement('li');
    li.textContent = `${f.name} (${formatBytes(f.size)})`;
    li.title = `Geändert: ${f.modified || '?'}`;
    ragFileListEl.appendChild(li);
  });
}

async function uploadRagFiles() {
  if (!ragFileInput.files.length) {
    setRagStatus('Bitte zuerst Dateien auswählen', 'error');
    return;
  }
  const fd = new FormData();
  for (const file of ragFileInput.files) fd.append('files', file);
  ragUploadBtn.disabled = true;
  setRagStatus('Lade Dateien hoch...', 'info');
  try {
    const res = await fetch(`${API_BASE}/api/rag/upload`, { method: 'POST', body: fd });
    const data = await res.json();
    const names = (data.savedFiles || []).join(', ');
    setRagStatus(`Hochgeladen: ${names}`, 'done');
    ragFileInput.value = '';
    loadRagFiles();
  } catch (e) {
    setRagStatus('Upload fehlgeschlagen', 'error');
  } finally {
    ragUploadBtn.disabled = false;
  }
}

async function indexRagData() {
  ragIndexBtn.disabled = true;
  setRagStatus('Indexiere Wissen...', 'info');
  try {
    const res = await fetch(`${API_BASE}/api/rag/index`, { method: 'POST' });
    const data = await res.json();
    setRagStatus(`Indexiert: ${data.indexed_chunks} Chunks aus ${data.data_dir}`, 'done');
  } catch (e) {
    setRagStatus('Indexierung fehlgeschlagen', 'error');
  } finally {
    ragIndexBtn.disabled = false;
  }
}

ragUploadBtn.addEventListener('click', uploadRagFiles);
ragIndexBtn.addEventListener('click', indexRagData);

// ── Projekte View ──
async function loadEdaTools() {
  // Alle Tools laden (nicht nur installierte), damit der ModelSim-Button
  // bei jedem Projekt sichtbar ist; nicht installierte Tools werden
  // deaktiviert angezeigt.
  try {
    const res = await fetch(`${API_BASE}/api/eda-tools`);
    const data = await res.json();
    edaTools = data.tools || [];
  } catch (e) {
    edaTools = [];
  }
}

function toolButton(t, projectName) {
  const installed = !!t.installed;
  const binary = t.binary || '';
  const title = installed
    ? `Projekt in ${escapeHtml(t.name)} öffnen`
    : `${escapeHtml(t.name)} (${escapeHtml(binary)}) ist nicht installiert`;
  if (projectName) {
    const btn = document.createElement('button');
    btn.className = `btn-small tool-btn${installed ? '' : ' disabled'}`;
    btn.textContent = t.name;
    btn.title = title;
    if (!installed) btn.disabled = true;
    btn.addEventListener('click', () => openProjectInTool(projectName, t.id));
    return btn;
  }
  return `<button class="btn-small tool-btn${installed ? '' : ' disabled'}" data-tool="${t.id}" title="${title}"${installed ? '' : ' disabled'}>${escapeHtml(t.name)}</button>`;
}

async function loadProjects() {
  await loadEdaTools();
  try {
    const res = await fetch(`${API_BASE}/api/projects`);
    const data = await res.json();
    renderProjects(data.projects || []);
  } catch (e) {
    projectListEl.innerHTML = '<li class="empty">Projektliste nicht verfügbar</li>';
  }
}

function renderProjects(projects) {
  projectListEl.innerHTML = '';
  if (!projects.length) {
    projectListEl.innerHTML = '<li class="empty">Noch keine Projekte vorhanden</li>';
    return;
  }
  projects.forEach((p) => {
    const li = document.createElement('li');
    li.className = 'project-item';
    const status = p.status || 'UNKNOWN';
    const filesCount = (p.generated_files || []).length;
    const toolsRow = edaTools.length
      ? `<div class="project-tools">${edaTools
          .map((t) => toolButton(t))
          .join('')}</div>`
      : '';
    li.innerHTML = `
      <div class="project-head">
        <span class="project-name">${escapeHtml(p.name)}</span>
        <span class="project-status ${statusClass(status)}">${escapeHtml(status)}</span>
      </div>
      <div class="project-request">${escapeHtml(p.request || '')}</div>
      <div class="project-meta">${formatDate(p.created_at)} · ${filesCount} Datei(en)</div>
      <div class="project-actions">
        <button class="btn-small" data-action="load">In Chat laden</button>
        <button class="btn-small" data-action="details">Details</button>
        <button class="btn-small danger" data-action="delete">Löschen</button>
      </div>
      ${toolsRow}`;
    li.querySelector('[data-action="load"]').addEventListener('click', () => loadProjectIntoChat(p));
    li.querySelector('[data-action="details"]').addEventListener('click', () => showProjectDetails(p.name));
    li.querySelector('[data-action="delete"]').addEventListener('click', () => deleteProject(p));
    li.querySelectorAll('[data-tool]').forEach((btn) => {
      btn.addEventListener('click', () => openProjectInTool(p.name, btn.dataset.tool));
    });
    projectListEl.appendChild(li);
  });
}

async function openProjectInTool(name, tool) {
  try {
    const res = await fetch(`${API_BASE}/api/projects/${encodeURIComponent(name)}/open-tool`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tool }),
    });
    const data = await res.json();
    if (data.error) {
      alert(`Fehler: ${data.error}`);
      return;
    }
    alert(data.message || 'Tool wurde gestartet');
  } catch (e) {
    alert(`Fehler: ${e}`);
  }
}

async function deleteProject(p) {
  const name = p.name || p.task_id || '';
  if (!name) return;
  const confirmed = confirm(`Projekt "${name}" wirklich löschen? Diese Aktion kann nicht rückgängig gemacht werden.`);
  if (!confirmed) return;

  try {
    const res = await fetch(`${API_BASE}/api/projects/${encodeURIComponent(name)}`, { method: 'DELETE' });
    const data = await res.json();
    if (data.error) {
      alert(`Löschen fehlgeschlagen: ${data.error}`);
      return;
    }
    if (currentTaskId === name || currentTaskId === p.task_id) {
      currentTaskId = null;
      taskIdEl.textContent = '—';
      taskStatusEl.textContent = '—';
      chatTaskEl.textContent = '—';
    }
    addSystemMessage(`Projekt "${name}" gelöscht`);
    loadProjects();
  } catch (e) {
    alert(`Löschen fehlgeschlagen: ${e}`);
  }
}

function loadProjectIntoChat(p) {
  currentTaskId = p.task_id || p.name;
  taskIdEl.textContent = currentTaskId;
  taskStatusEl.textContent = p.status || 'UNKNOWN';
  chatTaskEl.textContent = currentTaskId;
  setBadgeFromStatus(p.status);
  updateWorkflow(p.status);
  taskWorkspaceEl.textContent = p.workspace || `projects/${p.name}`;
  if (p.generated_files && p.generated_files.length) {
    renderFiles(p.generated_files);
  }
  addSystemMessage(`Projekt "${p.name}" geladen`);
  if (p.request) addAgentMessage(`Anfrage: ${p.request}`);
  switchView('ai-engineer');
}

async function showProjectDetails(name) {
  try {
    const res = await fetch(`${API_BASE}/api/projects/${encodeURIComponent(name)}`);
    const data = await res.json();
    projectListEl.classList.add('hidden');
    projectDetailEl.classList.remove('hidden');
    projectDetailTitleEl.textContent = data.name;
    projectDetailRequestEl.textContent = data.state?.request || '';
    projectDetailToolsEl.innerHTML = '';
    edaTools.forEach((t) => {
      projectDetailToolsEl.appendChild(toolButton(t, data.name));
    });
    projectDetailContentEl.textContent = '';
    projectDetailMemoryEl.textContent = data.memory || 'Noch kein Gedächtnis vorhanden';
    projectDetailFilesEl.innerHTML = '';
    const files = data.files || [];
    if (!files.length) {
      projectDetailFilesEl.innerHTML = '<li class="empty">Keine Dateien</li>';
    }
    files.forEach((f) => {
      const li = document.createElement('li');
      li.textContent = f;
      li.classList.add('file-link');
      li.title = 'Datei anzeigen';
      li.addEventListener('click', () => showProjectFile(name, f));
      projectDetailFilesEl.appendChild(li);
    });
  } catch (e) {
  }
}

async function showProjectFile(name, path) {
  try {
    projectDetailContentEl.textContent = 'Lade Datei...';
    const res = await fetch(`${API_BASE}/api/projects/${encodeURIComponent(name)}/file?path=${encodeURIComponent(path)}`);
    const data = await res.json();
    projectDetailContentEl.textContent = data.content || 'Datei nicht gefunden';
  } catch (e) {
    projectDetailContentEl.textContent = 'Fehler beim Laden der Datei';
  }
}

projectBackBtn.addEventListener('click', () => {
  projectDetailEl.classList.add('hidden');
  projectListEl.classList.remove('hidden');
});

// ── Neues Projekt ──
function startNewProject() {
  currentTaskId = null;
  taskIdEl.textContent = '—';
  taskStatusEl.textContent = '—';
  taskWorkspaceEl.textContent = '—';
  chatTaskEl.textContent = '—';
  setBadge('', 'Idle');
  updateWorkflow('CREATED');
  messagesEl.innerHTML = '';
  fileListEl.innerHTML = '<li class="empty">Noch keine Dateien generiert</li>';
  logListEl.innerHTML = '';
  testOutputEl.textContent = 'Warte auf Testergebnisse...';
  addSystemMessage('Neues leeres Projekt gestartet — beschreibe deine Aufgabe');
  switchView('ai-engineer');
}

document.getElementById('project-new-btn').addEventListener('click', startNewProject);

function statusClass(status) {
  if (status === 'COMPLETED') return 'done';
  if (status === 'FAILED') return 'error';
  return 'info';
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '—';
  return d.toLocaleString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

connect();
addAgentMessage('Hello! I\'m your AI Engineering Agent. Describe a task and I\'ll generate the design, run tests, and deliver the results.');

// ── Settings View ──
function initSettings() {
  // Color swatch selection
  document.querySelectorAll('.swatch').forEach((swatch) => {
    swatch.addEventListener('click', () => {
      document.querySelectorAll('.swatch').forEach((s) => s.classList.remove('active'));
      swatch.classList.add('active');
      const accent = swatch.dataset.accent;
      if (accent) {
        document.documentElement.style.setProperty('--accent', accent);
        // Compute hover and soft variants
        document.documentElement.style.setProperty('--accent-hover', accent + 'dd');
        document.documentElement.style.setProperty('--accent-soft', accent + '1a');
        document.documentElement.style.setProperty('--accent-border', accent + '59');
      }
    });
  });

  // Save button
  const saveBtn = document.getElementById('settings-save-btn');
  const statusEl = document.getElementById('settings-status');
  if (saveBtn) {
    saveBtn.addEventListener('click', () => {
      const settings = {
        llm: {
          provider: document.getElementById('settings-llm-provider')?.value || 'ollama',
          model: document.getElementById('settings-llm-model')?.value || '',
          base_url: document.getElementById('settings-llm-base-url')?.value || '',
          temperature: parseFloat(document.getElementById('settings-llm-temperature')?.value || '0.1'),
          max_tokens: parseInt(document.getElementById('settings-llm-max-tokens')?.value || '4096'),
        },
        theme: document.getElementById('settings-theme')?.value || 'dark',
        synthesis: {
          default_fpga: document.getElementById('settings-default-fpga')?.value || 'arty_s7_50',
        },
        opencode: {
          max_repair_iterations: parseInt(document.getElementById('settings-max-repairs')?.value || '5'),
        },
        vivado: {
          binary: document.getElementById('settings-vivado-binary')?.value || '',
          settings_script: document.getElementById('settings-vivado-settings')?.value || '',
        },
        ghdl: {
          binary: document.getElementById('settings-ghdl-binary')?.value || 'ghdl',
        },
      };
      localStorage.setItem('ai-engineer-settings', JSON.stringify(settings));
      if (statusEl) {
        statusEl.textContent = 'Einstellungen gespeichert';
        statusEl.className = 'rag-status done';
        statusEl.style.display = 'inline-flex';
        setTimeout(() => { statusEl.style.display = 'none'; }, 2500);
      }
    });
  }

  // Reset button
  const resetBtn = document.getElementById('settings-reset-btn');
  if (resetBtn) {
    resetBtn.addEventListener('click', () => {
      localStorage.removeItem('ai-engineer-settings');
      // Reset accent color
      document.documentElement.style.removeProperty('--accent');
      document.documentElement.style.removeProperty('--accent-hover');
      document.documentElement.style.removeProperty('--accent-soft');
      document.documentElement.style.removeProperty('--accent-border');
      // Reset swatch selection
      document.querySelectorAll('.swatch').forEach((s) => s.classList.remove('active'));
      const defaultSwatch = document.querySelector('.swatch[data-accent="#3f8ef0"]');
      if (defaultSwatch) defaultSwatch.classList.add('active');
      // Reset form fields
      const defaults = {
        'settings-llm-provider': 'ollama',
        'settings-llm-model': 'gpt-oss:120b-cloud',
        'settings-llm-base-url': 'http://localhost:11434',
        'settings-llm-temperature': '0.1',
        'settings-llm-max-tokens': '4096',
        'settings-theme': 'dark',
        'settings-max-repairs': '5',
        'settings-default-fpga': 'arty_s7_50',
        'settings-vivado-binary': '/home/alex/Xilinx/2026.1/Vivado/bin/vivado',
        'settings-vivado-settings': '/home/alex/Xilinx/2026.1/Vivado/settings64.sh',
        'settings-ghdl-binary': 'ghdl',
      };
      Object.entries(defaults).forEach(([id, val]) => {
        const el = document.getElementById(id);
        if (el) el.value = val;
      });
      if (statusEl) {
        statusEl.textContent = 'Einstellungen zurückgesetzt';
        statusEl.className = 'rag-status info';
        statusEl.style.display = 'inline-flex';
        setTimeout(() => { statusEl.style.display = 'none'; }, 2500);
      }
    });
  }

  // Load saved settings
  loadSettings();
}

function loadSettings() {
  try {
    const saved = JSON.parse(localStorage.getItem('ai-engineer-settings') || '{}');
    if (saved.llm) {
      if (saved.llm.provider) setVal('settings-llm-provider', saved.llm.provider);
      if (saved.llm.model) setVal('settings-llm-model', saved.llm.model);
      if (saved.llm.base_url) setVal('settings-llm-base-url', saved.llm.base_url);
      if (saved.llm.temperature !== undefined) setVal('settings-llm-temperature', saved.llm.temperature);
      if (saved.llm.max_tokens !== undefined) setVal('settings-llm-max-tokens', saved.llm.max_tokens);
    }
    if (saved.theme) setVal('settings-theme', saved.theme);
    if (saved.synthesis?.default_fpga) setVal('settings-default-fpga', saved.synthesis.default_fpga);
    if (saved.opencode?.max_repair_iterations) setVal('settings-max-repairs', saved.opencode.max_repair_iterations);
    if (saved.vivado?.binary) setVal('settings-vivado-binary', saved.vivado.binary);
    if (saved.vivado?.settings_script) setVal('settings-vivado-settings', saved.vivado.settings_script);
    if (saved.ghdl?.binary) setVal('settings-ghdl-binary', saved.ghdl.binary);
  } catch (e) {
    // Ignore parse errors
  }
}

function setVal(id, value) {
  const el = document.getElementById(id);
  if (el) el.value = value;
}

initSettings();

// ── Code Editor View ──
let codeFiles = {};
let currentCodeFile = null;

function initCodeEditor() {
  const fileListEl = document.getElementById('code-file-list');
  const editorEl = document.getElementById('code-editor');
  const currentFileEl = document.getElementById('code-current-file');
  const fileInfoEl = document.getElementById('code-file-info');
  const statusEl = document.getElementById('code-status');
  const newBtn = document.getElementById('code-new-btn');
  const saveBtn = document.getElementById('code-save-btn');
  const deleteBtn = document.getElementById('code-delete-btn');

  if (newBtn) {
    newBtn.addEventListener('click', () => {
      const name = prompt('Dateiname (z.B. counter.vhd):');
      if (!name) return;
      if (codeFiles[name]) {
        alert('Datei existiert bereits');
        return;
      }
      codeFiles[name] = '';
      currentCodeFile = name;
      renderCodeFiles();
      selectCodeFile(name);
      if (statusEl) statusEl.textContent = `Neue Datei: ${name}`;
    });
  }

  if (saveBtn) {
    saveBtn.addEventListener('click', () => {
      if (!currentCodeFile) {
        alert('Keine Datei ausgewählt');
        return;
      }
      codeFiles[currentCodeFile] = editorEl.value;
      localStorage.setItem('ai-engineer-code', JSON.stringify(codeFiles));
      if (statusEl) statusEl.textContent = `Gespeichert: ${currentCodeFile}`;
      updateCodeInfo();
    });
  }

  if (deleteBtn) {
    deleteBtn.addEventListener('click', () => {
      if (!currentCodeFile) return;
      if (!confirm(`Datei "${currentCodeFile}" wirklich löschen?`)) return;
      delete codeFiles[currentCodeFile];
      currentCodeFile = null;
      editorEl.value = '';
      currentFileEl.textContent = 'Keine Datei ausgewählt';
      fileInfoEl.textContent = '';
      renderCodeFiles();
      localStorage.setItem('ai-engineer-code', JSON.stringify(codeFiles));
      if (statusEl) statusEl.textContent = 'Datei gelöscht';
    });
  }

  if (editorEl) {
    editorEl.addEventListener('input', () => {
      if (currentCodeFile) {
        codeFiles[currentCodeFile] = editorEl.value;
        updateCodeInfo();
      }
    });
    // Tab key inserts spaces
    editorEl.addEventListener('keydown', (e) => {
      if (e.key === 'Tab') {
        e.preventDefault();
        const start = editorEl.selectionStart;
        const end = editorEl.selectionEnd;
        editorEl.value = editorEl.value.substring(0, start) + '    ' + editorEl.value.substring(end);
        editorEl.selectionStart = editorEl.selectionEnd = start + 4;
        if (currentCodeFile) codeFiles[currentCodeFile] = editorEl.value;
      }
    });
  }

  loadCodeFiles();
}

function renderCodeFiles() {
  const fileListEl = document.getElementById('code-file-list');
  if (!fileListEl) return;
  fileListEl.innerHTML = '';
  const names = Object.keys(codeFiles);
  if (!names.length) {
    fileListEl.innerHTML = '<li class="empty">Keine Dateien vorhanden</li>';
    return;
  }
  names.forEach((name) => {
    const li = document.createElement('li');
    li.textContent = name;
    if (name === currentCodeFile) li.classList.add('active');
    li.addEventListener('click', () => selectCodeFile(name));
    fileListEl.appendChild(li);
  });
}

function selectCodeFile(name) {
  currentCodeFile = name;
  const editorEl = document.getElementById('code-editor');
  const currentFileEl = document.getElementById('code-current-file');
  const statusEl = document.getElementById('code-status');

  if (editorEl) editorEl.value = codeFiles[name] || '';
  if (currentFileEl) currentFileEl.textContent = name;
  if (statusEl) statusEl.textContent = `Geöffnet: ${name}`;

  renderCodeFiles();
  updateCodeInfo();
}

function updateCodeInfo() {
  const fileInfoEl = document.getElementById('code-file-info');
  const editorEl = document.getElementById('code-editor');
  if (!fileInfoEl || !editorEl) return;
  const lines = editorEl.value.split('\n').length;
  const chars = editorEl.value.length;
  fileInfoEl.textContent = `${lines} Zeilen · ${chars} Zeichen`;
}

function loadCodeFiles() {
  try {
    const saved = JSON.parse(localStorage.getItem('ai-engineer-code') || '{}');
    if (saved && typeof saved === 'object') {
      codeFiles = saved;
    }
  } catch (e) {
    codeFiles = {};
  }
  renderCodeFiles();
}

initCodeEditor();
