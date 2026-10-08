// ============================================
// Costos: gastos repartidos y recurrentes (plan Maker, 1.24)
// ============================================
//
// Repartir un gasto entre proyectos de la misma moneda (PUT /api/costs/{id}/split)
// y la tarjeta "Gastos recurrentes" (/api/costs/recurring). El editor de reparto
// (allocationEditor) es el mismo en los dos. Usa costsState, loadCostRows,
// refreshCostsSummary, money2 y categoryOptions de costs.js, formatMoney de
// project-overview.js y el() de reports.js. El backend genera los cobros que ya
// llegaron cada vez que se pide la hoja, el resumen o esta lista.

const splitModal = document.getElementById('costSplitModal');
const splitError = document.getElementById('costSplitError');
const recurringModal = document.getElementById('recurringModal');
const recurringForm = document.getElementById('recurringForm');
const recurringFormError = document.getElementById('recurringFormError');
const recurringList = document.getElementById('recurringList');
const recurringError = document.getElementById('recurringError');

const recurringState = {
    list: [],
    splitCost: null,      // el gasto que se está repartiendo
    splitEditor: null,
    editing: null,        // el recurrente que se edita (null: uno nuevo)
    formEditor: null,
    fromCost: null,       // "Hacer recurrente": el gasto de la hoja del que sale
};

const FREQUENCY_LABEL = { monthly: 'Cada mes', yearly: 'Cada año' };

// Proyectos entre los que se puede repartir: activos (o el que ya está en el
// reparto) y de la moneda del gasto. "Sin asignar" no sale en el resumen.
function splitCandidates(currency, keepIds = []) {
    const projects = (costsState.summary && costsState.summary.projects) || [];
    return projects.filter(p => p.currency === currency && (p.is_active || keepIds.includes(p.project_id)));
}

// ============================================
// El editor de reparto: un proyecto por fila, con su %
// ============================================

function pctFromBp(bp) {
    return String(Math.round(bp) / 100);
}

function allocationEditor(projects, allocations) {
    const chosen = new Map(allocations.map(a => [a.project_id, a.bp]));
    const box = el('div', 'allocation-editor');
    const rows = projects.map(p => {
        const row = el('label', 'allocation-row');
        const check = document.createElement('input');
        check.type = 'checkbox';
        check.checked = chosen.has(p.project_id);
        const dot = el('i', 'report-bar-dot');
        if (p.color) dot.style.background = p.color;
        const name = el('span', 'allocation-name');
        name.append(dot, document.createTextNode(p.name));
        const pct = document.createElement('input');
        pct.type = 'number';
        pct.min = '0.01';
        pct.max = '100';
        pct.step = '0.01';
        pct.inputMode = 'decimal';
        pct.className = 'allocation-pct';
        pct.setAttribute('aria-label', `Porcentaje de ${p.name}`);
        pct.value = chosen.has(p.project_id) ? pctFromBp(chosen.get(p.project_id)) : '';
        pct.disabled = !check.checked;
        check.addEventListener('change', () => {
            pct.disabled = !check.checked;
            if (check.checked && !pct.value) pct.value = String(Math.max(0, Math.round((100 - sum()) * 100) / 100));
            paintSum();
            if (check.checked) pct.focus();
        });
        pct.addEventListener('input', paintSum);
        row.append(check, name, pct, el('span', 'allocation-unit', '%'));
        box.appendChild(row);
        return { project: p, check, pct };
    });
    const total = el('p', 'allocation-sum');
    box.appendChild(total);

    function sum() {
        return rows.filter(r => r.check.checked).reduce((acc, r) => acc + (Number(r.pct.value) || 0), 0);
    }

    function paintSum() {
        const value = Math.round(sum() * 100) / 100;
        total.textContent = `Suma: ${value} %${value === 100 ? ' ✓' : ' (tiene que ser 100 %)'}`;
        total.classList.toggle('negative', value !== 100);
    }
    paintSum();

    return {
        node: box,
        // [{project_id, bp}] o un Error con el motivo
        read() {
            const picked = rows.filter(r => r.check.checked)
                .map(r => ({ project_id: r.project.project_id, bp: Math.round((Number(r.pct.value) || 0) * 100) }));
            if (!picked.length) return new Error('Elige al menos un proyecto.');
            if (picked.some(a => a.bp < 1)) return new Error('Cada proyecto elegido necesita un porcentaje.');
            if (picked.reduce((acc, a) => acc + a.bp, 0) !== 10000) return new Error('Los porcentajes tienen que sumar 100 %.');
            return picked;
        },
    };
}

// ============================================
// Repartir un gasto
// ============================================

function openSplitDialog(cost) {
    recurringState.splitCost = cost;
    splitError.classList.add('hidden');
    const current = cost.split_with && cost.split_with.length
        ? cost.split_with.map(w => ({ project_id: w.project_id, bp: w.bp }))
        : [{ project_id: cost.project_id, bp: 10000 }];
    const projects = splitCandidates(costsState.currency, current.map(a => a.project_id));
    recurringState.splitEditor = allocationEditor(projects, current);
    const total = cost.group_total_cents ?? cost.total_cents;
    document.getElementById('costSplitSummary').textContent =
        `${cost.concept}: ${formatMoney(total, costsState.currency)} en total. Elige los proyectos y su parte; `
        + `solo salen los de la misma moneda (${costsState.currency}).`;
    document.getElementById('costSplitEditor').replaceChildren(recurringState.splitEditor.node);
    showModal(splitModal);
}

function closeSplitDialog() {
    hideModal(splitModal);
    recurringState.splitCost = null;
}

async function saveSplit() {
    const allocations = recurringState.splitEditor.read();
    if (allocations instanceof Error) {
        showError(splitError, allocations.message);
        return;
    }
    try {
        await apiFetch(`/api/costs/${recurringState.splitCost.id}/split`, { method: 'PUT', json: { allocations } });
        closeSplitDialog();
        await loadCostRows();
        refreshCostsSummary();
    } catch (error) {
        showError(splitError, error.message);
    }
}

document.getElementById('costSplitSave').addEventListener('click', saveSplit);
document.getElementById('costSplitCancel').addEventListener('click', closeSplitDialog);
document.getElementById('costSplitClose').addEventListener('click', closeSplitDialog);
splitModal.querySelector('.modal-overlay').addEventListener('click', closeSplitDialog);

// ============================================
// Gastos recurrentes: la lista
// ============================================

function dayText(key) {
    const d = dateFromKey(key);
    return `${d.getDate()} ${MONTH_SHORT[d.getMonth()]} ${d.getFullYear()}`;
}

function scheduleText(rc) {
    const d = dateFromKey(rc.start_date);
    if (rc.frequency === 'yearly') return `Cada año, el ${d.getDate()} de ${MONTH_NAMES[d.getMonth()]}`;
    return `Cada mes, el día ${d.getDate()}`;
}

function allocationText(allocations) {
    if (allocations.length === 1) return allocations[0].name;
    return allocations.map(a => `${a.name} ${pctFromBp(a.bp)} %`).join(' · ');
}

async function loadRecurringCosts() {
    if (!getToken() || !moduleEnabled('maker')) return;
    recurringError.classList.add('hidden');
    try {
        recurringState.list = (await apiFetch('/api/costs/recurring')).recurring;
    } catch (error) {
        showError(recurringError, error.message);
        return;
    }
    renderRecurringList();
}

function renderRecurringList() {
    if (!recurringState.list.length) {
        recurringList.replaceChildren(el('li', 'work-empty',
            'Aún no tienes gastos recurrentes. Agrega los que pagas cada mes o cada año (hosting, suscripciones, dominios): se anotan solos en su fecha.'));
        return;
    }
    recurringList.replaceChildren(...recurringState.list.map(rc => {
        const item = el('li', `recurring-item${rc.paused ? ' paused' : ''}`);
        item.dataset.id = String(rc.id);
        const text = el('div', 'recurring-text');
        const when = rc.paused ? 'En pausa' : (rc.next_date ? `Siguiente: ${dayText(rc.next_date)}` : 'Terminado');
        text.append(
            el('strong', '', `🔁 ${rc.concept} · ${formatMoney(rc.total_cents, rc.currency)}`),
            el('small', '', `${scheduleText(rc)} · ${when} · ${allocationText(rc.allocations)}`),
        );
        const actions = el('div', 'recurring-actions');
        const edit = el('button', 'link-btn', 'Editar');
        edit.type = 'button';
        edit.dataset.action = 'edit';
        const pause = el('button', 'link-btn', rc.paused ? 'Reanudar' : 'Pausar');
        pause.type = 'button';
        pause.dataset.action = 'pause';
        const remove = el('button', 'cost-delete', '×');
        remove.type = 'button';
        remove.dataset.action = 'delete';
        remove.title = 'Dejar de cobrarlo';
        remove.setAttribute('aria-label', `Borrar el recurrente ${rc.concept}`);
        actions.append(edit, pause, remove);
        item.append(text, actions);
        return item;
    }));
}

async function recurringAction(request) {
    recurringError.classList.add('hidden');
    try {
        await request();
    } catch (error) {
        showError(recurringError, error.message);
    }
    await loadRecurringCosts();
    await loadCostRows();
    refreshCostsSummary();
}

recurringList.addEventListener('click', async (event) => {
    const button = event.target.closest('[data-action]');
    if (!button) return;
    const rc = recurringState.list.find(r => String(r.id) === button.closest('.recurring-item').dataset.id);
    if (!rc) return;
    if (button.dataset.action === 'edit') openRecurringForm(rc);
    else if (button.dataset.action === 'pause') {
        recurringAction(() => apiFetch(`/api/costs/recurring/${rc.id}`, { method: 'PATCH', json: { paused: !rc.paused } }));
    } else if (button.dataset.action === 'delete') {
        const ok = await confirmDialog(`¿Dejar de cobrar "${rc.concept}"?`, { confirmLabel: 'Dejar de cobrarlo', danger: true });
        if (!ok) return;
        // Lo ya anotado: se queda (dejar de pagarlo) o se borra (se creó mal y se rehace)
        let deleteCosts = false;
        if (rc.last_charge) {
            deleteCosts = await confirmDialog(
                `¿Qué hago con los gastos que ya anotó (el último, el ${dayText(rc.last_charge)})? Si lo creaste con la fecha `
                + 'equivocada, bórralos y vuelve a crearlo; si solo dejas de pagarlo, consérvalos.',
                { title: 'Sus gastos anotados', confirmLabel: 'Borrarlos también', cancelLabel: 'Conservarlos', danger: true });
        }
        recurringAction(() => apiFetch(`/api/costs/recurring/${rc.id}${deleteCosts ? '?delete_costs=true' : ''}`,
            { method: 'DELETE' }));
    }
});

// ============================================
// Gastos recurrentes: crear y editar
// ============================================

// El mismo día del mes siguiente (el 31 cae en el último día de un mes corto),
// como lo calcula el backend
function nextMonthKey(key) {
    const d = dateFromKey(key);
    const last = new Date(d.getFullYear(), d.getMonth() + 2, 0).getDate();
    return getDateKey(new Date(d.getFullYear(), d.getMonth() + 1, Math.min(d.getDate(), last)));
}

// "Hacer recurrente" desde un gasto de la hoja: el formulario con sus datos y su
// reparto, y el primer cobro el mes siguiente (el de hoy ya está anotado)
function openRecurringFromCost(cost) {
    openRecurringForm(null, {
        category_id: cost.category_id, concept: cost.concept, quantity: cost.quantity,
        unit_cost_cents: cost.unit_cost_cents, note: cost.note, frequency: 'monthly',
        start_date: nextMonthKey(cost.cost_date), end_date: null, currency: costsState.currency,
        allocations: cost.split_with && cost.split_with.length
            ? cost.split_with.map(w => ({ project_id: w.project_id, bp: w.bp }))
            : [{ project_id: cost.project_id, bp: 10000 }],
    }, cost);
}

function openRecurringForm(rc = null, prefill = null, fromCost = null) {
    recurringState.editing = rc;
    recurringState.fromCost = fromCost;
    recurringFormError.classList.add('hidden');
    const f = recurringForm.elements;
    const src = rc || prefill;
    document.getElementById('recurringTitle').textContent = rc ? 'Editar gasto recurrente'
        : fromCost ? 'Hacer recurrente' : 'Nuevo gasto recurrente';
    document.getElementById('recurringFromHint').hidden = !fromCost;
    categoryOptions(f.category_id, src ? src.category_id : costsState.categories[costsState.categories.length - 1].id);
    f.concept.value = src ? src.concept : '';
    f.quantity.value = src ? String(src.quantity) : '1';
    f.unit_cost.value = src ? money2(src.unit_cost_cents) : '';
    f.frequency.value = src ? src.frequency : 'monthly';
    f.end_date.value = src && src.end_date ? src.end_date : '';
    f.note.value = src && src.note ? src.note : '';
    // Con cobros anotados, la fecha es la del siguiente cobro: se puede mover,
    // pero después del último ya anotado (el backend lo comprueba también)
    const charged = Boolean(rc && rc.last_charge);
    f.start_date.value = charged ? (rc.next_date || rc.start_date) : (src ? src.start_date : getDateKey(new Date()));
    f.start_date.min = charged ? addDaysKey(rc.last_charge, 1) : '';
    recurringState.shownStart = f.start_date.value;
    recurringState.shownFrequency = f.frequency.value;
    document.getElementById('recurringStartLabel').textContent = charged ? 'Siguiente cobro' : 'Primer cobro';
    document.getElementById('recurringLockedHint').hidden = !charged;
    // A qué cobros ya anotados se aplican los cambios (por defecto, a ninguno)
    document.getElementById('recurringApply').hidden = !charged;
    f.apply_to.value = 'future';
    paintApplyCurrent();
    paintRecurringWarning();

    const current = src ? src.allocations.map(a => ({ project_id: a.project_id, bp: a.bp }))
        : costsState.projectId ? [{ project_id: costsState.projectId, bp: 10000 }] : [];
    const currency = src ? src.currency : costsState.currency;
    recurringState.formEditor = allocationEditor(splitCandidates(currency, current.map(a => a.project_id)), current);
    document.getElementById('recurringCurrency').textContent =
        `Solo salen los proyectos en ${currency}: un gasto se reparte entre proyectos de la misma moneda.`;
    document.getElementById('recurringAllocations').replaceChildren(recurringState.formEditor.node);
    showModal(recurringModal);
    f.concept.focus();
}

function addDaysKey(key, days) {
    const d = dateFromKey(key);
    return getDateKey(new Date(d.getFullYear(), d.getMonth(), d.getDate() + days));
}

// Avisa, sin bloquear: un primer cobro en el mismo mes (o año) que el gasto del
// que sale, en otra fecha, lo anotaría dos veces; y uno en el pasado anota los
// cobros atrasados hasta hoy
function paintRecurringWarning() {
    const f = recurringForm.elements;
    const warning = document.getElementById('recurringWarning');
    const notes = [];
    const start = f.start_date.value;
    const cost = recurringState.fromCost;
    if (cost && start && start !== cost.cost_date) {
        const sameMonth = start.slice(0, 7) === cost.cost_date.slice(0, 7);
        const sameYear = start.slice(0, 4) === cost.cost_date.slice(0, 4);
        if (f.frequency.value === 'monthly' ? sameMonth : sameYear) {
            notes.push(`Ya está anotado este gasto el ${dayText(cost.cost_date)}: un cobro el ${dayText(start)} lo `
                + 'repetiría en el mismo periodo. Usa su misma fecha (cuenta como el primer cobro) o el periodo siguiente; '
                + 'si lo guardas así, puedes borrar después el que sobre.');
        }
    }
    const today = getDateKey(new Date());
    const editing = recurringState.editing;
    if (start && start < today && !(editing && editing.last_charge)) {
        notes.push(`El primer cobro ya pasó: se anotarán los cobros desde el ${dayText(start)} hasta hoy.`);
    }
    warning.textContent = notes.join(' ');
    warning.hidden = !notes.length;
}

// "Desde este mes (octubre)" o "Desde este año (2026)", según la frecuencia
function paintApplyCurrent() {
    const now = new Date();
    document.getElementById('recurringApplyCurrent').textContent = recurringForm.elements.frequency.value === 'yearly'
        ? `Desde este año (${now.getFullYear()}) en adelante`
        : `Desde este mes (${MONTH_NAMES[now.getMonth()]}) en adelante`;
}

recurringForm.elements.start_date.addEventListener('input', paintRecurringWarning);
recurringForm.elements.frequency.addEventListener('change', () => {
    paintRecurringWarning();
    paintApplyCurrent();
});

function closeRecurringForm() {
    hideModal(recurringModal);
    recurringState.editing = null;
    recurringState.fromCost = null;
}

recurringForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const f = recurringForm.elements;
    const allocations = recurringState.formEditor.read();
    if (allocations instanceof Error) {
        showError(recurringFormError, allocations.message);
        return;
    }
    const body = {
        category_id: Number(f.category_id.value),
        concept: f.concept.value.trim(),
        quantity: Number(f.quantity.value) || 1,
        unit_cost_cents: f.unit_cost.value === '' ? 0 : centsFromInput(f.unit_cost.value),
        end_date: f.end_date.value || null,
        note: f.note.value.trim() || null,
        allocations,
    };
    const rc = recurringState.editing;
    if (!rc || !rc.last_charge) {
        body.frequency = f.frequency.value;
        body.start_date = f.start_date.value;
    } else {
        // Con cobros anotados, solo si cambió: mover el siguiente cobro (o la
        // frecuencia) hace que la serie cuente desde esa fecha
        if (f.start_date.value !== recurringState.shownStart) body.start_date = f.start_date.value;
        if (f.frequency.value !== recurringState.shownFrequency) {
            body.frequency = f.frequency.value;
            body.start_date = f.start_date.value;
        }
    }
    if (!rc && recurringState.fromCost) body.from_cost_id = recurringState.fromCost.id;
    if (rc && rc.last_charge) body.apply_to = f.apply_to.value;
    try {
        await apiFetch(rc ? `/api/costs/recurring/${rc.id}` : '/api/costs/recurring',
            { method: rc ? 'PATCH' : 'POST', json: body });
        closeRecurringForm();
        await loadRecurringCosts();
        await loadCostRows();
        refreshCostsSummary();
    } catch (error) {
        showError(recurringFormError, error.message);
    }
});

document.getElementById('recurringAdd').addEventListener('click', () => openRecurringForm());
document.getElementById('recurringCancel').addEventListener('click', closeRecurringForm);
document.getElementById('recurringClose').addEventListener('click', closeRecurringForm);
recurringModal.querySelector('.modal-overlay').addEventListener('click', closeRecurringForm);

document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    if (!splitModal.classList.contains('hidden')) closeSplitDialog();
    else if (!recurringModal.classList.contains('hidden')) closeRecurringForm();
});

window.appLogoutHooks.push(() => {
    recurringState.list = [];
    recurringList.replaceChildren();
    closeSplitDialog();
    closeRecurringForm();
});
