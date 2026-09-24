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
    loaded: false,          // ya se sabe si el usuario tiene tableros
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

        boardState.loaded = true;
        renderBoardSelect();
        renderBoard();
        refreshOpenCard();
        maybeOfferFirstBoard();
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

// Tiempo por tarea, calculado por la API junto con la tarea: sirve también
// para tareas de proyectos archivados, que el resumen de proyectos no trae.
function boardTaskSeconds(task) {
    return task.seconds || 0;
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

const NEW_BOARD_OPTION = 'new';

function renderBoardSelect() {
    boardSelect.innerHTML = '';
    boardState.boards.forEach(board => {
        const option = document.createElement('option');
        option.value = String(board.id);
        option.textContent = board.name;
        boardSelect.appendChild(option);
    });
    const create = document.createElement('option');
    create.value = NEW_BOARD_OPTION;
    create.textContent = '＋ Nuevo tablero…';
    boardSelect.appendChild(create);
    if (boardState.boardId !== null) boardSelect.value = String(boardState.boardId);
}

function buildCard(task, columns) {
    const card = document.createElement('article');
    card.className = 'board-card';
    card.dataset.taskId = String(task.id);
    card.dataset.timerTask = String(task.id); // ver syncTimerMarks() en pomodoro.js
    card.tabIndex = 0;
    card.draggable = canDragCards;
    card.setAttribute('aria-label', task.title);

    const head = document.createElement('div');
    head.className = 'board-card-head';

    const title = document.createElement('span');
    title.className = 'board-card-title';
    title.textContent = task.title;

    // Mientras corre, el total cede su sitio al reloj en vivo
    const time = document.createElement('span');
    time.className = 'board-card-time';
    time.innerHTML = '<span class="timer-idle"></span><span class="timer-live"></span>';
    time.firstChild.textContent = formatDuration(boardTaskSeconds(task));

    // El cronómetro se puede arrancar en cualquier columna, y no mueve la
    // tarjeta: solo el usuario la cambia de columna.
    const play = document.createElement('button');
    play.type = 'button';
    play.className = 'board-card-play';
    play.dataset.labelIdle = `Cronometrar ${task.title}`;
    play.dataset.labelTiming = 'Detener y guardar el tiempo';
    play.title = play.dataset.labelIdle;
    play.setAttribute('aria-label', play.dataset.labelIdle);
    play.innerHTML = '<span class="timer-idle">▶</span><span class="timer-on">■</span>';

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
    syncTimerMarks();
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
    if (boardSelect.value === NEW_BOARD_OPTION) {
        // No es un tablero: se vuelve al que estaba y se abre Organizar
        boardSelect.value = String(boardState.boardId);
        openBoardConfig({ focusNewBoard: true });
        return;
    }
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

    // Optimista: la tarjeta pasa ya al final de la otra columna, como hace el
    // servidor, y el refresco confirma.
    task.column_id = columnId;
    boardState.tasks = [...boardState.tasks.filter(t => t.id !== taskId), task];
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
    const card = event.target.closest('.board-card');
    if (!card) return;
    const task = boardState.tasks.find(t => t.id === Number(card.dataset.taskId));
    if (!task) return;

    if (event.target.closest('.board-card-play')) {
        toggleTimerForTask(task.project_id, task.id, task.title);
        return;
    }
    // El select de "Mover a…" vive dentro de la tarjeta: tocarlo no la abre
    if (event.target.closest('.board-card-move')) return;
    openCardModal(task.id);
});

boardColumns.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter' || !event.target.classList.contains('board-card')) return;
    event.preventDefault();
    openCardModal(Number(event.target.dataset.taskId));
});

// ============================================
// Arrastrar y soltar (solo mouse/trackpad)
// ============================================
//
// Una tarjeta se suelta en cualquier punto de una columna, la suya incluida:
// una línea marca dónde caerá, y al soltar se guarda el orden de la columna.

let draggedTaskId = null;
const dropIndicator = document.createElement('div');
dropIndicator.className = 'drop-indicator';

// La tarjeta (visible, y que no sea la arrastrada) delante de la que caería:
// la primera cuya mitad queda por debajo del puntero. null = al final.
function cardBeforePointer(list, clientY) {
    const cards = [...list.querySelectorAll('.board-card:not(.dragging)')];
    return cards.find(card => {
        const box = card.getBoundingClientRect();
        return clientY < box.top + box.height / 2;
    }) || null;
}

function clearDropMarks() {
    dropIndicator.remove();
    boardColumns.querySelectorAll('.dragging, .drop-target').forEach(el => {
        el.classList.remove('dragging', 'drop-target');
    });
}

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

    const list = column.querySelector('.board-cards');
    const before = cardBeforePointer(list, event.clientY);
    if (before) list.insertBefore(dropIndicator, before);
    else list.appendChild(dropIndicator);
});

boardColumns.addEventListener('dragleave', (event) => {
    const column = event.target.closest('.board-column');
    if (column && !column.contains(event.relatedTarget)) column.classList.remove('drop-target');
});

boardColumns.addEventListener('drop', (event) => {
    const column = event.target.closest('.board-column');
    if (!column || draggedTaskId === null) return;
    event.preventDefault();
    const list = column.querySelector('.board-cards');
    const before = cardBeforePointer(list, event.clientY);
    const taskId = draggedTaskId;
    draggedTaskId = null;
    clearDropMarks();
    dropTask(taskId, Number(column.dataset.columnId), before ? Number(before.dataset.taskId) : null);
});

boardColumns.addEventListener('dragend', () => {
    draggedTaskId = null;
    clearDropMarks();
});

// Suelta la tarea en la columna, delante de beforeId (null = al final). El
// orden se calcula sobre TODAS las tareas de la columna, no solo las visibles:
// con un filtro activo, las ocultas conservan su sitio relativo.
async function dropTask(taskId, columnId, beforeId) {
    const task = boardState.tasks.find(t => t.id === taskId);
    if (!task || beforeId === taskId) return;

    const others = boardState.tasks.filter(t => t.column_id === columnId && t.id !== taskId);
    let index = beforeId === null ? others.length : others.findIndex(t => t.id === beforeId);
    if (index < 0) index = others.length;
    const ordered = [...others.slice(0, index), task, ...others.slice(index)];

    const sameColumn = task.column_id === columnId;
    const current = boardState.tasks.filter(t => t.column_id === columnId).map(t => t.id);
    if (sameColumn && current.join(',') === ordered.map(t => t.id).join(',')) return;

    // Optimista: el tablero se ve ya como quedará, y el refresco lo confirma
    task.column_id = columnId;
    const rest = boardState.tasks.filter(t => t.column_id !== columnId);
    boardState.tasks = [...rest, ...ordered];
    renderBoard();

    try {
        if (!sameColumn) {
            await apiFetch(`/api/tasks/${taskId}?today=${getDateKey(new Date())}`, {
                method: 'PATCH',
                json: { column_id: columnId },
            });
        }
        await apiFetch('/api/tasks/reorder', {
            method: 'POST',
            json: { column_id: columnId, task_ids: ordered.map(t => t.id) },
        });
    } catch (error) {
        console.error('Error al mover la tarjeta:', error);
    }
    await refreshAfterBoardChange();
}

// ============================================
// Detalle de la tarjeta
// ============================================
//
// Cada campo se guarda en cuanto cambia. El tablero se refresca al cerrar (si
// algo cambió), no en cada tecla: así el modal no parpadea mientras se edita.

const cardModal = document.getElementById('cardModal');
const cardTitleInput = document.getElementById('cardTitle');
const cardTimeEl = document.getElementById('cardTime');
const cardColumnSelect = document.getElementById('cardColumn');
const cardProjectSelect = document.getElementById('cardProject');
const cardTimerEl = document.getElementById('cardTimer');
const cardNewProjectForm = document.getElementById('cardNewProjectForm');
const cardNewProjectName = document.getElementById('cardNewProjectName');
const cardNewProjectColor = document.getElementById('cardNewProjectColor');
const cardNewProjectError = document.getElementById('cardNewProjectError');
const NEW_PROJECT_OPTION = 'new';
const cardTagRow = document.getElementById('cardTagRow');
const tagPicker = document.getElementById('tagPicker');
const tagPickerList = document.getElementById('tagPickerList');
const tagPickerForm = document.getElementById('tagPickerForm');
const tagPickerName = document.getElementById('tagPickerName');
const tagPickerColor = document.getElementById('tagPickerColor');

// Color sugerido para cada etiqueta nueva: rota para que no salgan todas iguales
const TAG_COLORS = ['#3498db', '#2ecc71', '#e67e22', '#9b59b6', '#e74c3c', '#1abc9c', '#f1c40f', '#95a5a6'];
const cardNotesInput = document.getElementById('cardNotes');
const cardChecklistEl = document.getElementById('cardChecklist');
const cardChecklistProgress = document.getElementById('cardChecklistProgress');
const cardChecklistForm = document.getElementById('cardChecklistForm');
const cardCommentsEl = document.getElementById('cardComments');
const cardCommentForm = document.getElementById('cardCommentForm');

const cardHistoryEl = document.getElementById('cardHistory');
const cardHistoryMetaEl = document.getElementById('cardHistoryMeta');
const CARD_HISTORY_PREVIEW = 5;

const cardState = {
    taskId: null,
    checklist: null,  // null mientras carga
    comments: null,
    sessions: null,   // registros de tiempo de la tarea (solo foco), null mientras carga
    historyExpanded: false,
    editing: null,    // { kind: 'check' | 'comment', id } mientras se edita en el sitio
    dirty: false,     // algo cambió: refrescar el tablero al cerrar
};

function cardTask() {
    return boardState.tasks.find(t => t.id === cardState.taskId) || null;
}

function fitTitleHeight() {
    cardTitleInput.style.height = 'auto';
    cardTitleInput.style.height = `${cardTitleInput.scrollHeight}px`;
}

function renderCardColumnSelect(task) {
    // Todos los tableros activos: cambiar la tarjeta de tablero es elegir una
    // columna de otro.
    cardColumnSelect.innerHTML = '';
    boardState.boards.forEach(board => {
        const group = document.createElement('optgroup');
        group.label = board.name;
        board.columns.forEach(column => {
            const option = document.createElement('option');
            option.value = String(column.id);
            option.textContent = column.name;
            group.appendChild(option);
        });
        cardColumnSelect.appendChild(group);
    });
    cardColumnSelect.value = String(task.column_id);
}

function renderCardProjectSelect(task) {
    cardProjectSelect.innerHTML = '';
    // Los activos, y el de la tarea aunque esté archivado, para no mentir
    const projects = boardState.projects.filter(p => p.is_active || p.id === task.project_id);
    projects
        .sort((a, b) => Number(b.is_system) - Number(a.is_system) || a.name.localeCompare(b.name))
        .forEach(project => {
            const option = document.createElement('option');
            option.value = String(project.id);
            option.textContent = project.is_active ? project.name : `${project.name} (archivado)`;
            cardProjectSelect.appendChild(option);
        });
    const create = document.createElement('option');
    create.value = NEW_PROJECT_OPTION;
    create.textContent = '＋ Nuevo proyecto…';
    cardProjectSelect.appendChild(create);
    cardProjectSelect.value = String(task.project_id);
}

// Chips discretos bajo el título, con + al final para abrir el panel
function renderCardTagRow(task) {
    cardTagRow.innerHTML = '';
    boardState.tags
        .filter(tag => task.tag_ids.includes(tag.id))
        .forEach(tag => {
            const chip = document.createElement('button');
            chip.type = 'button';
            chip.className = 'card-tag-chip';
            chip.title = 'Cambiar etiquetas';
            if (tag.color) chip.style.setProperty('--chip-color', tag.color);
            chip.textContent = tag.name;
            cardTagRow.appendChild(chip);
        });

    const add = document.createElement('button');
    add.type = 'button';
    add.className = 'card-tag-add';
    add.textContent = task.tag_ids.length ? '+' : '+ Etiqueta';
    add.setAttribute('aria-label', 'Agregar o quitar etiquetas');
    add.setAttribute('aria-expanded', String(!tagPicker.classList.contains('hidden')));
    cardTagRow.appendChild(add);
}

// Una fila por etiqueta: el clic en cualquier parte de la fila la pone o la
// quita. Lo escrito en la caja de abajo filtra la lista.
function renderTagPicker(task) {
    tagPickerList.innerHTML = '';
    const filter = tagPickerName.value.trim().toLowerCase();
    const tags = boardState.tags.filter(tag => tag.name.toLowerCase().includes(filter));

    if (tags.length === 0) {
        const hint = document.createElement('p');
        hint.className = 'tag-picker-empty';
        hint.textContent = filter
            ? `Enter para crear "${tagPickerName.value.trim()}"`
            : 'Todavía no tienes etiquetas: crea la primera aquí abajo.';
        tagPickerList.appendChild(hint);
        return;
    }

    tags.forEach(tag => {
        const on = task.tag_ids.includes(tag.id);
        const row = document.createElement('button');
        row.type = 'button';
        row.className = 'tag-picker-row' + (on ? ' on' : '');
        row.dataset.tagId = String(tag.id);
        row.setAttribute('role', 'menuitemcheckbox');
        row.setAttribute('aria-checked', String(on));
        if (tag.color) row.style.setProperty('--chip-color', tag.color);

        const dot = document.createElement('span');
        dot.className = 'tag-picker-dot';
        const name = document.createElement('span');
        name.className = 'tag-picker-name';
        name.textContent = tag.name;
        const check = document.createElement('span');
        check.className = 'tag-picker-check';
        check.textContent = on ? '✓' : '';

        row.appendChild(dot);
        row.appendChild(name);
        row.appendChild(check);
        tagPickerList.appendChild(row);
    });
}

function nextTagColor() {
    return TAG_COLORS[boardState.tags.length % TAG_COLORS.length];
}

function openTagPicker() {
    const task = cardTask();
    if (!task) return;
    tagPicker.classList.remove('hidden');
    tagPickerName.value = '';
    tagPickerColor.value = nextTagColor();
    renderCardTagRow(task);
    renderTagPicker(task);
    tagPickerName.focus();
}

function closeTagPicker() {
    if (tagPicker.classList.contains('hidden')) return;
    tagPicker.classList.add('hidden');
    const task = cardTask();
    if (task) renderCardTagRow(task);
}

function isTagPickerOpen() {
    return !tagPicker.classList.contains('hidden');
}

function renderCardHeader(task) {
    if (document.activeElement !== cardTitleInput) {
        cardTitleInput.value = task.title;
        fitTitleHeight();
    }
    cardTimeEl.textContent = formatDuration(boardTaskSeconds(task));
}

// Con el detalle abierto, el tablero se recarga debajo (p. ej. al detener el
// tiempo desde la tarjeta): su tiempo tiene que seguirlo, no esperar a cerrar.
// Solo la cabecera: título y descripción pueden estar a medio escribir.
function refreshOpenCard() {
    if (cardModal.classList.contains('hidden')) return;
    const task = cardTask();
    if (!task) return;
    renderCardHeader(task);
    // El total cambió o puede haber cambiado: el historial va con él
    loadCardHistory(task.id);
}

// ============================================
// Historial de tiempo de la tarjeta
// ============================================

async function loadCardHistory(taskId) {
    try {
        const data = await apiFetch(`/api/pomodoro?task_id=${taskId}`);
        if (cardState.taskId !== taskId) return; // se cerró o se abrió otra
        // Solo foco: es lo que suma el tiempo de la tarjeta
        cardState.sessions = data.sessions.filter(s => s.mode === 'focus');
        renderCardHistory();
    } catch (error) {
        console.error('Error al cargar el historial de tiempo:', error);
    }
}

function renderCardHistory() {
    cardHistoryEl.replaceChildren();
    const sessions = cardState.sessions;
    cardHistoryMetaEl.textContent = sessions && sessions.length
        ? `· ${sessions.length} ${sessions.length === 1 ? 'registro' : 'registros'}`
        : '';

    if (sessions === null) {
        cardHistoryEl.appendChild(Object.assign(document.createElement('p'),
            { className: 'card-empty', textContent: 'Cargando…' }));
        return;
    }
    if (sessions.length === 0) {
        cardHistoryEl.appendChild(Object.assign(document.createElement('p'), {
            className: 'card-empty',
            textContent: 'Todavía no hay tiempo registrado. Empieza con ▶ o regístralo a mano.',
        }));
        return;
    }

    // Vienen del más reciente al más antiguo
    const visible = cardState.historyExpanded ? sessions : sessions.slice(0, CARD_HISTORY_PREVIEW);
    visible.forEach(session => {
        const originTitle = sessionOrigin(session).title;
        const detail = session.note ? `${originTitle} — ${session.note}` : originTitle;
        cardHistoryEl.appendChild(buildSessionRow(session, detail));
    });

    if (sessions.length > visible.length) {
        const more = document.createElement('button');
        more.type = 'button';
        more.className = 'card-history-more';
        more.dataset.action = 'more';
        more.textContent = `Ver los ${sessions.length} registros`;
        cardHistoryEl.appendChild(more);
    }
}

cardHistoryEl.addEventListener('click', async (event) => {
    const button = event.target.closest('[data-action]');
    const task = cardTask();
    if (!button || !task) return;

    if (button.dataset.action === 'more') {
        cardState.historyExpanded = true;
        renderCardHistory();
        return;
    }

    const sessionId = Number(button.closest('.session-row').dataset.sessionId);
    const session = (cardState.sessions || []).find(s => s.id === sessionId);
    if (!session) return;

    if (button.dataset.action === 'edit') {
        // Se abre encima de la tarjeta (z-index propio); al guardar,
        // loadProjects() recarga el tablero y refreshOpenCard() este historial.
        openLogTimeModal(session.project_id || task.project_id, session);
        return;
    }

    const summary = `${formatShortDate(session.session_date)} · ${formatClockRange(session)} · ${formatDuration(session.duration_seconds)}`;
    const ok = await confirmDialog(`${summary}. Se descuenta del tiempo de la tarea y de su proyecto.`, {
        title: '¿Eliminar este registro?', confirmLabel: 'Eliminar', danger: true,
    });
    if (!ok) return;
    try {
        await apiFetch(`/api/pomodoro/${sessionId}`, { method: 'DELETE' });
        await refreshAfterBoardChange();
    } catch (error) {
        console.error('Error al eliminar el registro:', error);
    }
});

function renderCardChecklist() {
    cardChecklistEl.innerHTML = '';
    const items = cardState.checklist;
    if (items === null) {
        cardChecklistProgress.textContent = '';
        cardChecklistEl.innerHTML = '<p class="card-empty">Cargando…</p>';
        return;
    }
    const done = items.filter(i => i.is_done).length;
    cardChecklistProgress.textContent = items.length ? `${done}/${items.length}` : '';

    items.forEach(item => {
        const row = document.createElement('div');
        row.className = 'card-check-row' + (item.is_done ? ' done' : '');
        row.dataset.itemId = String(item.id);

        if (isEditing('check', item.id)) {
            const input = document.createElement('input');
            input.type = 'text';
            input.className = 'card-inline-edit';
            input.maxLength = 200;
            input.value = item.text;
            input.setAttribute('aria-label', 'Editar elemento del checklist');
            row.appendChild(input);
            cardChecklistEl.appendChild(row);
            requestAnimationFrame(() => { input.focus(); input.select(); });
            return;
        }

        const label = document.createElement('label');
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.checked = item.is_done;
        const text = document.createElement('span');
        text.textContent = item.text;
        label.appendChild(checkbox);
        label.appendChild(text);

        const editBtn = document.createElement('button');
        editBtn.type = 'button';
        editBtn.className = 'card-check-edit';
        editBtn.setAttribute('aria-label', `Editar ${item.text}`);
        editBtn.title = 'Editar';
        editBtn.textContent = '✎';

        const remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'card-check-delete';
        remove.setAttribute('aria-label', `Quitar ${item.text}`);
        remove.textContent = '×';

        row.appendChild(label);
        row.appendChild(editBtn);
        row.appendChild(remove);
        cardChecklistEl.appendChild(row);
    });
}

function formatCommentDate(value) {
    // UTC naive del backend -> hora local del usuario
    return parseUtcIso(value).toLocaleString('es-MX', {
        day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
    });
}

function renderCardComments() {
    cardCommentsEl.innerHTML = '';
    const comments = cardState.comments;
    if (comments === null) {
        cardCommentsEl.innerHTML = '<p class="card-empty">Cargando…</p>';
        return;
    }
    if (comments.length === 0) {
        cardCommentsEl.innerHTML = '<p class="card-empty">Sin comentarios todavía.</p>';
        return;
    }

    // El más reciente arriba: es el que se busca al volver a una tarea
    [...comments].reverse().forEach(comment => {
        const item = document.createElement('article');
        item.className = 'card-comment';
        item.dataset.commentId = String(comment.id);

        const meta = document.createElement('div');
        meta.className = 'card-comment-meta';
        const author = document.createElement('strong');
        author.textContent = comment.author_name;
        const when = document.createElement('span');
        when.textContent = formatCommentDate(comment.created_at) + (comment.edited_at ? ' · editado' : '');
        meta.appendChild(author);
        meta.appendChild(when);

        // Solo el autor puede editarlo o borrarlo (el backend lo exige igual)
        const editing = isEditing('comment', comment.id);
        if (currentUser && comment.author_id === currentUser.id && !editing) {
            const editBtn = document.createElement('button');
            editBtn.type = 'button';
            editBtn.className = 'card-comment-edit';
            editBtn.textContent = 'Editar';
            meta.appendChild(editBtn);
            const remove = document.createElement('button');
            remove.type = 'button';
            remove.className = 'card-comment-delete';
            remove.textContent = 'Eliminar';
            meta.appendChild(remove);
        }
        item.appendChild(meta);

        if (editing) {
            const form = document.createElement('form');
            form.className = 'card-comment-edit-form';
            const textarea = document.createElement('textarea');
            textarea.className = 'card-inline-edit';
            textarea.rows = 3;
            textarea.maxLength = 2000;
            textarea.value = comment.body;
            textarea.setAttribute('aria-label', 'Editar comentario');
            const actions = document.createElement('div');
            actions.className = 'card-comment-edit-actions';
            const save = document.createElement('button');
            save.type = 'submit';
            save.className = 'card-comment-save';
            save.textContent = 'Guardar';
            const cancel = document.createElement('button');
            cancel.type = 'button';
            cancel.className = 'card-comment-cancel';
            cancel.textContent = 'Cancelar';
            actions.append(save, cancel);
            form.append(textarea, actions);
            item.appendChild(form);
            cardCommentsEl.appendChild(item);
            requestAnimationFrame(() => textarea.focus());
            return;
        }

        const body = document.createElement('p');
        body.className = 'card-comment-body';
        body.textContent = comment.body;
        item.appendChild(body);
        cardCommentsEl.appendChild(item);
    });
}

function renderCardModal() {
    const task = cardTask();
    if (!task) return;
    renderCardHeader(task);
    renderCardColumnSelect(task);
    renderCardProjectSelect(task);
    renderCardTagRow(task);
    if (isTagPickerOpen()) renderTagPicker(task);
    renderCardChecklist();
    renderCardComments();
}

async function openCardModal(taskId) {
    const task = boardState.tasks.find(t => t.id === taskId);
    if (!task) return;

    cardState.taskId = taskId;
    cardState.checklist = null;
    cardState.comments = null;
    cardState.sessions = null;
    cardState.historyExpanded = false;
    cardState.editing = null;
    cardState.dirty = false;
    cardNotesInput.value = task.notes || '';
    cardTimerEl.dataset.timerTask = String(taskId);
    tagPicker.classList.add('hidden');
    cardNewProjectForm.classList.add('hidden');

    showModal(cardModal);
    renderCardModal();
    renderCardHistory();
    syncTimerMarks();
    loadCardHistory(taskId);

    try {
        const [checklist, comments] = await Promise.all([
            apiFetch(`/api/tasks/${taskId}/checklist`),
            apiFetch(`/api/tasks/${taskId}/comments`),
        ]);
        if (cardState.taskId !== taskId) return; // se cerró o se abrió otra
        cardState.checklist = checklist.items;
        cardState.comments = comments.comments;
        renderCardChecklist();
        renderCardComments();
    } catch (error) {
        console.error('Error al cargar el detalle de la tarjeta:', error);
    }
}

async function closeCardModal() {
    // Lo que se esté escribiendo en el título o la descripción se guarda
    await saveCardText();
    hideModal(cardModal);
    const changed = cardState.dirty;
    cardState.taskId = null;
    if (changed) await refreshAfterBoardChange();
}

async function patchCardTask(payload) {
    const task = cardTask();
    if (!task) return;
    try {
        const updated = await apiFetch(`/api/tasks/${task.id}?today=${getDateKey(new Date())}`, {
            method: 'PATCH',
            json: payload,
        });
        Object.assign(task, updated);
        cardState.dirty = true;
    } catch (error) {
        console.error('Error al guardar la tarjeta:', error);
    }
    renderCardModal();
}

// Encadenados: al cerrar con la X, el blur del título y el cierre piden
// guardar casi a la vez, y el segundo tiene que ver lo que guardó el primero.
let cardTextSave = Promise.resolve();

function saveCardText() {
    cardTextSave = cardTextSave.then(saveCardTextNow);
    return cardTextSave;
}

async function saveCardTextNow() {
    const task = cardTask();
    if (!task) return;
    const payload = {};

    const title = cardTitleInput.value.trim();
    if (title && title !== task.title) payload.title = title;
    if (!title) cardTitleInput.value = task.title; // vacío: se deshace

    const notes = cardNotesInput.value.trim();
    if (notes !== (task.notes || '')) payload.notes = notes || null;

    if (Object.keys(payload).length) await patchCardTask(payload);
}

cardTitleInput.addEventListener('input', fitTitleHeight);
cardTitleInput.addEventListener('keydown', (event) => {
    // El título es de una línea: Enter guarda en vez de saltar de renglón
    if (event.key === 'Enter') {
        event.preventDefault();
        cardTitleInput.blur();
    }
});
cardTitleInput.addEventListener('blur', saveCardText);
cardNotesInput.addEventListener('blur', saveCardText);

cardColumnSelect.addEventListener('change', () => {
    patchCardTask({ column_id: Number(cardColumnSelect.value) });
});

cardProjectSelect.addEventListener('change', () => {
    if (cardProjectSelect.value === NEW_PROJECT_OPTION) {
        // No es un proyecto: se vuelve al que tenía y se abre la fila de crear
        const task = cardTask();
        if (task) cardProjectSelect.value = String(task.project_id);
        openCardNewProject();
        return;
    }
    patchCardTask({ project_id: Number(cardProjectSelect.value) });
});

function openCardNewProject() {
    cardNewProjectError.classList.add('hidden');
    cardNewProjectName.value = '';
    cardNewProjectForm.classList.remove('hidden');
    cardNewProjectName.focus();
}

function closeCardNewProject() {
    cardNewProjectForm.classList.add('hidden');
}

cardNewProjectForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const name = cardNewProjectName.value.trim();
    if (!name || !cardTask()) return;
    try {
        const project = await apiFetch('/api/projects', {
            method: 'POST',
            json: { name, color: cardNewProjectColor.value },
        });
        boardState.projects.push(project);
        closeCardNewProject();
        await patchCardTask({ project_id: project.id });
    } catch (error) {
        // 409: el nombre ya existe (quizá archivado); el backend lo explica
        showError(cardNewProjectError, error.message || 'No se pudo crear el proyecto');
    }
});

document.getElementById('cardNewProjectCancel').addEventListener('click', closeCardNewProject);

cardTagRow.addEventListener('click', (event) => {
    if (!event.target.closest('button')) return;
    if (isTagPickerOpen()) closeTagPicker();
    else openTagPicker();
});

tagPickerList.addEventListener('click', (event) => {
    const row = event.target.closest('.tag-picker-row');
    const task = cardTask();
    if (!row || !task) return;
    const tagId = Number(row.dataset.tagId);
    const tagIds = task.tag_ids.includes(tagId)
        ? task.tag_ids.filter(id => id !== tagId)
        : [...task.tag_ids, tagId];
    patchCardTask({ tag_ids: tagIds });
});

tagPickerName.addEventListener('input', () => {
    const task = cardTask();
    if (task) renderTagPicker(task);
});

tagPickerForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const name = tagPickerName.value.trim();
    const task = cardTask();
    if (!name || !task) return;

    // Si ya existe (sin distinguir mayúsculas), se pone esa en vez de duplicarla
    let tag = boardState.tags.find(t => t.name.toLowerCase() === name.toLowerCase());
    if (!tag) {
        try {
            tag = await apiFetch('/api/tags', { method: 'POST', json: { name, color: tagPickerColor.value } });
            boardState.tags.push(tag);
            boardState.tags.sort((a, b) => a.name.localeCompare(b.name));
        } catch (error) {
            console.error('Error al crear la etiqueta:', error);
            return;
        }
    }
    tagPickerName.value = '';
    tagPickerColor.value = nextTagColor();
    if (!task.tag_ids.includes(tag.id)) {
        await patchCardTask({ tag_ids: [...task.tag_ids, tag.id] });
    } else {
        renderTagPicker(task);
    }
    tagPickerName.focus();
});

// Clic fuera del panel (y de su +) lo cierra. Con composedPath() y no con
// contains(): abrir el panel repinta la fila de chips, así que el + pulsado
// ya no está en el documento cuando el clic llega aquí, y contains() lo
// tomaría por un clic fuera.
cardModal.addEventListener('click', (event) => {
    if (!isTagPickerOpen()) return;
    const path = event.composedPath();
    if (path.includes(tagPicker) || path.includes(cardTagRow)) return;
    closeTagPicker();
});

cardChecklistForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const input = cardChecklistForm.querySelector('input');
    const text = input.value.trim();
    const taskId = cardState.taskId;
    if (!text || !taskId || cardState.checklist === null) return;
    input.value = '';
    try {
        const item = await apiFetch(`/api/tasks/${taskId}/checklist`, { method: 'POST', json: { text } });
        cardState.checklist.push(item);
        cardState.dirty = true;
    } catch (error) {
        console.error('Error al añadir al checklist:', error);
    }
    renderCardChecklist();
});

cardChecklistEl.addEventListener('change', async (event) => {
    const row = event.target.closest('.card-check-row');
    if (!row || event.target.type !== 'checkbox') return;
    const item = cardState.checklist.find(i => i.id === Number(row.dataset.itemId));
    if (!item) return;
    try {
        const updated = await apiFetch(`/api/tasks/${cardState.taskId}/checklist/${item.id}`, {
            method: 'PATCH',
            json: { is_done: event.target.checked },
        });
        Object.assign(item, updated);
        cardState.dirty = true;
    } catch (error) {
        console.error('Error al marcar el checklist:', error);
    }
    renderCardChecklist();
});

// ============================================
// Editar en el sitio: elementos del checklist y comentarios
// ============================================

function isEditing(kind, id) {
    return !!cardState.editing && cardState.editing.kind === kind && cardState.editing.id === id;
}

function startEditing(kind, id) {
    cardState.editing = { kind, id };
    if (kind === 'check') renderCardChecklist();
    else renderCardComments();
}

function stopEditing() {
    const kind = cardState.editing && cardState.editing.kind;
    cardState.editing = null;
    if (kind === 'check') renderCardChecklist();
    else if (kind === 'comment') renderCardComments();
}

async function saveChecklistText(itemId, value) {
    const item = (cardState.checklist || []).find(i => i.id === itemId);
    const text = value.trim();
    // Vacío o sin cambios: se deja como estaba (para quitarlo está la ×)
    if (!item || !text || text === item.text) {
        stopEditing();
        return;
    }
    try {
        // Solo el texto: si estaba marcado, sigue marcado
        const updated = await apiFetch(`/api/tasks/${cardState.taskId}/checklist/${itemId}`, {
            method: 'PATCH',
            json: { text },
        });
        Object.assign(item, updated);
        cardState.dirty = true;
    } catch (error) {
        console.error('Error al editar el checklist:', error);
    }
    stopEditing();
}

async function saveCommentBody(commentId, value) {
    const comment = (cardState.comments || []).find(c => c.id === commentId);
    const body = value.trim();
    if (!comment || !body || body === comment.body) {
        stopEditing();
        return;
    }
    try {
        const updated = await apiFetch(`/api/tasks/${cardState.taskId}/comments/${commentId}`, {
            method: 'PATCH',
            json: { body },
        });
        Object.assign(comment, updated);
        cardState.dirty = true;
    } catch (error) {
        console.error('Error al editar el comentario:', error);
    }
    stopEditing();
}

// Enter guarda y Escape cancela. stopPropagation: el Escape de document
// cerraría la tarjeta entera.
cardChecklistEl.addEventListener('keydown', (event) => {
    const input = event.target.closest('.card-inline-edit');
    if (!input) return;
    if (event.key === 'Enter') {
        event.preventDefault();
        input.dataset.done = '1';
        saveChecklistText(cardState.editing.id, input.value);
    } else if (event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
        input.dataset.done = '1';
        stopEditing();
    }
});

// Salir del campo también guarda (salvo que ya lo hayan hecho Enter o Escape)
cardChecklistEl.addEventListener('focusout', (event) => {
    const input = event.target.closest('.card-inline-edit');
    if (!input || input.dataset.done || !cardState.editing) return;
    saveChecklistText(cardState.editing.id, input.value);
});

cardCommentsEl.addEventListener('submit', (event) => {
    const form = event.target.closest('.card-comment-edit-form');
    if (!form) return;
    event.preventDefault();
    saveCommentBody(cardState.editing.id, form.querySelector('textarea').value);
});

cardCommentsEl.addEventListener('keydown', (event) => {
    const textarea = event.target.closest('.card-comment-edit-form textarea');
    if (!textarea) return;
    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
        event.preventDefault();
        saveCommentBody(cardState.editing.id, textarea.value);
    } else if (event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
        stopEditing();
    }
});

cardChecklistEl.addEventListener('click', async (event) => {
    const editBtn = event.target.closest('.card-check-edit');
    if (editBtn) {
        startEditing('check', Number(editBtn.closest('.card-check-row').dataset.itemId));
        return;
    }
    const remove = event.target.closest('.card-check-delete');
    if (!remove) return;
    const itemId = Number(remove.closest('.card-check-row').dataset.itemId);
    try {
        await apiFetch(`/api/tasks/${cardState.taskId}/checklist/${itemId}`, { method: 'DELETE' });
        cardState.checklist = cardState.checklist.filter(i => i.id !== itemId);
        cardState.dirty = true;
    } catch (error) {
        console.error('Error al quitar del checklist:', error);
    }
    renderCardChecklist();
});

cardCommentForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const textarea = cardCommentForm.querySelector('textarea');
    const body = textarea.value.trim();
    const taskId = cardState.taskId;
    if (!body || !taskId || cardState.comments === null) return;
    try {
        const comment = await apiFetch(`/api/tasks/${taskId}/comments`, { method: 'POST', json: { body } });
        cardState.comments.push(comment);
        cardState.dirty = true;
        textarea.value = '';
    } catch (error) {
        console.error('Error al comentar:', error);
    }
    renderCardComments();
});

cardCommentsEl.addEventListener('click', async (event) => {
    if (event.target.closest('.card-comment-edit')) {
        startEditing('comment', Number(event.target.closest('.card-comment').dataset.commentId));
        return;
    }
    if (event.target.closest('.card-comment-cancel')) {
        stopEditing();
        return;
    }
    const remove = event.target.closest('.card-comment-delete');
    if (!remove) return;
    const commentId = Number(remove.closest('.card-comment').dataset.commentId);
    const ok = await confirmDialog('El comentario se borrará y no se puede recuperar.', {
        title: '¿Eliminar comentario?', confirmLabel: 'Eliminar', danger: true,
    });
    if (!ok) return;
    try {
        await apiFetch(`/api/tasks/${cardState.taskId}/comments/${commentId}`, { method: 'DELETE' });
        cardState.comments = cardState.comments.filter(c => c.id !== commentId);
        cardState.dirty = true;
    } catch (error) {
        console.error('Error al borrar el comentario:', error);
    }
    renderCardComments();
});

// Cada botón hace lo suyo al instante y el detalle sigue abierto: arrancar o
// detener, para seguir escribiendo mientras corre (syncTimerMarks cambia los
// botones por "■ Detener" con el reloj), y el registro a mano, que se abre
// encima con su propio z-index.
cardTimerEl.addEventListener('click', async (event) => {
    const button = event.target.closest('[data-timer]');
    const task = cardTask();
    if (!button || !task) return;
    const action = button.dataset.timer;

    if (action === 'stop') {
        await stopTimer();
    } else if (action === 'manual') {
        openLogTimeModal(task.project_id, null, { id: task.id, title: task.title });
    } else {
        await startTimerForTask(task.project_id, task.id, action, task.title);
    }
});

document.getElementById('cardDeleteBtn').addEventListener('click', async () => {
    const task = cardTask();
    if (!task) return;
    const ok = await confirmDialog(
        `"${task.title}" se borrará con su checklist y sus comentarios. Su tiempo registrado se conserva en el proyecto.`,
        { title: '¿Eliminar tarjeta?', confirmLabel: 'Eliminar', danger: true }
    );
    if (!ok) return;
    try {
        await apiFetch(`/api/tasks/${task.id}`, { method: 'DELETE' });
    } catch (error) {
        console.error('Error al eliminar la tarjeta:', error);
    }
    hideModal(cardModal);
    cardState.taskId = null;
    await refreshAfterBoardChange();
});

document.getElementById('closeCardModalBtn').addEventListener('click', closeCardModal);
cardModal.querySelector('.modal-overlay').addEventListener('click', closeCardModal);
document.addEventListener('keydown', (event) => {
    // Con el confirm abierto encima, Escape es de él
    if (event.key !== 'Escape') return;
    if (!document.getElementById('confirmModal').classList.contains('hidden')) return;
    // El ajuste del cronómetro (pomodoro.js) maneja su propio Escape
    if (!document.getElementById('adjustStartModal').classList.contains('hidden')) return;
    // Con el registro de tiempo abierto sobre la tarjeta (o sobre el tiempo
    // del día), Escape cierra ese. preventDefault: el listener del tiempo del
    // día (pomodoro.js) corre después y no debe cerrar también el suyo.
    if (!document.getElementById('logTimeModal').classList.contains('hidden')) {
        hideModal(document.getElementById('logTimeModal'));
        event.preventDefault();
        return;
    }
    if (!cardModal.classList.contains('hidden') && isTagPickerOpen()) closeTagPicker();
    else if (!cardModal.classList.contains('hidden')) closeCardModal();
    else if (!boardConfigModal.classList.contains('hidden') && isConfigPomoPage()) showConfigPage('main');
    else if (!boardConfigModal.classList.contains('hidden')) closeBoardConfig();
    else if (!boardOnboardingModal.classList.contains('hidden')) skipFirstBoard();
});

// ============================================
// Organizar: tableros y columnas
// ============================================

// De una columna solo se enseña lo que cambia algo: la primera "todo" es por
// donde entran las tareas nuevas, y las "done" marcan la tarea como hecha.
// "doing" no hace nada especial, así que no lleva marca.
function columnBadge(column, columns) {
    const entry = columns.find(c => c.category === 'todo');
    if (entry && entry.id === column.id) {
        return { text: '📥 Entrada', title: 'Aquí llegan las tareas nuevas, y aquí vuelve una tarea al quitarle la palomita' };
    }
    if (column.category === 'done') {
        return { text: '✓ Terminada', title: 'Una tarea que muevas aquí cuenta como hecha' };
    }
    return { text: '', title: '' };
}

const boardConfigModal = document.getElementById('boardConfigModal');
const boardConfigError = document.getElementById('boardConfigError');
const configBoardsEl = document.getElementById('configBoards');
const configArchivedBoardsEl = document.getElementById('configArchivedBoards');
const configBoardForm = document.getElementById('configBoardForm');
const configNewBoardInput = document.getElementById('configNewBoard');
const configColumnsBoard = document.getElementById('configColumnsBoard');
const configColumnsEl = document.getElementById('configColumns');
const configColumnForm = document.getElementById('configColumnForm');
const configTagsEl = document.getElementById('configTags');
const configProjectsEl = document.getElementById('configProjects');
const configArchivedProjectsEl = document.getElementById('configArchivedProjects');
const configProjectForm = document.getElementById('configProjectForm');
const configTagForm = document.getElementById('configTagForm');

const configState = {
    boards: [],          // todos, archivados incluidos
    columnsBoardId: null,
    tags: [],
    projects: [],        // activos, sin "Sin asignar" (no se renombra ni se archiva)
    archivedProjects: [],
    dirty: false,
};

function configBoard() {
    return configState.boards.find(b => b.id === configState.columnsBoardId) || null;
}

async function reloadConfig() {
    const [data, tagsData, projectsData] = await Promise.all([
        apiFetch('/api/boards?include_inactive=true'),
        apiFetch('/api/tags'),
        apiFetch('/api/projects?include_inactive=true'),
    ]);
    configState.boards = data.boards;
    configState.tags = tagsData.tags;
    const userProjects = projectsData.projects
        .filter(p => !p.is_system)
        .sort((a, b) => a.name.localeCompare(b.name));
    configState.projects = userProjects.filter(p => p.is_active);
    configState.archivedProjects = userProjects.filter(p => !p.is_active);
    const active = data.boards.filter(b => b.is_active);
    if (!active.some(b => b.id === configState.columnsBoardId)) {
        configState.columnsBoardId = active.some(b => b.id === boardState.boardId)
            ? boardState.boardId
            : (active[0] ? active[0].id : null);
    }
    renderConfig();
}

function configButton(className, label, text) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = className;
    button.setAttribute('aria-label', label);
    button.title = label;
    button.textContent = text;
    return button;
}

function buildConfigRow({ id, color, name, maxLength, typeLabel, typeTitle, first, last, reorder, deleteClass, deleteText = '×', deleteLabel = null }) {
    const row = document.createElement('div');
    row.className = 'config-row';
    row.dataset.itemId = String(id);

    // El asa hace arrastrable la fila solo mientras se sujeta: si toda la fila
    // lo fuera, no se podría seleccionar texto dentro del nombre.
    if (reorder) {
        const handle = document.createElement('span');
        handle.className = 'config-drag';
        handle.title = 'Arrastra para ordenar';
        handle.setAttribute('aria-hidden', 'true');
        handle.textContent = '⠿';
        row.appendChild(handle);
    }

    const colorInput = document.createElement('input');
    colorInput.type = 'color';
    colorInput.className = 'config-color';
    colorInput.value = color || '#95a5a6';
    colorInput.setAttribute('aria-label', `Color de ${name}`);

    const nameInput = document.createElement('input');
    nameInput.type = 'text';
    nameInput.className = 'config-name';
    nameInput.maxLength = maxLength;
    nameInput.value = name;
    nameInput.setAttribute('aria-label', `Nombre de ${name}`);

    row.appendChild(colorInput);
    row.appendChild(nameInput);

    // Vacío también ocupa su sitio, para que las filas queden alineadas
    if (typeLabel !== undefined) {
        const type = document.createElement('span');
        type.className = 'config-type';
        type.textContent = typeLabel;
        if (typeTitle) type.title = typeTitle;
        row.appendChild(type);
    }
    if (reorder) {
        const up = configButton('config-action config-move', `Subir ${name}`, '↑');
        up.dataset.delta = '-1';
        up.disabled = first;
        const down = configButton('config-action config-move', `Bajar ${name}`, '↓');
        down.dataset.delta = '1';
        down.disabled = last;
        row.appendChild(up);
        row.appendChild(down);
    }
    row.appendChild(configButton(`config-action danger ${deleteClass}`, deleteLabel || `Eliminar ${name}`, deleteText));
    return row;
}

// Reescribe "order" de los elementos que cambiaron de sitio al mover uno
function orderRequests(list, urlFor) {
    return () => Promise.all(list
        .map((item, index) => ({ item, index }))
        .filter(({ item, index }) => item.order !== index)
        .map(({ item, index }) => apiFetch(urlFor(item), { method: 'PATCH', json: { order: index } })));
}

function reorderRequests(items, itemId, delta, urlFor) {
    const list = [...items];
    const from = list.findIndex(item => item.id === itemId);
    const to = from + delta;
    if (from < 0 || to < 0 || to >= list.length) return null;
    [list[from], list[to]] = [list[to], list[from]];
    return orderRequests(list, urlFor);
}

function renderConfig() {
    const active = configState.boards.filter(b => b.is_active);
    const archived = configState.boards.filter(b => !b.is_active);

    configBoardsEl.innerHTML = '';
    active.forEach(board => {
        const row = document.createElement('div');
        row.className = 'config-row';
        row.dataset.boardId = String(board.id);

        const name = document.createElement('input');
        name.type = 'text';
        name.className = 'config-name';
        name.maxLength = 60;
        name.value = board.name;
        name.setAttribute('aria-label', `Nombre del tablero ${board.name}`);
        row.appendChild(name);

        // El último activo no se archiva ni se borra (el backend lo impide)
        if (active.length > 1) {
            row.appendChild(configButton('config-action config-archive-board', `Archivar ${board.name}`, 'Archivar'));
            row.appendChild(configButton('config-action danger config-delete-board', `Eliminar ${board.name}`, '×'));
        }
        configBoardsEl.appendChild(row);
    });

    configArchivedBoardsEl.innerHTML = '';
    if (archived.length) {
        const title = document.createElement('p');
        title.className = 'config-hint';
        title.textContent = 'Archivados:';
        configArchivedBoardsEl.appendChild(title);
        archived.forEach(board => {
            const row = document.createElement('div');
            row.className = 'config-row archived';
            row.dataset.boardId = String(board.id);
            const name = document.createElement('span');
            name.className = 'config-name';
            name.textContent = board.name;
            row.appendChild(name);
            row.appendChild(configButton('config-action config-restore-board', `Restaurar ${board.name}`, 'Restaurar'));
            row.appendChild(configButton('config-action danger config-delete-board', `Eliminar ${board.name}`, '×'));
            configArchivedBoardsEl.appendChild(row);
        });
    }

    configColumnsBoard.innerHTML = '';
    active.forEach(board => {
        const option = document.createElement('option');
        option.value = String(board.id);
        option.textContent = board.name;
        configColumnsBoard.appendChild(option);
    });
    if (configState.columnsBoardId !== null) configColumnsBoard.value = String(configState.columnsBoardId);

    renderConfigProjects();
    renderConfigTags();

    configColumnsEl.innerHTML = '';
    const board = configBoard();
    if (!board) return;
    board.columns.forEach((column, index) => {
        configColumnsEl.appendChild(buildConfigRow({
            id: column.id, color: column.color, name: column.name, maxLength: 40,
            typeLabel: columnBadge(column, board.columns).text,
            typeTitle: columnBadge(column, board.columns).title,
            first: index === 0, last: index === board.columns.length - 1,
            reorder: true, deleteClass: 'config-delete-column',
        }));
    });
}

function renderConfigProjects() {
    configProjectsEl.innerHTML = '';
    if (configState.projects.length === 0) {
        const hint = document.createElement('p');
        hint.className = 'config-hint';
        hint.textContent = 'Todavía no hay proyectos.';
        configProjectsEl.appendChild(hint);
    }
    configState.projects.forEach(project => {
        configProjectsEl.appendChild(buildConfigRow({
            id: project.id, color: project.color, name: project.name, maxLength: 80,
            reorder: false, deleteClass: 'config-archive-project',
            deleteText: 'Archivar', deleteLabel: `Archivar ${project.name}`,
        }));
    });

    // Los archivados, con Restaurar: antes no se veían en ningún sitio, y la
    // única forma de recuperarlos era crear otro con el mismo nombre.
    configArchivedProjectsEl.innerHTML = '';
    if (configState.archivedProjects.length === 0) return;
    const title = document.createElement('p');
    title.className = 'config-hint';
    title.textContent = 'Archivados:';
    configArchivedProjectsEl.appendChild(title);
    configState.archivedProjects.forEach(project => {
        const row = document.createElement('div');
        row.className = 'config-row archived';
        row.dataset.itemId = String(project.id);
        const name = document.createElement('span');
        name.className = 'config-name';
        name.textContent = project.name;
        row.appendChild(name);
        row.appendChild(configButton('config-action config-restore-project', `Restaurar ${project.name}`, 'Restaurar'));
        configArchivedProjectsEl.appendChild(row);
    });
}

function renderConfigTags() {
    configTagsEl.innerHTML = '';
    if (configState.tags.length === 0) {
        const hint = document.createElement('p');
        hint.className = 'config-hint';
        hint.textContent = 'Todavía no hay etiquetas.';
        configTagsEl.appendChild(hint);
    }
    configState.tags.forEach(tag => {
        configTagsEl.appendChild(buildConfigRow({
            id: tag.id, color: tag.color, name: tag.name, maxLength: 30,
            reorder: false, deleteClass: 'config-delete-tag',
        }));
    });
}

// Toda acción pasa por aquí: el error del backend (409 de "tiene tareas",
// nombre repetido...) ya viene en español y se enseña tal cual.
async function configAction(action) {
    boardConfigError.classList.add('hidden');
    try {
        await action();
        configState.dirty = true;
    } catch (error) {
        showError(boardConfigError, error.message || 'No se pudo guardar el cambio');
    }
    try {
        await reloadConfig();
    } catch (error) {
        console.error('Error al recargar Organizar:', error);
    }
}

// ============================================
// Organizar › Pomodoro (segunda página, deslizando)
// ============================================
//
// Las duraciones del pomodoro son de la cuenta (users.pomodoro_*_seconds) pero
// solo las usa el tiempo de las tarjetas, así que se configuran desde aquí.

const configTrack = document.getElementById('configTrack');
const configMainPage = document.getElementById('configMainPage');
const configPomoPage = document.getElementById('configPomoPage');
const configPomoForm = document.getElementById('configPomoForm');
const configPomoError = document.getElementById('configPomoError');
const configPomoStatus = document.getElementById('configPomoStatus');
const CONFIG_POMO_FIELDS = [
    { id: 'configPomoFocus', field: 'pomodoro_focus_seconds' },
    { id: 'configPomoShort', field: 'pomodoro_short_break_seconds' },
    { id: 'configPomoLong', field: 'pomodoro_long_break_seconds' },
];
let configPageTimer = null;

function isConfigPomoPage() {
    return configTrack.classList.contains('show-pomo');
}

// La página que no se ve se pliega al terminar el deslizamiento: si no, el
// modal tomaría la altura de la más alta
function showConfigPage(page, { animate = true } = {}) {
    const toPomo = page === 'pomo';
    clearTimeout(configPageTimer);
    configMainPage.classList.remove('collapsed');
    configPomoPage.classList.remove('collapsed');
    configTrack.classList.toggle('no-anim', !animate);
    configTrack.classList.toggle('show-pomo', toPomo);
    boardConfigModal.querySelector('.modal-content').scrollTop = 0;
    const finish = () => {
        (toPomo ? configMainPage : configPomoPage).classList.add('collapsed');
        if (toPomo) document.getElementById('configPomoFocus').focus();
    };
    if (animate) configPageTimer = setTimeout(finish, 320);
    else finish();
}

function openConfigPomo() {
    CONFIG_POMO_FIELDS.forEach(({ id, field }) => {
        const seconds = currentUser ? currentUser[field] : null;
        document.getElementById(id).value = seconds ? String(Math.round(seconds / 60)) : '';
    });
    configPomoError.classList.add('hidden');
    showConfigPage('pomo');
}

configPomoForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const payload = {};
    for (const { id, field } of CONFIG_POMO_FIELDS) {
        const raw = document.getElementById(id).value.trim();
        const minutes = Number(raw);
        if (raw && (!Number.isInteger(minutes) || minutes < 1 || minutes > 240)) {
            showError(configPomoError, 'Las duraciones van de 1 a 240 minutos.');
            return;
        }
        payload[field] = raw ? minutes * 60 : null;
    }
    try {
        // currentUser es de script.js: pomoDuration() lo lee al arrancar un timer
        currentUser = await apiFetch('/api/auth/me', { method: 'PATCH', json: payload });
    } catch (error) {
        showError(configPomoError, error.message || 'No se pudo guardar');
        return;
    }
    showConfigPage('main');
    configPomoStatus.textContent = 'Guardado ✓';
    setTimeout(() => { configPomoStatus.textContent = ''; }, 2500);
});

document.getElementById('configPomoOpen').addEventListener('click', openConfigPomo);
document.getElementById('configPomoBack').addEventListener('click', () => showConfigPage('main'));
document.getElementById('configPomoCancel').addEventListener('click', () => showConfigPage('main'));

async function openBoardConfig({ focusNewBoard = false } = {}) {
    showConfigPage('main', { animate: false });
    configState.dirty = false;
    configState.columnsBoardId = boardState.boardId;
    boardConfigError.classList.add('hidden');
    showModal(boardConfigModal);
    try {
        await reloadConfig();
    } catch (error) {
        showError(boardConfigError, error.message || 'No se pudo cargar');
    }
    if (focusNewBoard) configNewBoardInput.focus();
}

async function closeBoardConfig() {
    hideModal(boardConfigModal);
    if (!configState.dirty) return;
    // El tablero que se veía pudo archivarse o borrarse
    const stillActive = configState.boards.some(b => b.is_active && b.id === boardState.boardId);
    if (!stillActive) {
        boardState.boardId = null;
        boardState.mobileColumnId = null;
    }
    await refreshAfterBoardChange();
}

document.getElementById('boardConfigBtn').addEventListener('click', () => openBoardConfig());
document.getElementById('closeBoardConfigBtn').addEventListener('click', closeBoardConfig);
boardConfigModal.querySelector('.modal-overlay').addEventListener('click', closeBoardConfig);

configBoardForm.addEventListener('submit', (event) => {
    event.preventDefault();
    const name = configNewBoardInput.value.trim();
    if (!name) return;
    configAction(async () => {
        const board = await apiFetch('/api/boards', { method: 'POST', json: { name } });
        configNewBoardInput.value = '';
        // El tablero nuevo pasa a ser el que se ve y el que se configura
        boardState.boardId = board.id;
        boardState.mobileColumnId = null;
        boardState.filterProjects.clear();
        boardState.filterTags.clear();
        writeStored(SELECTED_BOARD_KEY, String(board.id));
        configState.columnsBoardId = board.id;
    });
});

// "change" de un input de texto salta al salir del campo tras editarlo
configBoardsEl.addEventListener('change', (event) => {
    const input = event.target.closest('.config-name');
    if (!input) return;
    const boardId = Number(input.closest('.config-row').dataset.boardId);
    const name = input.value.trim();
    if (!name) {
        renderConfig();
        return;
    }
    configAction(() => apiFetch(`/api/boards/${boardId}`, { method: 'PATCH', json: { name } }));
});

async function handleBoardRowClick(event) {
    const row = event.target.closest('.config-row');
    if (!row) return;
    const boardId = Number(row.dataset.boardId);
    const board = configState.boards.find(b => b.id === boardId);

    if (event.target.closest('.config-archive-board')) {
        configAction(() => apiFetch(`/api/boards/${boardId}`, { method: 'PATCH', json: { is_active: false } }));
    } else if (event.target.closest('.config-restore-board')) {
        configAction(() => apiFetch(`/api/boards/${boardId}`, { method: 'PATCH', json: { is_active: true } }));
    } else if (event.target.closest('.config-delete-board')) {
        const ok = await confirmDialog(
            `Solo se puede borrar un tablero vacío. Si "${board.name}" tiene tareas, muévelas antes o archívalo.`,
            { title: '¿Eliminar tablero?', confirmLabel: 'Eliminar', danger: true }
        );
        if (ok) configAction(() => apiFetch(`/api/boards/${boardId}`, { method: 'DELETE' }));
    }
}

configBoardsEl.addEventListener('click', handleBoardRowClick);
configArchivedBoardsEl.addEventListener('click', handleBoardRowClick);

configColumnsBoard.addEventListener('change', () => {
    configState.columnsBoardId = Number(configColumnsBoard.value);
    renderConfig();
});

configColumnsEl.addEventListener('change', (event) => {
    const row = event.target.closest('.config-row');
    if (!row) return;
    const boardId = configState.columnsBoardId;
    const columnId = Number(row.dataset.itemId);

    if (event.target.classList.contains('config-color')) {
        configAction(() => apiFetch(`/api/boards/${boardId}/columns/${columnId}`, {
            method: 'PATCH', json: { color: event.target.value },
        }));
    } else if (event.target.classList.contains('config-name')) {
        const name = event.target.value.trim();
        if (!name) {
            renderConfig();
            return;
        }
        configAction(() => apiFetch(`/api/boards/${boardId}/columns/${columnId}`, {
            method: 'PATCH', json: { name },
        }));
    }
});

configColumnsEl.addEventListener('click', (event) => {
    const row = event.target.closest('.config-row');
    const board = configBoard();
    if (!row || !board) return;
    const columnId = Number(row.dataset.itemId);

    const move = event.target.closest('.config-move');
    if (move) {
        const requests = reorderRequests(board.columns, columnId, Number(move.dataset.delta),
            column => `/api/boards/${board.id}/columns/${column.id}`);
        if (requests) configAction(requests);
        return;
    }

    if (event.target.closest('.config-delete-column')) {
        // Sin confirmación: el backend no borra una columna con tareas ni la
        // última de su tipo, así que lo peor es quitar una columna vacía.
        configAction(() => apiFetch(`/api/boards/${board.id}/columns/${columnId}`, { method: 'DELETE' }));
    }
});

// Arrastrar columnas por el asa ⠿ (las flechas siguen para teclado y táctil)
let draggedConfigColumnId = null;
const configDropIndicator = document.createElement('div');
configDropIndicator.className = 'drop-indicator';

configColumnsEl.addEventListener('pointerdown', (event) => {
    const handle = event.target.closest('.config-drag');
    if (handle) handle.closest('.config-row').draggable = true;
});

configColumnsEl.addEventListener('dragstart', (event) => {
    const row = event.target.closest('.config-row');
    if (!row || !row.draggable) return;
    draggedConfigColumnId = Number(row.dataset.itemId);
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', row.dataset.itemId);
    row.classList.add('dragging');
});

function configRowBeforePointer(clientY) {
    const rows = [...configColumnsEl.querySelectorAll('.config-row:not(.dragging)')];
    return rows.find(row => {
        const box = row.getBoundingClientRect();
        return clientY < box.top + box.height / 2;
    }) || null;
}

configColumnsEl.addEventListener('dragover', (event) => {
    if (draggedConfigColumnId === null) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
    const before = configRowBeforePointer(event.clientY);
    if (before) configColumnsEl.insertBefore(configDropIndicator, before);
    else configColumnsEl.appendChild(configDropIndicator);
});

configColumnsEl.addEventListener('drop', (event) => {
    const board = configBoard();
    if (draggedConfigColumnId === null || !board) return;
    event.preventDefault();
    const before = configRowBeforePointer(event.clientY);
    const moved = board.columns.find(c => c.id === draggedConfigColumnId);
    const others = board.columns.filter(c => c.id !== draggedConfigColumnId);
    let index = before ? others.findIndex(c => c.id === Number(before.dataset.itemId)) : others.length;
    if (index < 0) index = others.length;
    const list = [...others.slice(0, index), moved, ...others.slice(index)];
    endConfigColumnDrag();
    if (list.some((column, i) => column.order !== i)) {
        configAction(orderRequests(list, column => `/api/boards/${board.id}/columns/${column.id}`));
    }
});

function endConfigColumnDrag() {
    draggedConfigColumnId = null;
    configDropIndicator.remove();
    configColumnsEl.querySelectorAll('.config-row').forEach(row => {
        row.draggable = false;
        row.classList.remove('dragging');
    });
}

configColumnsEl.addEventListener('dragend', endConfigColumnDrag);
// Soltar el asa sin arrastrar no debe dejar la fila arrastrable
document.addEventListener('pointerup', () => {
    if (draggedConfigColumnId === null) {
        configColumnsEl.querySelectorAll('.config-row[draggable="true"]').forEach(row => { row.draggable = false; });
    }
});

configColumnForm.addEventListener('submit', (event) => {
    event.preventDefault();
    const input = configColumnForm.querySelector('input[type="text"]');
    const doneBox = document.getElementById('configColumnDone');
    // "doing" es el tipo neutro; "todo" solo lo tiene la columna de entrada
    const category = doneBox.checked ? 'done' : 'doing';
    const name = input.value.trim();
    const boardId = configState.columnsBoardId;
    if (!name || boardId === null) return;
    configAction(async () => {
        await apiFetch(`/api/boards/${boardId}/columns`, { method: 'POST', json: { name, category } });
        input.value = '';
        doneBox.checked = false;
    });
});

// Etiquetas y proyectos: nombre y color al salir del campo
function handleConfigItemChange(event, urlFor) {
    const row = event.target.closest('.config-row');
    if (!row) return;
    const url = urlFor(Number(row.dataset.itemId));
    if (event.target.classList.contains('config-color')) {
        configAction(() => apiFetch(url, { method: 'PATCH', json: { color: event.target.value } }));
    } else if (event.target.classList.contains('config-name')) {
        const name = event.target.value.trim();
        if (!name) {
            renderConfig();
            return;
        }
        configAction(() => apiFetch(url, { method: 'PATCH', json: { name } }));
    }
}

configTagsEl.addEventListener('change', (event) => handleConfigItemChange(event, id => `/api/tags/${id}`));
configProjectsEl.addEventListener('change', (event) => handleConfigItemChange(event, id => `/api/projects/${id}`));

// Archivar no pide confirmación: conserva tareas y tiempo, y crear otra vez
// un proyecto con ese nombre lo reactiva.
configProjectsEl.addEventListener('click', (event) => {
    if (!event.target.closest('.config-archive-project')) return;
    const projectId = Number(event.target.closest('.config-row').dataset.itemId);
    boardState.filterProjects.delete(projectId);
    configAction(() => apiFetch(`/api/projects/${projectId}`, { method: 'PATCH', json: { is_active: false } }));
});

configArchivedProjectsEl.addEventListener('click', (event) => {
    if (!event.target.closest('.config-restore-project')) return;
    const projectId = Number(event.target.closest('.config-row').dataset.itemId);
    configAction(() => apiFetch(`/api/projects/${projectId}`, { method: 'PATCH', json: { is_active: true } }));
});

configProjectForm.addEventListener('submit', (event) => {
    event.preventDefault();
    const input = configProjectForm.querySelector('input[type="text"]');
    const color = document.getElementById('configProjectColor');
    const name = input.value.trim();
    if (!name) return;
    configAction(async () => {
        await apiFetch('/api/projects', { method: 'POST', json: { name, color: color.value } });
        input.value = '';
    });
});

configTagsEl.addEventListener('click', async (event) => {
    if (!event.target.closest('.config-delete-tag')) return;
    const tagId = Number(event.target.closest('.config-row').dataset.itemId);
    const tag = configState.tags.find(t => t.id === tagId);
    const ok = await confirmDialog(
        `"${tag.name}" se quitará de todas sus tareas. Las tareas y su tiempo no cambian.`,
        { title: '¿Eliminar etiqueta?', confirmLabel: 'Eliminar', danger: true }
    );
    if (!ok) return;
    boardState.filterTags.delete(tagId);
    configAction(() => apiFetch(`/api/tags/${tagId}`, { method: 'DELETE' }));
});

configTagForm.addEventListener('submit', (event) => {
    event.preventDefault();
    const input = configTagForm.querySelector('input');
    const name = input.value.trim();
    if (!name) return;
    configAction(async () => {
        await apiFetch('/api/tags', { method: 'POST', json: { name } });
        input.value = '';
    });
});

// ============================================
// Primer tablero
// ============================================
//
// Un usuario sin tableros (el backend solo crea "Mi tablero" si ya tenía
// tareas) recibe esta oferta cada vez que entra a Tableros. Omitir lo
// devuelve al Calendario: la pestaña no tiene nada que enseñar sin tablero.

const boardOnboardingModal = document.getElementById('boardOnboardingModal');
const boardOnboardingForm = document.getElementById('boardOnboardingForm');
const boardOnboardingName = document.getElementById('boardOnboardingName');
const boardOnboardingError = document.getElementById('boardOnboardingError');

function maybeOfferFirstBoard() {
    if (!boardState.loaded || boardState.boards.length > 0) return;
    if (currentViewIndex !== 1 || !boardOnboardingModal.classList.contains('hidden')) return;
    boardOnboardingError.classList.add('hidden');
    showModal(boardOnboardingModal);
    boardOnboardingName.focus();
}

function skipFirstBoard() {
    hideModal(boardOnboardingModal);
    goToView(0);
}

boardOnboardingForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const name = boardOnboardingName.value.trim() || boardOnboardingName.placeholder;
    try {
        const board = await apiFetch('/api/boards', { method: 'POST', json: { name } });
        boardState.boardId = board.id;
        writeStored(SELECTED_BOARD_KEY, String(board.id));
        hideModal(boardOnboardingModal);
        await refreshAfterBoardChange();
    } catch (error) {
        showError(boardOnboardingError, error.message || 'No se pudo crear el tablero');
    }
});

document.getElementById('boardOnboardingSkip').addEventListener('click', skipFirstBoard);
boardOnboardingModal.querySelector('.modal-overlay').addEventListener('click', skipFirstBoard);

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
    boardState.loaded = false;
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
window.viewChangedHooks.push(maybeOfferFirstBoard);
