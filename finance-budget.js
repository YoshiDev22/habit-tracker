// ============================================
// Finanzas: el presupuesto del mes. El ingreso que esperas y lo que piensas
// gastar, en grupos con su parte del ingreso (de una referencia, como 50/30/20, o
// los tuyos). Es solo el plan: nada de aquí crea movimientos. Un renglón puede
// volverse fijo (ese sí se anota solo cada mes) o quedarse como estimación.
// Usa finance-app.js (estado, hojas, formato) y la API /api/finance/budget.
// ============================================

// editing: el ✎ de arriba (cambiar de lugar); pick: lo primero que se tocó, { type, id }
const finBudget = { groups: [], items: [], loaded: false, loading: null, editing: false, pick: null, drag: null };
// Arrastrar, solo con ratón (como el tablero de la app) y con el ✎ puesto
const FIN_BUDGET_CAN_DRAG = window.matchMedia('(hover: hover) and (pointer: fine)');
const finBudgetItemSheet = document.getElementById('finBudgetItemSheet');
const finBudgetGroupSheet = document.getElementById('finBudgetGroupSheet');
const finBudgetForm = { item: null, kind: 'expense', groupId: null, fixed: false };
let finBudgetGroupEditing = null;

const FIN_BUDGET_REFERENCE = 'La regla 50/30/20 la popularizaron Elizabeth Warren y Amelia Warren Tyagi '
    + '(All Your Worth, 2005): del ingreso neto, 50 % para necesidades, 30 % para gustos y 20 % para '
    + 'ahorro y deudas. Es un punto de partida: cambia los nombres y porcentajes, o agrega tus grupos.';

function finBudgetMoney(cents) {
    return formatMoney(cents, finMainCurrency());
}

// Lo que un fijo cuesta al mes: la quincenal, dos veces; la anual, entre doce
function finRecurringMonthly(rc) {
    if (rc.frequency === 'semimonthly') return rc.amount_cents * 2;
    if (rc.frequency === 'yearly') return Math.round(rc.amount_cents / 12);
    return rc.amount_cents;
}

async function finLoadBudget() {
    if (finBudget.loading) return finBudget.loading;
    finBudget.loading = (async () => {
        try {
            const data = await apiFetch('/api/finance/budget');
            finBudget.groups = data.groups;
            finBudget.items = data.items;
            finBudget.loaded = true;
            await finBudgetStartIncome();
        } finally {
            finBudget.loading = null;
        }
    })();
    return finBudget.loading;
}

// La primera vez, el ingreso empieza con lo que dijiste en "¿Cuánto cobras?"
async function finBudgetStartIncome() {
    if (finBudget.groups.length || finBudget.items.length) return;
    const salary = finSalaryFixed();
    if (!salary) return;
    const saved = await apiFetch('/api/finance/budget/items', { method: 'POST', json: {
        kind: 'income', name: salary.concept.slice(0, 80), amount_cents: finRecurringMonthly(salary),
        category_id: salary.category_id,
    } });
    finBudget.items.push(saved);
}

async function finRenderBudget() {
    const box = document.getElementById('finBudget');
    const errorEl = document.getElementById('finBudgetError');
    if (!finBudget.loaded) {
        try {
            await finLoadBudget();
        } catch (error) {
            showError(errorEl, error.message || 'No se pudo cargar el presupuesto.');
            return;
        }
    }
    errorEl.classList.add('hidden');
    if (finState.tab !== 'budget') return;
    if (!finBudget.groups.length) finBudget.editing = false;
    box.classList.toggle('editing', finBudget.editing);
    box.replaceChildren(...finBudgetBody());
    const edit = document.getElementById('finBudgetEdit');
    edit.hidden = !finBudget.groups.length;
    edit.replaceChildren(financeIcon(finBudget.editing ? 'check' : 'pencil', 18));
    edit.setAttribute('aria-pressed', String(finBudget.editing));
    edit.setAttribute('aria-label', finBudget.editing ? 'Listo' : 'Ordenar el presupuesto');
    edit.title = edit.getAttribute('aria-label');
    document.getElementById('finBudgetHint').hidden = !finBudget.editing;
}

function finBudgetStopEditing() {
    finBudget.editing = false;
    finBudget.pick = null;
    document.getElementById('finBudgetEdit').hidden = true;
    document.getElementById('finBudgetHint').hidden = true;
}

function finBudgetPicked(type, id) {
    return Boolean(finBudget.pick && finBudget.pick.type === type && finBudget.pick.id === id);
}

function finBudgetIncome() {
    return finBudget.items.filter(i => i.kind === 'income').reduce((acc, i) => acc + i.amount_cents, 0);
}

function finBudgetPlanned(groupId) {
    return finBudget.items.filter(i => i.kind === 'expense' && (groupId == null || i.group_id === groupId))
        .reduce((acc, i) => acc + i.amount_cents, 0);
}

// Un renglón: nombre (con su nota y 🔁 si es fijo) y monto
function finBudgetRow(item) {
    const row = el('button', 'fin-budget-row');
    row.type = 'button';
    row.dataset.budgetItem = String(item.id);
    if (finBudgetPicked('item', item.id)) row.classList.add('picked');
    row.draggable = finBudgetDraggable();
    const text = el('span', 'fin-budget-row-text');
    const name = el('span', '', item.name);
    if (item.recurring_id) name.prepend(financeIcon('repeat', 14));
    text.appendChild(name);
    const sub = [item.note, item.recurring_id ? 'fijo' : ''].filter(Boolean).join(' · ');
    if (sub) text.appendChild(el('small', '', sub));
    row.append(text, el('span', 'fin-budget-row-amount', finBudgetMoney(item.amount_cents)));
    return row;
}

function finBudgetAddButton(label, data, className = 'link-btn fin-budget-add') {
    const button = el('button', className, label);
    button.type = 'button';
    Object.entries(data).forEach(([key, value]) => { button.dataset[key] = value; });
    return button;
}

function finBudgetIncomeCard() {
    const card = el('section', 'fin-card fin-budget-card');
    card.dataset.budgetIncomeCard = '1';
    const head = el('div', 'fin-budget-head');
    head.append(el('h2', 'fin-card-title', 'Ingreso mensual'), el('strong', '', finBudgetMoney(finBudgetIncome())));
    card.appendChild(head);
    card.appendChild(el('p', 'fin-hint', 'Lo que esperas que entre cada mes. Es tu plan: no cambia tus ingresos reales.'));
    finBudget.items.filter(i => i.kind === 'income').forEach(i => card.appendChild(finBudgetRow(i)));
    if (!finBudget.editing) card.appendChild(finBudgetAddButton('+ Ingreso', { budgetAdd: 'income' }));
    return card;
}

// Arriba, el ingreso y la tabla del plan; debajo, la cuadrícula de grupos
function finBudgetBody() {
    const top = el('div', 'fin-budget-top');
    top.appendChild(finBudgetIncomeCard());
    if (!finBudget.groups.length) {
        const empty = el('section', 'fin-card fin-budget-card');
        empty.append(el('h2', 'fin-card-title', 'Reparte tu ingreso'),
            el('p', 'fin-hint', 'Haz grupos con la parte de tu ingreso que va a cada cosa (necesidades, ahorro, '
                + 'gustos…) y anota en cada uno lo que cuesta vivir al mes.'),
            el('p', 'fin-hint', FIN_BUDGET_REFERENCE));
        const actions = el('div', 'fin-form-actions');
        const blank = el('button', 'link-btn', 'Empezar en blanco');
        blank.type = 'button';
        blank.dataset.budgetGroupNew = '1';
        const reference = el('button', 'submit-btn', 'Empezar con 50/30/20');
        reference.type = 'button';
        reference.dataset.budgetTemplate = '50-30-20';
        actions.append(blank, reference);
        empty.appendChild(actions);
        top.appendChild(empty);
        return [top];
    }
    top.appendChild(finBudgetSummaryCard());
    const grid = el('div', 'fin-budget-grid');
    finBudget.groups.forEach(group => grid.appendChild(finBudgetGroupCard(group)));
    if (!finBudget.editing) grid.appendChild(finBudgetAddButton('+ Grupo', { budgetGroupNew: '1' }, 'fin-card fin-budget-new-group'));
    const loose = finBudgetLooseFixed();
    return loose ? [top, grid, loose] : [top, grid];
}

// La tabla de arriba: cada grupo con su %, lo teórico (% del ingreso) y lo planeado
function finBudgetSummaryCard() {
    const income = finBudgetIncome();
    const card = el('section', 'fin-card fin-budget-card');
    card.appendChild(el('h2', 'fin-card-title', 'Tu plan del mes'));
    const table = el('table', 'fin-budget-table');
    const head = el('tr');
    ['Grupo', '%', 'Teórico', 'Planeado'].forEach(text => head.appendChild(el('th', '', text)));
    table.appendChild(head);
    let percent = 0;
    finBudget.groups.forEach(group => {
        percent += group.percent_bp;
        const tr = el('tr');
        [group.name, finBudgetPercent(group.percent_bp), finBudgetMoney(Math.round(income * group.percent_bp / 10000)),
            finBudgetMoney(finBudgetPlanned(group.id))].forEach(text => tr.appendChild(el('td', '', text)));
        table.appendChild(tr);
    });
    const planned = finBudgetPlanned(null);
    const total = el('tr', 'total');
    ['Total', finBudgetPercent(percent), finBudgetMoney(Math.round(income * percent / 10000)), finBudgetMoney(planned)]
        .forEach(text => total.appendChild(el('td', '', text)));
    table.appendChild(total);
    card.appendChild(table);
    const left = income - planned;
    const free = el('div', 'fin-budget-free');
    free.append(el('span', '', left >= 0 ? 'Dinero disponible' : 'Te falta'),
        el('strong', left >= 0 ? '' : 'short', finBudgetMoney(Math.abs(left))));
    card.appendChild(free);
    if (percent !== 10000) {
        card.appendChild(el('p', 'fin-hint', `Tus grupos suman ${finBudgetPercent(percent)} de tu ingreso.`));
    }
    return card;
}

function finBudgetPercent(bp) {
    return `${Number((bp / 100).toFixed(2))} %`;
}

function finBudgetGroupCard(group) {
    const income = finBudgetIncome();
    const card = el('section', 'fin-card fin-budget-card fin-budget-group');
    card.dataset.budgetGroupCard = String(group.id);
    card.draggable = finBudgetDraggable();
    if (finBudgetPicked('group', group.id)) card.classList.add('picked');
    const head = el('button', 'fin-budget-group-head');
    head.type = 'button';
    head.dataset.budgetGroup = String(group.id);
    const title = el('span', 'fin-budget-group-title');
    title.append(el('strong', '', group.name),
        el('small', '', `${finBudgetPercent(group.percent_bp)} · teórico ${finBudgetMoney(Math.round(income * group.percent_bp / 10000))}`));
    head.append(title, el('strong', '', finBudgetMoney(finBudgetPlanned(group.id))));
    if (!finBudget.editing) head.appendChild(financeIcon('pencil', 16));
    card.appendChild(head);
    finBudget.items.filter(i => i.kind === 'expense' && i.group_id === group.id)
        .forEach(i => card.appendChild(finBudgetRow(i)));
    if (!finBudget.editing) card.appendChild(finBudgetAddButton('+ Agregar', { budgetAdd: 'expense', group: String(group.id) }));
    return card;
}

// Los fijos de gasto que aún no están en el presupuesto: se meten a un grupo
function finBudgetLooseFixed() {
    const linked = new Set(finBudget.items.map(i => i.recurring_id).filter(Boolean));
    const loose = finState.recurring.filter(rc => rc.kind === 'expense' && !rc.paused && !linked.has(rc.id));
    if (!loose.length) return null;
    const card = el('section', 'fin-card fin-budget-card');
    card.append(el('h2', 'fin-card-title', 'Fijos sin presupuesto'),
        el('p', 'fin-hint', 'Ya se anotan solos; ponlos en un grupo para que cuenten en tu plan.'));
    loose.forEach(rc => {
        const row = el('div', 'fin-budget-loose');
        const text = el('span', 'fin-budget-row-text');
        text.append(el('span', '', rc.concept), el('small', '', `${finBudgetMoney(finRecurringMonthly(rc))} al mes`));
        const select = el('select', 'fin-import-input');
        select.dataset.budgetLoose = String(rc.id);
        select.setAttribute('aria-label', `Grupo para ${rc.concept}`);
        const first = el('option', '', 'Agregar a…');
        first.value = '';
        select.appendChild(first);
        finBudget.groups.forEach(g => {
            const option = el('option', '', g.name);
            option.value = String(g.id);
            select.appendChild(option);
        });
        row.append(text, select);
        card.appendChild(row);
    });
    return card;
}

// ---------- La hoja de un renglón ----------

function openFinBudgetItem({ item = null, kind = 'expense', groupId = null } = {}) {
    Object.assign(finBudgetForm, { item, kind: item ? item.kind : kind, groupId: item ? item.group_id : groupId, fixed: false });
    const income = finBudgetForm.kind === 'income';
    const group = finBudget.groups.find(g => g.id === finBudgetForm.groupId);
    document.getElementById('finBudgetItemTitle').textContent = item ? item.name
        : income ? 'Nuevo ingreso' : `Agregar a ${group ? group.name : 'un grupo'}`;
    document.getElementById('finBudgetItemName').value = item ? item.name : '';
    document.getElementById('finBudgetItemName').placeholder = income ? 'Sueldo' : 'Renta';
    document.getElementById('finBudgetItemAmount').value = item ? (item.amount_cents / 100).toFixed(2) : '';
    document.getElementById('finBudgetItemNote').value = item && item.note ? item.note : '';
    document.getElementById('finBudgetItemGroupField').hidden = income;
    const groupSelect = document.getElementById('finBudgetItemGroup');
    groupSelect.replaceChildren(...finBudget.groups.map(g => {
        const option = el('option', '', g.name);
        option.value = String(g.id);
        return option;
    }));
    if (finBudgetForm.groupId) groupSelect.value = String(finBudgetForm.groupId);
    const categorySelect = document.getElementById('finBudgetItemCategory');
    const none = el('option', '', 'Sin categoría');
    none.value = '';
    categorySelect.replaceChildren(none, ...finState.categories.filter(c => c.kind === finBudgetForm.kind).map(c => {
        const option = el('option', '', c.name);
        option.value = String(c.id);
        return option;
    }));
    categorySelect.value = item && item.category_id ? String(item.category_id) : '';
    const rc = item && item.recurring_id ? finState.recurring.find(r => r.id === item.recurring_id) : null;
    document.getElementById('finBudgetItemStatus').textContent = rc
        ? `Es fijo: se anota solo (${rc.concept}, ${finBudgetMoney(rc.amount_cents)}). Cámbialo en Ajustes › Fijos.`
        : income ? 'Solo es tu plan: no se anota en tus movimientos.'
            : 'Es una estimación: no se anota en tus movimientos. Si es un pago seguro cada mes, hazlo fijo.';
    document.getElementById('finBudgetItemFixed').hidden = income || Boolean(rc);
    document.getElementById('finBudgetFixedBox').hidden = true;
    document.getElementById('finBudgetItemDelete').hidden = !item;
    document.getElementById('finBudgetItemError').classList.add('hidden');
    openFinSheet(finBudgetItemSheet);
    document.getElementById('finBudgetItemName').focus();
}

document.getElementById('finBudgetItemFixed').addEventListener('click', () => {
    finBudgetForm.fixed = true;
    const accounts = finActiveAccounts();
    document.getElementById('finBudgetFixedAccount').replaceChildren(...accounts.map(a => {
        const option = el('option', '', a.name);
        option.value = String(a.id);
        return option;
    }));
    document.getElementById('finBudgetFixedDate').value = finToday();
    document.getElementById('finBudgetFixedBox').hidden = false;
    document.getElementById('finBudgetItemFixed').hidden = true;
});

document.getElementById('finBudgetItemForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    const errorEl = document.getElementById('finBudgetItemError');
    errorEl.classList.add('hidden');
    const { item, kind } = finBudgetForm;
    const name = document.getElementById('finBudgetItemName').value.trim();
    const amountText = document.getElementById('finBudgetItemAmount').value.trim();
    const amount = amountText ? parseMoneyCents(amountText) : 0;
    const note = document.getElementById('finBudgetItemNote').value.trim();
    const categoryValue = document.getElementById('finBudgetItemCategory').value;
    const categoryId = categoryValue ? Number(categoryValue) : null;
    if (!name) return showError(errorEl, 'Escribe el nombre.');
    if (amount == null || amount < 0) return showError(errorEl, 'Escribe el monto al mes: solo números.');
    const payload = { name, amount_cents: amount, note: note || null, category_id: categoryId };
    if (kind === 'expense') payload.group_id = Number(document.getElementById('finBudgetItemGroup').value);
    try {
        // Hacer fijo: primero el fijo (con su categoría), luego el renglón lo enlaza
        if (finBudgetForm.fixed) {
            if (!categoryId) return showError(errorEl, 'Elige la categoría del fijo: así se anota en tus gastos.');
            if (!amount) return showError(errorEl, 'Un fijo necesita su monto.');
            const rc = await apiFetch('/api/finance/recurring', { method: 'POST', json: {
                kind: 'expense', account_id: Number(document.getElementById('finBudgetFixedAccount').value),
                category_id: categoryId, concept: name.slice(0, 200), amount_cents: amount,
                start_date: document.getElementById('finBudgetFixedDate').value || finToday(),
            } });
            payload.recurring_id = rc.id;
        }
        if (item) {
            const rc = item.recurring_id ? finState.recurring.find(r => r.id === item.recurring_id) : null;
            await apiFetch(`/api/finance/budget/items/${item.id}`, { method: 'PATCH', json: payload });
            // Un fijo mensual con otro monto: ¿también el fijo, desde el siguiente cobro?
            if (rc && rc.frequency === 'monthly' && amount && amount !== rc.amount_cents
                && await confirmDialog(`¿Cambiar también el fijo "${rc.concept}" a ${finBudgetMoney(amount)} desde el siguiente cobro?`,
                    { confirmLabel: 'Cambiar el fijo' })) {
                await apiFetch(`/api/finance/recurring/${rc.id}`, { method: 'PATCH', json: { amount_cents: amount } });
            }
        } else {
            await apiFetch('/api/finance/budget/items', { method: 'POST', json: { ...payload, kind } });
        }
        closeFinSheet(finBudgetItemSheet);
        await finBudgetRefresh();
    } catch (error) {
        showError(errorEl, error.message);
    }
});

document.getElementById('finBudgetItemDelete').addEventListener('click', async () => {
    const { item } = finBudgetForm;
    if (!item) return;
    const fixed = item.recurring_id ? ' Su fijo sigue anotándose (quítalo en Ajustes › Fijos si ya no va).' : '';
    if (!(await confirmDialog(`¿Quitar "${item.name}" del presupuesto?${fixed}`, { confirmLabel: 'Quitar' }))) return;
    try {
        await apiFetch(`/api/finance/budget/items/${item.id}`, { method: 'DELETE' });
        closeFinSheet(finBudgetItemSheet);
        await finBudgetRefresh();
    } catch (error) {
        showError(document.getElementById('finBudgetItemError'), error.message);
    }
});

// ---------- La hoja de un grupo ----------

function openFinBudgetGroup(group = null) {
    finBudgetGroupEditing = group;
    document.getElementById('finBudgetGroupTitle').textContent = group ? group.name : 'Nuevo grupo';
    document.getElementById('finBudgetGroupName').value = group ? group.name : '';
    document.getElementById('finBudgetGroupPercent').value = group ? String(group.percent_bp / 100) : '';
    document.getElementById('finBudgetGroupDelete').hidden = !group;
    document.getElementById('finBudgetGroupError').classList.add('hidden');
    openFinSheet(finBudgetGroupSheet);
    document.getElementById('finBudgetGroupName').focus();
}

document.getElementById('finBudgetGroupForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    const errorEl = document.getElementById('finBudgetGroupError');
    const name = document.getElementById('finBudgetGroupName').value.trim();
    const percentText = document.getElementById('finBudgetGroupPercent').value.trim().replace(',', '.').replace('%', '');
    const percent = percentText ? Number(percentText) : 0;
    if (!name) return showError(errorEl, 'Escribe el nombre del grupo.');
    if (!Number.isFinite(percent) || percent < 0 || percent > 100) return showError(errorEl, 'El porcentaje va de 0 a 100.');
    const payload = { name, percent_bp: Math.round(percent * 100) };
    try {
        if (finBudgetGroupEditing) {
            await apiFetch(`/api/finance/budget/groups/${finBudgetGroupEditing.id}`, { method: 'PATCH', json: payload });
        } else {
            await apiFetch('/api/finance/budget/groups', { method: 'POST', json: payload });
        }
        closeFinSheet(finBudgetGroupSheet);
        await finBudgetRefresh();
    } catch (error) {
        showError(errorEl, error.message);
    }
});

document.getElementById('finBudgetGroupDelete').addEventListener('click', async () => {
    const group = finBudgetGroupEditing;
    if (!group) return;
    const count = finBudget.items.filter(i => i.group_id === group.id).length;
    const lines = count ? ` Se quita también lo que tiene (${count}); los fijos siguen anotándose.` : '';
    if (!(await confirmDialog(`¿Quitar el grupo "${group.name}"?${lines}`, { confirmLabel: 'Quitar' }))) return;
    try {
        await apiFetch(`/api/finance/budget/groups/${group.id}`, { method: 'DELETE' });
        closeFinSheet(finBudgetGroupSheet);
        await finBudgetRefresh();
    } catch (error) {
        showError(document.getElementById('finBudgetGroupError'), error.message);
    }
});

// ---------- La pestaña ----------

// Después de un cambio: el presupuesto otra vez, y los fijos (uno nuevo, o un monto)
async function finBudgetRefresh() {
    finBudget.loaded = false;
    try {
        finState.recurring = (await apiFetch('/api/finance/recurring')).recurring;
    } catch (error) { /* se quedan los de antes */ }
    await finRenderBudget();
}

// ---------- Cambiar de lugar (el ✎ de arriba) ----------

document.getElementById('finBudgetEdit').addEventListener('click', () => {
    finBudget.editing = !finBudget.editing;
    finBudget.pick = null;
    finRenderBudget();
});

// Lo segundo que se toca cambia de lugar con lo primero: dos grupos, o dos gastos
// (de un grupo a otro, también) o dos ingresos. Cada uno se queda con el orden del otro.
async function finBudgetEditTap(target) {
    const groupEl = target.closest('[data-budget-group]');
    const itemEl = target.closest('[data-budget-item]');
    const tapped = itemEl ? { type: 'item', id: Number(itemEl.dataset.budgetItem) }
        : groupEl ? { type: 'group', id: Number(groupEl.dataset.budgetGroup) } : null;
    if (!tapped) return;
    const first = finBudget.pick;
    const list = tapped.type === 'group' ? finBudget.groups : finBudget.items;
    const a = first && first.type === tapped.type ? list.find(x => x.id === first.id) : null;
    const b = list.find(x => x.id === tapped.id);
    // Lo mismo otra vez lo suelta; algo de otra clase (un ingreso y un gasto) empieza de nuevo
    if (!a || a.id === b.id || (tapped.type === 'item' && a.kind !== b.kind)) {
        finBudget.pick = a && a.id === b.id ? null : tapped;
        finRenderBudget();
        return;
    }
    finBudget.pick = null;
    const path = tapped.type === 'group' ? 'groups' : 'items';
    const changes = [[a, { order: b.order }], [b, { order: a.order }]];
    if (tapped.type === 'item' && a.group_id !== b.group_id) {
        changes[0][1].group_id = b.group_id;
        changes[1][1].group_id = a.group_id;
    }
    try {
        for (const [row, body] of changes) {
            await apiFetch(`/api/finance/budget/${path}/${row.id}`, { method: 'PATCH', json: body });
        }
    } catch (error) {
        showError(document.getElementById('finBudgetError'), error.message);
    }
    await finBudgetRefresh();
}

function finBudgetDraggable() {
    return finBudget.editing && FIN_BUDGET_CAN_DRAG.matches;
}

// Guarda un orden nuevo: cada uno toma, en su lugar, uno de los órdenes que ya tenían
// entre todos (así no choca con los de otros grupos). Solo manda lo que cambió.
async function finBudgetSaveOrder(path, rows, moved = null, groupId = null) {
    const orders = rows.map(r => r.order).sort((a, b) => a - b);
    for (const [i, row] of rows.entries()) {
        const body = {};
        if (row.order !== orders[i]) body.order = orders[i];
        if (row === moved && groupId != null && row.group_id !== groupId) body.group_id = groupId;
        if (Object.keys(body).length) await apiFetch(`/api/finance/budget/${path}/${row.id}`, { method: 'PATCH', json: body });
    }
}

// Soltar lo arrastrado: un grupo cae en el lugar de otro; un gasto, antes del gasto
// donde se suelta (o al final del grupo, soltado en la tarjeta); un ingreso, entre ingresos
function finBudgetDropPlan(target) {
    const drag = finBudget.drag;
    if (!drag) return null;
    if (drag.type === 'group') {
        const card = target.closest('[data-budget-group-card]');
        const id = card ? Number(card.dataset.budgetGroupCard) : null;
        return id && id !== drag.id ? { el: card, id } : null;
    }
    const item = finBudget.items.find(i => i.id === drag.id);
    const rowEl = target.closest('[data-budget-item]');
    const over = rowEl ? finBudget.items.find(i => i.id === Number(rowEl.dataset.budgetItem)) : null;
    if (over) return over.id !== item.id && over.kind === item.kind ? { el: rowEl, over } : null;
    const card = item.kind === 'income' ? target.closest('[data-budget-income-card]') : target.closest('[data-budget-group-card]');
    return card ? { el: card, groupId: item.kind === 'income' ? null : Number(card.dataset.budgetGroupCard) } : null;
}

async function finBudgetDrop(plan) {
    const drag = finBudget.drag;
    try {
        if (drag.type === 'group') {
            const rows = finBudget.groups.slice();
            const from = rows.findIndex(g => g.id === drag.id);
            const to = rows.findIndex(g => g.id === plan.id);
            rows.splice(to, 0, ...rows.splice(from, 1));
            await finBudgetSaveOrder('groups', rows);
        } else {
            const item = finBudget.items.find(i => i.id === drag.id);
            const groupId = plan.over ? plan.over.group_id : plan.groupId;
            const rows = finBudget.items.filter(i => i.kind === item.kind && i.group_id === groupId && i.id !== item.id);
            const sameGroup = item.group_id === groupId;
            let at = plan.over ? rows.indexOf(plan.over) : rows.length;
            // En el mismo grupo, hacia abajo queda después del que estaba ahí
            if (plan.over && sameGroup) {
                const list = finBudget.items.filter(i => i.kind === item.kind && i.group_id === groupId);
                if (list.indexOf(item) < list.indexOf(plan.over)) at += 1;
            }
            rows.splice(at, 0, item);
            await finBudgetSaveOrder('items', rows, item, item.kind === 'income' ? null : groupId);
        }
    } catch (error) {
        showError(document.getElementById('finBudgetError'), error.message);
    }
    await finBudgetRefresh();
}

function finBudgetClearDrop() {
    document.querySelectorAll('#finBudget .drop-target').forEach(x => x.classList.remove('drop-target'));
}

const finBudgetBox = document.getElementById('finBudget');
finBudgetBox.addEventListener('dragstart', (event) => {
    if (!finBudgetDraggable()) return;
    const itemEl = event.target.closest('[data-budget-item]');
    const groupEl = event.target.closest('[data-budget-group-card]');
    finBudget.drag = itemEl ? { type: 'item', id: Number(itemEl.dataset.budgetItem) }
        : groupEl ? { type: 'group', id: Number(groupEl.dataset.budgetGroupCard) } : null;
    if (!finBudget.drag) return;
    finBudget.pick = null;
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', '');   // Firefox no arrastra sin datos
    (itemEl || groupEl).classList.add('dragging');
});
finBudgetBox.addEventListener('dragover', (event) => {
    const plan = finBudgetDropPlan(event.target);
    finBudgetClearDrop();
    if (!plan) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
    plan.el.classList.add('drop-target');
});
finBudgetBox.addEventListener('drop', (event) => {
    const plan = finBudgetDropPlan(event.target);
    finBudgetClearDrop();
    if (!plan) return;
    event.preventDefault();
    finBudgetDrop(plan);   // lee lo arrastrado antes de su primer await
});
finBudgetBox.addEventListener('dragend', () => {
    finBudget.drag = null;
    finBudgetClearDrop();
    document.querySelectorAll('#finBudget .dragging').forEach(x => x.classList.remove('dragging'));
});

document.getElementById('finBudget').addEventListener('click', async (event) => {
    const errorEl = document.getElementById('finBudgetError');
    if (finBudget.editing) {
        finBudgetEditTap(event.target);
        return;
    }
    const row = event.target.closest('[data-budget-item]');
    if (row) {
        const item = finBudget.items.find(i => i.id === Number(row.dataset.budgetItem));
        if (item) openFinBudgetItem({ item });
        return;
    }
    const add = event.target.closest('[data-budget-add]');
    if (add) {
        openFinBudgetItem({ kind: add.dataset.budgetAdd, groupId: add.dataset.group ? Number(add.dataset.group) : null });
        return;
    }
    const head = event.target.closest('[data-budget-group]');
    if (head) {
        openFinBudgetGroup(finBudget.groups.find(g => g.id === Number(head.dataset.budgetGroup)) || null);
        return;
    }
    if (event.target.closest('[data-budget-group-new]')) {
        openFinBudgetGroup(null);
        return;
    }
    const template = event.target.closest('[data-budget-template]');
    if (template) {
        try {
            await apiFetch('/api/finance/budget/template', { method: 'POST', json: { template: template.dataset.budgetTemplate } });
            await finBudgetRefresh();
        } catch (error) {
            showError(errorEl, error.message);
        }
    }
});

document.getElementById('finBudget').addEventListener('change', async (event) => {
    const select = event.target.closest('[data-budget-loose]');
    if (!select || !select.value) return;
    const rc = finState.recurring.find(r => r.id === Number(select.dataset.budgetLoose));
    if (!rc) return;
    try {
        await apiFetch('/api/finance/budget/items', { method: 'POST', json: {
            kind: 'expense', group_id: Number(select.value), name: rc.concept.slice(0, 80),
            amount_cents: finRecurringMonthly(rc), category_id: rc.category_id, recurring_id: rc.id,
        } });
        await finBudgetRefresh();
    } catch (error) {
        showError(document.getElementById('finBudgetError'), error.message);
    }
});
