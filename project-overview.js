// ============================================
// Ficha de proyecto: todo su tiempo, de un vistazo
// ============================================
//
// Solo lectura (épica 24, Fase 1). Sale entera de GET /api/projects/{id}/overview,
// con el mismo criterio que la Lista y Reportes (solo sesiones de enfoque), así
// que su total cuadra con ellas. Se abre al tocar un proyecto en la Lista, o
// con 📊 en Organizar, encima de ese modal. Usa las barras y las cifras de
// Reportes (barList, summaryStat, reportCard, el): carga después de reports.js.

const projectOverviewModal = document.getElementById('projectOverviewModal');
const overviewTitle = document.getElementById('overviewTitle');
const overviewMeta = document.getElementById('overviewMeta');
const overviewBody = document.getElementById('overviewBody');
const overviewEditBtn = document.getElementById('overviewEditBtn');

let overviewProject = null;
let overviewRequestId = 0;

async function openProjectOverview(projectId) {
    const requestId = ++overviewRequestId;
    overviewProject = null;
    overviewTitle.textContent = 'Cargando…';
    overviewMeta.textContent = '';
    overviewEditBtn.hidden = true;
    overviewBody.replaceChildren();
    showModal(projectOverviewModal);
    try {
        const data = await apiFetch(`/api/projects/${projectId}/overview`);
        if (requestId !== overviewRequestId) return;   // ya se abrió otra
        renderProjectOverview(data);
    } catch (error) {
        if (requestId !== overviewRequestId) return;
        overviewTitle.textContent = 'Ficha del proyecto';
        overviewBody.replaceChildren(reportsMessage(error.message || 'No se pudo cargar la ficha.'));
    }
}

function closeProjectOverview() {
    overviewRequestId++;
    overviewProject = null;
    hideModal(projectOverviewModal);
}

function overviewMonthName(month) {
    const [year, number] = month.split('-').map(Number);
    return `${MONTH_SHORT[number - 1]} ${year}`;
}

function renderProjectOverview(data) {
    const { project } = data;
    overviewProject = project;
    overviewTitle.textContent = `${project.icon ? `${project.icon} ` : ''}${project.name}`;
    const notes = [];
    if (!project.is_active) notes.push('Archivado');
    if (data.first_date) {
        notes.push(data.first_date === data.last_date
            ? `Tiempo del ${formatShortDate(data.first_date)}`
            : `Tiempo del ${formatShortDate(data.first_date)} al ${formatShortDate(data.last_date)}`);
    }
    overviewMeta.textContent = notes.join(' · ');
    // "Sin asignar" no se edita; un archivado se edita desde Organizar
    overviewEditBtn.hidden = project.is_system || !project.is_active;

    const stats = el('div', 'report-stats');
    stats.append(
        summaryStat(formatDuration(data.total_seconds), 'tiempo total'),
        summaryStat(`${data.task_done} de ${data.task_total}`, 'tareas hechas'),
        summaryStat(String(data.session_count), data.session_count === 1 ? 'registro de tiempo' : 'registros de tiempo'),
        summaryStat(String(data.months.length), data.months.length === 1 ? 'mes con tiempo' : 'meses con tiempo'),
    );
    const cards = [reportCard('Resumen', stats)];

    if (data.total_seconds === 0) {
        cards.push(reportsMessage(data.task_total
            ? 'Todavía no hay tiempo registrado en sus tareas.'
            : 'Todavía no tiene tareas ni tiempo registrado.'));
    } else {
        cards.push(renderOverviewTasks(data), renderOverviewTags(data), renderOverviewMonths(data));
    }
    overviewBody.replaceChildren(...cards.filter(Boolean));
}

function renderOverviewTasks(data) {
    const rows = data.tasks
        .filter(task => task.seconds > 0)
        .map(task => ({
            name: task.title,
            color: overviewColor(data),
            seconds: task.seconds,
            note: task.is_done ? '✓ hecha' : '',
        }));
    if (data.seconds_no_task > 0) {
        rows.push({ name: 'Sin tarea', seconds: data.seconds_no_task, muted: true });
    }
    const withoutTime = data.tasks.filter(task => task.seconds === 0).length;
    const note = withoutTime
        ? el('p', 'report-compare-small', `${withoutTime} ${withoutTime === 1 ? 'tarea' : 'tareas'} sin tiempo todavía`)
        : null;
    return reportCard('Por tarea', barList(rows, data.total_seconds), note);
}

function renderOverviewTags(data) {
    if (data.tags.length === 0) return null;
    const rows = data.tags.map(tag => ({ name: tag.name, color: tag.color, seconds: tag.seconds }));
    if (data.untagged_seconds > 0) {
        rows.push({ name: 'Sin etiqueta', seconds: data.untagged_seconds, muted: true });
    }
    // Una sesión cuenta en cada etiqueta de su tarea: sin porcentaje, que
    // sumaría más de 100 %
    const note = data.tags.length > 1
        ? el('p', 'report-compare-small', 'Una tarea con varias etiquetas cuenta su tiempo en cada una.')
        : null;
    return reportCard('Por etiqueta', barList(rows), note);
}

function renderOverviewMonths(data) {
    if (data.months.length < 2) return null;
    const rows = data.months.map(m => ({ name: overviewMonthName(m.month), color: overviewColor(data), seconds: m.seconds }));
    return reportCard('Por mes', barList(rows, data.total_seconds));
}

function overviewColor(data) {
    return data.project.color || null;
}

document.getElementById('closeOverviewBtn').addEventListener('click', closeProjectOverview);
projectOverviewModal.querySelector('.modal-overlay').addEventListener('click', closeProjectOverview);

overviewEditBtn.addEventListener('click', () => {
    const project = overviewProject;
    if (!project) return;
    closeProjectOverview();
    openEditProjectModal(project);
});

// En captura: con la ficha encima de Organizar, Escape cierra solo la ficha
// (el listener de board.js cerraría también el de abajo).
document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape' || projectOverviewModal.classList.contains('hidden')) return;
    event.stopPropagation();
    closeProjectOverview();
}, true);

window.appLogoutHooks.push(closeProjectOverview);
