// ============================================
// Constantes y estado
// ============================================

const POMO_DURATIONS = { focus: 1500, short_break: 300, long_break: 900 }; // segundos
const POMO_MIN_LOG_SECONDS = 60; // debajo de esto, "Detener" descarta en vez de guardar
const POMO_STORAGE_KEY = 'pomodoro_state';
const POMO_PENDING_KEY = 'pomodoro_pending';
const POMO_SOUND_KEY = 'pomodoro_sound';
const POMO_STALE_MS = 24 * 60 * 60 * 1000; // rehidratar más viejo que esto: descartar

function createIdlePomoState(mode = 'focus') {
    return {
        status: 'idle',           // idle | running | paused
        mode,                      // focus | short_break | long_break
        plannedSeconds: POMO_DURATIONS[mode],
        targetEpochMs: null,       // deadline absoluto mientras corre
        pausedRemainingMs: null,   // ms restantes mientras está en pausa
        startedEpochMs: null,      // cuándo arrancó esta sesión (para "started_at" y el chequeo de vejez)
        projectId: null,
        taskId: null,
    };
}

let pomoState = createIdlePomoState();
let pomoIntervalId = null;
let audioCtx = null;

// ============================================
// Elementos del DOM
// ============================================

const pomoModeBtns = document.querySelectorAll('.pomodoro-mode-btn');
const pomoDisplay = document.getElementById('pomoDisplay');
const pomoStatusEl = document.getElementById('pomoStatus');
const pomoProjectSelect = document.getElementById('pomoProjectSelect');
const pomoTaskSelect = document.getElementById('pomoTaskSelect');
const pomoStartBtn = document.getElementById('pomoStartBtn');
const pomoPauseBtn = document.getElementById('pomoPauseBtn');
const pomoStopBtn = document.getElementById('pomoStopBtn');
const pomoSoundBtn = document.getElementById('pomoSoundBtn');
const pomoTodayEl = document.getElementById('pomoToday');

const pomodoroBar = document.getElementById('pomodoroBar');
const pomodoroBarProgress = document.getElementById('pomodoroBarProgress');
const pomodoroBarLabel = document.getElementById('pomodoroBarLabel');
const pomodoroBarTime = document.getElementById('pomodoroBarTime');
const pomodoroBarPauseBtn = document.getElementById('pomodoroBarPauseBtn');
const pomodoroBarStopBtn = document.getElementById('pomodoroBarStopBtn');

// ============================================
// Persistencia (localStorage)
// ============================================

function savePomoState() {
    try {
        localStorage.setItem(POMO_STORAGE_KEY, JSON.stringify(pomoState));
    } catch (e) {
        // localStorage puede lanzar en navegación privada; el timer sigue
        // funcionando en memoria, solo no sobrevive a un refresh.
    }
}

function clearPomoState() {
    try {
        localStorage.removeItem(POMO_STORAGE_KEY);
    } catch (e) {}
}

function loadPomoStateFromStorage() {
    try {
        const raw = localStorage.getItem(POMO_STORAGE_KEY);
        return raw ? JSON.parse(raw) : null;
    } catch (e) {
        return null;
    }
}

function isSoundEnabled() {
    try {
        return localStorage.getItem(POMO_SOUND_KEY) !== '0';
    } catch (e) {
        return true;
    }
}

function setSoundEnabled(enabled) {
    try {
        localStorage.setItem(POMO_SOUND_KEY, enabled ? '1' : '0');
    } catch (e) {}
}

// Cola de reintento: si el POST falla (backend caído, sin red), se guarda
// aquí y se reintenta al iniciar y tras cada envío exitoso.
function queuePendingSession(payload) {
    let pending = [];
    try {
        pending = JSON.parse(localStorage.getItem(POMO_PENDING_KEY) || '[]');
    } catch (e) {
        pending = [];
    }
    pending.push(payload);
    try {
        localStorage.setItem(POMO_PENDING_KEY, JSON.stringify(pending));
    } catch (e) {}
}

async function flushPendingSessions() {
    let pending;
    try {
        pending = JSON.parse(localStorage.getItem(POMO_PENDING_KEY) || '[]');
    } catch (e) {
        pending = [];
    }
    if (!pending.length) return;

    const stillPending = [];
    for (const payload of pending) {
        try {
            await apiFetch('/api/pomodoro', { method: 'POST', json: payload });
        } catch (error) {
            stillPending.push(payload);
        }
    }

    try {
        if (stillPending.length) {
            localStorage.setItem(POMO_PENDING_KEY, JSON.stringify(stillPending));
        } else {
            localStorage.removeItem(POMO_PENDING_KEY);
        }
    } catch (e) {}
}

async function postSession(payload) {
    try {
        await apiFetch('/api/pomodoro', { method: 'POST', json: payload });
    } catch (error) {
        console.error('Error al registrar sesión de pomodoro, se reintentará más tarde:', error);
        queuePendingSession(payload);
    }
}

// ============================================
// Helpers de tiempo
// ============================================

function getRemainingMs(state) {
    if (state.status === 'paused') return state.pausedRemainingMs;
    if (state.status === 'running') return state.targetEpochMs - Date.now();
    return state.plannedSeconds * 1000;
}

function formatClock(totalSeconds) {
    const s = Math.max(0, Math.round(totalSeconds));
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
}

// El backend guarda datetimes naive en UTC (igual que datetime.utcnow() en
// backend/auth.py). toISOString() ya está en UTC; solo hay que quitarle la
// 'Z' para que Pydantic lo interprete como naive en vez de aware.
function toNaiveUtcIso(epochMs) {
    return new Date(epochMs).toISOString().replace('Z', '');
}

function buildPayload(state, startedEpochMs, endedEpochMs, durationSeconds, wasCompleted) {
    return {
        project_id: state.projectId,
        task_id: state.taskId,
        session_date: getDateKey(new Date(startedEpochMs)), // fecha LOCAL de inicio
        started_at: toNaiveUtcIso(startedEpochMs),
        ended_at: toNaiveUtcIso(endedEpochMs),
        duration_seconds: durationSeconds,
        planned_seconds: state.plannedSeconds,
        mode: state.mode,
        was_completed: wasCompleted,
    };
}

// ============================================
// Ciclo del timer
// ============================================

function startTicking() {
    stopTicking();
    tickPomodoro();
    pomoIntervalId = setInterval(tickPomodoro, 250);
}

function stopTicking() {
    if (pomoIntervalId) {
        clearInterval(pomoIntervalId);
        pomoIntervalId = null;
    }
}

function tickPomodoro() {
    if (pomoState.status !== 'running') return;
    if (Date.now() >= pomoState.targetEpochMs) {
        finishPomodoro(pomoState.targetEpochMs, true);
        return;
    }
    renderPomoUI();
}

// Recalcula el tiempo restante en cuanto la pestaña vuelve a estar visible,
// en vez de esperar hasta el próximo tick de 250ms (que en una pestaña que
// estuvo en segundo plano puede tardar mucho en llegar).
document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible' && pomoState.status === 'running') {
        tickPomodoro();
    }
});

function startPomodoro() {
    if (pomoState.status !== 'idle') return;

    const mode = pomoState.mode;
    const plannedSeconds = POMO_DURATIONS[mode];
    const now = Date.now();

    pomoState = {
        status: 'running',
        mode,
        plannedSeconds,
        targetEpochMs: now + plannedSeconds * 1000,
        pausedRemainingMs: null,
        startedEpochMs: now,
        projectId: pomoProjectSelect.value ? Number(pomoProjectSelect.value) : null,
        taskId: pomoTaskSelect.value ? Number(pomoTaskSelect.value) : null,
    };

    // Debe crearse/reanudarse dentro de un gesto de usuario (este click) para
    // que el navegador permita reproducir audio más adelante.
    ensureAudioContext();

    pomoStatusEl.textContent = '';
    savePomoState();
    startTicking();
    renderPomoUI();
}

function pausePomodoro() {
    if (pomoState.status !== 'running') return;
    pomoState.pausedRemainingMs = pomoState.targetEpochMs - Date.now();
    pomoState.status = 'paused';
    stopTicking();
    savePomoState();
    renderPomoUI();
}

function resumePomodoro() {
    if (pomoState.status !== 'paused') return;
    pomoState.targetEpochMs = Date.now() + pomoState.pausedRemainingMs;
    pomoState.pausedRemainingMs = null;
    pomoState.status = 'running';
    savePomoState();
    startTicking();
    renderPomoUI();
}

async function stopPomodoro() {
    if (pomoState.status !== 'running' && pomoState.status !== 'paused') return;
    stopTicking();

    const finishedState = pomoState;
    const now = Date.now();
    const remainingMs = getRemainingMs(finishedState);
    const elapsedSeconds = Math.max(0, Math.round((finishedState.plannedSeconds * 1000 - remainingMs) / 1000));

    // Limpiar y volver a "idle" ANTES del await: la UI responde al instante
    // y localStorage queda libre sin esperar la respuesta de red.
    clearPomoState();
    pomoState = createIdlePomoState(finishedState.mode);
    renderPomoUI();

    const wasFocus = finishedState.mode === 'focus';

    if (wasFocus && elapsedSeconds >= POMO_MIN_LOG_SECONDS) {
        const payload = buildPayload(finishedState, finishedState.startedEpochMs, now, elapsedSeconds, false);
        await postSession(payload);
        await refreshTodaySeconds();
        await loadProjects();
        pomoStatusEl.textContent = `Sesión guardada (${formatClock(elapsedSeconds)}).`;
    } else if (wasFocus) {
        pomoStatusEl.textContent = 'Sesión descartada (menos de 1 minuto).';
    } else {
        pomoStatusEl.textContent = '';
    }
}

// announce=false se usa al rehidratar una sesión que terminó hace rato,
// para no sonar/mostrar el aviso de "completado" con horas de retraso.
async function finishPomodoro(endedEpochMs, announce) {
    stopTicking();

    const finishedState = pomoState;
    clearPomoState(); // primero: evita que otra pestaña reprocese la misma sesión
    pomoState = createIdlePomoState(finishedState.mode);
    renderPomoUI();

    const wasFocus = finishedState.mode === 'focus';

    if (wasFocus) {
        const payload = buildPayload(
            finishedState,
            finishedState.startedEpochMs,
            endedEpochMs,
            finishedState.plannedSeconds,
            true
        );
        await postSession(payload);
        await refreshTodaySeconds();
        await loadProjects();
    }

    if (announce) {
        playBeep();
        pomoStatusEl.textContent = wasFocus ? '¡Pomodoro completado!' : 'Descanso terminado.';
    }
}

// ============================================
// Render
// ============================================

function pomoBarLabelText() {
    const modeLabel = { focus: 'Enfoque', short_break: 'Descanso', long_break: 'Descanso largo' }[pomoState.mode];
    const project = projectsState.projects.find(p => p.id === pomoState.projectId);
    return project ? `${modeLabel} · ${project.name}` : modeLabel;
}

function renderPomoUI() {
    const remainingMs = getRemainingMs(pomoState);
    const remainingSeconds = Math.max(0, Math.ceil(remainingMs / 1000));
    const clock = formatClock(remainingSeconds);
    const isActive = pomoState.status === 'running' || pomoState.status === 'paused';

    pomoDisplay.textContent = clock;

    pomoStartBtn.classList.toggle('hidden', isActive);
    pomoPauseBtn.classList.toggle('hidden', !isActive);
    pomoStopBtn.classList.toggle('hidden', !isActive);
    pomoPauseBtn.textContent = pomoState.status === 'paused' ? 'Reanudar' : 'Pausar';

    pomoModeBtns.forEach(btn => {
        btn.classList.toggle('active', btn.dataset.mode === pomoState.mode);
        btn.disabled = isActive; // no cambiar de modo a mitad de sesión
    });
    pomoProjectSelect.disabled = isActive;
    pomoTaskSelect.disabled = isActive || !pomoProjectSelect.value;

    if (isActive) {
        pomodoroBar.classList.remove('hidden');
        document.body.classList.add('has-pomodoro-bar');

        const totalMs = pomoState.plannedSeconds * 1000;
        const progressPct = Math.min(100, Math.max(0, 100 - (remainingMs / totalMs) * 100));
        pomodoroBarProgress.style.width = `${progressPct}%`;
        pomodoroBarTime.textContent = clock;
        pomodoroBarLabel.textContent = pomoBarLabelText();
        pomodoroBarPauseBtn.textContent = pomoState.status === 'paused' ? '▶' : '⏸';
        pomodoroBarPauseBtn.setAttribute('aria-label', pomoState.status === 'paused' ? 'Reanudar' : 'Pausar');

        document.title = `⏱ ${clock} — Habit Tracker`;
    } else {
        pomodoroBar.classList.add('hidden');
        document.body.classList.remove('has-pomodoro-bar');
        document.title = 'Habit Tracker';
    }
}

// ============================================
// Sonido (WebAudio, sin Notification API — ver plan de la fase)
// ============================================

function ensureAudioContext() {
    if (!audioCtx) {
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        if (AudioContextClass) {
            audioCtx = new AudioContextClass();
        }
    }
    if (audioCtx && audioCtx.state === 'suspended') {
        audioCtx.resume().catch(() => {});
    }
}

function playBeep() {
    if (!isSoundEnabled() || !audioCtx) return;

    const now = audioCtx.currentTime;
    [880, 1320].forEach((freq, i) => {
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.frequency.value = freq;
        osc.connect(gain);
        gain.connect(audioCtx.destination);

        const start = now + i * 0.18;
        gain.gain.setValueAtTime(0, start);
        gain.gain.linearRampToValueAtTime(0.2, start + 0.02);
        gain.gain.linearRampToValueAtTime(0, start + 0.15);
        osc.start(start);
        osc.stop(start + 0.16);
    });
}

function updateSoundBtn() {
    const enabled = isSoundEnabled();
    pomoSoundBtn.textContent = enabled ? '🔊' : '🔇';
    const label = enabled ? 'Sonido activado' : 'Sonido desactivado';
    pomoSoundBtn.title = label;
    pomoSoundBtn.setAttribute('aria-label', label);
}

// ============================================
// Selects de proyecto / tarea
// ============================================

function populateProjectSelect() {
    const previousValue = pomoProjectSelect.value;
    pomoProjectSelect.innerHTML = '<option value="">Sin proyecto</option>';

    projectsState.projects.forEach(project => {
        const option = document.createElement('option');
        option.value = String(project.id);
        option.textContent = project.name;
        pomoProjectSelect.appendChild(option);
    });

    const stillExists = Array.from(pomoProjectSelect.options).some(o => o.value === previousValue);
    pomoProjectSelect.value = stillExists ? previousValue : '';

    populateTaskSelect();
}

async function populateTaskSelect() {
    const previousValue = pomoTaskSelect.value;
    pomoTaskSelect.innerHTML = '<option value="">Sin tarea</option>';
    const projectId = pomoProjectSelect.value;
    pomoTaskSelect.disabled = !projectId || pomoState.status !== 'idle';

    if (!projectId) return;

    try {
        const data = await apiFetch(`/api/tasks?project_id=${projectId}&include_done=false`);
        data.tasks.forEach(task => {
            const option = document.createElement('option');
            option.value = String(task.id);
            option.textContent = task.title;
            pomoTaskSelect.appendChild(option);
        });

        // Conservar la tarea elegida: ahora esto corre en cada cambio de tarea,
        // y marcar otra como hecha no debe perder la selección del usuario.
        const stillExists = Array.from(pomoTaskSelect.options).some(o => o.value === previousValue);
        pomoTaskSelect.value = stillExists ? previousValue : '';
    } catch (error) {
        console.error('Error al cargar tareas para el selector de pomodoro:', error);
    }
}

async function refreshTodaySeconds() {
    try {
        const stats = await apiFetch('/api/pomodoro/stats');
        pomoTodayEl.textContent = `Hoy: ${formatDuration(stats.today_seconds)}`;
    } catch (error) {
        console.error('Error al cargar estadísticas de pomodoro:', error);
    }
}

// ============================================
// Eventos
// ============================================

pomoModeBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        if (pomoState.status !== 'idle') return;
        pomoState.mode = btn.dataset.mode;
        pomoState.plannedSeconds = POMO_DURATIONS[pomoState.mode];
        renderPomoUI();
    });
});

pomoProjectSelect.addEventListener('change', populateTaskSelect);

pomoStartBtn.addEventListener('click', startPomodoro);

pomoPauseBtn.addEventListener('click', () => {
    if (pomoState.status === 'running') pausePomodoro();
    else if (pomoState.status === 'paused') resumePomodoro();
});

pomoStopBtn.addEventListener('click', stopPomodoro);

pomoSoundBtn.addEventListener('click', () => {
    setSoundEnabled(!isSoundEnabled());
    updateSoundBtn();
});

pomodoroBarPauseBtn.addEventListener('click', (event) => {
    event.stopPropagation();
    if (pomoState.status === 'running') pausePomodoro();
    else if (pomoState.status === 'paused') resumePomodoro();
});

pomodoroBarStopBtn.addEventListener('click', (event) => {
    event.stopPropagation();
    stopPomodoro();
});

// Tocar el cuerpo de la barra (no sus botones) lleva a la vista Proyectos.
pomodoroBar.addEventListener('click', () => {
    goToView(1);
});

// ============================================
// Logout: si hay una sesión de foco en curso, guardarla antes de perder el
// token (ver runHooks en script.js: este hook corre ANTES de removeToken()).
// ============================================

async function handlePomodoroLogout() {
    stopTicking();

    if (pomoState.status === 'running' || pomoState.status === 'paused') {
        const elapsedMs = pomoState.plannedSeconds * 1000 - getRemainingMs(pomoState);
        const elapsedSeconds = Math.max(0, Math.round(elapsedMs / 1000));

        if (pomoState.mode === 'focus' && elapsedSeconds >= POMO_MIN_LOG_SECONDS) {
            const payload = buildPayload(pomoState, pomoState.startedEpochMs, Date.now(), elapsedSeconds, false);
            try {
                await apiFetch('/api/pomodoro', { method: 'POST', json: payload });
            } catch (error) {
                console.error('No se pudo guardar la sesión de pomodoro al cerrar sesión:', error);
            }
        }
    }

    // A diferencia de las preferencias de hábitos (que handleLogout conserva
    // a propósito), un timer sin enviar pertenece a la cuenta que cierra
    // sesión: dejarlo en localStorage haría que el próximo usuario en este
    // dispositivo lo re-envíe bajo su propio user_id al rehidratar.
    pomoState = createIdlePomoState();
    clearPomoState();
    try { localStorage.removeItem(POMO_PENDING_KEY); } catch (e) {}
    renderPomoUI();
}

// ============================================
// Inicialización / rehidratación
// ============================================

async function initPomodoro() {
    updateSoundBtn();

    const stored = loadPomoStateFromStorage();

    if (!stored || Date.now() - (stored.startedEpochMs || 0) > POMO_STALE_MS) {
        if (stored) clearPomoState(); // estado viejo (ej. laptop dormida días): descartar
        renderPomoUI();
        await refreshTodaySeconds();
        await flushPendingSessions();
        return;
    }

    pomoState = stored;

    if (pomoState.status === 'paused') {
        renderPomoUI();
    } else if (pomoState.status === 'running' && Date.now() < pomoState.targetEpochMs) {
        startTicking();
        renderPomoUI();
    } else if (pomoState.status === 'running') {
        // Terminó mientras la pestaña estaba cerrada.
        const endedEpochMs = pomoState.targetEpochMs;
        const announce = Date.now() - endedEpochMs < 60000; // no sonar horas después
        await finishPomodoro(endedEpochMs, announce);
    } else {
        renderPomoUI();
    }

    await refreshTodaySeconds();
    await flushPendingSessions();
}

window.appInitHooks.push(initPomodoro);
// Los selects se llenan desde projectsState, así que se enganchan al hook de
// projects.js en vez de a appDataHooks: corre al cargar los proyectos (login)
// y además en cada alta, edición o borrado de proyecto o tarea, sin que el
// usuario tenga que recargar la página.
window.projectsChangedHooks.push(populateProjectSelect);
window.appLogoutHooks.push(handlePomodoroLogout);
