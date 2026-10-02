// ============================================
// Ficha de proyecto: todo su tiempo, de un vistazo
// ============================================
//
// Solo lectura (épica 24, Fase 1). Sale entera de GET /api/projects/{id}/overview,
// con el mismo criterio que la Lista y Reportes (solo sesiones de enfoque), así
// que su total cuadra con ellas. Se abre al tocar un proyecto en la Lista, o
// con 📊 encima de Organizar o del detalle de una tarjeta. Usa las barras y las cifras de
// Reportes (barList, summaryStat, reportCard, el): carga después de reports.js.

const projectOverviewModal = document.getElementById('projectOverviewModal');
const overviewTitle = document.getElementById('overviewTitle');
const overviewMeta = document.getElementById('overviewMeta');
const overviewBody = document.getElementById('overviewBody');
const overviewEditBtn = document.getElementById('overviewEditBtn');

let overviewProject = null;
let overviewRequestId = 0;
let overviewEditable = false;

// `editable`: solo desde la Lista. Encima de la tarjeta o de Organizar, el
// formulario del proyecto se abriría debajo de esos modales (va antes en el HTML).
async function openProjectOverview(projectId, { editable = false } = {}) {
    const requestId = ++overviewRequestId;
    overviewProject = null;
    overviewEditable = editable;
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
    overviewEditBtn.hidden = !overviewEditable || project.is_system || !project.is_active;

    const stats = el('div', 'report-stats');
    stats.append(
        summaryStat(formatDuration(data.total_seconds), 'tiempo total'),
        summaryStat(`${data.task_done} de ${data.task_total}`, 'tareas hechas'),
        summaryStat(String(data.session_count), data.session_count === 1 ? 'registro de tiempo' : 'registros de tiempo'),
        summaryStat(String(data.months.length), data.months.length === 1 ? 'mes con tiempo' : 'meses con tiempo'),
    );
    const cards = [reportCard('Resumen', stats)];
    // Solo con el plan maker encendido trae `finance` (el backend decide)
    if (data.finance) cards.push(renderCosting(data.finance));
    // Igual `estimates`; sin ningún estimado en el proyecto, la tarjeta sobra
    if (data.estimates && (data.estimates.overall.tasks || data.tasks.some(t => t.estimate_minutes))) {
        cards.push(estimatesCard(data.estimates, 'Estimado contra real'));
    }

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
            estimateMinutes: task.estimate_minutes,
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

// ============================================
// Estimado contra real (plan maker, Fase 4)
// ============================================
// La ficha y Costos pintan el mismo bloque `estimates` del backend
// (costing.estimate_deviation): aquí no se calcula nada, solo se formatea.

// 160 → "1.6×"
function formatRatio(pct) {
    return `${(pct / 100).toLocaleString('es-MX', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}×`;
}

function estimateRowItem(name, color, row, minTasks, muted = false) {
    const item = el('li', `estimate-row${muted ? ' muted' : ''}`);
    const label = el('span', 'estimate-name');
    if (color || muted) {
        const dot = el('i', 'report-bar-dot');
        if (color) dot.style.background = color;
        label.appendChild(dot);
    }
    label.append(name);
    const detail = el('span', 'estimate-detail',
        `${row.tasks} ${row.tasks === 1 ? 'tarea' : 'tareas'} · ${formatDuration(row.actual_seconds)} de ${formatDuration(row.estimate_seconds)}`);
    const ratio = row.ratio_pct === null
        ? el('span', 'estimate-ratio pending', 'poco historial')
        : el('span', 'estimate-ratio', formatRatio(row.ratio_pct));
    if (row.ratio_pct === null) ratio.title = `Hace falta al menos ${minTasks} tareas para dar una cifra`;
    item.append(label, ratio, detail);
    return item;
}

function estimatesCard(estimates, title) {
    const { overall, tags, untagged, min_tasks: minTasks } = estimates;
    if (!overall.tasks) {
        return reportCard(title, el('p', 'estimate-empty',
            'Todavía no hay tareas que comparar. Pon un estimado en el detalle de una tarjeta: '
            + 'cuenta al terminarla, o antes si ya se pasó de él.'));
    }
    const headline = el('p', 'estimate-headline');
    if (overall.ratio_pct === null) {
        headline.textContent = `Con ${overall.tasks} ${overall.tasks === 1 ? 'tarea' : 'tareas'} todavía hay poco historial: `
            + `la cifra sale desde ${minTasks}.`;
    } else {
        // ratio_pct × 36 = segundos reales por cada hora (3600 s) estimada
        headline.append('Tardas ', el('strong', '', formatRatio(overall.ratio_pct)), ' lo que estimas: ',
            `cada hora estimada te lleva ${formatDuration(overall.ratio_pct * 36)}.`);
    }
    const list = el('ul', 'estimate-rows');
    list.appendChild(estimateRowItem('Total', null, overall, minTasks));
    tags.forEach(tag => list.appendChild(estimateRowItem(tag.name, tag.color, tag, minTasks)));
    if (tags.length && untagged.tasks) list.appendChild(estimateRowItem('Sin etiqueta', null, untagged, minTasks, true));
    const note = el('p', 'report-compare-small',
        'Cuentan las tareas terminadas y las abiertas que ya pasaron su estimado.'
        + (tags.length > 1 ? ' Una tarea con varias etiquetas cuenta en cada una.' : ''));
    return reportCard(title, headline, list, note);
}

// ============================================
// Costeo (plan maker)
// ============================================
// Cliente, tarifa, moneda y presupuesto se guardan al cambiar cada campo, como
// el detalle de tarjeta. Al guardar solo se repinta el resultado, no los
// campos: repintarlos le quitaría el foco al siguiente.

// Las de CURRENCIES en backend/schemas.py
const CURRENCIES = ['MXN', 'USD', 'EUR', 'CAD', 'GBP', 'COP', 'ARS', 'CLP', 'PEN'];

function formatMoney(cents, currency) {
    try {
        return new Intl.NumberFormat('es-MX', { style: 'currency', currency }).format(cents / 100);
    } catch (error) {
        return `${(cents / 100).toFixed(2)} ${currency}`;
    }
}

// "350.5" → 35050; vacío → null. Centavos enteros, como los guarda el backend.
function centsFromInput(value) {
    const text = String(value).trim().replace(',', '.');
    return text === '' ? null : Math.round(Number(text) * 100);
}

function costingField(label, input) {
    const wrap = el('label', 'costing-field');
    wrap.append(el('span', 'costing-label', label), input);
    return wrap;
}

function costingInput(field, type, value, attrs = {}) {
    const input = document.createElement('input');
    input.type = type;
    input.dataset.field = field;
    input.value = value;
    Object.entries(attrs).forEach(([name, attr]) => input.setAttribute(name, attr));
    return input;
}

function renderCosting(finance) {
    const card = el('section', 'report-card costing-card');
    const head = el('div', 'costing-head');
    head.append(el('h3', 'report-card-title', 'Costeo'));
    const badge = el('span', 'costing-badge', 'Cotización');
    badge.title = 'Tiene presupuesto y todavía no hay tiempo registrado';
    head.appendChild(badge);

    const currency = document.createElement('select');
    currency.dataset.field = 'currency';
    CURRENCIES.forEach(code => currency.appendChild(new Option(code, code)));
    currency.value = finance.currency;

    const money = cents => (cents == null ? '' : (cents / 100).toFixed(2));
    const fields = el('div', 'costing-fields');
    fields.append(
        costingField('Cliente', costingInput('client_name', 'text', finance.client_name || '',
            { maxlength: '120', placeholder: 'Opcional' })),
        costingField('Tarifa por hora', costingInput('hourly_rate_cents', 'number', money(finance.hourly_rate_cents),
            { min: '0', step: '0.01', inputmode: 'decimal', placeholder: '0.00' })),
        costingField('Moneda', currency),
        costingField('Presupuesto', costingInput('budget_cents', 'number', money(finance.budget_cents),
            { min: '0', step: '0.01', inputmode: 'decimal', placeholder: 'Opcional' })),
        costingField('Presupuesto en horas', costingInput('budget_minutes', 'number',
            finance.budget_minutes == null ? '' : String(+(finance.budget_minutes / 60).toFixed(2)),
            { min: '0', step: '0.5', inputmode: 'decimal', placeholder: 'Opcional' })),
    );

    const result = el('div', 'costing-result');
    const error = el('div', 'form-error hidden');
    card.append(head, result, fields, error);
    paintCostingResult(card, finance);

    fields.addEventListener('change', (event) => saveCostingField(card, event.target));
    return card;
}

function paintCostingResult(card, finance) {
    card.querySelector('.costing-badge').hidden = !finance.is_quote;
    const result = card.querySelector('.costing-result');
    const { currency } = finance;
    const parts = [];
    if (finance.labor_cents != null) {
        const line = el('p', 'costing-labor');
        line.append(
            el('strong', '', formatMoney(finance.labor_cents, currency)),
            document.createTextNode(` de mano de obra · ${formatDuration(finance.total_seconds)} × ${formatMoney(finance.hourly_rate_cents, currency)}/h`),
        );
        parts.push(line);
    } else {
        parts.push(el('p', 'report-compare-small', 'Pon una tarifa por hora para calcular la mano de obra.'));
    }

    // Los gastos de la pestaña Costos, y lo que suman con la mano de obra
    if (finance.costs_cents > 0) {
        parts.push(el('p', 'costing-line',
            `+ ${formatMoney(finance.costs_cents, currency)} de gastos = ${formatMoney(finance.total_cost_cents, currency)} de costo total`));
    }
    if (finance.margin_cents != null) {
        const margin = el('p', `costing-line costing-margin${finance.margin_cents < 0 ? ' negative' : ''}`);
        margin.textContent = finance.margin_cents < 0
            ? `Te pasas del presupuesto por ${formatMoney(-finance.margin_cents, currency)}`
            : `Margen: ${formatMoney(finance.margin_cents, currency)}`;
        parts.push(margin);
    }

    // El avance del presupuesto, en dinero (horas + gastos) y en tiempo
    const rows = [];
    if (finance.budget_cents) {
        rows.push({
            name: `Presupuesto: ${formatMoney(finance.total_cost_cents || 0, currency)} de ${formatMoney(finance.budget_cents, currency)}`,
            pct: finance.budget_money_pct,
        });
    }
    if (finance.budget_minutes) {
        rows.push({
            name: `Horas: ${formatDuration(finance.total_seconds)} de ${formatDuration(finance.budget_minutes * 60)}`,
            pct: finance.budget_time_pct,
        });
    }
    if (rows.length) {
        const list = el('ul', 'report-bars');
        rows.forEach(row => {
            const pct = row.pct || 0;
            const item = el('li', `report-bar-row${pct > 100 ? ' over' : ''}`);
            const head = el('div', 'report-bar-head');
            head.append(el('span', 'report-bar-name', row.name), el('span', 'report-bar-value', `${pct} %`));
            const track = el('div', 'report-bar-track');
            const fill = el('div', 'report-bar-fill');
            fill.style.width = `${Math.min(100, pct)}%`;
            track.appendChild(fill);
            item.append(head, track);
            list.appendChild(item);
        });
        parts.push(list);
    }
    result.replaceChildren(...parts);
}

async function saveCostingField(card, input) {
    const field = input.dataset.field;
    if (!field || !overviewProject) return;
    let value;
    if (field === 'client_name') value = input.value.trim() || null;
    else if (field === 'currency') value = input.value;
    else if (field === 'budget_minutes') value = input.value === '' ? null : Math.round(Number(input.value) * 60);
    else value = centsFromInput(input.value);

    const error = card.querySelector('.form-error');
    error.classList.add('hidden');
    try {
        const finance = await apiFetch(`/api/projects/${overviewProject.id}/finance`, {
            method: 'PUT',
            json: { [field]: value },
        });
        paintCostingResult(card, finance);
    } catch (err) {
        showError(error, err.message);
    }
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
// Encender o apagar el plan maker pone o quita el costeo de la ficha abierta
window.modulesChangedHooks.push(() => {
    if (overviewProject && !projectOverviewModal.classList.contains('hidden')) {
        openProjectOverview(overviewProject.id, { editable: overviewEditable });
    }
});
