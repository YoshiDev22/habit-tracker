// ============================================
// Reportes guardados (épica 30, Fase 4)
// ============================================
//
// Pinta un reporte guardado (POST/GET /api/reports) con las cifras que congeló
// al generarse: no vuelve a pedir sesiones. En la pestaña Reportes, con Semana
// o Mes, el botón genera o abre el del periodo que se ve; "Reportes guardados"
// abre la lista. "Imprimir / PDF" imprime solo el modal (@media print en
// styles.css). Usa el, svg, svgText, reportCard, summaryStat, barList,
// MONTH_NAMES y MONTH_SHORT de reports.js, y formatDuration de projects.js.

const savedModal = document.getElementById('savedReportsModal');
const savedTitle = document.getElementById('savedReportTitle');
const savedMeta = document.getElementById('savedReportMeta');
const savedActions = document.getElementById('savedReportActions');
const savedError = document.getElementById('savedReportError');
const savedList = document.getElementById('savedReportList');
const savedBody = document.getElementById('savedReportBody');
const savedBack = document.getElementById('savedReportBack');
const savedReportBtn = document.getElementById('savedReportBtn');
const savedRegenerate = document.getElementById('savedReportRegenerate');
const savedRewrite = document.getElementById('savedReportRewrite');
const savedStatus = document.getElementById('savedReportStatus');
const savedAiUsage = document.getElementById('savedReportAiUsage');
const PRINT_CHART_WIDTH = 680;   // ancho de las gráficas al imprimir: el de una hoja, no el de la pantalla
const KIND_TITLE = { week: 'Reporte semanal', month: 'Reporte mensual' };

const savedState = {
    list: [],          // filas de GET /api/reports (sin cifras)
    loaded: false,
    current: null,     // el reporte abierto, completo
    fromList: false,   // se abrió desde la lista: ‹ vuelve a ella
    readyAt: 0,        // Date.now() desde el que se puede volver a generar (regenerate_in)
    busy: false,       // generando o reescribiendo: un clic más no manda otra petición
    printing: false,   // dibujando para imprimir
    statusTimer: null,
};

// ============================================
// Fechas y textos
// ============================================

function shortDay(key) {
    const d = dateFromKey(key);
    return `${d.getDate()} ${MONTH_SHORT[d.getMonth()]}`;
}

function savedPeriodLabel(report) {
    const from = dateFromKey(report.period_start);
    if (report.kind === 'month') {
        const name = MONTH_NAMES[from.getMonth()];
        return `${name.charAt(0).toUpperCase()}${name.slice(1)} ${from.getFullYear()}`;
    }
    const to = dateFromKey(report.period_end);
    return `${shortDay(report.period_start)} – ${shortDay(report.period_end)} ${to.getFullYear()}`;
}

function savedMetaText(report) {
    // created_at es UTC sin huso: se marca como UTC para verlo en hora local
    const made = new Date(`${report.created_at}Z`);
    const when = made.toLocaleString('es-MX', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
    const parts = [periodSentence(report)];
    if (report.through < report.period_end) parts.push(`con corte al ${longDay(report.through)}`);
    parts.push(`generado el ${when} (${report.trigger === 'auto' ? 'automático' : 'a mano'})`);
    parts.push(report.text_source === 'ai' ? `texto de IA (${report.text_model})` : 'texto de reglas');
    return parts.join(' · ');
}

function aiOn() {
    return Boolean(currentUser && currentUser.modules && currentUser.modules.ai && currentUser.modules.ai.enabled);
}

// ============================================
// El reporte (las secciones de los reportes de ejemplo)
// ============================================

// Horas en decimal, como los ejemplos: 14.3 h · 0.5 h · 0 h
function hoursText(seconds) {
    const value = Math.round((seconds || 0) / 360) / 10;
    return value === 0 ? '0 h' : `${value.toFixed(1)} h`;
}

function weekdayShort(key) {
    const name = WEEKDAY_NAMES[(dateFromKey(key).getDay() + 6) % 7];
    return name.charAt(0).toUpperCase() + name.slice(1, 3);
}

function longDay(key) {
    const d = dateFromKey(key);
    return `${WEEKDAY_NAMES[(d.getDay() + 6) % 7]} ${d.getDate()} de ${MONTH_NAMES[d.getMonth()]}`;
}

// "Semana del 28 de septiembre al 4 de octubre de 2026" · "Septiembre 2026"
function periodSentence(report) {
    if (report.kind === 'month') return savedPeriodLabel(report);
    const from = dateFromKey(report.period_start);
    const to = dateFromKey(report.period_end);
    const left = from.getMonth() === to.getMonth() ? `${from.getDate()}` : `${from.getDate()} de ${MONTH_NAMES[from.getMonth()]}`;
    return `Semana del ${left} al ${to.getDate()} de ${MONTH_NAMES[to.getMonth()]} de ${to.getFullYear()}`;
}

function rangeShort(fromKey, toKey) {
    const from = dateFromKey(fromKey);
    const to = dateFromKey(toKey);
    return from.getMonth() === to.getMonth()
        ? `${from.getDate()}–${to.getDate()} ${MONTH_SHORT[to.getMonth()]}`
        : `${shortDay(fromKey)}–${shortDay(toKey)}`;
}

function para(text, className = 'saved-report-text') {
    return text ? el('p', className, text) : null;
}

function listCard(title, items) {
    if (!items || !items.length) return null;
    const list = el('ul', 'saved-report-points');
    items.forEach(item => list.appendChild(el('li', '', item)));
    return reportCard(title, list);
}

// El texto de un día que no tiene barra: "festivo", "sin registro", "pendiente"
function dayNote(day) {
    if (day.seconds) return '';
    if (day.status === 'missing') return 'sin registro';
    if (day.status === 'pending') return 'pendiente';
    if (day.status === 'today') return 'hoy';
    if (day.status === 'off' && day.reason && day.reason !== 'fin de semana') {
        return day.reason === 'Vacaciones' ? 'vacaciones' : 'festivo';
    }
    return '';
}

// ---------- Métricas: la tabla, periodo anterior contra este ----------

function daysNote(m) {
    const notes = [];
    const missing = m.missing_workdays || [];
    // Uno o dos se nombran ("falta vie 25"); más, se cuentan
    if (missing.length > 2) notes.push(`faltan ${missing.length}`);
    else missing.forEach(d => notes.push(`falta ${weekdayShort(d).toLowerCase()} ${dateFromKey(d).getDate()}`));
    (m.non_working_days || []).forEach(d => {
        if (d.reason) {
            const what = d.reason === 'Vacaciones' ? 'vacaciones' : 'festivo';
            notes.push(`${weekdayShort(d.date).toLowerCase()} ${dateFromKey(d.date).getDate()} ${what}`);
        }
    });
    return notes.length ? ` (${notes.join('; ')})` : '';
}

function metricsTable(report) {
    const m = report.metrics;
    const p = m.previous || {};
    const hasPrev = 'avg_session_seconds' in p;
    const partial = report.through < report.period_end;
    const minutes = s => (s ? `${Math.round(s / 60)} min` : '—');
    const pct = v => (v === null || v === undefined ? '—' : `${v}%`);
    const avg = s => (s ? hoursText(s) : '—');
    const rows = [
        ['Horas totales', hoursText(p.total_seconds),
            hoursText(m.total_seconds) + (m.unconfirmed_seconds
                ? ` (${hoursText(m.total_seconds - m.unconfirmed_seconds)} sin lo no confirmado)` : '')],
        ['Días con registro / hábiles', `${p.active_workdays} de ${p.workdays}${daysNote(p)}`,
            `${m.active_workdays} de ${m.workdays}${partial ? ' hasta hoy' : ''}${daysNote(m)}`],
        ['Promedio por día registrado', avg(p.avg_seconds_per_active_day), avg(m.avg_seconds_per_active_day)],
        ['Duración media por sesión', minutes(p.avg_session_seconds), minutes(m.avg_session_seconds)],
        ['Registrado a mano', pct(p.manual_pct), pct(m.manual_pct)],
        ['Sesiones nocturnas (después de 23 h)', String(p.night_count ?? '—'), String(m.night_sessions.length)],
        ['Fin de semana', hoursText(p.weekend_seconds), hoursText(m.weekend_seconds)],
    ];
    if (m.pomodoros || p.pomodoros) {
        rows.push(['Pomodoros cortados', `${p.pomodoros_cut} de ${p.pomodoros}`, `${m.pomodoros_cut} de ${m.pomodoros}`]);
    }
    const table = el('table', 'saved-metrics');
    const head = el('tr');
    head.append(el('th', '', 'Métrica'));
    if (hasPrev) head.append(el('th', '', rangeShort(p.date_from, p.date_to)));
    head.append(el('th', '', `${rangeShort(report.period_start, report.period_end)}${partial ? ' (parcial)' : ''}`));
    const thead = el('thead');
    thead.appendChild(head);
    const tbody = el('tbody');
    rows.forEach(([label, before, now]) => {
        const tr = el('tr');
        tr.append(el('th', '', label));
        if (hasPrev) tr.append(el('td', '', before));
        tr.append(el('td', '', now));
        tbody.appendChild(tr);
    });
    table.append(thead, tbody);
    const wrap = el('div', 'saved-metrics-wrap');
    wrap.appendChild(table);
    return wrap;
}

// ---------- Gráficas (SVG, colores del tema) ----------

function chartFrame(maxSeconds, W, H, L, T, B, R) {
    const peakHours = Math.max(1, Math.ceil(maxSeconds / 3600));
    const step = peakHours <= 4 ? 1 : peakHours <= 10 ? 2 : Math.ceil(peakHours / 5);
    const top = Math.ceil(peakHours / step) * step;
    const plotH = H - T - B;
    const y = seconds => T + plotH - (seconds / (top * 3600)) * plotH;
    const chart = svg('svg', { viewBox: `0 0 ${W} ${H}`, class: 'report-chart', role: 'img' });
    for (let h = 0; h <= top; h += step) {
        chart.appendChild(svg('line', { x1: L, x2: W - R, y1: y(h * 3600), y2: y(h * 3600), class: 'chart-grid' }));
        chart.appendChild(svgText({ x: L - 6, y: y(h * 3600) + 4, class: 'chart-axis', 'text-anchor': 'end' }, `${h}`));
    }
    return { chart, y, base: T + plotH };
}

function chartWidthFor() {
    if (savedState.printing) return PRINT_CHART_WIDTH;
    return Math.max(300, Math.min(720, (savedBody.clientWidth || 600) - 34));
}

function legendOf(items) {
    const legend = el('div', 'report-legend');
    items.forEach(([cls, label]) => {
        const item = el('span', 'legend-item');
        item.append(el('i', `legend-swatch ${cls}`), document.createTextNode(label));
        legend.appendChild(item);
    });
    return legend;
}

// La semana: dos barras por día, la semana anterior (tenue) y esta
function weekDayChart(report) {
    const m = report.metrics;
    const days = m.days_detail || [];
    if (!days.length) return null;
    const prevDays = (m.previous && m.previous.by_day) || [];
    const shown = days.map((d, i) => ({ ...d, prev: (prevDays[i] || {}).seconds || 0, index: i }))
        .filter(d => d.index < 5 || d.seconds || d.prev);
    const W = chartWidthFor(), H = 210, L = 30, R = 6, T = 18, B = 40;
    const peak = Math.max(...shown.map(d => Math.max(d.seconds, d.prev)));
    const { chart, y, base } = chartFrame(peak, W, H, L, T, B, R);
    chart.setAttribute('aria-label', 'Horas por día, esta semana y la anterior');
    const step = (W - L - R) / shown.length;
    const barW = Math.max(6, Math.min(28, step * 0.32));
    shown.forEach((day, i) => {
        const cx = L + step * i + step / 2;
        const bars = [
            { seconds: day.prev, x: cx - barW - 1, cls: 'chart-bar-prev', label: 'semana anterior' },
            { seconds: day.seconds, x: cx + 1, cls: 'chart-bar', label: 'esta semana' },
        ];
        bars.forEach(bar => {
            if (!bar.seconds) return;
            const top = y(bar.seconds);
            const rect = svg('rect', { x: bar.x, y: top, width: barW, height: base - top, rx: 3, class: bar.cls });
            const tip = svg('title');
            tip.textContent = `${weekdayShort(day.date)} · ${bar.label}: ${hoursText(bar.seconds)}`;
            rect.appendChild(tip);
            chart.appendChild(rect);
        });
        if (day.seconds) {
            chart.appendChild(svgText({ x: cx + 1 + barW / 2, y: y(day.seconds) - 5, class: 'chart-value', 'text-anchor': 'middle' },
                (Math.round(day.seconds / 360) / 10).toFixed(1)));
        }
        const note = dayNote(day);
        if (note) {
            const nx = cx + 1 + barW / 2 + 4;
            chart.appendChild(svgText({ x: nx, y: base - 4, class: 'chart-note', transform: `rotate(-90 ${nx} ${base - 4})` }, note));
        }
        chart.appendChild(svgText({ x: cx, y: H - B + 17, class: 'chart-axis', 'text-anchor': 'middle' }, weekdayShort(day.date)));
        chart.appendChild(svgText({ x: cx, y: H - B + 30, class: 'chart-axis small', 'text-anchor': 'middle' },
            String(dateFromKey(day.date).getDate())));
    });
    const p = m.previous || {};
    const box = el('div', 'saved-chart');
    box.append(el('p', 'saved-chart-title', 'Horas por día'), chart);
    if (p.date_from) {
        box.appendChild(legendOf([
            ['prev', `Semana ${rangeShort(p.date_from, p.date_to)}`],
            ['current', `Semana ${rangeShort(report.period_start, report.period_end)}`],
        ]));
    }
    return box;
}

// El mes: una barra por semana, con su valor
function monthWeekChart(report) {
    const weeks = report.metrics.by_week || [];
    if (!weeks.length) return null;
    const W = chartWidthFor(), H = 210, L = 30, R = 6, T = 18, B = 44;
    const { chart, y, base } = chartFrame(Math.max(...weeks.map(w => w.seconds)), W, H, L, T, B, R);
    chart.setAttribute('aria-label', 'Horas por semana del mes');
    const step = (W - L - R) / weeks.length;
    const barW = Math.max(10, Math.min(60, step * 0.55));
    weeks.forEach((week, i) => {
        const cx = L + step * i + step / 2;
        if (week.seconds) {
            const top = y(week.seconds);
            const rect = svg('rect', { x: cx - barW / 2, y: top, width: barW, height: base - top, rx: 3, class: 'chart-bar' });
            const tip = svg('title');
            tip.textContent = `${rangeShort(week.start, week.end)}: ${hoursText(week.seconds)}`;
            rect.appendChild(tip);
            chart.appendChild(rect);
            chart.appendChild(svgText({ x: cx, y: top - 5, class: 'chart-value', 'text-anchor': 'middle' }, hoursText(week.seconds)));
        }
        chart.appendChild(svgText({ x: cx, y: H - B + 17, class: 'chart-axis', 'text-anchor': 'middle' },
            rangeShort(week.start, week.end)));
        let sub = '';
        if (week.pending) sub = 'pendiente';
        else if (week.workdays < 5) sub = `${week.workdays} ${week.workdays === 1 ? 'día hábil' : 'días hábiles'}`;
        if (sub) chart.appendChild(svgText({ x: cx, y: H - B + 31, class: 'chart-axis small', 'text-anchor': 'middle' }, sub));
    });
    const box = el('div', 'saved-chart');
    box.append(el('p', 'saved-chart-title', 'Horas por semana'), chart);
    return box;
}

function arcPath(cx, cy, r, ir, a0, a1) {
    const large = a1 - a0 > Math.PI ? 1 : 0;
    const p = (rad, a) => `${(cx + rad * Math.cos(a)).toFixed(2)} ${(cy + rad * Math.sin(a)).toFixed(2)}`;
    return `M ${p(r, a0)} A ${r} ${r} 0 ${large} 1 ${p(r, a1)} L ${p(ir, a1)} A ${ir} ${ir} 0 ${large} 0 ${p(ir, a0)} Z`;
}

// Una dona con su leyenda (nombre, horas y %): la identidad no va solo en el color
function donut(caption, rows, total) {
    const box = el('div', 'saved-donut');
    box.appendChild(el('p', 'saved-chart-title', caption));
    if (!total) {
        box.appendChild(el('p', 'saved-report-text muted', 'Sin tiempo registrado.'));
        return box;
    }
    const size = 160, cx = 80, cy = 80, r = 76, ir = 46;
    const chart = svg('svg', { viewBox: `0 0 ${size} ${size}`, class: 'saved-donut-chart', role: 'img', 'aria-label': caption });
    let angle = -Math.PI / 2;
    rows.forEach(row => {
        if (!row.seconds) return;
        const span = (row.seconds / total) * Math.PI * 2;
        // Todo en un proyecto: un arco no puede cerrar el círculo; va un anillo
        const slice = span >= Math.PI * 2 - 1e-6
            ? svg('circle', { cx, cy, r: (r + ir) / 2, class: 'donut-ring', 'stroke-width': r - ir })
            : svg('path', { d: arcPath(cx, cy, r, ir, angle, angle + span), class: 'donut-slice' });
        if (slice.tagName === 'circle') slice.style.stroke = row.color || 'var(--text-muted)';
        else slice.style.fill = row.color || 'var(--text-muted)';
        const tip = svg('title');
        tip.textContent = `${row.name}: ${hoursText(row.seconds)} (${row.pct}%)`;
        slice.appendChild(tip);
        chart.appendChild(slice);
        angle += span;
    });
    const legend = el('ul', 'saved-donut-legend');
    rows.forEach(row => {
        const item = el('li');
        const dot = el('i', 'report-bar-dot');
        if (row.color) dot.style.background = row.color;
        item.append(dot, el('span', '', row.name), el('span', 'saved-donut-value', `${hoursText(row.seconds)} (${row.pct}%)`));
        legend.appendChild(item);
    });
    const body = el('div', 'saved-donut-body');
    body.append(chart, legend);
    box.appendChild(body);
    return box;
}

function whereTimeWent(report) {
    const m = report.metrics;
    if (!m.total_seconds) return null;
    const p = m.previous || {};
    const donuts = el('div', 'saved-donuts');
    if (p.by_project) {
        donuts.appendChild(donut(`${rangeShort(p.date_from, p.date_to)} · ${hoursText(p.total_seconds)}`,
            p.by_project, p.total_seconds));
    }
    donuts.appendChild(donut(`${rangeShort(report.period_start, report.period_end)} · ${hoursText(m.total_seconds)}`,
        m.by_project, m.total_seconds));
    const parts = [donuts];
    if (m.top_tasks.length) {
        parts.push(el('p', 'saved-chart-title', report.kind === 'week' ? 'Tareas principales de esta semana' : 'Tareas principales'));
        parts.push(barList(m.top_tasks.map(task => ({ name: task.title, color: task.color, seconds: task.seconds })), null, hoursText));
        // Leyenda de proyectos: el color de cada barra es el de su proyecto
        const seen = new Map();
        m.top_tasks.forEach(task => { if (task.project && !seen.has(task.project)) seen.set(task.project, task.color); });
        if (seen.size > 1) {
            const legend = el('div', 'report-legend');
            seen.forEach((color, name) => {
                const item = el('span', 'legend-item');
                const swatch = el('i', 'legend-swatch');
                if (color) swatch.style.background = color;
                item.append(swatch, document.createTextNode(name));
                legend.appendChild(item);
            });
            parts.push(legend);
        }
    }
    return reportCard('¿En qué se fue el tiempo?', ...parts);
}

// El mes: el proyecto principal por etiqueta ("Tesis por actividad")
function topProjectByTag(report) {
    const t = report.metrics.top_project_tags;
    if (report.kind !== 'month' || !t || !t.tags || t.tags.length < 2) return null;
    const rows = t.tags.map(tag => ({ name: tag.name, color: tag.color, seconds: tag.seconds }));
    if (t.untagged_seconds) rows.push({ name: 'Sin etiqueta', seconds: t.untagged_seconds, muted: true });
    return reportCard(`${t.project} por actividad`, barList(rows, null, hoursText),
        el('p', 'report-compare-small',
            `Las horas suman más de ${hoursText(t.seconds)} porque una sesión cuenta en cada etiqueta de su tarea.`));
}

function closingCard(closing) {
    if (!closing) return null;
    if (typeof closing === 'string') return reportCard('Cierre', para(closing));   // reportes de antes
    const box = el('div', 'saved-closing');
    [['Bien hecho:', closing.well_done], ['Tip:', closing.tip]].forEach(([label, text]) => {
        if (!text) return;
        const item = el('p', 'saved-closing-item');
        item.append(el('strong', '', label), document.createTextNode(` ${text}`));
        box.appendChild(item);
    });
    return reportCard('Cierre', box);
}

function reviewLine(item) {
    const parts = [`${shortDay(item.date)} ${item.start}–${item.end}`, hoursText(item.seconds)];
    if (item.task) parts.push(item.task);
    return parts.join(' · ');
}

function savedReview(m) {
    const r = m.to_review;
    const groups = [
        ['Sin confirmar', r.unconfirmed.map(reviewLine)],
        ['De más de 4 h', r.long_sessions.map(reviewLine)],
        ['Se enciman con la siguiente', r.overlaps.map(o => `${reviewLine(o.first)} / ${reviewLine(o.second)}`)],
        ['Duración mayor que su horario', r.inconsistent.map(reviewLine)],
    ].filter(([, items]) => items.length);
    if (!groups.length) return null;
    const box = el('div', 'saved-report-review');
    groups.forEach(([title, items]) => {
        box.appendChild(el('p', 'work-subtitle', title));
        const list = el('ul', 'saved-report-points');
        items.forEach(text => list.appendChild(el('li', '', text)));
        box.appendChild(list);
    });
    return reportCard('Registros a revisar', box);
}

function nextStepsTitle(report) {
    if (report.kind === 'week') return 'Para la próxima semana';
    const end = dateFromKey(report.period_end);
    return `Metas para ${MONTH_NAMES[(end.getMonth() + 1) % 12]}`;
}

function renderSavedReport(report) {
    const m = report.metrics;
    const t = report.text || {};
    const review = m.unconfirmed_seconds
        ? el('p', 'report-review-note', `Incluye ${hoursText(m.unconfirmed_seconds)} sin confirmar.`)
        : null;
    savedBody.replaceChildren(...[
        reportCard('Resumen', para(t.summary), para(t.data_cleanup, 'saved-report-text muted'), review),
        reportCard('Métricas', metricsTable(report), report.kind === 'month' ? monthWeekChart(report) : weekDayChart(report)),
        whereTimeWent(report),
        topProjectByTag(report),
        listCard('Patrones', t.patterns),
        listCard('Legibilidad y etiquetado', t.legibility),
        t.comparison ? reportCard('Comparativa', para(t.comparison)) : null,
        listCard('Observaciones', t.observations),
        listCard(nextStepsTitle(report), t.next_steps),
        listCard('Recomendaciones', t.recommendations),   // reportes de antes
        closingCard(t.closing),
        savedReview(m),
    ].filter(Boolean));
}

// ============================================
// El modal: lista o reporte
// ============================================

function showSavedError(message) {
    if (message) showError(savedError, message);
    else savedError.classList.add('hidden');
}

function openSavedModal() {
    showModal(savedModal);
}

function closeSavedModal() {
    clearTimeout(savedState.statusTimer);
    savedStatus.textContent = '';
    hideModal(savedModal);
    document.body.classList.remove('saved-report-open');
    savedState.current = null;
}

// "Reporte generado ✓ 11:22 p.m." o "Espera 25 s…": se borra solo
function showSavedStatus(text, ms = 6000) {
    clearTimeout(savedState.statusTimer);
    savedStatus.textContent = text;
    if (ms) savedState.statusTimer = setTimeout(() => { savedStatus.textContent = ''; }, ms);
}

function secondsToWait() {
    return Math.max(0, Math.ceil((savedState.readyAt - Date.now()) / 1000));
}

// Con la IA encendida: cuántos textos le quedan hoy a la cuenta
async function refreshAiUsage() {
    savedAiUsage.hidden = true;
    if (!aiOn()) return;
    try {
        const usage = await apiFetch('/api/reports/ai-usage');
        if (!usage.configured) return;
        savedAiUsage.textContent = `IA: te quedan ${usage.remaining} de ${usage.limit} textos hoy.`;
        savedAiUsage.hidden = false;
    } catch (error) {
        // Sin el dato no pasa nada: el servidor igual pone el límite
    }
}

function showSavedReport(report) {
    savedState.current = report;
    savedState.readyAt = Date.now() + (report.regenerate_in || 0) * 1000;
    savedTitle.textContent = `${KIND_TITLE[report.kind]} de tiempo`;
    savedMeta.textContent = savedMetaText(report);
    savedActions.hidden = false;
    savedRewrite.hidden = !aiOn();
    savedRewrite.textContent = report.text_source === 'ai' ? 'Reescribir con IA otra vez' : 'Reescribir con IA';
    savedBack.hidden = !savedState.fromList;
    savedList.replaceChildren();
    savedList.hidden = true;
    document.body.classList.add('saved-report-open');
    renderSavedReport(report);
    // Por qué no lo escribió la IA, si le tocaba (límite, error, sin configurar)
    if (report.text_note) {
        const note = report.text_note;
        showSavedError(`El texto salió de las reglas: ${note.charAt(0).toLowerCase()}${note.slice(1)}.`);
    }
    savedModal.querySelector('.modal-content').scrollTop = 0;
    refreshAiUsage();
}

function showSavedLoading(text) {
    savedTitle.textContent = text;
    savedMeta.textContent = '';
    savedActions.hidden = true;
    savedBack.hidden = true;
    savedList.hidden = true;
    savedBody.replaceChildren(el('p', 'reports-message', 'Un momento…'));
}

async function loadSavedList() {
    try {
        const data = await apiFetch('/api/reports');
        savedState.list = data.reports;
        savedState.loaded = true;
    } catch (error) {
        console.error('No se pudieron cargar los reportes guardados:', error);
    }
    syncSavedReportButton();
}

function renderSavedList() {
    savedState.current = null;
    document.body.classList.remove('saved-report-open');
    savedTitle.textContent = 'Reportes guardados';
    savedMeta.textContent = 'Los automáticos salen cada lunes (la semana anterior) y cada día 1 (el mes anterior), si hubo tiempo registrado.';
    savedActions.hidden = true;
    savedBack.hidden = true;
    savedBody.replaceChildren();
    savedList.hidden = false;
    if (!savedState.list.length) {
        savedList.replaceChildren(el('li', 'work-empty',
            'Aún no hay reportes. Genera uno desde Reportes, con Semana o Mes, o espera al primero automático.'));
        return;
    }
    savedList.replaceChildren(...savedState.list.map(report => {
        const item = el('li');
        const button = el('button', 'saved-report-row');
        button.type = 'button';
        button.dataset.id = String(report.id);
        const text = el('span', 'saved-report-row-text');
        text.append(el('strong', '', savedPeriodLabel(report)),
            el('small', '', `${KIND_TITLE[report.kind]} · ${formatDuration(report.total_seconds)}`));
        button.append(text, el('span', 'settings-item-go', '›'));
        item.appendChild(button);
        return item;
    }));
}

async function openSavedList() {
    showSavedError(null);
    savedState.fromList = false;
    openSavedModal();
    if (!savedState.loaded) {
        showSavedLoading('Reportes guardados');
        await loadSavedList();
    }
    renderSavedList();
}

async function openSavedReportById(id) {
    showSavedError(null);
    showSavedLoading('Reporte');
    try {
        showSavedReport(await apiFetch(`/api/reports/${id}`));
    } catch (error) {
        showSavedError(error.message);
    }
}

// Genera (o regenera) el reporte de un periodo y lo muestra
// Genera el reporte de un periodo. Si ya hay uno abierto (Regenerar), se queda
// a la vista mientras tanto, y si falla (p. ej. la espera) no se pierde.
async function generateSavedReport(kind, periodStart) {
    const regenerating = Boolean(savedState.current);
    showSavedError(null);
    if (regenerating) {
        savedState.busy = true;
        savedRegenerate.disabled = true;
        savedRegenerate.textContent = 'Generando…';
    } else {
        showSavedLoading('Generando reporte…');
    }
    try {
        const report = await apiFetch('/api/reports', {
            method: 'POST',
            json: { kind, period_start: periodStart, today: getDateKey(new Date()) },
        });
        showSavedReport(report);
        showSavedStatus(`Reporte generado ✓ ${new Date().toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' })}`);
    } catch (error) {
        if (error.status === 429) showSavedStatus(error.message);
        else showSavedError(error.message);
    } finally {
        savedState.busy = false;
        savedRegenerate.disabled = false;
        savedRegenerate.textContent = 'Regenerar';
    }
    await loadSavedList();
}

// Un clic dentro de la espera no manda nada: dice cuánto falta
function blockedByCooldown() {
    if (savedState.busy) return true;
    const wait = secondsToWait();
    if (!wait) return false;
    showSavedStatus(`Acabas de generarlo. Espera ${wait} s para volver a hacerlo.`, 4000);
    return true;
}

// ============================================
// El botón de la pestaña Reportes
// ============================================

function savedForCurrentRange() {
    const { kind, from } = reportsState;
    if (kind === 'custom' || !from) return null;
    const start = getDateKey(from);
    return savedState.list.find(r => r.kind === kind && r.period_start === start) || null;
}

// Lo llama setRange() de reports.js en cada cambio de periodo
function syncSavedReportButton() {
    const custom = reportsState.kind === 'custom';
    savedReportBtn.hidden = custom;
    savedReportBtn.textContent = savedForCurrentRange() ? 'Ver reporte' : 'Generar reporte';
}

savedReportBtn.addEventListener('click', async () => {
    const { kind, from } = reportsState;
    if (kind === 'custom') return;
    savedState.fromList = false;
    openSavedModal();
    const existing = savedForCurrentRange();
    if (existing) await openSavedReportById(existing.id);
    else await generateSavedReport(kind, getDateKey(from));
});

document.getElementById('savedReportsListBtn').addEventListener('click', openSavedList);

savedList.addEventListener('click', (event) => {
    const row = event.target.closest('.saved-report-row');
    if (!row) return;
    savedState.fromList = true;
    openSavedReportById(Number(row.dataset.id));
});

savedBack.addEventListener('click', () => {
    showSavedError(null);
    renderSavedList();
});

savedRegenerate.addEventListener('click', () => {
    const report = savedState.current;
    if (!report || blockedByCooldown()) return;
    generateSavedReport(report.kind, report.period_start);
});

savedRewrite.addEventListener('click', async () => {
    const report = savedState.current;
    if (!report || blockedByCooldown()) return;
    showSavedError(null);
    savedState.busy = true;
    savedRewrite.disabled = true;
    savedRewrite.textContent = 'Escribiendo…';
    try {
        showSavedReport(await apiFetch(`/api/reports/${report.id}/rewrite`, { method: 'POST' }));
        showSavedStatus(`Texto reescrito ✓ ${new Date().toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' })}`);
    } catch (error) {
        // El reporte se queda como estaba
        savedRewrite.textContent = report.text_source === 'ai' ? 'Reescribir con IA otra vez' : 'Reescribir con IA';
        if (error.status === 429) showSavedStatus(error.message);
        else showSavedError(error.message);
        refreshAiUsage();
    } finally {
        savedState.busy = false;
        savedRewrite.disabled = false;
    }
});

// Imprimir: las gráficas se dibujan al ancho de una hoja (dibujadas al de la
// pantalla, en el teléfono salían enormes y con las fechas encimadas) y se
// vuelven a dibujar al terminar. También si se imprime desde el menú del navegador.
function renderForPrint(printing) {
    if (!savedState.current || savedState.printing === printing) return;
    savedState.printing = printing;
    renderSavedReport(savedState.current);
}

window.addEventListener('beforeprint', () => renderForPrint(true));
window.addEventListener('afterprint', () => renderForPrint(false));
document.getElementById('savedReportPrint').addEventListener('click', () => {
    renderForPrint(true);
    window.print();
});
document.getElementById('savedReportClose').addEventListener('click', closeSavedModal);
savedModal.querySelector('.modal-overlay').addEventListener('click', closeSavedModal);
document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape' || savedModal.classList.contains('hidden')) return;
    event.preventDefault();
    if (savedState.current && savedState.fromList) renderSavedList();
    else closeSavedModal();
});

// La lista se pide al entrar a Reportes (es corta: sin cifras)
window.viewChangedHooks.push(viewId => {
    if (viewId === 'reports' && getToken()) loadSavedList();
});
window.appLogoutHooks.push(() => {
    savedState.list = [];
    savedState.loaded = false;
    closeSavedModal();
});
