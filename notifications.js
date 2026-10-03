// ============================================
// Avisos: la campanita de la barra de arriba
// ============================================
//
// Siempre a la vista, en cualquier pestaña. Hoy avisa de las sesiones por
// confirmar (needs_review): un cronómetro que llegó al tope de 8 h sin que
// nadie dijera cuánto se trabajó. La pregunta del tope puede no verse nunca
// (otra pestaña, cerrar sesión, el token vencido), y sin este aviso ese
// tiempo quedaba como 8 h sin que nadie lo revisara. Después avisará también
// de reportes nuevos (épica 30). Carga después de pomodoro.js: usa
// openLogTimeModal() para "Corregir".

const bellBtn = document.getElementById('bellBtn');
const bellCount = document.getElementById('bellCount');
const noticesModal = document.getElementById('noticesModal');
const noticesList = document.getElementById('noticesList');
const noticesError = document.getElementById('noticesError');

let noticesSessions = [];
let noticesRequestId = 0;

async function refreshNotices() {
    if (!getToken()) return;
    const requestId = ++noticesRequestId;
    try {
        const data = await apiFetch('/api/pomodoro/review');
        if (requestId !== noticesRequestId) return;
        noticesSessions = data.sessions;
    } catch (error) {
        console.error('No se pudieron cargar los avisos:', error);
        return;
    }
    paintBell();
    if (!noticesModal.classList.contains('hidden')) renderNotices();
}

function paintBell() {
    const count = noticesSessions.length;
    bellCount.textContent = count > 9 ? '9+' : String(count);
    bellCount.hidden = count === 0;
    bellBtn.classList.toggle('has-notices', count > 0);
    const label = count === 0 ? 'Avisos: nada pendiente'
        : `Avisos: ${count} ${count === 1 ? 'registro de tiempo por confirmar' : 'registros de tiempo por confirmar'}`;
    bellBtn.title = label;
    bellBtn.setAttribute('aria-label', label);
}

function noticeWhen(session) {
    const start = new Date(`${session.started_at}Z`);
    const end = new Date(`${session.ended_at}Z`);
    const day = start.toLocaleDateString('es-MX', { weekday: 'short', day: 'numeric', month: 'short' });
    return `${day}, ${clockLabel(start.getTime())}–${clockLabel(end.getTime())}`;
}

async function renderNotices() {
    noticesError.classList.add('hidden');
    if (noticesSessions.length === 0) {
        noticesList.replaceChildren(el('p', 'empty-state', 'No tienes avisos pendientes.'));
        return;
    }
    // Los títulos de las tareas: incluidas las hechas y las de proyectos archivados
    let tasks = [];
    try {
        tasks = (await apiFetch('/api/tasks')).tasks;
    } catch (error) {
        tasks = [];
    }
    const taskById = new Map(tasks.map(t => [t.id, t]));
    const projectById = new Map((projectsState.projects || []).map(p => [p.id, p]));

    noticesList.replaceChildren(...noticesSessions.map(session => {
        const task = taskById.get(session.task_id);
        const project = projectById.get(session.project_id);
        const item = el('div', 'notice-item');
        item.dataset.sessionId = String(session.id);
        const text = el('div', 'notice-text');
        const title = el('p', 'notice-title', `⚠ ${task ? task.title : 'Sin tarea'}`);
        const meta = el('p', 'notice-meta',
            `${noticeWhen(session)} · ${formatDuration(session.duration_seconds)}`
            + (project && !project.is_system ? ` · ${project.name}` : ''));
        const hint = el('p', 'notice-hint', 'El cronómetro llegó al tope de 8 h. ¿Cuánto trabajaste de verdad?');
        text.append(title, meta, hint);

        const actions = el('div', 'notice-actions');
        const fix = el('button', 'submit-btn notice-fix', 'Corregir');
        fix.type = 'button';
        const ok = el('button', 'submit-btn btn-neutral notice-ok', 'Está bien');
        ok.type = 'button';
        ok.title = 'Confirmar las 8 h tal cual';
        actions.append(fix, ok);
        item.append(text, actions);
        return item;
    }));
}

function openNotices() {
    showModal(noticesModal);
    renderNotices();
    refreshNotices();
}

function closeNotices() {
    hideModal(noticesModal);
}

noticesList.addEventListener('click', async (event) => {
    const item = event.target.closest('.notice-item');
    if (!item) return;
    const session = noticesSessions.find(s => String(s.id) === item.dataset.sessionId);
    if (!session) return;

    if (event.target.closest('.notice-fix')) {
        // El registro a mano se abre encima (z-index 1050); al guardar se
        // recargan los proyectos y, con ellos, los avisos
        openLogTimeModal(session.project_id, session);
        return;
    }
    if (event.target.closest('.notice-ok')) {
        noticesError.classList.add('hidden');
        try {
            await apiFetch(`/api/pomodoro/${session.id}`, { method: 'PATCH', json: { needs_review: false } });
        } catch (error) {
            showError(noticesError, error.message);
            return;
        }
        await refreshNotices();
    }
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
    noticesSessions = [];
    paintBell();
    closeNotices();
}

window.appDataHooks.push(refreshNotices);
// Guardar, corregir o borrar tiempo termina en loadProjects(): ahí se repasa
window.projectsChangedHooks.push(refreshNotices);
window.appLogoutHooks.push(resetNotices);
