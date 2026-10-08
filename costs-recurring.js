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
        const ok = await confirmDialog(`¿Dejar de cobrar "${rc.concept}"? Los gastos que ya generó se quedan en la hoja.`,
            { confirmLabel: 'Dejar de cobrarlo', danger: true });
        if (ok) recurringAction(() => apiFetch(`/api/costs/recurring/${rc.id}`, { method: 'DELETE' }));
    }
});

// ============================================
// Gastos recurrentes: crear y editar
// ============================================

function openRecurringForm(rc = null) {
    recurringState.editing = rc;
    recurringFormError.classList.add('hidden');
    const f = recurringForm.elements;
    document.getElementById('recurringTitle').textContent = rc ? 'Editar gasto recurrente' : 'Nuevo gasto recurrente';
    categoryOptions(f.category_id, rc ? rc.category_id : costsState.categories[costsState.categories.length - 1].id);
    f.concept.value = rc ? rc.concept : '';
    f.quantity.value = rc ? String(rc.quantity) : '1';
    f.unit_cost.value = rc ? money2(rc.unit_cost_cents) : '';
    f.frequency.value = rc ? rc.frequency : 'monthly';
    f.start_date.value = rc ? rc.start_date : getDateKey(new Date());
    f.end_date.value = rc && rc.end_date ? rc.end_date : '';
    f.note.value = rc && rc.note ? rc.note : '';
    // Con cobros hechos, el primer cobro y la frecuencia quedan fijos
    const locked = Boolean(rc && rc.generated);
    f.start_date.disabled = locked;
    f.frequency.disabled = locked;
    document.getElementById('recurringLockedHint').hidden = !locked;

    const current = rc ? rc.allocations.map(a => ({ project_id: a.project_id, bp: a.bp }))
        : costsState.projectId ? [{ project_id: costsState.projectId, bp: 10000 }] : [];
    const currency = rc ? rc.currency : costsState.currency;
    recurringState.formEditor = allocationEditor(splitCandidates(currency, current.map(a => a.project_id)), current);
    document.getElementById('recurringCurrency').textContent =
        `Solo salen los proyectos en ${currency}: un gasto se reparte entre proyectos de la misma moneda.`;
    document.getElementById('recurringAllocations').replaceChildren(recurringState.formEditor.node);
    showModal(recurringModal);
    f.concept.focus();
}

function closeRecurringForm() {
    hideModal(recurringModal);
    recurringState.editing = null;
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
    if (!rc || !rc.generated) {
        body.frequency = f.frequency.value;
        body.start_date = f.start_date.value;
    }
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
