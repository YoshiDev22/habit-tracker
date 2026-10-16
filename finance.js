// ============================================
// Finanzas: el dinero del día a día (épica 37, fase 1)
// ============================================
//
// Quinta vista, solo con el módulo Finanzas encendido (como Costos con Maker).
// Arriba, el periodo (mes o quincena: la primera vez se pregunta "¿Cada cuándo
// cobras?", y luego cuánto: el fijo "Sueldo") con ‹ ›; luego el resumen de /api/finance/summary y los
// movimientos del periodo. ＋ Agregar abre la alta rápida; pegar filas de un
// estado de cuenta (o un CSV) abre la vista previa, que marca lo repetido.
// Organizar (cuentas, fijos y categorías) es un menú de desglose.
//
// Las fechas del periodo y todas las cifras son del backend (backend/finance.py);
// aquí solo se pintan. Carga después de costs.js: usa parseTable,
// parseMoneyCents, parseDate y normalize de ahí, formatMoney y CURRENCIES de
// project-overview.js, el, reportCard, summaryStat y barList de reports.js, y
// configButton de board.js.

const financeState = {
    day: null,              // un día del periodo que se ve (null = hoy)
    summary: null,
    transactions: [],
    accounts: [],
    categories: [],
    recurring: [],
    loaded: false,
    kind: 'expense',        // el tipo elegido en la alta rápida
    editing: null,          // el movimiento que se edita, o null al agregar
    categoryTouched: false, // la categoría la eligió el usuario: no adivinar
    pending: null,          // la vista previa de lo pegado
    editingFixed: null,     // el fijo que se edita en Organizar
    fixedKind: 'expense',
    salaryStep: false,      // se ve el paso "¿Cuánto cobras?" (solo en esta sesión)
};
// "tacos" → la última categoría usada con ese concepto, para adivinar la siguiente
const financeConceptCategory = new Map();

const financeSummaryEl = document.getElementById('financeSummary');
const financeListEl = document.getElementById('financeList');
const financeErrorEl = document.getElementById('financeError');
const financeAskEl = document.getElementById('financeAsk');
const financeTxModal = document.getElementById('financeTxModal');
const financeImportModal = document.getElementById('financeImportModal');
const financeConfigModal = document.getElementById('financeConfigModal');
const financeConfigError = document.getElementById('financeConfigError');

const FINANCE_KIND_LABELS = { cash: 'Efectivo', debit: 'Débito', credit: 'Crédito' };
const FINANCE_FREQUENCY_LABELS = { monthly: 'cada mes', semimonthly: 'cada quincena', yearly: 'cada año' };
const FINANCE_MONTHS = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre',
    'octubre', 'noviembre', 'diciembre'];
const FINANCE_MONTHS_SHORT = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
const FINANCE_WEEKDAYS = ['dom', 'lun', 'mar', 'mié', 'jue', 'vie', 'sáb'];

function isFinanceVisible() {
    return typeof currentViewId !== 'undefined' && currentViewId === 'finance';
}

function financeDate(iso) {
    const [y, m, d] = iso.split('-').map(Number);
    return new Date(y, m - 1, d);
}

function financeToday() {
    return getDateKey(new Date());
}

function financeAccount(id) {
    return financeState.accounts.find(a => a.id === id);
}

function financeCategory(id) {
    return financeState.categories.find(c => c.id === id);
}

function financeDefaultCurrency() {
    const account = financeState.accounts.find(a => a.is_default) || financeState.accounts[0];
    return account ? account.currency : 'MXN';
}

// ============================================
// Módulo: la pestaña y su página de Configuración, solo con Finanzas
// ============================================

function applyFinanceModule() {
    const on = moduleEnabled('finance');
    // La casilla de Configuración › Módulos solo para las cuentas con acceso.
    // currentUser solo cambia al entrar y al tocar un módulo: los dos hooks
    // que llaman aquí, así que script.js no necesita saber de Finanzas.
    const state = currentUser && currentUser.modules && currentUser.modules.finance;
    document.getElementById('moduleFinanceOption').hidden = !(state && state.allowed);
    // Antes de mostrarla: setViewVisible() pasa por goToView(), que recuerda la
    // pestaña actual y taparía que se recargó estando en Finanzas
    const wasOnFinance = readLastView() === 'finance';
    setViewVisible('finance', on);
    if (on && wasOnFinance && currentViewId !== 'finance') {
        goToView('finance', { animate: false });
    }
    document.getElementById('settingsFinanceItem').hidden = !on;
    document.getElementById('settingsFinancePage').hidden = !on;
    if (!on) financeState.loaded = false;
}

// ============================================
// Carga
// ============================================

async function loadFinance() {
    if (!getToken() || !moduleEnabled('finance')) return;
    financeErrorEl.classList.add('hidden');
    const day = financeState.day ? `?day=${financeState.day}` : '';
    try {
        const [summary, list, accounts, categories, recurring] = await Promise.all([
            apiFetch(`/api/finance/summary${day}`),
            apiFetch(`/api/finance/transactions${day}`),
            apiFetch('/api/finance/accounts'),
            apiFetch('/api/finance/categories'),
            apiFetch('/api/finance/recurring'),   // para saber si ya hay sueldo
        ]);
        Object.assign(financeState, {
            summary, transactions: list.transactions, accounts: accounts.accounts,
            categories: categories.categories, recurring: recurring.recurring, loaded: true,
        });
    } catch (error) {
        financeSummaryEl.replaceChildren(reportsMessage(error.message || 'No se pudo cargar Finanzas.'));
        return;
    }
    // Del más antiguo al más reciente: el último uso de un concepto gana
    [...financeState.transactions].reverse().forEach(tx => {
        if (tx.category_id) financeConceptCategory.set(normalize(tx.concept), tx.category_id);
    });
    renderFinance();
}

function renderFinance() {
    const s = financeState.summary;
    if (!s) return;
    financeAskEl.hidden = s.period_asked;
    syncFinancePeriodToggle(s.period_asked ? s.period : null);
    // Después del periodo, el sueldo: el paso, o una línea discreta mientras no haya
    document.getElementById('financeSalary').hidden = !(s.period_asked && financeState.salaryStep);
    document.getElementById('financeSalaryHint').hidden = !s.period_asked || financeState.salaryStep
        || Boolean(financeSalaryFixed());
    renderFinanceSalarySetting();
    document.getElementById('financePeriodLabel').textContent = financePeriodLabel(s);
    // No hay movimientos en el futuro: el siguiente periodo empieza después de hoy
    document.getElementById('financeNext').disabled = s.next_day > financeToday();
    renderFinanceSummary();
    renderFinanceList();
}

function financePeriodLabel(s) {
    const from = financeDate(s.date_from);
    const to = financeDate(s.date_to);
    if (s.period === 'month') {
        const month = FINANCE_MONTHS[from.getMonth()];
        return `${month[0].toUpperCase()}${month.slice(1)} ${from.getFullYear()}`;
    }
    return `${from.getDate()}–${to.getDate()} ${FINANCE_MONTHS_SHORT[to.getMonth()]} ${to.getFullYear()}`;
}

function goToFinancePeriod(day) {
    financeState.day = day;
    loadFinance();
}

// ============================================
// Resumen
// ============================================

function renderFinanceSummary() {
    const s = financeState.summary;
    const totals = s.totals.length ? s.totals
        : [{ currency: financeDefaultCurrency(), expense_cents: 0, income_cents: 0, net_cents: 0 }];
    const children = [];
    totals.forEach(total => {
        const grid = el('div', 'report-stats');
        const net = summaryStat(formatMoney(total.net_cents, total.currency), 'balance');
        if (total.net_cents < 0) net.classList.add('finance-negative');
        grid.append(
            summaryStat(formatMoney(total.expense_cents, total.currency), 'gastado'),
            summaryStat(formatMoney(total.income_cents, total.currency), 'ingresos'),
            net,
        );
        const title = totals.length > 1 ? `Resumen en ${total.currency}` : 'Resumen';
        children.push(reportCard(title, grid));
    });
    if (s.needs_review) {
        children[0].appendChild(el('p', 'costs-hint',
            `${s.needs_review} ${s.needs_review === 1 ? 'movimiento está' : 'movimientos están'} por confirmar: cuentan igual.`));
    }

    // En qué se fue: el gasto por categoría, por moneda
    const expenses = s.categories.filter(c => c.kind === 'expense');
    const currencies = [...new Set(expenses.map(c => c.currency))];
    if (expenses.length) {
        const card = reportCard('En qué se fue');
        currencies.forEach(currency => {
            const rows = expenses.filter(c => c.currency === currency);
            if (currencies.length > 1) card.appendChild(el('p', 'recurring-label', currency));
            const total = rows.reduce((sum, c) => sum + c.cents, 0);
            card.appendChild(barList(rows.map(c => ({ name: c.name, color: c.color, seconds: c.cents })), total,
                cents => formatMoney(cents, currency)));
        });
        children.push(card);
    }

    // Por cuenta: lo que se movió (no es su saldo)
    const moved = s.accounts.filter(a => a.expense_cents || a.income_cents || a.transfer_in_cents || a.transfer_out_cents);
    if (moved.length) {
        const list = el('ul', 'recurring-list');
        moved.forEach(a => {
            const item = el('li', 'recurring-item');
            const text = el('div', 'recurring-text');
            text.append(el('strong', '', a.name));
            const parts = [];
            if (a.expense_cents) parts.push(`gastos ${formatMoney(a.expense_cents, a.currency)}`);
            if (a.income_cents) parts.push(`ingresos ${formatMoney(a.income_cents, a.currency)}`);
            if (a.transfer_in_cents) parts.push(`entró ${formatMoney(a.transfer_in_cents, a.currency)}`);
            if (a.transfer_out_cents) parts.push(`salió ${formatMoney(a.transfer_out_cents, a.currency)}`);
            text.append(el('small', '', parts.join(' · ')));
            const net = el('span', `finance-amount${a.net_cents < 0 ? '' : ' income'}`,
                `${a.net_cents < 0 ? '−' : '+'}${formatMoney(Math.abs(a.net_cents), a.currency)}`);
            item.append(text, net);
            list.appendChild(item);
        });
        const card = reportCard('Por cuenta', list);
        card.appendChild(el('p', 'costs-hint', 'Lo que entró y salió de cada cuenta en el periodo, no su saldo. '
            + 'El pago de la tarjeta sale del débito y entra al crédito: no es un gasto.'));
        children.push(card);
    }
    financeSummaryEl.replaceChildren(...children);
}

// ============================================
// Movimientos
// ============================================

function financeDayTitle(iso) {
    const today = financeToday();
    if (iso === today) return 'Hoy';
    const yesterday = new Date();
    yesterday.setDate(yesterday.getDate() - 1);
    if (iso === getDateKey(yesterday)) return 'Ayer';
    const d = financeDate(iso);
    return `${FINANCE_WEEKDAYS[d.getDay()]} ${d.getDate()} ${FINANCE_MONTHS_SHORT[d.getMonth()]}`;
}

function financeShortDate(iso) {
    if (!iso) return '—';
    const d = financeDate(iso);
    return `${d.getDate()} ${FINANCE_MONTHS_SHORT[d.getMonth()]}`;
}

function financeAmountText(tx) {
    const money = formatMoney(tx.amount_cents, tx.currency);
    if (tx.kind === 'expense') return `−${money}`;
    if (tx.kind === 'income') return `+${money}`;
    return `⇄ ${money}`;
}

function renderFinanceList() {
    const txs = financeState.transactions;
    if (!txs.length) {
        financeListEl.replaceChildren(reportsMessage('Aún no hay movimientos en este periodo. Toca ＋ Agregar.'));
        return;
    }
    const days = new Map();
    txs.forEach(tx => {
        if (!days.has(tx.tx_date)) days.set(tx.tx_date, []);
        days.get(tx.tx_date).push(tx);
    });
    const groups = [];
    days.forEach((items, iso) => {
        const group = el('section', 'finance-day');
        const head = el('div', 'finance-day-head');
        head.append(el('span', '', financeDayTitle(iso)));
        // El gasto del día, por moneda
        const spent = new Map();
        items.filter(tx => tx.kind === 'expense').forEach(tx => {
            spent.set(tx.currency, (spent.get(tx.currency) || 0) + tx.amount_cents);
        });
        if (spent.size) {
            head.append(el('span', 'finance-day-total',
                [...spent].map(([currency, cents]) => formatMoney(cents, currency)).join(' · ')));
        }
        const list = el('ul', 'finance-tx-list');
        items.forEach(tx => list.appendChild(financeTxRow(tx)));
        group.append(head, list);
        groups.push(group);
    });
    financeListEl.replaceChildren(...groups);
}

function financeTxRow(tx) {
    const item = el('li');
    const button = el('button', 'finance-tx');
    button.type = 'button';
    button.dataset.txId = String(tx.id);
    const text = el('span', 'finance-tx-text');
    text.append(el('span', 'finance-tx-concept', (tx.recurring_id ? '🔁 ' : '') + tx.concept));
    const account = financeAccount(tx.account_id);
    const details = [];
    if (tx.kind === 'transfer') {
        const target = financeAccount(tx.to_account_id);
        details.push(`${account ? account.name : '—'} → ${target ? target.name : '—'}`);
    } else {
        const category = financeCategory(tx.category_id);
        if (category) details.push(category.name);
        if (account) details.push(account.name);
    }
    if (tx.needs_review) details.push('⚠ por confirmar');
    text.append(el('small', '', details.join(' · ')));
    const dot = el('i', 'finance-tx-dot');
    const category = financeCategory(tx.category_id);
    if (category && category.color) dot.style.background = category.color;
    button.append(dot, text, el('span', `finance-amount ${tx.kind}`, financeAmountText(tx)));
    item.appendChild(button);
    return item;
}

financeListEl.addEventListener('click', (event) => {
    const button = event.target.closest('[data-tx-id]');
    if (!button) return;
    const tx = financeState.transactions.find(t => t.id === Number(button.dataset.txId));
    if (tx) openFinanceTx(tx);
});

// ============================================
// Alta rápida y edición
// ============================================

const financeTxForm = document.getElementById('financeTxForm');
const financeTxAmount = document.getElementById('financeTxAmount');
const financeTxDate = document.getElementById('financeTxDate');
const financeTxConcept = document.getElementById('financeTxConcept');
const financeTxAccount = document.getElementById('financeTxAccount');
const financeTxCategory = document.getElementById('financeTxCategory');
const financeTxTo = document.getElementById('financeTxTo');
const financeTxNote = document.getElementById('financeTxNote');
const financeTxError = document.getElementById('financeTxError');

function financeOptions(select, items, selectedId, label = item => item.name) {
    select.replaceChildren(...items.map(item => {
        const option = el('option', '', label(item));
        option.value = String(item.id);
        option.selected = item.id === selectedId;
        return option;
    }));
}

function financeAccountLabel(account) {
    // "Efectivo (Efectivo)" sobra: el tipo solo si el nombre no lo dice ya
    const kind = FINANCE_KIND_LABELS[account.kind];
    const extra = [normalize(account.name).includes(normalize(kind)) ? null : kind,
        account.last4 ? `•${account.last4}` : null,
        account.currency !== 'MXN' ? account.currency : null].filter(Boolean).join(' ');
    return extra ? `${account.name} (${extra})` : account.name;
}

// Las activas, más la de un movimiento viejo que se edita aunque esté archivada
function financeUsableAccounts(keepId) {
    return financeState.accounts.filter(a => a.is_active || a.id === keepId);
}

function financeKindCategories(kind) {
    return financeState.categories.filter(c => c.kind === kind);
}

function setFinanceTxKind(kind) {
    financeState.kind = kind;
    document.querySelectorAll('#financeTxKind [data-kind]').forEach(button => {
        button.setAttribute('aria-pressed', String(button.dataset.kind === kind));
    });
    const transfer = kind === 'transfer';
    document.getElementById('financeTxCategoryField').hidden = transfer;
    document.getElementById('financeTxToField').hidden = !transfer;
    document.getElementById('financeTxAccountLabel').textContent = transfer ? 'De la cuenta' : 'Cuenta';
    // Repetir es de un gasto o ingreso nuevo: una transferencia no es un fijo, y editar toca solo ese
    document.getElementById('financeTxRepeatField').hidden = transfer || Boolean(financeState.editing);
    renderFinanceTxRepeat();
    if (!transfer) {
        const categories = financeKindCategories(kind);
        const current = Number(financeTxCategory.value);
        const keep = categories.some(c => c.id === current) ? current : financeGuessCategory(kind);
        financeOptions(financeTxCategory, categories, keep);
    }
    renderFinanceTransferTargets();
}

// La última categoría usada con ese concepto; si no, "Otros" (la última del tipo)
function financeGuessCategory(kind) {
    const guess = financeConceptCategory.get(normalize(financeTxConcept.value));
    const categories = financeKindCategories(kind);
    if (categories.some(c => c.id === guess)) return guess;
    const last = categories[categories.length - 1];
    return last ? last.id : null;
}

// A dónde puede ir una transferencia: otra cuenta de la misma moneda
function renderFinanceTransferTargets() {
    const from = financeAccount(Number(financeTxAccount.value));
    const keep = financeState.editing ? financeState.editing.to_account_id : null;
    const targets = financeUsableAccounts(keep).filter(a => from && a.id !== from.id && a.currency === from.currency);
    const current = Number(financeTxTo.value);
    // Por defecto, la de crédito: lo más común es pagar la tarjeta
    const preferred = targets.find(a => a.id === current) || targets.find(a => a.id === keep)
        || targets.find(a => a.kind === 'credit') || targets[0];
    financeOptions(financeTxTo, targets, preferred ? preferred.id : null, financeAccountLabel);
    const target = financeAccount(Number(financeTxTo.value));
    document.getElementById('financeTxHint').hidden = !(financeState.kind === 'transfer' && target && target.kind === 'credit');
}

function openFinanceTx(tx = null) {
    financeState.editing = tx;
    financeState.categoryTouched = !!tx;
    financeTxError.classList.add('hidden');
    document.getElementById('financeTxTitle').textContent = tx ? 'Editar movimiento' : 'Agregar';
    document.getElementById('financeTxDelete').hidden = !tx;
    const s = financeState.summary;
    const today = financeToday();
    // Al agregar, hoy si el periodo que se ve lo incluye; si no, su primer día
    const date = tx ? tx.tx_date : (!s || (s.date_from <= today && today <= s.date_to) ? today : s.date_from);
    financeTxAmount.value = tx ? (tx.amount_cents / 100).toFixed(2) : '';
    financeTxDate.value = date;
    financeTxConcept.value = tx ? tx.concept : '';
    financeTxNote.value = tx ? (tx.note || '') : '';
    document.getElementById('financeTxRepeat').value = '';
    const accounts = financeUsableAccounts(tx ? tx.account_id : null);
    const defaultAccount = accounts.find(a => a.is_default) || accounts[0];
    financeOptions(financeTxAccount, accounts, tx ? tx.account_id : (defaultAccount && defaultAccount.id), financeAccountLabel);
    financeTxCategory.replaceChildren();
    if (tx && tx.category_id) {
        financeOptions(financeTxCategory, financeKindCategories(tx.kind), tx.category_id);
    }
    financeTxTo.replaceChildren();
    setFinanceTxKind(tx ? tx.kind : 'expense');
    showModal(financeTxModal);
    financeTxAmount.focus();
}

function closeFinanceTx() {
    financeState.editing = null;
    hideModal(financeTxModal);
}

function financeTxPayload() {
    const cents = parseMoneyCents(financeTxAmount.value);
    if (cents == null || cents <= 0) throw new Error('Escribe el monto: un número mayor que cero.');
    const concept = financeTxConcept.value.trim();
    if (!concept) throw new Error('Escribe el concepto.');
    if (!financeTxDate.value) throw new Error('Elige la fecha.');
    const transfer = financeState.kind === 'transfer';
    if (transfer && !financeTxTo.value) throw new Error('Necesitas otra cuenta de la misma moneda para transferir.');
    return {
        kind: financeState.kind,
        amount_cents: Math.abs(cents),
        tx_date: financeTxDate.value,
        concept,
        note: financeTxNote.value.trim() || null,
        account_id: Number(financeTxAccount.value),
        category_id: transfer ? null : Number(financeTxCategory.value),
        to_account_id: transfer ? Number(financeTxTo.value) : null,
    };
}

// Lo que hará el fijo, dicho con la fecha elegida
function renderFinanceTxRepeat() {
    const hint = document.getElementById('financeTxRepeatHint');
    const frequency = financeTxRepeatFrequency();
    hint.hidden = !frequency || !financeTxDate.value;
    if (hint.hidden) return;
    const day = financePayDay(financeTxDate.value);
    const d = financeDate(financeTxDate.value);
    const when = {
        // El mensual repite el día exacto (un 31 cae en el último de los meses cortos)
        monthly: `el ${d.getDate()} de cada mes${d.getDate() > 28 ? ' (o el último, si el mes es más corto)' : ''}`,
        semimonthly: (() => {
            const [first, second] = [day, financeOtherPayDay(day)].sort((a, b) => a - b);
            return `${financeDayText(first)} y ${financeDayText(second)} de cada mes`;
        })(),
        yearly: `cada ${d.getDate()} de ${FINANCE_MONTHS[d.getMonth()]}`,
    }[frequency];
    hint.textContent = `Se anota solo ${when}, como un fijo. Lo cambias o lo quitas en Organizar › Fijos.`;
}

function financeTxRepeatFrequency() {
    const field = document.getElementById('financeTxRepeatField');
    return field.hidden ? '' : document.getElementById('financeTxRepeat').value;
}

// Un fijo cuyo primer cobro es este movimiento: el servidor lo anota en su fecha
// (ya, si es hoy o antes), así que no se crea el movimiento aparte
function financeTxRecurringPayload(payload, frequency) {
    const fields = {
        kind: payload.kind, account_id: payload.account_id, category_id: payload.category_id,
        concept: payload.concept, note: payload.note, amount_cents: payload.amount_cents,
        frequency, start_date: payload.tx_date,
    };
    if (frequency === 'semimonthly') {
        const day = financePayDay(payload.tx_date);
        const other = financeOtherPayDay(day);
        Object.assign(fields, { first_day: Math.min(day, other), second_day: Math.max(day, other) });
    }
    return fields;
}

async function saveFinanceTx(event) {
    event.preventDefault();
    const saveBtn = document.getElementById('financeTxSave');
    let payload;
    try {
        payload = financeTxPayload();
    } catch (error) {
        showError(financeTxError, error.message);
        return;
    }
    saveBtn.disabled = true;
    try {
        const editing = financeState.editing;
        const frequency = financeTxRepeatFrequency();
        if (editing) {
            await apiFetch(`/api/finance/transactions/${editing.id}`, { method: 'PATCH', json: payload });
        } else if (frequency) {
            await apiFetch('/api/finance/recurring', {
                method: 'POST', json: financeTxRecurringPayload(payload, frequency),
            });
        } else {
            await apiFetch('/api/finance/transactions', { method: 'POST', json: payload });
        }
        if (payload.category_id) financeConceptCategory.set(normalize(payload.concept), payload.category_id);
        closeFinanceTx();
        await loadFinance();
    } catch (error) {
        showError(financeTxError, error.message);
    } finally {
        saveBtn.disabled = false;
    }
}

async function deleteFinanceTx() {
    const tx = financeState.editing;
    if (!tx) return;
    const ok = await confirmDialog(`¿Borrar "${tx.concept}" (${formatMoney(tx.amount_cents, tx.currency)})?`
        + (tx.recurring_id ? ' Es un cobro de un fijo: no vuelve a anotarse.' : ''),
    { confirmLabel: 'Borrar', danger: true });
    if (!ok) return;
    try {
        await apiFetch(`/api/finance/transactions/${tx.id}`, { method: 'DELETE' });
        closeFinanceTx();
        await loadFinance();
    } catch (error) {
        showError(financeTxError, error.message);
    }
}

document.querySelectorAll('#financeTxKind [data-kind]').forEach(button => {
    button.addEventListener('click', () => setFinanceTxKind(button.dataset.kind));
});
financeTxConcept.addEventListener('change', () => {
    if (financeState.categoryTouched || financeState.kind === 'transfer') return;
    financeTxCategory.value = String(financeGuessCategory(financeState.kind));
});
financeTxCategory.addEventListener('change', () => { financeState.categoryTouched = true; });
financeTxAccount.addEventListener('change', renderFinanceTransferTargets);
financeTxTo.addEventListener('change', renderFinanceTransferTargets);
financeTxForm.addEventListener('submit', saveFinanceTx);
document.getElementById('financeTxDelete').addEventListener('click', deleteFinanceTx);
document.getElementById('financeTxCancel').addEventListener('click', closeFinanceTx);
document.getElementById('financeTxClose').addEventListener('click', closeFinanceTx);
financeTxModal.querySelector('.modal-overlay').addEventListener('click', closeFinanceTx);
document.getElementById('financeAddBtn').addEventListener('click', () => openFinanceTx());

// ============================================
// Pegar el estado de cuenta / importar un CSV
// ============================================

const FINANCE_HEADER_ALIASES = {
    tx_date: ['fecha', 'date', 'dia', 'día', 'fecha de operacion', 'fecha operacion', 'fecha de cargo'],
    concept: ['concepto', 'descripcion', 'descripción', 'description', 'detalle', 'movimiento', 'comercio',
        'establecimiento'],
    category: ['categoria', 'categoría', 'category', 'rubro'],
    charge: ['cargo', 'cargos', 'retiro', 'retiros', 'gasto', 'gastos', 'egreso', 'egresos', 'debito', 'débito'],
    credit: ['abono', 'abonos', 'deposito', 'depósito', 'depositos', 'depósitos', 'ingreso', 'ingresos'],
    amount: ['monto', 'importe', 'cantidad', 'amount', 'valor', 'total'],
};
// Sin encabezado: fecha, concepto, monto y categoría
const FINANCE_DEFAULT_ORDER = ['tx_date', 'concept', 'amount', 'category'];

function financeColumns(header) {
    const columns = {};
    header.map(normalize).forEach((name, i) => {
        Object.entries(FINANCE_HEADER_ALIASES).forEach(([field, aliases]) => {
            if (columns[field] !== undefined) return;
            if (aliases.some(alias => name === normalize(alias))) columns[field] = i;
        });
    });
    return columns;
}

// Filas de texto → movimientos para la vista previa. Con columnas de cargo y
// abono, cada una dice el tipo. Con una sola de monto, si hay signos mezclados
// el más común es el gasto (en un estado de cuenta casi todo son compras).
function rowsToFinance(table) {
    if (!table.length) return [];
    let columns = financeColumns(table[0]);
    const hasHeader = columns.concept !== undefined
        || ['amount', 'charge', 'credit'].some(field => columns[field] !== undefined);
    const body = hasHeader ? table.slice(1) : table;
    if (!hasHeader) {
        columns = {};
        FINANCE_DEFAULT_ORDER.forEach((field, i) => { columns[field] = i; });
    }
    const get = (cells, field) => (columns[field] === undefined ? '' : (cells[columns[field]] || '').trim());
    const signs = body.map(cells => parseMoneyCents(get(cells, 'amount'))).filter(c => c);
    const negatives = signs.filter(c => c < 0).length;
    const expenseSign = negatives > signs.length - negatives ? -1 : 1;

    return body.map(cells => {
        const charge = parseMoneyCents(get(cells, 'charge'));
        const credit = parseMoneyCents(get(cells, 'credit'));
        let kind = 'expense';
        let cents = null;
        if (charge) {
            cents = Math.abs(charge);
        } else if (credit) {
            kind = 'income';
            cents = Math.abs(credit);
        } else {
            const amount = parseMoneyCents(get(cells, 'amount'));
            if (amount) {
                kind = Math.sign(amount) === expenseSign ? 'expense' : 'income';
                cents = Math.abs(amount);
            }
        }
        const dateText = get(cells, 'tx_date');
        const row = {
            tx_date: parseDate(dateText),
            concept: get(cells, 'concept').slice(0, 200),
            categoryName: get(cells, 'category'),
            kind,
            amount_cents: cents,
        };
        row.problem = !row.concept ? 'sin concepto'
            : row.tx_date == null ? `fecha "${dateText}" no válida`
                : !row.amount_cents ? 'sin monto'
                    : null;
        return row;
    });
}

// La categoría de cada fila: la escrita si existe y es de su tipo; si no, la
// última usada con ese concepto; si no, "Otros" del tipo
function financeRowCategory(row) {
    const categories = financeKindCategories(row.kind);
    const byName = categories.find(c => normalize(c.name) === normalize(row.categoryName || ''));
    if (byName) return byName;
    const guess = financeConceptCategory.get(normalize(row.concept));
    return categories.find(c => c.id === guess) || categories[categories.length - 1];
}

async function openFinanceImport(text) {
    financeErrorEl.classList.add('hidden');
    const rows = rowsToFinance(parseTable(text));
    if (!rows.length) {
        showError(financeErrorEl, 'No encontré filas para agregar.');
        return;
    }
    const accounts = financeUsableAccounts(null);
    const preferred = accounts.find(a => a.kind !== 'cash') || accounts[0];
    financeOptions(document.getElementById('financeImportAccount'), accounts, preferred && preferred.id, financeAccountLabel);
    financeState.pending = { rows, existing: null };
    document.getElementById('financeImportDupes').checked = false;
    document.getElementById('financeImportError').classList.add('hidden');
    await refreshFinanceImport();
    showModal(financeImportModal);
}

// Con la cuenta elegida: lo que ya existe (mismo día, monto y tipo) se marca
// repetido, contando repeticiones (dos tacos iguales el mismo día no tapan un
// tercero). En una tarjeta de crédito, un abono es el pago: va como
// transferencia desde el débito, no como ingreso, así que se salta.
async function refreshFinanceImport() {
    const pending = financeState.pending;
    if (!pending) return;
    const account = financeAccount(Number(document.getElementById('financeImportAccount').value));
    const dated = pending.rows.filter(r => r.tx_date).map(r => r.tx_date).sort();
    const counts = new Map();
    let checked = false;
    if (account && dated.length) {
        const from = dated[0];
        const to = dated[dated.length - 1];
        if ((financeDate(to) - financeDate(from)) / 86400000 < 366) {
            try {
                const data = await apiFetch(`/api/finance/transactions?date_from=${from}&date_to=${to}&account_id=${account.id}`);
                data.transactions.filter(tx => tx.account_id === account.id && tx.kind !== 'transfer').forEach(tx => {
                    const key = `${tx.tx_date}|${tx.amount_cents}|${tx.kind}`;
                    counts.set(key, (counts.get(key) || 0) + 1);
                });
                checked = true;
            } catch (error) { /* sin la revisión de repetidos: se avisa abajo */ }
        }
    }
    pending.rows.forEach(row => {
        row.duplicate = false;
        row.skip = row.problem;
        if (!row.skip && account && account.kind === 'credit' && row.kind === 'income') {
            row.skip = 'abono a la tarjeta: anótalo como transferencia desde tu débito';
        }
        if (row.skip) return;
        const key = `${row.tx_date}|${row.amount_cents}|${row.kind}`;
        if (counts.get(key)) {
            row.duplicate = true;
            counts.set(key, counts.get(key) - 1);
        }
        const category = financeRowCategory(row);
        row.category_id = category ? category.id : null;
        row.categoryLabel = category ? category.name : '—';
    });
    renderFinanceImport(account, checked);
}

function renderFinanceImport(account, checked) {
    const rows = financeState.pending.rows;
    const currency = account ? account.currency : 'MXN';
    const dupes = rows.filter(r => r.duplicate).length;
    const includeDupes = document.getElementById('financeImportDupes').checked;
    const valid = rows.filter(r => !r.skip && (!r.duplicate || includeDupes)).length;
    document.getElementById('financeImportSummary').textContent =
        `${valid} de ${rows.length} ${rows.length === 1 ? 'fila' : 'filas'} se agregarán a "${account ? account.name : ''}".`
        + (rows.some(r => r.skip) ? ' Las marcadas en rojo se saltan.' : '')
        + (checked ? '' : ' No pude revisar si ya existían.');
    document.getElementById('financeImportRows').replaceChildren(...rows.map(r => {
        const tr = el('tr', r.skip ? 'invalid' : (r.duplicate && !includeDupes ? 'duplicate' : ''));
        // El monto con su signo, junto al concepto: en un teléfono la tabla se recorta por la derecha
        const amount = r.amount_cents ? `${r.kind === 'income' ? '+' : '−'}${formatMoney(r.amount_cents, currency)}` : '—';
        [financeShortDate(r.tx_date), r.concept || '—', amount, r.skip ? '' : r.categoryLabel]
            .forEach((text, i) => {
                const td = el('td', i === 2 ? `finance-amount ${r.kind}` : '', text);
                tr.appendChild(td);
            });
        if (r.skip) tr.title = r.skip;
        else if (r.duplicate) tr.title = 'Ya hay uno igual (mismo día, monto y cuenta)';
        return tr;
    }));
    const option = document.getElementById('financeImportDupesOption');
    option.classList.toggle('hidden', dupes === 0);
    document.getElementById('financeImportDupesLabel').textContent =
        `Agregar también ${dupes === 1 ? 'el que ya existe' : `los ${dupes} que ya existen`} (grises): marca esto solo si de verdad fueron dos compras iguales`;
    document.getElementById('financeImportConfirm').disabled = valid === 0;
}

function closeFinanceImport() {
    financeState.pending = null;
    hideModal(financeImportModal);
}

async function confirmFinanceImport() {
    const pending = financeState.pending;
    if (!pending) return;
    const confirmBtn = document.getElementById('financeImportConfirm');
    const accountId = Number(document.getElementById('financeImportAccount').value);
    const includeDupes = document.getElementById('financeImportDupes').checked;
    const rows = pending.rows.filter(r => !r.skip && (!r.duplicate || includeDupes)).map(r => ({
        kind: r.kind, account_id: accountId, amount_cents: r.amount_cents, tx_date: r.tx_date,
        category_id: r.category_id, concept: r.concept,
    }));
    confirmBtn.disabled = true;
    try {
        await apiFetch('/api/finance/transactions/import', { method: 'POST', json: { rows } });
        closeFinanceImport();
        await loadFinance();
    } catch (error) {
        showError(document.getElementById('financeImportError'), error.message);
        confirmBtn.disabled = false;
    }
}

// Pegar varias celdas en la lista abre la vista previa (como la hoja de Costos)
document.querySelector('.finance-list-card').addEventListener('paste', (event) => {
    const text = event.clipboardData && event.clipboardData.getData('text/plain');
    if (!text || !/[\t\n]/.test(text.trim())) return;
    event.preventDefault();
    openFinanceImport(text);
});
document.getElementById('financeImportBtn').addEventListener('click', () => document.getElementById('financeImportFile').click());
document.getElementById('financeImportFile').addEventListener('change', async (event) => {
    const file = event.target.files[0];
    event.target.value = '';
    if (!file) return;
    if (file.size > 1024 * 1024) {
        showError(financeErrorEl, 'El archivo pesa más de 1 MB.');
        return;
    }
    openFinanceImport(await file.text());
});
document.getElementById('financeImportAccount').addEventListener('change', refreshFinanceImport);
document.getElementById('financeImportDupes').addEventListener('change', () => {
    renderFinanceImport(financeAccount(Number(document.getElementById('financeImportAccount').value)), true);
});
document.getElementById('financeImportConfirm').addEventListener('click', confirmFinanceImport);
document.getElementById('financeImportCancel').addEventListener('click', closeFinanceImport);
document.getElementById('financeImportClose').addEventListener('click', closeFinanceImport);
financeImportModal.querySelector('.modal-overlay').addEventListener('click', closeFinanceImport);

// Escape cierra la alta rápida o la vista previa (en captura: no cierra lo de abajo)
document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    const confirmOpen = !document.getElementById('confirmModal').classList.contains('hidden');
    if (confirmOpen) return;
    if (!financeImportModal.classList.contains('hidden')) {
        event.stopPropagation();
        closeFinanceImport();
    } else if (!financeTxModal.classList.contains('hidden')) {
        event.stopPropagation();
        closeFinanceTx();
    }
}, true);

// ============================================
// El periodo: "¿Cada cuándo cobras?" y Configuración › Finanzas
// ============================================

function syncFinancePeriodToggle(period) {
    document.querySelectorAll('#financePeriodToggle [data-period]').forEach(button => {
        button.setAttribute('aria-pressed', String(button.dataset.period === period));
    });
}

async function saveFinancePeriod(period, errorEl) {
    try {
        await apiFetch('/api/finance/settings', { method: 'PUT', json: { period } });
        syncFinancePeriodToggle(period);
        financeState.day = null;   // el periodo de hoy, con la nueva medida
        await loadFinance();
    } catch (error) {
        showError(errorEl, error.message);
    }
}

financeAskEl.addEventListener('click', async (event) => {
    const button = event.target.closest('[data-period]');
    if (!button) return;
    await saveFinancePeriod(button.dataset.period, financeErrorEl);
    // Contestado el cada cuándo, el cuánto (si aún no hay sueldo)
    if (financeState.summary && financeState.summary.period_asked && !financeSalaryFixed()) openFinanceSalary();
});
document.getElementById('financePeriodToggle').addEventListener('click', (event) => {
    const button = event.target.closest('[data-period]');
    if (button) saveFinancePeriod(button.dataset.period, document.getElementById('financePeriodError'));
});
// Al abrir la página, lo guardado (pudo cambiar en otro dispositivo)
document.getElementById('settingsFinanceItem').addEventListener('click', async () => {
    document.getElementById('financePeriodError').classList.add('hidden');
    try {
        const [settings, recurring, accounts, categories] = await Promise.all([
            apiFetch('/api/finance/settings'),
            apiFetch('/api/finance/recurring'),
            apiFetch('/api/finance/accounts'),
            apiFetch('/api/finance/categories'),
        ]);
        syncFinancePeriodToggle(settings.period);
        Object.assign(financeState, {
            recurring: recurring.recurring, accounts: accounts.accounts, categories: categories.categories,
        });
        renderFinanceSalarySetting();
    } catch (error) {
        showError(document.getElementById('financePeriodError'), error.message);
    }
});

function renderFinanceSalarySetting() {
    const salary = financeSalaryFixed();
    document.getElementById('financeSalarySetting').textContent = salary ? financeFixedText(salary) : 'Sin agregar';
    document.getElementById('financeSalarySettingAdd').hidden = Boolean(salary);
}

document.getElementById('financeSalarySettingAdd').addEventListener('click', async () => {
    hideHabitsSetup();
    goToView('finance');
    if (!financeState.summary) await loadFinance();
    openFinanceSalary();
});

// ============================================
// El sueldo: "¿Cuánto cobras?", guardado como el fijo "Sueldo"
// ============================================

// El fijo que hace de sueldo: el ingreso de la categoría Sueldo, o cualquier ingreso fijo
function financeSalaryFixed() {
    const income = financeState.recurring.filter(rc => rc.kind === 'income');
    const category = financeState.categories.find(c => c.kind === 'income' && c.name === 'Sueldo');
    return income.find(rc => category && rc.category_id === category.id) || income[0] || null;
}

function financeLastDay(date) {
    return new Date(date.getFullYear(), date.getMonth() + 1, 0).getDate();
}

// El día de pago de una fecha: el último del mes cuenta como 31 (así se repite cada fin de mes)
function financePayDay(iso) {
    const d = financeDate(iso);
    return d.getDate() === financeLastDay(d) ? 31 : d.getDate();
}

// El otro pago de la quincena, para proponerlo: quince días antes o después
function financeOtherPayDay(day) {
    if (day === 31) return 15;
    if (day === 15) return 31;
    return day < 15 ? day + 15 : day - 15;
}

function financeDayText(day) {
    return day >= 31 ? 'el último día' : `el ${day}`;
}

// La fecha que se propone: el siguiente 15 o fin de mes (quincena), o el fin de mes
function financeNextPayDate(biweekly) {
    const today = financeDate(financeToday());
    const day = biweekly && today.getDate() <= 15 ? 15 : financeLastDay(today);
    return getDateKey(new Date(today.getFullYear(), today.getMonth(), day));
}

function financeSalaryBiweekly() {
    return Boolean(financeState.summary && financeState.summary.period === 'biweekly');
}

function renderFinanceSalaryDays() {
    const date = document.getElementById('financeSalaryDate').value;
    const text = document.getElementById('financeSalaryDays');
    const shorter = day => (day > 28 && day < 31 ? ' (o el último, si el mes es más corto)' : '');
    if (!date) {
        text.textContent = '';
        return;
    }
    const day = financePayDay(date);
    if (!financeSalaryBiweekly()) {
        // El mensual repite el día exacto de la fecha, no "el último"
        const exact = financeDate(date).getDate();
        text.textContent = `Te pagan el ${exact} de cada mes${exact > 28 ? ' (o el último, si el mes es más corto)' : ''}.`;
        return;
    }
    const other = Number(document.getElementById('financeSalarySecond').value);
    if (!other) {
        text.textContent = '';
        return;
    }
    const [first, second] = [day, other].sort((a, b) => a - b);
    text.textContent = first === second ? 'Los dos pagos tienen que ser en días distintos.'
        : `Te pagan ${financeDayText(first)} y ${financeDayText(second)} de cada mes${shorter(second)}.`;
}

function renderFinanceSalaryAccounts(selectedId) {
    const select = document.getElementById('financeSalaryAccount');
    const accounts = financeUsableAccounts(null);
    // El sueldo casi nunca llega en efectivo: de entrada, la primera de débito
    const preferred = selectedId || (accounts.find(a => a.kind === 'debit')
        || accounts.find(a => a.is_default) || accounts[0] || {}).id;
    financeOptions(select, accounts, preferred, financeAccountLabel);
    const fresh = document.createElement('option');
    fresh.value = 'new';
    fresh.textContent = 'Nueva cuenta de débito…';
    select.append(fresh);
    if (!accounts.length) select.value = 'new';
    document.getElementById('financeSalaryNewAccountField').hidden = select.value !== 'new';
}

function openFinanceSalary() {
    const biweekly = financeSalaryBiweekly();
    financeState.salaryStep = true;
    document.getElementById('financeSalaryError').classList.add('hidden');
    document.getElementById('financeSalaryTitle').textContent =
        `¿Cuánto cobras ${biweekly ? 'cada quincena' : 'cada mes'}?`;
    document.getElementById('financeSalaryForm').reset();
    renderFinanceSalaryAccounts(null);
    const date = financeNextPayDate(biweekly);
    document.getElementById('financeSalaryDate').value = date;
    document.getElementById('financeSalarySecondField').hidden = !biweekly;
    document.getElementById('financeSalarySecond').value = String(financeOtherPayDay(financePayDay(date)));
    renderFinanceSalaryDays();
    renderFinance();
    window.scrollTo({ top: 0 });
    document.getElementById('financeSalaryAmount').focus();
}

function closeFinanceSalary() {
    financeState.salaryStep = false;
    renderFinance();
}

async function saveFinanceSalary(event) {
    event.preventDefault();
    const errorEl = document.getElementById('financeSalaryError');
    errorEl.classList.add('hidden');
    const biweekly = financeSalaryBiweekly();
    const cents = parseMoneyCents(document.getElementById('financeSalaryAmount').value);
    const date = document.getElementById('financeSalaryDate').value;
    const accountSelect = document.getElementById('financeSalaryAccount');
    const newName = document.getElementById('financeSalaryNewAccount').value.trim();
    if (cents == null || cents <= 0) return showError(errorEl, 'Escribe cuánto cobras: un número mayor que cero.');
    if (!date) return showError(errorEl, 'Elige en el calendario cuándo te pagan la próxima vez.');
    const fields = { frequency: biweekly ? 'semimonthly' : 'monthly' };
    if (biweekly) {
        const day = financePayDay(date);
        const other = Number(document.getElementById('financeSalarySecond').value);
        if (!Number.isInteger(other) || other < 1 || other > 31) {
            return showError(errorEl, 'Escribe el día del otro pago: del 1 al 31 (31 es el último día).');
        }
        if (other === day) return showError(errorEl, 'Los dos pagos tienen que ser en días distintos.');
        Object.assign(fields, { first_day: Math.min(day, other), second_day: Math.max(day, other) });
    }
    if (accountSelect.value === 'new' && !newName) return showError(errorEl, 'Escribe el nombre de la cuenta.');
    const category = financeState.categories.find(c => c.kind === 'income' && c.name === 'Sueldo')
        || financeKindCategories('income')[0];
    if (!category) return showError(errorEl, 'Crea una categoría de ingresos en Organizar › Categorías.');
    const save = document.getElementById('financeSalarySave');
    save.disabled = true;
    try {
        let accountId = Number(accountSelect.value);
        if (accountSelect.value === 'new') {
            const account = await apiFetch('/api/finance/accounts', {
                method: 'POST', json: { name: newName, kind: 'debit', currency: financeDefaultCurrency() },
            });
            financeState.accounts.push(account);
            // Si lo siguiente falla, reintentar no crea la cuenta otra vez
            renderFinanceSalaryAccounts(account.id);
            accountId = account.id;
        }
        await apiFetch('/api/finance/recurring', {
            method: 'POST',
            json: {
                ...fields, kind: 'income', concept: 'Sueldo', amount_cents: Math.abs(cents),
                account_id: accountId, category_id: category.id, start_date: date,
            },
        });
        financeState.salaryStep = false;
        await loadFinance();
    } catch (error) {
        showError(errorEl, error.message);
    } finally {
        save.disabled = false;
    }
}

document.getElementById('financeSalaryForm').addEventListener('submit', saveFinanceSalary);
document.getElementById('financeSalaryLater').addEventListener('click', closeFinanceSalary);
document.getElementById('financeSalaryOpen').addEventListener('click', openFinanceSalary);
document.getElementById('financeSalaryAccount').addEventListener('change', (event) => {
    const fresh = event.target.value === 'new';
    document.getElementById('financeSalaryNewAccountField').hidden = !fresh;
    if (fresh) document.getElementById('financeSalaryNewAccount').focus();
});
document.getElementById('financeSalaryDate').addEventListener('change', (event) => {
    if (event.target.value && financeSalaryBiweekly()) {
        document.getElementById('financeSalarySecond').value =
            String(financeOtherPayDay(financePayDay(event.target.value)));
    }
    renderFinanceSalaryDays();
});
document.getElementById('financeSalarySecond').addEventListener('input', renderFinanceSalaryDays);
document.getElementById('financeTxRepeat').addEventListener('change', renderFinanceTxRepeat);
financeTxDate.addEventListener('change', renderFinanceTxRepeat);

document.getElementById('financePrev').addEventListener('click', () => {
    if (financeState.summary) goToFinancePeriod(financeState.summary.prev_day);
});
document.getElementById('financeNext').addEventListener('click', () => {
    if (financeState.summary) goToFinancePeriod(financeState.summary.next_day);
});

// ============================================
// Organizar: cuentas, fijos y categorías
// ============================================

const financeConfigNav = createDrillDown({
    modal: financeConfigModal,
    menu: document.getElementById('financeConfigMenu'),
    back: document.getElementById('financeConfigBack'),
    title: document.getElementById('financeConfigTitle'),
    rootTitle: 'Organizar',
    onPage: () => financeConfigError.classList.add('hidden'),
    onMenu: () => financeConfigError.classList.add('hidden'),
    onClose: () => closeFinanceConfig(),
});

async function openFinanceConfig() {
    financeConfigError.classList.add('hidden');
    financeConfigNav.showMenu({ animate: false });
    // Lo que ya se tiene, al instante; lo fresco (y los fijos) al llegar
    renderFinanceAccounts();
    renderFinanceCategories();
    renderFinanceFixed();
    showModal(financeConfigModal);
    await refreshFinanceConfig();
}

function closeFinanceConfig() {
    hideModal(financeConfigModal);
    resetFinanceFixedForm();
    loadFinance();   // lo cambiado aquí (nombres, fijos) se ve en la lista
}

async function refreshFinanceConfig() {
    try {
        const [accounts, categories, recurring] = await Promise.all([
            apiFetch('/api/finance/accounts'),
            apiFetch('/api/finance/categories'),
            apiFetch('/api/finance/recurring'),
        ]);
        financeState.accounts = accounts.accounts;
        financeState.categories = categories.categories;
        financeState.recurring = recurring.recurring;
    } catch (error) {
        showError(financeConfigError, error.message);
        return;
    }
    renderFinanceAccounts();
    renderFinanceCategories();
    renderFinanceFixed();
}

// Un cambio en Organizar: el error, si lo hay, y la lista al día
async function financeConfigAction(request) {
    financeConfigError.classList.add('hidden');
    try {
        await request();
    } catch (error) {
        showError(financeConfigError, error.message);
    }
    await refreshFinanceConfig();
}

// --- Cuentas ---

function renderFinanceAccounts() {
    const list = document.getElementById('financeAccountList');
    const accounts = [...financeState.accounts].sort((a, b) => Number(b.is_active) - Number(a.is_active));
    list.replaceChildren(...accounts.map(a => {
        const row = el('div', `config-row finance-account-row${a.is_active ? '' : ' archived'}`);
        row.dataset.accountId = String(a.id);
        const star = configButton('config-action finance-default', a.is_default ? `${a.name} es la de por defecto`
            : `Usar ${a.name} por defecto`, a.is_default ? '★' : '☆');
        star.disabled = a.is_default || !a.is_active;
        const name = document.createElement('input');
        name.type = 'text';
        name.className = 'config-name';
        name.maxLength = 40;
        name.value = a.name;
        name.setAttribute('aria-label', `Nombre de ${a.name}`);
        const kind = document.createElement('select');
        kind.className = 'finance-account-kind';
        kind.setAttribute('aria-label', `Tipo de ${a.name}`);
        Object.entries(FINANCE_KIND_LABELS).forEach(([value, label]) => {
            const option = el('option', '', label);
            option.value = value;
            option.selected = value === a.kind;
            kind.appendChild(option);
        });
        const info = [a.currency, a.last4 ? `•${a.last4}` : null,
            a.tx_count ? `${a.tx_count} ${a.tx_count === 1 ? 'mov.' : 'movs.'}` : null,
            a.is_active ? null : 'archivada'].filter(Boolean).join(' · ');
        const count = el('span', 'config-type finance-account-info', info);
        const action = a.tx_count
            ? configButton('config-action finance-archive', a.is_active ? `Archivar ${a.name}` : `Reactivar ${a.name}`,
                a.is_active ? 'Archivar' : 'Reactivar')
            : configButton('config-action danger finance-account-delete', `Eliminar ${a.name}`, '×');
        row.append(star, name, kind, count, action);
        return row;
    }));
    const currency = document.getElementById('financeAccountCurrency');
    if (!currency.options.length) financeOptions(currency, CURRENCIES.map(c => ({ id: c, name: c })), 'MXN');
}

document.getElementById('financeAccountList').addEventListener('change', (event) => {
    const row = event.target.closest('[data-account-id]');
    if (!row) return;
    const id = row.dataset.accountId;
    if (event.target.classList.contains('config-name')) {
        const name = event.target.value.trim();
        if (!name) return refreshFinanceConfig();
        financeConfigAction(() => apiFetch(`/api/finance/accounts/${id}`, { method: 'PATCH', json: { name } }));
    } else if (event.target.classList.contains('finance-account-kind')) {
        financeConfigAction(() => apiFetch(`/api/finance/accounts/${id}`, { method: 'PATCH', json: { kind: event.target.value } }));
    }
});

document.getElementById('financeAccountList').addEventListener('click', async (event) => {
    const button = event.target.closest('button');
    const row = event.target.closest('[data-account-id]');
    if (!button || !row) return;
    const account = financeAccount(Number(row.dataset.accountId));
    if (!account) return;
    const url = `/api/finance/accounts/${account.id}`;
    if (button.classList.contains('finance-default')) {
        financeConfigAction(() => apiFetch(url, { method: 'PATCH', json: { is_default: true } }));
    } else if (button.classList.contains('finance-archive')) {
        financeConfigAction(() => apiFetch(url, { method: 'PATCH', json: { is_active: !account.is_active } }));
    } else if (button.classList.contains('finance-account-delete')) {
        if (!await confirmDialog(`¿Eliminar la cuenta "${account.name}"?`, { confirmLabel: 'Eliminar', danger: true })) return;
        financeConfigAction(() => apiFetch(url, { method: 'DELETE' }));
    }
});

document.getElementById('financeAccountForm').addEventListener('submit', (event) => {
    event.preventDefault();
    const nameInput = document.getElementById('financeAccountName');
    const last4Input = document.getElementById('financeAccountLast4');
    const name = nameInput.value.trim();
    const last4 = last4Input.value.trim();
    if (!name) return;
    if (last4 && !/^\d{4}$/.test(last4)) {
        showError(financeConfigError, 'Escribe solo los últimos 4 dígitos de la tarjeta.');
        return;
    }
    financeConfigAction(async () => {
        await apiFetch('/api/finance/accounts', {
            method: 'POST',
            json: {
                name, last4: last4 || null,
                kind: document.getElementById('financeAccountKind').value,
                currency: document.getElementById('financeAccountCurrency').value,
            },
        });
        nameInput.value = '';
        last4Input.value = '';
    });
});

// --- Categorías ---

function financeCategoryRow(c) {
    const row = el('div', 'config-row');
    row.dataset.categoryId = String(c.id);
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
    const count = el('span', 'config-type', c.tx_count ? `${c.tx_count} ${c.tx_count === 1 ? 'mov.' : 'movs.'}` : '');
    const remove = configButton('config-action danger finance-category-delete', `Eliminar ${c.name}`, '×');
    row.append(color, name, count, remove);
    return row;
}

function renderFinanceCategories() {
    document.getElementById('financeExpenseCategories')
        .replaceChildren(...financeKindCategories('expense').map(financeCategoryRow));
    document.getElementById('financeIncomeCategories')
        .replaceChildren(...financeKindCategories('income').map(financeCategoryRow));
}

['financeExpenseCategories', 'financeIncomeCategories'].forEach(id => {
    const list = document.getElementById(id);
    list.addEventListener('change', (event) => {
        const row = event.target.closest('[data-category-id]');
        if (!row) return;
        const url = `/api/finance/categories/${row.dataset.categoryId}`;
        if (event.target.classList.contains('config-color')) {
            financeConfigAction(() => apiFetch(url, { method: 'PATCH', json: { color: event.target.value } }));
        } else if (event.target.classList.contains('config-name')) {
            const name = event.target.value.trim();
            if (!name) return refreshFinanceConfig();
            financeConfigAction(() => apiFetch(url, { method: 'PATCH', json: { name } }));
        }
    });
    list.addEventListener('click', async (event) => {
        const button = event.target.closest('.finance-category-delete');
        const row = event.target.closest('[data-category-id]');
        if (!button || !row) return;
        const category = financeCategory(Number(row.dataset.categoryId));
        if (!category) return;
        if (!await confirmDialog(`¿Eliminar la categoría "${category.name}"?`, { confirmLabel: 'Eliminar', danger: true })) return;
        financeConfigAction(() => apiFetch(`/api/finance/categories/${category.id}`, { method: 'DELETE' }));
    });
});

document.getElementById('financeCategoryForm').addEventListener('submit', (event) => {
    event.preventDefault();
    const nameInput = document.getElementById('financeCategoryName');
    const name = nameInput.value.trim();
    if (!name) return;
    financeConfigAction(async () => {
        await apiFetch('/api/finance/categories', {
            method: 'POST',
            json: {
                name,
                color: document.getElementById('financeCategoryColor').value,
                kind: document.getElementById('financeCategoryKind').value,
            },
        });
        nameInput.value = '';
    });
});

// --- Fijos ---

function financeFixedText(rc) {
    const account = financeAccount(rc.account_id);
    const days = rc.frequency === 'semimonthly' && rc.first_day
        ? ` (${financeDayText(rc.first_day)} y ${financeDayText(rc.second_day)})` : '';
    const parts = [`${formatMoney(rc.amount_cents, rc.currency)} ${FINANCE_FREQUENCY_LABELS[rc.frequency]}${days}`];
    if (account) parts.push(account.name);
    if (rc.paused) parts.push('en pausa');
    else if (rc.next_date) {
        const d = financeDate(rc.next_date);
        parts.push(`siguiente: ${d.getDate()} ${FINANCE_MONTHS_SHORT[d.getMonth()]} ${d.getFullYear()}`);
    } else parts.push('terminado');
    return parts.join(' · ');
}

function renderFinanceFixed() {
    const list = document.getElementById('financeFixedList');
    if (!financeState.recurring.length) {
        list.replaceChildren(el('li', 'costs-hint', 'Todavía no tienes fijos.'));
    } else {
        list.replaceChildren(...financeState.recurring.map(rc => {
            const item = el('li', `recurring-item${rc.paused ? ' paused' : ''}`);
            item.dataset.fixedId = String(rc.id);
            const text = el('div', 'recurring-text');
            text.append(el('strong', '', `${rc.kind === 'income' ? '＋ ' : ''}${rc.concept}`), el('small', '', financeFixedText(rc)));
            const actions = el('div', 'recurring-actions');
            actions.append(
                configButton('config-action finance-fixed-edit', `Editar ${rc.concept}`, '✎'),
                configButton('config-action finance-fixed-pause', rc.paused ? `Reanudar ${rc.concept}` : `Pausar ${rc.concept}`,
                    rc.paused ? '▶' : '⏸'),
                configButton('config-action danger finance-fixed-delete', `Eliminar ${rc.concept}`, '×'),
            );
            item.append(text, actions);
            return item;
        }));
    }
    renderFinanceFixedSelects();
}

function setFinanceFixedKind(kind) {
    financeState.fixedKind = kind;
    document.querySelectorAll('#financeFixedKind [data-kind]').forEach(button => {
        button.setAttribute('aria-pressed', String(button.dataset.kind === kind));
    });
    renderFinanceFixedSelects();
}

function renderFinanceFixedSelects() {
    const editing = financeState.editingFixed;
    const accountSelect = document.getElementById('financeFixedAccount');
    const categorySelect = document.getElementById('financeFixedCategory');
    const accounts = financeUsableAccounts(editing ? editing.account_id : null);
    const accountId = Number(accountSelect.value) || (editing ? editing.account_id
        : ((accounts.find(a => a.is_default) || accounts[0] || {}).id));
    financeOptions(accountSelect, accounts, accountId, financeAccountLabel);
    const categories = financeKindCategories(financeState.fixedKind);
    const current = Number(categorySelect.value) || (editing ? editing.category_id : null);
    const keep = categories.some(c => c.id === current) ? current : (categories[categories.length - 1] || {}).id;
    financeOptions(categorySelect, categories, keep);
}

function resetFinanceFixedForm() {
    financeState.editingFixed = null;
    const form = document.getElementById('financeFixedForm');
    form.reset();
    document.getElementById('financeFixedFormTitle').textContent = 'Nuevo fijo';
    document.getElementById('financeFixedStartLabel').textContent = 'Primer cobro';
    document.getElementById('financeFixedSave').textContent = 'Agregar';
    document.getElementById('financeFixedCancel').hidden = true;
    document.getElementById('financeFixedStart').value = financeToday();
    document.getElementById('financeFixedKind').hidden = false;
    document.getElementById('financeFixedAccount').value = '';
    document.getElementById('financeFixedCategory').value = '';
    setFinanceFixedDays(15, 31);
    setFinanceFixedKind('expense');
}

// Los días de una quincenal: solo se ven con Quincena
function setFinanceFixedDays(first, second) {
    document.getElementById('financeFixedFirstDay').value = String(first);
    document.getElementById('financeFixedSecondDay').value = String(second);
    syncFinanceFixedDays();
}

function syncFinanceFixedDays() {
    document.getElementById('financeFixedDaysField').hidden =
        document.getElementById('financeFixedFrequency').value !== 'semimonthly';
}

function editFinanceFixed(rc) {
    financeState.editingFixed = rc;
    document.getElementById('financeFixedFormTitle').textContent = `Editar "${rc.concept}"`;
    document.getElementById('financeFixedConcept').value = rc.concept;
    document.getElementById('financeFixedAmount').value = (rc.amount_cents / 100).toFixed(2);
    document.getElementById('financeFixedFrequency').value = rc.frequency;
    setFinanceFixedDays(rc.first_day || 15, rc.second_day || 31);
    // Con cobros ya anotados, la fecha es la del siguiente
    document.getElementById('financeFixedStartLabel').textContent = rc.generated ? 'Siguiente cobro' : 'Primer cobro';
    document.getElementById('financeFixedStart').value = (rc.generated ? rc.next_date : rc.start_date) || rc.start_date;
    document.getElementById('financeFixedSave').textContent = 'Guardar';
    document.getElementById('financeFixedCancel').hidden = false;
    // El tipo no cambia: sus cobros anotados son de ese tipo
    document.getElementById('financeFixedKind').hidden = true;
    document.getElementById('financeFixedAccount').value = '';
    document.getElementById('financeFixedCategory').value = '';
    setFinanceFixedKind(rc.kind);
    document.getElementById('financeFixedConcept').focus();
}

document.querySelectorAll('#financeFixedKind [data-kind]').forEach(button => {
    button.addEventListener('click', () => setFinanceFixedKind(button.dataset.kind));
});
document.getElementById('financeFixedCancel').addEventListener('click', resetFinanceFixedForm);
document.getElementById('financeFixedFrequency').addEventListener('change', syncFinanceFixedDays);

document.getElementById('financeFixedForm').addEventListener('submit', (event) => {
    event.preventDefault();
    const cents = parseMoneyCents(document.getElementById('financeFixedAmount').value);
    const concept = document.getElementById('financeFixedConcept').value.trim();
    const start = document.getElementById('financeFixedStart').value;
    if (cents == null || cents <= 0) {
        showError(financeConfigError, 'Escribe el monto: un número mayor que cero.');
        return;
    }
    if (!concept || !start) {
        showError(financeConfigError, 'Escribe el concepto y la fecha del cobro.');
        return;
    }
    const fields = {
        concept, amount_cents: Math.abs(cents),
        frequency: document.getElementById('financeFixedFrequency').value,
        account_id: Number(document.getElementById('financeFixedAccount').value),
        category_id: Number(document.getElementById('financeFixedCategory').value),
    };
    if (fields.frequency === 'semimonthly') {
        const days = ['financeFixedFirstDay', 'financeFixedSecondDay'].map(id => Number(document.getElementById(id).value));
        if (days.some(d => !Number.isInteger(d) || d < 1 || d > 31)) {
            showError(financeConfigError, 'Los días de pago van del 1 al 31 (31 es el último día).');
            return;
        }
        [fields.first_day, fields.second_day] = days;
    }
    const editing = financeState.editingFixed;
    financeConfigAction(async () => {
        if (editing) {
            const shown = (editing.generated ? editing.next_date : editing.start_date) || editing.start_date;
            // La fecha solo viaja si cambió: con cobros anotados, mandarla vuelve a anclar la serie
            if (start !== shown || fields.frequency !== editing.frequency) fields.start_date = start;
            await apiFetch(`/api/finance/recurring/${editing.id}`, { method: 'PATCH', json: fields });
        } else {
            await apiFetch('/api/finance/recurring', {
                method: 'POST', json: { ...fields, kind: financeState.fixedKind, start_date: start },
            });
        }
        resetFinanceFixedForm();
    });
});

document.getElementById('financeFixedList').addEventListener('click', async (event) => {
    const button = event.target.closest('button');
    const item = event.target.closest('[data-fixed-id]');
    if (!button || !item) return;
    const rc = financeState.recurring.find(r => r.id === Number(item.dataset.fixedId));
    if (!rc) return;
    const url = `/api/finance/recurring/${rc.id}`;
    if (button.classList.contains('finance-fixed-edit')) {
        editFinanceFixed(rc);
    } else if (button.classList.contains('finance-fixed-pause')) {
        financeConfigAction(() => apiFetch(url, { method: 'PATCH', json: { paused: !rc.paused } }));
    } else if (button.classList.contains('finance-fixed-delete')) {
        const ok = await confirmDialog(`¿Dejar de anotar "${rc.concept}"? Los movimientos que ya anotó se quedan.`,
            { confirmLabel: 'Eliminar', danger: true });
        if (!ok) return;
        if (financeState.editingFixed && financeState.editingFixed.id === rc.id) resetFinanceFixedForm();
        financeConfigAction(() => apiFetch(url, { method: 'DELETE' }));
    }
});

document.getElementById('financeOrganize').addEventListener('click', openFinanceConfig);
document.getElementById('financeConfigClose').addEventListener('click', closeFinanceConfig);
financeConfigModal.querySelector('.modal-overlay').addEventListener('click', closeFinanceConfig);
resetFinanceFixedForm();

// ============================================
// Ciclo de vida
// ============================================

function resetFinance() {
    Object.assign(financeState, {
        day: null, summary: null, transactions: [], accounts: [], categories: [], recurring: [],
        loaded: false, editing: null, pending: null, editingFixed: null, salaryStep: false,
    });
    financeConceptCategory.clear();
    financeSummaryEl.replaceChildren();
    financeListEl.replaceChildren();
    [financeTxModal, financeImportModal, financeConfigModal].forEach(hideModal);
    setViewVisible('finance', false);
    document.getElementById('moduleFinanceOption').hidden = true;
    document.getElementById('settingsFinanceItem').hidden = true;
    document.getElementById('settingsFinancePage').hidden = true;
}

window.appDataHooks.push(applyFinanceModule);
window.modulesChangedHooks.push(() => {
    applyFinanceModule();
    if (isFinanceVisible()) loadFinance();
});
// Al entrar a la vista se pide de nuevo: un fijo pudo anotarse desde la última vez
window.viewChangedHooks.push(viewId => {
    if (viewId === 'finance') loadFinance();
});
// Al principio, como Costos: ocultar la vista pasa por goToView(), que recuerda la pestaña
window.appLogoutHooks.unshift(resetFinance);
