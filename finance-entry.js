// ============================================
// Finanzas: la hoja del monto (agregar o editar un movimiento)
// ============================================
//
// Tocar una categoría abre esta hoja desde abajo: arriba dos bandas de color
// (de dónde sale y a dónde va el dinero; tocarlas cambia la cuenta o la
// categoría, y elegir una cuenta como destino la vuelve transferencia), el
// monto grande, Notas…, y un teclado con calculadora. El 📅 abre la fecha
// (Ayer, Hoy o el calendario) y la periodicidad: con una, se guarda un fijo
// cuyo primer cobro es este movimiento. La calculadora no usa eval: un
// intérprete de las cuatro operaciones.

const finEntry = {
    tx: null,           // el movimiento que se edita, o null
    kind: 'expense',    // expense | income | transfer
    accountId: null,    // de dónde (gasto, transferencia) o a dónde (ingreso)
    categoryId: null,
    toAccountId: null,  // transferencia
    expr: '',           // lo tecleado: "120+35.5"
    date: null,
    frequency: '',      // '' = no se repite
    picking: null,      // qué banda abrió el selector: 'from' | 'to'
};

const finEntrySheet = document.getElementById('finEntry');
const FIN_OPS = { '+': '+', '-': '−', '*': '×', '/': '÷' };

// ============================================
// La calculadora
// ============================================

// "120+35.5*2" → centavos (con × y ÷ antes que + y −); null si no se puede
function finEvaluate(expr) {
    const tokens = expr.match(/\d+(?:\.\d*)?|\.\d+|[+\-*/]/g);
    if (!tokens) return null;
    while (tokens.length && '+-*/'.includes(tokens[tokens.length - 1])) tokens.pop();   // "12+" = 12
    if (!tokens.length) return null;
    const values = [];
    const ops = [];
    for (const token of tokens) {
        if ('+-*/'.includes(token)) ops.push(token);
        else values.push(Number(token));
    }
    if (values.some(v => !Number.isFinite(v)) || values.length !== ops.length + 1) return null;
    // Primero × y ÷
    const sums = [values[0]];
    const sumOps = [];
    ops.forEach((op, i) => {
        const v = values[i + 1];
        if (op === '*') sums[sums.length - 1] *= v;
        else if (op === '/') sums[sums.length - 1] = v === 0 ? NaN : sums[sums.length - 1] / v;
        else { sumOps.push(op); sums.push(v); }
    });
    let result = sums[0];
    sumOps.forEach((op, i) => { result = op === '+' ? result + sums[i + 1] : result - sums[i + 1]; });
    return Number.isFinite(result) ? Math.round(result * 100) : null;
}

function finPressKey(key) {
    let expr = finEntry.expr;
    const lastNumber = expr.split(/[+\-*/]/).pop();
    if (key === 'back') {
        expr = expr.slice(0, -1);
    } else if ('+-*/'.includes(key)) {
        if (!expr) return;
        // Un operador seguido reemplaza al anterior
        expr = '+-*/'.includes(expr.slice(-1)) ? expr.slice(0, -1) + key : expr + key;
    } else if (key === '.') {
        if (lastNumber.includes('.')) return;
        expr += lastNumber === '' ? '0.' : '.';
    } else {
        // Dígitos: como mucho 2 decimales y 12 cifras por número
        const decimals = lastNumber.includes('.') ? lastNumber.split('.')[1].length : -1;
        if (decimals >= 2 || lastNumber.replace('.', '').length >= 12) return;
        if (lastNumber === '0' && key !== '00') expr = expr.slice(0, -1);
        if (key === '00' && (lastNumber === '' || lastNumber === '0')) return;
        expr += key;
    }
    finEntry.expr = expr;
    finRenderAmount();
}

function finRenderAmount() {
    const expr = finEntry.expr;
    const pretty = expr.replace(/[+\-*/]/g, op => ` ${FIN_OPS[op]} `);
    document.getElementById('finEntryExpr').textContent = `$ ${pretty || '0'}`;
    const hasOp = /[+\-*/]\d/.test(expr);
    const cents = finEvaluate(expr);
    document.getElementById('finEntryResult').textContent = hasOp && cents != null ? `= ${formatMoney(cents, finEntryCurrency())}` : '';
}

function finEntryCurrency() {
    const account = finAccount(finEntry.accountId);
    return account ? account.currency : finMainCurrency();
}

// El teclado: 5 columnas; ✓ ocupa dos filas
const FIN_KEYS = [
    ['/', '÷', 'op'], ['7'], ['8'], ['9'], ['back', '', 'fn'],
    ['*', '×', 'op'], ['4'], ['5'], ['6'], ['date', '', 'fn'],
    ['-', '−', 'op'], ['1'], ['2'], ['3'], ['ok', '', 'ok'],
    ['+', '+', 'op'], ['00'], ['0'], ['.', '.'],
];

function finBuildKeypad() {
    const pad = document.getElementById('finKeypad');
    pad.replaceChildren(...FIN_KEYS.map(([key, label, kind]) => {
        const button = el('button', `fin-key${kind ? ` ${kind}` : ''}`);
        button.type = 'button';
        button.dataset.key = key;
        if (key === 'back') {
            button.appendChild(financeIcon('delete', 22));
            button.setAttribute('aria-label', 'Borrar');
        } else if (key === 'date') {
            button.appendChild(financeIcon('calendar', 22));
            button.setAttribute('aria-label', 'Fecha y periodicidad');
        } else if (key === 'ok') {
            button.appendChild(financeIcon('check', 28));
            button.setAttribute('aria-label', 'Guardar');
        } else {
            button.textContent = label || key;
        }
        return button;
    }));
}

document.getElementById('finKeypad').addEventListener('click', (event) => {
    const button = event.target.closest('[data-key]');
    if (!button) return;
    const key = button.dataset.key;
    if (key === 'ok') saveFinEntry();
    else if (key === 'date') openFinDateSheet();
    else finPressKey(key);
});

// En computadora, el teclado de verdad también sirve (salvo escribiendo una nota)
document.addEventListener('keydown', (event) => {
    if (finEntrySheet.classList.contains('hidden') || finSheets[finSheets.length - 1] !== finEntrySheet) return;
    if (event.target.closest('input, select, textarea')) return;
    const map = { Backspace: 'back', Enter: 'ok', ',': '.' };
    const key = map[event.key] || event.key;
    if (key === 'ok') {
        event.preventDefault();
        saveFinEntry();
    } else if (/^[0-9.]$/.test(key) || '+-*/'.includes(key) || key === 'back') {
        event.preventDefault();
        finPressKey(key);
    }
});

// ============================================
// Abrir y pintar
// ============================================

// { kind, categoryId } para uno nuevo desde un círculo; { tx } para editar
function openFinEntry({ kind = 'expense', categoryId = null, tx = null } = {}) {
    const accounts = finActiveAccounts();
    const defaultAccount = accounts.find(a => a.is_default) || accounts[0];
    const s = finState.summary;
    const today = finToday();
    Object.assign(finEntry, {
        tx,
        kind: tx ? tx.kind : kind,
        accountId: tx ? tx.account_id : (defaultAccount && defaultAccount.id),
        categoryId: tx ? tx.category_id : (categoryId || (finKindCategories(kind)[0] || {}).id || null),
        toAccountId: tx ? tx.to_account_id : null,
        expr: tx ? String(tx.amount_cents / 100) : '',
        // Al agregar: hoy si el periodo que se ve lo incluye; si no, su primer día
        date: tx ? tx.tx_date : (!s || (s.date_from <= today && today <= s.date_to) ? today : s.date_from),
        frequency: '',
        picking: null,
    });
    document.getElementById('finEntryNotes').value = tx && tx.concept !== finEntryDefaultConcept() ? tx.concept : '';
    document.getElementById('finEntryDelete').hidden = !tx;
    document.getElementById('finEntryError').classList.add('hidden');
    finRenderEntry();
    finRenderAmount();
    openFinSheet(finEntrySheet);
}

// El concepto que se guarda si no se escribe nota: el nombre de la categoría
function finEntryDefaultConcept() {
    if (finEntry.kind === 'transfer') return 'Transferencia';
    const category = finCategory(finEntry.categoryId);
    return category ? category.name : 'Movimiento';
}

function finSetBand(side, { label, name, icon, color }) {
    const band = document.getElementById(side === 'from' ? 'finBandFrom' : 'finBandTo');
    band.style.setProperty('--band', color);
    document.getElementById(side === 'from' ? 'finBandFromLabel' : 'finBandToLabel').textContent = label;
    document.getElementById(side === 'from' ? 'finBandFromName' : 'finBandToName').textContent = name;
    document.getElementById(side === 'from' ? 'finBandFromIcon' : 'finBandToIcon')
        .replaceChildren(financeIcon(icon, 22));
}

function finAccountBand(label, id) {
    const account = finAccount(id);
    return account
        ? { label, name: account.name, icon: finAccountIcon(account), color: finAccountColor(account) }
        : { label, name: 'Elige una cuenta', icon: 'wallet', color: FIN_NEUTRAL };
}

function finCategoryBand(label, id) {
    const category = finCategory(id);
    return category
        ? { label, name: category.name, icon: finCategoryIcon(category), color: finCategoryColor(category) }
        : { label, name: 'Elige una categoría', icon: 'ellipsis', color: FIN_NEUTRAL };
}

function finRenderEntry() {
    const k = finEntry.kind;
    if (k === 'income') {
        finSetBand('from', finCategoryBand('De categoría', finEntry.categoryId));
        finSetBand('to', finAccountBand('A cuenta', finEntry.accountId));
    } else if (k === 'transfer') {
        finSetBand('from', finAccountBand('De cuenta', finEntry.accountId));
        finSetBand('to', finAccountBand('A cuenta', finEntry.toAccountId));
    } else {
        finSetBand('from', finAccountBand('De cuenta', finEntry.accountId));
        finSetBand('to', finCategoryBand('A categoría', finEntry.categoryId));
    }
    const kindEl = document.getElementById('finEntryKind');
    kindEl.textContent = { expense: 'Gasto', income: 'Ingreso', transfer: 'Transferencia' }[k];
    kindEl.dataset.kind = k;
    finEntrySheet.dataset.kind = k;
    // La fecha, y si se repite
    const today = finToday();
    const d = finEntry.date;
    const prefix = d === today ? 'Hoy, ' : d === finAddDays(today, -1) ? 'Ayer, ' : '';
    document.getElementById('finEntryDate').textContent = `${prefix}${finShortDate(d)}`;
    const flags = document.getElementById('finEntryFlags');
    flags.replaceChildren();
    if (finEntry.frequency) {
        const flag = el('span', 'fin-flag');
        flag.append(financeIcon('repeat', 14), document.createTextNode(` ${finRepeatText(finEntry.frequency, d)}`));
        flags.appendChild(flag);
    }
    finRenderAmount();
}

// ============================================
// Elegir cuenta o categoría
// ============================================

const finPicker = document.getElementById('finPicker');

function finPickerItem(dataset, name, badge, sub = '') {
    const button = el('button', 'fin-pick');
    button.type = 'button';
    Object.assign(button.dataset, dataset);
    button.append(badge, el('span', 'fin-pick-name', name));
    if (sub) button.appendChild(el('small', 'fin-pick-sub', sub));
    return button;
}

function finAccountPicks(skipId) {
    return finActiveAccounts().filter(a => a.id !== skipId).map(a => finPickerItem(
        { pickAccount: String(a.id) }, a.name,
        finBadge(finAccountIcon(a), finAccountColor(a), { square: true }), formatMoney(a.balance_cents, a.currency)));
}

function finCategoryPicks(kind) {
    return finKindCategories(kind).map(c => finPickerItem(
        { pickCategory: String(c.id) }, c.name, finBadge(finCategoryIcon(c), finCategoryColor(c))));
}

function openFinPicker(side) {
    finEntry.picking = side;
    const k = finEntry.kind;
    const grid = document.getElementById('finPickerGrid');
    const title = document.getElementById('finPickerTitle');
    const accountSide = (k === 'income' && side === 'to') || (k !== 'income' && side === 'from');
    if (accountSide) {
        title.textContent = 'De qué cuenta';
        if (k === 'income') title.textContent = 'A qué cuenta';
        grid.replaceChildren(...finAccountPicks(null));
    } else if (k === 'income') {
        title.textContent = 'De qué categoría';
        grid.replaceChildren(...finCategoryPicks('income'));
    } else {
        // El destino de un gasto: una categoría, o una cuenta (transferencia)
        title.textContent = 'A qué categoría';
        const accounts = finAccountPicks(finEntry.accountId);
        grid.replaceChildren(...finCategoryPicks('expense'),
            ...(accounts.length ? [el('p', 'fin-pick-section', 'O a otra cuenta tuya (transferencia)'), ...accounts] : []));
    }
    openFinSheet(finPicker);
}

document.getElementById('finBandFrom').addEventListener('click', () => openFinPicker('from'));
document.getElementById('finBandTo').addEventListener('click', () => openFinPicker('to'));

document.getElementById('finPickerGrid').addEventListener('click', (event) => {
    const item = event.target.closest('.fin-pick');
    if (!item) return;
    const side = finEntry.picking;
    const k = finEntry.kind;
    if (item.dataset.pickAccount) {
        const id = Number(item.dataset.pickAccount);
        const accountSide = (k === 'income' && side === 'to') || (k !== 'income' && side === 'from');
        if (accountSide) {
            finEntry.accountId = id;
            if (finEntry.toAccountId === id) finEntry.toAccountId = null;
        } else {
            // Una cuenta como destino: es una transferencia
            finEntry.kind = 'transfer';
            finEntry.toAccountId = id;
            finEntry.frequency = '';
        }
    } else if (item.dataset.pickCategory) {
        finEntry.categoryId = Number(item.dataset.pickCategory);
        if (k === 'transfer') {
            finEntry.kind = 'expense';
            finEntry.toAccountId = null;
        }
    }
    closeFinSheet(finPicker);
    finRenderEntry();
});

// ============================================
// Fecha y periodicidad
// ============================================

const finDateSheet = document.getElementById('finDateSheet');

function finPayDay(iso) {
    const d = finDate(iso);
    const last = new Date(d.getFullYear(), d.getMonth() + 1, 0).getDate();
    return d.getDate() === last ? 31 : d.getDate();
}

// El otro pago de una quincena, para proponerlo: quince días antes o después
function finOtherPayDay(day) {
    if (day === 31) return 15;
    if (day === 15) return 31;
    return day < 15 ? day + 15 : day - 15;
}

function finDayText(day) {
    return day >= 31 ? 'el último día' : `el ${day}`;
}

function finRepeatText(frequency, iso) {
    const d = finDate(iso);
    if (frequency === 'monthly') {
        return `el ${d.getDate()} de cada mes${d.getDate() > 28 ? ' (o el último, si el mes es más corto)' : ''}`;
    }
    if (frequency === 'semimonthly') {
        const day = finPayDay(iso);
        const [first, second] = [day, finOtherPayDay(day)].sort((a, b) => a - b);
        return `${finDayText(first)} y ${finDayText(second)} de cada mes`;
    }
    return `cada ${d.getDate()} de ${FIN_MONTHS[d.getMonth()]}`;
}

function openFinDateSheet() {
    const today = finToday();
    document.getElementById('finDateToday').textContent = finShortDate(today);
    document.getElementById('finDateYesterday').textContent = finShortDate(finAddDays(today, -1));
    document.getElementById('finDateInput').value = finEntry.date;
    const select = document.getElementById('finRepeatSelect');
    select.value = finEntry.frequency;
    // Repetir es de un gasto o ingreso nuevo: editar toca solo ese movimiento
    document.getElementById('finRepeatTile').hidden = Boolean(finEntry.tx) || finEntry.kind === 'transfer';
    finSyncDateSheet();
    openFinSheet(finDateSheet);
}

function finSyncDateSheet() {
    const today = finToday();
    document.querySelectorAll('#finDateSheet [data-day]').forEach(tile => {
        tile.classList.toggle('active', finAddDays(today, Number(tile.dataset.day)) === finEntry.date);
    });
    const frequency = document.getElementById('finRepeatSelect').value;
    document.getElementById('finRepeatHint').textContent = frequency
        ? `Se anota solo ${finRepeatText(frequency, finEntry.date)}.` : '';
}

document.querySelectorAll('#finDateSheet [data-day]').forEach(tile => {
    tile.addEventListener('click', () => {
        finEntry.date = finAddDays(finToday(), Number(tile.dataset.day));
        document.getElementById('finDateInput').value = finEntry.date;
        finSyncDateSheet();
    });
});
document.getElementById('finDateInput').addEventListener('change', (event) => {
    if (event.target.value) finEntry.date = event.target.value;
    finSyncDateSheet();
});
document.getElementById('finRepeatSelect').addEventListener('change', finSyncDateSheet);
document.getElementById('finDateDone').addEventListener('click', () => {
    finEntry.frequency = document.getElementById('finRepeatTile').hidden ? '' : document.getElementById('finRepeatSelect').value;
    closeFinSheet(finDateSheet);
    finRenderEntry();
});
finSheetDismiss.set('finDateSheet', () => document.getElementById('finDateDone').click());

// ============================================
// Guardar y borrar
// ============================================

async function saveFinEntry() {
    const errorEl = document.getElementById('finEntryError');
    errorEl.classList.add('hidden');
    const cents = finEvaluate(finEntry.expr);
    if (cents == null || cents <= 0) {
        showError(errorEl, 'Escribe el monto: un número mayor que cero.');
        return;
    }
    const k = finEntry.kind;
    if (!finEntry.accountId) return showError(errorEl, 'Elige la cuenta.');
    if (k === 'transfer' && !finEntry.toAccountId) return showError(errorEl, 'Elige la cuenta de destino.');
    if (k !== 'transfer' && !finEntry.categoryId) return showError(errorEl, 'Elige la categoría.');
    const concept = document.getElementById('finEntryNotes').value.trim() || finEntryDefaultConcept();
    const payload = {
        kind: k, amount_cents: cents, tx_date: finEntry.date, concept,
        account_id: finEntry.accountId,
        category_id: k === 'transfer' ? null : finEntry.categoryId,
        to_account_id: k === 'transfer' ? finEntry.toAccountId : null,
    };
    const ok = document.querySelector('#finKeypad [data-key="ok"]');
    ok.disabled = true;
    try {
        if (finEntry.tx) {
            await apiFetch(`/api/finance/transactions/${finEntry.tx.id}`, { method: 'PATCH', json: payload });
        } else if (finEntry.frequency) {
            // Un fijo cuyo primer cobro es este: el servidor lo anota en su fecha
            const fields = {
                kind: k, account_id: payload.account_id, category_id: payload.category_id, concept,
                amount_cents: cents, frequency: finEntry.frequency, start_date: payload.tx_date,
            };
            if (finEntry.frequency === 'semimonthly') {
                const day = finPayDay(payload.tx_date);
                const other = finOtherPayDay(day);
                Object.assign(fields, { first_day: Math.min(day, other), second_day: Math.max(day, other) });
            }
            await apiFetch('/api/finance/recurring', { method: 'POST', json: fields });
        } else {
            await apiFetch('/api/finance/transactions', { method: 'POST', json: payload });
        }
        closeFinSheet(finEntrySheet);
        await finLoad();
    } catch (error) {
        showError(errorEl, error.message);
    } finally {
        ok.disabled = false;
    }
}

document.getElementById('finEntryDelete').addEventListener('click', async () => {
    const tx = finEntry.tx;
    if (!tx) return;
    const ok = await confirmDialog(tx.recurring_id
        ? `¿Borrar este cobro de "${tx.concept}"? El fijo sigue: no vuelve a anotar este.`
        : `¿Borrar "${tx.concept}"?`, { confirmLabel: 'Borrar', danger: true });
    if (!ok) return;
    try {
        await apiFetch(`/api/finance/transactions/${tx.id}`, { method: 'DELETE' });
        closeFinSheet(finEntrySheet);
        await finLoad();
    } catch (error) {
        showError(document.getElementById('finEntryError'), error.message);
    }
});
document.getElementById('finEntryCancel').addEventListener('click', () => closeFinSheet(finEntrySheet));
document.getElementById('finEntryDate').addEventListener('click', openFinDateSheet);

finBuildKeypad();
