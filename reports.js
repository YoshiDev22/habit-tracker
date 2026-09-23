// ============================================
// Reportes: en qué se fue el tiempo en un rango de fechas
// ============================================
//
// Tercera vista. Todo sale de endpoints que ya existen, pedidos con el rango
// elegido; las fechas son siempre las LOCALES del usuario (session_date,
// completed_at, getDateKey), igual que en el resto de la app.

const REPORTS_VIEW_INDEX = 2;
const MONTH_NAMES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio',
    'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
const MONTH_SHORT = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];

const reportsState = {
    kind: 'week',       // week | month | custom
    from: null,         // Date local, a medianoche
    to: null,           // Date local, incluido
    requestId: 0,       // descarta respuestas de un rango que ya no se ve
};

const reportsBody = document.getElementById('reportsBody');
const reportsRangeLabel = document.getElementById('reportsRangeLabel');
const reportsPrev = document.getElementById('reportsPrev');
const reportsNext = document.getElementById('reportsNext');
const reportsCustom = document.getElementById('reportsCustom');
const reportsFrom = document.getElementById('reportsFrom');
const reportsTo = document.getElementById('reportsTo');
const reportsRangeBtns = document.querySelectorAll('[data-range]');

// ============================================
// Fechas
// ============================================

function dateFromKey(key) {
    const [y, m, d] = key.split('-').map(Number);
    return new Date(y, m - 1, d);
}

function addDays(date, days) {
    return new Date(date.getFullYear(), date.getMonth(), date.getDate() + days);
}

function startOfToday() {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), now.getDate());
}

// La semana empieza en lunes: getDay() da 0 al domingo.
function startOfWeek(date) {
    return addDays(date, -((date.getDay() + 6) % 7));
}

function daysBetween(from, to) {
    // Con Math.round: un cambio de horario deja días de 23 o 25 horas.
    return Math.round((to - from) / 86400000) + 1;
}

function rangeFor(kind, anchor) {
    if (kind === 'month') {
        const from = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
        return { from, to: new Date(anchor.getFullYear(), anchor.getMonth() + 1, 0) };
    }
    const from = startOfWeek(anchor);
    return { from, to: addDays(from, 6) };
}

// El periodo inmediatamente anterior, del mismo tamaño: la semana o el mes
// anterior, o los mismos días justo antes en uno personalizado.
function previousRange() {
    const { kind, from, to } = reportsState;
    if (kind === 'month') {
        return rangeFor('month', new Date(from.getFullYear(), from.getMonth() - 1, 1));
    }
    const length = daysBetween(from, to);
    return { from: addDays(from, -length), to: addDays(from, -1) };
}

function formatRangeLabel() {
    const { kind, from, to } = reportsState;
    if (kind === 'month') {
        const name = MONTH_NAMES[from.getMonth()];
        return `${name.charAt(0).toUpperCase()}${name.slice(1)} ${from.getFullYear()}`;
    }
    const day = d => `${d.getDate()} ${MONTH_SHORT[d.getMonth()]}`;
    const sameYear = from.getFullYear() === to.getFullYear();
    const left = sameYear ? day(from) : `${day(from)} ${from.getFullYear()}`;
    return `${left} – ${day(to)} ${to.getFullYear()}`;
}

// ============================================
// Rango
// ============================================

function setRange(kind, from, to) {
    reportsState.kind = kind;
    reportsState.from = from;
    reportsState.to = to;

    reportsRangeBtns.forEach(btn => {
        btn.setAttribute('aria-pressed', String(btn.dataset.range === kind));
    });
    reportsCustom.classList.toggle('hidden', kind !== 'custom');
    reportsFrom.value = getDateKey(from);
    reportsTo.value = getDateKey(to);
    reportsRangeLabel.textContent = formatRangeLabel();
    // Hacia delante solo mientras el periodo no llegue a hoy
    reportsNext.disabled = to >= startOfToday();

    loadReports();
}

function shiftRange(direction) {
    const { kind, from, to } = reportsState;
    if (kind === 'month') {
        const { from: f, to: t } = rangeFor('month', new Date(from.getFullYear(), from.getMonth() + direction, 1));
        setRange(kind, f, t);
        return;
    }
    const length = daysBetween(from, to);
    setRange(kind, addDays(from, direction * length), addDays(to, direction * length));
}

reportsRangeBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        const kind = btn.dataset.range;
        if (kind === 'custom') {
            // Arranca con lo que se veía, para ajustarlo desde ahí
            setRange('custom', reportsState.from, reportsState.to);
            reportsFrom.focus();
            return;
        }
        const { from, to } = rangeFor(kind, startOfToday());
        setRange(kind, from, to);
    });
});

reportsPrev.addEventListener('click', () => shiftRange(-1));
reportsNext.addEventListener('click', () => shiftRange(1));

function onCustomDateChange() {
    if (!reportsFrom.value || !reportsTo.value) return;
    let from = dateFromKey(reportsFrom.value);
    let to = dateFromKey(reportsTo.value);
    if (from > to) [from, to] = [to, from];
    setRange('custom', from, to);
}

reportsFrom.addEventListener('change', onCustomDateChange);
reportsTo.addEventListener('change', onCustomDateChange);

// ============================================
// Carga
// ============================================

function isReportsVisible() {
    return typeof currentViewIndex !== 'undefined' && currentViewIndex === REPORTS_VIEW_INDEX;
}

async function loadReports() {
    // Solo se pide mientras la vista está a la vista: al entrar se recarga
    if (!getToken() || !isReportsVisible() || !reportsState.from) return;
    const requestId = ++reportsState.requestId;

    try {
        const data = await fetchReportData();
        if (requestId !== reportsState.requestId) return;
        renderReports(data);
    } catch (error) {
        if (requestId !== reportsState.requestId) return;
        console.error('Error al cargar los reportes:', error);
        reportsBody.replaceChildren(reportsMessage('No se pudieron cargar los reportes. Intenta de nuevo.'));
    }
}

async function fetchReportData() {
    return {};
}

function reportsMessage(text) {
    const p = document.createElement('p');
    p.className = 'empty-state';
    p.textContent = text;
    return p;
}

function renderReports() {
    reportsBody.replaceChildren();
}

// ============================================
// Hooks
// ============================================

function initReports() {
    const { from, to } = rangeFor('week', startOfToday());
    reportsState.kind = 'week';
    reportsState.from = from;
    reportsState.to = to;
    reportsRangeLabel.textContent = formatRangeLabel();
    reportsNext.disabled = true;
}

function resetReports() {
    reportsState.requestId++;
    reportsBody.replaceChildren();
    initReports();
}

// Al entrar a la vista se pide de nuevo: el tiempo y los hábitos cambian
// desde las otras dos, y a esta escala pedirlo otra vez es barato.
window.viewChangedHooks.push(index => {
    if (index === REPORTS_VIEW_INDEX) loadReports();
});
// Mientras se ve (p. ej. termina un pomodoro), también se refresca
window.projectsChangedHooks.push(() => {
    if (isReportsVisible()) loadReports();
});
window.appInitHooks.push(initReports);
window.appLogoutHooks.push(resetReports);
