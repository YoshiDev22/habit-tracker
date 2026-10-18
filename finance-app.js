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
    // Qué se ve: 'period' (mes o quincena, lo que contestó), 'day', 'week',
    // 'month', 'year', 'all' o 'custom'; anchor es un día dentro (null = hoy)
    range: { mode: 'period', anchor: null, from: null, to: null },
    summary: null,
    transactions: [],
    accounts: [],
    categories: [],
    recurring: [],
    tab: 'categories',
    accountsSub: 'accounts',
    ringKind: 'expense',    // qué categorías rodean el anillo
    ringEditing: false,     // ✎: tocar dos categorías las cambia de lugar
    ringPick: null,         // la primera que se tocó
    accountFilter: null,    // Movimientos de una sola cuenta (desde su menú)
    hideTotal: false,       // 👁: el total de arriba, oculto (finance_hide_total)
    openStatements: new Set(),  // tarjetas con el detalle del estado de cuenta abierto (en la sesión)
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
    document.getElementById('finMenuBtn').textContent = finInitial();
    const module = finState.me.modules && finState.me.modules.finance;
    if (!module || !module.enabled) {
        location.replace('/');   // apagado o sin acceso: aquí no hay nada
        return;
    }
    if (!(await finAskConsent())) return;
    let saved = null;
    try {
        saved = localStorage.getItem('finance_tab');
        finState.hideTotal = localStorage.getItem('finance_hide_total') === '1';
        const mode = localStorage.getItem('finance_range');
        if (['period', 'week', 'month', 'year', 'all'].includes(mode)) finState.range.mode = mode;
    } catch (e) { /* sin localStorage */ }
    finSetTab(FIN_TABS.includes(saved) ? saved : 'categories', { save: false });
    await finLoad();
}

// El consentimiento expreso, la primera vez: hasta aceptarlo no se pide nada
// más (la API tampoco lo daría). Devuelve si se puede seguir.
async function finAskConsent() {
    try {
        const { consent_at } = await apiFetch('/api/finance/consent');
        if (consent_at) return true;
    } catch (error) {
        if (error.status !== 401) finShowError(error.message || 'No se pudo cargar Finanzas.');
        return false;
    }
    const screen = document.getElementById('finConsent');
    const accept = document.getElementById('finConsentAccept');
    screen.hidden = false;
    accept.focus();
    return new Promise((resolve) => {
        accept.addEventListener('click', async function onAccept() {
            accept.disabled = true;
            try {
                await apiFetch('/api/finance/consent', { method: 'POST' });
                accept.removeEventListener('click', onAccept);
                screen.hidden = true;
                resolve(true);
            } catch (error) {
                showError(document.getElementById('finConsentError'), error.message || 'No se pudo guardar. Intenta otra vez.');
            } finally {
                accept.disabled = false;
            }
        });
    });
}

// Las fechas del rango que se ve (salvo el periodo y "Siempre", que da el servidor)
function finRangeBounds() {
    const { mode, anchor, from, to } = finState.range;
    const day = anchor || finToday();
    const d = finDate(day);
    if (mode === 'day') return [day, day];
    if (mode === 'week') {
        const monday = finAddDays(day, -((d.getDay() + 6) % 7));
        return [monday, finAddDays(monday, 6)];
    }
    if (mode === 'month') {
        return [getDateKey(new Date(d.getFullYear(), d.getMonth(), 1)), getDateKey(new Date(d.getFullYear(), d.getMonth() + 1, 0))];
    }
    if (mode === 'year') return [`${d.getFullYear()}-01-01`, `${d.getFullYear()}-12-31`];
    if (mode === 'custom') return [from, to];
    return null;
}

async function finLoad() {
    document.getElementById('finError').classList.add('hidden');
    const { mode, anchor } = finState.range;
    const bounds = finRangeBounds();
    const query = bounds ? `?date_from=${bounds[0]}&date_to=${bounds[1]}`
        : mode === 'all' ? '?all=true' : (anchor ? `?day=${anchor}` : '');
    try {
        // Los fijos primero: generan lo que ya llegó, y el resumen ya lo cuenta
        const recurring = await apiFetch('/api/finance/recurring');
        const [summary, accounts, categories, plans] = await Promise.all([
            apiFetch(`/api/finance/summary${query}`),
            apiFetch('/api/finance/accounts'),
            apiFetch('/api/finance/categories'),
            // Las mensualidades de MSI solo se enseñan en la lista: sin ellas, todo lo demás sale
            apiFetch('/api/finance/installments').catch(() => ({ installments: [] })),
        ]);
        // La lista, con las fechas que dio el resumen (así "Siempre" sabe desde cuándo)
        const list = await apiFetch(`/api/finance/transactions?date_from=${summary.date_from}&date_to=${summary.date_to}`);
        Object.assign(finState, {
            summary, transactions: list.transactions, accounts: accounts.accounts,
            categories: categories.categories, recurring: recurring.recurring, installments: plans.installments,
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
    const hide = finState.hideTotal;
    totalEl.textContent = hide ? '•••••' : finMoney(total, main);
    totalEl.classList.toggle('negative', total < 0 && !hide);
    // Otras monedas, aparte: nunca se suman ni se convierten
    document.getElementById('finTotalMore').textContent = [...byCurrency.entries()]
        .filter(([currency]) => currency !== main)
        .map(([currency, cents]) => (hide ? `${currency} •••` : finMoney(cents, currency))).join(' · ');
    const eye = document.getElementById('finEyeBtn');
    eye.replaceChildren(financeIcon(hide ? 'eye-off' : 'eye', 18));
    eye.setAttribute('aria-pressed', String(hide));
    eye.setAttribute('aria-label', hide ? 'Mostrar el total' : 'Ocultar el total');
    eye.title = eye.getAttribute('aria-label');

    const s = finState.summary;
    document.getElementById('finPeriodLabel').textContent = finRangeLabel(s.date_from, s.date_to, finState.range.mode, s.period);
    // Siempre y un rango elegido no se recorren; nada en el futuro
    const fixed = ['all', 'custom'].includes(finState.range.mode);
    document.getElementById('finPrev').disabled = fixed;
    document.getElementById('finNext').disabled = fixed || finStep(1) > finToday();
}

function finMonthName(d) {
    const month = FIN_MONTHS[d.getMonth()];
    return `${month[0].toUpperCase()}${month.slice(1)}`;
}

function finRangeLabel(fromIso, toIso, mode, period) {
    const from = finDate(fromIso);
    const to = finDate(toIso);
    const today = finToday();
    if (mode === 'all') return 'Siempre';
    if (mode === 'year') return `Año ${from.getFullYear()}`;
    if (mode === 'day') {
        if (fromIso === today) return 'Hoy';
        if (fromIso === finAddDays(today, -1)) return 'Ayer';
        return finShortDate(fromIso);
    }
    if (mode === 'month' || (mode === 'period' && period === 'month')) return `${finMonthName(from)} ${from.getFullYear()}`;
    if (mode === 'custom' || from.getMonth() !== to.getMonth()) {
        return from.getFullYear() === to.getFullYear() && mode !== 'custom'
            ? `${from.getDate()} ${FIN_MONTHS_SHORT[from.getMonth()]} – ${to.getDate()} ${FIN_MONTHS_SHORT[to.getMonth()]}`
            : `${finShortDate(fromIso)} – ${finShortDate(toIso)}`;
    }
    return `${from.getDate()}–${to.getDate()} ${FIN_MONTHS_SHORT[to.getMonth()]} ${to.getFullYear()}`;
}

// Un día del rango anterior (step = -1) o del siguiente (1)
function finStep(step) {
    const s = finState.summary;
    const { mode } = finState.range;
    if (mode === 'period') return step < 0 ? s.prev_day : s.next_day;
    const d = finDate(s.date_from);
    if (mode === 'day') return finAddDays(s.date_from, step);
    if (mode === 'week') return finAddDays(s.date_from, 7 * step);
    if (mode === 'month') return getDateKey(new Date(d.getFullYear(), d.getMonth() + step, 1));
    if (mode === 'year') return `${d.getFullYear() + step}-01-01`;
    return s.date_from;
}

function finSetRange(range) {
    finState.range = { mode: 'period', anchor: null, from: null, to: null, ...range };
    try {
        if (['period', 'week', 'month', 'year', 'all'].includes(finState.range.mode)) {
            localStorage.setItem('finance_range', finState.range.mode);
        }
    } catch (e) { /* sin localStorage */ }
    finLoad();
}

function finGoToPeriod(day) {
    finState.range.anchor = day;
    finLoad();
}

// ============================================
// La hoja del periodo
// ============================================

const finRangeSheet = document.getElementById('finRangeSheet');

function openFinRange() {
    const today = finToday();
    const t = finDate(today);
    const monday = finAddDays(today, -((t.getDay() + 6) % 7));
    const s = finState.summary;
    document.getElementById('finRangeWeek').textContent = finRangeLabel(monday, finAddDays(monday, 6), 'week', 'month');
    document.getElementById('finRangeToday').textContent = finShortDate(today);
    document.getElementById('finRangeYear').textContent = `Año ${t.getFullYear()}`;
    document.getElementById('finRangeMonth').textContent = `${finMonthName(t)} ${t.getFullYear()}`;
    // La quincena, solo si cobra por quincena (si no, su periodo es el mes)
    const biweekly = s && s.period === 'biweekly';
    document.getElementById('finRangePeriod').hidden = !biweekly;
    document.getElementById('finRangePeriodLabel').textContent = biweekly ? 'Tu periodo' : '';
    document.getElementById('finRangeFrom').value = s ? s.date_from : today;
    document.getElementById('finRangeTo').value = s ? s.date_to : today;
    document.getElementById('finRangeDay').value = finState.range.mode === 'day' && s ? s.date_from : '';
    const active = finState.range.mode === 'period' && !biweekly ? 'month' : finState.range.mode;
    finRangeSheet.querySelectorAll('[data-range]').forEach(tile => {
        tile.classList.toggle('active', tile.dataset.range === active && (active !== 'day' || s.date_from === today));
    });
    openFinSheet(finRangeSheet);
}

finRangeSheet.querySelectorAll('[data-range]').forEach(tile => {
    tile.addEventListener('click', () => {
        const mode = tile.dataset.range;
        const biweekly = finState.summary && finState.summary.period === 'biweekly';
        closeFinSheet(finRangeSheet);
        // Si cobra por mes, "Mes" es su periodo (con su ‹ › de siempre)
        finSetRange({ mode: mode === 'month' && !biweekly ? 'period' : mode });
    });
});
document.getElementById('finRangeDay').addEventListener('change', (event) => {
    if (!event.target.value) return;
    closeFinSheet(finRangeSheet);
    finSetRange({ mode: 'day', anchor: event.target.value });
});
document.getElementById('finRangeApply').addEventListener('click', () => {
    let from = document.getElementById('finRangeFrom').value;
    let to = document.getElementById('finRangeTo').value;
    if (!from || !to) return;
    if (to < from) [from, to] = [to, from];
    closeFinSheet(finRangeSheet);
    finSetRange({ mode: 'custom', from, to });
});

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
    // El ✎ de ordenar, arriba, solo en Categorías; al salir, termina de ordenar
    document.getElementById('finRingEdit').hidden = tab !== 'categories';
    if (tab !== 'categories') {
        finState.ringEditing = false;
        finState.ringPick = null;
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
        const button = el('button', `fin-cat${finState.ringEditing ? ' editing' : ''}`
            + `${finState.ringPick === category.id ? ' picked' : ''}`);
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
    grid.replaceChildren(finRingCenter(categories, totals), ...cells, ...(finState.ringEditing ? [] : [add]));
    const edit = document.getElementById('finRingEdit');
    edit.replaceChildren(financeIcon(finState.ringEditing ? 'check' : 'pencil', 18));
    edit.setAttribute('aria-pressed', String(finState.ringEditing));
    edit.setAttribute('aria-label', finState.ringEditing ? 'Listo' : 'Ordenar categorías');
    edit.title = edit.getAttribute('aria-label');
    document.getElementById('finRingHint').hidden = !finState.ringEditing;
}

// Ordenar: la segunda categoría tocada cambia de lugar con la primera
async function finSwapCategories(firstId, secondId) {
    const kind = finState.ringKind;
    const ids = finKindCategories(kind).map(c => c.id);
    const a = ids.indexOf(firstId);
    const b = ids.indexOf(secondId);
    if (a < 0 || b < 0) return;
    [ids[a], ids[b]] = [ids[b], ids[a]];
    try {
        const body = await apiFetch('/api/finance/categories/order', { method: 'PUT', json: { kind, ids } });
        finState.categories = body.categories;
    } catch (error) {
        finShowError(error.message);
    }
    finRenderRing();
}

document.getElementById('finRingEdit').addEventListener('click', () => {
    finState.ringEditing = !finState.ringEditing;
    finState.ringPick = null;
    finRenderRing();
});

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
        finState.ringPick = null;
        finRenderRing();
        return;
    }
    if (finState.ringEditing) {
        const picked = event.target.closest('[data-category-id]');
        if (!picked) return;
        const id = Number(picked.dataset.categoryId);
        if (finState.ringPick === null || finState.ringPick === id) {
            finState.ringPick = finState.ringPick === id ? null : id;
            finRenderRing();
            return;
        }
        const first = finState.ringPick;
        finState.ringPick = null;
        finSwapCategories(first, id);
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
// Movimientos: por día
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

// El saldo con el que empezó una cuenta, en su día: solo se enseña (no es un
// movimiento ni un ingreso, así que no suma al día ni al resumen)
function finOpeningRow(account) {
    const row = el('button', 'fin-tx opening');
    row.type = 'button';
    row.dataset.openingAccount = String(account.id);
    const debt = account.kind === 'credit' && account.opening_balance_cents < 0;
    const text = el('span', 'fin-tx-text');
    text.append(el('strong', '', debt ? 'Deuda inicial' : 'Saldo inicial'), el('small', '', account.name));
    row.append(finBadge(finAccountIcon(account), finAccountColor(account), { square: true }), text,
        el('span', 'fin-tx-amount', formatMoney(account.opening_balance_cents, account.currency)));
    return row;
}

// Una mensualidad de MSI en el corte que la pide: también solo se enseña (la compra,
// o la deuda inicial, ya la contó)
function finBillRow({ plan, bill }) {
    const account = finAccount(plan.account_id);
    const row = el('button', 'fin-tx bill');
    row.type = 'button';
    row.dataset.openingAccount = String(plan.account_id);
    const text = el('span', 'fin-tx-text');
    text.append(el('strong', '', plan.concept),
        el('small', '', [`Meses sin intereses · ${bill.part} de ${plan.months}`, account ? account.name : ''].filter(Boolean).join(' · ')));
    row.append(finBadge('calendar-days', FIN_NEUTRAL), text,
        el('span', 'fin-tx-amount', formatMoney(bill.amount_cents, plan.currency)));
    return row;
}

function finBillsInPeriod(only) {
    const s = finState.summary;
    const out = [];
    (finState.installments || []).forEach(plan => {
        if (only && plan.account_id !== only.id) return;
        if (!finAccount(plan.account_id)) return;
        plan.bills.forEach(bill => {
            if (!s || (bill.cut >= s.date_from && bill.cut <= s.date_to)) out.push({ plan, bill });
        });
    });
    return out;
}

function finOpeningsInPeriod(only) {
    const s = finState.summary;
    return finState.accounts.filter(a => a.opening_date && a.opening_balance_cents
        && (!only || a.id === only.id) && (!s || (a.opening_date >= s.date_from && a.opening_date <= s.date_to)));
}

function finRenderList() {
    const list = document.getElementById('finTxList');
    const only = finState.accountFilter ? finAccount(finState.accountFilter) : null;
    if (!only) finState.accountFilter = null;
    document.getElementById('finTxFilter').hidden = !only;
    if (only) {
        document.getElementById('finTxFilterLabel').textContent = `Solo ${only.name}`;
        document.getElementById('finTxFilterClear').replaceChildren(financeIcon('x', 18));
    }
    const txs = only ? finState.transactions.filter(t => t.account_id === only.id || t.to_account_id === only.id)
        : finState.transactions;
    const openings = finOpeningsInPeriod(only);
    const bills = finBillsInPeriod(only);
    if (!txs.length && !openings.length && !bills.length) {
        list.replaceChildren(el('p', 'fin-empty', only ? `Sin movimientos de ${only.name} en este periodo.`
            : 'Sin movimientos en este periodo. Toca una categoría o ＋ Agregar.'));
        return;
    }
    const byDay = new Map();
    txs.forEach(tx => {
        if (!byDay.has(tx.tx_date)) byDay.set(tx.tx_date, []);
        byDay.get(tx.tx_date).push(tx);
    });
    openings.forEach(account => { if (!byDay.has(account.opening_date)) byDay.set(account.opening_date, []); });
    bills.forEach(({ bill }) => { if (!byDay.has(bill.cut)) byDay.set(bill.cut, []); });
    const main = finMainCurrency();
    const groups = [...byDay.entries()].sort((a, b) => (a[0] < b[0] ? 1 : -1)).map(([day, rows]) => {
        const net = rows.filter(t => t.currency === main && t.kind !== 'transfer')
            .reduce((acc, t) => acc + (t.kind === 'income' ? t.amount_cents : -t.amount_cents), 0);
        const group = el('section', 'fin-day');
        const head = el('div', 'fin-day-head');
        head.append(el('span', '', finDayTitle(day)), el('span', `fin-day-total${net < 0 ? ' expense' : net > 0 ? ' income' : ''}`, rows.length ? finMoney(net, main) : ''));
        // El saldo inicial va al empezar el día: abajo, porque la lista va del más reciente
        group.append(head, ...rows.map(finTxRow),
            ...bills.filter(b => b.bill.cut === day).map(finBillRow),
            ...openings.filter(a => a.opening_date === day).map(finOpeningRow));
        return group;
    });
    list.replaceChildren(...groups);
}

document.getElementById('finTxFilterClear').addEventListener('click', () => {
    finState.accountFilter = null;
    finRenderList();
});

document.getElementById('finEyeBtn').addEventListener('click', () => {
    finState.hideTotal = !finState.hideTotal;
    try {
        if (finState.hideTotal) localStorage.setItem('finance_hide_total', '1');
        else localStorage.removeItem('finance_hide_total');
    } catch (e) { /* sin localStorage: solo esta vez */ }
    finRenderTop();
});

document.getElementById('finTxList').addEventListener('click', (event) => {
    const opening = event.target.closest('[data-opening-account]');
    if (opening) {
        const account = finAccount(Number(opening.dataset.openingAccount));
        if (account) openFinAccountMenu(account);
        return;
    }
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
    const byMonth = (finDate(s.date_to) - finDate(s.date_from)) / 86400000 > 62;
    chart.append(el('h2', 'fin-card-title', byMonth ? 'Gasto por mes' : 'Gasto por día'),
        finDayColumns(s.date_from, s.date_to, expenses, byMonth));
    const last = s.date_to < today ? s.date_to : today;
    const days = Math.max(1, Math.round((finDate(last) - finDate(s.date_from)) / 86400000) + 1);
    const weekStart = (() => {
        const d = finDate(today);
        d.setDate(d.getDate() - ((d.getDay() + 6) % 7));   // el lunes
        return getDateKey(d);
    })();
    const sumWhere = test => expenses.filter(tx => test(tx.tx_date)).reduce((acc, tx) => acc + tx.amount_cents, 0);
    const stats = el('div', 'fin-tiles three');
    if (s.date_from <= today && today <= s.date_to) {
        stats.append(
            finStat('Promedio por día', finMoney(Math.round(t.expense_cents / days), main)),
            finStat('Hoy', finMoney(sumWhere(d => d === today), main)),
            finStat('Esta semana', finMoney(sumWhere(d => d >= weekStart && d <= today), main)),
        );
    } else {
        // Un rango que ya pasó: hoy y esta semana no dicen nada
        const perDay = new Map();
        expenses.forEach(tx => perDay.set(tx.tx_date, (perDay.get(tx.tx_date) || 0) + tx.amount_cents));
        stats.append(
            finStat('Promedio por día', finMoney(Math.round(t.expense_cents / days), main)),
            finStat('El día más alto', finMoney(Math.max(0, ...perDay.values()), main)),
            finStat('Compras', String(expenses.length)),
        );
    }
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

// Monto corto para el eje: $850, $3.2k, $12k
function finShortMoney(cents) {
    const value = cents / 100;
    if (value >= 10000) return `$${Math.round(value / 1000)}k`;
    if (value >= 1000) return `$${(value / 1000).toFixed(1).replace(/\.0$/, '')}k`;
    return `$${Math.round(value)}`;
}

// Columnas apiladas por categoría (un movimiento dividido, cada parte con su
// color): una por día, o una por mes si el rango pasa de dos meses
function finDayColumns(from, to, expenses, byMonth = false) {
    const keyOf = iso => (byMonth ? iso.slice(0, 7) : iso);
    const keys = [];
    for (let d = from; d <= to; d = finAddDays(d, 1)) {
        const key = keyOf(d);
        if (keys[keys.length - 1] !== key) keys.push(key);
    }
    const parts = new Map(keys.map(k => [k, new Map()]));
    expenses.forEach(tx => {
        const bucket = parts.get(keyOf(tx.tx_date));
        if (!bucket) return;
        const pieces = tx.splits && tx.splits.length ? tx.splits : [{ category_id: tx.category_id, amount_cents: tx.amount_cents }];
        pieces.forEach(p => bucket.set(p.category_id, (bucket.get(p.category_id) || 0) + p.amount_cents));
    });
    const totals = keys.map(k => [...parts.get(k).values()].reduce((acc, c) => acc + c, 0));
    const max = Math.max(1, ...totals);
    const left = 34;
    const width = 320;
    const height = 140;
    const top = 8;
    const plot = width - left;
    const colWidth = plot / keys.length;
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    const node = (tag, attrs, text) => {
        const n = document.createElementNS('http://www.w3.org/2000/svg', tag);
        Object.entries(attrs).forEach(([k, v]) => n.setAttribute(k, v));
        if (text !== undefined) n.textContent = text;
        return n;
    };
    svg.setAttribute('viewBox', `0 0 ${width} ${height + 18}`);
    svg.setAttribute('class', 'fin-columns');
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', byMonth ? 'Gasto de cada mes del rango' : 'Gasto de cada día del rango');
    // El eje: el más alto y la mitad, con su línea
    [1, 0.5].forEach(f => {
        const y = top + (height - top) * (1 - f);
        svg.append(node('line', { x1: left, x2: width, y1: y, y2: y, class: 'fin-columns-grid' }),
            node('text', { x: left - 4, y: y + 3, class: 'fin-columns-label', 'text-anchor': 'end' }, finShortMoney(max * f)));
    });
    svg.appendChild(node('line', { x1: left, x2: width, y1: height, y2: height, class: 'fin-columns-base' }));
    keys.forEach((key, i) => {
        let y = height;
        parts.get(key).forEach((cents, categoryId) => {
            const h = (cents / max) * (height - top);
            const category = finCategory(categoryId);
            const rect = node('rect', {
                x: left + i * colWidth + colWidth * 0.18, y: y - h, width: Math.max(1.5, colWidth * 0.64), height: h,
                rx: 1.5, fill: category ? finCategoryColor(category) : FIN_NEUTRAL,
            });
            const label = byMonth ? `${finMonthName(finDate(`${key}-01`))} ${key.slice(0, 4)}` : finShortDate(key);
            rect.appendChild(node('title', {}, `${label}: ${finMoney(totals[i])}${category ? ` (${category.name}: ${finMoney(cents)})` : ''}`));
            svg.appendChild(rect);
            y -= h;
        });
        // Etiquetas: la primera, la última y unas en medio
        const every = byMonth ? Math.max(1, Math.ceil(keys.length / 6)) : 7;
        if (i === 0 || i === keys.length - 1 || (i % every === 0 && keys.length - 1 - i > every / 2)) {
            const text = byMonth ? FIN_MONTHS_SHORT[Number(key.slice(5, 7)) - 1] : String(finDate(key).getDate());
            svg.appendChild(node('text', { x: left + i * colWidth + colWidth / 2, y: height + 14,
                class: 'fin-columns-label', 'text-anchor': 'middle' }, text));
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
    const label = st.upcoming
        ? `Próximo corte, el ${finShortDate(st.last_cut)}: pagar antes del ${finShortDate(st.due_date)}`
        : `Para no generar intereses, antes del ${finShortDate(st.due_date)}`;
    pay.append(el('span', 'fin-stat-label', label),
        el('strong', st.remaining_cents ? '' : 'paid',
            st.remaining_cents ? money(st.remaining_cents) : (st.upcoming ? 'Nada por ahora' : 'Pagado')));
    main.appendChild(pay);
    if (st.remaining_cents) {
        const button = el('button', 'submit-btn fin-pay-btn', 'Pagar');
        button.type = 'button';
        button.dataset.payCard = String(card.id);
        button.dataset.payAmount = String(st.remaining_cents);
        button.dataset.payDebt = String(Math.max(0, -card.balance_cents));
        main.appendChild(button);
    }
    lines.push(main);
    const facts = [];
    if (st.upcoming) {
        // Aún no corta: lo que lleva acumulado hasta hoy
        facts.push(`Llevas ${money(st.pay_no_interest_cents)} para ese corte`);
        if (st.msi_pending_cents) facts.push(`sin contar ${money(st.msi_pending_cents)} de meses que vienen después`);
    } else {
        facts.push(st.from_bank
            ? `Corte del ${finShortDate(st.last_cut)}: ${money(st.pay_no_interest_cents)}, según tu estado de cuenta `
              + `(la app calculaba ${money(st.estimated_cents)})`
            : `Corte del ${finShortDate(st.last_cut)}: ${money(st.pay_no_interest_cents)}`);
        if (st.paid_since_cut_cents) facts.push(`ya pagaste ${money(st.paid_since_cut_cents)}`);
        if (st.cycle_charges_cents) facts.push(`desde el corte, ${money(st.cycle_charges_cents)} (van al del ${finShortDate(st.next_cut)})`);
    }
    lines.push(el('p', 'fin-statement-facts', facts.join(' · ')));
    // El corte en curso se corrige con lo que dice el banco
    if (!st.upcoming) {
        const fix = el('button', 'link-btn fin-bank-edit', st.from_bank ? 'Cambiar el monto del banco'
            : 'Corregir con tu estado de cuenta');
        fix.type = 'button';
        fix.dataset.bankEdit = String(card.id);
        fix.dataset.cut = st.last_cut;
        fix.dataset.amount = String(st.pay_no_interest_cents);
        fix.dataset.fromBank = st.from_bank ? '1' : '';
        lines.push(fix);
    }
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
    // A la vista, solo cuánto pagar; el corte, corregirlo y los MSI, tras la flecha
    const [first, ...rest] = lines;
    const more = el('details', 'fin-statement-more');
    more.open = finState.openStatements.has(card.id);
    const summary = el('summary', '', 'Detalle');
    summary.appendChild(financeIcon('chevron-down', 16));
    more.append(summary, ...rest);
    more.addEventListener('toggle', () => {
        if (more.open) finState.openStatements.add(card.id);
        else finState.openStatements.delete(card.id);
    });
    return [first, more];
}

document.getElementById('finAccountTabs').addEventListener('click', (event) => {
    const button = event.target.closest('[data-sub]');
    if (!button) return;
    finState.accountsSub = button.dataset.sub;
    finRenderAccounts();
});
// El formulario de "lo que dice el banco", en lugar del enlace
function finBankForm(button) {
    const form = el('form', 'fin-bank-form');
    form.dataset.bankCard = button.dataset.bankEdit;
    form.dataset.cut = button.dataset.cut;
    const label = el('label', 'fin-field wide', 'Pago para no generar intereses, según tu estado de cuenta');
    const input = el('input');
    input.type = 'text';
    input.inputMode = 'decimal';
    input.autocomplete = 'off';
    input.value = (Number(button.dataset.amount) / 100).toFixed(2);
    label.appendChild(input);
    const actions = el('div', 'fin-form-actions wide');
    if (button.dataset.fromBank) {
        const reset = el('button', 'link-btn', 'Usar el cálculo de la app');
        reset.type = 'button';
        reset.dataset.bankReset = '1';
        actions.appendChild(reset);
    }
    const cancel = el('button', 'link-btn', 'Cancelar');
    cancel.type = 'button';
    cancel.dataset.bankCancel = '1';
    const save = el('button', 'submit-btn', 'Guardar');
    save.type = 'submit';
    actions.append(cancel, save);
    form.append(label, actions, el('div', 'form-error hidden'));
    button.replaceWith(form);
    input.select();
}

async function finSaveBank(form, reset) {
    const errorEl = form.querySelector('.form-error');
    const url = `/api/finance/accounts/${form.dataset.bankCard}/statement`;
    try {
        if (reset) {
            await apiFetch(`${url}?cut_date=${form.dataset.cut}`, { method: 'DELETE' });
        } else {
            const cents = parseMoneyCents(form.querySelector('input').value.trim());
            if (cents == null || cents < 0) return showError(errorEl, 'Escribe el monto: solo números.');
            await apiFetch(url, { method: 'PUT', json: { cut_date: form.dataset.cut, pay_no_interest_cents: cents } });
        }
        finRenderAccounts();
    } catch (error) {
        showError(errorEl, error.message);
    }
}

document.getElementById('finAccountsBody').addEventListener('submit', (event) => {
    const form = event.target.closest('.fin-bank-form');
    if (!form) return;
    event.preventDefault();
    finSaveBank(form, false);
});

document.getElementById('finAccountsBody').addEventListener('click', (event) => {
    const bankEdit = event.target.closest('[data-bank-edit]');
    if (bankEdit) {
        finBankForm(bankEdit);
        return;
    }
    if (event.target.closest('[data-bank-cancel]')) {
        finRenderAccounts();
        return;
    }
    if (event.target.closest('[data-bank-reset]')) {
        finSaveBank(event.target.closest('.fin-bank-form'), true);
        return;
    }
    const pay = event.target.closest('[data-pay-card]');
    if (pay) {
        const options = [{ label: 'Sin intereses', cents: Number(pay.dataset.payAmount) }];
        const debt = Number(pay.dataset.payDebt);
        if (debt > options[0].cents) options.push({ label: 'Toda la deuda', cents: debt });
        openFinEntry({ kind: 'transfer', toAccountId: Number(pay.dataset.payCard), amountCents: options[0].cents,
            payOptions: options });
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
    if (row) openFinAccountMenu(finAccount(Number(row.dataset.accountId)));
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
    document.getElementById('finPrev').appendChild(financeIcon('chevron-left', 18));
    document.getElementById('finNext').appendChild(financeIcon('chevron-right', 18));
    document.querySelectorAll('[data-icon]').forEach(span => span.appendChild(financeIcon(span.dataset.icon, 22)));
}

document.getElementById('finNav').addEventListener('click', (event) => {
    const button = event.target.closest('[data-tab]');
    if (button) finSetTab(button.dataset.tab);
});
document.getElementById('finPrev').addEventListener('click', () => {
    if (finState.summary) finGoToPeriod(finStep(-1));
});
document.getElementById('finNext').addEventListener('click', () => {
    if (finState.summary) finGoToPeriod(finStep(1));
});
document.getElementById('finPeriodLabel').addEventListener('click', openFinRange);
// ‹ regresa a la pestaña de la app de donde se vino (projects.js lee last_view)
document.getElementById('finBack').addEventListener('click', (event) => {
    if (history.length > 1 && document.referrer && new URL(document.referrer).origin === location.origin
        && new URL(document.referrer).pathname === '/') {
        event.preventDefault();
        history.back();
    }
});
document.getElementById('finMenuBtn').addEventListener('click', () => openFinDrawer());

document.addEventListener('DOMContentLoaded', finStart);
