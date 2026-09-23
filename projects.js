// ============================================
// Estado
// ============================================

const projectsState = {
    projects: [],            // ProjectResponse[] (id, name, description, color, icon, ...)
    summaryByProject: {},    // { [id]: ProjectSummary }
    tasksByProject: {},      // { [id]: TaskResponse[] } — cache, se invalida en cada mutación
    sessionsByProject: {},   // { [id]: PomodoroSessionResponse[] } — mismo criterio
    expanded: new Set(),
};

let editingProjectId = null;
let pendingProjectId = null;

// Hooks que corren cada vez que cambian los proyectos o sus tareas. Se declara
// aquí porque projects.js es el dueño de ese estado; pomodoro.js se engancha
// para mantener sus selects al día sin que este archivo lo conozca.
window.projectsChangedHooks = [];

// Corren (síncronos) cada vez que goToView() cambia de vista, con el índice
// nuevo. board.js los usa para ensanchar la app solo mientras se ve el tablero.
window.viewChangedHooks = [];

// ============================================
// Elementos del DOM
// ============================================

const tabCalendar = document.getElementById('tabCalendar');
const tabProjects = document.getElementById('tabProjects');
const tabReports = document.getElementById('tabReports');
const viewsViewport = document.getElementById('viewsViewport');
const viewsTrack = document.getElementById('viewsTrack');
const tabIndicator = document.querySelector('.tab-indicator');

const projectsList = document.getElementById('projectsList');
const projectsEmpty = document.getElementById('projectsEmpty');
const addProjectBtn = document.getElementById('addProjectBtn');

const projectModal = document.getElementById('projectModal');
const projectModalTitle = document.getElementById('projectModalTitle');
const projectForm = document.getElementById('projectForm');
const projectNameInput = document.getElementById('projectName');
const projectDescriptionInput = document.getElementById('projectDescription');
const projectIconInput = document.getElementById('projectIcon');
const projectColorInput = document.getElementById('projectColor');
const projectFormError = document.getElementById('projectFormError');
const closeProjectModalBtn = document.getElementById('closeProjectModalBtn');

const projectDeleteModal = document.getElementById('projectDeleteModal');
const projectDeleteMessage = document.getElementById('projectDeleteMessage');
const projectDeleteTimeOption = document.getElementById('projectDeleteTimeOption');
const projectDeleteTimeInput = document.getElementById('projectDeleteTime');
const projectDeleteTimeLabel = document.getElementById('projectDeleteTimeLabel');
const confirmProjectDeleteBtn = document.getElementById('confirmProjectDeleteBtn');

// ============================================
// Tabs + swipe
// ============================================

const VIEW_TABS = [tabCalendar, tabProjects, tabReports];
const VIEW_COUNT = VIEW_TABS.length;
let currentViewIndex = 0;

function goToView(index, opts = {}) {
    const animate = opts.animate !== false;
    currentViewIndex = Math.max(0, Math.min(VIEW_COUNT - 1, index));

    // El popover solo tiene sentido sobre la vista Calendario.
    hideHabitPopover();

    viewsTrack.style.transition = animate ? '' : 'none';
    viewsTrack.style.transform = `translateX(${-100 * currentViewIndex}%)`;

    VIEW_TABS.forEach((tab, i) => {
        const active = i === currentViewIndex;
        tab.classList.toggle('active', active);
        tab.setAttribute('aria-selected', String(active));
        tab.tabIndex = active ? 0 : -1;
    });
    tabIndicator.style.transform = `translateX(${100 * currentViewIndex}%)`;
    watchActiveView();
    writeLastView(currentViewIndex);

    window.viewChangedHooks.forEach(hook => hook(currentViewIndex));
}

// Las vistas van lado a lado en el track, así que la página tomaría la altura
// de la más alta: con Reportes cargado, el Calendario quedaba con metros de
// blanco debajo. El viewport mide lo que la vista activa y la sigue cuando
// crece o encoge (un tablero que carga, un reporte que se pinta).
const viewSections = [...viewsTrack.children];
let observedView = null;
const viewResizeObserver = 'ResizeObserver' in window
    ? new ResizeObserver(fitViewportToActiveView)
    : null;

function fitViewportToActiveView() {
    viewsViewport.style.height = `${viewSections[currentViewIndex].offsetHeight}px`;
}

function watchActiveView() {
    if (!viewResizeObserver) return;   // sin él, la página conserva la altura del track
    const view = viewSections[currentViewIndex];
    if (observedView !== view) {
        if (observedView) viewResizeObserver.unobserve(observedView);
        viewResizeObserver.observe(view);
        observedView = view;
    }
    fitViewportToActiveView();
}

watchActiveView();

// La última pestaña se recuerda en este dispositivo (localStorage.last_view):
// al recargar se vuelve a ella sin pedir nada extra al servidor. Se aplica ya,
// al cargar el script, para no enseñar un instante el Calendario; los hooks de
// vista (tablero ancho, cargar Reportes) se disparan en init, cuando board.js y
// reports.js ya se registraron.
const LAST_VIEW_KEY = 'last_view';

function readLastView() {
    try {
        const index = Number(localStorage.getItem(LAST_VIEW_KEY));
        return Number.isInteger(index) && index >= 0 && index < VIEW_COUNT ? index : 0;
    } catch (error) {
        return 0;
    }
}

function writeLastView(index) {
    try {
        localStorage.setItem(LAST_VIEW_KEY, String(index));
    } catch (error) {
        // Sin almacenamiento (modo privado estricto): solo no se recuerda
    }
}

goToView(readLastView(), { animate: false });
window.appInitHooks.push(() => goToView(currentViewIndex, { animate: false }));
// Quien entre después en este dispositivo empieza por el Calendario
window.appLogoutHooks.push(() => {
    goToView(0, { animate: false });
    try {
        localStorage.removeItem(LAST_VIEW_KEY);
    } catch (error) {
        // nada que limpiar
    }
});

VIEW_TABS.forEach((tab, i) => {
    tab.addEventListener('click', () => goToView(i));
});

// Patrón WAI-ARIA tabs: flechas, Home/End, roving tabindex.
VIEW_TABS.forEach((tab, i) => {
    tab.addEventListener('keydown', (event) => {
        let target = null;
        if (event.key === 'ArrowRight') target = (i + 1) % VIEW_COUNT;
        else if (event.key === 'ArrowLeft') target = (i - 1 + VIEW_COUNT) % VIEW_COUNT;
        else if (event.key === 'Home') target = 0;
        else if (event.key === 'End') target = VIEW_COUNT - 1;

        if (target !== null) {
            event.preventDefault();
            goToView(target);
            VIEW_TABS[target].focus();
        }
    });
});

// Swipe táctil. No hay drag con mouse a propósito: en escritorio ya están
// las tabs, y arrastrar con mouse pelea con selección de texto por poco
// beneficio real.
let swipeStartX = 0;
let swipeStartY = 0;
let swipeStartT = 0;
let swipeAxis = null; // null | 'x' | 'y'
let swipeDx = 0;
let suppressNextClick = false;

function prefersReducedMotion() {
    return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
}

viewsViewport.addEventListener('touchstart', (event) => {
    if (event.touches.length > 1) return;
    const touch = event.touches[0];
    swipeStartX = touch.clientX;
    swipeStartY = touch.clientY;
    swipeStartT = Date.now();
    swipeAxis = null;
    swipeDx = 0;
}, { passive: true });

viewsViewport.addEventListener('touchmove', (event) => {
    if (event.touches.length > 1) return;
    const touch = event.touches[0];
    const dx = touch.clientX - swipeStartX;
    const dy = touch.clientY - swipeStartY;

    if (swipeAxis === null) {
        // Umbral de 10px antes de decidir el eje, para no tragarnos un tap.
        if (Math.hypot(dx, dy) < 10) return;
        // Sesgo 1.2x a favor de vertical: un falso positivo horizontal
        // mientras se hace scroll es más molesto que un swipe fallido.
        swipeAxis = Math.abs(dx) > Math.abs(dy) * 1.2 ? 'x' : 'y';
    }

    if (swipeAxis !== 'x') return; // deja el scroll vertical nativo intacto

    event.preventDefault();
    swipeDx = dx;

    let effectiveDx = dx;
    if ((currentViewIndex === 0 && dx > 0) || (currentViewIndex === VIEW_COUNT - 1 && dx < 0)) {
        effectiveDx = dx * 0.35; // amortiguar en los bordes
    }

    viewsTrack.style.transition = 'none';
    viewsTrack.style.transform = `translateX(calc(${-100 * currentViewIndex}% + ${effectiveDx}px))`;
}, { passive: false });

function endSwipe() {
    if (swipeAxis !== 'x') {
        swipeAxis = null;
        return;
    }

    const width = viewsViewport.clientWidth || 1;
    const dt = Math.max(1, Date.now() - swipeStartT);
    const velocity = Math.abs(swipeDx) / dt; // px/ms

    let targetIndex = currentViewIndex;
    if (Math.abs(swipeDx) > width * 0.25 || (velocity > 0.4 && Math.abs(swipeDx) > 40)) {
        targetIndex = currentViewIndex + (swipeDx < 0 ? 1 : -1);
    }

    // Evita que el click sintetizado tras el touchend abra el popover
    // sobre la celda donde arrancó el swipe.
    suppressNextClick = true;
    setTimeout(() => { suppressNextClick = false; }, 400);

    goToView(targetIndex, { animate: !prefersReducedMotion() });
    swipeAxis = null;
    swipeDx = 0;
}

viewsViewport.addEventListener('touchend', endSwipe, { passive: true });
viewsViewport.addEventListener('touchcancel', endSwipe, { passive: true });

// Fase de captura: debe correr antes que el listener de click de la celda.
viewsViewport.addEventListener('click', (event) => {
    if (suppressNextClick) {
        event.stopPropagation();
        event.preventDefault();
        suppressNextClick = false;
    }
}, true);

// ============================================
// Carga de datos
// ============================================

async function loadProjects() {
    // Normalmente corre desde appDataHooks, ya autenticado. La excepción es
    // finishPomodoro(), alcanzable desde appInitHooks con el token expirado.
    if (!getToken()) return;

    try {
        const [listData, summaryData] = await Promise.all([
            apiFetch('/api/projects'),
            apiFetch('/api/projects/summary'),
        ]);

        projectsState.projects = listData.projects;
        projectsState.summaryByProject = {};
        // Los registros de tiempo cambian con cada alta o borrado; se vuelven a
        // pedir para los proyectos que estén desplegados.
        projectsState.sessionsByProject = {};
        summaryData.summaries.forEach(s => {
            projectsState.summaryByProject[s.project_id] = s;
        });

        renderProjects();

        // Toda mutación de proyecto o tarea termina llamando a loadProjects(),
        // así que este es el único punto que necesita avisar a los demás módulos.
        await runHooks(window.projectsChangedHooks);
    } catch (error) {
        console.error('Error al cargar proyectos:', error);
    }
}

// El backend guarda datetimes UTC naive (sin 'Z'). new Date() sin la 'Z' los
// interpretaría como hora LOCAL y pintaría el reloj corrido por el huso.
function parseUtcIso(value) {
    return new Date(value.endsWith('Z') ? value : `${value}Z`);
}

function formatClockRange(session) {
    const start = parseUtcIso(session.started_at);
    const end = parseUtcIso(session.ended_at);
    const hhmm = (d) => `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
    return `${hhmm(start)}–${hhmm(end)}`;
}

function formatShortDate(dateKey) {
    const [year, month, day] = dateKey.split('-').map(Number);
    const MONTHS = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
    return `${day} ${MONTHS[month - 1]}`;
}

// De dónde salió un registro de tiempo. El pomodoro conserva su ⏱ de siempre
// para no cambiarle el icono a los registros que ya existen. Lo usan la Lista
// y el historial de la tarjeta (board.js).
function sessionOrigin(session) {
    const originBySource = {
        manual: { icon: '✍️', title: 'Registrado a mano' },
        stopwatch: { icon: '▶', title: 'Medido con el cronómetro' },
    };
    return originBySource[session.source] || { icon: '⏱', title: 'Medido con un pomodoro' };
}

async function loadSessions(projectId) {
    try {
        const data = await apiFetch(`/api/pomodoro?project_id=${projectId}`);
        projectsState.sessionsByProject[projectId] = data.sessions;
        const container = document.getElementById(`tasks-${projectId}`);
        if (container) fillTaskListElement(container, projectId);
    } catch (error) {
        console.error('Error al cargar los registros de tiempo:', error);
    }
}

const sessionDeleteModal = document.getElementById('sessionDeleteModal');
const sessionDeleteDetail = document.getElementById('sessionDeleteDetail');
let pendingSessionDelete = null;

function askSessionDelete(projectId, sessionId) {
    const sessions = projectsState.sessionsByProject[projectId] || [];
    const session = sessions.find(s => s.id === sessionId);
    if (!session) return;

    pendingSessionDelete = { projectId, sessionId };
    sessionDeleteDetail.textContent =
        `${formatShortDate(session.session_date)} · ${formatClockRange(session)} · ${formatDuration(session.duration_seconds)}`;
    showModal(sessionDeleteModal);
}

document.getElementById('confirmSessionDeleteBtn').addEventListener('click', () => {
    if (!pendingSessionDelete) return;
    const { projectId, sessionId } = pendingSessionDelete;
    pendingSessionDelete = null;
    hideModal(sessionDeleteModal);
    removeSession(projectId, sessionId);
});

document.getElementById('cancelSessionDeleteBtn').addEventListener('click', () => {
    pendingSessionDelete = null;
    hideModal(sessionDeleteModal);
});

sessionDeleteModal.querySelector('.modal-overlay').addEventListener('click', () => {
    pendingSessionDelete = null;
    hideModal(sessionDeleteModal);
});

async function removeSession(projectId, sessionId) {
    try {
        await apiFetch(`/api/pomodoro/${sessionId}`, { method: 'DELETE' });
        delete projectsState.sessionsByProject[projectId];
        await loadProjects();
    } catch (error) {
        console.error('Error al eliminar el registro:', error);
    }
}

async function loadTasks(projectId) {
    try {
        const data = await apiFetch(`/api/tasks?project_id=${projectId}`);
        projectsState.tasksByProject[projectId] = data.tasks;
    } catch (error) {
        console.error('Error al cargar tareas:', error);
        projectsState.tasksByProject[projectId] = [];
    }

    // La lista pudo haberse vuelto a renderizar (o colapsado) mientras
    // esperábamos la respuesta; solo tocar el DOM si el contenedor sigue ahí.
    const container = document.getElementById(`tasks-${projectId}`);
    if (container && projectsState.expanded.has(projectId)) {
        fillTaskListElement(container, projectId);
        syncTimerMarks();
    }
}

// ============================================
// Render
// ============================================

function formatDuration(totalSeconds) {
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    return hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`;
}

function formatProjectMeta(summary) {
    if (!summary || summary.task_total === 0) {
        return 'Sin tareas';
    }
    let meta = `${summary.task_done}/${summary.task_total} tareas`;
    // total_seconds siempre es 0 hasta que exista Pomodoro (fase siguiente).
    if (summary.total_seconds > 0) {
        meta += ` · ${formatDuration(summary.total_seconds)}`;
    }
    return meta;
}

function buildProjectCard(project) {
    const summary = projectsState.summaryByProject[project.id];
    const isExpanded = projectsState.expanded.has(project.id);

    const card = document.createElement('article');
    card.className = 'project-card';
    card.dataset.projectId = String(project.id);

    const chip = document.createElement('span');
    chip.className = 'project-chip';
    chip.style.backgroundColor = project.color || '#95a5a6';

    const main = document.createElement('div');
    main.className = 'project-main';

    const name = document.createElement('h3');
    name.className = 'project-name';
    name.textContent = project.icon ? `${project.icon} ${project.name}` : project.name;

    const meta = document.createElement('p');
    meta.className = 'project-meta';
    meta.textContent = formatProjectMeta(summary);

    main.appendChild(name);
    main.appendChild(meta);

    const toggleBtn = document.createElement('button');
    toggleBtn.type = 'button';
    toggleBtn.className = 'project-toggle';
    toggleBtn.setAttribute('aria-expanded', String(isExpanded));
    toggleBtn.setAttribute('aria-label', isExpanded ? 'Ocultar tareas' : 'Mostrar tareas');
    toggleBtn.textContent = '▾';

    // El comportamiento vive en pomodoro.js, que escucha este botón por
    // delegación: es quien sabe construir una sesión.
    const logTimeBtn = document.createElement('button');
    logTimeBtn.type = 'button';
    logTimeBtn.className = 'project-log-time';
    logTimeBtn.setAttribute('aria-label', 'Registrar tiempo trabajado');
    logTimeBtn.title = 'Registrar tiempo trabajado';
    logTimeBtn.textContent = '⏱';

    const menuBtn = document.createElement('button');
    menuBtn.type = 'button';
    menuBtn.className = 'project-menu';
    menuBtn.setAttribute('aria-label', 'Opciones del proyecto');
    menuBtn.textContent = '⋯';

    card.appendChild(chip);
    card.appendChild(main);
    card.appendChild(logTimeBtn);
    card.appendChild(toggleBtn);
    // "Sin asignar" no se archiva ni se borra: su menú estaría vacío. Se
    // oculta sin quitarlo, para que sus botones queden alineados con el resto.
    if (project.is_system) {
        menuBtn.style.visibility = 'hidden';
        menuBtn.tabIndex = -1;
        menuBtn.setAttribute('aria-hidden', 'true');
    }
    card.appendChild(menuBtn);

    return card;
}

function fillTaskListElement(container, projectId) {
    container.innerHTML = '';
    const tasks = projectsState.tasksByProject[projectId];
    const summary = projectsState.summaryByProject[projectId];
    // Clave string: el backend serializa task_id así porque JSON no admite
    // claves numéricas.
    const secondsByTask = (summary && summary.seconds_by_task) || {};

    if (!tasks) {
        const loading = document.createElement('p');
        loading.className = 'empty-state';
        loading.textContent = 'Cargando tareas...';
        container.appendChild(loading);
    } else {
        tasks.forEach(task => {
            const row = document.createElement('label');
            row.className = 'task-row' + (task.is_done ? ' done' : '');
            row.dataset.taskId = String(task.id);
            row.dataset.timerTask = String(task.id); // ver syncTimerMarks()

            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.className = 'task-check';
            checkbox.checked = task.is_done;

            const title = document.createElement('span');
            title.className = 'task-title';
            title.textContent = task.title;

            const taskSeconds = secondsByTask[String(task.id)] || 0;

            // ▶ arranca el cronómetro apuntando a esta tarea. En una tarea ya
            // hecha no tiene sentido, así que no se pinta.
            const playBtn = document.createElement('button');
            playBtn.type = 'button';
            playBtn.className = 'task-play';
            playBtn.dataset.labelIdle = `Cronometrar la tarea ${task.title}`;
            playBtn.dataset.labelTiming = 'Detener y guardar el tiempo';
            playBtn.setAttribute('aria-label', playBtn.dataset.labelIdle);
            playBtn.title = playBtn.dataset.labelIdle;
            playBtn.innerHTML = '<span class="timer-idle">▶</span><span class="timer-on">■</span>';

            const deleteBtn = document.createElement('button');
            deleteBtn.type = 'button';
            deleteBtn.className = 'task-delete';
            deleteBtn.setAttribute('aria-label', 'Eliminar tarea');
            deleteBtn.textContent = '×';

            // Siempre visible, incluso en 0m: si solo apareciera cuando hay
            // tiempo, una tarea sin registros no se distinguiría de una a la
            // que la columna no llega.
            // Mientras corre, el total cede su sitio al reloj en vivo
            const time = document.createElement('span');
            time.className = 'task-time';
            time.innerHTML = '<span class="timer-idle"></span><span class="timer-live"></span>';
            time.firstChild.textContent = formatDuration(taskSeconds);

            row.appendChild(checkbox);
            row.appendChild(title);
            row.appendChild(time);
            if (!task.is_done) row.appendChild(playBtn);
            row.appendChild(deleteBtn);
            container.appendChild(row);
        });

        // El tiempo registrado en el proyecto sin elegir tarea. Sin esta línea
        // las tareas no sumarían el total que muestra la tarjeta.
        if (summary && summary.seconds_no_task > 0) {
            const orphan = document.createElement('p');
            orphan.className = 'task-orphan-time';
            orphan.textContent = `Sin tarea: ${formatDuration(summary.seconds_no_task)}`;
            container.appendChild(orphan);
        }
    }

    const form = document.createElement('form');
    form.className = 'task-add';

    const input = document.createElement('input');
    input.type = 'text';
    input.placeholder = 'Nueva tarea';
    input.maxLength = 200;

    const submitBtn = document.createElement('button');
    submitBtn.type = 'submit';
    submitBtn.textContent = '+';
    submitBtn.setAttribute('aria-label', 'Agregar tarea');

    form.appendChild(input);
    form.appendChild(submitBtn);
    container.appendChild(form);

    container.appendChild(buildSessionLog(projectId, tasks));
}

// Historial de tiempo del proyecto. Los registros son append-only: se crean y
// se borran, no se editan, así que esta lista es la única forma de deshacer
// un registro equivocado desde la UI.
function buildSessionLog(projectId, tasks) {
    const wrapper = document.createElement('div');
    wrapper.className = 'session-log';

    const heading = document.createElement('h4');
    heading.className = 'session-log-title';
    heading.textContent = 'Registros de tiempo';
    wrapper.appendChild(heading);

    const sessions = projectsState.sessionsByProject[projectId];
    if (!sessions) {
        const loading = document.createElement('p');
        loading.className = 'empty-state';
        loading.textContent = 'Cargando registros...';
        wrapper.appendChild(loading);
        loadSessions(projectId);
        return wrapper;
    }

    if (sessions.length === 0) {
        const empty = document.createElement('p');
        empty.className = 'empty-state';
        empty.textContent = 'Todavía no hay tiempo registrado en este proyecto.';
        wrapper.appendChild(empty);
        return wrapper;
    }

    const titleByTask = {};
    (tasks || []).forEach(task => { titleByTask[task.id] = task.title; });

    const RECENT_LIMIT = 10;
    sessions.slice(0, RECENT_LIMIT).forEach(session => {
        const row = document.createElement('div');
        row.className = 'session-row';
        row.dataset.sessionId = String(session.id);

        const origin = document.createElement('span');
        origin.className = 'session-origin';
        const originInfo = sessionOrigin(session);
        origin.textContent = originInfo.icon;
        origin.title = originInfo.title;

        const body = document.createElement('div');
        body.className = 'session-body';

        const when = document.createElement('span');
        when.className = 'session-when';
        when.textContent = `${formatShortDate(session.session_date)} · ${formatClockRange(session)} · ${formatDuration(session.duration_seconds)}`;
        body.appendChild(when);

        // El título solo está disponible si las tareas ya se cargaron; una tarea
        // borrada deja registros huérfanos que siguen contando en el total.
        const details = [];
        if (session.task_id && titleByTask[session.task_id]) {
            details.push(titleByTask[session.task_id]);
        }
        if (session.note) {
            details.push(session.note);
        }
        if (details.length > 0) {
            const detail = document.createElement('span');
            detail.className = 'session-detail';
            detail.textContent = details.join(' — ');
            body.appendChild(detail);
        }

        // El comportamiento vive en pomodoro.js, que reabre su propio modal.
        const editBtn = document.createElement('button');
        editBtn.type = 'button';
        editBtn.className = 'session-edit';
        editBtn.setAttribute('aria-label', 'Editar registro');
        editBtn.title = 'Editar registro';
        editBtn.textContent = '✎';

        const deleteBtn = document.createElement('button');
        deleteBtn.type = 'button';
        deleteBtn.className = 'session-delete';
        deleteBtn.setAttribute('aria-label', 'Eliminar registro');
        deleteBtn.textContent = '×';

        row.appendChild(origin);
        row.appendChild(body);
        row.appendChild(editBtn);
        row.appendChild(deleteBtn);
        wrapper.appendChild(row);
    });

    if (sessions.length > RECENT_LIMIT) {
        const more = document.createElement('p');
        more.className = 'session-more';
        more.textContent = `Mostrando ${RECENT_LIMIT} de ${sessions.length} registros.`;
        wrapper.appendChild(more);
    }

    return wrapper;
}

function buildTaskListElement(projectId) {
    const container = document.createElement('div');
    container.className = 'task-list';
    container.id = `tasks-${projectId}`;
    container.dataset.projectId = String(projectId);
    fillTaskListElement(container, projectId);
    return container;
}

function renderProjects() {
    projectsList.innerHTML = '';
    const projects = projectsState.projects;
    projectsEmpty.classList.toggle('hidden', projects.length > 0);

    projects.forEach(project => {
        projectsList.appendChild(buildProjectCard(project));

        if (projectsState.expanded.has(project.id)) {
            projectsList.appendChild(buildTaskListElement(project.id));
            if (!projectsState.tasksByProject[project.id]) {
                loadTasks(project.id);
            }
        }
    });
    syncTimerMarks();
}

// ============================================
// Delegación de eventos sobre #projectsList
// ============================================

projectsList.addEventListener('click', (event) => {
    const toggleBtn = event.target.closest('.project-toggle');
    if (toggleBtn) {
        const projectId = Number(toggleBtn.closest('.project-card').dataset.projectId);
        if (projectsState.expanded.has(projectId)) {
            projectsState.expanded.delete(projectId);
        } else {
            projectsState.expanded.add(projectId);
        }
        renderProjects();
        return;
    }

    const menuBtn = event.target.closest('.project-menu');
    if (menuBtn) {
        const projectId = Number(menuBtn.closest('.project-card').dataset.projectId);
        openProjectMenu(projectId, menuBtn);
        return;
    }

    const mainArea = event.target.closest('.project-main');
    if (mainArea) {
        const projectId = Number(mainArea.closest('.project-card').dataset.projectId);
        const project = projectsState.projects.find(p => p.id === projectId);
        if (project) openEditProjectModal(project);
        return;
    }

    const deleteSessionBtn = event.target.closest('.session-delete');
    if (deleteSessionBtn) {
        const sessionId = Number(deleteSessionBtn.closest('.session-row').dataset.sessionId);
        const projectId = Number(deleteSessionBtn.closest('.task-list').dataset.projectId);
        askSessionDelete(projectId, sessionId);
        return;
    }

    // startStopwatchForTask() vive en pomodoro.js, que carga después de este
    // archivo; el click ocurre mucho más tarde, así que la global ya existe.
    const playTaskBtn = event.target.closest('.task-play');
    if (playTaskBtn) {
        const row = playTaskBtn.closest('.task-row');
        const projectId = Number(playTaskBtn.closest('.task-list').dataset.projectId);
        toggleTimerForTask(projectId, Number(row.dataset.taskId), row.querySelector('.task-title').textContent);
        return;
    }

    const deleteTaskBtn = event.target.closest('.task-delete');
    if (deleteTaskBtn) {
        const taskId = Number(deleteTaskBtn.closest('.task-row').dataset.taskId);
        const projectId = Number(deleteTaskBtn.closest('.task-list').dataset.projectId);
        removeTask(projectId, taskId);
        return;
    }
});

projectsList.addEventListener('change', (event) => {
    const checkbox = event.target.closest('.task-check');
    if (!checkbox) return;
    const taskId = Number(checkbox.closest('.task-row').dataset.taskId);
    const projectId = Number(checkbox.closest('.task-list').dataset.projectId);
    toggleTaskDone(projectId, taskId, checkbox.checked);
});

projectsList.addEventListener('submit', (event) => {
    const form = event.target.closest('.task-add');
    if (!form) return;
    event.preventDefault();
    const projectId = Number(form.closest('.task-list').dataset.projectId);
    const input = form.querySelector('input');
    const title = input.value.trim();
    if (title) {
        addTask(projectId, title);
        input.value = '';
    }
});

// ============================================
// Mutaciones de tareas
// ============================================

async function refreshAfterTaskChange(projectId) {
    delete projectsState.tasksByProject[projectId];
    await loadProjects();
}

async function toggleTaskDone(projectId, taskId, isDone) {
    try {
        await apiFetch(`/api/tasks/${taskId}?today=${getDateKey(new Date())}`, { method: 'PATCH', json: { is_done: isDone } });
    } catch (error) {
        console.error('Error al actualizar tarea:', error);
    }
    await refreshAfterTaskChange(projectId);
}

async function removeTask(projectId, taskId) {
    try {
        await apiFetch(`/api/tasks/${taskId}`, { method: 'DELETE' });
    } catch (error) {
        console.error('Error al eliminar tarea:', error);
    }
    await refreshAfterTaskChange(projectId);
}

async function addTask(projectId, title) {
    try {
        await apiFetch('/api/tasks', { method: 'POST', json: { project_id: projectId, title } });
    } catch (error) {
        console.error('Error al crear tarea:', error);
    }
    await refreshAfterTaskChange(projectId);
}

// ============================================
// Modal de crear/editar proyecto
// ============================================

function openCreateProjectModal() {
    editingProjectId = null;
    projectModalTitle.textContent = 'Nuevo Proyecto';
    projectForm.reset();
    projectColorInput.value = '#3498db';
    projectFormError.classList.add('hidden');
    showModal(projectModal);
}

function openEditProjectModal(project) {
    editingProjectId = project.id;
    projectModalTitle.textContent = 'Editar Proyecto';
    projectNameInput.value = project.name;
    projectDescriptionInput.value = project.description || '';
    projectIconInput.value = project.icon || '';
    projectColorInput.value = project.color || '#3498db';
    projectFormError.classList.add('hidden');
    showModal(projectModal);
}

// Si el POST de creación devuelve 409, el nombre ya existe (activo o
// archivado). Igual que handleSaveHabits con hábitos: si está archivado,
// se reactiva con los datos nuevos en vez de solo mostrar el error.
async function reactivateArchivedProjectByName(name, payload) {
    const data = await apiFetch('/api/projects?include_inactive=true');
    const match = data.projects.find(p => p.name === name && !p.is_active);

    if (!match) {
        throw new ApiError(`Ya existe un proyecto con el nombre "${name}"`, 409);
    }

    return apiFetch(`/api/projects/${match.id}`, {
        method: 'PATCH',
        json: { ...payload, is_active: true }
    });
}

async function submitProjectForm(event) {
    event.preventDefault();
    projectFormError.classList.add('hidden');

    const name = projectNameInput.value.trim();
    if (!name) return;

    const payload = {
        name,
        description: projectDescriptionInput.value.trim() || null,
        icon: projectIconInput.value.trim() || null,
        color: projectColorInput.value,
    };

    try {
        if (editingProjectId) {
            await apiFetch(`/api/projects/${editingProjectId}`, { method: 'PATCH', json: payload });
        } else {
            try {
                await apiFetch('/api/projects', { method: 'POST', json: { ...payload, order: 0 } });
            } catch (err) {
                if (err instanceof ApiError && err.status === 409) {
                    await reactivateArchivedProjectByName(name, { ...payload, order: 0 });
                } else {
                    throw err;
                }
            }
        }
        hideModal(projectModal);
        await loadProjects();
    } catch (err) {
        showError(projectFormError, err.message || 'Error al guardar el proyecto');
    }
}

projectForm.addEventListener('submit', submitProjectForm);
addProjectBtn.addEventListener('click', openCreateProjectModal);
closeProjectModalBtn.addEventListener('click', () => hideModal(projectModal));
projectModal.querySelector('.modal-overlay').addEventListener('click', () => hideModal(projectModal));

// ============================================
// Menú del proyecto: archivar o eliminar
// ============================================
//
// Un menú pequeño junto al ⋯ en vez de un modal con tres botones grandes.
// Archivar es reversible y va directo; eliminar pide confirmación.

const projectMenu = document.createElement('div');
projectMenu.className = 'project-menu-popover hidden';
projectMenu.setAttribute('role', 'menu');
projectMenu.innerHTML = `
    <button type="button" role="menuitem" data-project-action="archive">📦 Archivar</button>
    <button type="button" role="menuitem" data-project-action="delete" class="danger">🗑️ Eliminar…</button>
`;
document.body.appendChild(projectMenu);

function openProjectMenu(projectId, anchor) {
    if (!projectMenu.classList.contains('hidden') && pendingProjectId === projectId) {
        closeProjectMenu();
        return;
    }
    pendingProjectId = projectId;
    projectMenu.classList.remove('hidden');
    // Fijo a la ventana, alineado a la derecha del ⋯ y sin salirse de ella:
    // si no cabe debajo, se abre hacia arriba.
    const rect = anchor.getBoundingClientRect();
    const width = projectMenu.offsetWidth;
    const height = projectMenu.offsetHeight;
    const fitsBelow = rect.bottom + 4 + height <= window.innerHeight - 8;
    projectMenu.style.top = `${fitsBelow ? rect.bottom + 4 : Math.max(8, rect.top - 4 - height)}px`;
    projectMenu.style.left = `${Math.max(8, Math.min(rect.right - width, window.innerWidth - width - 8))}px`;
    projectMenu.querySelector('button').focus();
}

function closeProjectMenu() {
    projectMenu.classList.add('hidden');
}

document.addEventListener('click', (event) => {
    if (projectMenu.classList.contains('hidden')) return;
    if (projectMenu.contains(event.target) || event.target.closest('.project-menu')) return;
    closeProjectMenu();
});
document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') closeProjectMenu();
});
// Posición fija: al desplazar o cambiar de tamaño quedaría suelto
window.addEventListener('scroll', closeProjectMenu, true);
window.addEventListener('resize', closeProjectMenu);

projectMenu.addEventListener('click', (event) => {
    const item = event.target.closest('[data-project-action]');
    if (!item || pendingProjectId == null) return;
    closeProjectMenu();
    if (item.dataset.projectAction === 'archive') {
        archivePendingProject();
    } else {
        openProjectDeleteModal(pendingProjectId);
    }
});

async function archivePendingProject() {
    if (pendingProjectId == null) return;
    try {
        await apiFetch(`/api/projects/${pendingProjectId}`, { method: 'PATCH', json: { is_active: false } });
    } catch (error) {
        console.error('Error al archivar proyecto:', error);
    }
    pendingProjectId = null;
    await loadProjects();
}

function updateProjectDeleteButton() {
    confirmProjectDeleteBtn.textContent = projectDeleteTimeInput.checked
        ? 'Eliminar proyecto y tiempo'
        : 'Eliminar';
}

function openProjectDeleteModal(projectId) {
    const project = projectsState.projects.find(p => p.id === projectId);
    if (!project) return;
    pendingProjectId = projectId;

    const summary = projectsState.summaryByProject[projectId];
    const taskTotal = summary ? summary.task_total : 0;
    const seconds = summary ? summary.total_seconds : 0;

    document.getElementById('projectDeleteTitle').textContent = `¿Eliminar "${project.name}"?`;
    const tasksText = taskTotal === 1 ? 'Su tarea' : `Sus ${taskTotal} tareas`;
    if (taskTotal > 0 && seconds > 0) {
        projectDeleteMessage.textContent = `${tasksText} y su tiempo pasarán a Sin asignar.`;
    } else if (taskTotal > 0) {
        projectDeleteMessage.textContent = `${tasksText} ${taskTotal === 1 ? 'pasará' : 'pasarán'} a Sin asignar.`;
    } else if (seconds > 0) {
        projectDeleteMessage.textContent = 'Su tiempo registrado pasará a Sin asignar.';
    } else {
        projectDeleteMessage.textContent = 'No tiene tareas ni tiempo registrado.';
    }

    projectDeleteTimeInput.checked = false;
    projectDeleteTimeLabel.textContent = `Borrar también su tiempo registrado (${formatDuration(seconds)})`;
    projectDeleteTimeOption.classList.toggle('hidden', seconds === 0);
    updateProjectDeleteButton();
    showModal(projectDeleteModal);
}

function closeProjectDeleteModal() {
    hideModal(projectDeleteModal);
    pendingProjectId = null;
}

async function deletePendingProject() {
    if (pendingProjectId == null) return;
    const projectId = pendingProjectId;
    const deleteSessions = projectDeleteTimeInput.checked;
    try {
        await apiFetch(`/api/projects/${projectId}${deleteSessions ? '?delete_sessions=true' : ''}`, { method: 'DELETE' });
    } catch (error) {
        console.error('Error al eliminar proyecto:', error);
    }
    // Sus tareas ahora son de "Sin asignar": se invalida toda la caché
    projectsState.tasksByProject = {};
    projectsState.expanded.delete(projectId);
    closeProjectDeleteModal();
    await loadProjects();
}

projectDeleteTimeInput.addEventListener('change', updateProjectDeleteButton);
confirmProjectDeleteBtn.addEventListener('click', deletePendingProject);
document.getElementById('cancelProjectDeleteBtn').addEventListener('click', closeProjectDeleteModal);
projectDeleteModal.querySelector('.modal-overlay').addEventListener('click', closeProjectDeleteModal);

// ============================================
// Registro en los hooks de script.js (Fase 0)
// ============================================

window.appDataHooks.push(loadProjects);
