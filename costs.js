// ============================================
// Costos: lo que cuesta cada proyecto (plan Maker, épica 24 Fase 3)
// ============================================
//
// Cuarta vista, solo con el plan Maker encendido. Arriba, el resumen de
// /api/costs/summary (costo y margen por proyecto, gasto por categoría,
// totales por moneda); abajo, la hoja de gastos del proyecto elegido, que se
// edita celda por celda. Varios gastos entran de una vez pegando filas de
// Excel o Google Sheets (llegan como texto separado por tabuladores) o con un
// CSV, siempre con vista previa. Los cálculos de dinero son del backend
// (backend/costing.py); aquí solo se formatean. Carga después de
// project-overview.js: usa formatMoney y CURRENCIES de ahí, y barList,
// summaryStat, reportCard y el de reports.js.

const costsState = {
    summary: null,
    categories: [],
    projectId: null,      // proyecto de la hoja
    costs: [],
    currency: 'MXN',
    loaded: false,
    pending: null,        // filas de la vista previa, antes de "Agregar"
};

const costsSummaryEl = document.getElementById('costsSummary');
const costsProjectSelect = document.getElementById('costsProject');
const costsRows = document.getElementById('costsRows');
const costsTotalEl = document.getElementById('costsTotal');
const costsError = document.getElementById('costsError');
const costsCategoryList = document.getElementById('costsCategoryList');
const costsCategoryError = document.getElementById('costsCategoryError');
const costsImportModal = document.getElementById('costsImportModal');
const COSTS_PROJECT_KEY = 'costs_project';

function isCostsVisible() {
    return typeof currentViewId !== 'undefined' && currentViewId === 'costs';
}

// En computadora (≥ 900 px) la app se ensancha mientras se ve Costos, como
// el tablero: la hoja necesita sus siete columnas
const wideCostsQuery = window.matchMedia ? window.matchMedia('(min-width: 900px)') : null;

function applyCostsWide() {
    document.body.classList.toggle('costs-wide', isCostsVisible() && !!(wideCostsQuery && wideCostsQuery.matches));
}

if (wideCostsQuery && wideCostsQuery.addEventListener) {
    wideCostsQuery.addEventListener('change', applyCostsWide);
}

// ============================================
// Módulo: la pestaña existe solo con el plan Maker
// ============================================

function applyCostsModule() {
    const on = moduleEnabled('maker');
    // Antes de mostrarla: setViewVisible() pasa por goToView(), que recuerda la
    // pestaña actual y taparía que se recargó estando en Costos
    const wasOnCosts = readLastView() === 'costs';
    setViewVisible('costs', on);
    // Recargar estando en Costos: la vista se pidió antes de saber del plan
    if (on && wasOnCosts && currentViewId !== 'costs') {
        goToView('costs', { animate: false });
    }
    if (!on) costsState.loaded = false;
}

// ============================================
// Carga
// ============================================

async function loadCosts() {
    if (!getToken() || !moduleEnabled('maker')) return;
    try {
        const [summary, categories] = await Promise.all([
            apiFetch('/api/costs/summary'),
            apiFetch('/api/costs/categories'),
        ]);
        costsState.summary = summary;
        costsState.categories = categories.categories;
        costsState.loaded = true;
    } catch (error) {
        costsSummaryEl.replaceChildren(reportsMessage(error.message || 'No se pudo cargar Costos.'));
        return;
    }
    renderCostsSummary();
    renderCostsProjectSelect();
    renderCostCategories();
    await loadCostRows();
}

async function loadCostRows() {
    costsError.classList.add('hidden');
    if (!costsState.projectId) {
        costsState.costs = [];
        renderCostRows();
        return;
    }
    try {
        const data = await apiFetch(`/api/costs?project_id=${costsState.projectId}`);
        costsState.costs = data.costs;
        costsState.currency = data.currency;
    } catch (error) {
        showError(costsError, error.message);
        costsState.costs = [];
    }
    renderCostRows();
}

// Tras guardar algo: el resumen cambia, la hoja ya está al día
async function refreshCostsSummary() {
    try {
        costsState.summary = await apiFetch('/api/costs/summary');
        renderCostsSummary();
    } catch (error) {
        console.error('Error actualizando el resumen de costos:', error);
    }
}

// ============================================
// Resumen
// ============================================

function renderCostsSummary() {
    const { summary } = costsState;
    if (!summary) return;
    const cards = [];

    // Una tarjeta de totales por moneda: nunca se suman monedas distintas
    summary.totals.forEach(total => {
        const stats = el('div', 'report-stats');
        stats.append(
            summaryStat(formatMoney(total.total_cost_cents, total.currency), 'costo total'),
            summaryStat(formatMoney(total.labor_cents, total.currency), 'mano de obra'),
            summaryStat(formatMoney(total.costs_cents, total.currency), 'gastos'),
            summaryStat(total.budget_cents ? formatMoney(total.budget_cents, total.currency) : '—', 'presupuestado'),
        );
        cards.push(reportCard(summary.totals.length > 1 ? `Resumen · ${total.currency}` : 'Resumen', stats));
    });

    if (summary.projects.length === 0) {
        cards.push(reportsMessage('Todavía no tienes proyectos. Crea uno en Tableros para costearlo.'));
    } else {
        cards.push(reportCard('Por proyecto', costsProjectTable(summary.projects)));
    }

    // En qué se va el dinero, por moneda: la mano de obra (horas × tarifa) como
    // una barra más, y cada categoría de gasto
    summary.totals.forEach(total => {
        const rows = [];
        if (total.labor_cents > 0) {
            rows.push({ key: 'labor', name: 'Mano de obra', color: 'var(--accent)', cents: total.labor_cents });
        }
        summary.categories
            .filter(c => c.currency === total.currency)
            .forEach(c => rows.push({ key: `cat-${c.category_id}`, name: c.name, color: c.color, cents: c.cents }));
        if (!rows.length) return;
        const title = summary.totals.length > 1 ? `En qué se va el dinero · ${total.currency}` : 'En qué se va el dinero';
        cards.push(reportCard(title, costsBreakdownChart(rows, total.currency)));
    });
    costsSummaryEl.replaceChildren(...cards);
}

// Ocultas de la gráfica (no de los totales), en esta sesión: "labor" o "cat-<id>"
const hiddenBreakdown = new Set();

// Barras de dinero con su leyenda abajo: tocar un punto oculta o muestra esa
// barra, y las demás se reescalan a la más grande de las que quedan
function costsBreakdownChart(rows, currency) {
    const wrap = el('div', 'costs-breakdown');
    const bars = el('ul', 'report-bars');
    const legend = el('div', 'costs-legend');
    legend.setAttribute('role', 'group');
    legend.setAttribute('aria-label', 'Mostrar u ocultar en la gráfica');

    function paint() {
        const visible = rows.filter(r => !hiddenBreakdown.has(r.key));
        const max = Math.max(1, ...visible.map(r => r.cents));
        const sum = visible.reduce((total, r) => total + r.cents, 0);
        bars.replaceChildren(...visible.map(r => {
            const item = el('li', 'report-bar-row');
            const head = el('div', 'report-bar-head');
            const name = el('span', 'report-bar-name');
            const dot = el('i', 'report-bar-dot');
            if (r.color) dot.style.background = r.color;
            name.append(dot, document.createTextNode(r.name));
            const value = el('span', 'report-bar-value', formatMoney(r.cents, currency));
            if (sum) value.appendChild(el('span', 'report-bar-pct', ` · ${Math.round(r.cents / sum * 100)}%`));
            head.append(name, value);
            const track = el('div', 'report-bar-track');
            const fill = el('div', 'report-bar-fill');
            fill.style.width = `${(r.cents / max) * 100}%`;
            if (r.color) fill.style.background = r.color;
            track.appendChild(fill);
            item.append(head, track);
            return item;
        }));
        if (!visible.length) bars.appendChild(el('li', 'costs-legend-empty', 'Todo está oculto: toca un punto para mostrarlo.'));
        legend.querySelectorAll('[data-key]').forEach(button => {
            button.setAttribute('aria-pressed', String(!hiddenBreakdown.has(button.dataset.key)));
        });
    }

    rows.forEach(r => {
        const button = el('button', 'costs-legend-item');
        button.type = 'button';
        button.dataset.key = r.key;
        button.title = 'Mostrar u ocultar en la gráfica';
        const dot = el('i', 'report-bar-dot');
        if (r.color) dot.style.background = r.color;
        button.append(dot, document.createTextNode(r.name));
        button.addEventListener('click', () => {
            if (hiddenBreakdown.has(r.key)) hiddenBreakdown.delete(r.key);
            else hiddenBreakdown.add(r.key);
            paint();
        });
        legend.appendChild(button);
    });
    paint();
    wrap.append(bars, legend);
    return wrap;
}

function costsProjectTable(projects) {
    const wrap = el('div', 'costs-sheet-scroll');
    const table = el('table', 'costs-projects');
    const head = el('tr');
    [['Proyecto', ''], ['Horas', 'col-hide-narrow'], ['Mano de obra', 'col-hide-narrow'],
        ['Gastos', 'col-hide-narrow'], ['Costo', ''], ['Presupuesto', 'col-hide-narrow'], ['Margen', '']]
        .forEach(([text, cls]) => head.appendChild(el('th', cls, text)));
    const thead = el('thead');
    thead.appendChild(head);
    const tbody = el('tbody');
    projects.forEach(p => {
        const row = el('tr', p.project_id === costsState.projectId ? 'selected' : '');
        row.dataset.projectId = String(p.project_id);
        row.tabIndex = 0;
        row.title = 'Ver sus gastos';
        const name = el('td', 'costs-project-name');
        const dot = el('i', 'report-bar-dot');
        if (p.color) dot.style.background = p.color;
        name.append(dot, document.createTextNode(p.name));
        if (!p.is_active) name.appendChild(el('span', 'report-bar-note', ' archivado'));
        if (p.is_quote) name.appendChild(el('span', 'costing-badge', 'Cotización'));
        const money = cents => (cents == null ? '—' : formatMoney(cents, p.currency));
        const margin = el('td', p.margin_cents == null ? '' : (p.margin_cents < 0 ? 'negative' : 'positive'),
            money(p.margin_cents));
        // Mano de obra y presupuesto se editan tocándolos. La mano de obra se
        // calcula (horas × tarifa): lo que se cambia es la tarifa por hora.
        const labor = el('td', 'col-hide-narrow costs-editable', money(p.labor_cents));
        labor.dataset.edit = 'hourly_rate_cents';
        labor.dataset.value = p.hourly_rate_cents == null ? '' : (p.hourly_rate_cents / 100).toFixed(2);
        labor.title = p.hourly_rate_cents == null
            ? 'Toca para poner la tarifa por hora'
            : `Tarifa: ${formatMoney(p.hourly_rate_cents, p.currency)}/h. Toca para cambiarla`;
        const budget = el('td', 'col-hide-narrow costs-editable', money(p.budget_cents));
        budget.dataset.edit = 'budget_cents';
        budget.dataset.value = p.budget_cents == null ? '' : (p.budget_cents / 100).toFixed(2);
        budget.title = 'Toca para cambiar el presupuesto';
        row.append(
            name,
            el('td', 'col-hide-narrow', formatDuration(p.total_seconds)),
            labor,
            el('td', 'col-hide-narrow', money(p.costs_cents)),
            el('td', '', money(p.total_cost_cents)),
            budget,
            margin,
        );
        tbody.appendChild(row);
    });
    table.append(thead, tbody);
    wrap.appendChild(table);
    return wrap;
}

// Editar en la celda: un campo en su lugar; Enter o salir guarda, Escape cancela
function startCostsCellEdit(td) {
    if (td.querySelector('input')) return;
    const projectId = Number(td.closest('tr').dataset.projectId);
    const field = td.dataset.edit;
    const shown = td.textContent;
    const input = document.createElement('input');
    input.type = 'number';
    input.min = '0';
    input.step = '0.01';
    input.inputMode = 'decimal';
    input.className = 'costs-cell-input';
    input.value = td.dataset.value;
    input.placeholder = field === 'hourly_rate_cents' ? 'Tarifa/h' : 'Presupuesto';
    input.setAttribute('aria-label', field === 'hourly_rate_cents' ? 'Tarifa por hora' : 'Presupuesto');
    td.replaceChildren(input);
    input.focus();
    input.select();

    let done = false;
    const finish = async (save) => {
        if (done) return;
        done = true;
        if (!save || input.value === td.dataset.value) {
            td.textContent = shown;
            return;
        }
        costsError.classList.add('hidden');
        try {
            await apiFetch(`/api/projects/${projectId}/finance`, {
                method: 'PUT',
                json: { [field]: input.value === '' ? null : centsFromInput(input.value) },
            });
            await refreshCostsSummary();
        } catch (error) {
            td.textContent = shown;
            showError(costsError, error.message);
        }
    };
    input.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') { event.preventDefault(); finish(true); }
        else if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); finish(false); }
    });
    input.addEventListener('blur', () => finish(true));
}

costsSummaryEl.addEventListener('click', (event) => {
    const editable = event.target.closest('.costs-editable');
    if (editable) {
        startCostsCellEdit(editable);
        return;
    }
    if (event.target.closest('.costs-cell-input')) return;
    const row = event.target.closest('tr[data-project-id]');
    if (row) selectCostsProject(Number(row.dataset.projectId), { scroll: true });
});
costsSummaryEl.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter' || event.target.closest('.costs-cell-input')) return;
    const row = event.target.closest('tr[data-project-id]');
    if (row) selectCostsProject(Number(row.dataset.projectId), { scroll: true });
});

// ============================================
// Hoja de gastos
// ============================================

function renderCostsProjectSelect() {
    const projects = (costsState.summary && costsState.summary.projects) || [];
    costsProjectSelect.innerHTML = '';
    projects.forEach(p => {
        costsProjectSelect.appendChild(new Option(p.is_active ? p.name : `${p.name} (archivado)`, String(p.project_id)));
    });
    let stored = null;
    try { stored = Number(localStorage.getItem(COSTS_PROJECT_KEY)); } catch (error) { /* sin almacenamiento */ }
    const ids = projects.map(p => p.project_id);
    if (!ids.includes(costsState.projectId)) {
        costsState.projectId = ids.includes(stored) ? stored : (ids[0] || null);
    }
    if (costsState.projectId) costsProjectSelect.value = String(costsState.projectId);
    costsProjectSelect.disabled = projects.length === 0;
}

async function selectCostsProject(projectId, { scroll = false } = {}) {
    // Los borradores eran del proyecto anterior
    if (projectId !== costsState.projectId) costsRows.replaceChildren();
    costsState.projectId = projectId;
    costsProjectSelect.value = String(projectId);
    try { localStorage.setItem(COSTS_PROJECT_KEY, String(projectId)); } catch (error) { /* solo no se recuerda */ }
    costsSummaryEl.querySelectorAll('tr[data-project-id]').forEach(row => {
        row.classList.toggle('selected', Number(row.dataset.projectId) === projectId);
    });
    await loadCostRows();
    // Solo en vertical: scrollIntoView() también correría en horizontal el
    // contenedor de las vistas, y dejaba la pestaña desplazada a un lado
    if (scroll) {
        const top = document.querySelector('.costs-sheet-card').getBoundingClientRect().top + window.scrollY - 12;
        window.scrollTo({ top, behavior: prefersReducedMotion() ? 'auto' : 'smooth' });
    }
}

costsProjectSelect.addEventListener('change', () => selectCostsProject(Number(costsProjectSelect.value)));

function categoryOptions(select, selectedId) {
    select.innerHTML = '';
    costsState.categories.forEach(c => select.appendChild(new Option(c.name, String(c.id))));
    if (selectedId) select.value = String(selectedId);
}

function money2(cents) {
    return cents == null ? '' : (cents / 100).toFixed(2);
}

function cell(child, cls) {
    const td = el('td', cls);
    td.appendChild(child);
    return td;
}

function sheetInput(field, type, value, attrs = {}) {
    const input = document.createElement('input');
    input.type = type;
    input.dataset.field = field;
    input.value = value;
    Object.entries(attrs).forEach(([name, attr]) => input.setAttribute(name, attr));
    return input;
}

// Una fila de la hoja. Sin id es un borrador: se crea en el backend al tener
// concepto. Con id, cada celda se guarda al cambiar (PATCH de esa celda).
function buildCostRow(cost) {
    const row = el('tr', 'cost-row');
    if (cost.id) row.dataset.costId = String(cost.id);
    const category = document.createElement('select');
    category.dataset.field = 'category_id';
    category.setAttribute('aria-label', 'Categoría');
    categoryOptions(category, cost.category_id);

    const remove = el('button', 'cost-delete', '×');
    remove.type = 'button';
    remove.title = 'Borrar este gasto';
    remove.setAttribute('aria-label', `Borrar ${cost.concept || 'este gasto'}`);

    row.append(
        cell(sheetInput('cost_date', 'date', cost.cost_date, { 'aria-label': 'Fecha', required: '' }), 'col-date'),
        cell(sheetInput('concept', 'text', cost.concept || '', { maxlength: '200', placeholder: 'Concepto', 'aria-label': 'Concepto' }), 'col-concept'),
        cell(category, 'col-category'),
        cell(sheetInput('quantity', 'number', String(cost.quantity ?? 1), { min: '0', step: 'any', inputmode: 'decimal', 'aria-label': 'Cantidad' }), 'col-qty'),
        cell(sheetInput('unit_cost_cents', 'number', money2(cost.unit_cost_cents), { min: '0', step: '0.01', inputmode: 'decimal', placeholder: '0.00', 'aria-label': 'Costo unitario' }), 'col-unit'),
        el('td', 'col-total', cost.id ? formatMoney(cost.total_cents, costsState.currency) : ''),
        cell(remove, 'col-actions'),
    );
    return row;
}

function renderCostRows() {
    // Las filas nuevas sin guardar (sin concepto todavía) sobreviven al repintado:
    // "＋ Agregar fila" justo mientras llegaban los gastos las borraba
    const drafts = [...costsRows.querySelectorAll('tr.cost-row:not([data-cost-id])')];
    costsRows.replaceChildren(...drafts, ...costsState.costs.map(buildCostRow));
    if (!costsState.projectId) {
        const empty = el('tr', 'cost-empty');
        const td = el('td', '', 'Elige un proyecto para ver sus gastos.');
        td.colSpan = 7;
        empty.appendChild(td);
        costsRows.appendChild(empty);
    }
    paintCostsTotal();
    document.getElementById('costsAddRow').disabled = !costsState.projectId;
}

function paintCostsTotal() {
    const total = costsState.costs.reduce((sum, c) => sum + (c.total_cents || 0), 0);
    costsTotalEl.textContent = costsState.projectId ? formatMoney(total, costsState.currency) : '';
}

function addDraftRow() {
    if (!costsState.projectId || !costsState.categories.length) return;
    const draft = {
        cost_date: getDateKey(new Date()), concept: '', quantity: 1, unit_cost_cents: null,
        category_id: costsState.categories[costsState.categories.length - 1].id,   // "Otro" de inicio
    };
    const row = buildCostRow(draft);
    costsRows.prepend(row);
    row.querySelector('[data-field="concept"]').focus();
}

document.getElementById('costsAddRow').addEventListener('click', addDraftRow);

function readCostField(input) {
    const field = input.dataset.field;
    if (field === 'category_id') return Number(input.value);
    if (field === 'quantity') return input.value === '' ? null : Number(input.value);
    if (field === 'unit_cost_cents') return input.value === '' ? 0 : centsFromInput(input.value);
    if (field === 'concept') return input.value.trim();
    return input.value;
}

async function saveCostCell(input) {
    const row = input.closest('tr.cost-row');
    if (!row) return;
    costsError.classList.add('hidden');
    const id = row.dataset.costId;
    try {
        let saved;
        if (id) {
            saved = await apiFetch(`/api/costs/${id}`, { method: 'PATCH', json: { [input.dataset.field]: readCostField(input) } });
            costsState.costs = costsState.costs.map(c => (c.id === saved.id ? saved : c));
        } else {
            // Un borrador se crea cuando ya tiene concepto, con todas sus celdas
            const fields = {};
            row.querySelectorAll('[data-field]').forEach(f => { fields[f.dataset.field] = readCostField(f); });
            if (!fields.concept) return;
            saved = await apiFetch('/api/costs', { method: 'POST', json: { project_id: costsState.projectId, ...fields } });
            row.dataset.costId = String(saved.id);
            costsState.costs = [saved, ...costsState.costs];
        }
        row.querySelector('.col-total').textContent = formatMoney(saved.total_cents, costsState.currency);
        paintCostsTotal();
        refreshCostsSummary();
    } catch (error) {
        showError(costsError, error.message);
    }
}

costsRows.addEventListener('change', (event) => {
    if (event.target.dataset.field) saveCostCell(event.target);
});

// Enter baja a la misma columna de la fila siguiente, como en una hoja
costsRows.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter' || !event.target.dataset.field || event.target.tagName === 'SELECT') return;
    event.preventDefault();
    const field = event.target.dataset.field;
    const next = event.target.closest('tr').nextElementSibling;
    event.target.blur();   // dispara su change: se guarda
    const target = next && next.querySelector(`[data-field="${field}"]`);
    if (target) target.focus();
});

costsRows.addEventListener('click', async (event) => {
    const button = event.target.closest('.cost-delete');
    if (!button) return;
    const row = button.closest('tr.cost-row');
    const id = row.dataset.costId;
    if (!id) {           // borrador sin guardar
        row.remove();
        return;
    }
    const cost = costsState.costs.find(c => String(c.id) === id);
    const ok = await confirmDialog(`¿Borrar el gasto "${cost ? cost.concept : ''}"?`, { confirmLabel: 'Borrar', danger: true });
    if (!ok) return;
    try {
        await apiFetch(`/api/costs/${id}`, { method: 'DELETE' });
        costsState.costs = costsState.costs.filter(c => String(c.id) !== id);
        row.remove();
        paintCostsTotal();
        refreshCostsSummary();
    } catch (error) {
        showError(costsError, error.message);
    }
});

// ============================================
// Pegar de una hoja / importar un CSV
// ============================================

const HEADER_ALIASES = {
    cost_date: ['fecha', 'date', 'dia', 'día'],
    concept: ['concepto', 'descripcion', 'descripción', 'concept', 'description', 'detalle', 'articulo', 'artículo', 'producto'],
    category: ['categoria', 'categoría', 'category', 'tipo', 'rubro'],
    quantity: ['cantidad', 'qty', 'quantity', 'cant', 'unidades', 'piezas'],
    unit_cost: ['costo unitario', 'precio unitario', 'costo', 'precio', 'unit cost', 'price', 'importe', 'monto', 'unitario'],
    note: ['nota', 'notas', 'note', 'comentario', 'observaciones'],
};
// Sin encabezado: el orden de las columnas de la hoja
const DEFAULT_ORDER = ['cost_date', 'concept', 'category', 'quantity', 'unit_cost', 'note'];

function normalize(text) {
    return String(text).trim().toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
}

// Texto de una hoja o un CSV en filas de celdas. Respeta comillas ("a, b") y
// saltos de línea dentro de ellas. El separador: tabulador (lo que copia
// Excel/Sheets), si no punto y coma (Excel en español), si no coma.
function parseTable(text) {
    const clean = text.replace(/^﻿/, '').replace(/\r\n?/g, '\n');
    const firstLine = clean.split('\n')[0];
    const sep = firstLine.includes('\t') ? '\t' : (firstLine.split(';').length > firstLine.split(',').length ? ';' : ',');
    const rows = [];
    let row = [];
    let value = '';
    let quoted = false;
    for (let i = 0; i < clean.length; i++) {
        const ch = clean[i];
        if (quoted) {
            if (ch === '"' && clean[i + 1] === '"') { value += '"'; i++; }
            else if (ch === '"') quoted = false;
            else value += ch;
        } else if (ch === '"' && value === '') quoted = true;
        else if (ch === sep) { row.push(value); value = ''; }
        else if (ch === '\n') { row.push(value); rows.push(row); row = []; value = ''; }
        else value += ch;
    }
    if (value !== '' || row.length) { row.push(value); rows.push(row); }
    return rows.filter(r => r.some(c => c.trim() !== ''));
}

// "1,234.50", "1.234,50", "$ 350", "350,5" → centavos; null si no es número
function parseMoneyCents(text) {
    let s = String(text).replace(/[^\d.,-]/g, '');
    if (!s) return null;
    const lastComma = s.lastIndexOf(',');
    const lastDot = s.lastIndexOf('.');
    if (lastComma > -1 && lastDot > -1) {
        // El que va al final es el decimal
        s = lastComma > lastDot ? s.replace(/\./g, '').replace(',', '.') : s.replace(/,/g, '');
    } else if (lastComma > -1) {
        // Solo coma: decimal si le siguen 1 o 2 cifras al final ("350,5"); si no, de miles
        s = /,\d{1,2}$/.test(s) ? s.replace(',', '.') : s.replace(/,/g, '');
    }
    const number = Number(s);
    return Number.isFinite(number) ? Math.round(number * 100) : null;
}

function parseQuantity(text) {
    if (String(text).trim() === '') return 1;
    const cents = parseMoneyCents(text);
    return cents == null ? null : cents / 100;
}

// "2026-09-30", "30/09/2026", "30/9/26" → "AAAA-MM-DD" (día primero: México); vacío → hoy
function parseDate(text) {
    const s = String(text).trim();
    if (!s) return getDateKey(new Date());
    let m = s.match(/^(\d{4})-(\d{1,2})-(\d{1,2})/);
    if (m) return `${m[1]}-${m[2].padStart(2, '0')}-${m[3].padStart(2, '0')}`;
    m = s.match(/^(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})$/);
    if (m) {
        const year = m[3].length === 2 ? `20${m[3]}` : m[3];
        const day = Number(m[1]);
        const month = Number(m[2]);
        if (month >= 1 && month <= 12 && day >= 1 && day <= 31) {
            return `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
        }
    }
    return null;
}

// Filas de texto → gastos para la vista previa, con el problema de cada una
function rowsToCosts(table) {
    if (!table.length) return { rows: [], newCategories: [] };
    // ¿La primera fila es un encabezado? Si alguna celda se reconoce, sí
    const header = table[0].map(normalize);
    const columns = {};
    header.forEach((name, i) => {
        Object.entries(HEADER_ALIASES).forEach(([field, aliases]) => {
            if (columns[field] === undefined && aliases.some(alias => name === normalize(alias))) columns[field] = i;
        });
    });
    const hasHeader = columns.concept !== undefined || columns.unit_cost !== undefined;
    const body = hasHeader ? table.slice(1) : table;
    if (!hasHeader) DEFAULT_ORDER.forEach((field, i) => { columns[field] = i; });

    const byName = new Map(costsState.categories.map(c => [normalize(c.name), c]));
    const fallback = costsState.categories[costsState.categories.length - 1];
    const newCategories = new Set();
    const rows = body.map(cells => {
        const get = field => (columns[field] === undefined ? '' : (cells[columns[field]] || '').trim());
        const categoryName = get('category');
        const known = categoryName ? byName.get(normalize(categoryName)) : null;
        if (categoryName && !known) newCategories.add(categoryName);
        const row = {
            cost_date: parseDate(get('cost_date')),
            concept: get('concept').slice(0, 200),
            categoryName: known ? known.name : (categoryName || fallback.name),
            category_id: known ? known.id : (categoryName ? null : fallback.id),
            quantity: parseQuantity(get('quantity')),
            unit_cost_cents: get('unit_cost') === '' ? 0 : parseMoneyCents(get('unit_cost')),
            note: get('note').slice(0, 500) || null,
        };
        row.problem = !row.concept ? 'sin concepto'
            : row.cost_date == null ? `fecha "${get('cost_date')}" no válida`
                : row.quantity == null || row.quantity <= 0 ? `cantidad "${get('quantity')}" no válida`
                    : row.unit_cost_cents == null || row.unit_cost_cents < 0 ? `costo "${get('unit_cost')}" no válido`
                        : null;
        return row;
    });
    return { rows, newCategories: [...newCategories] };
}

function openCostsImport(text) {
    if (!costsState.projectId) {
        showError(costsError, 'Elige primero el proyecto al que van los gastos.');
        return;
    }
    const { rows, newCategories } = rowsToCosts(parseTable(text));
    if (!rows.length) {
        showError(costsError, 'No encontré filas para agregar.');
        return;
    }
    costsState.pending = { rows, newCategories };
    const project = costsState.summary.projects.find(p => p.project_id === costsState.projectId);
    const valid = rows.filter(r => !r.problem).length;
    document.getElementById('costsImportSummary').textContent =
        `${valid} de ${rows.length} ${rows.length === 1 ? 'fila' : 'filas'} se agregarán a "${project ? project.name : ''}".`
        + (valid < rows.length ? ' Las marcadas en rojo se saltan.' : '');
    const tbody = document.getElementById('costsImportRows');
    tbody.replaceChildren(...rows.map(r => {
        const tr = el('tr', r.problem ? 'invalid' : '');
        const total = r.problem ? '' : formatMoney(Math.round((r.quantity || 0) * (r.unit_cost_cents || 0)), costsState.currency);
        [r.cost_date || '—', r.concept || '—', r.categoryName, r.quantity == null ? '—' : String(r.quantity),
            r.unit_cost_cents == null ? '—' : formatMoney(r.unit_cost_cents, costsState.currency), total]
            .forEach(text => tr.appendChild(el('td', '', text)));
        if (r.problem) tr.title = r.problem;
        return tr;
    }));
    const option = document.getElementById('costsImportNewCatsOption');
    option.classList.toggle('hidden', newCategories.length === 0);
    document.getElementById('costsImportNewCats').checked = true;
    document.getElementById('costsImportNewCatsLabel').textContent =
        `Crear ${newCategories.length === 1 ? 'la categoría' : 'las categorías'} ${newCategories.map(n => `"${n}"`).join(', ')} (si no, van a "${costsState.categories[costsState.categories.length - 1].name}")`;
    document.getElementById('costsImportError').classList.add('hidden');
    document.getElementById('costsImportConfirm').disabled = valid === 0;
    showModal(costsImportModal);
}

// Un color que ninguna categoría use, para las que se crean al importar: sin
// color salían del mismo azul que la mano de obra en la gráfica
const CATEGORY_PALETTE = ['#e67e22', '#3498db', '#27ae60', '#9b59b6', '#95a5a6', '#e74c3c',
    '#1abc9c', '#f1c40f', '#e84393', '#8d6e63', '#34495e', '#00b894'];

function freeCategoryColor() {
    const used = new Set(costsState.categories.map(c => (c.color || '').toLowerCase()));
    return CATEGORY_PALETTE.find(color => !used.has(color)) || CATEGORY_PALETTE[costsState.categories.length % CATEGORY_PALETTE.length];
}

function closeCostsImport() {
    costsState.pending = null;
    hideModal(costsImportModal);
}

async function confirmCostsImport() {
    const pending = costsState.pending;
    if (!pending) return;
    const errorEl = document.getElementById('costsImportError');
    const confirmBtn = document.getElementById('costsImportConfirm');
    confirmBtn.disabled = true;
    try {
        // Las categorías nuevas primero, si se pidió; si no, a la de "otro"
        const fallback = costsState.categories[costsState.categories.length - 1];
        const created = new Map();
        if (document.getElementById('costsImportNewCats').checked) {
            for (const name of pending.newCategories) {
                const category = await apiFetch('/api/costs/categories', {
                    method: 'POST', json: { name: name.slice(0, 40), color: freeCategoryColor() },
                });
                costsState.categories.push(category);   // para que la siguiente tome otro color
                created.set(name, category.id);
            }
        }
        const rows = pending.rows.filter(r => !r.problem).map(r => ({
            cost_date: r.cost_date, concept: r.concept, quantity: r.quantity,
            unit_cost_cents: r.unit_cost_cents, note: r.note,
            category_id: r.category_id ?? created.get(r.categoryName) ?? fallback.id,
        }));
        await apiFetch('/api/costs/import', { method: 'POST', json: { project_id: costsState.projectId, rows } });
        closeCostsImport();
        await loadCosts();
    } catch (error) {
        showError(errorEl, error.message);
        confirmBtn.disabled = false;
    }
}

// Pegar varias celdas en la hoja abre la vista previa. Una sola celda (sin
// tabulador ni salto de línea) se pega normal en la celda.
document.querySelector('.costs-sheet-card').addEventListener('paste', (event) => {
    const text = event.clipboardData && event.clipboardData.getData('text/plain');
    if (!text || !/[\t\n]/.test(text.trim())) return;
    event.preventDefault();
    openCostsImport(text);
});

document.getElementById('costsImportBtn').addEventListener('click', () => document.getElementById('costsImportFile').click());
document.getElementById('costsImportFile').addEventListener('change', async (event) => {
    const file = event.target.files[0];
    event.target.value = '';
    if (!file) return;
    if (file.size > 1024 * 1024) {
        showError(costsError, 'El archivo pesa más de 1 MB.');
        return;
    }
    openCostsImport(await file.text());
});
document.getElementById('costsImportConfirm').addEventListener('click', confirmCostsImport);
document.getElementById('costsImportCancel').addEventListener('click', closeCostsImport);
document.getElementById('costsImportClose').addEventListener('click', closeCostsImport);
costsImportModal.querySelector('.modal-overlay').addEventListener('click', closeCostsImport);
document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape' || costsImportModal.classList.contains('hidden')) return;
    event.stopPropagation();
    closeCostsImport();
}, true);

// ============================================
// Categorías
// ============================================

function renderCostCategories() {
    costsCategoryList.replaceChildren(...costsState.categories.map((c, i, all) => {
        const row = el('div', 'config-row');
        row.dataset.categoryId = String(c.id);
        // Asa para arrastrar, como las columnas de Organizar (con mouse; en
        // táctil quedan las flechas)
        const handle = el('span', 'config-drag', '⠿');
        handle.title = 'Arrastra para ordenar';
        handle.setAttribute('aria-hidden', 'true');
        const color = document.createElement('input');
        color.type = 'color';
        color.className = 'config-color';
        color.value = c.color || '#95a5a6';
        color.setAttribute('aria-label', `Color de ${c.name}`);
        const name = document.createElement('input');
        name.type = 'text';
        name.className = 'config-name';
        name.maxLength = 40;
        name.value = c.name;
        name.setAttribute('aria-label', `Nombre de ${c.name}`);
        const count = el('span', 'config-type', c.cost_count ? `${c.cost_count} ${c.cost_count === 1 ? 'gasto' : 'gastos'}` : '');
        const up = configButton('config-action cost-cat-move', `Subir ${c.name}`, '↑');
        up.dataset.delta = '-1';
        up.disabled = i === 0;
        const down = configButton('config-action cost-cat-move', `Bajar ${c.name}`, '↓');
        down.dataset.delta = '1';
        down.disabled = i === all.length - 1;
        const remove = configButton('config-action danger cost-cat-delete', `Eliminar ${c.name}`, '×');
        row.append(handle, color, name, count, up, down, remove);
        return row;
    }));
}

async function costCategoryAction(request) {
    costsCategoryError.classList.add('hidden');
    try {
        await request();
    } catch (error) {
        showError(costsCategoryError, error.message);
    }
    await loadCosts();
}

costsCategoryList.addEventListener('change', (event) => {
    const row = event.target.closest('[data-category-id]');
    if (!row) return;
    const id = row.dataset.categoryId;
    const json = event.target.type === 'color' ? { color: event.target.value } : { name: event.target.value };
    costCategoryAction(() => apiFetch(`/api/costs/categories/${id}`, { method: 'PATCH', json }));
});

costsCategoryList.addEventListener('click', (event) => {
    const row = event.target.closest('[data-category-id]');
    if (!row) return;
    const id = Number(row.dataset.categoryId);
    if (event.target.closest('.cost-cat-delete')) {
        costCategoryAction(() => apiFetch(`/api/costs/categories/${id}`, { method: 'DELETE' }));
        return;
    }
    const move = event.target.closest('.cost-cat-move');
    if (!move) return;
    const list = [...costsState.categories];
    const from = list.findIndex(c => c.id === id);
    const to = from + Number(move.dataset.delta);
    if (to < 0 || to >= list.length) return;
    [list[from], list[to]] = [list[to], list[from]];
    saveCategoryOrder(list);
});

// Reescribe el orden de las que cambian de lugar, como las columnas
function saveCategoryOrder(list) {
    if (!list.some((c, index) => c.order !== index)) return;
    costCategoryAction(() => Promise.all(list
        .map((c, index) => ({ c, index }))
        .filter(({ c, index }) => c.order !== index)
        .map(({ c, index }) => apiFetch(`/api/costs/categories/${c.id}`, { method: 'PATCH', json: { order: index } }))));
}

// Arrastrar por el asa ⠿: la fila solo es arrastrable mientras se sujeta,
// para que se pueda seleccionar el texto del nombre
let draggedCategoryId = null;
const categoryDropIndicator = el('div', 'drop-indicator');

costsCategoryList.addEventListener('pointerdown', (event) => {
    const handle = event.target.closest('.config-drag');
    if (handle) handle.closest('.config-row').draggable = true;
});

costsCategoryList.addEventListener('dragstart', (event) => {
    const row = event.target.closest('.config-row');
    if (!row || !row.draggable) return;
    draggedCategoryId = Number(row.dataset.categoryId);
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', row.dataset.categoryId);
    row.classList.add('dragging');
});

function categoryRowBeforePointer(clientY) {
    return [...costsCategoryList.querySelectorAll('.config-row:not(.dragging)')].find(row => {
        const box = row.getBoundingClientRect();
        return clientY < box.top + box.height / 2;
    }) || null;
}

costsCategoryList.addEventListener('dragover', (event) => {
    if (draggedCategoryId === null) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
    const before = categoryRowBeforePointer(event.clientY);
    if (before) costsCategoryList.insertBefore(categoryDropIndicator, before);
    else costsCategoryList.appendChild(categoryDropIndicator);
});

costsCategoryList.addEventListener('drop', (event) => {
    if (draggedCategoryId === null) return;
    event.preventDefault();
    const before = categoryRowBeforePointer(event.clientY);
    const moved = costsState.categories.find(c => c.id === draggedCategoryId);
    const others = costsState.categories.filter(c => c.id !== draggedCategoryId);
    let index = before ? others.findIndex(c => c.id === Number(before.dataset.categoryId)) : others.length;
    if (index < 0) index = others.length;
    endCategoryDrag();
    saveCategoryOrder([...others.slice(0, index), moved, ...others.slice(index)]);
});

function endCategoryDrag() {
    draggedCategoryId = null;
    categoryDropIndicator.remove();
    costsCategoryList.querySelectorAll('.config-row').forEach(row => {
        row.draggable = false;
        row.classList.remove('dragging');
    });
}

costsCategoryList.addEventListener('dragend', endCategoryDrag);
// Soltar el asa sin arrastrar no debe dejar la fila arrastrable
document.addEventListener('pointerup', () => {
    if (draggedCategoryId === null) {
        costsCategoryList.querySelectorAll('.config-row[draggable="true"]').forEach(row => { row.draggable = false; });
    }
});

document.getElementById('costsCategoryForm').addEventListener('submit', (event) => {
    event.preventDefault();
    const name = document.getElementById('costsCategoryName');
    const color = document.getElementById('costsCategoryColor');
    if (!name.value.trim()) return;
    costCategoryAction(async () => {
        await apiFetch('/api/costs/categories', { method: 'POST', json: { name: name.value.trim(), color: color.value } });
        name.value = '';
    });
});

// ============================================
// Ciclo de vida
// ============================================

function resetCosts() {
    Object.assign(costsState, { summary: null, categories: [], projectId: null, costs: [], loaded: false, pending: null });
    hiddenBreakdown.clear();
    costsSummaryEl.replaceChildren();
    costsRows.replaceChildren();
    hideModal(costsImportModal);
    setViewVisible('costs', false);
    try { localStorage.removeItem(COSTS_PROJECT_KEY); } catch (error) { /* nada que limpiar */ }
}

window.appDataHooks.push(applyCostsModule);
window.modulesChangedHooks.push(() => {
    applyCostsModule();
    if (isCostsVisible()) loadCosts();
});
// Al entrar a la vista se pide de nuevo: el tiempo cambia desde Tableros
window.viewChangedHooks.push(viewId => {
    applyCostsWide();
    if (viewId === 'costs') loadCosts();
});
// Un proyecto nuevo, renombrado o con más tiempo: el resumen cambia
window.projectsChangedHooks.push(() => {
    if (isCostsVisible() && costsState.loaded) refreshCostsSummary();
});
// Al principio: ocultar la vista pasa por goToView(), que recuerda la pestaña,
// y el hook de projects.js (que corre después) es el que la olvida al salir
window.appLogoutHooks.unshift(resetCosts);
