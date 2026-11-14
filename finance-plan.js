// ============================================
// Finanzas: el plan de pagos del mes (Presupuesto › Pagos del mes, Finanzas 0.9).
// Por fecha, lo que hay que pagar (tarjetas, préstamos, fijos) y lo que entra, con
// cuánto te va quedando; al final, los aproximados del presupuesto que tú eliges.
// El monto que cambies aquí es solo de ese mes: el presupuesto no cambia. Lo calcula
// el servidor (GET /api/finance/budget/plan); aquí solo se pinta.
// Usa finance-app.js (estado, formato) y finance-budget.js (la pestaña).
// ============================================

// view: el Presupuesto o el plan (de este dispositivo); which: este mes o el siguiente
const finPlan = { view: 'budget', which: 'current', data: null, saving: false };
try { if (localStorage.getItem('finance_budget_view') === 'plan') finPlan.view = 'plan'; } catch (_) { /* sin almacenamiento */ }

function finPlanShowView() {
    const plan = finPlan.view === 'plan';
    document.querySelectorAll('#finBudgetViews [data-budget-view]').forEach(button => {
        button.setAttribute('aria-selected', String(button.dataset.budgetView === finPlan.view));
    });
    document.getElementById('finBudget').hidden = plan;
    document.getElementById('finPlan').hidden = !plan;
    return plan;
}

function finPlanNextMonth(iso) {
    const d = finDate(iso);
    return getDateKey(new Date(d.getFullYear(), d.getMonth() + 1, 1));
}

function finPlanMonthName(iso) {
    return FIN_MONTHS[finDate(iso).getMonth()];
}

async function finRenderPlan() {
    const box = document.getElementById('finPlan');
    const errorEl = document.getElementById('finBudgetError');
    try {
        const today = finPlan.data ? finPlan.data.today : finToday();
        const month = finPlan.which === 'next' ? `?month=${finPlanNextMonth(today)}` : '';
        finPlan.data = await apiFetch(`/api/finance/budget/plan${month}`);
    } catch (error) {
        showError(errorEl, error.message || 'No se pudo calcular el plan de pagos.');
        return;
    }
    errorEl.classList.add('hidden');
    if (finState.tab !== 'budget' || finPlan.view !== 'plan') return;
    box.replaceChildren(...finPlanBody(finPlan.data));
}

function finPlanBody(plan) {
    const currency = plan.currency;
    const money = cents => formatMoney(cents, currency);
    const nextIso = finPlanNextMonth(plan.today);
    const months = el('div', 'fin-subtabs fin-plan-months');
    months.setAttribute('role', 'tablist');
    [['current', `Este mes · ${finPlanMonthName(plan.today)}`], ['next', `Siguiente · ${finPlanMonthName(nextIso)}`]]
        .forEach(([which, label]) => {
            const button = el('button', 'fin-subtab', label);
            button.type = 'button';
            button.dataset.planMonth = which;
            button.setAttribute('aria-selected', String(finPlan.which === which));
            months.appendChild(button);
        });

    const startRow = plan.start.find(s => s.currency === currency);
    let balance = startRow ? startRow.cents : 0;
    const head = el('section', 'fin-card fin-plan-start');
    head.append(el('span', '', plan.current ? 'Disponible hoy' : `Te quedaría al empezar ${finPlanMonthName(plan.month)}`),
        el('strong', balance < 0 ? 'short' : '', money(balance)));
    head.appendChild(el('p', 'fin-hint', plan.current
        ? 'Lo que tienes hoy en efectivo y débito, sin apartados ni inversiones.'
        : 'Lo que tienes hoy, más lo que aún entra y menos lo que aún falta pagar este mes.'));

    const mine = plan.entries.filter(e => e.currency === currency);
    const dated = mine.filter(e => e.kind !== 'estimate');
    const estimates = mine.filter(e => e.kind === 'estimate');
    const list = el('section', 'fin-card fin-plan-list');
    list.appendChild(el('h2', 'fin-card-title', 'Pagos e ingresos'));
    // Si cobras quincenal, en dos mitades; lo que no tiene día (un préstamo sin día de pago) va al final
    const biweekly = plan.period === 'biweekly';
    const halves = biweekly ? ['Del 1 al 15', `Del 16 al ${Number(plan.date_to.slice(8))}`] : [null];
    const halfOf = e => (biweekly && e.tx_date && Number(e.tx_date.slice(8)) <= 15 ? 0 : halves.length - 1);
    halves.forEach((title, index) => {
        const rows = dated.filter(e => halfOf(e) === index);
        if (title) list.appendChild(el('h3', 'fin-plan-half', title));
        if (!rows.length) list.appendChild(el('p', 'fin-empty', title ? 'Nada en esta quincena.' : 'No hay pagos este mes.'));
        rows.forEach(e => {
            if (e.status !== 'done') balance += e.direction === 'in' ? e.pending_cents : -e.pending_cents;
            list.appendChild(finPlanRow(e, balance, money, plan.today));
        });
        if (title && index === 0) {
            const sub = el('div', 'fin-plan-subtotal');
            sub.append(el('span', '', 'Al 15 te quedarían'), el('strong', balance < 0 ? 'short' : '', money(balance)));
            list.appendChild(sub);
        }
    });

    const approx = el('section', 'fin-card fin-plan-list');
    approx.appendChild(el('h2', 'fin-card-title', 'Aproximados del presupuesto'));
    approx.appendChild(el('p', 'fin-hint', estimates.length
        ? 'Elige cuáles entran en este mes y cuánto. Lo que cambies aquí es solo de este mes: tu presupuesto no cambia.'
        : 'Los renglones de tu presupuesto que no son fijos (comida, gasolina…) salen aquí para elegirlos.'));
    estimates.forEach(e => {
        if (e.included) balance += e.direction === 'in' ? e.pending_cents : -e.pending_cents;
        approx.appendChild(finPlanEstimate(e, money, plan.current));
    });

    const end = el('section', 'fin-card fin-plan-start fin-plan-end');
    end.append(el('span', '', balance >= 0 ? 'Te quedan al final del mes' : 'Te faltarían al final del mes'),
        el('strong', balance < 0 ? 'short' : '', money(Math.abs(balance))));
    const others = plan.entries.some(e => e.currency !== currency);
    if (others) end.appendChild(el('p', 'fin-hint', `Lo que va en otras monedas no entra en este plan (va en ${currency}).`));
    return [months, head, list, approx, end];
}

function finPlanDetail(e, money, today) {
    const paid = e.amount_cents - e.pending_cents;
    if (e.kind === 'card') {
        const source = { bank: 'lo que pide el banco', calculated: 'calculado', estimated: 'estimado' }[e.source] || '';
        const parts = [`Tarjeta${source ? ` · ${source}` : ''}`];
        if (e.source === 'estimated' && e.cut_date) parts.push(`corta el ${finShortDate(e.cut_date)}`);
        if (e.msi_cents) parts.push(`incluye ${money(e.msi_cents)} de MSI`);
        if (e.status === 'done') parts.push('pagado');
        else if (e.status === 'partial') parts.push(`pagaste ${money(paid)} de ${money(e.amount_cents)}`);
        else if (e.status === 'past') parts.push('venció sin pago anotado');
        return parts.join(' · ');
    }
    if (e.kind === 'loan') {
        if (e.status === 'done') return 'Préstamo · pagado';
        const late = e.tx_date && e.tx_date < today ? ' · ya pasó su fecha' : '';
        return `Préstamo · ${e.source === 'table' ? 'de tu tabla de amortización' : 'tu mensualidad'}${late}`;
    }
    const where = e.account_name ? ` · ${e.direction === 'in' ? 'a' : 'de'} ${e.account_name}` : '';
    return `Fijo${where}${e.status === 'done' ? ' · ya se anotó' : ''}`;
}

function finPlanRow(e, balance, money, today) {
    const row = el('div', `fin-plan-row${e.status === 'done' || e.status === 'past' ? ' done' : ''}`);
    row.appendChild(el('span', 'fin-plan-date', e.tx_date ? finShortDate(e.tx_date).replace(/ \d{4}$/, '') : '—'));
    const text = el('span', 'fin-debt-text');
    const name = el('strong', '', e.name);
    if (e.status === 'done') name.prepend(financeIcon('check', 14));
    text.append(name, el('small', '', finPlanDetail(e, money, today)));
    const shown = e.status === 'done' || e.status === 'past' ? e.amount_cents : e.pending_cents;
    const amount = el('span', `fin-plan-amount${e.direction === 'in' ? ' in' : ''}`,
        `${e.direction === 'in' ? '+' : '−'}${money(shown)}`);
    const left = el('span', `fin-plan-left${balance < 0 ? ' short' : ''}`, e.status === 'done' || e.status === 'past' ? '' : money(balance));
    const right = el('span', 'fin-plan-right');
    right.append(amount, left);
    row.append(text, right);
    return row;
}

function finPlanEstimate(e, money, current) {
    const row = el('div', `fin-plan-row fin-plan-estimate${e.included ? '' : ' off'}`);
    const label = el('label', 'fin-plan-check');
    const box = el('input');
    box.type = 'checkbox';
    box.checked = e.included;
    box.dataset.planItem = String(e.ref_id);
    label.append(box, el('span', '', e.name));
    const text = el('span', 'fin-debt-text');
    text.appendChild(label);
    const notes = [];
    if (e.amount_cents !== e.budget_cents) notes.push(`en tu presupuesto: ${money(e.budget_cents)}`);
    if (current && e.spent_cents) notes.push(`llevas ${money(e.spent_cents)}, faltan ${money(Math.max(0, e.amount_cents - e.spent_cents))}`);
    if (notes.length) text.appendChild(el('small', '', notes.join(' · ')));
    const input = el('input', 'fin-plan-input');
    input.type = 'text';
    input.inputMode = 'decimal';
    input.autocomplete = 'off';
    input.value = (e.amount_cents / 100).toFixed(2);
    input.dataset.planAmount = String(e.ref_id);
    input.setAttribute('aria-label', `Monto de ${e.name} este mes`);
    row.append(text, input);
    return row;
}

// Guarda lo elegido de un aproximado (si entra y su monto) y repinta con lo que vuelve
async function finPlanSave(itemId, changes) {
    const entry = finPlan.data.entries.find(e => e.kind === 'estimate' && e.ref_id === itemId);
    if (!entry || finPlan.saving) return;
    finPlan.saving = true;
    const errorEl = document.getElementById('finBudgetError');
    try {
        finPlan.data = await apiFetch(`/api/finance/budget/plan/items/${itemId}`, { method: 'PUT', json: {
            month: finPlan.data.month, included: entry.included, amount_cents: entry.amount_cents, ...changes,
        } });
        errorEl.classList.add('hidden');
    } catch (error) {
        showError(errorEl, error.message || 'No se pudo guardar.');
    } finally {
        finPlan.saving = false;
    }
    if (finState.tab === 'budget' && finPlan.view === 'plan') {
        document.getElementById('finPlan').replaceChildren(...finPlanBody(finPlan.data));
    }
}

document.getElementById('finBudgetViews').addEventListener('click', (event) => {
    const button = event.target.closest('[data-budget-view]');
    if (!button || button.dataset.budgetView === finPlan.view) return;
    finPlan.view = button.dataset.budgetView;
    try { localStorage.setItem('finance_budget_view', finPlan.view); } catch (_) { /* sin almacenamiento */ }
    finRenderBudget();
});

const finPlanBox = document.getElementById('finPlan');
finPlanBox.addEventListener('click', (event) => {
    const button = event.target.closest('[data-plan-month]');
    if (!button || button.dataset.planMonth === finPlan.which) return;
    finPlan.which = button.dataset.planMonth;
    finRenderPlan();
});
finPlanBox.addEventListener('change', (event) => {
    const box = event.target.closest('[data-plan-item]');
    if (box) {
        finPlanSave(Number(box.dataset.planItem), { included: box.checked });
        return;
    }
    const input = event.target.closest('[data-plan-amount]');
    if (!input) return;
    const cents = parseMoneyCents(input.value);
    const itemId = Number(input.dataset.planAmount);
    if (cents == null || cents < 0) {
        showError(document.getElementById('finBudgetError'), 'Escribe un monto, por ejemplo 4000 o 4,000.00');
        return;
    }
    // Cambiar el monto también lo incluye: para eso se escribe
    finPlanSave(itemId, { amount_cents: cents, included: true });
});
finPlanBox.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && event.target.matches('[data-plan-amount]')) event.target.blur();
});
