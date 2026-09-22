// ============================================
// Tablero kanban de la vista Proyectos
// ============================================
//
// Cada tablero tiene sus columnas y sus tareas viven en ellas; el proyecto es
// una etiqueta de la tarea. La vista Lista es la de projects.js (proyectos
// con sus tareas), y este archivo solo alterna entre las dos.
//
// Todo cambio termina en refreshAfterBoardChange() -> loadProjects(), que
// dispara projectsChangedHooks: así el tablero, la lista y los selects del
// pomodoro se refrescan por el mismo camino.

const PROJECTS_VIEW_KEY = 'projects_view';   // 'board' | 'list'
const SELECTED_BOARD_KEY = 'board_selected'; // id del último tablero abierto

const boardState = {
    boards: [],             // BoardResponse[] con sus columnas
    boardId: null,
    tasks: [],              // TaskResponse[] del tablero actual
    tags: [],               // TagResponse[]
    projects: [],           // ProjectResponse[], archivados incluidos, para las etiquetas
    filterProjects: new Set(),
    filterTags: new Set(),
    mobileColumnId: null,   // la columna visible en pantallas angostas
    view: 'board',
};

const boardSelect = document.getElementById('boardSelect');
const boardView = document.getElementById('boardView');
const listView = document.getElementById('listView');
const boardFilters = document.getElementById('boardFilters');
const boardSummary = document.getElementById('boardSummary');
const boardColumnTabs = document.getElementById('boardColumnTabs');
const boardColumns = document.getElementById('boardColumns');
const viewToggleBtns = document.querySelectorAll('.view-toggle-btn');

// Arrastrar solo con un puntero fino que además flota (mouse, trackpad). En
// táctil, HTML5 drag & drop no funciona, y ahí está "Mover a…".
const canDragCards = !!(window.matchMedia && window.matchMedia('(hover: hover) and (pointer: fine)').matches);
const wideBoardQuery = window.matchMedia ? window.matchMedia('(min-width: 900px)') : null;

function readStored(key) {
    try {
        return localStorage.getItem(key);
    } catch (error) {
        return null;
    }
}

function writeStored(key, value) {
    try {
        localStorage.setItem(key, value);
    } catch (error) {
        // Modo privado o almacenamiento bloqueado: la preferencia no se recuerda.
    }
}

// ============================================
// Carga
// ============================================

async function loadBoard() {
    if (!getToken()) return;

    try {
        const [boardsData, tagsData, projectsData] = await Promise.all([
            apiFetch('/api/boards'),
            apiFetch('/api/tags'),
            apiFetch('/api/projects?include_inactive=true'),
        ]);
        boardState.boards = boardsData.boards;
        boardState.tags = tagsData.tags;
        boardState.projects = projectsData.projects;

        const stored = Number(readStored(SELECTED_BOARD_KEY));
        const wanted = boardState.boardId || stored;
        const exists = boardState.boards.some(b => b.id === wanted);
        boardState.boardId = exists ? wanted : (boardState.boards[0] ? boardState.boards[0].id : null);

        if (boardState.boardId !== null) {
            const tasksData = await apiFetch(`/api/tasks?board_id=${boardState.boardId}`);
            boardState.tasks = tasksData.tasks;
        } else {
            boardState.tasks = [];
        }

        renderBoardSelect();
        renderBoard();
    } catch (error) {
        console.error('Error al cargar el tablero:', error);
    }
}

async function refreshAfterBoardChange() {
    // La lista cachea las tareas por proyecto: se invalida entera porque una
    // tarjeta puede haber cambiado de proyecto, de columna o de "hecha".
    projectsState.tasksByProject = {};
    await loadProjects();
}

function currentBoard() {
    return boardState.boards.find(b => b.id === boardState.boardId) || null;
}

function projectById(projectId) {
    return boardState.projects.find(p => p.id === projectId) || null;
}

// Tiempo por tarea, del mismo resumen que usa la lista: así los dos muestran
// lo mismo. Solo cubre proyectos activos (el resumen no trae archivados).
function boardTaskSeconds(task) {
    const summary = projectsState.summaryByProject[task.project_id];
    return summary && summary.seconds_by_task ? (summary.seconds_by_task[String(task.id)] || 0) : 0;
}

// ============================================
// Filtros
// ============================================

// Proyectos y etiquetas combinan con Y; dentro de cada grupo, con O.
function filteredTasks() {
    return boardState.tasks.filter(task => {
        if (boardState.filterProjects.size && !boardState.filterProjects.has(task.project_id)) return false;
        if (boardState.filterTags.size && !task.tag_ids.some(id => boardState.filterTags.has(id))) return false;
        return true;
    });
}

function buildFilterChip(label, color, pressed, dataset) {
    const chip = document.createElement('button');
    chip.type = 'button';
    chip.className = 'filter-chip';
    chip.setAttribute('aria-pressed', String(pressed));
    Object.assign(chip.dataset, dataset);
    if (color) chip.style.setProperty('--chip-color', color);

    const dot = document.createElement('span');
    dot.className = 'filter-chip-dot';
    chip.appendChild(dot);
    chip.appendChild(document.createTextNode(label));
    return chip;
}

function renderFilters() {
    boardFilters.innerHTML = '';

    // Solo lo que aparece en este tablero: un filtro que no puede devolver
    // nada solo estorba.
    const projectIds = new Set(boardState.tasks.map(t => t.project_id));
    const tagIds = new Set(boardState.tasks.flatMap(t => t.tag_ids));

    const projects = boardState.projects
        .filter(p => projectIds.has(p.id))
        .sort((a, b) => Number(a.is_system) - Number(b.is_system) || a.name.localeCompare(b.name));
    const tags = boardState.tags.filter(t => tagIds.has(t.id));

    const addRow = (title, chips) => {
        if (chips.length === 0) return;
        const row = document.createElement('div');
        row.className = 'filter-row';
        const label = document.createElement('span');
        label.className = 'filter-row-label';
        label.textContent = title;
        row.appendChild(label);
        chips.forEach(chip => row.appendChild(chip));
        boardFilters.appendChild(row);
    };

    addRow('Proyectos', projects.map(p => buildFilterChip(
        p.icon ? `${p.icon} ${p.name}` : p.name,
        p.color, boardState.filterProjects.has(p.id), { filterProject: p.id }
    )));
    addRow('Etiquetas', tags.map(t => buildFilterChip(
        t.name, t.color, boardState.filterTags.has(t.id), { filterTag: t.id }
    )));

    if (boardState.filterProjects.size || boardState.filterTags.size) {
        const clear = document.createElement('button');
        clear.type = 'button';
        clear.className = 'filter-clear';
        clear.textContent = 'Quitar filtros';
        boardFilters.appendChild(clear);
    }
}

boardFilters.addEventListener('click', (event) => {
    const chip = event.target.closest('.filter-chip');
    if (chip) {
        const toggle = (set, id) => (set.has(id) ? set.delete(id) : set.add(id));
        if (chip.dataset.filterProject) toggle(boardState.filterProjects, Number(chip.dataset.filterProject));
        if (chip.dataset.filterTag) toggle(boardState.filterTags, Number(chip.dataset.filterTag));
        renderBoard();
        return;
    }
    if (event.target.closest('.filter-clear')) {
        boardState.filterProjects.clear();
        boardState.filterTags.clear();
        renderBoard();
    }
});

// ============================================
// Render
// ============================================

function renderBoardSelect() {
    boardSelect.innerHTML = '';
    boardState.boards.forEach(board => {
        const option = document.createElement('option');
        option.value = String(board.id);
        option.textContent = board.name;
        boardSelect.appendChild(option);
    });
    if (boardState.boardId !== null) boardSelect.value = String(boardState.boardId);
}

function buildCard(task, columns) {
    const card = document.createElement('article');
    card.className = 'board-card';
    card.dataset.taskId = String(task.id);
    card.tabIndex = 0;
    card.draggable = canDragCards;
    card.setAttribute('aria-label', task.title);

    const head = document.createElement('div');
    head.className = 'board-card-head';

    const title = document.createElement('span');
    title.className = 'board-card-title';
    title.textContent = task.title;

    const time = document.createElement('span');
    time.className = 'board-card-time';
    time.textContent = formatDuration(boardTaskSeconds(task));

    // El cronómetro se puede arrancar en cualquier columna, y no mueve la
    // tarjeta: solo el usuario la cambia de columna.
    const play = document.createElement('button');
    play.type = 'button';
    play.className = 'board-card-play';
    play.title = 'Cronometrar esta tarea';
    play.setAttribute('aria-label', `Cronometrar ${task.title}`);
    play.textContent = '▶';

    head.appendChild(title);
    head.appendChild(time);
    head.appendChild(play);
    card.appendChild(head);

    const meta = document.createElement('div');
    meta.className = 'board-card-meta';

    const project = projectById(task.project_id);
    if (project) {
        const badge = document.createElement('span');
        badge.className = 'board-card-project' + (project.is_system ? ' unassigned' : '');
        if (!project.is_system && project.color) badge.style.setProperty('--chip-color', project.color);
        badge.textContent = project.name;
        meta.appendChild(badge);
    }

    task.tag_ids.forEach(tagId => {
        const tag = boardState.tags.find(t => t.id === tagId);
        if (!tag) return;
        const chip = document.createElement('span');
        chip.className = 'board-card-tag';
        if (tag.color) chip.style.setProperty('--chip-color', tag.color);
        chip.textContent = tag.name;
        meta.appendChild(chip);
    });

    if (task.checklist_total > 0) {
        const checklist = document.createElement('span');
        checklist.className = 'board-card-count' + (task.checklist_done === task.checklist_total ? ' complete' : '');
        checklist.title = 'Checklist';
        checklist.textContent = `☑ ${task.checklist_done}/${task.checklist_total}`;
        meta.appendChild(checklist);
    }
    if (task.comment_count > 0) {
        const comments = document.createElement('span');
        comments.className = 'board-card-count';
        comments.title = 'Comentarios';
        comments.textContent = `💬 ${task.comment_count}`;
        meta.appendChild(comments);
    }
    card.appendChild(meta);

    // Un <select> nativo: en el teléfono abre el selector del sistema, que
    // es la forma más cómoda de elegir columna con el dedo. Con mouse se
    // arrastra, y el CSS lo oculta.
    const actions = document.createElement('div');
    actions.className = 'board-card-actions';

    const move = document.createElement('select');
    move.className = 'board-card-move';
    move.setAttribute('aria-label', `Mover ${task.title} a otra columna`);
    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = 'Mover a…';
    move.appendChild(placeholder);
    columns.forEach(column => {
        if (column.id === task.column_id) return;
        const option = document.createElement('option');
        option.value = String(column.id);
        option.textContent = column.name;
        move.appendChild(option);
    });

    actions.appendChild(move);
    card.appendChild(actions);

    return card;
}

function buildColumn(column, tasks, columns) {
    const section = document.createElement('section');
    section.className = 'board-column';
    section.dataset.columnId = String(column.id);
    section.setAttribute('aria-label', column.name);
    if (column.color) section.style.setProperty('--column-color', column.color);
    if (column.id === boardState.mobileColumnId) section.classList.add('is-current');

    const header = document.createElement('header');
    header.className = 'board-column-header';
    const name = document.createElement('h3');
    name.className = 'board-column-name';
    name.textContent = column.name;
    const count = document.createElement('span');
    count.className = 'board-column-count';
    count.textContent = String(tasks.length);
    header.appendChild(name);
    header.appendChild(count);
    section.appendChild(header);

    const list = document.createElement('div');
    list.className = 'board-cards';
    tasks.forEach(task => list.appendChild(buildCard(task, columns)));
    if (tasks.length === 0) {
        const empty = document.createElement('p');
        empty.className = 'board-column-empty';
        empty.textContent = canDragCards ? 'Arrastra tarjetas aquí' : 'Sin tarjetas';
        list.appendChild(empty);
    }
    section.appendChild(list);

    const form = document.createElement('form');
    form.className = 'board-add';
    const input = document.createElement('input');
    input.type = 'text';
    input.maxLength = 200;
    input.placeholder = '+ Añadir tarjeta';
    input.setAttribute('aria-label', `Añadir tarjeta en ${column.name}`);
    form.appendChild(input);
    section.appendChild(form);

    return section;
}

function renderBoard() {
    const board = currentBoard();
    boardColumns.innerHTML = '';
    boardColumnTabs.innerHTML = '';

    if (!board) {
        boardFilters.innerHTML = '';
        boardSummary.textContent = '';
        return;
    }

    renderFilters();

    const visible = filteredTasks();
    const byColumn = new Map(board.columns.map(c => [c.id, []]));
    visible.forEach(task => {
        if (byColumn.has(task.column_id)) byColumn.get(task.column_id).push(task);
    });

    if (!byColumn.has(boardState.mobileColumnId)) {
        // Por defecto, la primera columna "doing" con algo: es donde se trabaja
        const doing = board.columns.find(c => c.category === 'doing' && byColumn.get(c.id).length > 0);
        boardState.mobileColumnId = (doing || board.columns[0]).id;
    }

    // Una tarea con dos etiquetas del filtro es una sola tarea: sumando por
    // tarjeta visible, su tiempo cuenta una vez.
    const totalSeconds = visible.reduce((sum, task) => sum + boardTaskSeconds(task), 0);
    const filtered = boardState.filterProjects.size || boardState.filterTags.size;
    const taskWord = visible.length === 1 ? 'tarea' : 'tareas';
    boardSummary.textContent = `${visible.length} ${taskWord} · ${formatDuration(totalSeconds)}${filtered ? ' (con filtro)' : ''}`;

    board.columns.forEach(column => {
        const tasks = byColumn.get(column.id);

        const tab = document.createElement('button');
        tab.type = 'button';
        tab.className = 'board-column-tab';
        tab.setAttribute('role', 'tab');
        tab.setAttribute('aria-selected', String(column.id === boardState.mobileColumnId));
        tab.dataset.columnId = String(column.id);
        tab.textContent = `${column.name} ${tasks.length}`;
        boardColumnTabs.appendChild(tab);

        boardColumns.appendChild(buildColumn(column, tasks, board.columns));
    });
}

// ============================================
// Vista: tablero o lista
// ============================================

function applyWideLayout() {
    // Solo con el tablero a la vista: el calendario y la lista están
    // pensados para la columna angosta de siempre.
    const wide = boardState.view === 'board'
        && currentViewIndex === 1
        && !!(wideBoardQuery && wideBoardQuery.matches);
    document.body.classList.toggle('board-wide', wide);
}

function setProjectsView(view) {
    boardState.view = view === 'list' ? 'list' : 'board';
    writeStored(PROJECTS_VIEW_KEY, boardState.view);

    boardView.classList.toggle('hidden', boardState.view !== 'board');
    boardSelect.classList.toggle('hidden', boardState.view !== 'board');
    listView.classList.toggle('hidden', boardState.view !== 'list');
    viewToggleBtns.forEach(btn => {
        btn.setAttribute('aria-pressed', String(btn.dataset.projectsView === boardState.view));
    });
    applyWideLayout();
}

viewToggleBtns.forEach(btn => {
    btn.addEventListener('click', () => setProjectsView(btn.dataset.projectsView));
});

boardSelect.addEventListener('change', () => {
    boardState.boardId = Number(boardSelect.value);
    writeStored(SELECTED_BOARD_KEY, String(boardState.boardId));
    boardState.filterProjects.clear();
    boardState.filterTags.clear();
    boardState.mobileColumnId = null;
    loadBoard();
});

boardColumnTabs.addEventListener('click', (event) => {
    const tab = event.target.closest('.board-column-tab');
    if (!tab) return;
    boardState.mobileColumnId = Number(tab.dataset.columnId);
    renderBoard();
});

// ============================================
// Mutaciones
// ============================================

async function moveTaskToColumn(taskId, columnId) {
    const task = boardState.tasks.find(t => t.id === taskId);
    if (!task || task.column_id === columnId) return;

    // Optimista: la tarjeta cambia de columna ya, y el refresco confirma.
    task.column_id = columnId;
    renderBoard();

    try {
        await apiFetch(`/api/tasks/${taskId}?today=${getDateKey(new Date())}`, {
            method: 'PATCH',
            json: { column_id: columnId },
        });
    } catch (error) {
        console.error('Error al mover la tarjeta:', error);
    }
    await refreshAfterBoardChange();
}

async function addCard(columnId, title) {
    const payload = { title, column_id: columnId };
    // Con un solo proyecto filtrado, la tarjeta nueva nace en él: si no,
    // desaparecería del tablero en cuanto se crea.
    if (boardState.filterProjects.size === 1) {
        payload.project_id = [...boardState.filterProjects][0];
    }
    try {
        await apiFetch(`/api/tasks?today=${getDateKey(new Date())}`, { method: 'POST', json: payload });
    } catch (error) {
        console.error('Error al crear la tarjeta:', error);
    }
    // Con un filtro de etiquetas activo la tarjeta nueva (sin etiquetas) no
    // se vería: se quita ese filtro para no crear algo invisible.
    boardState.filterTags.clear();
    await refreshAfterBoardChange();
}

boardColumns.addEventListener('submit', (event) => {
    const form = event.target.closest('.board-add');
    if (!form) return;
    event.preventDefault();
    const input = form.querySelector('input');
    const title = input.value.trim();
    if (!title) return;
    input.value = '';
    addCard(Number(form.closest('.board-column').dataset.columnId), title);
});

boardColumns.addEventListener('change', (event) => {
    const move = event.target.closest('.board-card-move');
    if (!move || !move.value) return;
    const taskId = Number(move.closest('.board-card').dataset.taskId);
    moveTaskToColumn(taskId, Number(move.value));
});

boardColumns.addEventListener('click', (event) => {
    const play = event.target.closest('.board-card-play');
    if (play) {
        const task = boardState.tasks.find(t => t.id === Number(play.closest('.board-card').dataset.taskId));
        if (task) startTimerForTask(task.project_id, task.id, 'stopwatch', task.title);
    }
});

// ============================================
// Arrastrar y soltar (solo mouse/trackpad)
// ============================================

let draggedTaskId = null;

boardColumns.addEventListener('dragstart', (event) => {
    const card = event.target.closest('.board-card');
    if (!card) return;
    draggedTaskId = Number(card.dataset.taskId);
    event.dataTransfer.effectAllowed = 'move';
    // Firefox no arranca el arrastre sin datos
    event.dataTransfer.setData('text/plain', card.dataset.taskId);
    card.classList.add('dragging');
});

boardColumns.addEventListener('dragover', (event) => {
    const column = event.target.closest('.board-column');
    if (!column || draggedTaskId === null) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
    boardColumns.querySelectorAll('.board-column.drop-target').forEach(c => {
        if (c !== column) c.classList.remove('drop-target');
    });
    column.classList.add('drop-target');
});

boardColumns.addEventListener('dragleave', (event) => {
    const column = event.target.closest('.board-column');
    if (column && !column.contains(event.relatedTarget)) column.classList.remove('drop-target');
});

boardColumns.addEventListener('drop', (event) => {
    const column = event.target.closest('.board-column');
    if (!column || draggedTaskId === null) return;
    event.preventDefault();
    const taskId = draggedTaskId;
    draggedTaskId = null;
    moveTaskToColumn(taskId, Number(column.dataset.columnId));
});

boardColumns.addEventListener('dragend', () => {
    draggedTaskId = null;
    boardColumns.querySelectorAll('.dragging, .drop-target').forEach(el => {
        el.classList.remove('dragging', 'drop-target');
    });
});

// ============================================
// Hooks
// ============================================

function initBoard() {
    setProjectsView(readStored(PROJECTS_VIEW_KEY) || 'board');
    if (wideBoardQuery && wideBoardQuery.addEventListener) {
        wideBoardQuery.addEventListener('change', applyWideLayout);
    }
}

function resetBoard() {
    // El tablero recordado es de esta cuenta; la vista (tablero o lista) es
    // una preferencia del dispositivo y se queda.
    try {
        localStorage.removeItem(SELECTED_BOARD_KEY);
    } catch (error) {
        // Almacenamiento bloqueado: no había nada que borrar.
    }
    boardState.boards = [];
    boardState.boardId = null;
    boardState.tasks = [];
    boardState.tags = [];
    boardState.projects = [];
    boardState.filterProjects.clear();
    boardState.filterTags.clear();
    boardState.mobileColumnId = null;
    boardColumns.innerHTML = '';
    boardColumnTabs.innerHTML = '';
    boardFilters.innerHTML = '';
    boardSummary.textContent = '';
}

window.appInitHooks.push(initBoard);
window.appLogoutHooks.push(resetBoard);
// loadProjects() corre en cada cambio y al entrar; el tablero va detrás de él
// porque usa su resumen para el tiempo de cada tarjeta.
window.projectsChangedHooks.push(loadBoard);
window.viewChangedHooks.push(applyWideLayout);
