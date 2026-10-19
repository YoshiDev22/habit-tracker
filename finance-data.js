// ============================================
// Finanzas: el panel lateral de la inicial (Configuración, Datos, aviso, regresar),
// donde cada opción se abre en el mismo panel con ‹, y
// Datos: exportar los movimientos a CSV e importarlos de un CSV con varias
// cuentas (el que exporta esta app u otro con columnas parecidas), con vista
// previa. Las cuentas y categorías que falten se crean al confirmar; los
// movimientos entran de una vez (POST /transactions/import: o todos o ninguno).
// ============================================

const finDrawer = document.getElementById('finDrawer');
const finDrawerPanel = document.getElementById('finDrawerPanel');
const finDataImportModal = document.getElementById('finDataImportModal');
let finDataPending = null;

// ---------- El panel lateral ----------

function finUserName() {
    const me = finState.me || {};
    return me.display_name || me.first_name || (me.email || '').split('@')[0] || 'Tú';
}

function finInitial() {
    return (Array.from(finUserName())[0] || '?').toUpperCase();
}

// Las páginas del panel: la portada (root), Configuración y sus cuatro páginas,
// Datos y el aviso. Cada una sabe a cuál vuelve ‹ (data-parent)
const finDrawerNav = { current: 'root' };
const FIN_SETTINGS_PAGES = ['period', 'categories', 'fixed', 'archived'];

function finDrawerPages() {
    return [...finDrawerPanel.querySelectorAll('.fin-drawer-page')];
}

function finDrawerShow(name, { animate = true } = {}) {
    const page = finDrawerPages().find(p => p.dataset.section === name);
    if (!page) return;
    const back = finDrawerNav.current !== 'root' && page.dataset.section === finDrawerParent(finDrawerNav.current);
    finDrawerNav.current = name;
    finDrawerPages().forEach(p => p.classList.toggle('active', p === page));
    const home = name === 'root';
    document.getElementById('finDrawerHome').hidden = !home;
    document.getElementById('finDrawerBar').hidden = home;
    document.getElementById('finDrawerPageTitle').textContent = page.dataset.title;
    // Las páginas con formularios necesitan más ancho que la lista
    finDrawerPanel.classList.toggle('wide', !home);
    document.getElementById('finSettingsError').classList.add('hidden');
    finDrawerPanel.scrollTop = 0;
    if (animate) {
        page.classList.remove('slide-from-right', 'slide-from-left');
        void page.offsetWidth;
        page.classList.add(back ? 'slide-from-left' : 'slide-from-right');
    }
    if (FIN_SETTINGS_PAGES.includes(name)) finRenderSettingsPage(name);
    if (name === 'data') document.getElementById('finDataError').classList.add('hidden');
    if (name === 'privacy') {
        const frame = document.getElementById('finPrivacyFrame');
        if (!frame.getAttribute('src')) frame.setAttribute('src', '/privacidad');
    }
}

function finDrawerParent(name) {
    const page = finDrawerPages().find(p => p.dataset.section === name);
    return page ? page.dataset.parent || 'root' : 'root';
}

function openFinDrawer(page = 'root') {
    document.getElementById('finDrawerAvatar').textContent = finInitial();
    document.getElementById('finDrawerUser').textContent = finUserName();
    if (finDrawer.classList.contains('hidden')) openFinSheet(finDrawer);
    finDrawerShow(page, { animate: false });
}

// Cerrar el panel: lo que se cambió en Configuración se ve en la página
function closeFinDrawer() {
    const wasSettings = finDrawerNav.current !== 'root';
    closeFinSheet(finDrawer);
    finResetCategoryForm();
    finSettings.editingFixed = null;
    finDrawerShow('root', { animate: false });
    if (wasSettings) finLoad();
}

finSheetDismiss.set('finDrawer', closeFinDrawer);

finDrawerPanel.addEventListener('click', (event) => {
    const go = event.target.closest('[data-go]');
    if (go) {
        finDrawerShow(go.dataset.go);
        return;
    }
    const open = event.target.closest('#finSettingsMenu [data-open]');
    if (open) finDrawerShow(open.dataset.open);
});
document.getElementById('finDrawerBack').addEventListener('click', () => finDrawerShow(finDrawerParent(finDrawerNav.current)));

// Escape, dentro de una página, regresa un paso; en la portada, cierra (finDismissSheet)
window.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape' || finDrawer.classList.contains('hidden') || finDrawerNav.current === 'root') return;
    if (finSheets[finSheets.length - 1] !== finDrawer) return;
    if (!document.getElementById('confirmModal').classList.contains('hidden')) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    finDrawerShow(finDrawerParent(finDrawerNav.current));
}, true);

// ---------- Exportar ----------

const FIN_KIND_NAMES = { expense: 'Gasto', income: 'Ingreso', transfer: 'Transferencia' };
const FIN_DATA_HEADER = ['Fecha', 'Tipo', 'Cuenta', 'Hacia cuenta', 'Categoría', 'Monto', 'Moneda', 'Concepto', 'Nota',
    'Parte de'];

// Una celda de CSV: entre comillas si hace falta, y un texto que empiece por
// = + - @ con ' delante (Excel lo correría como fórmula)
function finCsvCell(value, text = true) {
    let s = value == null ? '' : String(value);
    if (text && /^[=+\-@]/.test(s)) s = `'${s}`;
    return /[",;\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function finCsvLine(cells) {
    return cells.map(([value, text]) => finCsvCell(value, text)).join(',');
}

function finDownloadCsv(name, lines) {
    const blob = new Blob(['﻿' + lines.join('\r\n') + '\r\n'], { type: 'text/csv;charset=utf-8' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = name;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}

// Las filas de unos movimientos: un dividido sale en una fila por parte, con la
// misma marca en "Parte de"
function finExportLines(transactions) {
    const accountName = id => (finAccount(id) || {}).name || '';
    const categoryName = id => (finCategory(id) || {}).name || '';
    const money = cents => (cents / 100).toFixed(2);
    const lines = [FIN_DATA_HEADER.join(',')];
    [...transactions].sort((a, b) => (a.tx_date < b.tx_date ? -1 : a.tx_date > b.tx_date ? 1 : a.id - b.id))
        .forEach(tx => {
            const base = [[tx.tx_date, false], [FIN_KIND_NAMES[tx.kind], false], [accountName(tx.account_id), true],
                [tx.to_account_id ? accountName(tx.to_account_id) : '', true]];
            const tail = [[tx.currency, false], [tx.concept, true], [tx.note || '', true]];
            if (tx.splits && tx.splits.length) {
                tx.splits.forEach(part => lines.push(finCsvLine([...base, [categoryName(part.category_id), true],
                    [money(part.amount_cents), false], ...tail, [`D${tx.id}`, false]])));
            } else {
                lines.push(finCsvLine([...base, [categoryName(tx.category_id), true], [money(tx.amount_cents), false],
                    ...tail, ['', false]]));
            }
        });
    return lines;
}

async function finExport(all) {
    const errorEl = document.getElementById('finDataError');
    errorEl.classList.add('hidden');
    try {
        let from = finState.summary.date_from;
        let to = finState.summary.date_to;
        if (all) {
            const always = await apiFetch('/api/finance/summary?all=true');
            from = always.date_from;
            to = always.date_to;
        }
        const { transactions } = await apiFetch(`/api/finance/transactions?date_from=${from}&date_to=${to}`);
        if (!transactions.length) return showError(errorEl, 'No hay movimientos que exportar.');
        finDownloadCsv(all ? 'finanzas.csv' : `finanzas-${from}-a-${to}.csv`, finExportLines(transactions));
    } catch (error) {
        showError(errorEl, error.message || 'No se pudo exportar.');
    }
}

document.getElementById('finExportAll').addEventListener('click', () => finExport(true));
document.getElementById('finExportPeriod').addEventListener('click', () => finExport(false));

// ---------- Importar: leer ----------

const FIN_DATA_ALIASES = {
    tx_date: ['fecha', 'date', 'dia', 'día'],
    kind: ['tipo', 'type', 'clase'],
    account: ['cuenta', 'account', 'de cuenta', 'desde', 'origen', 'cuenta origen'],
    to_account: ['hacia cuenta', 'a cuenta', 'destino', 'cuenta destino', 'to account', 'hacia'],
    // Otras apps exportan cuenta o categoría en una sola columna de destino: en
    // un gasto es la categoría, en una transferencia la cuenta, en un ingreso la cuenta
    target: ['a cuenta/a categoria', 'a cuenta / a categoria', 'a cuenta o categoria', 'hacia cuenta/categoria'],
    amount2: ['cantidad 2', 'monto 2', 'importe 2'],
    currency2: ['moneda 2', 'divisa 2'],
    tags: ['etiquetas', 'tags', 'etiqueta'],
    category: ['categoria', 'categoría', 'category', 'rubro'],
    amount: ['monto', 'importe', 'cantidad', 'amount', 'valor', 'total'],
    currency: ['moneda', 'currency', 'divisa'],
    concept: ['concepto', 'descripcion', 'descripción', 'description', 'detalle', 'titulo', 'título'],
    note: ['nota', 'notas', 'note', 'notes', 'comentario', 'comentarios'],
    group: ['parte de', 'dividido', 'grupo'],
};
const FIN_KIND_WORDS = {
    expense: ['gasto', 'gastos', 'expense', 'egreso', 'cargo'],
    income: ['ingreso', 'ingresos', 'income', 'abono', 'deposito', 'depósito'],
    transfer: ['transferencia', 'transfer', 'traspaso'],
};

function finDataColumns(header) {
    const columns = {};
    header.map(normalize).forEach((name, i) => {
        Object.entries(FIN_DATA_ALIASES).forEach(([field, aliases]) => {
            if (columns[field] === undefined && aliases.some(alias => name === normalize(alias))) columns[field] = i;
        });
        // "A cuenta / a categoría" con otra escritura
        if (columns.target === undefined && name.includes('cuenta') && name.includes('categor')) columns.target = i;
    });
    return columns;
}

// Quita el ' que finCsvCell puso delante de = + - @
function finUncell(text) {
    return /^'[=+\-@]/.test(text) ? text.slice(1) : text;
}

function finKindOf(text) {
    const word = normalize(text || '');
    return Object.keys(FIN_KIND_WORDS).find(kind => FIN_KIND_WORDS[kind].some(w => normalize(w) === word)) || null;
}

// Filas de texto → movimientos (sin ids todavía: cuentas y categorías van por nombre)
function rowsToFinanceData(table) {
    if (table.length < 2) return [];
    const columns = finDataColumns(table[0]);
    const get = (cells, field) => (columns[field] === undefined ? '' : finUncell((cells[columns[field]] || '').trim()));
    const knownAccounts = new Set(finState.accounts.map(a => normalize(a.name)));
    const rows = table.slice(1).map(cells => {
        const dateText = get(cells, 'tx_date');
        const signed = parseMoneyCents(get(cells, 'amount'));
        const target = get(cells, 'target');
        let account = get(cells, 'account');
        let toAccount = get(cells, 'to_account');
        let category = get(cells, 'category');
        const kind = finKindOf(get(cells, 'kind'))
            || (toAccount ? 'transfer' : signed != null && signed > 0 ? 'income' : 'expense');
        if (target) {
            if (kind === 'transfer') toAccount = toAccount || target;
            else if (kind === 'expense') category = category || target;
            // En un ingreso, el destino es la cuenta y el origen la categoría,
            // salvo que el origen sea una cuenta que ya tienes
            else if (!category) {
                const fromIsAccount = knownAccounts.has(normalize(account)) && !knownAccounts.has(normalize(target));
                category = fromIsAccount ? target : account;
                account = fromIsAccount ? account : target;
            }
        }
        if (kind === 'transfer') category = '';
        // Sin columna de concepto, la nota es el concepto (lo que se ve en la lista)
        const hasConcept = columns.concept !== undefined;
        const note = get(cells, 'note');
        const tags = get(cells, 'tags');
        const currency = get(cells, 'currency').toUpperCase();
        const currency2 = get(cells, 'currency2').toUpperCase();
        const row = {
            tx_date: parseDate(dateText),
            kind,
            accountName: account,
            toAccountName: kind === 'transfer' ? toAccount : '',
            parts: [{ categoryName: category, amount_cents: signed == null ? null : Math.abs(signed) }],
            currency,
            concept: (hasConcept ? get(cells, 'concept') : note).slice(0, 200),
            note: [hasConcept ? note : '', tags ? `Etiquetas: ${tags}` : ''].filter(Boolean).join(' · ').slice(0, 500),
            group: get(cells, 'group'),
        };
        row.problem = !dateText || row.tx_date == null ? `fecha "${dateText}" no válida`
            : !row.accountName ? 'sin cuenta'
                : !row.parts[0].amount_cents ? 'sin monto'
                    : kind === 'transfer' && !row.toAccountName ? 'transferencia sin cuenta de destino'
                        : kind !== 'transfer' && !category ? 'sin categoría'
                            : currency2 && currency && currency2 !== currency ? `cambia de moneda (${currency} → ${currency2}): la app no convierte`
                                : null;
        return row;
    });
    // Las filas de un dividido ("Parte de" igual) son un solo movimiento
    const merged = [];
    const byGroup = new Map();
    rows.forEach(row => {
        const first = row.group && byGroup.get(row.group);
        if (!first) {
            if (row.group) byGroup.set(row.group, row);
            merged.push(row);
            return;
        }
        if (row.problem || row.kind !== first.kind || normalize(row.accountName) !== normalize(first.accountName)) {
            first.problem = first.problem || 'las partes de un dividido no coinciden (tipo o cuenta)';
            return;
        }
        first.parts.push(row.parts[0]);
    });
    merged.forEach(row => {
        row.amount_cents = row.parts.reduce((acc, p) => acc + (p.amount_cents || 0), 0);
        if (row.parts.length > 1) {
            const names = row.parts.map(p => normalize(p.categoryName));
            if (new Set(names).size !== names.length) row.problem = row.problem || 'un dividido repite una categoría';
        }
        if (!row.concept) row.concept = row.parts.length > 1 ? 'Dividido' : (row.parts[0].categoryName || 'Transferencia');
    });
    return merged;
}

// ---------- Importar: con lo que ya hay ----------

// La cuenta nueva: su tipo adivinado por el nombre (se cambia en la vista previa)
function finGuessKind(name) {
    const n = normalize(name);
    if (/efectivo|cash|cartera/.test(n)) return 'cash';
    if (/tarjeta|credit|credito|tdc|visa|master|amex/.test(n)) return 'credit';
    return 'debit';
}

async function finRefreshDataImport() {
    if (!finDataPending) return;
    const rows = finDataPending.rows;
    const accounts = new Map(finState.accounts.map(a => [normalize(a.name), a]));
    const categories = new Map(finState.categories.map(c => [normalize(c.name), c]));
    const main = finMainCurrency();
    const newAccounts = finDataPending.newAccounts;     // nombre normalizado → {name, kind, currency}
    const newCategories = new Map();                    // nombre normalizado → {name, kind}
    const seenAccounts = new Set();
    // La moneda que dice el archivo puede ser solo la etiqueta de "$" de la otra app:
    // una que ninguna de tus cuentas usa se toma, de entrada, como tu moneda principal
    const currencyMap = finDataPending.currencyMap;     // la del archivo → la que se usa
    const used = new Set(finState.accounts.map(a => a.currency));
    rows.forEach(row => {
        if (row.currency && !currencyMap.has(row.currency)) {
            currencyMap.set(row.currency, used.has(row.currency) ? row.currency : main);
        }
    });
    [...currencyMap.keys()].forEach(code => { if (!rows.some(r => r.currency === code)) currencyMap.delete(code); });
    newAccounts.forEach(account => {
        account.currency = account.fileCurrency ? currencyMap.get(account.fileCurrency) || account.fileCurrency : main;
    });
    rows.forEach(row => {
        row.skip = row.problem;
        if (row.skip) return;
        const currency = row.currency ? currencyMap.get(row.currency) || row.currency : '';
        [row.accountName, row.toAccountName].filter(Boolean).forEach(name => {
            const key = normalize(name);
            seenAccounts.add(key);
            if (!accounts.has(key) && !newAccounts.has(key)) {
                newAccounts.set(key, { name: name.slice(0, 40), kind: finGuessKind(name),
                    fileCurrency: row.currency, currency: currency || main });
            }
        });
        const currencyOf = name => {
            const key = normalize(name);
            return (accounts.get(key) || newAccounts.get(key)).currency;
        };
        if (currency && currency !== currencyOf(row.accountName)) {
            row.skip = `moneda ${currency}, la cuenta es en ${currencyOf(row.accountName)}`;
            return;
        }
        if (row.kind === 'transfer' && currencyOf(row.toAccountName) !== currencyOf(row.accountName)) {
            row.skip = 'transferencia entre monedas distintas';
            return;
        }
        if (normalize(row.accountName) === normalize(row.toAccountName)) {
            row.skip = 'transferencia a la misma cuenta';
            return;
        }
        for (const part of row.kind === 'transfer' ? [] : row.parts) {
            const key = normalize(part.categoryName);
            const existing = categories.get(key);
            if (existing && existing.kind !== row.kind) {
                row.skip = `"${existing.name}" es de ${existing.kind === 'income' ? 'ingresos' : 'gastos'}`;
                return;
            }
            const pending = newCategories.get(key);
            if (pending && pending.kind !== row.kind) {
                row.skip = `"${part.categoryName}" sale como gasto y como ingreso`;
                return;
            }
            if (!existing && !pending) newCategories.set(key, { name: part.categoryName.slice(0, 40), kind: row.kind });
        }
    });
    // Una cuenta nueva que ya no usa ninguna fila (se corrigió el archivo) sale de la lista
    [...newAccounts.keys()].forEach(key => { if (!seenAccounts.has(key)) newAccounts.delete(key); });
    finDataPending.newCategories = newCategories;

    // Repetidos: mismo día, monto, tipo y cuenta que uno que ya existe
    const dated = rows.filter(r => !r.skip).map(r => r.tx_date).sort();
    const counts = new Map();
    let checked = !dated.length;
    if (dated.length) {
        try {
            const data = await apiFetch(`/api/finance/transactions?date_from=${dated[0]}&date_to=${dated[dated.length - 1]}`);
            data.transactions.forEach(tx => {
                const key = `${tx.tx_date}|${tx.amount_cents}|${tx.kind}|${normalize((finAccount(tx.account_id) || {}).name || '')}`;
                counts.set(key, (counts.get(key) || 0) + 1);
            });
            checked = true;
        } catch (error) { /* sin la revisión de repetidos: se avisa abajo */ }
    }
    rows.forEach(row => {
        row.duplicate = false;
        if (row.skip) return;
        const key = `${row.tx_date}|${row.amount_cents}|${row.kind}|${normalize(row.accountName)}`;
        if (counts.get(key)) {
            row.duplicate = true;
            counts.set(key, counts.get(key) - 1);
        }
    });
    finRenderDataImport(checked);
}

function finRenderDataImport(checked) {
    const { rows, newAccounts, newCategories } = finDataPending;
    const includeDupes = document.getElementById('finDataDupes').checked;
    const valid = rows.filter(r => !r.skip && (!r.duplicate || includeDupes)).length;
    const dupes = rows.filter(r => r.duplicate).length;
    document.getElementById('finDataSummary').textContent = !rows.length
        ? 'Elige un archivo CSV o pega las filas, con la de los nombres de las columnas primero.'
        : `${valid} de ${rows.length} ${rows.length === 1 ? 'movimiento' : 'movimientos'} se importarán.`
            + (rows.some(r => r.skip) ? ' Los marcados en rojo se saltan (pasa el cursor o tócalos para ver por qué).' : '')
            + (checked ? '' : ' No pude revisar si ya existían.');

    // Lo que se va a crear: las cuentas, con su tipo para elegir
    const box = document.getElementById('finDataNew');
    const parts = [];
    const main = finMainCurrency();
    const fileCurrencies = [...finDataPending.currencyMap.entries()].filter(([code, to]) => code !== main || to !== main);
    if (fileCurrencies.length) {
        const list = el('div', 'fin-data-new');
        list.appendChild(el('p', 'fin-stat-label', 'Moneda del archivo'));
        fileCurrencies.forEach(([code, to]) => {
            const row = el('label', 'fin-data-new-row');
            const select = el('select', 'fin-import-input');
            select.dataset.currencyMap = code;
            [...new Set([main, code])].forEach(value => {
                const option = el('option', '', value === code ? `${code}, tal cual` : `${value}, tu moneda`);
                option.value = value;
                select.appendChild(option);
            });
            select.value = to;
            row.append(el('span', '', `El archivo dice ${code}`), select);
            list.appendChild(row);
        });
        list.appendChild(el('p', 'fin-hint', 'Si tu otra app ponía "$" como USD pero tus cuentas son en pesos, elige tu moneda.'));
        parts.push(list);
    }
    if (newAccounts.size) {
        const list = el('div', 'fin-data-new');
        list.appendChild(el('p', 'fin-stat-label', 'Cuentas nuevas'));
        [...newAccounts.entries()].forEach(([key, account]) => {
            const row = el('label', 'fin-data-new-row');
            const select = el('select', 'fin-import-input');
            select.dataset.newAccount = key;
            Object.entries(FIN_KIND_LABELS).forEach(([value, text]) => {
                const option = el('option', '', text);
                option.value = value;
                select.appendChild(option);
            });
            select.value = account.kind;
            row.append(el('span', '', `${account.name} (${account.currency})`), select);
            list.appendChild(row);
        });
        parts.push(list);
    }
    if (newCategories.size) {
        const names = [...newCategories.values()].map(c => `${c.name} (${c.kind === 'income' ? 'ingreso' : 'gasto'})`);
        parts.push(el('p', 'fin-hint', `Categorías nuevas: ${names.join(', ')}.`));
    }
    box.replaceChildren(...parts);

    document.getElementById('finDataRows').replaceChildren(...rows.map(r => {
        const tr = el('tr', r.skip ? 'invalid' : (r.duplicate && !includeDupes ? 'duplicate' : ''));
        const account = r.kind === 'transfer' ? `${r.accountName} → ${r.toAccountName}` : r.accountName;
        const category = r.kind === 'transfer' ? 'Transferencia'
            : r.parts.map(p => p.categoryName).filter(Boolean).join(' + ');
        const sign = r.kind === 'income' ? '+' : r.kind === 'expense' ? '−' : '';
        const amount = r.amount_cents ? `${sign}${(r.amount_cents / 100).toFixed(2)}` : '—';
        [r.tx_date ? finShortDate(r.tx_date) : '—', account || '—', category || '—', amount, r.concept || '—']
            .forEach((text, i) => tr.appendChild(el('td', i === 3 ? `fin-import-amount ${r.kind}` : '', text)));
        if (r.skip) tr.title = r.skip;
        else if (r.duplicate) tr.title = 'Ya hay uno igual (mismo día, monto, tipo y cuenta)';
        return tr;
    }));
    document.getElementById('finDataDupesOption').classList.toggle('hidden', dupes === 0);
    document.getElementById('finDataDupesLabel').textContent =
        `Importar también ${dupes === 1 ? 'el que ya existe' : `los ${dupes} que ya existen`} (grises): solo si de verdad se repitieron`;
    document.getElementById('finDataConfirm').disabled = valid === 0;
}

function finParseDataImport() {
    const text = document.getElementById('finDataText').value;
    const keep = finDataPending ? finDataPending.newAccounts : new Map();
    const currencyMap = finDataPending ? finDataPending.currencyMap : new Map();
    finDataPending = { rows: text.trim() ? rowsToFinanceData(parseTable(text)) : [], newAccounts: keep,
        newCategories: new Map(), currencyMap };
    finRefreshDataImport();
}

function openFinDataImport() {
    closeFinDrawer();
    finDataPending = null;
    document.getElementById('finDataText').value = '';
    document.getElementById('finDataDupes').checked = false;
    document.getElementById('finDataImportError').classList.add('hidden');
    showModal(finDataImportModal);
    finParseDataImport();
}

function closeFinDataImport() {
    finDataPending = null;
    hideModal(finDataImportModal);
}

// ---------- Importar: guardar ----------

async function confirmFinDataImport() {
    if (!finDataPending) return;
    const button = document.getElementById('finDataConfirm');
    const errorEl = document.getElementById('finDataImportError');
    errorEl.classList.add('hidden');
    const includeDupes = document.getElementById('finDataDupes').checked;
    const rows = finDataPending.rows.filter(r => !r.skip && (!r.duplicate || includeDupes));
    if (!rows.length) return;
    button.disabled = true;
    const created = [];
    try {
        // Primero lo que falta: cuentas y categorías (con color de la paleta)
        const accountIds = new Map(finState.accounts.map(a => [normalize(a.name), a.id]));
        for (const [key, account] of finDataPending.newAccounts) {
            if (!rows.some(r => normalize(r.accountName) === key || normalize(r.toAccountName) === key)) continue;
            const saved = await apiFetch('/api/finance/accounts', { method: 'POST', json: {
                name: account.name, kind: account.kind, currency: account.currency,
                color: FIN_PALETTE[(accountIds.size * 4 + 3) % FIN_PALETTE.length],
            } });
            accountIds.set(key, saved.id);
            created.push(saved.name);
        }
        const categoryIds = new Map(finState.categories.map(c => [normalize(c.name), c.id]));
        for (const [key, category] of finDataPending.newCategories) {
            const saved = await apiFetch('/api/finance/categories', { method: 'POST', json: {
                name: category.name, kind: category.kind,
                color: FIN_PALETTE[(categoryIds.size * 5 + 1) % FIN_PALETTE.length],
            } });
            categoryIds.set(key, saved.id);
            created.push(saved.name);
        }
        const payload = rows.map(r => {
            const row = {
                kind: r.kind, account_id: accountIds.get(normalize(r.accountName)), amount_cents: r.amount_cents,
                tx_date: r.tx_date, concept: r.concept, note: r.note || null,
            };
            if (r.kind === 'transfer') row.to_account_id = accountIds.get(normalize(r.toAccountName));
            else if (r.parts.length > 1) {
                row.splits = r.parts.map(p => ({ category_id: categoryIds.get(normalize(p.categoryName)),
                    amount_cents: p.amount_cents }));
            } else row.category_id = categoryIds.get(normalize(r.parts[0].categoryName));
            return row;
        });
        await apiFetch('/api/finance/transactions/import', { method: 'POST', json: { rows: payload } });
        closeFinDataImport();
        await finLoad();
    } catch (error) {
        const made = created.length ? ` Ya se crearon: ${created.join(', ')}; no se importó ningún movimiento.` : '';
        showError(errorEl, (error.message || 'No se pudo importar.') + made);
        await finLoad();
        if (finDataPending) finRefreshDataImport();
    } finally {
        button.disabled = false;
    }
}

// Una plantilla con las columnas y tres filas de ejemplo
function finDataTemplate() {
    const today = finToday();
    const day = d => `${today.slice(0, 8)}${String(d).padStart(2, '0')}`;
    return [
        FIN_DATA_HEADER.join(','),
        `${day(1)},Gasto,Efectivo,,Súper,850.50,MXN,Súper de la semana,,`,
        `${day(2)},Gasto,Tarjeta,,Comer fuera,400.00,MXN,Cena,,D1`,
        `${day(2)},Gasto,Tarjeta,,Ocio,200.00,MXN,Cena,,D1`,
        `${day(5)},Transferencia,Débito,Tarjeta,,600.00,MXN,Pago de la tarjeta,,`,
        `${day(15)},Ingreso,Débito,,Sueldo,"15,000.00",MXN,Sueldo,,`,
    ];
}

document.getElementById('finDataImportOpen').addEventListener('click', openFinDataImport);
document.getElementById('finDataTemplate').addEventListener('click', () => finDownloadCsv('finanzas-plantilla.csv', finDataTemplate()));
document.getElementById('finDataFileBtn').addEventListener('click', () => document.getElementById('finDataFile').click());
document.getElementById('finDataFile').addEventListener('change', async (event) => {
    const file = event.target.files[0];
    event.target.value = '';
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) {
        showError(document.getElementById('finDataImportError'), 'El archivo pesa más de 5 MB.');
        return;
    }
    document.getElementById('finDataImportError').classList.add('hidden');
    document.getElementById('finDataText').value = await file.text();
    finParseDataImport();
});
let finDataTimer = null;
document.getElementById('finDataText').addEventListener('input', () => {
    clearTimeout(finDataTimer);
    finDataTimer = setTimeout(finParseDataImport, 300);
});
document.getElementById('finDataNew').addEventListener('change', (event) => {
    if (!finDataPending) return;
    const currency = event.target.closest('[data-currency-map]');
    if (currency) {
        finDataPending.currencyMap.set(currency.dataset.currencyMap, currency.value);
        finRefreshDataImport();
        return;
    }
    const select = event.target.closest('[data-new-account]');
    if (!select) return;
    const account = finDataPending.newAccounts.get(select.dataset.newAccount);
    if (account) account.kind = select.value;
});
document.getElementById('finDataDupes').addEventListener('change', () => finRenderDataImport(true));
document.getElementById('finDataConfirm').addEventListener('click', confirmFinDataImport);
document.getElementById('finDataCancel').addEventListener('click', closeFinDataImport);
document.getElementById('finDataImportClose').addEventListener('click', closeFinDataImport);
finDataImportModal.querySelector('.modal-overlay').addEventListener('click', closeFinDataImport);
document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !finDataImportModal.classList.contains('hidden')
        && document.getElementById('confirmModal').classList.contains('hidden')) {
        closeFinDataImport();
    }
});
