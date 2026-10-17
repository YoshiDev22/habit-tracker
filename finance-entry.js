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
// intérprete de las cuatro operaciones. Un gasto o ingreso puede dividirse en
// varias categorías (las partes suman el monto), y una compra con tarjeta de
// crédito, ir a meses sin intereses (el plan se guarda después del movimiento).

const finEntry = {
    tx: null,           // el movimiento que se edita, o null
    kind: 'expense',    // expense | income | transfer
    accountId: null,    // de dónde (gasto, transferencia) o a dónde (ingreso)
    categoryId: null,
    toAccountId: null,  // transferencia
    expr: '',           // lo tecleado: "120+35.5"
    date: null,
    frequency: '',      // '' = no se repite
    msi: '',            // '' o los meses sin intereses (compra con tarjeta de crédito)
    prefilled: false,   // el monto lo propuso la app (Pagar): el primer número lo reemplaza
    payOptions: [],     // al pagar una tarjeta: [{label, cents}] para elegir de un toque
    splits: null,       // null, o las partes: [{category_id, amount_cents}]
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
    // Un monto propuesto (Pagar) se reemplaza con el primer número; un operador
    // lo conserva para sumarle ("300 + 200": pagar de más)
    if (finEntry.prefilled && key !== 'back' && !'+-*/'.includes(key)) finEntry.expr = '';
    if (finEntry.prefilled && key === 'back') finEntry.expr = '';
    finEntry.prefilled = false;
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
    const exprEl = document.getElementById('finEntryExpr');
    exprEl.textContent = `$ ${pretty || '0'}`;
    exprEl.classList.toggle('prefilled', finEntry.prefilled);
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

// { kind, categoryId } para uno nuevo desde un círculo; { tx } para editar;
// { kind: 'transfer', toAccountId, amountCents } para pagar una tarjeta
function openFinEntry({ kind = 'expense', categoryId = null, tx = null, toAccountId = null, amountCents = null,
    payOptions = [] } = {}) {
    const accounts = finActiveAccounts();
    // Para pagar una tarjeta, de entrada la primera cuenta que no sea de crédito
    const defaultAccount = kind === 'transfer'
        ? accounts.find(a => a.kind !== 'credit' && a.id !== toAccountId) || accounts.find(a => a.id !== toAccountId)
        : accounts.find(a => a.is_default) || accounts[0];
    const s = finState.summary;
    const today = finToday();
    Object.assign(finEntry, {
        tx,
        kind: tx ? tx.kind : kind,
        accountId: tx ? tx.account_id : (defaultAccount && defaultAccount.id),
        categoryId: tx ? tx.category_id : (categoryId || (finKindCategories(kind)[0] || {}).id || null),
        toAccountId: tx ? tx.to_account_id : toAccountId,
        expr: tx ? String(tx.amount_cents / 100) : (amountCents ? String(amountCents / 100) : ''),
        // Al agregar: hoy si el periodo que se ve lo incluye; si no, su primer día
        date: tx ? tx.tx_date : (!s || (s.date_from <= today && today <= s.date_to) ? today : s.date_from),
        frequency: '',
        msi: '',
        prefilled: Boolean(amountCents) && !tx,
        payOptions,
        splits: tx && tx.splits && tx.splits.length ? tx.splits.map(p => ({ ...p })) : null,
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

// Dividido: la banda de la categoría dice cuántas
function finSplitBand(label) {
    return { label, name: `${finEntry.splits.length} categorías`, icon: 'split', color: FIN_NEUTRAL };
}

function finRenderEntry() {
    const k = finEntry.kind;
    if (k === 'transfer') finEntry.splits = null;
    if (k === 'income') {
        finSetBand('from', finEntry.splits ? finSplitBand('De categorías') : finCategoryBand('De categoría', finEntry.categoryId));
        finSetBand('to', finAccountBand('A cuenta', finEntry.accountId));
    } else if (k === 'transfer') {
        finSetBand('from', finAccountBand('De cuenta', finEntry.accountId));
        finSetBand('to', finAccountBand('A cuenta', finEntry.toAccountId));
    } else {
        finSetBand('from', finAccountBand('De cuenta', finEntry.accountId));
        finSetBand('to', finEntry.splits ? finSplitBand('A categorías') : finCategoryBand('A categoría', finEntry.categoryId));
    }
    const splitBtn = document.getElementById('finSplitBtn');
    splitBtn.hidden = k === 'transfer';
    splitBtn.lastChild.textContent = finEntry.splits ? `Dividido en ${finEntry.splits.length}` : 'Dividir en categorías';
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
    // Pagar una tarjeta: lo que se propone, de un toque; teclear pone otro monto
    finEntry.payOptions.forEach(option => {
        const chip = el('button', 'fin-chip fin-pay-option', `${option.label}: ${formatMoney(option.cents, finEntryCurrency())}`);
        chip.type = 'button';
        chip.dataset.cents = String(option.cents);
        flags.appendChild(chip);
    });
    if (finEntry.payOptions.length) flags.appendChild(el('small', 'fin-pay-hint', 'O escribe otro monto: puedes pagar de más.'));
    if (finEntry.msi || (finEntry.tx && finEntry.tx.installment_id)) {
        const flag = el('span', 'fin-flag');
        flag.append(financeIcon('credit-card', 14),
            document.createTextNode(finEntry.msi ? ` A ${finEntry.msi} meses sin intereses` : ' Compra a meses'));
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

document.getElementById('finBandFrom').addEventListener('click', () => {
    if (finEntry.splits && finEntry.kind === 'income') openFinSplit();
    else openFinPicker('from');
});
document.getElementById('finBandTo').addEventListener('click', () => {
    if (finEntry.splits && finEntry.kind === 'expense') openFinSplit();
    else openFinPicker('to');
});

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
            finEntry.msi = '';
            finEntry.splits = null;
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
    // A meses: una compra nueva con tarjeta de crédito
    const account = finAccount(finEntry.accountId);
    const msiTile = document.getElementById('finMsiTile');
    msiTile.hidden = Boolean(finEntry.tx) || finEntry.kind !== 'expense' || !account || account.kind !== 'credit';
    const msiSelect = document.getElementById('finMsiSelect');
    msiSelect.value = finEntry.msi;
    msiSelect.disabled = !msiTile.hidden && !account.statement_day;
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
    const account = finAccount(finEntry.accountId);
    const months = Number(document.getElementById('finMsiSelect').value);
    const hint = document.getElementById('finMsiHint');
    if (document.getElementById('finMsiTile').hidden || !account) {
        hint.textContent = '';
    } else if (!account.statement_day) {
        hint.textContent = 'Pon el día de corte de la tarjeta (Cuentas › Tarjetas) para pagarla a meses.';
    } else if (months) {
        const cents = finEvaluate(finEntry.expr);
        const first = finCutOnOrAfter(account.statement_day, finEntry.date);
        hint.textContent = cents
            ? `${months} pagos de ${formatMoney(Math.ceil(cents / months), account.currency)}, el primero en el corte del ${finShortDate(first)}.`
            : `El primero en el corte del ${finShortDate(first)}.`;
    } else {
        hint.textContent = '';
    }
}

// El primer corte en o después de una fecha (el que factura una compra de ese día)
function finCutOnOrAfter(statementDay, iso) {
    const d = finDate(iso);
    const clamp = (y, m) => new Date(y, m, Math.min(statementDay, new Date(y, m + 1, 0).getDate()));
    const cut = clamp(d.getFullYear(), d.getMonth());
    return getDateKey(cut >= d ? cut : clamp(d.getFullYear(), d.getMonth() + 1));
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
// Repetir y a meses no van juntos: un fijo no es una compra a meses
document.getElementById('finRepeatSelect').addEventListener('change', (event) => {
    if (event.target.value) document.getElementById('finMsiSelect').value = '';
    finSyncDateSheet();
});
document.getElementById('finMsiSelect').addEventListener('change', (event) => {
    if (event.target.value) document.getElementById('finRepeatSelect').value = '';
    finSyncDateSheet();
});
document.getElementById('finDateDone').addEventListener('click', () => {
    finEntry.frequency = document.getElementById('finRepeatTile').hidden ? '' : document.getElementById('finRepeatSelect').value;
    const msiTile = document.getElementById('finMsiTile');
    finEntry.msi = msiTile.hidden || document.getElementById('finMsiSelect').disabled
        ? '' : document.getElementById('finMsiSelect').value;
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
    const splits = k !== 'transfer' && finEntry.splits ? finEntry.splits : null;
    if (k !== 'transfer' && !splits && !finEntry.categoryId) return showError(errorEl, 'Elige la categoría.');
    if (splits) {
        const sum = splits.reduce((acc, p) => acc + p.amount_cents, 0);
        if (sum !== cents) {
            return showError(errorEl, `Las partes suman ${formatMoney(sum, finEntryCurrency())}: ajústalas en Dividir.`);
        }
    }
    const concept = document.getElementById('finEntryNotes').value.trim() || finEntryDefaultConcept();
    const payload = {
        kind: k, amount_cents: cents, tx_date: finEntry.date, concept,
        account_id: finEntry.accountId,
        category_id: k === 'transfer' || splits ? null : finEntry.categoryId,
        to_account_id: k === 'transfer' ? finEntry.toAccountId : null,
    };
    if (splits) payload.splits = splits;
    else if (finEntry.tx && finEntry.tx.splits && finEntry.tx.splits.length) payload.splits = null;
    const ok = document.querySelector('#finKeypad [data-key="ok"]');
    ok.disabled = true;
    try {
        if (finEntry.tx) {
            await apiFetch(`/api/finance/transactions/${finEntry.tx.id}`, { method: 'PATCH', json: payload });
        } else if (finEntry.frequency && !splits) {
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
            const saved = await apiFetch('/api/finance/transactions', { method: 'POST', json: payload });
            if (finEntry.msi && k === 'expense') {
                try {
                    await apiFetch('/api/finance/installments', {
                        method: 'POST', json: { transaction_id: saved.id, months: Number(finEntry.msi) },
                    });
                } catch (error) {
                    // La compra ya quedó: se dice por qué no quedó a meses, y la hoja se cierra
                    finShowError(`Se guardó la compra, pero no a meses: ${error.message}`);
                }
            }
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
document.getElementById('finEntryFlags').addEventListener('click', (event) => {
    const chip = event.target.closest('.fin-pay-option');
    if (!chip) return;
    finEntry.expr = String(Number(chip.dataset.cents) / 100);
    finEntry.prefilled = true;
    finRenderAmount();
});
document.getElementById('finEntryDate').addEventListener('click', openFinDateSheet);

// ============================================
// Dividir en categorías
// ============================================

const finSplitSheet = document.getElementById('finSplitSheet');
let finSplitDraft = [];

function finSplitCategories() {
    return finKindCategories(finEntry.kind === 'income' ? 'income' : 'expense');
}

function openFinSplit() {
    const errorEl = document.getElementById('finEntryError');
    const total = finEvaluate(finEntry.expr);
    if (!total || total <= 0) {
        showError(errorEl, 'Escribe primero el monto; luego lo divides.');
        return;
    }
    errorEl.classList.add('hidden');
    const categories = finSplitCategories();
    const other = categories.find(c => c.id !== finEntry.categoryId);
    finSplitDraft = finEntry.splits ? finEntry.splits.map(p => ({ ...p }))
        : [{ category_id: finEntry.categoryId || (categories[0] || {}).id, amount_cents: total },
            { category_id: other ? other.id : null, amount_cents: 0 }];
    document.getElementById('finSplitError').classList.add('hidden');
    finRenderSplit();
    openFinSheet(finSplitSheet);
}

function finRenderSplit() {
    const total = finEvaluate(finEntry.expr) || 0;
    const currency = finEntryCurrency();
    document.getElementById('finSplitTotal').textContent = `Total: ${formatMoney(total, currency)}. Cada parte, en su categoría.`;
    const categories = finSplitCategories();
    document.getElementById('finSplitRows').replaceChildren(...finSplitDraft.map((part, i) => {
        const row = el('div', 'fin-split-row');
        row.dataset.index = String(i);
        const select = el('select', 'fin-split-category');
        select.setAttribute('aria-label', `Categoría de la parte ${i + 1}`);
        categories.forEach(c => {
            const option = el('option', '', c.name);
            option.value = String(c.id);
            select.appendChild(option);
        });
        if (part.category_id) select.value = String(part.category_id);
        const input = el('input', 'fin-split-amount');
        input.type = 'text';
        input.inputMode = 'decimal';
        input.autocomplete = 'off';
        input.placeholder = '0.00';
        input.setAttribute('aria-label', `Monto de la parte ${i + 1}`);
        input.value = part.amount_cents ? (part.amount_cents / 100).toFixed(2) : '';
        const remove = el('button', 'fin-row-btn danger fin-split-remove');
        remove.type = 'button';
        remove.setAttribute('aria-label', `Quitar la parte ${i + 1}`);
        remove.appendChild(financeIcon('x', 16));
        remove.hidden = finSplitDraft.length <= 2;
        row.append(select, input, remove);
        return row;
    }));
    finRenderSplitLeft();
}

function finRenderSplitLeft() {
    const total = finEvaluate(finEntry.expr) || 0;
    const sum = finSplitDraft.reduce((acc, p) => acc + (p.amount_cents || 0), 0);
    const left = total - sum;
    const el2 = document.getElementById('finSplitLeft');
    el2.textContent = left === 0 ? 'Cuadra con el total.'
        : left > 0 ? `Falta repartir ${formatMoney(left, finEntryCurrency())}.`
            : `Te pasas por ${formatMoney(-left, finEntryCurrency())}.`;
    el2.classList.toggle('ok', left === 0);
}

document.getElementById('finSplitRows').addEventListener('input', (event) => {
    const row = event.target.closest('[data-index]');
    if (!row || !event.target.classList.contains('fin-split-amount')) return;
    const cents = parseMoneyCents(event.target.value);
    finSplitDraft[Number(row.dataset.index)].amount_cents = cents && cents > 0 ? cents : 0;
    finRenderSplitLeft();
});
document.getElementById('finSplitRows').addEventListener('change', (event) => {
    const row = event.target.closest('[data-index]');
    if (row && event.target.classList.contains('fin-split-category')) {
        finSplitDraft[Number(row.dataset.index)].category_id = Number(event.target.value);
    }
});
document.getElementById('finSplitRows').addEventListener('click', (event) => {
    const row = event.target.closest('[data-index]');
    if (row && event.target.closest('.fin-split-remove')) {
        finSplitDraft.splice(Number(row.dataset.index), 1);
        finRenderSplit();
    }
});
document.getElementById('finSplitAdd').addEventListener('click', () => {
    const used = new Set(finSplitDraft.map(p => p.category_id));
    const next = finSplitCategories().find(c => !used.has(c.id));
    finSplitDraft.push({ category_id: next ? next.id : null, amount_cents: 0 });
    finRenderSplit();
});
document.getElementById('finSplitClear').addEventListener('click', () => {
    if (finEntry.splits) finEntry.categoryId = finEntry.splits[0].category_id;
    finEntry.splits = null;
    closeFinSheet(finSplitSheet);
    finRenderEntry();
});
document.getElementById('finSplitDone').addEventListener('click', () => {
    const errorEl = document.getElementById('finSplitError');
    const total = finEvaluate(finEntry.expr) || 0;
    const parts = finSplitDraft.filter(p => p.amount_cents > 0);
    const ids = parts.map(p => p.category_id);
    if (parts.length < 2) return showError(errorEl, 'Para dividir hacen falta al menos dos partes con monto.');
    if (ids.some(id => !id)) return showError(errorEl, 'Elige la categoría de cada parte.');
    if (new Set(ids).size !== ids.length) return showError(errorEl, 'Hay una categoría dos veces: júntalas en una parte.');
    const sum = parts.reduce((acc, p) => acc + p.amount_cents, 0);
    if (sum !== total) return showError(errorEl, 'Las partes tienen que sumar el total.');
    finEntry.splits = parts.map(p => ({ category_id: p.category_id, amount_cents: p.amount_cents }));
    closeFinSheet(finSplitSheet);
    finRenderEntry();
});
document.getElementById('finSplitBtn').addEventListener('click', openFinSplit);

finBuildKeypad();
