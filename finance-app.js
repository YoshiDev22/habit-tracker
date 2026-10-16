// ============================================
// Finanzas: la página /finance (rediseño, docs/specs/finanzas.md)
// ============================================
//
// Otra página de la misma app: mismo servidor, misma API (/api/finance) y la
// misma sesión (el token de localStorage). Arriba, siempre, ‹ (regresa a /), el
// total de las cuentas y el periodo; abajo, cinco pestañas. Las cifras son del
// backend (backend/finance.py); aquí solo se pintan.
//
// Archivos: este (estado, carga y pestañas), finance-entry.js (la hoja del
// monto con su teclado), finance-settings.js (ajustes, cuentas, sueldo) y
// finance-import.js (pegar el estado de cuenta). Usa core.js e iconos de
// finance-icons.js.

const finState = {
    me: null,
    day: null,              // un día del periodo que se ve (null = hoy)
    summary: null,
    transactions: [],
    accounts: [],
    categories: [],
    recurring: [],
    tab: 'categories',
    accountsSub: 'accounts',
    ringKind: 'expense',    // qué categorías rodean el anillo
};

const FIN_TABS = ['accounts', 'categories', 'transactions', 'budget', 'overview'];
const FIN_MONTHS = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre',
    'octubre', 'noviembre', 'diciembre'];
const FIN_MONTHS_SHORT = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
const FIN_WEEKDAYS = ['dom', 'lun', 'mar', 'mié', 'jue', 'vie', 'sáb'];
const FIN_KIND_ICONS = { cash: 'banknote', debit: 'landmark', credit: 'credit-card' };
const FIN_KIND_LABELS = { cash: 'Efectivo', debit: 'Débito', credit: 'Crédito' };
// Las categorías de inicio guardadas antes de que hubiera iconos
const FIN_DEFAULT_ICONS = {
    'súper': 'shopping-basket', 'comer fuera': 'utensils', 'transporte': 'bus', 'casa y servicios': 'house',
    'suscripciones': 'tv', 'salud': 'heart-pulse', 'personal': 'shirt', 'ocio': 'ticket', 'otros': 'ellipsis',
    'sueldo': 'briefcase', 'otros ingresos': 'hand-coins',
};
const FIN_PALETTE = ['#27ae60', '#16a085', '#00b894', '#3498db', '#2563eb', '#5c6bc0', '#9b59b6', '#e84393',
    '#e74c3c', '#c0392b', '#e67e22', '#f1c40f', '#8d6e63', '#95a5a6', '#455a64'];
const FIN_NEUTRAL = '#95a5a6';

// Las capas que se abren encima, de abajo arriba: Escape cierra la última
const finSheets = [];

// apiFetch (core.js) la llama con un 401: sin sesión, a la app
function handleLogout() {
    removeToken();
    location.replace('/');
}

// ============================================
// Fechas y dinero
// ============================================

function finToday() {
    return getDateKey(new Date());
}

function finDate(iso) {
    const [y, m, d] = iso.split('-').map(Number);
    return new Date(y, m - 1, d);
}

function finAddDays(iso, days) {
    const d = finDate(iso);
    d.setDate(d.getDate() + days);
    return getDateKey(d);
}

function finShortDate(iso) {
    const d = finDate(iso);
    return `${d.getDate()} ${FIN_MONTHS_SHORT[d.getMonth()]} ${d.getFullYear()}`;
}

function finDayTitle(iso) {
    const today = finToday();
    const d = finDate(iso);
    const label = `${FIN_WEEKDAYS[d.getDay()]} ${d.getDate()} ${FIN_MONTHS_SHORT[d.getMonth()]}`;
    if (iso === today) return `Hoy · ${label}`;
    if (iso === finAddDays(today, -1)) return `Ayer · ${label}`;
    return label;
}

function finMainCurrency() {
    const account = finState.accounts.find(a => a.is_default) || finState.accounts[0];
    return account ? account.currency : 'MXN';
}

function finMoney(cents, currency = finMainCurrency()) {
    return formatMoney(cents, currency);
}

// ============================================
// Cuentas y categorías
// ============================================

function finAccount(id) {
    return finState.accounts.find(a => a.id === id);
}

function finCategory(id) {
    return finState.categories.find(c => c.id === id);
}

function finAccountIcon(account) {
    return account.icon || FIN_KIND_ICONS[account.kind] || 'wallet';
}

function finAccountColor(account) {
    return account.color || { cash: '#16a085', debit: '#5c6bc0', credit: '#e84393' }[account.kind] || FIN_NEUTRAL;
}

function finCategoryIcon(category) {
    return category.icon || FIN_DEFAULT_ICONS[normalizeKeepAccents(category.name)] || 'ellipsis';
}

function finCategoryColor(category) {
    return category.color || FIN_NEUTRAL;
}

function normalizeKeepAccents(text) {
    return String(text).trim().toLowerCase();
}

function finActiveAccounts() {
    return finState.accounts.filter(a => a.is_active);
}

function finKindCategories(kind) {
    return finState.categories.filter(c => c.kind === kind);
}

// Un círculo de color con el icono (cuenta o categoría)
function finBadge(icon, color, { size = 'md', square = false, faded = false } = {}) {
    const badge = el('span', `fin-badge ${size}${square ? ' square' : ''}${faded ? ' faded' : ''}`);
    badge.style.setProperty('--badge', color);
    badge.appendChild(financeIcon(icon, size === 'lg' ? 28 : size === 'sm' ? 16 : 22));
    return badge;
}

// ============================================
// Carga
// ============================================

async function finStart() {
    initConfirmDialog();
    watchSystemTheme();
    finPaintStaticIcons();
    try {
        finState.me = await apiFetch('/api/auth/me');
    } catch (error) {
        if (error.status !== 401) finShowError(error.message || 'No se pudo cargar Finanzas.');
        return;
    }
    const module = finState.me.modules && finState.me.modules.finance;
    if (!module || !module.enabled) {
        location.replace('/');   // apagado o sin acceso: aquí no hay nada
        return;
    }
    let saved = null;
    try { saved = localStorage.getItem('finance_tab'); } catch (e) { /* sin localStorage */ }
    finSetTab(FIN_TABS.includes(saved) ? saved : 'categories', { save: false });
    await finLoad();
}

async function finLoad() {
    document.getElementById('finError').classList.add('hidden');
    const day = finState.day ? `?day=${finState.day}` : '';
    try {
        // Los fijos primero: generan lo que ya llegó, y el resumen ya lo cuenta
        const recurring = await apiFetch('/api/finance/recurring');
        const [summary, list, accounts, categories] = await Promise.all([
            apiFetch(`/api/finance/summary${day}`),
            apiFetch(`/api/finance/transactions${day}`),
            apiFetch('/api/finance/accounts'),
            apiFetch('/api/finance/categories'),
        ]);
        Object.assign(finState, {
            summary, transactions: list.transactions, accounts: accounts.accounts,
            categories: categories.categories, recurring: recurring.recurring,
        });
    } catch (error) {
        if (error.status !== 401) finShowError(error.message || 'No se pudo cargar Finanzas.');
        return;
    }
    finRender();
}

function finShowError(message) {
    showError(document.getElementById('finError'), message);
}

function finRender() {
    if (!finState.summary) return;
    finRenderTop();
    const s = finState.summary;
    document.getElementById('finAsk').hidden = s.period_asked;
    document.getElementById('finSalaryHint').hidden = !s.period_asked || Boolean(finSalaryFixed());
    finRenderTab();
}

// ============================================
// Arriba: el total y el periodo
// ============================================

function finRenderTop() {
    const byCurrency = new Map();
    finActiveAccounts().forEach(a => byCurrency.set(a.currency, (byCurrency.get(a.currency) || 0) + a.balance_cents));
    const main = finMainCurrency();
    const total = byCurrency.get(main) || 0;
    const totalEl = document.getElementById('finTotal');
    totalEl.textContent = finMoney(total, main);
    totalEl.classList.toggle('negative', total < 0);
    // Otras monedas, aparte: nunca se suman ni se convierten
    document.getElementById('finTotalMore').textContent = [...byCurrency.entries()]
        .filter(([currency]) => currency !== main).map(([currency, cents]) => finMoney(cents, currency)).join(' · ');

    const s = finState.summary;
    const from = finDate(s.date_from);
    const to = finDate(s.date_to);
    let label;
    if (s.period === 'month') {
        const month = FIN_MONTHS[from.getMonth()];
        label = `${month[0].toUpperCase()}${month.slice(1)} ${from.getFullYear()}`;
    } else {
        label = `${from.getDate()}–${to.getDate()} ${FIN_MONTHS_SHORT[to.getMonth()]} ${to.getFullYear()}`;
    }
    document.getElementById('finPeriodLabel').textContent = label;
    // No hay movimientos en el futuro: el siguiente periodo empieza después de hoy
    document.getElementById('finNext').disabled = s.next_day > finToday();
}

function finGoToPeriod(day) {
    finState.day = day;
    finLoad();
}

// ============================================
// Pestañas
// ============================================

function finSetTab(tab, { save = true } = {}) {
    finState.tab = tab;
    document.querySelectorAll('.fin-tab').forEach(section => {
        section.hidden = section.dataset.tab !== tab;
    });
    document.querySelectorAll('.fin-nav-btn').forEach(button => {
        const active = button.dataset.tab === tab;
        button.classList.toggle('active', active);
        if (active) button.setAttribute('aria-current', 'page');
        else button.removeAttribute('aria-current');
    });
    if (save) {
        try { localStorage.setItem('finance_tab', tab); } catch (e) { /* sin localStorage */ }
    }
    finRenderTab();
    window.scrollTo({ top: 0 });
}

function finRenderTab() {
    if (!finState.summary) return;
    if (finState.tab === 'categories') finRenderRing();
    else if (finState.tab === 'transactions') finRenderList();
    else if (finState.tab === 'overview') finRenderOverview();
    else if (finState.tab === 'accounts') finRenderAccounts();
}

// ============================================
// Categorías: el anillo con los círculos alrededor
// ============================================

// Lo de cada categoría en el periodo, en la moneda principal
function finCategoryTotals() {
    const main = finMainCurrency();
    const totals = new Map();
    finState.summary.categories.filter(c => c.currency === main).forEach(c => {
        totals.set(c.category_id, (totals.get(c.category_id) || 0) + c.cents);
    });
    return totals;
}

function finPeriodTotals() {
    const main = finMainCurrency();
    return finState.summary.totals.find(t => t.currency === main)
        || { currency: main, expense_cents: 0, income_cents: 0, net_cents: 0 };
}

// Dónde va cada círculo: 4 arriba, 2 a cada lado del anillo, 4 abajo; el resto, debajo
function finRingSlot(index) {
    const around = [[1, 1], [1, 2], [1, 3], [1, 4], [2, 1], [2, 4], [3, 1], [3, 4], [4, 1], [4, 2], [4, 3], [4, 4]];
    if (index < around.length) return around[index];
    const extra = index - around.length;
    return [5 + Math.floor(extra / 4), (extra % 4) + 1];
}

function finRenderRing() {
    const grid = document.getElementById('finRingGrid');
    const kind = finState.ringKind;
    const categories = finKindCategories(kind);
    const totals = finCategoryTotals();
    const cells = categories.map((category, index) => {
        const cents = totals.get(category.id) || 0;
        const button = el('button', 'fin-cat');
        button.type = 'button';
        button.dataset.categoryId = String(category.id);
        const [row, col] = finRingSlot(index);
        button.style.gridRow = String(row);
        button.style.gridColumn = String(col);
        button.append(
            el('span', 'fin-cat-name', category.name),
            finBadge(finCategoryIcon(category), finCategoryColor(category), { size: 'lg', faded: !cents }),
            el('span', `fin-cat-amount${cents ? '' : ' zero'}`, finMoney(cents)),
        );
        button.querySelector('.fin-cat-amount').style.color = cents ? finCategoryColor(category) : '';
        button.setAttribute('aria-label', `${category.name}: ${finMoney(cents)}. Agregar ${kind === 'income' ? 'ingreso' : 'gasto'}`);
        return button;
    });
    // Agregar una categoría, en el siguiente lugar libre
    const add = el('button', 'fin-cat fin-cat-add');
    add.type = 'button';
    const [row, col] = finRingSlot(categories.length);
    add.style.gridRow = String(row);
    add.style.gridColumn = String(col);
    add.append(el('span', 'fin-cat-name', 'Nueva'), finBadge('plus', FIN_NEUTRAL, { size: 'lg', faded: true }),
        el('span', 'fin-cat-amount zero', ' '));
    add.setAttribute('aria-label', 'Nueva categoría');
    grid.replaceChildren(finRingCenter(categories, totals), ...cells, add);
}

// El anillo: lo de cada categoría como un arco de su color; en medio, el total
function finRingCenter(categories, totals) {
    const kind = finState.ringKind;
    const t = finPeriodTotals();
    const center = el('button', 'fin-ring');
    center.type = 'button';
    center.setAttribute('aria-label', kind === 'expense' ? 'Ver categorías de ingresos' : 'Ver categorías de gastos');
    const size = 160;
    const r = 66;
    const circumference = 2 * Math.PI * r;
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', `0 0 ${size} ${size}`);
    svg.setAttribute('class', 'fin-ring-svg');
    svg.setAttribute('aria-hidden', 'true');
    const track = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    Object.entries({ cx: size / 2, cy: size / 2, r, class: 'fin-ring-track' }).forEach(([k, v]) => track.setAttribute(k, v));
    svg.appendChild(track);
    const parts = categories.map(c => ({ c, cents: totals.get(c.id) || 0 })).filter(p => p.cents > 0);
    const sum = parts.reduce((acc, p) => acc + p.cents, 0);
    const gap = parts.length > 1 ? 3 : 0;
    let offset = 0;
    parts.forEach(({ c, cents }) => {
        const length = (cents / sum) * circumference;
        const arc = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        Object.entries({
            cx: size / 2, cy: size / 2, r, class: 'fin-ring-arc', stroke: finCategoryColor(c),
            'stroke-dasharray': `${Math.max(0, length - gap)} ${circumference}`,
            'stroke-dashoffset': String(-offset), transform: `rotate(-90 ${size / 2} ${size / 2})`,
        }).forEach(([k, v]) => arc.setAttribute(k, v));
        svg.appendChild(arc);
        offset += length;
    });
    const text = el('span', 'fin-ring-text');
    text.append(
        el('span', 'fin-ring-label', kind === 'expense' ? 'Gastos' : 'Ingresos'),
        el('strong', `fin-ring-main ${kind}`, finMoney(kind === 'expense' ? t.expense_cents : t.income_cents)),
        el('span', `fin-ring-other ${kind === 'expense' ? 'income' : 'expense'}`,
            finMoney(kind === 'expense' ? t.income_cents : t.expense_cents)),
    );
    center.append(svg, text);
    return center;
}

document.getElementById('finRingGrid').addEventListener('click', (event) => {
    if (event.target.closest('.fin-ring')) {
        finState.ringKind = finState.ringKind === 'expense' ? 'income' : 'expense';
        finRenderRing();
        return;
    }
    if (event.target.closest('.fin-cat-add')) {
        openFinSettings('categories', { kind: finState.ringKind });
        return;
    }
    const cell = event.target.closest('[data-category-id]');
    if (cell) openFinEntry({ kind: finState.ringKind, categoryId: Number(cell.dataset.categoryId) });
});

// ============================================
// Transacciones: por día
// ============================================

function finTxAmountText(tx) {
    const money = formatMoney(tx.amount_cents, tx.currency);
    if (tx.kind === 'income') return `+${money}`;
    if (tx.kind === 'expense') return `−${money}`;
    return money;
}

function finTxRow(tx) {
    const row = el('button', `fin-tx ${tx.kind}`);
    row.type = 'button';
    row.dataset.txId = String(tx.id);
    const account = finAccount(tx.account_id);
    let badge;
    let title;
    if (tx.kind === 'transfer') {
        badge = finBadge('arrow-left-right', FIN_NEUTRAL);
        title = 'Transferencia';
    } else if (tx.splits && tx.splits.length) {
        badge = finBadge('split', FIN_NEUTRAL);
        title = `${tx.splits.length} categorías`;
    } else {
        const category = finCategory(tx.category_id);
        badge = category ? finBadge(finCategoryIcon(category), finCategoryColor(category)) : finBadge('ellipsis', FIN_NEUTRAL);
        title = category ? category.name : 'Sin categoría';
    }
    const text = el('span', 'fin-tx-text');
    const to = tx.kind === 'transfer' ? finAccount(tx.to_account_id) : null;
    const where = [account ? account.name : '', to ? `→ ${to.name}` : ''].filter(Boolean).join(' ');
    const concept = tx.concept && tx.concept !== title ? tx.concept : '';
    const msi = tx.installment_id ? 'a meses' : '';
    text.append(el('strong', '', title), el('small', '', [concept, where, msi].filter(Boolean).join(' · ')));
    const amount = el('span', 'fin-tx-amount', finTxAmountText(tx));
    if (tx.recurring_id) amount.prepend(financeIcon('repeat', 14));
    row.append(badge, text, amount);
    return row;
}

function finRenderList() {
    const list = document.getElementById('finTxList');
    const txs = finState.transactions;
    if (!txs.length) {
        list.replaceChildren(el('p', 'fin-empty', 'Sin movimientos en este periodo. Toca una categoría o ＋ Agregar.'));
        return;
    }
    const byDay = new Map();
    txs.forEach(tx => {
        if (!byDay.has(tx.tx_date)) byDay.set(tx.tx_date, []);
        byDay.get(tx.tx_date).push(tx);
    });
    const main = finMainCurrency();
    const groups = [...byDay.entries()].sort((a, b) => (a[0] < b[0] ? 1 : -1)).map(([day, rows]) => {
        const net = rows.filter(t => t.currency === main && t.kind !== 'transfer')
            .reduce((acc, t) => acc + (t.kind === 'income' ? t.amount_cents : -t.amount_cents), 0);
        const group = el('section', 'fin-day');
        const head = el('div', 'fin-day-head');
        head.append(el('span', '', finDayTitle(day)), el('span', `fin-day-total${net < 0 ? '' : ' income'}`, finMoney(net, main)));
        group.append(head, ...rows.map(finTxRow));
        return group;
    });
    list.replaceChildren(...groups);
}

document.getElementById('finTxList').addEventListener('click', (event) => {
    const row = event.target.closest('[data-tx-id]');
    if (!row) return;
    const tx = finState.transactions.find(t => t.id === Number(row.dataset.txId));
    if (tx) openFinEntry({ tx });
});
document.getElementById('finAddBtn').addEventListener('click', () => openFinEntry({ kind: 'expense' }));

// ============================================
// Resumen
// ============================================

function finStat(label, value, className = '') {
    const box = el('div', `fin-stat ${className}`);
    box.append(el('span', 'fin-stat-label', label), el('strong', 'fin-stat-value', value));
    return box;
}

function finRenderOverview() {
    const s = finState.summary;
    const t = finPeriodTotals();
    const main = finMainCurrency();
    const today = finToday();
    const expenses = finState.transactions.filter(tx => tx.kind === 'expense' && tx.currency === main);

    const balance = el('section', 'fin-card fin-balance');
    balance.append(el('span', 'fin-stat-label', 'Balance del periodo'),
        el('strong', `fin-balance-value${t.net_cents < 0 ? ' negative' : ''}`, finMoney(t.net_cents, main)));
    const tiles = el('div', 'fin-tiles');
    tiles.append(finStat('Gastos', finMoney(t.expense_cents, main), 'expense'),
        finStat('Ingresos', finMoney(t.income_cents, main), 'income'));
    balance.appendChild(tiles);

    // Columnas por día, apiladas por categoría
    const chart = el('section', 'fin-card');
    chart.append(el('h2', 'fin-card-title', 'Gasto por día'), finDayColumns(s.date_from, s.date_to, expenses));
    const last = s.date_to < today ? s.date_to : today;
    const days = Math.max(1, Math.round((finDate(last) - finDate(s.date_from)) / 86400000) + 1);
    const weekStart = (() => {
        const d = finDate(today);
        d.setDate(d.getDate() - ((d.getDay() + 6) % 7));   // el lunes
        return getDateKey(d);
    })();
    const sumWhere = test => expenses.filter(tx => test(tx.tx_date)).reduce((acc, tx) => acc + tx.amount_cents, 0);
    const stats = el('div', 'fin-tiles three');
    stats.append(
        finStat('Promedio por día', finMoney(Math.round(t.expense_cents / days), main)),
        finStat('Hoy', finMoney(sumWhere(d => d === today), main)),
        finStat('Esta semana', finMoney(sumWhere(d => d >= weekStart && d <= today), main)),
    );
    chart.appendChild(stats);

    // Por categoría, con su porcentaje
    const totals = finCategoryTotals();
    const rows = finKindCategories('expense').map(c => ({ c, cents: totals.get(c.id) || 0 }))
        .filter(r => r.cents > 0).sort((a, b) => b.cents - a.cents);
    const byCategory = el('section', 'fin-card');
    byCategory.appendChild(el('h2', 'fin-card-title', 'Por categoría'));
    if (!rows.length) byCategory.appendChild(el('p', 'fin-empty', 'Aún no hay gastos en este periodo.'));
    rows.forEach(({ c, cents }) => {
        const pct = t.expense_cents ? Math.round((cents * 100) / t.expense_cents) : 0;
        const row = el('div', 'fin-catbar');
        const info = el('div', 'fin-catbar-info');
        info.append(el('span', 'fin-catbar-name', c.name), el('span', 'fin-catbar-amount', finMoney(cents, main)));
        const bar = el('div', 'fin-catbar-track');
        const fill = el('div', 'fin-catbar-fill');
        fill.style.width = `${pct}%`;
        fill.style.background = finCategoryColor(c);
        bar.appendChild(fill);
        const body = el('div', 'fin-catbar-body');
        body.append(info, bar);
        row.append(finBadge(finCategoryIcon(c), finCategoryColor(c), { size: 'sm' }), body, el('span', 'fin-catbar-pct', `${pct} %`));
        byCategory.appendChild(row);
    });
    document.getElementById('finOverview').replaceChildren(balance, chart, byCategory);
}

function finDayColumns(from, to, expenses) {
    const days = [];
    for (let d = from; d <= to; d = finAddDays(d, 1)) days.push(d);
    const perDay = new Map(days.map(d => [d, []]));
    expenses.forEach(tx => {
        if (perDay.has(tx.tx_date)) perDay.get(tx.tx_date).push(tx);
    });
    const totals = days.map(d => perDay.get(d).reduce((acc, tx) => acc + tx.amount_cents, 0));
    const max = Math.max(1, ...totals);
    const width = 320;
    const height = 140;
    const colWidth = width / days.length;
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', `0 0 ${width} ${height + 18}`);
    svg.setAttribute('class', 'fin-columns');
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', 'Gasto de cada día del periodo');
    days.forEach((day, i) => {
        let y = height;
        // Cada categoría, un pedazo de su color
        const byCat = new Map();
        perDay.get(day).forEach(tx => byCat.set(tx.category_id, (byCat.get(tx.category_id) || 0) + tx.amount_cents));
        byCat.forEach((cents, categoryId) => {
            const h = (cents / max) * (height - 6);
            const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
            const category = finCategory(categoryId);
            Object.entries({
                x: i * colWidth + colWidth * 0.18, y: y - h, width: Math.max(1, colWidth * 0.64), height: h,
                rx: 1.5, fill: category ? finCategoryColor(category) : FIN_NEUTRAL,
            }).forEach(([k, v]) => rect.setAttribute(k, v));
            const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
            title.textContent = `${finShortDate(day)}: ${finMoney(totals[i])}`;
            rect.appendChild(title);
            svg.appendChild(rect);
            y -= h;
        });
        // Etiquetas: el primer día, cada semana y el último
        if (i === 0 || i === days.length - 1 || (i % 7 === 0 && days.length - 1 - i > 3)) {
            const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
            Object.entries({ x: i * colWidth + colWidth / 2, y: height + 14, class: 'fin-columns-label', 'text-anchor': 'middle' })
                .forEach(([k, v]) => label.setAttribute(k, v));
            label.textContent = String(finDate(day).getDate());
            svg.appendChild(label);
        }
    });
    return svg;
}

// ============================================
// Cuentas
// ============================================

function finRenderAccounts() {
    document.querySelectorAll('#finAccountTabs [data-sub]').forEach(button => {
        button.setAttribute('aria-selected', String(button.dataset.sub === finState.accountsSub));
    });
    const body = document.getElementById('finAccountsBody');
    const sub = finState.accountsSub;
    if (sub === 'investments' || sub === 'debts') {
        const card = el('section', 'fin-card fin-soon');
        card.append(el('h2', 'fin-card-title', sub === 'investments' ? 'Inversiones' : 'Deudas'),
            el('p', 'fin-hint', sub === 'investments'
                ? 'Próximamente: lo que aportas, el valor que actualizas y una ganancia estimada, sin revolverlo con tu saldo.'
                : 'Próximamente: préstamos largos (carro, casa, negocio) con su pago y lo que falta, aparte del total de tus cuentas.'));
        body.replaceChildren(card);
        return;
    }
    const accounts = finActiveAccounts().filter(a => sub === 'cards' ? a.kind === 'credit' : true);
    const main = finMainCurrency();
    const head = el('div', 'fin-accounts-head');
    const sum = accounts.filter(a => a.currency === main).reduce((acc, a) => acc + a.balance_cents, 0);
    head.append(el('span', '', sub === 'cards' ? 'Tarjetas de crédito' : 'Cuentas'),
        el('strong', sum < 0 ? 'negative' : '', finMoney(sum, main)));
    const rows = accounts.map(a => {
        const row = el('button', 'fin-account');
        row.type = 'button';
        row.dataset.accountId = String(a.id);
        const text = el('span', 'fin-account-text');
        const balance = el('span', `fin-account-balance${a.balance_cents < 0 ? ' negative' : a.balance_cents === 0 ? ' zero' : ''}`,
            formatMoney(a.balance_cents, a.currency));
        text.append(el('strong', '', a.name), balance);
        const badge = finBadge(finAccountIcon(a), finAccountColor(a), { size: 'lg', square: true });
        if (a.is_default) badge.appendChild(el('span', 'fin-badge-star', '★'));
        const side = el('span', 'fin-account-side');
        if (a.available_cents != null) {
            side.append(el('small', '', 'Disponible'), el('span', 'fin-available', formatMoney(a.available_cents, a.currency)));
        }
        if (sub === 'cards' && (a.statement_day || a.due_day)) {
            side.appendChild(el('small', '', [a.statement_day ? `Corte: ${a.statement_day}` : '', a.due_day ? `Pago: ${a.due_day}` : '']
                .filter(Boolean).join(' · ')));
        }
        row.append(badge, text, side);
        return row;
    });
    const add = el('button', 'link-btn fin-add-account', sub === 'cards' ? '＋ Nueva tarjeta' : '＋ Nueva cuenta');
    add.type = 'button';
    add.dataset.newAccount = sub === 'cards' ? 'credit' : 'debit';
    if (!rows.length) rows.push(el('p', 'fin-empty', sub === 'cards' ? 'Aún no tienes tarjetas de crédito.' : 'Sin cuentas.'));
    if (sub !== 'cards') {
        body.replaceChildren(head, ...rows, add);
        return;
    }
    // Cada tarjeta, con su estado de cuenta debajo (se pide al entrar)
    const blocks = accounts.map((a, i) => {
        const block = el('div', 'fin-card-block');
        const statement = el('div', 'fin-statement');
        statement.dataset.statementFor = String(a.id);
        block.append(rows[i], statement);
        return block;
    });
    body.replaceChildren(head, ...(blocks.length ? blocks : rows), add);
    finLoadStatements(accounts);
}

async function finLoadStatements(cards) {
    let plans = [];
    try {
        plans = (await apiFetch('/api/finance/installments')).installments;
    } catch (error) { /* sin la lista de MSI: el estado de cuenta igual sale */ }
    await Promise.all(cards.map(async (card) => {
        const box = document.querySelector(`[data-statement-for="${card.id}"]`);
        if (!box) return;
        if (!card.statement_day || !card.due_day) {
            const hint = el('button', 'link-btn fin-statement-setup', 'Pon el día de corte y de pago para saber cuánto pagar');
            hint.type = 'button';
            hint.dataset.editAccount = String(card.id);
            box.replaceChildren(hint);
            return;
        }
        try {
            const st = await apiFetch(`/api/finance/accounts/${card.id}/statement`);
            box.replaceChildren(...finStatementView(card, st, plans.filter(p => p.account_id === card.id)));
        } catch (error) {
            box.replaceChildren(el('p', 'fin-hint', error.message));
        }
    }));
}

function finStatementView(card, st, plans) {
    const money = cents => formatMoney(cents, card.currency);
    const lines = [];
    const main = el('div', 'fin-statement-main');
    const pay = el('div', 'fin-statement-pay');
    pay.append(el('span', 'fin-stat-label', `Para no generar intereses, antes del ${finShortDate(st.due_date)}`),
        el('strong', st.remaining_cents ? '' : 'paid', st.remaining_cents ? money(st.remaining_cents) : 'Pagado'));
    main.appendChild(pay);
    if (st.remaining_cents) {
        const button = el('button', 'submit-btn fin-pay-btn', 'Pagar');
        button.type = 'button';
        button.dataset.payCard = String(card.id);
        button.dataset.payAmount = String(st.remaining_cents);
        main.appendChild(button);
    }
    lines.push(main);
    const facts = [`Corte del ${finShortDate(st.last_cut)}: ${money(st.pay_no_interest_cents)}`];
    if (st.paid_since_cut_cents) facts.push(`ya pagaste ${money(st.paid_since_cut_cents)}`);
    if (st.cycle_charges_cents) facts.push(`desde el corte, ${money(st.cycle_charges_cents)} (van al del ${finShortDate(st.next_cut)})`);
    lines.push(el('p', 'fin-statement-facts', facts.join(' · ')));
    if (plans.length) {
        const list = el('ul', 'fin-msi-list');
        plans.forEach(p => {
            const item = el('li', 'fin-msi');
            const done = p.billed >= p.months;
            const progress = p.billed ? `${p.billed} de ${p.months} facturadas`
                : `la primera, en el corte del ${finShortDate(p.next_statement)}`;
            item.append(el('span', '', p.concept),
                el('small', '', done ? `Liquidada (${p.months} meses)`
                    : `${progress} · ${money(p.monthly_cents)} al mes · faltan ${money(p.remaining_cents)}`));
            list.appendChild(item);
        });
        lines.push(el('p', 'fin-stat-label', 'Meses sin intereses'), list);
    }
    return lines;
}

document.getElementById('finAccountTabs').addEventListener('click', (event) => {
    const button = event.target.closest('[data-sub]');
    if (!button) return;
    finState.accountsSub = button.dataset.sub;
    finRenderAccounts();
});
document.getElementById('finAccountsBody').addEventListener('click', (event) => {
    const pay = event.target.closest('[data-pay-card]');
    if (pay) {
        openFinEntry({ kind: 'transfer', toAccountId: Number(pay.dataset.payCard), amountCents: Number(pay.dataset.payAmount) });
        return;
    }
    const setup = event.target.closest('[data-edit-account]');
    if (setup) {
        openFinAccount(finAccount(Number(setup.dataset.editAccount)));
        return;
    }
    const add = event.target.closest('[data-new-account]');
    if (add) {
        openFinAccount(null, add.dataset.newAccount);
        return;
    }
    const row = event.target.closest('[data-account-id]');
    if (row) openFinAccount(finAccount(Number(row.dataset.accountId)));
});

// ============================================
// Capas (hojas y modales) y navegación
// ============================================

function openFinSheet(sheet) {
    sheet.classList.remove('hidden');
    finSheets.push(sheet);
    document.body.classList.add('fin-sheet-open');
}

function closeFinSheet(sheet) {
    sheet.classList.add('hidden');
    const i = finSheets.indexOf(sheet);
    if (i > -1) finSheets.splice(i, 1);
    if (!finSheets.length) document.body.classList.remove('fin-sheet-open');
}

document.querySelectorAll('.fin-sheet [data-close-sheet]').forEach(overlay => {
    overlay.addEventListener('click', () => finDismissSheet(overlay.closest('.fin-sheet')));
});

// Cada hoja puede tener su forma de cerrarse (p. ej. el monto pregunta si descartar)
const finSheetDismiss = new Map();

function finDismissSheet(sheet) {
    const custom = finSheetDismiss.get(sheet.id);
    if (custom) custom();
    else closeFinSheet(sheet);
}

document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    if (!document.getElementById('confirmModal').classList.contains('hidden')) {
        resolveConfirmDialog(false);
        return;
    }
    const top = finSheets[finSheets.length - 1];
    if (top) {
        event.preventDefault();
        finDismissSheet(top);
    }
});

document.querySelector('#confirmModal .modal-overlay').addEventListener('click', () => resolveConfirmDialog(false));

// Los iconos fijos del HTML (flechas, pestañas, ajustes)
function finPaintStaticIcons() {
    document.getElementById('finBack').appendChild(financeIcon('chevron-left', 22));
    document.getElementById('finSettingsBtn').appendChild(financeIcon('settings', 20));
    document.getElementById('finPrev').appendChild(financeIcon('chevron-left', 18));
    document.getElementById('finNext').appendChild(financeIcon('chevron-right', 18));
    document.querySelectorAll('[data-icon]').forEach(span => span.appendChild(financeIcon(span.dataset.icon, 22)));
}

document.getElementById('finNav').addEventListener('click', (event) => {
    const button = event.target.closest('[data-tab]');
    if (button) finSetTab(button.dataset.tab);
});
document.getElementById('finPrev').addEventListener('click', () => {
    if (finState.summary) finGoToPeriod(finState.summary.prev_day);
});
document.getElementById('finNext').addEventListener('click', () => {
    if (finState.summary) finGoToPeriod(finState.summary.next_day);
});
document.getElementById('finPeriodLabel').addEventListener('click', () => finGoToPeriod(null));
// ‹ regresa a la pestaña de la app de donde se vino (projects.js lee last_view)
document.getElementById('finBack').addEventListener('click', (event) => {
    if (history.length > 1 && document.referrer && new URL(document.referrer).origin === location.origin
        && new URL(document.referrer).pathname === '/') {
        event.preventDefault();
        history.back();
    }
});
document.getElementById('finSettingsBtn').addEventListener('click', () => openFinSettings());

document.addEventListener('DOMContentLoaded', finStart);
