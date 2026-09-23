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
    sawFirstProjects: false,  // la primera carga de proyectos de la sesión no es un cambio
    tagIds: new Set(),  // etiquetas elegidas para su total sin contar doble
};

const reportsBody = document.getElementById('reportsBody');
const reportsRangeLabel = document.getElementById('reportsRangeLabel');
const reportsPrev = document.getElementById('reportsPrev');
const reportsNext = document.getElementById('reportsNext');
const reportsCustom = document.getElementById('reportsCustom');
const reportsFrom = document.getElementById('reportsFrom');
const reportsTo = document.getElementById('reportsTo');
const reportsRangeBtns = document.querySelectorAll('[data-range]');
const reportsExportBtn = document.getElementById('reportsExport');

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

function rangeQuery(from, to) {
    return `date_from=${getDateKey(from)}&date_to=${getDateKey(to)}`;
}

// Solo foco: los descansos no son trabajo, y así las cifras cuadran con las
// de las tarjetas y la vista Lista.
async function fetchFocusSessions(from, to) {
    const data = await apiFetch(`/api/pomodoro?${rangeQuery(from, to)}`);
    return data.sessions.filter(s => s.mode === 'focus');
}

async function fetchReportData() {
    const { from, to } = reportsState;
    const prev = previousRange();
    const tagQuery = [...reportsState.tagIds].map(id => `&tag_ids=${id}`).join('');
    const completedQuery = (f, t) => `/api/tasks?completed_from=${getDateKey(f)}&completed_to=${getDateKey(t)}`;
    const [sessions, prevSessions, projectsData, tagSummary, completed, prevCompleted, habitReport] = await Promise.all([
        fetchFocusSessions(from, to),
        fetchFocusSessions(prev.from, prev.to),
        // Con los archivados: su tiempo del rango también cuenta
        apiFetch('/api/projects?include_inactive=true'),
        apiFetch(`/api/tags/summary?${rangeQuery(from, to)}${tagQuery}`),
        apiFetch(completedQuery(from, to)),
        apiFetch(completedQuery(prev.from, prev.to)),
        apiFetch(`/api/habits/report?${rangeQuery(from, to)}&today=${getDateKey(new Date())}`),
    ]);
    return {
        sessions, prevSessions, projects: projectsData.projects, tagSummary,
        completed: completed.tasks, prevCompleted: prevCompleted.tasks, habitReport,
    };
}

function reportsMessage(text) {
    const p = document.createElement('p');
    p.className = 'empty-state';
    p.textContent = text;
    return p;
}

function sumSeconds(sessions) {
    return sessions.reduce((total, s) => total + s.duration_seconds, 0);
}

// Días del rango que ya pasaron (hoy incluido): el promedio no se diluye
// con los que faltan de la semana o el mes.
function elapsedDays() {
    const { from, to } = reportsState;
    const today = startOfToday();
    if (from > today) return 0;
    return daysBetween(from, to < today ? to : today);
}

function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
}

function reportCard(title, ...children) {
    const card = el('section', 'report-card');
    card.appendChild(el('h3', 'report-card-title', title));
    children.forEach(child => child && card.appendChild(child));
    return card;
}

function renderReports(data) {
    // Una sección sin nada que mostrar devuelve null y se omite
    reportsBody.replaceChildren(...[
        renderSummary(data),
        renderHabits(data),
        renderByDay(data),
        renderByProject(data),
        renderByTag(data),
        renderCompleted(data),
        renderByHour(data),
        renderBySource(data),
    ].filter(Boolean));
}

// ============================================
// Resumen
// ============================================

function previousPeriodName() {
    if (reportsState.kind === 'week') return 'la semana anterior';
    if (reportsState.kind === 'month') return 'el mes anterior';
    return 'el periodo anterior';
}

function comparisonText(total, prevTotal) {
    if (prevTotal === 0) {
        return total > 0 ? `Sin tiempo registrado en ${previousPeriodName()}` : '';
    }
    const diff = total - prevTotal;
    if (Math.abs(diff) < 60) return `Igual que ${previousPeriodName()}`;
    const sign = diff > 0 ? '+' : '−';
    return `${sign}${formatDuration(Math.abs(diff))} vs. ${previousPeriodName()}`;
}

function summaryStat(value, label) {
    const stat = el('div', 'report-stat');
    stat.append(el('span', 'report-stat-value', value), el('span', 'report-stat-label', label));
    return stat;
}

function renderSummary({ sessions, prevSessions, completed, prevCompleted }) {
    const total = sumSeconds(sessions);
    const prevTotal = sumSeconds(prevSessions);
    const days = elapsedDays();
    const activeDays = new Set(sessions.map(s => s.session_date)).size;

    const grid = el('div', 'report-stats');
    grid.append(
        summaryStat(formatDuration(total), 'tiempo total'),
        summaryStat(days ? formatDuration(Math.round(total / days)) : '—', 'promedio por día'),
        summaryStat(`${activeDays}${days ? ` de ${days}` : ''}`, 'días con tiempo'),
        summaryStat(String(completed.length), completed.length === 1 ? 'tarea terminada' : 'tareas terminadas'),
    );

    const comparison = comparisonText(total, prevTotal);
    const note = comparison
        ? el('p', `report-compare ${total >= prevTotal ? 'up' : 'down'}`, comparison)
        : null;
    const diffTasks = completed.length - prevCompleted.length;
    const tasksNote = (completed.length || prevCompleted.length) && diffTasks !== 0
        ? el('p', 'report-compare-small',
            `${diffTasks > 0 ? '+' : '−'}${Math.abs(diffTasks)} ${Math.abs(diffTasks) === 1 ? 'tarea' : 'tareas'} vs. ${previousPeriodName()}`)
        : null;
    return reportCard('Resumen', grid, note, tasksNote);
}

// ============================================
// Hábitos
// ============================================

function daysText(n) {
    return `${n} ${n === 1 ? 'día' : 'días'}`;
}

function renderHabits({ habitReport }) {
    const report = habitReport;
    if (report.habits.length === 0) {
        return reportCard('Hábitos', reportsMessage('Aún no tienes hábitos: configúralos desde el Calendario.'));
    }

    // La racha es la del backend (calculate_streak), la misma del calendario
    const streak = el('div', 'streak-container report-streak');
    const info = el('div', 'streak-info');
    info.append(el('span', 'streak-count', String(report.streak)),
        el('span', 'streak-label', report.streak === 1 ? 'día seguido' : 'días seguidos'));
    streak.append(el('div', 'streak-icon', '🔥'), info);
    const facts = el('div', 'report-streak-facts');
    facts.append(el('span', '', `Récord: ${daysText(report.best_streak)}`));
    if (report.days_elapsed > 0) {
        facts.append(el('span', '', `Con algún hábito: ${report.active_days} de ${daysText(report.days_elapsed)}`));
    }
    streak.appendChild(facts);

    // Los días de descanso no cuentan como días que tocaban
    const target = Math.max(0, report.days_elapsed - report.rest_days_elapsed);
    const list = el('ul', 'report-bars');
    report.habits.forEach(habit => {
        const color = habit.color;
        const item = el('li', 'report-bar-row');
        const head = el('div', 'report-bar-head');
        const name = el('span', 'report-bar-name');
        const dot = el('i', 'report-bar-dot');
        if (color) dot.style.background = color;
        name.append(dot, document.createTextNode(habitDisplayName(habit.icon, habit.label)));
        const value = target > 0 && habit.days_done <= target
            ? `${habit.days_done} de ${daysText(target)}`
            : daysText(habit.days_done);
        head.append(name, el('span', 'report-bar-value', value));

        const track = el('div', 'report-bar-track');
        const fill = el('div', 'report-bar-fill');
        fill.style.width = `${target > 0 ? Math.min(1, habit.days_done / target) * 100 : 0}%`;
        if (color) fill.style.background = color;
        track.appendChild(fill);

        const meta = el('div', 'report-habit-meta');
        meta.textContent = habit.current_streak > 0
            ? `🔥 ${daysText(habit.current_streak)} seguidos · récord ${daysText(habit.best_streak)}`
            : `Récord: ${daysText(habit.best_streak)}`;
        item.append(head, track, meta);
        list.appendChild(item);
    });

    const note = report.rest_days_elapsed > 0
        ? el('p', 'report-note', 'Los días de descanso no cuentan en el total de días.')
        : null;
    return reportCard('Hábitos', streak, list, note);
}

// ============================================
// Tiempo por día
// ============================================

const SVG_NS = 'http://www.w3.org/2000/svg';
const WEEKDAY_INITIALS = ['D', 'L', 'M', 'X', 'J', 'V', 'S'];   // por getDay()

function svg(tag, attrs = {}) {
    const node = document.createElementNS(SVG_NS, tag);
    Object.entries(attrs).forEach(([k, v]) => node.setAttribute(k, v));
    return node;
}

function svgText(attrs, text) {
    const node = svg('text', attrs);
    node.textContent = text;
    return node;
}

// Ancho real de la tarjeta, no uno fijo escalado: en el teléfono un viewBox
// de 600 dejaría los textos en 7px.
function chartWidth() {
    const available = reportsBody.clientWidth - 40;   // padding de .report-card
    return Math.max(280, Math.min(900, available || 600));
}

// users.rest_days usa weekday() de Python: lunes = 0. getDay() da domingo = 0.
function isRestDay(date) {
    const restDays = (typeof currentUser !== 'undefined' && currentUser && currentUser.rest_days) || [];
    return restDays.includes((date.getDay() + 6) % 7);
}

function renderByDay({ sessions }) {
    const { from, to } = reportsState;
    const count = daysBetween(from, to);
    const byDate = {};
    sessions.forEach(s => { byDate[s.session_date] = (byDate[s.session_date] || 0) + s.duration_seconds; });

    const days = Array.from({ length: count }, (_, i) => {
        const date = addDays(from, i);
        const key = getDateKey(date);
        return { date, key, seconds: byDate[key] || 0 };
    });
    // Escala en horas enteras y múltiplo del paso, para que la guía de arriba
    // quede por encima de la barra más alta.
    const peakHours = Math.max(1, Math.ceil(Math.max(...days.map(d => d.seconds)) / 3600));
    const hourStep = peakHours <= 4 ? 1 : Math.ceil(peakHours / 4);
    const maxHours = Math.ceil(peakHours / hourStep) * hourStep;

    const W = chartWidth(), H = 190, L = 34, R = 6, T = 10, B = 34;
    const plotW = W - L - R, plotH = H - T - B;
    const step = plotW / count;
    const barW = Math.max(3, Math.min(34, step * 0.62));
    const y = seconds => T + plotH - (seconds / (maxHours * 3600)) * plotH;
    const todayKey = getDateKey(startOfToday());

    const chart = svg('svg', { viewBox: `0 0 ${W} ${H}`, class: 'report-chart', role: 'img',
        'aria-label': 'Tiempo registrado por día' });

    for (let h = 0; h <= maxHours; h += hourStep) {
        chart.appendChild(svg('line', { x1: L, x2: W - R, y1: y(h * 3600), y2: y(h * 3600), class: 'chart-grid' }));
        chart.appendChild(svgText({ x: L - 6, y: y(h * 3600) + 4, class: 'chart-axis', 'text-anchor': 'end' }, `${h}h`));
    }

    // En un mes no caben todas las etiquetas: una cada pocos días
    const labelEvery = count <= 14 ? 1 : count <= 31 ? 5 : Math.ceil(count / 7);
    days.forEach((day, i) => {
        const cx = L + step * i + step / 2;
        if (isRestDay(day.date)) {
            chart.appendChild(svg('rect', { x: L + step * i + 1, y: T, width: Math.max(1, step - 2), height: plotH,
                class: 'chart-rest' }));
        }
        if (day.seconds > 0) {
            const top = y(day.seconds);
            const bar = svg('rect', { x: cx - barW / 2, y: top, width: barW, height: T + plotH - top, rx: 3,
                class: 'chart-bar' });
            const tip = svg('title');
            tip.textContent = `${day.date.getDate()} ${MONTH_SHORT[day.date.getMonth()]}: ${formatDuration(day.seconds)}`;
            bar.appendChild(tip);
            chart.appendChild(bar);
        }
        if (i % labelEvery === 0) {
            const cls = `chart-axis${day.key === todayKey ? ' today' : ''}`;
            const top = count <= 7 ? WEEKDAY_INITIALS[day.date.getDay()] : String(day.date.getDate());
            chart.appendChild(svgText({ x: cx, y: H - B + 16, class: cls, 'text-anchor': 'middle' }, top));
            if (count <= 7) {
                chart.appendChild(svgText({ x: cx, y: H - B + 29, class: `${cls} small`, 'text-anchor': 'middle' },
                    String(day.date.getDate())));
            }
        }
    });

    let legend = null;
    if (days.some(d => isRestDay(d.date))) {
        legend = el('div', 'report-legend');
        const item = el('span', 'legend-item');
        item.append(el('i', 'legend-swatch rest'), document.createTextNode('Día de descanso'));
        legend.appendChild(item);
    }
    return reportCard('Tiempo por día', chart, legend);
}

// ============================================
// Barras horizontales (proyectos y etiquetas)
// ============================================

// rows: [{ name, color, seconds, note?, muted? }]. La barra es relativa a la
// fila más larga; el porcentaje, al total que se pase (si se pasa).
function barList(rows, total) {
    const max = Math.max(1, ...rows.map(r => r.seconds));
    const list = el('ul', 'report-bars');
    rows.forEach(row => {
        const item = el('li', `report-bar-row${row.muted ? ' muted' : ''}`);
        const head = el('div', 'report-bar-head');
        const name = el('span', 'report-bar-name');
        const dot = el('i', 'report-bar-dot');
        if (row.color) dot.style.background = row.color;
        name.append(dot, document.createTextNode(row.name));
        if (row.note) name.appendChild(el('span', 'report-bar-note', row.note));
        const value = el('span', 'report-bar-value', formatDuration(row.seconds));
        if (total) value.appendChild(el('span', 'report-bar-pct', ` · ${Math.round(row.seconds / total * 100)}%`));
        head.append(name, value);

        const track = el('div', 'report-bar-track');
        const fill = el('div', 'report-bar-fill');
        fill.style.width = `${(row.seconds / max) * 100}%`;
        if (row.color) fill.style.background = row.color;
        track.appendChild(fill);
        item.append(head, track);
        list.appendChild(item);
    });
    return list;
}

// ============================================
// Por proyecto
// ============================================

function renderByProject({ sessions, projects }) {
    const byId = new Map(projects.map(p => [p.id, p]));
    const seconds = new Map();
    let unassigned = 0;
    sessions.forEach(s => {
        const project = byId.get(s.project_id);
        // "Sin asignar" y las sesiones sin proyecto son lo mismo: tiempo sin clasificar
        if (!project || project.is_system) {
            unassigned += s.duration_seconds;
            return;
        }
        seconds.set(project.id, (seconds.get(project.id) || 0) + s.duration_seconds);
    });

    const total = sumSeconds(sessions);
    if (total === 0) return reportCard('Por proyecto', reportsMessage('Sin tiempo registrado en este periodo.'));

    const rows = [...seconds.entries()]
        .map(([id, secs]) => {
            const p = byId.get(id);
            return { name: p.icon ? `${p.icon} ${p.name}` : p.name, color: p.color, seconds: secs,
                note: p.is_active ? '' : 'archivado' };
        })
        .sort((a, b) => b.seconds - a.seconds);
    if (unassigned > 0) {
        rows.push({ name: 'Sin asignar', seconds: unassigned, note: 'sin clasificar', muted: true });
    }
    return reportCard('Por proyecto', barList(rows, total));
}

// ============================================
// Por etiqueta
// ============================================

function renderByTag({ tagSummary }) {
    const used = tagSummary.summaries.filter(t => t.total_seconds > 0)
        .sort((a, b) => b.total_seconds - a.total_seconds);
    // Una etiqueta elegida que ya no tiene tiempo en el rango deja de contar
    const usedIds = new Set(used.map(t => t.tag_id));
    [...reportsState.tagIds].forEach(id => { if (!usedIds.has(id)) reportsState.tagIds.delete(id); });

    if (used.length === 0 && tagSummary.untagged_seconds === 0) {
        return reportCard('Por etiqueta', reportsMessage('Sin tiempo registrado en este periodo.'));
    }

    const rows = used.map(t => ({ name: t.name, color: t.color, seconds: t.total_seconds, tagId: t.tag_id }));
    if (tagSummary.untagged_seconds > 0) {
        rows.push({ name: 'Sin etiqueta', seconds: tagSummary.untagged_seconds, muted: true });
    }
    const list = barList(rows);

    // Tocar una etiqueta la elige; con dos o más se ve su total sin contar doble
    [...list.children].forEach((item, i) => {
        const tagId = rows[i].tagId;
        if (tagId === undefined) return;
        item.classList.add('selectable');
        item.tabIndex = 0;
        item.setAttribute('role', 'button');
        item.setAttribute('aria-pressed', String(reportsState.tagIds.has(tagId)));
        const toggle = () => {
            if (reportsState.tagIds.has(tagId)) reportsState.tagIds.delete(tagId);
            else reportsState.tagIds.add(tagId);
            loadReports();
        };
        item.addEventListener('click', toggle);
        item.addEventListener('keydown', (event) => {
            if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                toggle();
            }
        });
    });

    let footer;
    if (reportsState.tagIds.size >= 2) {
        footer = el('p', 'report-note strong',
            `Juntas: ${formatDuration(tagSummary.combined_seconds)}, cada sesión contada una vez.`);
    } else {
        footer = el('p', 'report-note',
            'Una sesión cuenta en cada etiqueta de su tarea, así que estos tiempos no se suman entre sí. '
            + 'Elige varias para ver su total sin contar doble.');
    }
    return reportCard('Por etiqueta', list, footer);
}

// ============================================
// Tareas terminadas
// ============================================

const COMPLETED_PREVIEW = 8;

function renderCompleted({ completed, projects }) {
    if (completed.length === 0) {
        return reportCard('Tareas terminadas', reportsMessage('Ninguna tarea terminada en este periodo.'));
    }
    const byId = new Map(projects.map(p => [p.id, p]));
    // Lo más reciente primero; el mismo día, en el orden del tablero
    const tasks = [...completed].sort((a, b) => b.completed_at.localeCompare(a.completed_at));

    const list = el('ul', 'report-tasks');
    tasks.forEach((task, i) => {
        const item = el('li', 'report-task');
        if (i >= COMPLETED_PREVIEW) item.classList.add('hidden');
        const project = byId.get(task.project_id);
        const dot = el('i', 'report-bar-dot');
        if (project && project.color && !project.is_system) dot.style.background = project.color;
        const main = el('div', 'report-task-main');
        main.append(el('span', 'report-task-title', task.title),
            el('span', 'report-task-meta', project && !project.is_system ? project.name : 'Sin asignar'));
        const date = dateFromKey(task.completed_at);
        const side = el('div', 'report-task-side');
        side.append(el('span', 'report-task-date', `${date.getDate()} ${MONTH_SHORT[date.getMonth()]}`),
            el('span', 'report-task-time', task.seconds ? formatDuration(task.seconds) : ''));
        item.append(dot, main, side);
        list.appendChild(item);
    });

    let more = null;
    if (tasks.length > COMPLETED_PREVIEW) {
        more = el('button', 'report-more', `Ver las ${tasks.length}`);
        more.type = 'button';
        more.addEventListener('click', () => {
            list.querySelectorAll('.report-task.hidden').forEach(item => item.classList.remove('hidden'));
            more.remove();
        });
    }
    const note = el('p', 'report-note', 'El tiempo de cada tarea es el total registrado, no solo el de este periodo.');
    return reportCard('Tareas terminadas', list, more, note);
}

// ============================================
// ¿A qué hora rindes más?
// ============================================

const WEEKDAY_NAMES = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo'];

// grid[día][hora] en segundos, lunes = 0, con la hora LOCAL del navegador.
// Una sesión que cruza de una hora a otra reparte su tiempo entre las dos; el
// total que se reparte es duration_seconds (lo medido), no fin − inicio.
function hourGrid(sessions) {
    const grid = Array.from({ length: 7 }, () => new Array(24).fill(0));
    sessions.forEach(s => {
        const start = parseUtcIso(s.started_at).getTime();
        const end = parseUtcIso(s.ended_at).getTime();
        const span = end - start;
        if (!(span > 0)) return;
        const scale = s.duration_seconds / (span / 1000);
        let t = start;
        while (t < end) {
            const at = new Date(t);
            const hourEnd = new Date(at.getFullYear(), at.getMonth(), at.getDate(), at.getHours() + 1).getTime();
            const sliceEnd = Math.min(end, hourEnd);
            grid[(at.getDay() + 6) % 7][at.getHours()] += ((sliceEnd - t) / 1000) * scale;
            t = sliceEnd;
        }
    });
    return grid;
}

function pad2(n) {
    return String(n).padStart(2, '0');
}

function renderByHour({ sessions }) {
    if (sessions.length === 0) {
        return reportCard('¿A qué hora rindes más?', reportsMessage('Sin tiempo registrado en este periodo.'));
    }
    const grid = hourGrid(sessions);
    const max = Math.max(...grid.flat());

    const heat = el('div', 'report-heat');
    heat.setAttribute('role', 'img');
    heat.setAttribute('aria-label', 'Tiempo por día de la semana y hora');
    heat.appendChild(el('span', 'heat-corner'));
    for (let h = 0; h < 24; h++) {
        heat.appendChild(el('span', 'heat-hour', h % 3 === 0 ? String(h) : ''));
    }
    grid.forEach((hours, day) => {
        heat.appendChild(el('span', 'heat-day', WEEKDAY_INITIALS[(day + 1) % 7]));
        hours.forEach((secs, h) => {
            const cell = el('span', 'heat-cell');
            if (secs > 0) {
                // Raíz: con escala lineal, un solo día largo deja todo lo demás en blanco
                cell.style.setProperty('--level', String(Math.max(0.12, Math.sqrt(secs / max))));
                cell.title = `${WEEKDAY_NAMES[day]}, ${pad2(h)}:00–${pad2(h + 1)}:00: ${formatDuration(Math.round(secs))}`;
            }
            heat.appendChild(cell);
        });
    });

    const byHour = new Array(24).fill(0);
    const byDay = new Array(7).fill(0);
    grid.forEach((hours, day) => hours.forEach((secs, h) => { byHour[h] += secs; byDay[day] += secs; }));
    // La mejor franja de dos horas seguidas: una sola hora es demasiado ruidosa
    let bestStart = 0;
    for (let h = 0; h < 23; h++) {
        if (byHour[h] + byHour[h + 1] > byHour[bestStart] + byHour[bestStart + 1]) bestStart = h;
    }
    const bestDay = byDay.indexOf(Math.max(...byDay));
    const insight = el('p', 'report-note strong',
        `Tu mejor franja: de ${pad2(bestStart)}:00 a ${pad2(bestStart + 2)}:00. El día que más rindes: el ${WEEKDAY_NAMES[bestDay]}.`);
    const note = el('p', 'report-note', 'Horas según el huso horario de este dispositivo.');
    return reportCard('¿A qué hora rindes más?', heat, insight, note);
}

// ============================================
// Cómo se registró el tiempo
// ============================================

const SOURCE_KINDS = [
    { key: 'timer', label: 'Pomodoro', className: 'src-timer' },
    { key: 'stopwatch', label: 'Cronómetro', className: 'src-stopwatch' },
    { key: 'manual', label: 'Registrado a mano', className: 'src-manual' },
];

function renderBySource({ sessions }) {
    const total = sumSeconds(sessions);
    if (total === 0) return null;
    const bySource = {};
    sessions.forEach(s => { bySource[s.source] = (bySource[s.source] || 0) + s.duration_seconds; });

    const bar = el('div', 'report-stack');
    const legend = el('div', 'report-legend');
    SOURCE_KINDS.forEach(kind => {
        const secs = bySource[kind.key] || 0;
        if (secs === 0) return;
        const part = el('span', `report-stack-part ${kind.className}`);
        part.style.width = `${(secs / total) * 100}%`;
        part.title = `${kind.label}: ${formatDuration(secs)}`;
        bar.appendChild(part);
        const item = el('span', 'legend-item');
        item.append(el('i', `legend-swatch ${kind.className}`),
            document.createTextNode(`${kind.label} · ${formatDuration(secs)} (${Math.round((secs / total) * 100)}%)`));
        legend.appendChild(item);
    });
    return reportCard('Cómo se registró', bar, legend);
}

// ============================================
// Exportar a CSV
// ============================================
//
// Un registro por fila, del rango que se ve, para abrirlo en Excel o Google
// Sheets. Se arma en el navegador con los mismos endpoints de la vista.

const CSV_HEADER = ['Fecha', 'Inicio', 'Fin', 'Duración', 'Horas', 'Tarea', 'Proyecto', 'Etiquetas', 'Origen', 'Nota'];

function csvCell(value) {
    let text = value === null || value === undefined ? '' : String(value);
    // Un título que empiece por = + - @ lo ejecutaría Excel como fórmula
    if (/^[=+\-@\t\r]/.test(text)) text = `'${text}`;
    return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function clockOf(date) {
    return `${pad2(date.getHours())}:${pad2(date.getMinutes())}`;
}

function buildTimeCsv(sessions, tasks, projects, tags) {
    const taskById = new Map(tasks.map(t => [t.id, t]));
    const projectById = new Map(projects.map(p => [p.id, p]));
    const tagById = new Map(tags.map(t => [t.id, t]));
    const sourceLabel = Object.fromEntries(SOURCE_KINDS.map(k => [k.key, k.label]));

    const rows = [...sessions]
        .sort((a, b) => a.started_at.localeCompare(b.started_at))
        .map(s => {
            const task = taskById.get(s.task_id);
            const project = projectById.get(s.project_id);
            const minutes = Math.round(s.duration_seconds / 60);
            const tagNames = task ? task.tag_ids.map(id => (tagById.get(id) || {}).name).filter(Boolean) : [];
            return [
                s.session_date,
                clockOf(parseUtcIso(s.started_at)),
                clockOf(parseUtcIso(s.ended_at)),
                `${Math.floor(minutes / 60)}:${pad2(minutes % 60)}`,
                (s.duration_seconds / 3600).toFixed(2),
                task ? task.title : '',
                project ? project.name : '',
                tagNames.join(', '),
                sourceLabel[s.source] || s.source,
                s.note || '',
            ];
        });
    // BOM: sin él, Excel abre el UTF-8 como Latin-1 y rompe los acentos
    return '\uFEFF' + [CSV_HEADER, ...rows].map(row => row.map(csvCell).join(',')).join('\r\n') + '\r\n';
}

function downloadText(filename, text, type) {
    const url = URL.createObjectURL(new Blob([text], { type }));
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function exportReportCsv() {
    const { from, to } = reportsState;
    const label = reportsExportBtn.textContent;
    reportsExportBtn.disabled = true;
    reportsExportBtn.textContent = 'Preparando…';
    try {
        const [sessions, tasksData, projectsData, tagsData] = await Promise.all([
            fetchFocusSessions(from, to),
            apiFetch('/api/tasks'),
            apiFetch('/api/projects?include_inactive=true'),
            apiFetch('/api/tags'),
        ]);
        if (sessions.length === 0) {
            reportsExportBtn.textContent = 'Sin registros en este periodo';
            setTimeout(() => { reportsExportBtn.textContent = label; }, 2500);
            return;
        }
        const csv = buildTimeCsv(sessions, tasksData.tasks, projectsData.projects, tagsData.tags);
        downloadText(`habit-tracker-tiempo_${getDateKey(from)}_${getDateKey(to)}.csv`, csv, 'text/csv;charset=utf-8');
        reportsExportBtn.textContent = label;
    } catch (error) {
        console.error('Error al exportar el reporte:', error);
        reportsExportBtn.textContent = 'No se pudo exportar';
        setTimeout(() => { reportsExportBtn.textContent = label; }, 2500);
    } finally {
        reportsExportBtn.disabled = false;
    }
}

reportsExportBtn.addEventListener('click', exportReportCsv);

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
    reportsState.sawFirstProjects = false;
    reportsState.tagIds.clear();
    reportsBody.replaceChildren();
    initReports();
}

// Al entrar a la vista se pide de nuevo: el tiempo y los hábitos cambian
// desde las otras dos, y a esta escala pedirlo otra vez es barato.
window.viewChangedHooks.push(index => {
    if (index === REPORTS_VIEW_INDEX) loadReports();
});
// Mientras se ve (p. ej. termina un pomodoro), también se refresca. La primera
// carga de proyectos de la sesión no cuenta: al recargar con Reportes abierto,
// la vista ya se pidió al entrar y se pediría dos veces.
window.projectsChangedHooks.push(() => {
    if (!reportsState.sawFirstProjects) {
        reportsState.sawFirstProjects = true;
        return;
    }
    if (isReportsVisible()) loadReports();
});
// El rango inicial se fija ya, al cargar: projects.js puede abrir esta vista
// (última pestaña recordada) antes de que corran los appInitHooks de aquí.
initReports();
window.appLogoutHooks.push(resetReports);
