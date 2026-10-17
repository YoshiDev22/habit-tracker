// ============================================
// Finanzas: tocar una cuenta abre su menú (saldo y acciones), el ajuste del
// saldo y los meses sin intereses que ya traía una deuda. Usa finance-app.js,
// finance-entry.js (openFinEntry) y finance-settings.js (openFinAccount).
// ============================================

const finAccountMenu = document.getElementById('finAccountMenu');
const finMenu = { account: null, plans: [] };

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
    finMenuPage(null);
    finRenderAccountMenu();
    openFinSheet(finAccountMenu);
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
        if (finState.tab === 'accounts') finRenderAccounts();
    } catch (error) {
        showError(errorEl, error.message);
    }
});
