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
    if (a.interest_rate_bp != null) more.push(`Tasa ${finRateText(a.interest_rate_bp)} anual`);
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
        ['term', 'landmark', 'Plazo fijo', '#2980b9'],
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
    } else if (act === 'term') {
        closeFinSheet(finAccountMenu);
        openFinTerm(null, a.id);
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

// ---------- A plazo fijo ----------

const finTermSheet = document.getElementById('finTermSheet');
const finTermForm = { term: null };
const FIN_ON_MATURITY = { stay: 'se queda ahí', return: 'regresa', renew: 'se reinvierte' };

// Las cuentas donde vive un plazo: activas y que no son de crédito
function finTermAccounts() {
    return finActiveAccounts().filter(a => a.kind !== 'credit');
}

function finFillAccountSelect(select, accounts, selectedId) {
    select.replaceChildren(...accounts.map(a => {
        const option = el('option', '', a.name);
        option.value = String(a.id);
        return option;
    }));
    if (selectedId != null && accounts.some(a => a.id === selectedId)) select.value = String(selectedId);
}

function openFinTerm(term = null, accountId = null) {
    finTermForm.term = term;
    document.getElementById('finTermTitle').textContent = term ? term.concept : 'Nuevo plazo fijo';
    document.getElementById('finTermConcept').value = term ? term.concept : '';
    const select = document.getElementById('finTermAccount');
    finFillAccountSelect(select, finTermAccounts(), term ? term.account_id : accountId);
    // CETES o una casa de bolsa suelen ser su propia cuenta: se crea aquí mismo
    const fresh = el('option', '', '＋ Nueva cuenta de inversión…');
    fresh.value = 'new';
    select.appendChild(fresh);
    if (!term && accountId == null) {
        const invest = finTermAccounts().find(a => a.kind === 'investment');
        select.value = invest ? String(invest.id) : 'new';
    }
    document.getElementById('finTermNewName').value = '';
    document.getElementById('finTermFromField').hidden = Boolean(term);
    document.getElementById('finTermFrom').value = '';
    document.getElementById('finTermPrincipal').value = term ? (term.principal_cents / 100).toFixed(2) : '';
    document.getElementById('finTermRate').value = term ? String(term.rate_bp / 100) : '';
    document.getElementById('finTermStart').value = term ? term.start_date : finToday();
    document.getElementById('finTermDays').value = term ? String(term.days) : '28';
    document.getElementById('finTermBasis').value = term ? String(term.day_basis) : '360';
    document.getElementById('finTermOnMaturity').value = term ? term.on_maturity : 'stay';
    document.getElementById('finTermDelete').hidden = !term;
    document.getElementById('finTermError').classList.add('hidden');
    finSyncTermForm(term ? term.return_account_id : null);
    openFinSheet(finTermSheet);
}

// "Regresa a" solo al regresar, sin la cuenta del plazo y en su moneda; y lo que dará
function finSyncTermForm(returnId) {
    const isNew = document.getElementById('finTermAccount').value === 'new';
    document.getElementById('finTermNewField').hidden = !isNew;
    // Una cuenta nueva es de la moneda principal
    const account = isNew ? { id: null, currency: finMainCurrency() }
        : finAccount(Number(document.getElementById('finTermAccount').value));
    const back = document.getElementById('finTermOnMaturity').value === 'return';
    document.getElementById('finTermReturnField').hidden = !back;
    const select = document.getElementById('finTermReturn');
    const keep = returnId !== undefined ? returnId : Number(select.value) || null;
    finFillAccountSelect(select, finActiveAccounts().filter(a => account && a.id !== account.id
        && a.currency === account.currency && a.kind !== 'credit'), keep);
    // De dónde sale el dinero: "Ya está ahí" o una cuenta de la misma moneda (la transferencia se anota al guardar)
    const from = document.getElementById('finTermFrom');
    const keepFrom = from.value;
    const already = el('option', '', 'Ya está ahí: no muevas nada');
    already.value = '';
    from.replaceChildren(already, ...finActiveAccounts().filter(a => account && a.id !== account.id
        && a.currency === account.currency && a.kind !== 'credit').map(a => {
        const option = el('option', '', a.name);
        option.value = String(a.id);
        return option;
    }));
    if ([...from.options].some(o => o.value === keepFrom)) from.value = keepFrom;
    const values = finTermValues();
    const preview = document.getElementById('finTermPreview');
    if (!account || !values) {
        preview.textContent = '';
        return;
    }
    const interest = Math.round(values.principal_cents * values.rate_bp * values.days / (10000 * values.day_basis));
    const end = finAddDays(values.start_date, values.days);
    preview.textContent = `Vence el ${finShortDate(end)} y da ${formatMoney(interest, account.currency)} `
        + `(${formatMoney(values.principal_cents + interest, account.currency)} en total).`;
}

// Lo del formulario, o null si falta algo
function finTermValues() {
    const principal = parseMoneyCents(document.getElementById('finTermPrincipal').value.trim());
    const rateText = document.getElementById('finTermRate').value.trim().replace(',', '.').replace('%', '');
    const rate = Number(rateText);
    const days = Number(document.getElementById('finTermDays').value);
    const start = document.getElementById('finTermStart').value;
    if (principal == null || principal <= 0 || !rateText || !Number.isFinite(rate) || rate < 0 || rate > 100
        || !Number.isInteger(days) || days < 1 || days > 3650 || !start) return null;
    return { principal_cents: principal, rate_bp: Math.round(rate * 100), days, start_date: start,
        day_basis: Number(document.getElementById('finTermBasis').value) };
}

['finTermAccount', 'finTermOnMaturity'].forEach(id => {
    document.getElementById(id).addEventListener('change', () => finSyncTermForm());
});
['finTermPrincipal', 'finTermRate', 'finTermDays', 'finTermStart', 'finTermBasis'].forEach(id => {
    document.getElementById(id).addEventListener('input', () => finSyncTermForm());
});

document.getElementById('finTermForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    const errorEl = document.getElementById('finTermError');
    errorEl.classList.add('hidden');
    const values = finTermValues();
    if (!values) return showError(errorEl, 'Revisa monto, tasa (0 a 100 %), días (1 a 3650) y la fecha.');
    const onMaturity = document.getElementById('finTermOnMaturity').value;
    const body = {
        ...values, account_id: Number(document.getElementById('finTermAccount').value),
        concept: document.getElementById('finTermConcept').value.trim() || 'Plazo fijo', on_maturity: onMaturity,
        return_account_id: onMaturity === 'return' ? Number(document.getElementById('finTermReturn').value) || null : null,
    };
    if (onMaturity === 'return' && !body.return_account_id) return showError(errorEl, 'Elige a qué cuenta regresa.');
    const newName = document.getElementById('finTermNewName').value.trim();
    const isNew = document.getElementById('finTermAccount').value === 'new';
    if (isNew && !newName) return showError(errorEl, 'Escribe el nombre de la cuenta nueva (CETES, GBM, Bitso…).');
    const term = finTermForm.term;
    try {
        if (isNew) {
            // Primero la cuenta; si el plazo falla, la cuenta queda y se elige en la lista
            const account = await apiFetch('/api/finance/accounts', { method: 'POST', json: {
                name: newName, kind: 'investment', currency: finMainCurrency(), icon: 'trending-up',
                color: FIN_PALETTE[(finState.accounts.length * 4 + 3) % FIN_PALETTE.length] } });
            finState.accounts.push(account);
            finFillAccountSelect(document.getElementById('finTermAccount'), finTermAccounts(), account.id);
            body.account_id = account.id;
        }
        const fromId = term ? null : Number(document.getElementById('finTermFrom').value) || null;
        const saved = await apiFetch(term ? `/api/finance/terms/${term.id}` : '/api/finance/terms',
            { method: term ? 'PUT' : 'POST', json: body });
        // Un plazo nuevo ya guardado se edita desde aquí si lo que sigue falla
        finTermForm.term = saved;
        if (fromId) {
            await apiFetch('/api/finance/transactions', { method: 'POST', json: {
                kind: 'transfer', account_id: fromId, to_account_id: body.account_id, amount_cents: body.principal_cents,
                tx_date: body.start_date, concept: `A plazo: ${body.concept}`.slice(0, 200) } });
        }
        closeFinSheet(finTermSheet);
        await finLoad();
    } catch (error) {
        showError(errorEl, finTermForm.term && !term
            ? `El plazo se guardó, pero el dinero no se movió: ${error.message}` : error.message);
    }
});

document.getElementById('finTermDelete').addEventListener('click', async () => {
    const term = finTermForm.term;
    if (!term) return;
    const ok = await confirmDialog(`¿Borrar "${term.concept}"? Lo que ya anotó se queda en tus movimientos.`,
        { confirmLabel: 'Borrar' });
    if (!ok) return;
    try {
        await apiFetch(`/api/finance/terms/${term.id}`, { method: 'DELETE' });
        closeFinSheet(finTermSheet);
        await finLoad();
    } catch (error) {
        showError(document.getElementById('finTermError'), error.message);
    }
});

// La pestaña Cuentas › Inversiones: los plazos fijos y las cuentas que ganan día a día
async function finRenderInvestments(body) {
    let terms = [];
    try {
        terms = (await apiFetch('/api/finance/terms')).terms;
    } catch (error) {
        body.replaceChildren(el('p', 'fin-hint', error.message));
        return;
    }
    if (finState.accountsSub !== 'investments') return;
    finState.terms = terms;
    const blocks = [];
    // Las cuentas de inversión (CETES, una casa de bolsa, un exchange), con su total
    const invest = finActiveAccounts().filter(a => a.kind === 'investment');
    const main = finMainCurrency();
    const investHead = el('div', 'fin-accounts-head');
    const investSum = invest.filter(a => a.currency === main).reduce((acc, a) => acc + a.balance_cents, 0);
    investHead.append(el('span', '', 'Cuentas de inversión'), el('strong', '', finMoney(investSum, main)));
    blocks.push(investHead);
    if (!invest.length) blocks.push(el('p', 'fin-empty', 'Agrega aquí CETES, tu casa de bolsa o tu exchange: cada una con su saldo.'));
    invest.forEach(a => blocks.push(finInvestmentRow(a)));
    const addAccount = el('button', 'link-btn fin-add-account', '＋ Nueva cuenta de inversión');
    addAccount.type = 'button';
    addAccount.dataset.newAccount = 'investment';
    blocks.push(addAccount);

    const open = terms.filter(t => !t.matured);
    const head = el('div', 'fin-accounts-head spaced');
    head.append(el('span', '', 'Plazos fijos'));
    blocks.push(head);
    if (!open.length) blocks.push(el('p', 'fin-empty', 'Sin plazos abiertos.'));
    open.forEach(t => {
        const a = finAccount(t.account_id);
        const currency = a ? a.currency : finMainCurrency();
        const row = el('button', 'fin-account fin-term');
        row.type = 'button';
        row.dataset.termId = String(t.id);
        const text = el('span', 'fin-account-text');
        text.append(el('strong', '', t.concept),
            el('span', 'fin-account-balance', formatMoney(t.principal_cents, currency)),
            el('small', 'fin-account-sub', `${a ? a.name : ''} · ${finRateText(t.rate_bp)} · ${t.days} días · ${FIN_ON_MATURITY[t.on_maturity]}`));
        const side = el('span', 'fin-account-side');
        side.append(el('small', '', `Vence el ${finShortDate(t.maturity_date)}`),
            el('span', 'fin-available', `+${formatMoney(t.interest_cents, currency)}`));
        row.append(finBadge('landmark', a ? finAccountColor(a) : FIN_NEUTRAL, { size: 'md', square: true }), text, side);
        blocks.push(row);
    });
    const add = el('button', 'link-btn fin-add-account', '＋ Nuevo plazo fijo');
    add.type = 'button';
    add.dataset.newTerm = '1';
    blocks.push(add);
    const done = terms.filter(t => t.matured).slice(0, 10);
    if (done.length) {
        const past = el('details', 'fin-terms-past');
        past.appendChild(el('summary', '', `Vencidos (${done.length})`));
        done.forEach(t => {
            const a = finAccount(t.account_id);
            past.appendChild(el('p', 'fin-hint', `${t.concept}: ${formatMoney(t.principal_cents, a ? a.currency : finMainCurrency())}`
                + ` + ${formatMoney(t.interest_cents, a ? a.currency : finMainCurrency())}, venció el ${finShortDate(t.maturity_date)}`));
        });
        blocks.push(past);
    }
    // Las demás que ganan día a día (una cuenta del banco, sus apartados)
    const daily = finActiveAccounts().filter(a => a.yield_rate_bp && a.kind !== 'investment');
    const dailyHead = el('div', 'fin-accounts-head spaced');
    dailyHead.appendChild(el('span', '', 'Rendimiento diario en tus cuentas'));
    blocks.push(dailyHead);
    if (!daily.length) {
        blocks.push(el('p', 'fin-empty', 'Ninguna otra cuenta gana día a día. Ponle su tasa en el menú de la cuenta › Rendimiento.'));
    }
    daily.forEach(a => blocks.push(finInvestmentRow(a)));
    body.replaceChildren(...blocks);
}

// Una cuenta en Inversiones: su saldo, su tasa, lo que está en plazos y lo ganado sin anotar
function finInvestmentRow(a) {
    const row = el('button', 'fin-account');
    row.type = 'button';
    row.dataset.accountId = String(a.id);
    const text = el('span', 'fin-account-text');
    text.append(el('strong', '', a.name), el('span', 'fin-account-balance', formatMoney(a.balance_cents, a.currency)));
    const details = [];
    if (a.yield_rate_bp) details.push(`Gana ${finRateText(a.yield_rate_bp)} anual`);
    if (a.term_locked_cents) details.push(`${formatMoney(a.term_locked_cents, a.currency)} en plazos`);
    if (details.length) text.appendChild(el('small', 'fin-account-sub', details.join(' · ')));
    const side = el('span', 'fin-account-side');
    if (a.yield_estimate_cents) {
        side.append(el('small', '', 'Sin anotar'), el('span', 'fin-available', `+${formatMoney(a.yield_estimate_cents, a.currency)}`));
    }
    row.append(finBadge(finAccountIcon(a), finAccountColor(a), { size: 'md', square: true }), text, side);
    return row;
}

document.getElementById('finAccountsBody').addEventListener('click', (event) => {
    const term = event.target.closest('[data-term-id]');
    if (term) {
        openFinTerm((finState.terms || []).find(t => t.id === Number(term.dataset.termId)) || null);
        return;
    }
    if (event.target.closest('[data-new-term]')) openFinTerm();
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
