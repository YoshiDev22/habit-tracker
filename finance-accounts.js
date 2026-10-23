// ============================================
// Finanzas: tocar una cuenta abre su menú (saldo y acciones), el ajuste del
// saldo y los meses sin intereses que ya traía una deuda. Usa finance-app.js,
// finance-entry.js (openFinEntry) y finance-settings.js (openFinAccount).
// ============================================

const finAccountMenu = document.getElementById('finAccountMenu');
const finMenu = { account: null, plans: [], statement: null };

// Las acciones de cada tipo de cuenta: [acción, icono, texto, color]
const FIN_MENU_ACTIONS = {
    base: [
        ['edit', 'pencil', 'Editar', '#f1c40f'],
        ['adjust', 'rotate-ccw', 'Ajustar saldo', '#95a5a6'],
        ['movements', 'list', 'Movimientos', '#16a085'],
        ['income', 'arrow-up', 'Ingreso', '#27ae60'],
        ['expense', 'arrow-down', 'Gasto', '#e84393'],
        ['transfer', 'arrow-right', 'Transferencia', '#5c6bc0'],
    ],
    credit: [
        ['edit', 'pencil', 'Editar', '#f1c40f'],
        ['adjust', 'rotate-ccw', 'Ajustar deuda', '#95a5a6'],
        ['movements', 'list', 'Movimientos', '#16a085'],
        ['pay', 'arrow-up', 'Pagar', '#27ae60'],
        ['expense', 'arrow-down', 'Compra', '#e84393'],
        ['msi', 'calendar-days', 'Meses sin intereses', '#5c6bc0'],
    ],
};

function openFinAccountMenu(account) {
    finMenu.account = account;
    finMenu.statement = null;
    finMenuPage(null);
    finRenderAccountMenu();
    openFinSheet(finAccountMenu);
    finLoadMenuStatement();
}

// La línea del estado de cuenta arriba de las acciones (solo tarjetas con corte y pago)
async function finLoadMenuStatement() {
    const a = finMenu.account;
    const row = document.getElementById('finMenuStatement');
    const pay = document.getElementById('finMenuStatementPay');
    if (!(a.kind === 'credit' && a.statement_day && a.due_day)) {
        row.hidden = true;
        return;
    }
    try {
        const st = await apiFetch(`/api/finance/accounts/${a.id}/statement`);
        if (finMenu.account !== a) return;
        finMenu.statement = st;
        pay.textContent = st.remaining_cents
            ? `Pagar ${formatMoney(st.remaining_cents, a.currency)} antes del ${finShortDate(st.due_date)}`
            : st.upcoming ? `Nada por pagar; corte el ${finShortDate(st.last_cut)}` : 'Pagado';
    } catch (error) {
        return;
    }
    // Solo se ve con las acciones; en una página, la página manda
    row.hidden = document.getElementById('finMenuActions').hidden;
    if (!document.getElementById('finStatementPage').hidden) finRenderStatementPage();
}

function finRenderAccountMenu() {
    const a = finMenu.account;
    const credit = a.kind === 'credit';
    document.getElementById('finMenuHead').style.setProperty('--band', finAccountColor(a));
    document.getElementById('finMenuIcon').replaceChildren(financeIcon(finAccountIcon(a), 26));
    document.getElementById('finMenuName').textContent = a.name;
    // En crédito, la deuda en positivo; si se pagó de más, lo que queda a favor
    const inFavor = credit && a.balance_cents > 0;
    document.getElementById('finMenuLabel').textContent = !credit ? 'Saldo de la cuenta' : inFavor ? 'A favor' : 'Deuda';
    document.getElementById('finMenuBalance').textContent = formatMoney(credit ? Math.abs(a.balance_cents)
        : a.balance_cents, a.currency);
    const more = [];
    const pockets = finState.accounts.filter(p => p.is_active && p.parent_id === a.id);
    if (pockets.length) {
        const total = pockets.reduce((acc, p) => acc + p.balance_cents, a.balance_cents);
        more.push(`Con ${pockets.length === 1 ? 'su apartado' : `sus ${pockets.length} apartados`}: ${formatMoney(total, a.currency)}`);
    }
    if (a.parent_id != null) {
        const parent = finState.accounts.find(p => p.id === a.parent_id);
        if (parent) more.push(`Apartado de ${parent.name}`);
    }
    if (a.yield_rate_bp) more.push(`Gana ${finRateText(a.yield_rate_bp)} anual`);
    if (a.available_cents != null) more.push(`Disponible ${formatMoney(a.available_cents, a.currency)}`);
    if (a.opening_date) more.push(`desde el ${finShortDate(a.opening_date)}`);
    document.getElementById('finMenuMore').textContent = more.join(' · ');
    // Lo de antes del día del saldo: se ve, pero no lo mueve
    const history = document.getElementById('finMenuHistory');
    history.hidden = !a.before_count;
    if (a.before_count) {
        const n = a.before_count === 1 ? '1 movimiento' : `${a.before_count} movimientos`;
        history.textContent = `Antes del ${finShortDate(a.opening_date)}: ${n} (entró ${formatMoney(a.before_in_cents, a.currency)}, `
            + `salió ${formatMoney(a.before_out_cents, a.currency)}). Son historial: no cambian el saldo.`;
    }
    const list = credit ? FIN_MENU_ACTIONS.credit : [...FIN_MENU_ACTIONS.base,
        ['yield', 'trending-up', 'Rendimiento', '#00b894'],
        // Una cuenta suelta puede tener apartados; un apartado, no
        ...(a.parent_id == null ? [['pocket', 'piggy-bank', 'Apartado', '#e67e22']] : [])];
    const actions = list.map(([act, icon, label, color]) => {
        const button = el('button', 'fin-menu-action');
        button.type = 'button';
        button.dataset.menuAct = act;
        const circle = el('span', 'fin-menu-action-icon');
        circle.style.setProperty('--tint', color);
        circle.appendChild(financeIcon(icon, 24));
        button.append(circle, el('span', '', label));
        return button;
    });
    document.getElementById('finMenuActions').replaceChildren(...actions);
}

// Una página del menú (ajustar, meses) en lugar de las acciones; null, las acciones
function finMenuPage(name) {
    document.getElementById('finMenuActions').hidden = Boolean(name);
    document.getElementById('finAdjustForm').hidden = name !== 'adjust';
    document.getElementById('finYieldPage').hidden = name !== 'yield';
    document.getElementById('finMsiPage').hidden = name !== 'msi';
    document.getElementById('finStatementPage').hidden = name !== 'statement';
    document.getElementById('finMenuStatement').hidden = Boolean(name) || !finMenu.statement;
}

document.getElementById('finMenuActions').addEventListener('click', (event) => {
    const button = event.target.closest('[data-menu-act]');
    if (!button) return;
    const a = finMenu.account;
    const act = button.dataset.menuAct;
    if (act === 'edit') {
        closeFinSheet(finAccountMenu);
        openFinAccount(a);
    } else if (act === 'adjust') {
        openFinAdjust();
    } else if (act === 'movements') {
        closeFinSheet(finAccountMenu);
        finState.accountFilter = a.id;
        finSetTab('transactions');
    } else if (act === 'income' || act === 'expense') {
        closeFinSheet(finAccountMenu);
        openFinEntry({ kind: act, accountId: a.id });
    } else if (act === 'transfer') {
        closeFinSheet(finAccountMenu);
        openFinEntry({ kind: 'transfer', accountId: a.id });
    } else if (act === 'pay') {
        closeFinSheet(finAccountMenu);
        finPayCard(a);
    } else if (act === 'msi') {
        openFinMsi();
    } else if (act === 'pocket') {
        closeFinSheet(finAccountMenu);
        openFinAccount(null, a.kind, { parentId: a.id });
    } else if (act === 'yield') {
        openFinYield();
    }
});

finAccountMenu.addEventListener('click', (event) => {
    if (event.target.closest('[data-menu-back]')) finMenuPage(null);
});

// ---------- El estado de cuenta, desglosado ----------

document.getElementById('finMenuStatement').addEventListener('click', () => {
    if (!finMenu.statement) return;
    finMenuPage('statement');
    finRenderStatementPage();
});

function finRenderStatementPage() {
    const a = finMenu.account;
    const st = finMenu.statement;
    const money = cents => formatMoney(cents, a.currency);
    const lines = [];
    const line = (label, value, className = '') => lines.push(el('dt', className, label), el('dd', className, value));
    // Dada de alta después del corte: su deuda de entonces es la inicial
    const afterCut = a.opening_date && a.opening_date > st.last_cut;
    const when = `pagar antes del ${finShortDate(st.due_date)}`;
    if (st.upcoming) {
        document.getElementById('finStPeriod').textContent = `Próximo corte, el ${finShortDate(st.last_cut)} · ${when}`;
        line('Deuda hoy', money(st.debt_at_cut_cents));
        if (st.msi_pending_cents) line('− Meses sin intereses de cortes después', money(st.msi_pending_cents));
        line('Llevas para ese corte', money(st.pay_no_interest_cents), 'total');
    } else {
        document.getElementById('finStPeriod').textContent = `Corte del ${finShortDate(st.last_cut)} · ${when}`;
        line(afterCut ? `Deuda al darla de alta (${finShortDate(a.opening_date)})` : 'Deuda al corte',
            money(st.debt_at_cut_cents));
        if (st.msi_pending_cents) line('− Meses sin intereses de cortes después', money(st.msi_pending_cents));
        line(st.from_bank ? 'Calculado por la app' : 'Para no generar intereses', money(st.estimated_cents),
            st.from_bank ? 'muted' : '');
        if (st.from_bank) line('Según tu estado de cuenta', money(st.pay_no_interest_cents));
        if (st.paid_since_cut_cents) line('− Ya pagaste desde el corte', money(st.paid_since_cut_cents));
        line('Te falta pagar', money(st.remaining_cents), 'total');
    }
    document.getElementById('finStLines').replaceChildren(...lines);

    const extra = [];
    // Cada plan a meses: lo que queda en grande y cuántos pagos lleva
    const plans = (finState.installments || []).filter(p => p.account_id === a.id && p.billed < p.months);
    if (plans.length) {
        const list = el('ul', 'fin-msi-cards');
        plans.forEach(p => list.appendChild(finMsiCard(p, st, money)));
        const left = plans.reduce((acc, p) => acc + p.remaining_cents, 0);
        const head = el('p', 'fin-msi-cards-head');
        head.append(el('span', 'fin-stat-label', 'Meses sin intereses'),
            el('span', 'fin-stat-label', `te quedan ${money(left)}`));
        extra.push(head, list);
    }
    if (!st.upcoming && st.cycle_charges_cents) {
        extra.push(el('p', 'fin-hint', `Desde el corte llevas ${money(st.cycle_charges_cents)} en compras: `
            + `van al corte del ${finShortDate(st.next_cut)}.`));
    }
    if (!st.upcoming && afterCut && !st.from_bank) {
        extra.push(el('p', 'fin-hint', 'La diste de alta después del corte: la app toma la deuda de ese día. '
            + 'Si tu estado de cuenta dice otra cifra, escríbela abajo.'));
    }
    document.getElementById('finStExtra').replaceChildren(...extra);

    // El corte en curso se corrige con lo que dice el banco; el próximo aún no tiene
    document.getElementById('finStBankForm').hidden = st.upcoming;
    document.getElementById('finStError').classList.add('hidden');
    document.getElementById('finStBankAmount').value = (st.pay_no_interest_cents / 100).toFixed(2);
    document.getElementById('finStBankReset').hidden = !st.from_bank;
    document.getElementById('finStPay').hidden = !st.remaining_cents;
}

function finMsiCard(p, st, money) {
    const item = el('li', 'fin-msi-card');
    const top = el('div', 'fin-msi-card-top');
    top.append(el('strong', '', p.concept), el('strong', 'fin-msi-card-left', money(p.remaining_cents)));
    const bar = el('div', 'fin-msi-bar');
    const fill = el('span');
    fill.style.width = `${Math.round((p.billed / p.months) * 100)}%`;
    bar.appendChild(fill);
    bar.setAttribute('role', 'img');
    bar.setAttribute('aria-label', `${p.billed} de ${p.months} pagos`);
    const left = p.months - p.billed;
    const now = p.bills.find(b => b.cut === st.last_cut);
    const lines = [`${p.billed} de ${p.months} pagos · ${left === 1 ? 'falta 1' : `faltan ${left}`} de ${money(p.monthly_cents)}`];
    if (now) lines.push(`este corte pide el ${now.part}: ${money(now.amount_cents)} (ya va en la deuda)`);
    item.append(top, bar, el('small', '', lines.join(' · ')));
    return item;
}

// Los planes de todas las tarjetas, otra vez: la página del estado de cuenta y Movimientos
async function finRefreshPlans() {
    try {
        finState.installments = (await apiFetch('/api/finance/installments')).installments;
    } catch (error) { /* se quedan los de antes */ }
    await finLoadMenuStatement();
    finRenderList();
}

async function finSaveStatementBank(reset) {
    const a = finMenu.account;
    const st = finMenu.statement;
    const errorEl = document.getElementById('finStError');
    const url = `/api/finance/accounts/${a.id}/statement`;
    try {
        if (reset) {
            finMenu.statement = await apiFetch(`${url}?cut_date=${st.last_cut}`, { method: 'DELETE' });
        } else {
            const cents = parseMoneyCents(document.getElementById('finStBankAmount').value.trim());
            if (cents == null || cents < 0) return showError(errorEl, 'Escribe el monto: solo números.');
            finMenu.statement = await apiFetch(url, { method: 'PUT',
                json: { cut_date: st.last_cut, pay_no_interest_cents: cents } });
        }
        await finLoadMenuStatement();
        if (finState.tab === 'accounts') finRenderAccounts();
    } catch (error) {
        showError(errorEl, error.message);
    }
}

document.getElementById('finStBankForm').addEventListener('submit', (event) => {
    event.preventDefault();
    finSaveStatementBank(false);
});
document.getElementById('finStBankReset').addEventListener('click', () => finSaveStatementBank(true));
document.getElementById('finStMsi').addEventListener('click', () => openFinMsi());
document.getElementById('finStPay').addEventListener('click', () => {
    closeFinSheet(finAccountMenu);
    finPayCard(finMenu.account);
});

// Pagar una tarjeta: con lo que pide su estado de cuenta, si se sabe
async function finPayCard(card) {
    let options = [];
    if (card.statement_day && card.due_day) {
        try {
            const st = await apiFetch(`/api/finance/accounts/${card.id}/statement`);
            if (st.remaining_cents) options.push({ label: 'Sin intereses', cents: st.remaining_cents });
        } catch (error) { /* sin estado de cuenta: el monto se escribe */ }
    }
    const debt = Math.max(0, -card.balance_cents);
    if (debt && (!options.length || debt > options[0].cents)) options.push({ label: 'Toda la deuda', cents: debt });
    openFinEntry({ kind: 'transfer', toAccountId: card.id, amountCents: options.length ? options[0].cents : null,
        payOptions: options });
}

// ---------- Ajustar el saldo ----------

function openFinAdjust() {
    const a = finMenu.account;
    const credit = a.kind === 'credit';
    document.getElementById('finAdjustLabel').textContent = credit ? 'Deuda real hoy' : 'Saldo real hoy';
    const shown = credit ? Math.max(0, -a.balance_cents) : a.balance_cents;
    document.getElementById('finAdjustAmount').value = (shown / 100).toFixed(2);
    document.getElementById('finAdjustError').classList.add('hidden');
    finMenuPage('adjust');
    document.getElementById('finAdjustAmount').select();
}

document.getElementById('finAdjustForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    const a = finMenu.account;
    const errorEl = document.getElementById('finAdjustError');
    const cents = parseMoneyCents(document.getElementById('finAdjustAmount').value.trim());
    if (cents == null) return showError(errorEl, 'Escribe el monto: solo números.');
    // En crédito se escribe la deuda (positiva); el saldo es negativo
    const target = a.kind === 'credit' ? -Math.abs(cents) : cents;
    const opening = a.opening_balance_cents + (target - a.balance_cents);
    try {
        await apiFetch(`/api/finance/accounts/${a.id}`, { method: 'PATCH', json: { opening_balance_cents: opening } });
        closeFinSheet(finAccountMenu);
        await finLoad();
    } catch (error) {
        showError(errorEl, error.message);
    }
});

// ---------- Rendimiento diario ----------

const finYield = { data: null };

async function openFinYield() {
    ['finYieldRecordError', 'finYieldRateError'].forEach(id => document.getElementById(id).classList.add('hidden'));
    document.getElementById('finYieldRateForm').reset();
    document.getElementById('finYieldFrom').value = finToday();
    document.getElementById('finYieldFrom').max = finToday();
    finMenuPage('yield');
    await finLoadYield();
}

async function finLoadYield() {
    const a = finMenu.account;
    try {
        finYield.data = await apiFetch(`/api/finance/accounts/${a.id}/yield`);
    } catch (error) {
        showError(document.getElementById('finYieldRateError'), error.message);
        return;
    }
    if (finMenu.account !== a) return;
    finRenderYield();
}

// "15 %", "12.5 %"
function finRateText(bp) {
    return `${(bp / 100).toLocaleString('es-MX', { maximumFractionDigits: 2 })} %`;
}

function finRenderYield() {
    const a = finMenu.account;
    const y = finYield.data;
    const money = cents => formatMoney(cents, a.currency);
    const hasRate = y.rates.length > 0;
    const earned = document.getElementById('finYieldEarned');
    earned.hidden = !hasRate;
    document.getElementById('finYieldRecordForm').hidden = !hasRate;
    if (hasRate) {
        const span = y.through < y.since ? 'Ganado sin anotar' : y.since === y.through
            ? `Ganado ayer (${finShortDate(y.since)})` : `Ganado del ${finShortDate(y.since)} al ${finShortDate(y.through)}`;
        document.getElementById('finYieldEarnedLabel').textContent = `${span}, estimado`;
        document.getElementById('finYieldEarnedAmount').textContent = money(y.estimate_cents || 0);
        document.getElementById('finYieldRecord').textContent = y.estimate_cents
            ? `Anotar ${money(y.estimate_cents)}` : 'Anotar';
    }
    const list = document.getElementById('finYieldRates');
    list.replaceChildren(...(hasRate ? [...y.rates].reverse().map(r => {
        const row = el('li', 'fin-yield-rate');
        row.dataset.rateId = String(r.id);
        const text = [`${finRateText(r.rate_bp)} desde el ${finShortDate(r.from_date)}`];
        if (r.cap_cents) text.push(`hasta ${money(r.cap_cents)}`);
        if (r.day_basis === 360) text.push('año de 360 días');
        const remove = el('button', 'link-btn fin-yield-remove', '×');
        remove.type = 'button';
        remove.setAttribute('aria-label', 'Quitar esta tasa');
        row.append(el('span', '', text.join(' · ')), remove);
        return row;
    }) : [el('li', 'fin-hint', 'Sin tasa: esta cuenta no gana rendimiento.')]));
}

document.getElementById('finYieldRates').addEventListener('click', async (event) => {
    const row = event.target.closest('[data-rate-id]');
    if (!row || !event.target.closest('.fin-yield-remove')) return;
    const a = finMenu.account;
    try {
        finYield.data = await apiFetch(`/api/finance/accounts/${a.id}/yield-rates/${row.dataset.rateId}`, { method: 'DELETE' });
        finRenderYield();
        finLoad();
    } catch (error) {
        showError(document.getElementById('finYieldRateError'), error.message);
    }
});

document.getElementById('finYieldRateForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    const a = finMenu.account;
    const errorEl = document.getElementById('finYieldRateError');
    errorEl.classList.add('hidden');
    const rateText = document.getElementById('finYieldRate').value.trim().replace(',', '.').replace('%', '');
    const rate = Number(rateText);
    if (!rateText || !Number.isFinite(rate) || rate < 0 || rate > 100) return showError(errorEl, 'La tasa va de 0 a 100 %.');
    const capText = document.getElementById('finYieldCap').value.trim();
    const cap = capText ? parseMoneyCents(capText) : null;
    if (capText && (cap == null || cap <= 0)) return showError(errorEl, 'El tope es un monto mayor que cero.');
    const from = document.getElementById('finYieldFrom').value || finToday();
    if (from > finToday()) return showError(errorEl, 'La tasa empieza hoy o antes.');
    try {
        finYield.data = await apiFetch(`/api/finance/accounts/${a.id}/yield-rates`, { method: 'PUT', json: {
            from_date: from, rate_bp: Math.round(rate * 100), cap_cents: cap,
            day_basis: Number(document.getElementById('finYieldBasis').value),
        } });
        document.getElementById('finYieldRateForm').reset();
        document.getElementById('finYieldFrom').value = finToday();
        finRenderYield();
        finLoad();
    } catch (error) {
        showError(errorEl, error.message);
    }
});

document.getElementById('finYieldRecordForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    const a = finMenu.account;
    const errorEl = document.getElementById('finYieldRecordError');
    errorEl.classList.add('hidden');
    const bankText = document.getElementById('finYieldBank').value.trim();
    const bank = bankText ? parseMoneyCents(bankText) : null;
    if (bankText && (bank == null || bank <= 0)) return showError(errorEl, 'Escribe el monto: solo números.');
    try {
        await apiFetch(`/api/finance/accounts/${a.id}/yield`, { method: 'POST', json: bank ? { amount_cents: bank } : {} });
        document.getElementById('finYieldBank').value = '';
        closeFinSheet(finAccountMenu);
        await finLoad();
    } catch (error) {
        showError(errorEl, error.message);
    }
});

// ---------- Meses sin intereses de la deuda ----------

async function openFinMsi() {
    document.getElementById('finMsiError').classList.add('hidden');
    finResetMsiForm();
    finMenuPage('msi');
    await finLoadMsi();
}

// El corte de partida: el del estado de cuenta que enseña la tarjeta (el último
// que ya llegó; si ya enseña el próximo, el de antes)
function finResetMsiForm() {
    document.getElementById('finMsiForm').reset();
    const st = finMenu.statement;
    document.getElementById('finMsiCut').value = st ? (st.upcoming ? st.prev_cut : st.last_cut) : '';
}

async function finLoadMsi() {
    const a = finMenu.account;
    const list = document.getElementById('finMsiList');
    try {
        finMenu.plans = (await apiFetch(`/api/finance/installments?account_id=${a.id}`)).installments;
    } catch (error) {
        showError(document.getElementById('finMsiError'), error.message);
        return;
    }
    if (!finMenu.plans.length) {
        list.replaceChildren(el('li', 'fin-empty', 'Ninguna todavía.'));
        return;
    }
    list.replaceChildren(...finMenu.plans.map(p => {
        const item = el('li', 'fin-msi');
        const done = p.billed >= p.months;
        const text = el('span', 'fin-msi-text');
        const money = cents => formatMoney(cents, p.currency);
        // Como en el estado de cuenta: el último pago pedido, lo que queda y el original
        const last = p.billed ? p.bills[p.billed - 1] : null;
        const detail = done ? `Liquidada (${p.months} meses de ${money(p.bills[0].amount_cents)})`
            : [last ? `pago ${last.part} de ${p.months} (corte del ${finShortDate(last.cut)})`
                : `pago 1 de ${p.months} en el corte del ${finShortDate(p.next_statement)}`,
               `${money(p.monthly_cents)} al mes`, `pendiente ${money(p.remaining_cents)}`,
               `original ${money(p.total_cents)}`].join(' · ');
        text.append(el('span', '', p.concept), el('small', '', detail));
        item.appendChild(text);
        // Solo se quitan desde aquí los que no tienen compra (los de una compra, con su compra)
        if (!p.transaction_id) {
            const remove = el('button', 'fin-row-btn');
            remove.type = 'button';
            remove.dataset.removePlan = String(p.id);
            remove.setAttribute('aria-label', `Quitar ${p.concept}`);
            remove.appendChild(financeIcon('x', 18));
            item.appendChild(remove);
        }
        return item;
    }));
}

document.getElementById('finMsiList').addEventListener('click', async (event) => {
    const button = event.target.closest('[data-remove-plan]');
    if (!button) return;
    const plan = finMenu.plans.find(p => p.id === Number(button.dataset.removePlan));
    if (!plan || !(await confirmDialog(`¿Quitar "${plan.concept}" de los meses sin intereses?`, { confirmLabel: 'Quitar' }))) return;
    try {
        await apiFetch(`/api/finance/installments/${plan.id}`, { method: 'DELETE' });
        await finLoadMsi();
        await finRefreshPlans();
        if (finState.tab === 'accounts') finRenderAccounts();
    } catch (error) {
        showError(document.getElementById('finMsiError'), error.message);
    }
});

document.getElementById('finMsiForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    const a = finMenu.account;
    const errorEl = document.getElementById('finMsiError');
    errorEl.classList.add('hidden');
    const value = id => document.getElementById(id).value.trim();
    const concept = value('finMsiConcept');
    const original = parseMoneyCents(value('finMsiOriginal'));
    const pending = value('finMsiPending') ? parseMoneyCents(value('finMsiPending')) : null;
    const monthly = value('finMsiMonthly') ? parseMoneyCents(value('finMsiMonthly')) : null;
    const part = Number(value('finMsiPart'));
    const months = Number(value('finMsiMonths'));
    const cut = value('finMsiCut');
    if (!concept) return showError(errorEl, 'Escribe la descripción, como viene en tu estado de cuenta.');
    if (original == null || original <= 0) return showError(errorEl, 'Escribe el monto original: solo números.');
    if ((value('finMsiPending') && pending == null) || (value('finMsiMonthly') && monthly == null)) {
        return showError(errorEl, 'El saldo pendiente y el pago requerido van en números.');
    }
    if (!Number.isInteger(months) || months < 1 || months > 48) return showError(errorEl, 'Los meses van de 1 a 48.');
    if (!Number.isInteger(part) || part < 1 || part > months) {
        return showError(errorEl, `El número de pago va de 1 a ${months} ("11 de 12").`);
    }
    if (!cut) return showError(errorEl, 'Escribe la fecha de corte de ese estado de cuenta.');
    if (!a.statement_day) return showError(errorEl, 'Primero pon el día de corte de la tarjeta (Editar).');
    try {
        await apiFetch('/api/finance/installments', { method: 'POST', json: {
            account_id: a.id, concept, total_cents: original, months, bank_cut: cut, bank_part: part,
            bank_monthly_cents: monthly, bank_pending_cents: pending,
        } });
        finResetMsiForm();
        await finLoadMsi();
        await finRefreshPlans();
        if (finState.tab === 'accounts') finRenderAccounts();
    } catch (error) {
        showError(errorEl, error.message);
    }
});
