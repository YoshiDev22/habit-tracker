// ============================================
// Estado
// ============================================

const projectsState = {
    projects: [],            // ProjectResponse[] (id, name, description, color, icon, ...)
    summaryByProject: {},    // { [id]: ProjectSummary }
    tasksByProject: {},      // { [id]: TaskResponse[] } — cache, se invalida en cada mutación
    expanded: new Set(),
};

let editingProjectId = null;
let pendingProjectId = null;

// Hooks que corren cada vez que cambian los proyectos o sus tareas. Se declara
// aquí porque projects.js es el dueño de ese estado; pomodoro.js se engancha
// para mantener sus selects al día sin que este archivo lo conozca.
window.projectsChangedHooks = [];

// ============================================
// Elementos del DOM
// ============================================

const tabCalendar = document.getElementById('tabCalendar');
const tabProjects = document.getElementById('tabProjects');
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

const projectActionModal = document.getElementById('projectActionModal');
const projectActionMessage = document.getElementById('projectActionMessage');
const archiveProjectBtn = document.getElementById('archiveProjectBtn');
const deleteProjectBtn = document.getElementById('deleteProjectBtn');
const cancelProjectActionBtn = document.getElementById('cancelProjectActionBtn');

// ============================================
// Tabs + swipe
// ============================================

const VIEW_COUNT = 2;
let currentViewIndex = 0;

function goToView(index, opts = {}) {
    const animate = opts.animate !== false;
    currentViewIndex = Math.max(0, Math.min(VIEW_COUNT - 1, index));

    // El popover solo tiene sentido sobre la vista Calendario.
    hideHabitPopover();

    viewsTrack.style.transition = animate ? '' : 'none';
    viewsTrack.style.transform = `translateX(${-100 * currentViewIndex}%)`;

    const tabs = [tabCalendar, tabProjects];
    tabs.forEach((tab, i) => {
        const active = i === currentViewIndex;
        tab.classList.toggle('active', active);
        tab.setAttribute('aria-selected', String(active));
        tab.tabIndex = active ? 0 : -1;
    });
    tabIndicator.style.transform = `translateX(${100 * currentViewIndex}%)`;
}

tabCalendar.addEventListener('click', () => goToView(0));
tabProjects.addEventListener('click', () => goToView(1));

// Patrón WAI-ARIA tabs: flechas, Home/End, roving tabindex.
[tabCalendar, tabProjects].forEach((tab, i) => {
    tab.addEventListener('keydown', (event) => {
        let target = null;
        if (event.key === 'ArrowRight') target = (i + 1) % VIEW_COUNT;
        else if (event.key === 'ArrowLeft') target = (i - 1 + VIEW_COUNT) % VIEW_COUNT;
        else if (event.key === 'Home') target = 0;
        else if (event.key === 'End') target = VIEW_COUNT - 1;

        if (target !== null) {
            event.preventDefault();
            goToView(target);
            [tabCalendar, tabProjects][target].focus();
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
    try {
        const [listData, summaryData] = await Promise.all([
            apiFetch('/api/projects'),
            apiFetch('/api/projects/summary'),
        ]);

        projectsState.projects = listData.projects;
        projectsState.summaryByProject = {};
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

    const menuBtn = document.createElement('button');
    menuBtn.type = 'button';
    menuBtn.className = 'project-menu';
    menuBtn.setAttribute('aria-label', 'Opciones del proyecto');
    menuBtn.textContent = '⋯';

    card.appendChild(chip);
    card.appendChild(main);
    card.appendChild(toggleBtn);
    card.appendChild(menuBtn);

    return card;
}

function fillTaskListElement(container, projectId) {
    container.innerHTML = '';
    const tasks = projectsState.tasksByProject[projectId];

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

            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.className = 'task-check';
            checkbox.checked = task.is_done;

            const title = document.createElement('span');
            title.className = 'task-title';
            title.textContent = task.title;

            const deleteBtn = document.createElement('button');
            deleteBtn.type = 'button';
            deleteBtn.className = 'task-delete';
            deleteBtn.setAttribute('aria-label', 'Eliminar tarea');
            deleteBtn.textContent = '×';

            row.appendChild(checkbox);
            row.appendChild(title);
            row.appendChild(deleteBtn);
            container.appendChild(row);
        });
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
        openProjectActionModal(projectId);
        return;
    }

    const mainArea = event.target.closest('.project-main');
    if (mainArea) {
        const projectId = Number(mainArea.closest('.project-card').dataset.projectId);
        const project = projectsState.projects.find(p => p.id === projectId);
        if (project) openEditProjectModal(project);
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
        await apiFetch(`/api/tasks/${taskId}`, { method: 'PATCH', json: { is_done: isDone } });
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
// Modal de archivar/eliminar proyecto
// ============================================

function openProjectActionModal(projectId) {
    pendingProjectId = projectId;
    const project = projectsState.projects.find(p => p.id === projectId);
    projectActionMessage.textContent = project
        ? `Elige qué hacer con "${project.name}":`
        : 'Selecciona una opción para el proyecto:';
    showModal(projectActionModal);
}

function closeProjectActionModal() {
    hideModal(projectActionModal);
    pendingProjectId = null;
}

async function archivePendingProject() {
    if (pendingProjectId == null) return;
    try {
        await apiFetch(`/api/projects/${pendingProjectId}`, { method: 'PATCH', json: { is_active: false } });
    } catch (error) {
        console.error('Error al archivar proyecto:', error);
    }
    closeProjectActionModal();
    await loadProjects();
}

async function deletePendingProject() {
    if (pendingProjectId == null) return;
    const projectId = pendingProjectId;
    try {
        await apiFetch(`/api/projects/${projectId}`, { method: 'DELETE' });
    } catch (error) {
        console.error('Error al eliminar proyecto:', error);
    }
    delete projectsState.tasksByProject[projectId];
    projectsState.expanded.delete(projectId);
    closeProjectActionModal();
    await loadProjects();
}

archiveProjectBtn.addEventListener('click', archivePendingProject);
deleteProjectBtn.addEventListener('click', deletePendingProject);
cancelProjectActionBtn.addEventListener('click', closeProjectActionModal);
projectActionModal.querySelector('.modal-overlay').addEventListener('click', closeProjectActionModal);

// ============================================
// Registro en los hooks de script.js (Fase 0)
// ============================================

window.appDataHooks.push(loadProjects);
