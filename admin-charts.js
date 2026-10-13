// ============================================
// Gráficas del panel (paso 7): columnas por día o semana y barras horizontales
// ============================================
//
// SVG a mano, sin librerías: la CSP del panel solo deja este origen. Los colores
// van por clase (.s1…, en admin.css), así cambian solos con el tema; los textos
// siempre con textContent. Cada columna es su propia zona de hover y de foco,
// con un tooltip que lista todas sus series: el tooltip ayuda, pero los mismos
// números siguen en la tabla de cada pestaña ("Ver tabla").

const SVG_NS = 'http://www.w3.org/2000/svg';
const chartNumber = new Intl.NumberFormat('es-MX');

function svgNode(tag, attrs = {}) {
    const el = document.createElementNS(SVG_NS, tag);
    for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, value);
    return el;
}

// Un tope "redondo" (1, 2, 2.5 o 5 × 10ⁿ) para el eje, con 3 o 4 líneas
function niceTicks(max) {
    if (max <= 0) return [0, 1];
    const raw = max / 4;
    const pow = 10 ** Math.floor(Math.log10(raw));
    const step = [1, 2, 2.5, 5, 10].map(m => m * pow).find(s => s >= raw);
    const whole = Math.max(step, 1);
    const top = Math.ceil(max / whole) * whole;
    const ticks = [];
    for (let v = 0; v <= top + whole / 2; v += whole) ticks.push(Math.round(v));
    return ticks;
}

// Columna con la punta redondeada (4px) y la base recta
function columnPath(x, y, w, h, round) {
    const r = round ? Math.min(4, h, w / 2) : 0;
    return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
}

function legendNode(series, totals) {
    const legend = document.createElement('ul');
    legend.className = 'chart-legend';
    for (const s of series) {
        const item = document.createElement('li');
        const key = document.createElement('span');
        key.className = `legend-key ${s.cls}`;
        const label = document.createElement('span');
        label.textContent = s.label;
        const value = document.createElement('strong');
        value.textContent = chartNumber.format(totals[s.key] || 0);
        item.append(key, label, value);
        legend.append(item);
    }
    return legend;
}

/**
 * Columnas (apiladas si hay varias series).
 *   series: [{key, label, cls}]   en orden fijo: el color sigue a la serie, no a su lugar
 *   rows:   [{label, tip, values: {key: n}}]  label va en el eje (puede ser ''), tip en el tooltip
 *   height: alto del área de datos; legend: false para una sola serie (el título ya la nombra)
 */
function columnChart({ series, rows, height = 170, legend = series.length > 1, empty = 'Sin datos en estos días.' }) {
    const figure = document.createElement('figure');
    figure.className = 'chart';
    const totals = {};
    for (const row of rows) for (const s of series) totals[s.key] = (totals[s.key] || 0) + (row.values[s.key] || 0);
    const grand = Object.values(totals).reduce((a, b) => a + b, 0);
    // Sin datos, solo el mensaje: una leyenda en ceros no dice nada
    if (legend && grand > 0) figure.append(legendNode(series, totals));
    if (!rows.length || grand === 0) {
        const none = document.createElement('p');
        none.className = 'empty';
        none.textContent = empty;
        figure.append(none);
        return figure;
    }
    const plot = document.createElement('div');
    plot.className = 'chart-plot';
    const tip = document.createElement('div');
    tip.className = 'chart-tip';
    tip.hidden = true;
    figure.append(plot);
    plot.append(tip);

    const draw = () => {
        const width = Math.max(plot.clientWidth, 260);
        const L = 34, R = 6, T = 10, B = 24;
        const plotW = width - L - R;
        const stackTotals = rows.map(r => series.reduce((sum, s) => sum + (r.values[s.key] || 0), 0));
        const ticks = niceTicks(Math.max(...stackTotals));
        const top = ticks[ticks.length - 1];
        const y = v => T + height - (v / top) * height;
        const band = plotW / rows.length;
        const barW = Math.max(2, Math.min(24, band * 0.62));
        const svg = svgNode('svg', { width, height: T + height + B, viewBox: `0 0 ${width} ${T + height + B}`, role: 'img' });

        for (const v of ticks) {
            svg.append(svgNode('line', { x1: L, x2: width - R, y1: y(v), y2: y(v), class: v ? 'chart-grid' : 'chart-base' }));
            const label = svgNode('text', { x: L - 6, y: y(v) + 4, 'text-anchor': 'end', class: 'chart-axis' });
            label.textContent = chartNumber.format(v);
            svg.append(label);
        }
        // Etiquetas del eje x espaciadas para que no se encimen (~56px cada una)
        const every = Math.max(1, Math.ceil(56 / band));
        rows.forEach((row, i) => {
            const cx = L + band * i + band / 2;
            const group = svgNode('g', { class: 'chart-col', tabindex: '0' });
            const parts = [];
            let acc = 0;
            const visible = series.filter(s => (row.values[s.key] || 0) > 0);
            visible.forEach((s, j) => {
                const value = row.values[s.key];
                const y0 = y(acc), y1 = y(acc + value);
                // 2px de superficie entre segmentos apilados
                const gap = j > 0 ? 2 : 0;
                const h = Math.max(0, y0 - y1 - gap);
                if (h > 0) group.append(svgNode('path', { d: columnPath(cx - barW / 2, y1, barW, h, j === visible.length - 1), class: s.cls }));
                acc += value;
                parts.push(`${s.label}: ${chartNumber.format(value)}`);
            });
            const total = stackTotals[i];
            group.setAttribute('aria-label', `${row.tip}: ${series.length > 1 ? parts.join(', ') : chartNumber.format(total)}`);
            // La zona de hover es toda la banda, no solo la columna pintada
            group.prepend(svgNode('rect', { x: L + band * i, y: T, width: band, height, class: 'chart-hit' }));
            group.addEventListener('pointerenter', () => showTip(row, cx));
            group.addEventListener('focus', () => showTip(row, cx));
            group.addEventListener('pointerleave', hideTip);
            group.addEventListener('blur', hideTip);
            svg.append(group);
            if (row.label && i % every === 0) {
                const label = svgNode('text', { x: cx, y: T + height + 16, 'text-anchor': 'middle', class: 'chart-axis' });
                label.textContent = row.label;
                svg.append(label);
            }
        });
        plot.querySelector('svg')?.remove();
        plot.prepend(svg);
    };

    function showTip(row, cx) {
        tip.replaceChildren();
        const title = document.createElement('span');
        title.className = 'chart-tip-title';
        title.textContent = row.tip;
        tip.append(title);
        for (const s of [...series].reverse()) {
            const line = document.createElement('span');
            line.className = 'chart-tip-row';
            const key = document.createElement('span');
            key.className = `tip-key ${s.cls}`;
            const value = document.createElement('strong');
            value.textContent = chartNumber.format(row.values[s.key] || 0);
            const name = document.createElement('span');
            name.textContent = s.label;
            line.append(key, value, name);
            tip.append(line);
        }
        tip.hidden = false;
        // Del lado que tenga espacio: a la derecha de la columna, o a la izquierda al final
        // y nunca fuera de su caja (en el teléfono se saldría de la pantalla)
        const left = cx + 12 + tip.offsetWidth > plot.clientWidth ? cx - 12 - tip.offsetWidth : cx + 12;
        tip.style.left = `${Math.max(0, Math.min(left, plot.clientWidth - tip.offsetWidth))}px`;
    }

    function hideTip() { tip.hidden = true; }

    // Se dibuja al ancho de su caja, y otra vez si la caja cambia (teléfono girado, pestaña nueva)
    if ('ResizeObserver' in window) {
        let last = 0;
        new ResizeObserver(() => {
            if (plot.clientWidth && plot.clientWidth !== last) {
                last = plot.clientWidth;
                draw();
            }
        }).observe(plot);
    } else {
        requestAnimationFrame(draw);
    }
    return figure;
}

/**
 * Barras horizontales con su cifra: rows [{label, value}], de un solo color.
 * `of` es el total contra el que se mide cada barra (las cuentas).
 */
function barList({ rows, of, cls = 's1' }) {
    const list = document.createElement('ul');
    list.className = 'bar-list';
    const max = Math.max(of, 1);
    for (const row of rows) {
        const item = document.createElement('li');
        const label = document.createElement('span');
        label.className = 'bar-label';
        label.textContent = row.label;
        const track = document.createElement('span');
        track.className = 'bar-track';
        track.setAttribute('aria-hidden', 'true');
        if (row.value > 0) {
            const fill = document.createElement('span');
            fill.className = `bar-fill ${cls}`;
            // Por CSSOM: la CSP no deja atributos style, pero sí esto
            fill.style.width = `${Math.max(2, (row.value / max) * 100)}%`;
            track.append(fill);
        }
        const value = document.createElement('strong');
        value.className = 'bar-value';
        value.textContent = chartNumber.format(row.value);
        item.append(label, track, value);
        list.append(item);
    }
    return list;
}
