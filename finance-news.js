// ============================================
// Finanzas: sus Novedades y su aviso de versión nueva. Finanzas lleva su propio
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
