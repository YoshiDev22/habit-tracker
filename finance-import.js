// ============================================
// Finanzas: pegar el estado de cuenta (o un CSV)
// ============================================
//
// Se pegan filas en el cuadro (o se elige un CSV) y sale la vista previa:
// columnas Cargo/Abono o un solo Monto con signo (rowsToFinance). Lo que ya
// existe en esa cuenta (mismo día, monto y tipo, contando repeticiones) sale
// tachado y no entra salvo que se pida, y un abono a una tarjeta de crédito se
// salta: es el pago, y va como transferencia. Nada se guarda hasta "Agregar"
// (POST /transactions/import: o todos o ninguno).

const finImportModal = document.getElementById('finImportModal');
let finPending = null;

const FIN_HEADER_ALIASES = {
    tx_date: ['fecha', 'date', 'dia', 'día', 'fecha de operacion', 'fecha operacion', 'fecha de cargo'],
    concept: ['concepto', 'descripcion', 'descripción', 'description', 'detalle', 'movimiento', 'comercio',
        'establecimiento'],
    category: ['categoria', 'categoría', 'category', 'rubro'],
    charge: ['cargo', 'cargos', 'retiro', 'retiros', 'gasto', 'gastos', 'egreso', 'egresos', 'debito', 'débito'],
    credit: ['abono', 'abonos', 'deposito', 'depósito', 'depositos', 'depósitos', 'ingreso', 'ingresos'],
    amount: ['monto', 'importe', 'cantidad', 'amount', 'valor', 'total'],
};
// Sin encabezado: fecha, concepto, monto y categoría
const FIN_DEFAULT_ORDER = ['tx_date', 'concept', 'amount', 'category'];

function finColumns(header) {
    const columns = {};
    header.map(normalize).forEach((name, i) => {
        Object.entries(FIN_HEADER_ALIASES).forEach(([field, aliases]) => {
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
    let columns = finColumns(table[0]);
    const hasHeader = columns.concept !== undefined
        || ['amount', 'charge', 'credit'].some(field => columns[field] !== undefined);
    const body = hasHeader ? table.slice(1) : table;
    if (!hasHeader) {
        columns = {};
        FIN_DEFAULT_ORDER.forEach((field, i) => { columns[field] = i; });
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
// última usada con ese concepto en lo que se ve; si no, la última del tipo ("Otros")
function finRowCategory(row) {
    const categories = finKindCategories(row.kind);
    const byName = categories.find(c => normalize(c.name) === normalize(row.categoryName || ''));
    if (byName) return byName;
    const used = finState.transactions.find(tx => tx.category_id && normalize(tx.concept) === normalize(row.concept));
    return categories.find(c => used && c.id === used.category_id) || categories[categories.length - 1];
}

function openFinImport(text = '') {
    const accounts = finActiveAccounts();
    const preferred = accounts.find(a => a.kind !== 'cash') || accounts[0];
    const select = document.getElementById('finImportAccount');
    select.replaceChildren(...accounts.map(a => {
        const option = el('option', '', a.name);
        option.value = String(a.id);
        return option;
    }));
    if (preferred) select.value = String(preferred.id);
    document.getElementById('finImportText').value = text;
    document.getElementById('finImportDupes').checked = false;
    document.getElementById('finImportError').classList.add('hidden');
    showModal(finImportModal);
    finParseImport();
    if (!text) document.getElementById('finImportText').focus();
}

function finParseImport() {
    const text = document.getElementById('finImportText').value;
    finPending = { rows: text.trim() ? rowsToFinance(parseTable(text)) : [] };
    refreshFinImport();
}

// Con la cuenta elegida, lo que ya existe se marca repetido
async function refreshFinImport() {
    if (!finPending) return;
    const account = finAccount(Number(document.getElementById('finImportAccount').value));
    const dated = finPending.rows.filter(r => r.tx_date).map(r => r.tx_date).sort();
    const counts = new Map();
    let checked = !dated.length;
    if (account && dated.length) {
        const from = dated[0];
        const to = dated[dated.length - 1];
        if ((finDate(to) - finDate(from)) / 86400000 < 366) {
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
    finPending.rows.forEach(row => {
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
        const category = finRowCategory(row);
        row.category_id = category ? category.id : null;
        row.categoryLabel = category ? category.name : '—';
    });
    renderFinImport(account, checked);
}

function renderFinImport(account, checked) {
    const rows = finPending.rows;
    const currency = account ? account.currency : finMainCurrency();
    const dupes = rows.filter(r => r.duplicate).length;
    const includeDupes = document.getElementById('finImportDupes').checked;
    const valid = rows.filter(r => !r.skip && (!r.duplicate || includeDupes)).length;
    document.getElementById('finImportSummary').textContent = !rows.length
        ? 'Pega las filas (fecha, concepto y monto, o columnas Cargo y Abono) o elige un CSV.'
        : `${valid} de ${rows.length} ${rows.length === 1 ? 'fila' : 'filas'} se agregarán a "${account ? account.name : ''}".`
            + (rows.some(r => r.skip) ? ' Las marcadas en rojo se saltan.' : '')
            + (checked ? '' : ' No pude revisar si ya existían.');
    document.getElementById('finImportRows').replaceChildren(...rows.map(r => {
        const tr = el('tr', r.skip ? 'invalid' : (r.duplicate && !includeDupes ? 'duplicate' : ''));
        const amount = r.amount_cents ? `${r.kind === 'income' ? '+' : '−'}${formatMoney(r.amount_cents, currency)}` : '—';
        [r.tx_date ? finShortDate(r.tx_date) : '—', r.concept || '—', amount, r.skip ? '' : r.categoryLabel]
            .forEach((text, i) => tr.appendChild(el('td', i === 2 ? `fin-import-amount ${r.kind}` : '', text)));
        if (r.skip) tr.title = r.skip;
        else if (r.duplicate) tr.title = 'Ya hay uno igual (mismo día, monto y cuenta)';
        return tr;
    }));
    document.getElementById('finImportDupesOption').classList.toggle('hidden', dupes === 0);
    document.getElementById('finImportDupesLabel').textContent =
        `Agregar también ${dupes === 1 ? 'el que ya existe' : `los ${dupes} que ya existen`} (grises): marca esto solo si de verdad fueron dos compras iguales`;
    document.getElementById('finImportConfirm').disabled = valid === 0;
}

function closeFinImport() {
    finPending = null;
    hideModal(finImportModal);
}

async function confirmFinImport() {
    if (!finPending) return;
    const button = document.getElementById('finImportConfirm');
    const accountId = Number(document.getElementById('finImportAccount').value);
    const includeDupes = document.getElementById('finImportDupes').checked;
    const rows = finPending.rows.filter(r => !r.skip && (!r.duplicate || includeDupes)).map(r => ({
        kind: r.kind, account_id: accountId, amount_cents: r.amount_cents, tx_date: r.tx_date,
        category_id: r.category_id, concept: r.concept,
    }));
    button.disabled = true;
    try {
        await apiFetch('/api/finance/transactions/import', { method: 'POST', json: { rows } });
        closeFinImport();
        await finLoad();
    } catch (error) {
        showError(document.getElementById('finImportError'), error.message);
        button.disabled = false;
    }
}

let finImportTimer = null;
document.getElementById('finImportText').addEventListener('input', () => {
    clearTimeout(finImportTimer);
    finImportTimer = setTimeout(finParseImport, 250);
});
document.getElementById('finPasteBtn').addEventListener('click', () => openFinImport());
document.getElementById('finCsvBtn').addEventListener('click', () => document.getElementById('finCsvInput').click());
document.getElementById('finCsvInput').addEventListener('change', async (event) => {
    const file = event.target.files[0];
    event.target.value = '';
    if (!file) return;
    if (file.size > 1024 * 1024) {
        finShowError('El archivo pesa más de 1 MB.');
        return;
    }
    openFinImport(await file.text());
});
// Pegar varias celdas sobre la lista también abre la vista previa
document.getElementById('finTxList').addEventListener('paste', (event) => {
    const text = event.clipboardData && event.clipboardData.getData('text/plain');
    if (!text || !/[\t\n]/.test(text.trim())) return;
    event.preventDefault();
    openFinImport(text);
});
document.getElementById('finImportAccount').addEventListener('change', refreshFinImport);
document.getElementById('finImportDupes').addEventListener('change', () => {
    renderFinImport(finAccount(Number(document.getElementById('finImportAccount').value)), true);
});
document.getElementById('finImportConfirm').addEventListener('click', confirmFinImport);
document.getElementById('finImportCancel').addEventListener('click', closeFinImport);
document.getElementById('finImportClose').addEventListener('click', closeFinImport);
finImportModal.querySelector('.modal-overlay').addEventListener('click', closeFinImport);
document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !finImportModal.classList.contains('hidden')
        && document.getElementById('confirmModal').classList.contains('hidden')) {
        closeFinImport();
    }
});
