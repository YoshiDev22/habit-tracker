// ============================================
// Finanzas: buscar y filtrar Movimientos (BACKLOG 48)
// ============================================
//
// La lupa de arriba (solo en Movimientos) abre la hoja Buscar: texto, tipo,
// cuentas y categorías. Filtra en el navegador lo cargado del periodo que se
// ve; para buscar en todo, "Siempre". Dentro de un grupo vale cualquiera (dos
// cuentas: de una o de la otra) y entre grupos, todos (Gasto y Súper: gastos de
// Súper). Una parte de un cargo dividido cuenta en su categoría. Los filtros
// viven en la sesión (finState.txFilter): al recargar, la lista sale completa.
// "Movimientos" del menú de una cuenta es este mismo filtro con esa cuenta.

const finSearchSheet = document.getElementById('finSearchSheet');
const FIN_SEARCH_KINDS = [['expense', 'Gasto', 'arrow-up'], ['income', 'Ingreso', 'arrow-down'],
    ['transfer', 'Transferencia', 'arrow-left-right']];
let finSearchDraft = null;

function finEmptyFilter() {
    return { q: '', kinds: new Set(), accounts: new Set(), categories: new Set() };
}

function finCopyFilter(f) {
    return { q: f.q, kinds: new Set(f.kinds), accounts: new Set(f.accounts), categories: new Set(f.categories) };
}

function finFilterActive(f = finState.txFilter) {
    return Boolean(f.q) || f.kinds.size > 0 || f.accounts.size > 0 || f.categories.size > 0;
}

// Más que cuentas: deja fuera lo que no es un movimiento (saldos iniciales, programados)
function finFilterNarrows(f = finState.txFilter) {
    return Boolean(f.q) || f.kinds.size > 0 || f.categories.size > 0;
}

// Sin acentos ni mayúsculas: "cafe" encuentra "Café"
function finFold(text) {
    return String(text || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
}

function finTxCategoryIds(tx) {
    return tx.splits && tx.splits.length ? tx.splits.map(s => s.category_id) : [tx.category_id];
}

function finTxMatches(tx, f = finState.txFilter) {
    if (f.kinds.size && !f.kinds.has(tx.kind)) return false;
    if (f.accounts.size && !f.accounts.has(tx.account_id) && !f.accounts.has(tx.to_account_id)) return false;
    const categoryIds = finTxCategoryIds(tx);
    if (f.categories.size && !categoryIds.some(id => f.categories.has(id))) return false;
    if (!f.q) return true;
    const q = finFold(f.q);
    const names = categoryIds.map(finCategory).filter(Boolean).map(c => c.name);
    if (finFold([tx.concept, ...names].join(' ')).includes(q)) return true;
    // Un monto: "350" encuentra $350.00 y $350.50; "350.5", solo $350.50
    const number = q.replace(/[$\s,]/g, '');
    if (!/^\d+(\.\d{1,2})?$/.test(number)) return false;
    return number.includes('.') ? Math.round(Number(number) * 100) === tx.amount_cents
        : Math.floor(tx.amount_cents / 100) === Number(number);
}

// "Solo Efectivo", o lo que filtra: “uber” · Gasto · 2 cuentas · Transporte
function finFilterLabel(f) {
    if (!finFilterNarrows(f) && f.accounts.size === 1) return `Solo ${finAccount([...f.accounts][0]).name}`;
    const parts = [];
    if (f.q) parts.push(`“${f.q}”`);
    if (f.kinds.size) parts.push(FIN_SEARCH_KINDS.filter(([k]) => f.kinds.has(k)).map(([, label]) => label).join(' o '));
    if (f.accounts.size === 1) parts.push(finAccount([...f.accounts][0]).name);
    else if (f.accounts.size) parts.push(`${f.accounts.size} cuentas`);
    const category = f.categories.size === 1 ? finCategory([...f.categories][0]) : null;
    if (category) parts.push(category.name);
    else if (f.categories.size) parts.push(`${f.categories.size} categorías`);
    return parts.join(' · ');
}

// La barra de arriba de la lista: qué filtra y, de lo que coincide, cuántos y cuánto
function finRenderFilterBar(txs) {
    const f = finState.txFilter;
    const bar = document.getElementById('finTxFilter');
    bar.hidden = !finFilterActive(f);
    finSyncSearchBtn();
    if (bar.hidden) return;
    document.getElementById('finTxFilterLabel').textContent = finFilterLabel(f);
    document.getElementById('finTxFilterClear').replaceChildren(financeIcon('x', 18));
    // Las sumas, en la moneda principal (las otras nunca se suman con ella)
    const main = finMainCurrency();
    const sum = kind => txs.filter(t => t.kind === kind && t.currency === main).reduce((acc, t) => acc + t.amount_cents, 0);
    const parts = [txs.length === 1 ? '1 movimiento' : `${txs.length} movimientos`];
    const expense = sum('expense');
    const income = sum('income');
    if (expense) parts.push(`Gastos −${finMoney(expense, main)}`);
    if (income) parts.push(`Ingresos +${finMoney(income, main)}`);
    document.getElementById('finTxFilterSum').textContent = parts.join(' · ');
}

// La lupa se marca mientras haya filtros
function finSyncSearchBtn() {
    const button = document.getElementById('finSearchBtn');
    const active = finFilterActive();
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', String(active));
    button.setAttribute('aria-label', active ? 'Buscar en movimientos (con filtros)' : 'Buscar en movimientos');
}

function finApplyFilter(filter) {
    finState.txFilter = filter;
    if (finSheets.includes(finSearchSheet)) closeFinSheet(finSearchSheet);
    finRenderList();
}

// ---------- La hoja Buscar ----------

function finSearchToggle(kind, value, pressed, label, content) {
    const button = el('button', `fin-chip fin-search-chip${pressed ? ' on' : ''}`);
    button.type = 'button';
    button.dataset.filter = kind;
    button.dataset.value = String(value);
    button.setAttribute('aria-pressed', String(pressed));
    button.append(...content, el('span', '', label));
    return button;
}

function openFinSearch() {
    finSearchDraft = finCopyFilter(finState.txFilter);
    const d = finSearchDraft;
    document.getElementById('finSearchText').value = d.q;
    document.getElementById('finSearchKinds').replaceChildren(...FIN_SEARCH_KINDS.map(([kind, label, icon]) =>
        finSearchToggle('kinds', kind, d.kinds.has(kind), label, [financeIcon(icon, 16)])));
    // Las activas, las tarjetas dadas de baja (su historial se sigue buscando) y las de un
    // filtro que ya no lo estén (una archivada desde entonces)
    const accounts = [...finActiveAccounts(),
        ...finState.accounts.filter(a => !a.is_active && (a.cancelled_on || d.accounts.has(a.id)))];
    document.getElementById('finSearchAccounts').replaceChildren(...accounts.map(a => {
        const button = finSearchToggle('accounts', a.id, d.accounts.has(a.id), a.name,
            [finBadge(finAccountIcon(a), finAccountColor(a), { size: 'sm', square: true })]);
        button.classList.add('fin-search-account');
        button.appendChild(el('small', '', a.cancelled_on ? `Dada de baja el ${finShortDate(a.cancelled_on)}`
            : formatMoney(a.balance_cents, a.currency)));
        return button;
    }));
    ['expense', 'income'].forEach(kind => {
        const box = document.getElementById(kind === 'expense' ? 'finSearchExpense' : 'finSearchIncome');
        box.replaceChildren(...finKindCategories(kind).map(c => finSearchToggle('categories', c.id, d.categories.has(c.id),
            c.name, [finBadge(finCategoryIcon(c), finCategoryColor(c), { size: 'sm' })])));
    });
    const s = finState.summary;
    const all = finState.range.mode === 'all';
    document.getElementById('finSearchScope').textContent = s
        ? `Busca en el periodo que ves: ${finRangeLabel(s.date_from, s.date_to, finState.range.mode, s.period)}.` : '';
    document.getElementById('finSearchAll').hidden = all;
    openFinSheet(finSearchSheet);
}

finSearchSheet.addEventListener('click', (event) => {
    const button = event.target.closest('[data-filter]');
    if (!button || !finSearchDraft) return;
    const set = finSearchDraft[button.dataset.filter];
    const value = button.dataset.filter === 'kinds' ? button.dataset.value : Number(button.dataset.value);
    if (set.has(value)) set.delete(value);
    else set.add(value);
    button.classList.toggle('on', set.has(value));
    button.setAttribute('aria-pressed', String(set.has(value)));
});

document.getElementById('finSearchText').addEventListener('input', (event) => {
    if (finSearchDraft) finSearchDraft.q = event.target.value.trim();
});

function finSearchDone() {
    if (finSearchDraft) finApplyFilter(finSearchDraft);
    finSearchDraft = null;
}

document.getElementById('finSearchText').addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
        event.preventDefault();
        finSearchDone();
    }
});
document.getElementById('finSearchDone').addEventListener('click', finSearchDone);
document.getElementById('finSearchClear').addEventListener('click', () => {
    finSearchDraft = null;
    finApplyFilter(finEmptyFilter());
});
document.getElementById('finSearchAll').addEventListener('click', () => {
    finSearchDone();
    finSetRange({ mode: 'all' });
});
// Cerrar tocando fuera o con Escape aplica lo elegido, como Hecho
finSheetDismiss.set('finSearchSheet', finSearchDone);

document.getElementById('finSearchBtn').appendChild(financeIcon('search', 20));
document.getElementById('finSearchClear').appendChild(financeIcon('x', 18));
document.getElementById('finSearchBtn').addEventListener('click', openFinSearch);
