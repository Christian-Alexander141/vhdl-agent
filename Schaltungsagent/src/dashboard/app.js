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
    addSystemMessage('Mit dem Server verbunden');
    // Kein Auto-Laden eines alten Projekts hier: Ein (Re-)Connect darf nie
    // von selbst ein Projekt aktiv setzen. Sonst würde eine frische Nachricht
    // direkt nach einem Seiten-Reload als Änderung an einem alten, zufällig
    // zuletzt abgeschlossenen Projekt geroutet statt ein neues zu starten –
    // z. B. triggert "baue ..." in ChatRouter.CHANGE_HINTS eine Änderung,
    // sobald current_project gesetzt ist. Alte Projekte sind nur über
    // "Neues Projekt" (keins aktiv) oder Projekte → "In Chat laden"
    // (explizit gewählt) erreichbar.
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
    addSystemMessage('Verbindung verloren – neuer Versuch in 3 s');
    scheduleReconnect();
  };
}

function scheduleReconnect() {
  clearTimeout(reconnectTimer);
  reconnectTimer = setTimeout(connect, 3000);
}

function setOnline() {
  connectionText.innerHTML = '<span class="dot online"></span><span>Verbunden</span>';
}

function setOffline() {
  connectionText.innerHTML = '<span class="dot offline"></span><span>Getrennt</span>';
}

function sendWS(data) {
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify(data));
  } else {
    addSystemMessage('Senden nicht möglich – keine Verbindung');
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
      setBadge('active', 'Aktiv');
      if (currentTaskId) addSystemMessage(`Task erstellt: ${currentTaskId}`);
      updateWorkflow('CREATED');
      break;

    case 'STATE_CHANGED':
      updateWorkflow(payload.to);
      taskStatusEl.textContent = payload.to;
      setBadgeFromStatus(payload.to);
      break;

    case 'ANALYSIS_STARTED':
    case 'ANALYSIS_FINISHED':
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
    case 'REFERENCE_MODEL':
    case 'MUTATION_ANALYSIS':
    case 'MUTATION_WARNING':
    case 'TOOLCHAIN_WARNING':
    case 'PROJECT_IMPLEMENTED':
    case 'FALLBACK_USED':
    case 'ESCALATION':
    case 'REPAIR_ROLLED_BACK':
    case 'REPAIR_RETRY':
    case 'REFERENCE_MODEL_DISPUTED':
    case 'AGENT_NOTE':
    case 'OPENCODE_CALL':
    case 'REQUIREMENTS_REVIEW':
    case 'REQUIREMENTS_WARNING':
    case 'IMPLEMENTATION_GRAPH_FAILED':
    case 'STAGE_STARTED':
    case 'STAGE_FINISHED':
    case 'AUTONOMOUS_LOOP_STARTED':
    case 'AUTONOMOUS_LIMIT_REACHED':
    case 'CONTRACT_CHECK_FAILED':
    case 'HUMAN_INTERVENTION_REQUESTED':
    case 'HARDWARE_TEST_STARTED':
    case 'HARDWARE_TEST_PASSED':
    case 'HARDWARE_TEST_FAILED': {
      const tone = eventTone(eventType);
      const logText = payload.stage ? `${humanizeEvent(eventType)}: ${stageLabel(payload.stage)}` : humanizeEvent(eventType) + (message ? ': ' + message : '');
      addLogEntry(logLevel(tone), logText);
      if (eventType === 'AGENT_FINISHED' && (payload.stdout || payload.stderr)) {
        addAgentMessageWithLabel(agent, formatAgentOutput(payload), tone);
      } else if (eventType === 'STAGE_STARTED' && payload.stage) {
        const stage = payload.stage.toUpperCase();
        updateWorkflow(stage);
        taskStatusEl.textContent = stageLabel(stage);
        setBadgeFromStatus(stage);
        addSystemMessage(`Phase: ${stageLabel(stage)}`);
      } else if (eventType === 'STAGE_FINISHED') {
        // Nur im Ereignisprotokoll – hält den Chat lesbar.
      } else {
        addAgentMessageWithLabel(agent, message || formatEventPayload(eventType, payload), tone);
      }
      break;
    }

    // Reine Ablauf-Events: nur im Ereignisprotokoll
    case 'TASK_GRAPH_CREATED':
    case 'PARALLEL_BATCH_STARTED':
    case 'PARALLEL_BATCH_COMPLETED':
    case 'TASK_INVALIDATED':
    case 'TASK_BLOCKED':
    case 'CONTRACT_CHECK_STARTED':
    case 'CONTRACT_CHECK_PASSED':
    case 'MODULE_IMPLEMENTED':
      addLogEntry(logLevel(eventTone(eventType)), formatEventPayload(eventType, payload).replace(/\n/g, ' · '));
      break;

    case 'AGENT_HEARTBEAT':
      addLogEntry('info', message || 'Der Agent arbeitet weiter.');
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
      addAgentMessageWithLabel(agent, formatAgentOutput(payload, 'OpenCode fehlgeschlagen'), 'error');
      break;

    case 'TEST_FAILED':
    case 'REPAIR_STARTED':
      addLogEntry('event', humanizeEvent(eventType) + (message ? ': ' + message : ''));
      addAgentMessageWithLabel(agent, formatEventPayload(eventType, payload), eventType === 'TEST_FAILED' ? 'error' : 'warning');
      if (payload.stderr) {
        testOutputEl.textContent += `\n[ERROR] ${payload.stderr.substring(0, 500)}`;
      }
      break;

    case 'REPAIR_FINISHED':
      addLogEntry('event', humanizeEvent(eventType) + (message ? ': ' + message : ''));
      break;

    case 'TASK_COMPLETED':
      updateWorkflow('COMPLETED');
      taskStatusEl.textContent = stageLabel('COMPLETED');
      setBadge('success', 'Abgeschlossen');
      addLogEntry('done', 'Task erfolgreich abgeschlossen');
      addAgentMessage(payload.outputs?.message || 'Task erfolgreich abgeschlossen', 'success');
      if (payload.files) updateFiles(payload);
      if (payload.workspace) taskWorkspaceEl.textContent = payload.workspace;
      break;

    case 'TASK_FAILED':
      updateWorkflow('FAILED');
      taskStatusEl.textContent = stageLabel('FAILED');
      setBadge('error', 'Fehlgeschlagen');
      addLogEntry('error', payload.error || 'Task fehlgeschlagen');
      addAgentMessage(`Task fehlgeschlagen${payload.error ? ':\n' + payload.error : ''}`, 'error');
      break;

    case 'CHAT_RESPONSE':
      if (payload.type === 'error') {
        addAgentMessage(payload.answer || payload.error || 'Fehler', 'error');
        setBadge('error', 'Fehlgeschlagen');
      } else if (payload.type === 'question' || payload.answer) {
        if (payload.project_id) {
          currentTaskId = payload.project_id;
          taskIdEl.textContent = payload.project_id;
          chatTaskEl.textContent = payload.project_id;
        }
        addAgentMessage(payload.answer || '');
        setBadge('', 'Bereit');
      } else if (payload.status === 'QUEUED') {
        if (payload.type === 'resume') {
          addSystemMessage(`Fortsetzung des Projekts: ${payload.task_id || payload.project_id || ''}`);
        } else {
          addSystemMessage('Neues Projekt wird erstellt...');
        }
        if (payload.task_id) {
          currentTaskId = payload.task_id;
          taskIdEl.textContent = payload.task_id;
          taskStatusEl.textContent = stageLabel('QUEUED');
          chatTaskEl.textContent = payload.task_id;
          setBadge('active', 'In Warteschlange');
          updateWorkflow('CREATED');
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

function showVhdlModal(code, title = 'VHDL-Code') {
  const backdrop = document.createElement('div');
  backdrop.className = 'modal-backdrop';
  backdrop.innerHTML = `
    <div class="modal" role="dialog" aria-modal="true">
      <div class="modal-head"><span>${escapeHtml(title)}</span><button class="modal-close" type="button" aria-label="Schließen">&times;</button></div>
      <pre>${escapeHtml(code)}</pre>
    </div>`;
  const close = () => { backdrop.remove(); document.removeEventListener('keydown', onKey); };
  const onKey = (e) => { if (e.key === 'Escape') close(); };
  backdrop.querySelector('.modal').onclick = (e) => e.stopPropagation();
  backdrop.querySelector('.modal-close').onclick = close;
  backdrop.onclick = close;
  document.addEventListener('keydown', onKey);
  document.body.appendChild(backdrop);
}

async function sendTask(request, files) {
  setBadge('active', 'Wird verarbeitet');
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
      setBadge('error', 'Fehlgeschlagen');
      return;
    }
    if (result.type === 'question' || result.answer) {
      currentTaskId = result.project_id || currentTaskId;
      if (result.project_id) {
        taskIdEl.textContent = result.project_id;
        chatTaskEl.textContent = result.project_id;
      }
      addAgentMessage(result.answer || result.message || '');
      setBadge('', 'Bereit');
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
    addAgentMessage(files && files.length ? `Fehler beim Hochladen: ${e}` : `Anfrage fehlgeschlagen: ${e}`);
    setBadge('error', 'Fehlgeschlagen');
  } finally {
    sendBtn.disabled = false;
  }
}

const STAGE_LABELS = {
  CREATED: 'Auftrag', QUEUED: 'In Warteschlange', ANALYZING: 'Analyse',
  ARCHITECTING: 'Architektur', UART_INTEGRATION: 'UART-Integration',
  IMPLEMENTING: 'Implementierung', STATIC_CHECK: 'Statischer Check',
  SIMULATING: 'Simulation', VALIDATING: 'Validierung', DEBUGGING: 'Diagnose',
  REPAIRING: 'Reparatur', SYNTHESIZING: 'Synthese',
  FPGA_PROGRAMMING: 'FPGA flashen', HARDWARE_TESTING: 'Hardwaretest',
  COMPLETED: 'Abgeschlossen', FAILED: 'Fehlgeschlagen', BLOCKED: 'Blockiert',
  INFRASTRUCTURE_FAILURE: 'Infrastrukturfehler', AUTONOMOUS_LIMIT_REACHED: 'Limit erreicht',
};

function normalizeStage(status) {
  return String(status || '').toUpperCase()
    .replace(/^DESIGNSTAGE\./, '').replace(/^WORKFLOWSTATE\./, '');
}

function stageLabel(status) {
  const s = normalizeStage(status);
  return STAGE_LABELS[s] || s || '—';
}

function updateWorkflow(activeStatus) {
  const workflowAliases = {
    QUEUED: 'CREATED',
    RUNNING: 'CREATED',
    RECEIVED: 'CREATED',
    VERIFYING: 'SIMULATING',
    SIMULATION_PASSED: 'VALIDATING',
    FLASHING: 'FPGA_PROGRAMMING',
    FLASHED: 'FPGA_PROGRAMMING',
    SUCCESS: 'COMPLETED',
    INFRASTRUCTURE_FAILURE: 'FAILED',
    AUTONOMOUS_LIMIT_REACHED: 'FAILED',
    UNRECOVERABLE_ERROR: 'FAILED',
  };
  activeStatus = normalizeStage(activeStatus || 'CREATED');
  activeStatus = workflowAliases[activeStatus] || activeStatus;
  const steps = Array.from(workflowSteps);
  const knownSteps = new Set(steps.map((step) => step.dataset.step));
  if (!knownSteps.has(activeStatus)) activeStatus = 'CREATED';

  const failed = activeStatus === 'FAILED';
  const doneAll = activeStatus === 'COMPLETED';
  let found = false;
  steps.forEach((step) => {
    const s = step.dataset.step;
    if (s === 'FAILED') {
      step.className = failed ? 'step step-fail failed' : 'step step-fail';
      return;
    }
    const base = step.classList.contains('step-optional') ? 'step step-optional' : 'step';
    if (!failed && s === activeStatus) {
      step.className = `${base} active`;
      found = true;
    } else if (!found && !failed && !step.classList.contains('step-optional')) {
      step.className = `${base} done`;
    } else {
      step.className = base;
    }
  });

  // Fortschritt über die Pflichtschritte
  const mandatory = steps.filter((st) => !st.classList.contains('step-optional') && st.dataset.step !== 'FAILED');
  const idx = mandatory.findIndex((st) => st.dataset.step === activeStatus);
  const pct = doneAll ? 100 : idx < 0 ? 0 : Math.round((idx / (mandatory.length - 1)) * 100);
  const bar = document.getElementById('workflow-progress-bar');
  const text = document.getElementById('workflow-progress-text');
  const col = document.getElementById('workflow-col');
  if (bar && !failed) bar.style.width = `${pct}%`;
  if (text) text.textContent = failed ? 'Fehler' : `${pct} %`;
  if (col) {
    col.classList.toggle('is-failed', failed);
    col.classList.toggle('is-done', doneAll);
  }
}

function setBadge(cls, text) {
  statusBadge.className = `badge ${cls}`;
  statusBadge.textContent = text;
}

function setBadgeFromStatus(status) {
  const s = normalizeStage(status);
  if (s === 'COMPLETED' || s === 'SUCCESS') setBadge('success', 'Abgeschlossen');
  else if (['FAILED', 'INFRASTRUCTURE_FAILURE', 'AUTONOMOUS_LIMIT_REACHED'].includes(s)) setBadge('error', stageLabel(s));
  else if (['DEBUGGING', 'REPAIRING', 'BLOCKED'].includes(s)) setBadge('warning', stageLabel(s));
  else if (STAGE_LABELS[s]) setBadge('active', stageLabel(s));
  else setBadge('', 'Bereit');
}

// ── Nachrichten ──
const AGENT_COLORS = {
  SupervisorAgent: '#6b7cff', Supervisor: '#6b7cff', ArchitectureAgent: '#9b6bff',
  HDLAgent: '#2f9be0', VerificationAgent: '#20a87a', DebugAgent: '#e08a2f',
  FPGAAgent: '#d9534f', HardwareTestAgent: '#c2569b', 'AI Engineer': '#4c8dff',
};

function agentInitials(name) {
  const clean = String(name || 'AI').replace(/Agent$/, '');
  const caps = clean.match(/[A-Z]/g);
  return (caps && caps.length >= 2 ? caps.slice(0, 2).join('') : clean.slice(0, 2)).toUpperCase();
}

function renderMessageText(text) {
  // Mehrzeilige technische Ausgaben (Logs, Code) als Codeblock darstellen.
  const str = String(text ?? '');
  const parts = str.split(/\n\n/);
  return parts.map((part) => {
    const lines = part.split('\n');
    const technical = lines.length > 3 || /^(Ausgabe|Fehlerausgabe|Fehler|Diagnose):/.test(part);
    if (technical && lines.length > 1) {
      return `${escapeHtml(lines[0])}<pre>${escapeHtml(lines.slice(1).join('\n'))}</pre>`;
    }
    return escapeHtml(part);
  }).join('\n\n');
}

function buildMessage(cls, label, text, avatarColor, tone) {
  const el = document.createElement('div');
  el.className = `message ${cls}${tone ? ' tone-' + tone : ''}`;
  el.innerHTML = `
    <div class="msg-avatar" style="--avatar:${avatarColor}">${escapeHtml(agentInitials(label))}</div>
    <div class="msg-body">
      <div class="msg-meta"><span class="msg-label">${escapeHtml(label)}</span><span class="timestamp">${now()}</span></div>
      <div class="msg-text">${cls === 'user' ? escapeHtml(text) : renderMessageText(text)}</div>
    </div>`;
  messagesEl.appendChild(el);
  scrollChat();
}

function addUserMessage(text) {
  buildMessage('user', 'Du', text, 'var(--bg-hover)');
}

function addAgentMessage(text, tone = '') {
  addAgentMessageWithLabel('AI Engineer', text, tone);
}

function addAgentMessageWithLabel(agent, text, tone = '') {
  buildMessage('agent', agent, text, AGENT_COLORS[agent] || '#5f6b7a', tone);
}

function eventTone(eventType) {
  if (/FAILED|ERROR|IDENTICAL|LIMIT|BLOCKED/.test(eventType)) return 'error';
  if (/PASSED|COMPLETED|FINISHED_OK|GRANTED/.test(eventType)) return 'success';
  if (/REPAIR|DEBUG|NO_PROGRESS|INVALIDATED|HUMAN_INTERVENTION|WARNING/.test(eventType)) return 'warning';
  return '';
}

function logLevel(tone) {
  return { error: 'error', success: 'done', warning: 'warning' }[tone] || 'info';
}

const EVENT_TITLES = {
  ANALYSIS_STARTED: 'Analyse gestartet', ANALYSIS_FINISHED: 'Analyse abgeschlossen',
  ARCHITECTURE_CREATED: 'Architektur erstellt', ARCHITECTURE_FAILED: 'Architektur fehlgeschlagen',
  IMPLEMENTATION_STARTED: 'Implementierung gestartet', IMPLEMENTATION_COMPLETED: 'Implementierung abgeschlossen',
  IMPLEMENTATION_FAILED: 'Implementierung fehlgeschlagen', MODULE_IMPLEMENTED: 'Modul implementiert',
  STATIC_CHECK_STARTED: 'Statischer Check gestartet', STATIC_CHECK_PASSED: 'Statischer Check bestanden',
  STATIC_CHECK_FAILED: 'Statischer Check fehlgeschlagen',
  CONTRACT_CHECK_STARTED: 'Contract-Check gestartet', CONTRACT_CHECK_PASSED: 'Contract-Check bestanden',
  CONTRACT_CHECK_FAILED: 'Contract-Check fehlgeschlagen',
  SIMULATION_STARTED: 'Simulation gestartet', SIMULATION_PASSED: 'Simulation bestanden', SIMULATION_FAILED: 'Simulation fehlgeschlagen',
  VALIDATION_STARTED: 'Validierung gestartet', VALIDATION_FINISHED: 'Validierung abgeschlossen',
  DEBUG_STARTED: 'Diagnose gestartet', DEBUG_COMPLETED: 'Diagnose abgeschlossen',
  REPAIR_ASSIGNED: 'Reparatur zugewiesen', REPAIR_STARTED: 'Reparatur gestartet',
  REPAIR_COMPLETED: 'Reparatur abgeschlossen', REPAIR_FAILED: 'Reparatur fehlgeschlagen', REPAIR_FINISHED: 'Reparatur beendet',
  NO_PROGRESS: 'Kein Fortschritt', IDENTICAL_ERROR: 'Gleicher Fehler wiederholt',
  REFERENCE_MODEL: 'Referenzmodell', MUTATION_ANALYSIS: 'Mutationsanalyse', MUTATION_WARNING: 'Testbench-Güte niedrig',
  TOOLCHAIN_WARNING: 'Werkzeug fehlt', PROJECT_IMPLEMENTED: 'Projekt implementiert',
  FALLBACK_USED: 'Vorlage statt OpenCode-Ergebnis', ESCALATION: 'Eskalation', REPAIR_ROLLED_BACK: 'Reparatur zurückgenommen', REPAIR_RETRY: 'Nächste Eskalationsstufe', REFERENCE_MODEL_DISPUTED: 'Referenzmodell abgeschaltet', AGENT_NOTE: 'Hinweis eines Agenten', OPENCODE_CALL: 'OpenCode-Aufruf', REQUIREMENTS_REVIEW: 'Abschlussprüfung Anforderungen', REQUIREMENTS_WARNING: 'Hinweis Anforderungen', TOP_INTEGRATED: 'Top-Level integriert',
  IMPLEMENTATION_GRAPH_COMPLETED: 'Implementierung abgeschlossen', IMPLEMENTATION_GRAPH_FAILED: 'Implementierung fehlgeschlagen',
  SYNTHESIS_STARTED: 'Synthese gestartet', SYNTHESIS_FINISHED: 'Synthese beendet',
  FLASH_STARTED: 'Flash gestartet', FLASH_FINISHED: 'Flash beendet',
  HARDWARE_TEST_STARTED: 'Hardwaretest gestartet', HARDWARE_TEST_PASSED: 'Hardwaretest bestanden',
  HARDWARE_TEST_FAILED: 'Hardwaretest fehlgeschlagen',
  HUMAN_INTERVENTION_REQUESTED: 'Eingriff erforderlich',
  TASK_GRAPH_CREATED: 'Task-Graph erstellt', PARALLEL_BATCH_STARTED: 'Parallel-Batch gestartet',
  PARALLEL_BATCH_COMPLETED: 'Parallel-Batch beendet', TASK_INVALIDATED: 'Task invalidiert', TASK_BLOCKED: 'Task blockiert',
  STAGE_STARTED: 'Phase gestartet', STAGE_FINISHED: 'Phase beendet',
  AUTONOMOUS_LOOP_STARTED: 'Workflow gestartet', AUTONOMOUS_LIMIT_REACHED: 'Iterationslimit erreicht',
  TEST_STARTED: 'Test gestartet', TEST_PASSED: 'Test bestanden', TEST_FAILED: 'Test fehlgeschlagen',
  FILES_CREATED: 'Dateien erzeugt', WORKSPACE_READY: 'Workspace bereit',
  AGENT_STARTED: 'Agent gestartet', AGENT_FINISHED: 'Agent beendet',
};

function humanizeEvent(eventType) {
  return EVENT_TITLES[eventType] || String(eventType || '').toLowerCase().replace(/_/g, ' ')
    .replace(/^./, (c) => c.toUpperCase());
}

function formatAgentOutput(payload, prefix = '') {
  const parts = [];
  if (prefix) parts.push(prefix);
  if (payload.stdout) parts.push(`Ausgabe:\n${payload.stdout}`);
  if (payload.stderr) parts.push(`Fehlerausgabe:\n${payload.stderr}`);
  if (payload.error && !payload.stderr) parts.push(`Fehler:\n${payload.error}`);
  return parts.join('\n\n') || prefix || 'Keine Ausgabe';
}

const REPAIR_TARGETS = {
  architecture: 'ArchitectureAgent', hdl: 'HDLAgent', verification: 'VerificationAgent',
  fpga: 'HDLAgent (Synthesekontext)', human: 'Benutzer',
};

function asList(value) {
  if (Array.isArray(value)) return value.map((v) => (typeof v === 'string' ? v : JSON.stringify(v))).join(', ');
  return String(value);
}

function formatEventPayload(eventType, payload) {
  const details = [];
  if (payload.repair_target) details.push(`Reparatur durch: ${REPAIR_TARGETS[payload.repair_target] || payload.repair_target}`);
  if (payload.failure_type) details.push(`Fehlerklasse: ${payload.failure_type}`);
  if (payload.module) details.push(`Modul: ${payload.module}`);
  if (payload.modules?.length) details.push(`Module: ${asList(payload.modules)}`);
  if (payload.failed_module?.length) details.push(`Module: ${asList(payload.failed_module)}`);
  if (payload.changed_modules?.length) details.push(`Geänderte Module: ${asList(payload.changed_modules)}`);
  if (payload.stage) details.push(`Phase: ${stageLabel(payload.stage)}`);
  if (payload.failed_stage) details.push(`Fehlgeschlagene Phase: ${stageLabel(payload.failed_stage)}`);
  if (payload.batch?.length) details.push(`Parallel: ${asList(payload.batch)}`);
  if (payload.task) details.push(`Task: ${payload.task}`);
  if (payload.reason) details.push(`Grund: ${payload.reason}`);
  if (payload.task_count !== undefined) details.push(`${payload.task_count} Tasks, ${(payload.reused_tasks || []).length} übernommen`);
  if (payload.test_mode) details.push(`Modus: ${payload.test_mode}`);
  if (payload.violations?.length) {
    details.push(`Verletzungen:\n${payload.violations.slice(0, 8).map((v) => `${v.module}: ${v.check} – erwartet ${v.expected}, ist ${v.actual}`).join('\n')}`);
  }
  if (payload.failures?.length) details.push(`Fehler:\n${payload.failures.map((f) => (typeof f === 'string' ? f : f.name || JSON.stringify(f))).join('\n')}`);
  if (payload.error) details.push(`Fehler: ${payload.error}`);
  if (payload.diagnosis) details.push(`Diagnose:\n${JSON.stringify(payload.diagnosis, null, 2)}`);
  const title = humanizeEvent(eventType);
  return details.length ? `${title}\n${details.join('\n')}` : title;
}

function addSystemMessage(text) {
  const el = document.createElement('div');
  el.className = 'message system';
  el.textContent = text;
  messagesEl.appendChild(el);
  scrollChat();
}

function scrollChat() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

const LOG_LABELS = { info: 'Info', done: 'OK', error: 'Fehler', event: 'Event', warning: 'Warnung' };
const MAX_LOG_ENTRIES = 400;

function addLogEntry(type, message) {
  const level = LOG_LABELS[type] ? type : 'info';
  const el = document.createElement('div');
  el.className = 'log-entry';
  el.innerHTML = `<span class="log-time">${now()}</span><span class="log-type ${level}">${LOG_LABELS[level]}</span><span class="log-msg">${escapeHtml(message)}</span>`;
  logListEl.appendChild(el);
  while (logListEl.children.length > MAX_LOG_ENTRIES) logListEl.firstChild.remove();
  logListEl.scrollTop = logListEl.scrollHeight;
}

document.getElementById('log-clear-btn')?.addEventListener('click', () => { logListEl.innerHTML = ''; });

function fileKind(path) {
  if (/_tb\.vhdl?$|^tests\//.test(path)) return 'tb';
  if (/\.xdc$|\.ccf$|^constraints\//.test(path)) return 'xdc';
  if (/\.vhdl?$/.test(path)) return 'src';
  return 'other';
}

function renderFiles(files) {
  fileListEl.innerHTML = '';
  files.forEach((f) => {
    const li = document.createElement('li');
    li.textContent = f;
    li.dataset.kind = fileKind(f);
    li.title = f;
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
  chatInput.style.height = 'auto';

  selectedFiles = [];
  renderFileChips();

  sendTask(text, files);
}

sendBtn.addEventListener('click', handleSend);
chatInput.addEventListener('input', () => {
  chatInput.style.height = 'auto';
  chatInput.style.height = `${Math.min(chatInput.scrollHeight, 200)}px`;
});
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
  if (!Array.isArray(projects) || !projects.length) {
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
        <span class="project-status ${statusClass(status)}">${escapeHtml(stageLabel(status))}</span>
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
    const res = await fetch(`${API_BASE}/api/projects/${encodeURIComponent(name)}/file?path=${encodeURIComponent(path)}`);
    const data = await res.json();
    showVhdlModal(data.content || 'Datei nicht gefunden', path);
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
  setBadge('', 'Bereit');
  updateWorkflow('CREATED');
  messagesEl.innerHTML = '';
  fileListEl.innerHTML = '<li class="empty">Noch keine Dateien generiert</li>';
  logListEl.innerHTML = '';
  testOutputEl.textContent = 'Warte auf Testergebnisse …';
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
addAgentMessage('Hallo! Beschreibe eine Schaltung und das Ziel-Board. Die Agenten planen die Architektur, implementieren und simulieren die Module, synthetisieren das Design und flashen es auf das Board.');

// ── Settings View ──
// Alle Felder mit data-setting="abschnitt.feld" kommen vom Server
// (GET /api/settings) und werden dort gespeichert. Nur Theme und Akzentfarbe
// liegen im Browser.
let serverSettings = {};

function settingFields() {
  return Array.from(document.querySelectorAll('[data-setting]'));
}

function readField(el) {
  if (el.type === 'checkbox') return el.checked;
  if (el.dataset.type === 'bool') return el.value === 'true';
  if (el.type === 'number') return el.value === '' ? null : Number(el.value);
  return el.value;
}

function writeField(el, value) {
  if (value === undefined || value === null) return;
  if (el.type === 'checkbox') el.checked = !!value;
  else el.value = typeof value === 'boolean' ? String(value) : value;
}

function serverValue(path) {
  const [section, field] = path.split('.');
  return serverSettings[section]?.[field];
}

function markDirty() {
  settingFields().forEach((el) => {
    const dirty = JSON.stringify(readField(el)) !== JSON.stringify(serverValue(el.dataset.setting));
    el.classList.toggle('dirty', dirty);
  });
  updateExecutionView();
}

function updateExecutionView() {
  const native = document.getElementById('set-exec-mode')?.value === 'true';
  const shared = document.getElementById('set-isolation')?.value === 'shared';
  document.getElementById('native-warning')?.classList.toggle('hidden', !native);
  document.querySelectorAll('.docker-only').forEach((el) => el.classList.toggle('is-hidden', native));
  document.querySelectorAll('.native-only').forEach((el) => el.classList.toggle('is-hidden', !native));
  if (!native) {
    document.querySelectorAll('.per-task-only').forEach((el) => el.classList.toggle('is-hidden', shared));
    document.querySelectorAll('.shared-only').forEach((el) => el.classList.toggle('is-hidden', !shared));
  }
}

function showSettingsStatus(text, cls, sticky = false) {
  const statusEl = document.getElementById('settings-status');
  if (!statusEl) return;
  statusEl.textContent = text;
  statusEl.className = `status-pill ${cls}`;
  statusEl.style.display = 'inline-flex';
  clearTimeout(showSettingsStatus._t);
  if (!sticky) showSettingsStatus._t = setTimeout(() => { statusEl.style.display = 'none'; }, 3500);
}

async function loadSettings() {
  try {
    const response = await fetch(`${API_BASE}/api/settings`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    serverSettings = await response.json();
  } catch (error) {
    showSettingsStatus(`Einstellungen konnten nicht geladen werden: ${error.message}`, 'error', true);
    return;
  }
  settingFields().forEach((el) => writeField(el, serverValue(el.dataset.setting)));
  const meta = serverSettings._meta || {};
  const pill = document.getElementById('runner-pill');
  if (pill) {
    const docker = meta.opencode_runner === 'DockerOpenCodeService';
    pill.textContent = docker ? 'aktiv: Docker' : 'aktiv: nativ';
    pill.className = `runner-pill ${docker ? 'docker' : 'native'}`;
  }
  document.getElementById('env-test-mode')?.classList.toggle('hidden', !meta.test_mode_forced_by_environment);
  markDirty();
}

async function saveSettings() {
  const payload = {};
  settingFields().forEach((el) => {
    const value = readField(el);
    if (JSON.stringify(value) === JSON.stringify(serverValue(el.dataset.setting))) return;
    const [section, field] = el.dataset.setting.split('.');
    (payload[section] ||= {})[field] = value;
  });
  if (!Object.keys(payload).length) {
    showSettingsStatus('Keine Änderungen', 'info');
    return;
  }
  try {
    const response = await fetch(`${API_BASE}/api/settings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const result = await response.json();
    if (!response.ok || result.error) throw new Error(result.error || `HTTP ${response.status}`);
    await loadSettings();
    if (result.restart_required?.length) {
      showSettingsStatus(`Gespeichert – Neustart nötig für: ${result.restart_required.join(', ')}`, 'warning', true);
    } else {
      showSettingsStatus('Gespeichert und sofort aktiv', 'done');
    }
  } catch (error) {
    showSettingsStatus(`Speichern fehlgeschlagen: ${error.message}`, 'error', true);
  }
}

// ── OpenCode-Modell-Picker ──
// Fuellt die <select data-pairs="..."> -Dropdowns aus /api/opencode/models
// und schreibt die Auswahl in das zugehoerige Text-Feld, statt die
// bestehende Speicherlogik (data-setting) anzufassen.
function populateModelPickers(data) {
  const providers = Object.keys(data.by_provider || {}).sort();
  document.querySelectorAll('.model-picker').forEach((select) => {
    const pairedInput = document.getElementById(select.dataset.pairs);
    const current = pairedInput ? pairedInput.value : '';
    select.innerHTML = '<option value="">— aus Liste wählen —</option>';
    let currentInList = false;
    providers.forEach((provider) => {
      const group = document.createElement('optgroup');
      group.label = provider || 'andere';
      (data.by_provider[provider] || []).forEach((modelId) => {
        const option = document.createElement('option');
        option.value = modelId;
        option.textContent = modelId;
        if (modelId === current) {
          option.selected = true;
          currentInList = true;
        }
        group.appendChild(option);
      });
      select.appendChild(group);
    });
    if (current && !currentInList) {
      const custom = document.createElement('option');
      custom.value = current;
      custom.textContent = `${current} (aktuell, nicht in der Liste)`;
      custom.selected = true;
      select.insertBefore(custom, select.children[1] || null);
    }
    select.disabled = false;
    select.onchange = () => {
      if (!select.value || !pairedInput) return;
      pairedInput.value = select.value;
      // Loest die bereits vorhandenen data-setting-Listener aus (markDirty etc.).
      pairedInput.dispatchEvent(new Event('input', { bubbles: true }));
    };
  });
}

async function loadOpenCodeModels() {
  const btn = document.getElementById('oc-models-load-btn');
  const status = document.getElementById('oc-models-status');
  if (!btn) return;
  btn.disabled = true;
  if (status) status.textContent = 'Lade Modelle … (kann bei kaltem Cache bis zu 20 s dauern)';
  try {
    const response = await fetch(`${API_BASE}/api/opencode/models`);
    const data = await response.json();
    if (!response.ok || data.error) {
      throw new Error(data.hint ? `${data.error} (${data.hint})` : data.error || `HTTP ${response.status}`);
    }
    populateModelPickers(data);
    const runnerLabel = data.runner === 'DockerOpenCodeService' ? 'Docker' : 'nativ';
    if (status) {
      status.textContent = `${data.models.length} Modelle geladen (${runnerLabel}${data.cached ? ', aus Zwischenspeicher' : ''})`;
    }
  } catch (error) {
    if (status) status.textContent = `Modelle konnten nicht geladen werden: ${error.message}`;
  } finally {
    btn.disabled = false;
  }
}

function initSettings() {
  document.getElementById('oc-models-load-btn')?.addEventListener('click', loadOpenCodeModels);

  document.querySelectorAll('.swatch').forEach((swatch) => {
    swatch.addEventListener('click', () => {
      document.querySelectorAll('.swatch').forEach((sw) => sw.classList.remove('active'));
      swatch.classList.add('active');
      const accent = swatch.dataset.accent;
      if (accent) {
        document.documentElement.style.setProperty('--accent', accent);
        persistUiSetting('accent', accent);
      }
    });
  });

  const themeSelect = document.getElementById('settings-theme');
  if (themeSelect) {
    themeSelect.addEventListener('change', () => {
      applyTheme(themeSelect.value);
      persistUiSetting('theme', themeSelect.value);
    });
  }
  try {
    const ui = JSON.parse(localStorage.getItem('ai-engineer-settings') || '{}');
    if (ui.theme && themeSelect) { themeSelect.value = ui.theme; applyTheme(ui.theme); }
    if (ui.accent) document.querySelectorAll('.swatch').forEach((sw) => sw.classList.toggle('active', sw.dataset.accent === ui.accent));
  } catch (e) {
    // localStorage nicht verfügbar
  }

  settingFields().forEach((el) => {
    el.addEventListener('input', markDirty);
    el.addEventListener('change', markDirty);
  });
  document.getElementById('settings-save-btn')?.addEventListener('click', saveSettings);
  document.getElementById('settings-reset-btn')?.addEventListener('click', () => {
    loadSettings().then(() => showSettingsStatus('Änderungen verworfen', 'info'));
  });
  loadSettings();
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = ['dark', 'light', 'blueprint'].includes(theme) ? theme : 'dark';
}

function persistUiSetting(key, value) {
  try {
    const saved = JSON.parse(localStorage.getItem('ai-engineer-settings') || '{}');
    saved[key] = value;
    localStorage.setItem('ai-engineer-settings', JSON.stringify(saved));
  } catch (e) {
    // localStorage nicht verfügbar – Einstellung gilt nur für diese Sitzung.
  }
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
