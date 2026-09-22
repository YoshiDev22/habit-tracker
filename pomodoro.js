// ============================================
// Constantes y estado
// ============================================

// El cronómetro (stopwatch) cuenta hacia arriba y no tiene duración planeada.
// Entra en el mapa con 0 para que nada lea undefined.
const POMO_DURATIONS = { focus: 1500, short_break: 300, long_break: 900, stopwatch: 0 }; // segundos
const POMO_MIN_LOG_SECONDS = 60; // debajo de esto, "Detener" descarta en vez de guardar
const POMO_STORAGE_KEY = 'pomodoro_state';
const POMO_PENDING_KEY = 'pomodoro_pending';
const POMO_SOUND_KEY = 'pomodoro_sound';
const POMO_STALE_MS = 24 * 60 * 60 * 1000; // rehidratar más viejo que esto: descartar
// El cronómetro no tiene final propio. Si se queda corriendo por olvido, se
// cierra solo al llegar a este tope y la sesión se guarda recortada, con nota.
const POMO_STOPWATCH_MAX_SECONDS = 8 * 60 * 60;
const POMO_AUTOCLOSE_NOTE = 'Cerrado automáticamente a las 8 h';

function createIdlePomoState(mode = 'focus') {
    return {
        status: 'idle',           // idle | running | paused
        mode,                      // focus | short_break | long_break | stopwatch
        plannedSeconds: POMO_DURATIONS[mode],
        targetEpochMs: null,       // deadline absoluto mientras corre (el cronómetro no lo usa)
        pausedRemainingMs: null,   // ms restantes mientras está en pausa (cuenta atrás)
        pausedAccumMs: 0,          // solo cronómetro: ms en pausa, que no cuentan como trabajo
        pausedAtEpochMs: null,     // solo cronómetro: cuándo se pausó, para congelar el transcurrido
        startedEpochMs: null,      // cuándo arrancó esta sesión (para "started_at" y el chequeo de vejez)
        projectId: null,
        taskId: null,
    };
}

let pomoState = createIdlePomoState();
let pomoIntervalId = null;
let audioCtx = null;
// Osciladores del pitido de fin ya encolados en el reloj de WebAudio.
let scheduledBeep = [];

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
    // Sin sesión no hay a quién atribuir las sesiones y el POST daría 401. Se
    // quedan en la cola de localStorage hasta el próximo login, que es
    // justamente para lo que existe la cola.
    if (!getToken()) return;

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
    // Sin sesión el POST daría 401 y acabaría igual en la cola, vía el catch.
    // Encolar directamente evita pedirle al servidor que lo rechace.
    if (!getToken()) {
        queuePendingSession(payload);
        return;
    }

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

function isStopwatch(state) {
    return state.mode === 'stopwatch';
}

// El cronómetro cuenta hacia arriba: su tiempo sale de cuándo arrancó, menos lo
// que estuvo en pausa. En pausa se congela en el instante de pausar.
function getElapsedMs(state) {
    if (!state.startedEpochMs) return 0;
    const until = state.status === 'paused' ? state.pausedAtEpochMs : Date.now();
    return Math.max(0, until - state.startedEpochMs - (state.pausedAccumMs || 0));
}

// formatClock() solo hace mm:ss, y pasada la hora mostraría "90:00".
function formatStopwatch(totalSeconds) {
    const s = Math.max(0, Math.round(totalSeconds));
    const h = Math.floor(s / 3600);
    const mm = String(Math.floor((s % 3600) / 60)).padStart(2, '0');
    const ss = String(s % 60).padStart(2, '0');
    return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
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

function buildPayload(state, startedEpochMs, endedEpochMs, durationSeconds, wasCompleted, note = null) {
    return {
        project_id: state.projectId,
        task_id: state.taskId,
        session_date: getDateKey(new Date(startedEpochMs)), // fecha LOCAL de inicio
        started_at: toNaiveUtcIso(startedEpochMs),
        ended_at: toNaiveUtcIso(endedEpochMs),
        duration_seconds: durationSeconds,
        planned_seconds: state.plannedSeconds,
        // El cronómetro se guarda como "focus" y se distingue por source: toda
        // la agregación del backend filtra mode == "focus", así que un modo
        // propio dejaría su tiempo fuera de los totales.
        mode: isStopwatch(state) ? 'focus' : state.mode,
        source: isStopwatch(state) ? 'stopwatch' : 'timer',
        was_completed: wasCompleted,
        note,
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

    if (isStopwatch(pomoState)) {
        // Sin meta: el único final automático es el tope de 8 h.
        if (getElapsedMs(pomoState) >= POMO_STOPWATCH_MAX_SECONDS * 1000) {
            finishStopwatch({ announce: true });
            return;
        }
        renderPomoUI();
        return;
    }

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
    const stopwatch = mode === 'stopwatch';
    const plannedSeconds = POMO_DURATIONS[mode];
    const now = Date.now();

    pomoState = {
        status: 'running',
        mode,
        plannedSeconds,
        targetEpochMs: stopwatch ? null : now + plannedSeconds * 1000,
        pausedRemainingMs: null,
        pausedAccumMs: 0,
        pausedAtEpochMs: null,
        startedEpochMs: now,
        projectId: pomoProjectSelect.value ? Number(pomoProjectSelect.value) : null,
        taskId: pomoTaskSelect.value ? Number(pomoTaskSelect.value) : null,
    };

    // Debe crearse/reanudarse dentro de un gesto de usuario (este click) para
    // que el navegador permita reproducir audio más adelante.
    ensureAudioContext();
    requestNotificationPermission();
    // El cronómetro no tiene final que anunciar; su aviso es el del tope.
    if (!stopwatch) scheduleEndBeep(plannedSeconds * 1000);

    pomoStatusEl.textContent = '';
    savePomoState();
    startTicking();
    renderPomoUI();
}

function pausePomodoro() {
    if (pomoState.status !== 'running') return;
    if (isStopwatch(pomoState)) {
        pomoState.pausedAtEpochMs = Date.now();
    } else {
        pomoState.pausedRemainingMs = pomoState.targetEpochMs - Date.now();
    }
    pomoState.status = 'paused';
    stopTicking();
    cancelScheduledBeep();
    savePomoState();
    renderPomoUI();
}

function resumePomodoro() {
    if (pomoState.status !== 'paused') return;

    if (isStopwatch(pomoState)) {
        // Lo que estuvo en pausa no cuenta como trabajado.
        pomoState.pausedAccumMs = (pomoState.pausedAccumMs || 0) + (Date.now() - pomoState.pausedAtEpochMs);
        pomoState.pausedAtEpochMs = null;
        pomoState.status = 'running';
        savePomoState();
        startTicking();
        renderPomoUI();
        return;
    }

    pomoState.targetEpochMs = Date.now() + pomoState.pausedRemainingMs;
    pomoState.pausedRemainingMs = null;
    pomoState.status = 'running';
    savePomoState();
    startTicking();
    scheduleEndBeep(pomoState.targetEpochMs - Date.now());
    renderPomoUI();
}

// Handler de los botones: así el evento del click no llega como opciones.
async function stopPomodoro() {
    await stopTimer();
}

async function stopTimer({ skipConfirm = false } = {}) {
    if (pomoState.status !== 'running' && pomoState.status !== 'paused') return;

    // Detener el cronómetro es justamente guardar el tiempo, así que no hay
    // nada que confirmar; el enfoque sí se pierde y por eso pregunta.
    if (isStopwatch(pomoState)) {
        await finishStopwatch({ announce: false });
        return;
    }

    // Por debajo del mínimo la sesión se descarta igual, así que no hay nada
    // que perder y preguntar solo estorba.
    const elapsedBeforeConfirm = Math.max(0, Math.round(
        (pomoState.plannedSeconds * 1000 - getRemainingMs(pomoState)) / 1000
    ));
    const worthConfirming = elapsedBeforeConfirm >= POMO_MIN_LOG_SECONDS;

    if (pomoState.mode === 'focus' && !skipConfirm && worthConfirming) {
        // Congelar el timer mientras se pregunta: el tick de 250ms no debe
        // poder terminar el pomodoro solo (finishPomodoro) con el diálogo
        // abierto. confirmDialog() está en script.js (global, igual que
        // apiFetch — ver CLAUDE.md).
        const wasRunning = pomoState.status === 'running';
        if (wasRunning) stopTicking();
        cancelScheduledBeep();

        const ok = await confirmDialog('¿Seguro que quieres irte? Vas a perder el enfoque en curso.', {
            confirmLabel: 'Sí, detener',
            cancelLabel: 'Seguir enfocado',
            danger: true
        });

        // Pudo terminar solo mientras se esperaba la respuesta (ej. el
        // listener de visibilitychange, si se cambió de pestaña y volvió).
        if (pomoState.status !== 'running' && pomoState.status !== 'paused') return;

        if (!ok) {
            if (wasRunning && pomoState.status === 'running') {
                startTicking();
                scheduleEndBeep(pomoState.targetEpochMs - Date.now());
            }
            return;
        }
    }

    stopTicking();
    cancelScheduledBeep();

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

// Cierra el cronómetro y guarda lo medido. Si se alcanzó el tope de 8 h, la
// duración se recorta ahí y la sesión queda con nota, para poder corregirla
// después con el ✎ del historial.
async function finishStopwatch({ announce }) {
    stopTicking();
    cancelScheduledBeep();

    const finishedState = pomoState;
    const maxMs = POMO_STOPWATCH_MAX_SECONDS * 1000;
    const elapsedMs = getElapsedMs(finishedState);
    const auto = elapsedMs >= maxMs;
    const durationSeconds = Math.round(Math.min(elapsedMs, maxMs) / 1000);
    // Reconstruye la hora de fin real: inicio + pausas + lo trabajado.
    const endedEpochMs = finishedState.startedEpochMs
        + (finishedState.pausedAccumMs || 0)
        + durationSeconds * 1000;

    clearPomoState();
    pomoState = createIdlePomoState(finishedState.mode);
    renderPomoUI();

    if (durationSeconds >= POMO_MIN_LOG_SECONDS) {
        const payload = buildPayload(
            finishedState,
            finishedState.startedEpochMs,
            endedEpochMs,
            durationSeconds,
            true,
            auto ? POMO_AUTOCLOSE_NOTE : null
        );
        await postSession(payload);
        await refreshTodaySeconds();
        await loadProjects();
        pomoStatusEl.textContent = auto
            ? `Cronómetro cerrado solo a las 8 h. Tiempo guardado (${formatStopwatch(durationSeconds)}).`
            : `Tiempo guardado (${formatStopwatch(durationSeconds)}).`;
    } else {
        pomoStatusEl.textContent = 'Tiempo descartado (menos de 1 minuto).';
    }

    if (announce) {
        if (scheduledBeep.length === 0) playBeep();
        scheduledBeep = [];
        notifyPomodoroEnd('stopwatch');
    }
}

// Globales a propósito: las llaman projects.js (▶ de cada tarea) y board.js
// (▶ de cada tarjeta), igual que ya usan apiFetch o hideHabitPopover del
// núcleo (ver CLAUDE.md). mode: 'stopwatch' o 'focus'.
async function startTimerForTask(projectId, taskId, mode = 'stopwatch', taskTitle = '') {
    if (pomoState.status !== 'idle') {
        const enCurso = isStopwatch(pomoState) ? 'un cronómetro' : 'un pomodoro';
        const nuevo = mode === 'stopwatch' ? 'el cronómetro' : 'un pomodoro';
        const ok = await confirmDialog(
            `Ya tienes ${enCurso} en curso. ¿Lo detienes y arrancas ${nuevo} en esta tarea?`,
            { confirmLabel: 'Detener y empezar', cancelLabel: 'Dejarlo como está' }
        );
        if (!ok) return;

        // Ya se confirmó aquí, así que el enfoque no vuelve a preguntar.
        await stopTimer({ skipConfirm: true });
        if (pomoState.status !== 'idle') return; // algo falló: no encadenar
    }

    pomoState = createIdlePomoState(mode);
    pomoProjectSelect.value = String(projectId);
    await populateTaskSelect();
    // El select solo lista tareas pendientes, y desde el tablero se puede
    // cronometrar una tarjeta de cualquier columna, "Hecho" incluida.
    if (!Array.from(pomoTaskSelect.options).some(o => o.value === String(taskId))) {
        const option = document.createElement('option');
        option.value = String(taskId);
        option.textContent = taskTitle || 'Tarea';
        pomoTaskSelect.appendChild(option);
    }
    pomoTaskSelect.value = String(taskId);
    startPomodoro();
    goToView(1);
}

function startStopwatchForTask(projectId, taskId) {
    return startTimerForTask(projectId, taskId, 'stopwatch');
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
        // Si el pitido estaba programado, ya sonó a su hora aunque este código
        // llegue tarde por el frenado de la pestaña; volver a llamarlo aquí
        // haría sonar el aviso dos veces.
        if (scheduledBeep.length === 0) {
            playBeep();
        }
        scheduledBeep = [];

        notifyPomodoroEnd(finishedState.mode);
        pomoStatusEl.textContent = wasFocus ? '¡Pomodoro completado!' : 'Descanso terminado.';
    } else {
        cancelScheduledBeep();
    }
}

// ============================================
// Render
// ============================================

function pomoBarLabelText() {
    const modeLabel = {
        focus: 'Enfoque',
        short_break: 'Descanso',
        long_break: 'Descanso largo',
        stopwatch: 'Cronómetro',
    }[pomoState.mode];
    const project = projectsState.projects.find(p => p.id === pomoState.projectId);
    return project ? `${modeLabel} · ${project.name}` : modeLabel;
}

function renderPomoUI() {
    const isActive = pomoState.status === 'running' || pomoState.status === 'paused';

    // El cronómetro cuenta hacia arriba y su "progreso" es sobre el tope de 8 h,
    // que es lo único que acota su duración.
    let clock;
    let progressPct;
    if (isStopwatch(pomoState)) {
        const elapsedSeconds = Math.floor(getElapsedMs(pomoState) / 1000);
        clock = formatStopwatch(elapsedSeconds);
        progressPct = Math.min(100, (elapsedSeconds / POMO_STOPWATCH_MAX_SECONDS) * 100);
    } else {
        const remainingMs = getRemainingMs(pomoState);
        clock = formatClock(Math.max(0, Math.ceil(remainingMs / 1000)));
        const totalMs = pomoState.plannedSeconds * 1000;
        progressPct = Math.min(100, Math.max(0, 100 - (remainingMs / totalMs) * 100));
    }

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

    // Marca la fila de la tarea que se está cronometrando. projects.js la
    // repinta en cada render de proyectos, así que aquí solo se ajusta la clase.
    document.querySelectorAll('.task-row.timing').forEach(row => row.classList.remove('timing'));
    if (isActive && pomoState.taskId) {
        const row = document.querySelector(`.task-row[data-task-id="${pomoState.taskId}"]`);
        if (row) row.classList.add('timing');
    }
}

// ============================================
// Sonido (WebAudio) y avisos del sistema (Notification API)
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

// Dos tonos cortos y ascendentes (la 880 Hz, mi 1320 Hz). Sintetizados, sin
// archivo de audio que descargar.
function playBeepAt(startTime) {
    if (!isSoundEnabled() || !audioCtx) return [];

    const oscillators = [];
    [880, 1320].forEach((freq, i) => {
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.frequency.value = freq;
        osc.connect(gain);
        gain.connect(audioCtx.destination);

        const start = startTime + i * 0.18;
        gain.gain.setValueAtTime(0, start);
        gain.gain.linearRampToValueAtTime(0.2, start + 0.02);
        gain.gain.linearRampToValueAtTime(0, start + 0.15);
        osc.start(start);
        osc.stop(start + 0.16);
        oscillators.push(osc);
    });
    return oscillators;
}

function playBeep() {
    if (!audioCtx) return;
    playBeepAt(audioCtx.currentTime);
}

// El tick de setInterval se frena en pestañas de segundo plano, así que
// esperar a que el tick detecte el final haría sonar el aviso tarde. El reloj
// de WebAudio no se frena: dejando el pitido programado a una hora exacta
// suena puntual aunque estés en otra pestaña.
function scheduleEndBeep(remainingMs) {
    cancelScheduledBeep();
    if (!isSoundEnabled() || !audioCtx || remainingMs <= 0) return;
    scheduledBeep = playBeepAt(audioCtx.currentTime + remainingMs / 1000);
}

function cancelScheduledBeep() {
    scheduledBeep.forEach(osc => {
        try { osc.stop(); } catch (e) {}
    });
    scheduledBeep = [];
}

// La notificación del sistema es lo que te avisa estés donde estés, incluso
// con el navegador de fondo. Pedir permiso exige un gesto del usuario, así que
// se pide al pulsar Iniciar y no al cargar la página.
function requestNotificationPermission() {
    if (typeof Notification === 'undefined' || Notification.permission !== 'default') return;
    try {
        Notification.requestPermission().catch(() => {});
    } catch (e) {}
}

function notifyPomodoroEnd(mode) {
    if (typeof Notification === 'undefined' || Notification.permission !== 'granted') return;

    const titles = {
        focus: '¡Pomodoro completado!',
        short_break: 'Descanso terminado',
        long_break: 'Descanso largo terminado',
        stopwatch: 'Cronómetro cerrado',
    };
    const bodies = {
        focus: 'Hora de descansar.',
        stopwatch: 'Llevaba 8 horas corriendo. El tiempo quedó guardado.',
    };
    try {
        new Notification(titles[mode] || 'Pomodoro', {
            body: bodies[mode] || 'Hora de volver al trabajo.',
            // Reemplaza el aviso anterior en vez de apilarlos.
            tag: 'pomodoro-end',
        });
    } catch (e) {}
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
    // initPomodoro corre desde appInitHooks, que initApp() ejecuta también sin
    // sesión (pantalla de login). Sin esta guarda, cada visita al login deja un
    // 401 en el log del servidor. Mismo patrón que loadHabitsFromAPI.
    if (!getToken()) return;

    try {
        // Fecha LOCAL: con la del servidor (UTC), "Hoy" se reiniciaría a
        // medianoche UTC en vez de a la del usuario.
        const stats = await apiFetch(`/api/pomodoro/stats?today=${getDateKey(new Date())}`);
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
    // El pitido se encola al arrancar: si el sonido se enciende o se apaga con
    // el timer corriendo, hay que rehacer esa reserva.
    // El cronómetro no encola pitido de fin: no tiene final que programar.
    if (pomoState.status === 'running' && !isStopwatch(pomoState)) {
        ensureAudioContext();
        scheduleEndBeep(pomoState.targetEpochMs - Date.now());
    } else {
        cancelScheduledBeep();
    }
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
        // El cronómetro deriva su tiempo de getElapsedMs; restar getRemainingMs
        // daría NaN, porque no tiene targetEpochMs.
        const stopwatch = isStopwatch(pomoState);
        const elapsedMs = stopwatch
            ? getElapsedMs(pomoState)
            : pomoState.plannedSeconds * 1000 - getRemainingMs(pomoState);
        const elapsedSeconds = Math.max(0, Math.round(elapsedMs / 1000));

        if ((stopwatch || pomoState.mode === 'focus') && elapsedSeconds >= POMO_MIN_LOG_SECONDS) {
            const payload = buildPayload(pomoState, pomoState.startedEpochMs, Date.now(), elapsedSeconds, stopwatch);
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

    // El cronómetro NO se descarta por viejo: eso sería tirar trabajo real. Si
    // pasó del tope se guarda recortado a 8 h; si no, sigue contando.
    if (stored && stored.mode === 'stopwatch' && (stored.status === 'running' || stored.status === 'paused')) {
        pomoState = stored;
        if (getElapsedMs(pomoState) >= POMO_STOPWATCH_MAX_SECONDS * 1000) {
            await finishStopwatch({ announce: false });
        } else {
            if (pomoState.status === 'running') startTicking();
            renderPomoUI();
        }
        await refreshTodaySeconds();
        await flushPendingSessions();
        return;
    }

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
        // Tras recargar la página no hay gesto del usuario todavía, así que el
        // navegador no deja crear el AudioContext y esto no encola nada. En ese
        // caso el aviso depende del tick, que basta con la pestaña delante; en
        // cuanto se toque cualquier control del timer vuelve a programarse.
        scheduleEndBeep(pomoState.targetEpochMs - Date.now());
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

// ============================================
// Registro manual de tiempo
// ============================================

const logTimeModal = document.getElementById('logTimeModal');
const logTimeForm = document.getElementById('logTimeForm');
const logTimeProjectEl = document.getElementById('logTimeProject');
const logTimeDateEl = document.getElementById('logTimeDate');
const logTimeHoursEl = document.getElementById('logTimeHours');
const logTimeMinutesEl = document.getElementById('logTimeMinutes');
const logTimeStartEl = document.getElementById('logTimeStart');
const logTimeEndEl = document.getElementById('logTimeEnd');
const logTimeDurationEl = document.getElementById('logTimeDuration');
const logTimeTaskEl = document.getElementById('logTimeTask');
const logTimeNoteEl = document.getElementById('logTimeNote');
const logTimeErrorEl = document.getElementById('logTimeError');
const logTimeTitleEl = document.getElementById('logTimeTitle');
const logTimeSubmitBtn = document.getElementById('logTimeSubmitBtn');

let logTimeProjectId = null;
// null = registro nuevo; un id = se está corrigiendo ese registro.
let logTimeSessionId = null;

// "HH:MM" del <input type="time"> a segundos desde medianoche.
function parseClockValue(value) {
    const match = /^(\d{2}):(\d{2})$/.exec(value || '');
    if (!match) return null;
    return Number(match[1]) * 3600 + Number(match[2]) * 60;
}

function logTimeDurationSeconds() {
    const start = parseClockValue(logTimeStartEl.value);
    const end = parseClockValue(logTimeEndEl.value);
    if (start === null || end === null || end <= start) return null;
    return end - start;
}

function renderLogTimeDuration() {
    const seconds = logTimeDurationSeconds();
    logTimeDurationEl.textContent = seconds === null
        ? 'Duración: —'
        : `Duración: ${formatDuration(seconds)}`;
}

function secondsToClockValue(secondsFromMidnight) {
    const hours = Math.floor(secondsFromMidnight / 3600);
    const minutes = Math.floor((secondsFromMidnight % 3600) / 60);
    return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`;
}

// Duración escrita a mano -> horas de inicio y fin. El fin es la hora actual
// (al minuto, que es la resolución de <input type="time">) y el inicio sale de
// restarle el rato indicado.
function applyTypedDuration() {
    const hours = Number(logTimeHoursEl.value) || 0;
    const minutes = Number(logTimeMinutesEl.value) || 0;
    const requested = hours * 3600 + minutes * 60;

    if (requested <= 0) {
        return;
    }

    const now = new Date();
    let end = now.getHours() * 3600 + now.getMinutes() * 60;
    let start = end - requested;

    // El rato no cabe antes de la hora actual: cruzaría a ayer, y una sesión
    // que salta la medianoche no se puede representar con dos horas del mismo
    // día. Se ancla al arranque del día y se avisa, en vez de guardar un rango
    // inválido en silencio.
    let clamped = false;
    if (start < 0) {
        start = 0;
        clamped = true;
    }

    logTimeStartEl.value = secondsToClockValue(start);
    logTimeEndEl.value = secondsToClockValue(end);
    renderLogTimeDuration();

    if (clamped) {
        logTimeDurationEl.textContent += ' — ajustado, ese rato empezaba ayer';
        syncTypedDurationFields();
    }
}

// El camino inverso: si se corrigen las horas a mano, los campos de duración
// dejan de mentir.
function syncTypedDurationFields() {
    const seconds = logTimeDurationSeconds();
    if (seconds === null) {
        return;
    }
    logTimeHoursEl.value = String(Math.floor(seconds / 3600));
    logTimeMinutesEl.value = String(Math.floor((seconds % 3600) / 60));
}

async function fillLogTimeTasks(projectId) {
    logTimeTaskEl.innerHTML = '<option value="">Sin tarea</option>';
    try {
        const data = await apiFetch(`/api/tasks?project_id=${projectId}&include_done=false`);
        data.tasks.forEach(task => {
            const option = document.createElement('option');
            option.value = String(task.id);
            option.textContent = task.title;
            logTimeTaskEl.appendChild(option);
        });
    } catch (error) {
        console.warn('Could not load tasks for the time log:', error);
    }
}

async function openLogTimeModal(projectId, session = null) {
    const project = projectsState.projects.find(p => p.id === projectId);
    if (!project) return;

    logTimeProjectId = projectId;
    logTimeSessionId = session ? session.id : null;
    logTimeProjectEl.textContent = project.name;
    logTimeTitleEl.textContent = session ? 'Editar registro' : 'Registrar tiempo';
    logTimeSubmitBtn.textContent = session ? 'Guardar cambios' : 'Guardar';

    // El calendario nativo abre en el día actual y no deja elegir futuro.
    const today = getDateKey(new Date());
    logTimeDateEl.max = today;

    if (session) {
        // Las horas se pintan en local: el backend las guarda en UTC sin 'Z'.
        const start = parseUtcIso(session.started_at);
        const end = parseUtcIso(session.ended_at);
        logTimeDateEl.value = session.session_date;
        logTimeStartEl.value = secondsToClockValue(start.getHours() * 3600 + start.getMinutes() * 60);
        logTimeEndEl.value = secondsToClockValue(end.getHours() * 3600 + end.getMinutes() * 60);
        logTimeNoteEl.value = session.note || '';
        renderLogTimeDuration();
        syncTypedDurationFields();
    } else {
        logTimeDateEl.value = today;
        logTimeHoursEl.value = '';
        logTimeMinutesEl.value = '';
        logTimeStartEl.value = '';
        logTimeEndEl.value = '';
        logTimeNoteEl.value = '';
        renderLogTimeDuration();
    }

    showModal(logTimeModal);

    // Después de mostrar, porque la lista viene de la red: al editar hay que
    // esperarla para poder preseleccionar la tarea del registro.
    await fillLogTimeTasks(projectId);
    if (session && session.task_id) {
        logTimeTaskEl.value = String(session.task_id);
    }
}

// "2026-09-08" + segundos desde medianoche -> instante LOCAL, y de ahí a UTC
// naive con el mismo helper que usa el timer, para que ambos orígenes queden
// guardados en el mismo formato.
function localEpochMs(dateKey, secondsFromMidnight) {
    const [year, month, day] = dateKey.split('-').map(Number);
    return new Date(year, month - 1, day, 0, 0, 0, 0).getTime() + secondsFromMidnight * 1000;
}

async function submitLogTime(event) {
    event.preventDefault();
    logTimeErrorEl.classList.add('hidden');

    const duration = logTimeDurationSeconds();
    if (duration === null) {
        showError(logTimeErrorEl, 'La hora de fin debe ser posterior a la de inicio.');
        return;
    }

    const dateKey = logTimeDateEl.value;
    if (dateKey > getDateKey(new Date())) {
        showError(logTimeErrorEl, 'No se puede registrar trabajo en una fecha futura.');
        return;
    }

    const startedEpochMs = localEpochMs(dateKey, parseClockValue(logTimeStartEl.value));
    const taskId = logTimeTaskEl.value ? Number(logTimeTaskEl.value) : null;
    const note = logTimeNoteEl.value.trim();

    // Al corregir, la duración es siempre el rango de horas que se ve en el
    // formulario: si no, un registro editado podría mostrar unas horas y
    // contar otra cosa distinta en los totales.
    const payload = {
        task_id: taskId,
        session_date: dateKey,
        started_at: toNaiveUtcIso(startedEpochMs),
        ended_at: toNaiveUtcIso(startedEpochMs + duration * 1000),
        duration_seconds: duration,
        note: note || null,
    };

    try {
        if (logTimeSessionId) {
            await apiFetch(`/api/pomodoro/${logTimeSessionId}`, { method: 'PATCH', json: payload });
        } else {
            await apiFetch('/api/pomodoro', {
                method: 'POST',
                json: {
                    ...payload,
                    project_id: logTimeProjectId,
                    planned_seconds: duration,
                    mode: 'focus',
                    was_completed: true,
                    source: 'manual',
                }
            });
        }

        hideModal(logTimeModal);
        // loadProjects() dispara projectsChangedHooks, que refresca el "Hoy".
        await loadProjects();
    } catch (error) {
        showError(logTimeErrorEl, error.message);
    }
}

projectsList.addEventListener('click', (event) => {
    const logBtn = event.target.closest('.project-log-time');
    if (logBtn) {
        openLogTimeModal(Number(logBtn.closest('.project-card').dataset.projectId));
        return;
    }

    const editBtn = event.target.closest('.session-edit');
    if (editBtn) {
        const projectId = Number(editBtn.closest('.task-list').dataset.projectId);
        const sessionId = Number(editBtn.closest('.session-row').dataset.sessionId);
        const session = (projectsState.sessionsByProject[projectId] || []).find(s => s.id === sessionId);
        if (session) openLogTimeModal(projectId, session);
    }
});

logTimeForm.addEventListener('submit', submitLogTime);
logTimeHoursEl.addEventListener('input', applyTypedDuration);
logTimeMinutesEl.addEventListener('input', applyTypedDuration);
logTimeStartEl.addEventListener('input', () => {
    renderLogTimeDuration();
    syncTypedDurationFields();
});
logTimeEndEl.addEventListener('input', () => {
    renderLogTimeDuration();
    syncTypedDurationFields();
});
document.getElementById('closeLogTimeBtn').addEventListener('click', () => hideModal(logTimeModal));
logTimeModal.querySelector('.modal-overlay').addEventListener('click', () => hideModal(logTimeModal));

window.appInitHooks.push(initPomodoro);
// initPomodoro solo corre al cargar la página. Sin esto, una sesión que quedó
// pendiente por un 401 esperaría a un F5: iniciar sesión otra vez en la misma
// pestaña no la reenviaba.
window.appDataHooks.push(flushPendingSessions);
// Los selects se llenan desde projectsState, así que se enganchan al hook de
// projects.js en vez de a appDataHooks: corre al cargar los proyectos (login)
// y además en cada alta, edición o borrado de proyecto o tarea, sin que el
// usuario tenga que recargar la página.
window.projectsChangedHooks.push(populateProjectSelect);
// El total de hoy cambia al registrar tiempo a mano, no solo al terminar un
// pomodoro, y ese registro pasa por loadProjects().
window.projectsChangedHooks.push(refreshTodaySeconds);
window.appLogoutHooks.push(handlePomodoroLogout);
