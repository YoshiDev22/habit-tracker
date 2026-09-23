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
// Al llegar al tope, si no se tocó la app en este rato, se pregunta en vez de
// guardar 8 h: lo más probable es que el cronómetro se olvidara.
const POMO_IDLE_ASK_MS = 2 * 60 * 60 * 1000;
const POMO_ACTIVITY_KEY = 'pomodoro_activity';

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
        taskTitle: null,           // para la barra: "Cronómetro · Rediseño kanban"
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

// La tarjeta del reloj ya no existe: el tiempo se inicia desde las tarjetas
// del tablero (startTimerForTask) y se controla desde la barra flotante. De
// ella solo quedan "Hoy" y el botón de sonido, en la barra del tablero.
const pomoSoundBtn = document.getElementById('pomoSoundBtn');
const pomoTodayEl = document.getElementById('pomoToday');

const pomodoroBar = document.getElementById('pomodoroBar');
const pomodoroBarProgress = document.getElementById('pomodoroBarProgress');
const pomodoroBarLabel = document.getElementById('pomodoroBarLabel');
const pomodoroBarTime = document.getElementById('pomodoroBarTime');
const pomodoroBarPauseBtn = document.getElementById('pomodoroBarPauseBtn');
const pomodoroBarStopBtn = document.getElementById('pomodoroBarStopBtn');
const pomodoroBarActions = document.getElementById('pomodoroBarActions');

// ============================================
// Persistencia (localStorage)
// ============================================

// false si localStorage no deja escribir: entonces no hay estado compartido
// entre pestañas que reclamar (ver claimPomoState).
let pomoStorageWorks = true;

function savePomoState() {
    try {
        localStorage.setItem(POMO_STORAGE_KEY, JSON.stringify(pomoState));
        pomoStorageWorks = true;
    } catch (e) {
        // localStorage puede lanzar en navegación privada; el timer sigue
        // funcionando en memoria, solo no sobrevive a un refresh.
        pomoStorageWorks = false;
    }
}

// Lock entre pestañas del mismo navegador (Web Locks). Sin la API (navegador
// viejo, o http que no sea localhost) corre sin lock.
function withPomoLock(name, fn) {
    if (navigator.locks && navigator.locks.request) {
        return navigator.locks.request(name, fn);
    }
    return Promise.resolve().then(fn);
}

// Cada pestaña abierta lleva su copia del timer en memoria, así que al
// terminar o detener, dos pestañas guardarían la misma sesión (pasaba con una
// pestaña restaurada al reabrir el navegador más otra nueva). La guarda solo
// la que la reclama: la sigue encontrando en pomodoro_state y la borra, dentro
// del lock. La otra la encuentra ya borrada y no la envía.
async function claimPomoState(state) {
    if (!pomoStorageWorks) return true;
    return withPomoLock('habit-tracker-pomodoro-state', () => {
        const stored = loadPomoStateFromStorage();
        if (!stored || stored.startedEpochMs !== state.startedEpochMs) return false;
        clearPomoState();
        return true;
    });
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

function readPendingSessions() {
    try {
        return JSON.parse(localStorage.getItem(POMO_PENDING_KEY) || '[]');
    } catch (e) {
        return [];
    }
}

// Al arrancar se llama dos veces (appDataHooks y el final de initPomodoro), y
// cada pestaña abierta la llama también: dos vaciados a la vez enviaban dos
// veces la misma sesión. Uno a la vez: en esta pestaña se comparte la promesa
// en curso, y entre pestañas lo ordena el lock.
let pendingFlush = null;

function flushPendingSessions() {
    if (!pendingFlush) {
        pendingFlush = withPomoLock('habit-tracker-pomodoro-pending', flushPendingNow)
            .finally(() => { pendingFlush = null; });
    }
    return pendingFlush;
}

async function flushPendingNow() {
    // Sin sesión no hay a quién atribuir las sesiones y el POST daría 401. Se
    // quedan en la cola de localStorage hasta el próximo login, que es
    // justamente para lo que existe la cola.
    if (!getToken()) return;

    const pending = readPendingSessions();
    if (!pending.length) return;

    const sent = [];
    for (const payload of pending) {
        try {
            await apiFetch('/api/pomodoro', { method: 'POST', json: payload });
            sent.push(JSON.stringify(payload));
        } catch (error) {
            // se queda en la cola
        }
    }

    // Se relee la cola en vez de sobrescribirla: lo que se encoló mientras se
    // enviaba (otro POST que falló) se perdía.
    const remaining = readPendingSessions().filter(payload => {
        const index = sent.indexOf(JSON.stringify(payload));
        if (index === -1) return true;
        sent.splice(index, 1);
        return false;
    });
    try {
        if (remaining.length) {
            localStorage.setItem(POMO_PENDING_KEY, JSON.stringify(remaining));
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
function getElapsedMs(state, atEpochMs = Date.now()) {
    if (!state.startedEpochMs) return 0;
    const until = state.status === 'paused' ? Math.min(state.pausedAtEpochMs, atEpochMs) : atEpochMs;
    return Math.max(0, until - state.startedEpochMs - (state.pausedAccumMs || 0));
}

// ============================================
// Cronómetro olvidado
// ============================================
//
// Se guarda la última vez que se tocó la app (clic o tecla, en cualquier
// pestaña; como mucho una escritura cada 30 s). Nada interrumpe mientras se
// trabaja: solo al llegar al tope de 8 h, y si no hubo actividad en las últimas
// 2 h, el cronómetro se detiene y pregunta si guardar hasta la última actividad
// o las 8 h. Con actividad reciente se cierra solo a las 8 h, como siempre.

let lastActivityWrite = 0;

function recordActivity(force = false) {
    const now = Date.now();
    if (!force && now - lastActivityWrite < 30000) return;
    lastActivityWrite = now;
    try {
        localStorage.setItem(POMO_ACTIVITY_KEY, String(now));
    } catch (e) {}
}

// La última actividad dentro de esta sesión: nunca antes de que empezara
function lastActivityFor(state) {
    let stored = 0;
    try {
        stored = Number(localStorage.getItem(POMO_ACTIVITY_KEY)) || 0;
    } catch (e) {}
    return Math.max(stored, state.startedEpochMs || 0);
}

function isIdleStopwatch() {
    return isStopwatch(pomoState) && pomoState.status === 'running'
        && Date.now() - lastActivityFor(pomoState) >= POMO_IDLE_ASK_MS;
}

['pointerdown', 'keydown'].forEach(type => {
    // La pregunta misma no cuenta: contestarla no debe mover la última actividad
    document.addEventListener(type, (event) => {
        if (event.target.closest && event.target.closest('#idleCheckModal')) return;
        recordActivity();
    }, { capture: true, passive: true });
});

const idleCheckModal = document.getElementById('idleCheckModal');
const idleCheckMessage = document.getElementById('idleCheckMessage');
const idleCheckSaveBtn = document.getElementById('idleCheckSaveBtn');
const idleCheckKeepBtn = document.getElementById('idleCheckKeepBtn');
let idleCheckLastActivity = null;   // fijada al preguntar: hasta dónde se guarda

function clockLabel(epochMs) {
    const d = new Date(epochMs);
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

function askIdleStopwatch() {
    if (!idleCheckModal.classList.contains('hidden')) return;
    idleCheckLastActivity = lastActivityFor(pomoState);
    const untilLast = Math.round(getElapsedMs(pomoState, idleCheckLastActivity) / 1000);
    const task = pomoState.taskTitle ? ` de «${pomoState.taskTitle}»` : '';
    const day = new Date(idleCheckLastActivity).toDateString() === new Date().toDateString() ? '' : ' de ayer';
    idleCheckMessage.textContent = `El cronómetro${task} llegó al tope de 8 h. `
        + `Tu última actividad en la app fue a las ${clockLabel(idleCheckLastActivity)}${day}.`;
    idleCheckSaveBtn.textContent = `Guardar hasta las ${clockLabel(idleCheckLastActivity)} (${formatDuration(untilLast)})`;
    showModal(idleCheckModal);
}

function closeIdleCheck() {
    hideModal(idleCheckModal);
    idleCheckLastActivity = null;
}

idleCheckSaveBtn.addEventListener('click', async () => {
    const until = idleCheckLastActivity;
    closeIdleCheck();
    if (!isStopwatch(pomoState) || pomoState.status === 'idle') return;
    await finishStopwatch({ announce: false, endAtEpochMs: until });
});

// "Guardar las 8 h": el cierre de siempre, recortado al tope y con su nota
idleCheckKeepBtn.addEventListener('click', async () => {
    closeIdleCheck();
    if (!isStopwatch(pomoState) || pomoState.status === 'idle') return;
    await finishStopwatch({ announce: false });
});

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
        // Sin meta: el único final automático es el tope de 8 h. Si para
        // entonces nadie tocó la app, se detiene y pregunta en vez de guardar 8 h.
        if (getElapsedMs(pomoState) >= POMO_STOPWATCH_MAX_SECONDS * 1000) {
            if (isIdleStopwatch()) {
                stopTicking();
                askIdleStopwatch();
                renderPomoUI();
                return;
            }
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

// Arranca el modo que tenga pomoState (el idle lo trae de createIdlePomoState)
// apuntando a este proyecto y tarea; los descansos van sin ninguno.
function startPomodoro(projectId = null, taskId = null, taskTitle = null) {
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
        projectId,
        taskId,
        taskTitle,
    };

    // Debe crearse/reanudarse dentro de un gesto de usuario (este click) para
    // que el navegador permita reproducir audio más adelante.
    ensureAudioContext();
    requestNotificationPermission();
    // El cronómetro no tiene final que anunciar; su aviso es el del tope.
    if (!stopwatch) scheduleEndBeep(plannedSeconds * 1000);

    clearBarMessage();
    recordActivity(true);
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

    // Reclamar y volver a "idle" ANTES del POST: la UI responde al instante
    // y localStorage queda libre sin esperar la respuesta de red.
    const claimed = await claimPomoState(finishedState);
    pomoState = createIdlePomoState(finishedState.mode);
    renderPomoUI();

    const wasFocus = finishedState.mode === 'focus';

    if (!claimed) {
        showBarMessage('Esta sesión ya se guardó desde otra pestaña.');
    } else if (wasFocus && elapsedSeconds >= POMO_MIN_LOG_SECONDS) {
        const payload = buildPayload(finishedState, finishedState.startedEpochMs, now, elapsedSeconds, false);
        await postSession(payload);
        await refreshTodaySeconds();
        await loadProjects();
        showBarMessage(`Sesión guardada (${formatClock(elapsedSeconds)}).`);
    } else if (wasFocus) {
        showBarMessage('Sesión descartada (menos de 1 minuto).');
    }
}

// Cierra el cronómetro y guarda lo medido. Si se alcanzó el tope de 8 h, la
// duración se recorta ahí y la sesión queda con nota, para poder corregirla
// después con el ✎ del historial.
// endAtEpochMs: guardar solo hasta ese momento (la última actividad, cuando
// se contesta al cronómetro olvidado).
async function finishStopwatch({ announce, endAtEpochMs = Date.now() }) {
    stopTicking();
    cancelScheduledBeep();
    if (!idleCheckModal.classList.contains('hidden')) closeIdleCheck();

    const finishedState = pomoState;
    const maxMs = POMO_STOPWATCH_MAX_SECONDS * 1000;
    const elapsedMs = getElapsedMs(finishedState, endAtEpochMs);
    const auto = elapsedMs >= maxMs;
    const durationSeconds = Math.round(Math.min(elapsedMs, maxMs) / 1000);
    // Reconstruye la hora de fin real: inicio + pausas + lo trabajado.
    const endedEpochMs = finishedState.startedEpochMs
        + (finishedState.pausedAccumMs || 0)
        + durationSeconds * 1000;

    const claimed = await claimPomoState(finishedState);
    pomoState = createIdlePomoState(finishedState.mode);
    renderPomoUI();

    if (!claimed) {
        showBarMessage('Este tiempo ya se guardó desde otra pestaña.');
        return;
    }

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
        showBarMessage(auto
            ? `Cronómetro cerrado solo a las 8 h. Tiempo guardado (${formatStopwatch(durationSeconds)}).`
            : `Tiempo guardado (${formatStopwatch(durationSeconds)}).`);
    } else {
        showBarMessage('Tiempo descartado (menos de 1 minuto).');
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
    startPomodoro(projectId, taskId, taskTitle || null);
}

function startStopwatchForTask(projectId, taskId, taskTitle = '') {
    return startTimerForTask(projectId, taskId, 'stopwatch', taskTitle);
}

// El ▶ de una tarea: si ESA tarea está corriendo, se convierte en ■ y detiene
// (guarda el tiempo); si no, arranca el cronómetro en ella. Antes siempre
// arrancaba, y pulsarlo con el cronómetro en marcha solo ofrecía reiniciarlo.
function toggleTimerForTask(projectId, taskId, taskTitle = '') {
    const isActive = pomoState.status === 'running' || pomoState.status === 'paused';
    if (isActive && pomoState.taskId === taskId) return stopTimer();
    return startTimerForTask(projectId, taskId, 'stopwatch', taskTitle);
}

function startBreak(mode) {
    clearBarMessage();
    if (pomoState.status !== 'idle') return;
    pomoState = createIdlePomoState(mode);
    startPomodoro();
}

// announce=false se usa al rehidratar una sesión que terminó hace rato,
// para no sonar/mostrar el aviso de "completado" con horas de retraso.
async function finishPomodoro(endedEpochMs, announce) {
    stopTicking();

    const finishedState = pomoState;
    // Primero reclamarla: con dos pestañas abiertas, las dos llegan aquí
    const claimed = await claimPomoState(finishedState);
    pomoState = createIdlePomoState(finishedState.mode);
    renderPomoUI();
    if (!claimed) return;

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
        if (wasFocus) {
            // Sin la tarjeta del reloj, el descanso se ofrece aquí mismo
            showBarMessage('¡Pomodoro completado!', [
                { label: 'Descanso 5 min', onClick: () => startBreak('short_break') },
                { label: '15 min', onClick: () => startBreak('long_break') },
                { label: 'Ahora no', onClick: clearBarMessage },
            ], BAR_OFFER_MS);
        } else {
            showBarMessage('Descanso terminado.');
        }
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
    if (pomoState.taskTitle) return `${modeLabel} · ${pomoState.taskTitle}`;
    const project = projectsState.projects.find(p => p.id === pomoState.projectId);
    return project ? `${modeLabel} · ${project.name}` : modeLabel;
}

// Modo mensaje de la barra: sin timer corriendo, enseña un aviso ("Sesión
// guardada", "¡Pomodoro completado!") con botones opcionales, y se va solo.
const BAR_MESSAGE_MS = 5000;
const BAR_OFFER_MS = 120000; // la oferta de descanso espera más
let barMessage = null; // { text, actions: [{ label, onClick }] }
let barMessageTimer = null;

function showBarMessage(text, actions = [], timeoutMs = BAR_MESSAGE_MS) {
    clearTimeout(barMessageTimer);
    barMessage = { text, actions };
    barMessageTimer = setTimeout(clearBarMessage, timeoutMs);
    renderPomoUI();
}

function clearBarMessage() {
    clearTimeout(barMessageTimer);
    barMessageTimer = null;
    if (!barMessage) return;
    barMessage = null;
    renderPomoUI();
}

function renderBarActions() {
    pomodoroBarActions.innerHTML = '';
    (barMessage ? barMessage.actions : []).forEach(action => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'pomodoro-bar-action';
        button.textContent = action.label;
        button.addEventListener('click', (event) => {
            event.stopPropagation();
            action.onClick();
        });
        pomodoroBarActions.appendChild(button);
    });
}

function renderPomoUI() {
    const isActive = pomoState.status === 'running' || pomoState.status === 'paused';

    // El cronómetro cuenta hacia arriba y su "progreso" es sobre el tope de 8 h,
    // que es lo único que acota su duración.
    let clock;
    let progressPct;
    if (isStopwatch(pomoState)) {
        // Tope incluido: mientras espera respuesta en el tope, el reloj no pasa de 8 h
        const elapsedSeconds = Math.min(POMO_STOPWATCH_MAX_SECONDS, Math.floor(getElapsedMs(pomoState) / 1000));
        clock = formatStopwatch(elapsedSeconds);
        progressPct = Math.min(100, (elapsedSeconds / POMO_STOPWATCH_MAX_SECONDS) * 100);
    } else {
        const remainingMs = getRemainingMs(pomoState);
        clock = formatClock(Math.max(0, Math.ceil(remainingMs / 1000)));
        const totalMs = pomoState.plannedSeconds * 1000;
        progressPct = Math.min(100, Math.max(0, 100 - (remainingMs / totalMs) * 100));
    }

    const showMessage = !isActive && barMessage !== null;
    pomodoroBar.classList.toggle('message', showMessage);
    pomodoroBarTime.classList.toggle('hidden', !isActive);
    pomodoroBarPauseBtn.classList.toggle('hidden', !isActive);
    pomodoroBarStopBtn.classList.toggle('hidden', !isActive);
    renderBarActions();

    if (showMessage) {
        pomodoroBar.classList.remove('hidden');
        document.body.classList.add('has-pomodoro-bar');
        pomodoroBarProgress.style.width = '0%';
        pomodoroBarLabel.textContent = barMessage.text;
        document.title = 'Habit Tracker';
    } else if (isActive) {
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

    syncTimerMarks(clock);
}

// Todo elemento con data-timer-task="<id>" (tarjeta del tablero, fila de la
// lista, botonera del detalle) se entera de si SU tarea está corriendo: recibe
// la clase .timing, sus .timer-live muestran el reloj, y sus botones con
// data-label-idle/data-label-timing cambian de nombre. Lo que se ve u oculta
// (▶ o ■, total o reloj) lo decide el CSS con esa clase. Corre en cada tick y
// después de cada repintado del tablero o la lista, que la pierden al rehacerse.
function syncTimerMarks(clock = null) {
    const isActive = pomoState.status === 'running' || pomoState.status === 'paused';
    const liveTaskId = isActive && pomoState.taskId ? String(pomoState.taskId) : null;
    const text = liveTaskId ? (clock || pomoClockText()) : '';

    document.querySelectorAll('[data-timer-task]').forEach(el => {
        const timing = el.dataset.timerTask === liveTaskId;
        el.classList.toggle('timing', timing);
        el.querySelectorAll('.timer-live').forEach(live => { live.textContent = timing ? text : ''; });
        el.querySelectorAll('[data-label-idle]').forEach(button => {
            const label = timing ? button.dataset.labelTiming : button.dataset.labelIdle;
            button.title = label;
            button.setAttribute('aria-label', label);
        });
    });
}

function pomoClockText() {
    if (isStopwatch(pomoState)) {
        return formatStopwatch(Math.min(POMO_STOPWATCH_MAX_SECONDS, Math.floor(getElapsedMs(pomoState) / 1000)));
    }
    return formatClock(Math.max(0, Math.ceil(getRemainingMs(pomoState) / 1000)));
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
// Tiempo registrado por día (tocando "Hoy")
// ============================================
//
// Todos los registros de un día, de todas las tareas: para ver de dónde sale
// el "Hoy" y corregirlo (p. ej. un cronómetro olvidado que se cerró solo).

const dayLogModal = document.getElementById('dayLogModal');
const dayLogDateEl = document.getElementById('dayLogDate');
const dayLogTotalEl = document.getElementById('dayLogTotal');
const dayLogListEl = document.getElementById('dayLogList');
const dayLogPrevBtn = document.getElementById('dayLogPrev');
const dayLogNextBtn = document.getElementById('dayLogNext');
const dayLogPicker = document.getElementById('dayLogPicker');
const DAY_LOG_WEEKDAYS = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'];

const dayLogState = {
    date: null,        // Date local, a medianoche
    sessions: [],
    requestId: 0,      // descarta respuestas de un día que ya no se ve
};

function localMidnight(date) {
    return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

function dayLogLabel(date) {
    const today = localMidnight(new Date());
    const diff = Math.round((today - date) / 86400000);
    const day = formatShortDate(getDateKey(date));
    if (diff === 0) return `Hoy, ${day}`;
    if (diff === 1) return `Ayer, ${day}`;
    return `${DAY_LOG_WEEKDAYS[date.getDay()]} ${day}`;
}

function isDayLogOpen() {
    return !dayLogModal.classList.contains('hidden');
}

function openDayLog() {
    dayLogState.date = localMidnight(new Date());
    showModal(dayLogModal);
    loadDayLog();
}

function closeDayLog() {
    dayLogState.requestId++;
    hideModal(dayLogModal);
}

function shiftDayLog(days) {
    const d = dayLogState.date;
    dayLogState.date = new Date(d.getFullYear(), d.getMonth(), d.getDate() + days);
    loadDayLog();
}

async function loadDayLog() {
    const date = dayLogState.date;
    const key = getDateKey(date);
    dayLogDateEl.textContent = `${dayLogLabel(date)} ▾`;
    dayLogNextBtn.disabled = date >= localMidnight(new Date());
    dayLogPicker.value = key;
    dayLogPicker.max = getDateKey(new Date());
    const requestId = ++dayLogState.requestId;

    try {
        const [sessionsData, tasksData, projectsData] = await Promise.all([
            apiFetch(`/api/pomodoro?date_from=${key}&date_to=${key}`),
            apiFetch('/api/tasks'),
            // Con los archivados: sus registros también suman en el día
            apiFetch('/api/projects?include_inactive=true'),
        ]);
        if (requestId !== dayLogState.requestId) return;
        // Solo foco, como el "Hoy"; y en el orden en que pasó el día
        dayLogState.sessions = sessionsData.sessions
            .filter(s => s.mode === 'focus')
            .sort((a, b) => a.started_at.localeCompare(b.started_at));
        renderDayLog(tasksData.tasks, projectsData.projects);
    } catch (error) {
        if (requestId !== dayLogState.requestId) return;
        console.error('Error al cargar el tiempo del día:', error);
        dayLogListEl.innerHTML = '<p class="card-empty">No se pudo cargar. Intenta de nuevo.</p>';
    }
}

function renderDayLog(tasks, projects) {
    const sessions = dayLogState.sessions;
    const total = sessions.reduce((sum, s) => sum + s.duration_seconds, 0);
    dayLogTotalEl.textContent = sessions.length
        ? `${formatDuration(total)} · ${sessions.length} ${sessions.length === 1 ? 'registro' : 'registros'}`
        : '';
    dayLogListEl.replaceChildren();

    if (sessions.length === 0) {
        dayLogListEl.innerHTML = '<p class="card-empty">Sin tiempo registrado este día.</p>';
        return;
    }

    const taskById = new Map(tasks.map(t => [t.id, t]));
    const projectById = new Map(projects.map(p => [p.id, p]));
    sessions.forEach(session => {
        const task = taskById.get(session.task_id);
        const project = projectById.get(session.project_id);
        const parts = [task ? task.title : 'Sin tarea'];
        if (project && !project.is_system) parts.push(project.name);
        if (session.note) parts.push(session.note);
        const row = buildSessionRow(session, parts.join(' · '));
        // El cronómetro olvidado que se cerró solo a las 8 h: lo que más se
        // corrige, así que se señala
        if (session.note === POMO_AUTOCLOSE_NOTE) {
            row.classList.add('session-flag');
            row.querySelector('.session-origin').textContent = '⚠';
            row.querySelector('.session-origin').title = POMO_AUTOCLOSE_NOTE;
        }
        dayLogListEl.appendChild(row);
    });
}

dayLogListEl.addEventListener('click', async (event) => {
    const button = event.target.closest('[data-action]');
    if (!button) return;
    const sessionId = Number(button.closest('.session-row').dataset.sessionId);
    const session = dayLogState.sessions.find(s => s.id === sessionId);
    if (!session) return;

    if (button.dataset.action === 'edit') {
        // Se abre encima (z-index 1050); al guardar, loadProjects() dispara
        // projectsChangedHooks y este listado se vuelve a pedir
        openLogTimeModal(session.project_id, session);
        return;
    }

    const summary = `${formatShortDate(session.session_date)} · ${formatClockRange(session)} · ${formatDuration(session.duration_seconds)}`;
    const ok = await confirmDialog(`${summary}. Se descuenta del tiempo de su tarea y de su proyecto.`, {
        title: '¿Eliminar este registro?', confirmLabel: 'Eliminar', danger: true,
    });
    if (!ok) return;
    try {
        await apiFetch(`/api/pomodoro/${sessionId}`, { method: 'DELETE' });
        projectsState.tasksByProject = {};
        await loadProjects();
    } catch (error) {
        console.error('Error al eliminar el registro:', error);
    }
});

pomoTodayEl.addEventListener('click', openDayLog);
dayLogPrevBtn.addEventListener('click', () => shiftDayLog(-1));
dayLogNextBtn.addEventListener('click', () => shiftDayLog(1));
dayLogDateEl.addEventListener('click', () => {
    try {
        dayLogPicker.showPicker();
    } catch (error) {
        // Sin showPicker (navegadores viejos): el input se enfoca y el
        // teclado o el clic lo abren
        dayLogPicker.focus();
    }
});
dayLogPicker.addEventListener('change', () => {
    if (!dayLogPicker.value) return;
    const [y, m, d] = dayLogPicker.value.split('-').map(Number);
    const picked = new Date(y, m - 1, d);
    // El max ya bloquea el futuro en el calendario; esto cubre lo que se teclee
    if (picked > localMidnight(new Date())) {
        dayLogPicker.value = getDateKey(dayLogState.date);
        return;
    }
    dayLogState.date = picked;
    loadDayLog();
});
document.getElementById('closeDayLogBtn').addEventListener('click', closeDayLog);
dayLogModal.querySelector('.modal-overlay').addEventListener('click', closeDayLog);
document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape' || event.defaultPrevented || !isDayLogOpen()) return;
    // Con el confirm o el registro abiertos encima, Escape es de ellos
    if (!document.getElementById('confirmModal').classList.contains('hidden')) return;
    if (!logTimeModal.classList.contains('hidden')) return;
    closeDayLog();
});
window.projectsChangedHooks.push(() => {
    if (isDayLogOpen()) loadDayLog();
});

// ============================================
// Eventos
// ============================================

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

// Tocar el cuerpo de la barra (no sus botones) lleva a la vista Tableros,
// salvo en modo mensaje, que no tiene nada que enseñar allí.
pomodoroBar.addEventListener('click', () => {
    if (pomoState.status !== 'idle') goToView(1);
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
    try { localStorage.removeItem(POMO_ACTIVITY_KEY); } catch (e) {}
    if (!idleCheckModal.classList.contains('hidden')) closeIdleCheck();
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
        // Pasado el tope se cierra solo, salvo que lleve rato sin actividad:
        // entonces el tick pregunta (lo más probable es que se olvidara)
        if (getElapsedMs(pomoState) >= POMO_STOPWATCH_MAX_SECONDS * 1000 && !isIdleStopwatch()) {
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

// fillLogTimeTasks() solo lista tareas pendientes, pero un registro puede ser
// de una tarea ya hecha (al editarlo, o al registrar desde una tarjeta de
// "Hecho"). Sin su opción, el select la perdería al guardar.
function ensureLogTimeTaskOption(taskId, title) {
    const value = String(taskId);
    if (!Array.from(logTimeTaskEl.options).some(o => o.value === value)) {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = title;
        logTimeTaskEl.appendChild(option);
    }
    logTimeTaskEl.value = value;
}

// task: {id, title} para abrirlo ya apuntando a esa tarea (desde el tablero).
async function openLogTimeModal(projectId, session = null, task = null) {
    const project = projectsState.projects.find(p => p.id === projectId);
    // Registrar pide un proyecto activo; editar no: un registro de un proyecto
    // archivado (visto desde el tiempo del día) también se corrige.
    if (!project && !session) return;

    logTimeProjectId = projectId;
    logTimeSessionId = session ? session.id : null;
    logTimeProjectEl.textContent = project ? project.name : 'Proyecto archivado';
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
        ensureLogTimeTaskOption(session.task_id, 'Tarea terminada');
    } else if (task) {
        ensureLogTimeTaskOption(task.id, task.title);
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
    let note = logTimeNoteEl.value.trim();
    // Corregir un cronómetro que se cerró solo: la nota automática ya no es
    // cierta y lo seguiría señalando con ⚠ en el tiempo del día
    if (logTimeSessionId && note === POMO_AUTOCLOSE_NOTE && duration !== POMO_STOPWATCH_MAX_SECONDS) {
        note = '';
    }

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
// El total de hoy cambia al registrar tiempo a mano, no solo al terminar un
// pomodoro, y ese registro pasa por loadProjects().
window.projectsChangedHooks.push(refreshTodaySeconds);
window.appLogoutHooks.push(handlePomodoroLogout);
