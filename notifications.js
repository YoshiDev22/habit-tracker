// ============================================
// Avisos: la campanita de la barra de arriba (centro de avisos, 1.26)
// ============================================
//
// Siempre a la vista, en cualquier pestaña. GET /api/notices trae los avisos
// de la cuenta (backend/notices.py), guardados por cuenta:
// - Pendientes, calculados de los datos: un registro por confirmar (el
//   cronómetro llegó a 8 h) y un día sin anotar con racha. Se resuelven ahí
//   mismo y pasan a "Hechos" solos.
// - Informativos: un reporte automático listo, las Novedades de una versión y
//   los anuncios para todas las cuentas (mantenimiento; scripts/announce.py).
//   Se leen al abrir la campanita.
// El círculo rojo cuenta los pendientes más los informativos sin leer.
// Carga después de pomodoro.js (openLogTimeModal para "Corregir"); usa
// openHabitDay (habits.js), openSavedReportById (saved-reports.js) y
// showNovedades (novedades.js), que cargan después: se llaman al tocar.

const bellBtn = document.getElementById('bellBtn');
const bellCount = document.getElementById('bellCount');
const noticesModal = document.getElementById('noticesModal');
const noticesList = document.getElementById('noticesList');
const noticesError = document.getElementById('noticesError');
const MAX_DONE_SHOWN = 10;

const noticesState = {
    notices: [],          // de /api/notices, lo pendiente primero
    unread: 0,
    sessions: new Map(),  // las sesiones por confirmar (para "Corregir"), por id
};
let noticesRequestId = 0;

async function refreshNotices() {
    if (!getToken()) return;
    const requestId = ++noticesRequestId;
    try {
        const [data, review] = await Promise.all([
            apiFetch(`/api/notices?today=${getDateKey(new Date())}`),
            apiFetch('/api/pomodoro/review'),
        ]);
        if (requestId !== noticesRequestId) return;
        noticesState.notices = data.notices;
        noticesState.unread = data.unread;
        noticesState.sessions = new Map(review.sessions.map(s => [s.id, s]));
    } catch (error) {
        console.error('No se pudieron cargar los avisos:', error);
        return;
    }
    paintBell();
    if (!noticesModal.classList.contains('hidden')) renderNotices();
}

function paintBell() {
    const count = noticesState.unread;
    bellCount.textContent = count > 9 ? '9+' : String(count);
    bellCount.hidden = count === 0;
    bellBtn.classList.toggle('has-notices', count > 0);
    const label = count === 0 ? 'Avisos: nada pendiente' : `Avisos: ${count} sin atender`;
    bellBtn.title = label;
    bellBtn.setAttribute('aria-label', label);
}

function noticeWhen(session) {
    const start = new Date(`${session.started_at}Z`);
    const end = new Date(`${session.ended_at}Z`);
    const day = start.toLocaleDateString('es-MX', { weekday: 'short', day: 'numeric', month: 'short' });
    return `${day}, ${clockLabel(start.getTime())}–${clockLabel(end.getTime())}`;
}

function longDate(key) {
    const [y, m, d] = key.split('-').map(Number);
    return new Date(y, m - 1, d).toLocaleDateString('es-MX', { weekday: 'long', day: 'numeric', month: 'long' });
}

function actionButton(label, action, neutral = false, title = '', extra = '') {
    const button = el('button', `submit-btn${neutral ? ' btn-neutral' : ''}${extra ? ` ${extra}` : ''}`, label);
    button.type = 'button';
    button.dataset.action = action;
    if (title) button.title = title;
    return button;
}

// Un aviso: su texto y, si los tiene, sus botones
function buildNotice(notice, taskById, projectById) {
    const item = el('div', `notice-item notice-${notice.status}${notice.status === 'info' && !notice.read ? ' unread' : ''}`);
    item.dataset.noticeId = String(notice.id);
    const text = el('div', 'notice-text');
    const actions = el('div', 'notice-actions');

    if (notice.kind === 'review' && notice.status === 'pending') {
        const session = noticesState.sessions.get(notice.session_id);
        const task = session && taskById.get(session.task_id);
        const project = session && projectById.get(session.project_id);
        text.append(el('p', 'notice-title', `⚠ ${task ? task.title : 'Registro por confirmar'}`));
        if (session) {
            text.append(el('p', 'notice-meta', `${noticeWhen(session)} · ${formatDuration(session.duration_seconds)}`
                + (project && !project.is_system ? ` · ${project.name}` : '')));
        }
        text.append(el('p', 'notice-hint', 'El cronómetro llegó al tope de 8 h. ¿Cuánto trabajaste de verdad?'));
        if (session) {
            item.dataset.sessionId = String(session.id);
            actions.append(actionButton('Corregir', 'fix', false, '', 'notice-fix'),
                actionButton('Está bien', 'ok', true, 'Confirmar las 8 h tal cual', 'notice-ok'));
        }
    } else if (notice.kind === 'missed_day' && notice.status === 'pending') {
        text.append(el('p', 'notice-title', `📅 Día sin anotar: ${longDate(notice.date)}`), el('p', 'notice-hint', notice.detail));
        actions.append(actionButton('Anotar', 'day'), actionButton('Descartar', 'dismiss', true, 'No lo voy a anotar'));
    } else if (notice.status === 'info') {
        const icon = { report_ready: '📊', novedades: '✨', announcement: '📢' }[notice.kind] || '🔔';
        text.append(el('p', 'notice-title', `${icon} ${notice.title}`));
        if (notice.detail) text.append(el('p', 'notice-hint', notice.detail));
        // Un anuncio para todas las cuentas (mantenimiento…) solo se lee
        if (notice.kind !== 'announcement') {
            actions.append(actionButton(notice.kind === 'report_ready' ? 'Ver reporte' : 'Ver novedades', 'open'));
        }
    } else {
        // Hecho o descartado: solo el registro de que pasó
        const label = notice.kind === 'review' ? 'Registro de tiempo confirmado'
            : `Día ${notice.status === 'done' ? 'anotado' : 'descartado'}: ${longDate(notice.date)}`;
        text.append(el('p', 'notice-title', `✓ ${label}`));
    }
    item.append(text);
    if (actions.childNodes.length) item.append(actions);
    return item;
}

async function renderNotices() {
    noticesError.classList.add('hidden');
    const pending = noticesState.notices.filter(n => n.status === 'pending');
    const info = noticesState.notices.filter(n => n.status === 'info');
    const done = noticesState.notices.filter(n => n.status === 'done' || n.status === 'dismissed').slice(0, MAX_DONE_SHOWN);
    if (!pending.length && !info.length && !done.length) {
        noticesList.replaceChildren(el('p', 'empty-state', 'No tienes avisos.'));
        return;
    }
    // Los títulos de las tareas de los registros por confirmar
    let tasks = [];
    if (pending.some(n => n.kind === 'review')) {
        try { tasks = (await apiFetch('/api/tasks')).tasks; } catch (error) { tasks = []; }
    }
    const taskById = new Map(tasks.map(t => [t.id, t]));
    const projectById = new Map((projectsState.projects || []).map(p => [p.id, p]));
    const groups = [['Pendientes', pending], ['Avisos', info], ['Hechos', done]].filter(([, list]) => list.length);
    noticesList.replaceChildren(...groups.flatMap(([title, list]) => [
        el('p', 'notice-group', title),
        ...list.map(n => buildNotice(n, taskById, projectById)),
    ]));
}

async function openNotices() {
    showModal(noticesModal);
    renderNotices();
    await refreshNotices();
    // Abrir la campanita lee los informativos (los pendientes siguen hasta resolverse)
    if (noticesState.notices.some(n => n.status === 'info' && !n.read)) {
        try {
            await apiFetch('/api/notices/read', { method: 'POST', json: {} });
            noticesState.unread = noticesState.notices.filter(n => n.status === 'pending').length;
            paintBell();
        } catch (error) { /* se intentará la próxima vez */ }
    }
}

function closeNotices() {
    hideModal(noticesModal);
}

// "No, no lo hice" en la ventana de ayer (habits.js): descarta su aviso
async function dismissMissedDayNotice(dateKey) {
    await refreshNotices();
    const notice = noticesState.notices.find(n => n.kind === 'missed_day' && n.date === dateKey && n.status === 'pending');
    if (!notice) return;
    try {
        await apiFetch(`/api/notices/${notice.id}/dismiss`, { method: 'POST' });
    } catch (error) {
        return;   // queda pendiente: se puede descartar desde la campanita
    }
    await refreshNotices();
}

noticesList.addEventListener('click', async (event) => {
    const button = event.target.closest('[data-action]');
    const item = event.target.closest('.notice-item');
    if (!button || !item) return;
    const notice = noticesState.notices.find(n => String(n.id) === item.dataset.noticeId);
    if (!notice) return;
    noticesError.classList.add('hidden');
    const action = button.dataset.action;

    try {
        if (action === 'fix') {
            // El registro a mano se abre encima (z-index 1050); al guardar se
            // recargan los proyectos y, con ellos, los avisos
            const session = noticesState.sessions.get(notice.session_id);
            if (session) openLogTimeModal(session.project_id, session);
            return;
        }
        if (action === 'ok') {
            await apiFetch(`/api/pomodoro/${notice.session_id}`, { method: 'PATCH', json: { needs_review: false } });
        } else if (action === 'dismiss') {
            await apiFetch(`/api/notices/${notice.id}/dismiss`, { method: 'POST' });
        } else if (action === 'day') {
            // Que este clic no llegue al document: ahí, un clic fuera del panel
            // del día lo cierra, y lo cerraba en cuanto se abría
            event.stopPropagation();
            closeNotices();
            openHabitDay(notice.date);
            return;
        } else if (action === 'open') {
            closeNotices();
            if (notice.kind === 'report_ready') {
                savedState.scope = notice.report_kind && notice.report_kind.startsWith('costs') ? 'costs' : 'reports';
                savedState.fromList = false;
                openSavedModal();
                openSavedReportById(notice.report_id);
            } else if (notice.kind === 'novedades') {
                const entry = novedadesState.data && novedadesState.data.versions.find(v => v.version === notice.version);
                if (entry) showNovedades([entry]);
            }
            return;
        }
    } catch (error) {
        showError(noticesError, error.message);
        return;
    }
    await refreshNotices();
});

bellBtn.addEventListener('click', openNotices);
document.getElementById('noticesClose').addEventListener('click', closeNotices);
noticesModal.querySelector('.modal-overlay').addEventListener('click', closeNotices);
document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape' || noticesModal.classList.contains('hidden')) return;
    // Con el registro a mano abierto encima, Escape cierra ese (pomodoro.js)
    if (!document.getElementById('logTimeModal').classList.contains('hidden')) return;
    closeNotices();
});

function resetNotices() {
    noticesRequestId++;
    noticesState.notices = [];
    noticesState.unread = 0;
    noticesState.sessions = new Map();
    paintBell();
    closeNotices();
}

window.appDataHooks.push(refreshNotices);
// Guardar, corregir o borrar tiempo termina en loadProjects(): ahí se repasa
window.projectsChangedHooks.push(refreshNotices);
window.appLogoutHooks.push(resetNotices);
// Al volver a la pestaña (otro dispositivo pudo resolver algo, o pasó la medianoche)
document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') refreshNotices();
});
