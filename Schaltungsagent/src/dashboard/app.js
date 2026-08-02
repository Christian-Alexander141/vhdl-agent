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
const statusBadge = document.getElementById('status-badge');
const connectionDot = document.querySelector('#connection-indicator .dot');
const connectionText = document.querySelector('#connection-indicator');
const workflowSteps = document.querySelectorAll('.step');
const taskIdEl = document.getElementById('task-id');
const taskStatusEl = document.getElementById('task-status');
const taskFilesEl = document.getElementById('task-files');
const taskWorkspaceEl = document.getElementById('task-workspace');
const fileListEl = document.getElementById('file-list');
const logListEl = document.getElementById('log-list');
const testOutputEl = document.getElementById('test-output');

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

  switch (eventType) {
    case 'TASK_CREATED':
      currentTaskId = msg.task_id || payload.task_id;
      taskIdEl.textContent = currentTaskId || '—';
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
      addLogEntry('info', eventType + (message ? ': ' + message : ''));
      addAgentMessage(message || `Event: ${eventType}`);
      break;

    case 'TEST_FAILED':
    case 'REPAIR_STARTED':
      addLogEntry('event', eventType + (message ? ': ' + message : ''));
      addAgentMessage(`Event: ${eventType} — ${message || ''}`);
      if (payload.stderr) {
        testOutputEl.textContent += `\n[ERROR] ${payload.stderr.substring(0, 500)}`;
      }
      break;

    case 'REPAIR_FINISHED':
      addLogEntry('event', eventType + (message ? ': ' + message : ''));
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

    default:
      if (eventType && eventType.startsWith('LOG_')) {
        addLogEntry('info', message);
      }
  }
}

async function fetchTaskList() {
  try {
    const res = await fetch(`${API_BASE}/api/tasks`);
    if (!res.ok) return;
    const tasks = await res.json();
    if (tasks.length > 0) {
      const latest = tasks[tasks.length - 1];
      currentTaskId = latest.task_id;
      taskIdEl.textContent = latest.task_id;
      taskStatusEl.textContent = latest.status;
      setBadgeFromStatus(latest.status);
      updateWorkflow(latest.status);
      if (latest.generated_files?.length) {
        taskFilesEl.textContent = latest.generated_files.join(', ');
        renderFiles(latest.generated_files);
      }
    }
  } catch (e) {
  }
}

async function sendTask(request) {
  setBadge('active', 'Processing');
  sendBtn.disabled = true;

  try {
    const res = await fetch(`${API_BASE}/api/task`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_request: request, domain: 'vhdl' }),
    });
    const result = await res.json();
    if (result.task_id) {
      currentTaskId = result.task_id;
      taskIdEl.textContent = result.task_id;
      taskStatusEl.textContent = result.status;
    }
  } catch (e) {
    sendWS({ action: 'run_task', request });
    addSystemMessage('Sent task via WebSocket');
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
  else if (status === 'FAILED') setBadge('error', 'Failed');
  else if (['ANALYZING','RAG_SEARCH','GENERATING_ARTIFACTS','WORKSPACE_READY','RUNNING_AGENT','TESTING','REPAIRING','VALIDATING'].includes(status))
    setBadge('active', status);
  else setBadge('', 'Idle');
}

function addUserMessage(text) {
  const el = document.createElement('div');
  el.className = 'message user';
  el.innerHTML = `<span>${escapeHtml(text)}</span><span class="timestamp">${now()}</span>`;
  messagesEl.appendChild(el);
  scrollChat();
}

function addAgentMessage(text) {
  const el = document.createElement('div');
  el.className = 'message agent';
  el.innerHTML = `<span>${escapeHtml(text)}</span><span class="timestamp">${now()}</span>`;
  messagesEl.appendChild(el);
  scrollChat();
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
    taskFilesEl.textContent = files.join(', ');
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
  if (!text) return;

  addUserMessage(text);
  chatInput.value = '';

  sendTask(text);
}

sendBtn.addEventListener('click', handleSend);
chatInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    handleSend();
  }
});

document.querySelectorAll('.tab').forEach((tab) => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach((t) => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach((c) => c.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById(`tab-${tab.dataset.tab}`).classList.add('active');
  });
});

connect();
addAgentMessage('Hello! I\'m your AI Engineering Agent. Describe a task and I\'ll generate the design, run tests, and deliver the results.');
