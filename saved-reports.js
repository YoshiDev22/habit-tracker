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
const KIND_TITLE = { week: 'Reporte semanal', month: 'Reporte mensual' };

const savedState = {
    list: [],          // filas de GET /api/reports (sin cifras)
    loaded: false,
    current: null,     // el reporte abierto, completo
    fromList: false,   // se abrió desde la lista: ‹ vuelve a ella
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

// 9.5 -> 09:30; 24.5 (pasada la medianoche) -> 00:30
function clockFromHours(hours) {
    const total = Math.round(hours * 60);
    return `${String(Math.floor(total / 60) % 24).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`;
}

function savedMetaText(report) {
    // created_at es UTC sin huso: se marca como UTC para verlo en hora local
    const made = new Date(`${report.created_at}Z`);
    const when = made.toLocaleString('es-MX', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
    const parts = [`Generado el ${when}`, report.trigger === 'auto' ? 'automático' : 'a mano'];
    if (report.through < report.period_end) parts.push(`con datos hasta el ${shortDay(report.through)}`);
    return parts.join(' · ');
}

// ============================================
// El reporte
// ============================================

function textCard(title, items, emptyText) {
    if (!items || !items.length) {
        return emptyText ? reportCard(title, el('p', 'saved-report-text muted', emptyText)) : null;
    }
    const list = el('ul', 'saved-report-points');
    items.forEach(item => list.appendChild(el('li', '', item)));
    return reportCard(title, list);
}

function savedSummary(report) {
    const m = report.metrics;
    const prev = (m.previous && m.previous.total_seconds) || 0;
    const grid = el('div', 'report-stats');
    grid.append(
        summaryStat(formatDuration(m.total_seconds), 'tiempo total'),
        summaryStat(`${m.active_workdays} de ${m.workdays}`, 'días hábiles con tiempo'),
        summaryStat(m.avg_seconds_per_active_day ? formatDuration(m.avg_seconds_per_active_day) : '—', 'promedio por día con tiempo'),
        summaryStat(m.median_seconds_per_active_day ? formatDuration(m.median_seconds_per_active_day) : '—', 'mediana por día con tiempo'),
    );
    const before = report.kind === 'week' ? 'la semana anterior' : 'el mes anterior';
    let compare = null;
    if (prev) {
        const diff = m.total_seconds - prev;
        compare = el('p', `report-compare ${diff >= 0 ? 'up' : 'down'}`,
            Math.abs(diff) < 60 ? `Igual que ${before}`
                : `${diff > 0 ? '+' : '−'}${formatDuration(Math.abs(diff))} vs. ${before} (${formatDuration(prev)})`);
    }
    const lead = el('p', 'saved-report-text', report.text.summary);
    const review = m.unconfirmed_seconds
        ? el('p', 'report-review-note', `⚠ Incluye ${formatDuration(m.unconfirmed_seconds)} sin confirmar.`)
        : null;
    return reportCard('Resumen', grid, compare, lead, review);
}

// Barras por día; los días no hábiles (fin de semana, festivos, vacaciones) sombreados
function savedByDay(m) {
    const days = m.by_day;
    if (!days.length) return null;
    const peakHours = Math.max(1, Math.ceil(Math.max(...days.map(d => d.seconds)) / 3600));
    const hourStep = peakHours <= 4 ? 1 : Math.ceil(peakHours / 4);
    const maxHours = Math.ceil(peakHours / hourStep) * hourStep;
    const W = Math.max(280, Math.min(760, (savedBody.clientWidth || 600) - 34));
    const H = 190, L = 34, R = 6, T = 10, B = 34;
    const plotW = W - L - R, plotH = H - T - B;
    const step = plotW / days.length;
    const barW = Math.max(3, Math.min(34, step * 0.62));
    const y = seconds => T + plotH - (seconds / (maxHours * 3600)) * plotH;
    const chart = svg('svg', { viewBox: `0 0 ${W} ${H}`, class: 'report-chart', role: 'img',
        'aria-label': 'Tiempo registrado por día' });
    for (let h = 0; h <= maxHours; h += hourStep) {
        chart.appendChild(svg('line', { x1: L, x2: W - R, y1: y(h * 3600), y2: y(h * 3600), class: 'chart-grid' }));
        chart.appendChild(svgText({ x: L - 6, y: y(h * 3600) + 4, class: 'chart-axis', 'text-anchor': 'end' }, `${h}h`));
    }
    const labelEvery = days.length <= 14 ? 1 : 5;
    days.forEach((day, i) => {
        const date = dateFromKey(day.date);
        const cx = L + step * i + step / 2;
        if (!day.workday) {
            chart.appendChild(svg('rect', { x: L + step * i + 1, y: T, width: Math.max(1, step - 2), height: plotH,
                class: 'chart-rest' }));
        }
        if (day.seconds > 0) {
            const top = y(day.seconds);
            const bar = svg('rect', { x: cx - barW / 2, y: top, width: barW, height: T + plotH - top, rx: 3,
                class: 'chart-bar' });
            const tip = svg('title');
            tip.textContent = `${shortDay(day.date)}: ${formatDuration(day.seconds)}`;
            bar.appendChild(tip);
            chart.appendChild(bar);
        }
        if (i % labelEvery === 0) {
            const top = days.length <= 7 ? WEEKDAY_INITIALS[date.getDay()] : String(date.getDate());
            chart.appendChild(svgText({ x: cx, y: H - B + 16, class: 'chart-axis', 'text-anchor': 'middle' }, top));
            if (days.length <= 7) {
                chart.appendChild(svgText({ x: cx, y: H - B + 29, class: 'chart-axis small', 'text-anchor': 'middle' },
                    String(date.getDate())));
            }
        }
    });
    let legend = null;
    if (days.some(d => !d.workday)) {
        legend = el('div', 'report-legend');
        const item = el('span', 'legend-item');
        item.append(el('i', 'legend-swatch rest'), document.createTextNode('Día no hábil'));
        legend.appendChild(item);
    }
    return reportCard('Tiempo por día', chart, legend);
}

function savedSchedule(m) {
    const grid = el('div', 'report-stats');
    if (m.schedule) {
        grid.appendChild(summaryStat(`${clockFromHours(m.schedule.usual_start)} – ${clockFromHours(m.schedule.usual_end)}`,
            'horario habitual (días hábiles)'));
    }
    grid.append(
        summaryStat(String(m.night_sessions.length), m.night_sessions.length === 1 ? 'sesión nocturna' : 'sesiones nocturnas'),
        summaryStat(formatDuration(m.weekend_seconds), 'en fin de semana'),
        summaryStat(formatDuration(m.seconds_after_16h), 'después de las 16 h'),
    );
    if (m.manual_pct !== null) grid.appendChild(summaryStat(`${m.manual_pct}%`, 'registrado a mano'));
    if (m.pomodoros) grid.appendChild(summaryStat(`${m.pomodoros_cut} de ${m.pomodoros}`, 'pomodoros cortados'));
    return reportCard('Horario y ritmo', grid);
}

function reviewLine(item) {
    const parts = [`${shortDay(item.date)} ${item.start}–${item.end}`, formatDuration(item.seconds)];
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
    return reportCard('A revisar', box);
}

function renderSavedReport(report) {
    const m = report.metrics;
    const t = report.text;
    const total = m.total_seconds;
    savedBody.replaceChildren(...[
        savedSummary(report),
        savedByDay(m),
        m.by_project.length ? reportCard('Por proyecto', barList(m.by_project, total)) : null,
        m.top_tasks.length ? reportCard('Tareas con más tiempo', barList(m.top_tasks.map(task => ({
            name: task.title, color: task.color, seconds: task.seconds,
            note: task.project ? ` · ${task.project}` : '',
        })), total)) : null,
        m.by_tag.length ? reportCard('Por etiqueta', barList(m.by_tag, null),
            el('p', 'report-compare-small', 'Una sesión cuenta en cada etiqueta de su tarea: no se suman entre sí.')) : null,
        total ? savedSchedule(m) : null,
        savedReview(m),
        textCard('Observaciones', t.observations),
        textCard('Recomendaciones', t.recommendations, 'Nada que señalar en este periodo.'),
        reportCard('Cierre', el('p', 'saved-report-text', t.closing)),
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
    hideModal(savedModal);
    document.body.classList.remove('saved-report-open');
    savedState.current = null;
}

function showSavedReport(report) {
    savedState.current = report;
    savedTitle.textContent = `${KIND_TITLE[report.kind]} · ${savedPeriodLabel(report)}`;
    savedMeta.textContent = savedMetaText(report);
    savedActions.hidden = false;
    savedBack.hidden = !savedState.fromList;
    savedList.replaceChildren();
    savedList.hidden = true;
    document.body.classList.add('saved-report-open');
    renderSavedReport(report);
    savedModal.querySelector('.modal-content').scrollTop = 0;
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
async function generateSavedReport(kind, periodStart) {
    showSavedError(null);
    showSavedLoading('Generando reporte…');
    try {
        const report = await apiFetch('/api/reports', {
            method: 'POST',
            json: { kind, period_start: periodStart, today: getDateKey(new Date()) },
        });
        showSavedReport(report);
    } catch (error) {
        showSavedError(error.message);
    }
    await loadSavedList();
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
    if (!report) return;
    generateSavedReport(report.kind, report.period_start);
});

document.getElementById('savedReportPrint').addEventListener('click', () => window.print());
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
