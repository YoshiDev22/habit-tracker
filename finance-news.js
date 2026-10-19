// ============================================
// Finanzas: la campana de avisos, sus Novedades y su aviso de versión nueva.
// La campana lee los avisos de la cuenta (GET /api/notices) pero solo enseña los
// que tocan a Finanzas (FIN_BELL_KINDS): los de Habit Tracker (día sin anotar,
// registro por confirmar, reportes, sus Novedades) se quedan en su campana. Finanzas lleva su propio
// número (FINANCE_VERSION, CLAUDE.md › Versionado): al entrar, si este
// dispositivo no ha visto las de la versión actual, se enseñan en una hoja; el
// panel lateral › Novedades las lista todas. Una página abierta no se actualiza
// sola: si el servidor ya corre otra versión (de Finanzas o de la app), una franja
// ofrece Actualizar, como en la app. Usa finance-app.js y finance-data.js.
// ============================================

const finNews = { versions: [], current: null, pageVersions: null, lastCheck: 0, dismissed: null };
const finNewsSheet = document.getElementById('finNewsSheet');
const FIN_NEWS_SEEN = 'finance_novedades_seen';
const FIN_UPDATE_EVERY_MS = 30 * 60 * 1000;
const FIN_UPDATE_ON_RETURN_MS = 5 * 60 * 1000;

function finCompareVersions(a, b) {
    const pa = String(a).split('.').map(Number);
    const pb = String(b).split('.').map(Number);
    for (let i = 0; i < 3; i += 1) {
        if ((pa[i] || 0) !== (pb[i] || 0)) return (pa[i] || 0) < (pb[i] || 0) ? -1 : 1;
    }
    return 0;
}

// "**Menú de cada cuenta**: …" con sus negritas, sin innerHTML
function finRichText(text) {
    const node = document.createElement('span');
    text.split(/(\*\*[^*]+\*\*)/).forEach(part => {
        if (part.startsWith('**') && part.endsWith('**') && part.length > 4) node.appendChild(el('strong', '', part.slice(2, -2)));
        else if (part) node.appendChild(document.createTextNode(part));
    });
    return node;
}

function finNewsBlock(entry) {
    const block = el('section', 'fin-news-version');
    const date = entry.date ? ` · ${finShortDate(entry.date)}` : '';
    block.appendChild(el('h3', 'fin-stat-label', `Finanzas ${entry.version}${date}`));
    entry.sections.forEach(section => {
        block.appendChild(el('p', 'fin-news-section', section.title));
        const list = el('ul', 'fin-news-list');
        section.items.forEach(item => {
            const li = el('li');
            li.appendChild(finRichText(item));
            list.appendChild(li);
        });
        block.appendChild(list);
    });
    return block;
}

async function finLoadNews() {
    try {
        const data = await apiFetch('/api/novedades/finance');
        finNews.versions = data.versions;
        finNews.current = data.current;
    } catch (error) {
        return;   // sin Novedades, la página sigue igual
    }
    let seen = null;
    try { seen = localStorage.getItem(FIN_NEWS_SEEN); } catch (e) { /* sin localStorage */ }
    // La primera vez en este dispositivo empieza al día: no enseña la historia
    if (!seen) {
        finMarkNewsSeen();
        return;
    }
    const unseen = finNews.versions.filter(v => finCompareVersions(v.version, seen) > 0);
    if (!unseen.length) return;
    document.getElementById('finNewsBody').replaceChildren(...unseen.map(finNewsBlock));
    openFinSheet(finNewsSheet);
}

function finMarkNewsSeen() {
    try { if (finNews.current) localStorage.setItem(FIN_NEWS_SEEN, finNews.current); } catch (e) { /* sin localStorage */ }
}

function closeFinNews() {
    finMarkNewsSeen();
    closeFinSheet(finNewsSheet);
}

finSheetDismiss.set('finNewsSheet', closeFinNews);
document.getElementById('finNewsOk').addEventListener('click', closeFinNews);

// La página del panel lateral: todas, de la más nueva a la más vieja
function finRenderNewsPage() {
    const box = document.getElementById('finNewsAll');
    box.replaceChildren(...(finNews.versions.length ? finNews.versions.map(finNewsBlock)
        : [el('p', 'fin-hint', 'Aún no hay novedades.')]));
    finMarkNewsSeen();
}

// ---------- ¿Hay versión nueva? ----------

async function finCheckUpdate() {
    finNews.lastCheck = Date.now();
    let info;
    try {
        info = await apiFetch('/api/version');
    } catch (error) {
        return;
    }
    const now = `${info.version}|${info.finance_version}`;
    if (!finNews.pageVersions) {
        finNews.pageVersions = now;   // con lo que abrió esta página
        return;
    }
    document.getElementById('finUpdateBanner').hidden = now === finNews.pageVersions || now === finNews.dismissed;
}

document.getElementById('finUpdateReload').addEventListener('click', () => location.reload());
document.getElementById('finUpdateDismiss').addEventListener('click', async () => {
    try {
        const info = await apiFetch('/api/version');
        finNews.dismissed = `${info.version}|${info.finance_version}`;
    } catch (error) { /* se vuelve a ofrecer en la siguiente revisión */ }
    document.getElementById('finUpdateBanner').hidden = true;
});
document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible' && Date.now() - finNews.lastCheck > FIN_UPDATE_ON_RETURN_MS) finCheckUpdate();
});
setInterval(finCheckUpdate, FIN_UPDATE_EVERY_MS);

// ---------- La campana: los avisos de tu cuenta ----------

const finNoticesSheet = document.getElementById('finNoticesSheet');
const finNotices = { list: [], unread: 0, lastLoad: 0 };
// Los anuncios para todas las cuentas (un mantenimiento) y los mensajes del panel
// para la tuya; los avisos propios de Finanzas (p. ej. un pago por vencer) irán aquí
const FIN_BELL_KINDS = ['announcement', 'message'];

async function finLoadNotices() {
    finNotices.lastLoad = Date.now();
    try {
        const data = await apiFetch(`/api/notices?today=${finToday()}`);
        finNotices.list = data.notices.filter(n => FIN_BELL_KINDS.includes(n.kind));
        finNotices.unread = finNotices.list.filter(n => n.status === 'pending' || (n.status === 'info' && !n.read)).length;
    } catch (error) {
        return;   // sin avisos, la campana se queda como estaba
    }
    const count = document.getElementById('finBellCount');
    count.hidden = !finNotices.unread;
    count.textContent = finNotices.unread > 9 ? '9+' : String(finNotices.unread);
    document.getElementById('finBellBtn').setAttribute('aria-label',
        finNotices.unread ? `Avisos: ${finNotices.unread} sin ver` : 'Avisos');
}

// El aviso de "Ya tienes acceso a Finanzas" es, aquí, su bienvenida
const FIN_WELCOME = {
    title: 'Te damos la bienvenida a Finanzas',
    detail: 'Empieza por tus cuentas, en la pestaña Cuentas. Con tu inicial, arriba a la izquierda, '
        + 'están la configuración, tus datos y las novedades.',
};

function finNoticeRow(notice) {
    const row = el('div', `fin-notice ${notice.status}`);
    const text = notice.access_module === 'finance' ? FIN_WELCOME : notice;
    row.append(el('strong', '', text.title));
    if (text.detail) row.appendChild(el('p', 'fin-hint', text.detail));
    return row;
}

async function openFinNotices() {
    await finLoadNotices();
    const groups = [
        ['Pendientes', finNotices.list.filter(n => n.status === 'pending')],
        ['Avisos', finNotices.list.filter(n => n.status === 'info')],
        ['Hechos', finNotices.list.filter(n => n.status === 'done' || n.status === 'dismissed').slice(0, 10)],
    ].filter(([, list]) => list.length);
    document.getElementById('finNoticesBody').replaceChildren(...(groups.length
        ? groups.flatMap(([title, list]) => [el('p', 'fin-stat-label fin-notice-group', title), ...list.map(finNoticeRow)])
        : [el('p', 'fin-hint', 'No tienes avisos.')]));
    openFinSheet(finNoticesSheet);
    // Abrir la campana lee solo sus avisos: los de Habit Tracker siguen sin leer en la app
    const unread = finNotices.list.filter(n => n.status === 'info' && !n.read).map(n => n.id);
    if (unread.length) {
        try {
            await apiFetch('/api/notices/read', { method: 'POST', json: { ids: unread } });
        } catch (error) { /* se leerán la próxima vez */ }
        await finLoadNotices();
    }
}

document.getElementById('finBellBtn').addEventListener('click', openFinNotices);
document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible' && Date.now() - finNotices.lastLoad > 60 * 1000) finLoadNotices();
});
