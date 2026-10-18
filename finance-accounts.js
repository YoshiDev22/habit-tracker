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
    const actions = (credit ? FIN_MENU_ACTIONS.credit : FIN_MENU_ACTIONS.base).map(([act, icon, label, color]) => {
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
    if (st.installments.length) {
        const list = el('ul', 'fin-msi-list');
        st.installments.forEach(i => {
            const item = el('li', 'fin-msi');
            item.append(el('span', '', i.concept), el('small', '', `${i.part} de ${i.months} · ${money(i.amount_cents)}`));
            list.appendChild(item);
        });
        extra.push(el('p', 'fin-stat-label', 'Mensualidades de este corte (ya van en la deuda)'), list);
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

// ---------- Meses sin intereses de la deuda ----------

async function openFinMsi() {
    document.getElementById('finMsiError').classList.add('hidden');
    document.getElementById('finMsiForm').reset();
    finMenuPage('msi');
    await finLoadMsi();
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
        text.append(el('span', '', p.concept), el('small', '', done ? `Liquidada (${p.months} meses)`
            : `${formatMoney(p.monthly_cents, p.currency)} al mes · faltan ${formatMoney(p.remaining_cents, p.currency)}`
              + (p.next_statement ? ` · siguiente, corte del ${finShortDate(p.next_statement)}` : '')));
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
        finLoadMenuStatement();
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
    const concept = document.getElementById('finMsiConcept').value.trim();
    const monthly = parseMoneyCents(document.getElementById('finMsiMonthly').value.trim());
    const months = Number(document.getElementById('finMsiMonths').value);
    if (!concept) return showError(errorEl, 'Escribe qué compra es.');
    if (monthly == null || monthly <= 0) return showError(errorEl, 'Escribe la mensualidad: solo números.');
    if (!Number.isInteger(months) || months < 1 || months > 48) return showError(errorEl, 'Los meses que faltan van de 1 a 48.');
    if (!a.statement_day) return showError(errorEl, 'Primero pon el día de corte de la tarjeta (Editar).');
    try {
        // Desde hoy: la siguiente mensualidad entra en el próximo corte
        await apiFetch('/api/finance/installments', { method: 'POST', json: {
            account_id: a.id, concept, total_cents: monthly * months, months, purchase_date: finToday(),
        } });
        document.getElementById('finMsiForm').reset();
        await finLoadMsi();
        finLoadMenuStatement();
        if (finState.tab === 'accounts') finRenderAccounts();
    } catch (error) {
        showError(errorEl, error.message);
    }
});
